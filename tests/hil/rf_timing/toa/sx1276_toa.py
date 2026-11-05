"""Deterministic Semtech SX1276 LoRa Time-on-Air (ToA) calculator.

Implements official airtime equations from:
Semtech SX1276/77/78/79 Datasheet (Rev 7, March 2015), Sections 4.1.1.5 - 4.1.1.7.

All outputs are labeled CALCULATED. Calculated ToA represents theoretical RF duration
and does not measure hardware start/stop latency, SPI command overhead, or ISR delay.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import io
import json
import math
from typing import Any, Sequence

DATASHEET_REFERENCE = "Semtech SX1276/77/78/79 Datasheet Rev 7 (March 2015), Sec 4.1.1.5-4.1.1.7"
EVIDENCE_PROVENANCE = "CALCULATED"


class ToAValidationError(ValueError):
    """Raised when input parameters violate SX1276 physical or regulatory domain constraints."""


@dataclass(frozen=True)
class ToAInput:
    sf: int
    bw_hz: int
    cr: int  # 1=4/5, 2=4/6, 3=4/7, 4=4/8
    payload_bytes: int
    preamble_len: int = 8
    header_explicit: bool = True
    crc_on: bool = True
    ldro: bool | None = None  # None = auto-detect based on Ts > 16 ms rule
    sync_word: int = 0x12  # MVP V1 P2P sync word (not LoRaWAN 0x34)
    freq_hz: int = 920_250_000  # VN920 Channel 0 default

    def validate(self) -> None:
        if not isinstance(self.sf, int) or isinstance(self.sf, bool):
            raise ToAValidationError(f"Spreading factor (SF) must be integer, got {type(self.sf).__name__}")
        if self.sf < 6 or self.sf > 12:
            raise ToAValidationError(f"Spreading factor {self.sf} out of range [6, 12]")

        if not isinstance(self.bw_hz, int) or isinstance(self.bw_hz, bool):
            raise ToAValidationError(f"Bandwidth (BW) must be integer, got {type(self.bw_hz).__name__}")
        if self.bw_hz <= 0:
            raise ToAValidationError(f"Bandwidth {self.bw_hz} Hz must be positive")
        if self.bw_hz not in (125_000, 250_000, 500_000):
            # Allow custom positive BW but validate typical LoRa channels
            pass

        if not isinstance(self.cr, int) or isinstance(self.cr, bool):
            raise ToAValidationError(f"Coding rate (CR) must be integer, got {type(self.cr).__name__}")
        if self.cr < 1 or self.cr > 4:
            raise ToAValidationError(f"Coding rate {self.cr} out of range [1, 4] (1=4/5, 2=4/6, 3=4/7, 4=4/8)")

        if not isinstance(self.payload_bytes, int) or isinstance(self.payload_bytes, bool):
            raise ToAValidationError(f"Payload length must be integer, got {type(self.payload_bytes).__name__}")
        if self.payload_bytes < 0 or self.payload_bytes > 255:
            raise ToAValidationError(f"Payload length {self.payload_bytes} out of range [0, 255] (SX1276 FIFO limit)")

        if not isinstance(self.preamble_len, int) or isinstance(self.preamble_len, bool):
            raise ToAValidationError(f"Preamble length must be integer, got {type(self.preamble_len).__name__}")
        if self.preamble_len < 6:
            raise ToAValidationError(f"Preamble length {self.preamble_len} must be >= 6 symbols per SX1276 datasheet")

        if self.sf == 6 and self.header_explicit:
            raise ToAValidationError("SF6 requires implicit header mode (header_explicit=False) per SX1276 silicon spec")

        if self.sync_word == 0x34:
            raise ToAValidationError("LoRaWAN public sync word 0x34 is prohibited; use 0x12 for Custom LoRa P2P")


@dataclass(frozen=True)
class ToAResult:
    sf: int
    bw_hz: int
    cr: int
    payload_bytes: int
    preamble_len: int
    header_explicit: bool
    crc_on: bool
    ldro_on: bool
    sync_word: int
    freq_hz: int
    # Timing quantities
    t_sym_us: float
    t_sym_ms: float
    n_preamble_sym: float
    t_preamble_us: float
    t_preamble_ms: float
    n_payload_sym: int
    t_payload_us: float
    t_payload_ms: float
    toa_calculated_us: float
    toa_calculated_ms: float
    # Provenance and metadata
    provenance: str
    datasheet_reference: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_sx1276_toa(params: ToAInput) -> ToAResult:
    """Calculate exact theoretical Time-on-Air (ToA) using Semtech SX1276 equations."""
    params.validate()

    sf = params.sf
    bw = params.bw_hz
    cr = params.cr
    pl = params.payload_bytes
    n_preamble = params.preamble_len
    h = 0 if params.header_explicit else 1
    crc = 1 if params.crc_on else 0

    # Symbol duration: Ts = (2^SF) / BW (in seconds)
    t_sym_s = (2 ** sf) / float(bw)
    t_sym_us = t_sym_s * 1_000_000.0
    t_sym_ms = t_sym_s * 1_000.0

    # Low Data Rate Optimization: required if symbol duration > 16 ms (16,000 us)
    if params.ldro is None:
        de = 1 if (t_sym_s > 0.016) else 0
    else:
        de = 1 if params.ldro else 0

    # Preamble duration: Tpreamble = (Npreamble + 4.25) * Ts
    n_preamble_sym = n_preamble + 4.25
    t_preamble_us = n_preamble_sym * t_sym_us
    t_preamble_ms = t_preamble_us / 1000.0

    # Payload symbol count:
    # Npayload = 8 + max( ceil((8*PL - 4*SF + 28 + 16*CRC - 20*H) / (4 * (SF - 2*DE))) * (CR + 4), 0 )
    numerator = 8 * pl - 4 * sf + 28 + 16 * crc - 20 * h
    denominator = 4 * (sf - 2 * de)
    if denominator <= 0:
        raise ToAValidationError(f"Invalid denominator 4*(SF - 2*DE) = {denominator}")

    raw_ratio = numerator / float(denominator)
    ceil_term = math.ceil(raw_ratio)
    symbol_terms = ceil_term * (cr + 4)
    n_payload_sym = 8 + max(symbol_terms, 0)

    t_payload_us = n_payload_sym * t_sym_us
    t_payload_ms = t_payload_us / 1000.0

    toa_us = t_preamble_us + t_payload_us
    toa_ms = toa_us / 1000.0

    return ToAResult(
        sf=sf,
        bw_hz=bw,
        cr=cr,
        payload_bytes=pl,
        preamble_len=n_preamble,
        header_explicit=params.header_explicit,
        crc_on=params.crc_on,
        ldro_on=(de == 1),
        sync_word=params.sync_word,
        freq_hz=params.freq_hz,
        t_sym_us=round(t_sym_us, 3),
        t_sym_ms=round(t_sym_ms, 6),
        n_preamble_sym=n_preamble_sym,
        t_preamble_us=round(t_preamble_us, 3),
        t_preamble_ms=round(t_preamble_ms, 6),
        n_payload_sym=n_payload_sym,
        t_payload_us=round(t_payload_us, 3),
        t_payload_ms=round(t_payload_ms, 6),
        toa_calculated_us=round(toa_us, 3),
        toa_calculated_ms=round(toa_ms, 6),
        provenance=EVIDENCE_PROVENANCE,
        datasheet_reference=DATASHEET_REFERENCE,
    )


def calculate_sx1276_toa_secondary(
    sf: int,
    bw_hz: int,
    cr: int,
    payload_len: int,
    preamble_len: int = 8,
    explicit_header: bool = True,
    crc_enabled: bool = True,
    force_ldro: bool | None = None,
) -> tuple[float, float, int, float]:
    """Secondary, alternative implementation used to cross-verify the primary calculator.

    Returns:
        (t_sym_us, t_preamble_us, n_payload_sym, total_toa_us)
    """
    ts_us = (1 << sf) * 1_000_000.0 / bw_hz
    t_preamble_us = (preamble_len + 4.25) * ts_us

    # LDRO condition
    ldro_active = (ts_us > 16_000.0) if force_ldro is None else force_ldro
    de = 1 if ldro_active else 0
    h = 0 if explicit_header else 1
    crc = 1 if crc_enabled else 0

    num = 8 * payload_len - 4 * sf + 28 + 16 * crc - 20 * h
    den = 4 * (sf - 2 * de)

    # Manual integer ceiling division
    if num >= 0:
        c = (num + den - 1) // den
    else:
        # Negative numerator truncated toward zero or floored
        c = int(math.ceil(num / den))

    n_payload = 8 + max(c * (cr + 4), 0)
    total_toa_us = t_preamble_us + (n_payload * ts_us)
    return (ts_us, t_preamble_us, n_payload, total_toa_us)


def generate_profile_matrix(
    payload_sizes: Sequence[int] = (12, 24, 32, 48),
    spreading_factors: Sequence[int] = (7, 8),
    bandwidths: Sequence[int] = (125_000,),
    coding_rate: int = 1,  # 4/5
    preamble_len: int = 8,
    header_explicit: bool = True,
    crc_on: bool = True,
    sync_word: int = 0x12,
    freq_hz: int = 920_250_000,
) -> list[ToAResult]:
    """Generate versioned profile matrix for specified combinations."""
    results: list[ToAResult] = []
    for sf in spreading_factors:
        for bw in bandwidths:
            for pl in payload_sizes:
                param = ToAInput(
                    sf=sf,
                    bw_hz=bw,
                    cr=coding_rate,
                    payload_bytes=pl,
                    preamble_len=preamble_len,
                    header_explicit=header_explicit,
                    crc_on=crc_on,
                    ldro=None,
                    sync_word=sync_word,
                    freq_hz=freq_hz,
                )
                res = calculate_sx1276_toa(param)
                results.append(res)
    return results


def export_matrix_to_json(results: Sequence[ToAResult]) -> str:
    """Serialize profile matrix to formatted JSON string."""
    payload = {
        "schema_version": "1.0.0",
        "provenance": EVIDENCE_PROVENANCE,
        "datasheet_reference": DATASHEET_REFERENCE,
        "profile_count": len(results),
        "profiles": [r.to_dict() for r in results],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def export_matrix_to_csv(results: Sequence[ToAResult]) -> str:
    """Serialize profile matrix to standard CSV string."""
    if not results:
        return ""
    output = io.StringIO()
    fields = [
        "provenance",
        "sf",
        "bw_hz",
        "cr",
        "payload_bytes",
        "preamble_len",
        "header_explicit",
        "crc_on",
        "ldro_on",
        "sync_word",
        "freq_hz",
        "t_sym_us",
        "t_sym_ms",
        "n_preamble_sym",
        "t_preamble_us",
        "t_preamble_ms",
        "n_payload_sym",
        "t_payload_us",
        "t_payload_ms",
        "toa_calculated_us",
        "toa_calculated_ms",
        "datasheet_reference",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for r in results:
        d = r.to_dict()
        writer.writerow({k: d[k] for k in fields})
    return output.getvalue()
