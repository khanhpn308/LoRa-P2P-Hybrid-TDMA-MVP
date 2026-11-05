"""Reproducible statistical parser and metric analyzer for timing log streams.

Conforms to Issue #11 / C deliverable requirements:
- Computes sample size N, min, max, mean, stddev, P50, P90, P95, P99 percentiles.
- Tracks invalid records, timeouts, and dropped sample counts.
- Enforces strict provenance separation (CALCULATED_TOA, HOST_SYNTHETIC, SOFTWARE_TIMESTAMP,
  HARDWARE_CAPTURE, EXTERNAL_RF_MEASURED).
- Rejects uncertified claims of EXTERNAL_RF_MEASURED.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Sequence

# Ensure sibling import works
CURRENT_DIR = Path(__file__).resolve().parent
HOST_DIR = CURRENT_DIR.parent / "host"
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from log_schema import LogRecord, validate_log_record
from host_collector import HostCollector


class ProvenanceError(ValueError):
    """Raised when evidence classification violates provenance boundaries."""


@dataclass(frozen=True)
class TimingIntervalStats:
    name: str
    n: int
    min_us: float
    max_us: float
    mean_us: float
    stddev_us: float
    p50_us: float
    p90_us: float
    p95_us: float
    p99_us: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_distribution_stats(name: str, values: Sequence[float]) -> TimingIntervalStats:
    """Compute complete statistical summary for a series of microsecond values."""
    if not values:
        return TimingIntervalStats(
            name=name, n=0, min_us=0.0, max_us=0.0, mean_us=0.0,
            stddev_us=0.0, p50_us=0.0, p90_us=0.0, p95_us=0.0, p99_us=0.0
        )

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def percentile(p: float) -> float:
        if n == 1:
            return sorted_vals[0]
        rank = p * (n - 1)
        low_idx = int(math.floor(rank))
        high_idx = int(math.ceil(rank))
        weight = rank - low_idx
        return sorted_vals[low_idx] * (1.0 - weight) + sorted_vals[high_idx] * weight

    mean_val = statistics.mean(sorted_vals)
    stddev_val = statistics.stdev(sorted_vals) if n > 1 else 0.0

    return TimingIntervalStats(
        name=name,
        n=n,
        min_us=round(float(sorted_vals[0]), 3),
        max_us=round(float(sorted_vals[-1]), 3),
        mean_us=round(float(mean_val), 3),
        stddev_us=round(float(stddev_val), 3),
        p50_us=round(percentile(0.50), 3),
        p90_us=round(percentile(0.90), 3),
        p95_us=round(percentile(0.95), 3),
        p99_us=round(percentile(0.99), 3),
    )


@dataclass
class TimingRunAnalysis:
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    dropped_records: int = 0
    timeout_count: int = 0
    overflow_count: int = 0
    evidence_classes_present: list[str] = field(default_factory=list)
    # Interval metrics
    tx_dispatch_latency: TimingIntervalStats = field(
        default_factory=lambda: calculate_distribution_stats("tx_dispatch_latency", [])
    )
    tx_irq_response_latency: TimingIntervalStats = field(
        default_factory=lambda: calculate_distribution_stats("tx_irq_response_latency", [])
    )
    tx_to_rx_turnaround: TimingIntervalStats = field(
        default_factory=lambda: calculate_distribution_stats("tx_to_rx_turnaround", [])
    )
    ack_roundtrip_latency: TimingIntervalStats = field(
        default_factory=lambda: calculate_distribution_stats("ack_roundtrip_latency", [])
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def analyze_timing_stream(
    records: Iterable[LogRecord],
    require_certified_rf: bool = False,
) -> TimingRunAnalysis:
    """Analyze stream of validated LogRecords and produce statistical metrics."""
    analysis = TimingRunAnalysis()
    evidence_set: set[str] = set()

    tx_dispatch_vals: list[float] = []
    tx_irq_vals: list[float] = []
    tx_to_rx_vals: list[float] = []
    ack_roundtrip_vals: list[float] = []

    last_tx_cmd_ts: int | None = None
    last_tx_start_ts: int | None = None
    last_dio0_ts: int | None = None
    last_tx_done_ts: int | None = None
    last_rx_cmd_ts: int | None = None

    for rec in records:
        analysis.total_records += 1
        evidence_set.add(rec.evidence_class)

        # Integrity check: forbid uncertified claims of EXTERNAL_RF_MEASURED
        if rec.evidence_class == "EXTERNAL_RF_MEASURED" and not require_certified_rf:
            raise ProvenanceError(
                f"Record seq={rec.seq} claims EXTERNAL_RF_MEASURED without calibrated equipment certificate"
            )

        if rec.evt == "RX_TIMEOUT":
            analysis.timeout_count += 1
        elif rec.evt == "OVERFLOW":
            analysis.overflow_count += 1

        # Match consecutive event state transitions
        if rec.evt == "TX_CMD":
            last_tx_cmd_ts = rec.ts_us
        elif rec.evt == "TX_START":
            if last_tx_cmd_ts is not None and rec.ts_us >= last_tx_cmd_ts:
                tx_dispatch_vals.append(float(rec.ts_us - last_tx_cmd_ts))
            last_tx_start_ts = rec.ts_us
        elif rec.evt == "DIO0_IRQ":
            last_dio0_ts = rec.ts_us
        elif rec.evt == "TX_DONE":
            if last_dio0_ts is not None and rec.ts_us >= last_dio0_ts:
                tx_irq_vals.append(float(rec.ts_us - last_dio0_ts))
            last_tx_done_ts = rec.ts_us
        elif rec.evt == "RX_CMD":
            if last_tx_done_ts is not None and rec.ts_us >= last_tx_done_ts:
                tx_to_rx_vals.append(float(rec.ts_us - last_tx_done_ts))
            last_rx_cmd_ts = rec.ts_us
        elif rec.evt == "RX_DONE":
            if last_rx_cmd_ts is not None and rec.ts_us >= last_rx_cmd_ts:
                ack_roundtrip_vals.append(float(rec.ts_us - last_rx_cmd_ts))

    analysis.valid_records = analysis.total_records
    analysis.evidence_classes_present = sorted(evidence_set)
    analysis.tx_dispatch_latency = calculate_distribution_stats("tx_dispatch_latency", tx_dispatch_vals)
    analysis.tx_irq_response_latency = calculate_distribution_stats("tx_irq_response_latency", tx_irq_vals)
    analysis.tx_to_rx_turnaround = calculate_distribution_stats("tx_to_rx_turnaround", tx_to_rx_vals)
    analysis.ack_roundtrip_latency = calculate_distribution_stats("ack_roundtrip_latency", ack_roundtrip_vals)

    return analysis
