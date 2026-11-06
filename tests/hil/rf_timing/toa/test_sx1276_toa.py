"""Comprehensive unit and regression tests for Semtech SX1276 ToA calculator."""

from __future__ import annotations

import csv
import json
import pytest

from tests.hil.rf_timing.toa.sx1276_toa import (
    ToAInput,
    ToAResult,
    ToAValidationError,
    calculate_sx1276_toa,
    calculate_sx1276_toa_secondary,
    export_matrix_to_csv,
    export_matrix_to_json,
    generate_profile_matrix,
)

# Hand-calculated and independently verified reference vectors:
# Preamble: 8 symbols, BW: 125 kHz, CR: 4/5 (1), CRC: ON (1), Explicit Header: ON (0)
# Ts(SF7) = 1.024 ms, Tpreamble(SF7) = 12.544 ms
# Ts(SF8) = 2.048 ms, Tpreamble(SF8) = 25.088 ms
EXPECTED_VECTORS_SF7 = {
    12: {"n_payload": 28, "toa_us": 41_216.0},
    24: {"n_payload": 48, "toa_us": 61_696.0},
    32: {"n_payload": 58, "toa_us": 71_936.0},
    48: {"n_payload": 83, "toa_us": 97_536.0},
}

EXPECTED_VECTORS_SF8 = {
    12: {"n_payload": 28, "toa_us": 82_432.0},
    24: {"n_payload": 43, "toa_us": 113_152.0},
    32: {"n_payload": 53, "toa_us": 133_632.0},
    48: {"n_payload": 73, "toa_us": 174_592.0},
}

# Normative V2 Packet Vectors (Issue #169 / Issue #201 / PR #202):
# 19B (DOWN_EVENT_ACK), 21B (UP_HEALTH_REPLY), 26B (UP_EVENT), 80B (DOWN_SYNC_BEACON)
EXPECTED_V2_VECTORS_SF7 = {
    19: {"n_payload": 38, "toa_us": 51_456.0},
    21: {"n_payload": 43, "toa_us": 56_576.0},
    26: {"n_payload": 48, "toa_us": 61_696.0},
    80: {"n_payload": 128, "toa_us": 143_616.0},
}

EXPECTED_V2_VECTORS_SF8 = {
    19: {"n_payload": 38, "toa_us": 102_912.0},
    21: {"n_payload": 38, "toa_us": 102_912.0},
    26: {"n_payload": 43, "toa_us": 113_152.0},
    80: {"n_payload": 113, "toa_us": 256_512.0},
}


def test_hand_calculated_vectors_sf7():
    for pl, exp in EXPECTED_VECTORS_SF7.items():
        inp = ToAInput(sf=7, bw_hz=125_000, cr=1, payload_bytes=pl)
        res = calculate_sx1276_toa(inp)
        assert res.n_payload_sym == exp["n_payload"], f"Failed for SF7 PL={pl}"
        assert abs(res.toa_calculated_us - exp["toa_us"]) < 1e-3
        assert res.provenance == "CALCULATED"
        assert res.ldro_on is False


def test_hand_calculated_vectors_sf8():
    for pl, exp in EXPECTED_VECTORS_SF8.items():
        inp = ToAInput(sf=8, bw_hz=125_000, cr=1, payload_bytes=pl)
        res = calculate_sx1276_toa(inp)
        assert res.n_payload_sym == exp["n_payload"], f"Failed for SF8 PL={pl}"
        assert abs(res.toa_calculated_us - exp["toa_us"]) < 1e-3
        assert res.provenance == "CALCULATED"
        assert res.ldro_on is False


def test_v2_vectors_sf7():
    """Verify exact ToA for V2 packets (19B ACK, 21B Health, 26B Event, 80B Beacon) at SF7."""
    for pl, exp in EXPECTED_V2_VECTORS_SF7.items():
        inp = ToAInput(sf=7, bw_hz=125_000, cr=1, payload_bytes=pl)
        res = calculate_sx1276_toa(inp)
        assert res.n_payload_sym == exp["n_payload"], f"Failed for SF7 V2 PL={pl}"
        assert abs(res.toa_calculated_us - exp["toa_us"]) < 1e-3
        assert res.provenance == "CALCULATED"


def test_v2_vectors_sf8():
    """Verify exact ToA for V2 packets (19B ACK, 21B Health, 26B Event, 80B Beacon) at SF8."""
    for pl, exp in EXPECTED_V2_VECTORS_SF8.items():
        inp = ToAInput(sf=8, bw_hz=125_000, cr=1, payload_bytes=pl)
        res = calculate_sx1276_toa(inp)
        assert res.n_payload_sym == exp["n_payload"], f"Failed for SF8 V2 PL={pl}"
        assert abs(res.toa_calculated_us - exp["toa_us"]) < 1e-3
        assert res.provenance == "CALCULATED"


def test_secondary_implementation_consistency():
    """Verify primary and secondary independent implementations yield identical numbers."""
    for sf in range(7, 13):
        for bw in (125_000, 250_000, 500_000):
            for pl in (0, 1, 12, 24, 32, 48, 64, 128, 255):
                for cr in (1, 2, 3, 4):
                    inp = ToAInput(sf=sf, bw_hz=bw, cr=cr, payload_bytes=pl)
                    primary = calculate_sx1276_toa(inp)
                    sec_ts, sec_tp, sec_np, sec_toa = calculate_sx1276_toa_secondary(
                        sf=sf, bw_hz=bw, cr=cr, payload_len=pl
                    )
                    assert primary.n_payload_sym == sec_np
                    assert abs(primary.toa_calculated_us - sec_toa) < 1e-3


def test_ldro_auto_behavior():
    """Verify LDRO is activated when Ts > 16 ms (e.g. SF11/12 at 125 kHz)."""
    # SF10 at 125 kHz: Ts = 1024 / 125000 = 8.192 ms -> LDRO OFF
    res_sf10 = calculate_sx1276_toa(ToAInput(sf=10, bw_hz=125_000, cr=1, payload_bytes=24))
    assert res_sf10.ldro_on is False

    # SF11 at 125 kHz: Ts = 2048 / 125000 = 16.384 ms -> LDRO ON
    res_sf11 = calculate_sx1276_toa(ToAInput(sf=11, bw_hz=125_000, cr=1, payload_bytes=24))
    assert res_sf11.ldro_on is True

    # SF12 at 125 kHz: Ts = 4096 / 125000 = 32.768 ms -> LDRO ON
    res_sf12 = calculate_sx1276_toa(ToAInput(sf=12, bw_hz=125_000, cr=1, payload_bytes=24))
    assert res_sf12.ldro_on is True

    # SF11 at 250 kHz: Ts = 2048 / 250000 = 8.192 ms -> LDRO OFF
    res_sf11_250k = calculate_sx1276_toa(ToAInput(sf=11, bw_hz=250_000, cr=1, payload_bytes=24))
    assert res_sf11_250k.ldro_on is False


def test_header_and_crc_effects():
    """Explicit vs Implicit header and CRC ON vs OFF."""
    # Test for PL=24 where disabling CRC crosses a ceil() boundary
    base_24 = ToAInput(sf=7, bw_hz=125_000, cr=1, payload_bytes=24, header_explicit=True, crc_on=True)
    res_base_24 = calculate_sx1276_toa(base_24)

    no_crc_24 = ToAInput(sf=7, bw_hz=125_000, cr=1, payload_bytes=24, header_explicit=True, crc_on=False)
    res_no_crc_24 = calculate_sx1276_toa(no_crc_24)
    assert res_no_crc_24.n_payload_sym < res_base_24.n_payload_sym
    assert res_no_crc_24.toa_calculated_us < res_base_24.toa_calculated_us

    # Test for PL=32 where both fall in same ceil block, verifying <= non-increasing property
    base_32 = ToAInput(sf=7, bw_hz=125_000, cr=1, payload_bytes=32, header_explicit=True, crc_on=True)
    res_base_32 = calculate_sx1276_toa(base_32)
    no_crc_32 = ToAInput(sf=7, bw_hz=125_000, cr=1, payload_bytes=32, header_explicit=True, crc_on=False)
    res_no_crc_32 = calculate_sx1276_toa(no_crc_32)
    assert res_no_crc_32.n_payload_sym <= res_base_32.n_payload_sym
    assert res_no_crc_32.toa_calculated_us <= res_base_32.toa_calculated_us

    # Implicit header removes 20 bits from header overhead: for PL=24 crosses boundary
    implicit_24 = ToAInput(sf=7, bw_hz=125_000, cr=1, payload_bytes=24, header_explicit=False, crc_on=True)
    res_implicit_24 = calculate_sx1276_toa(implicit_24)
    assert res_implicit_24.n_payload_sym < res_base_24.n_payload_sym
    assert res_implicit_24.toa_calculated_us < res_base_24.toa_calculated_us


def test_validation_errors():
    """Verify fail-closed error handling on invalid domain inputs."""
    # Invalid SF
    with pytest.raises(ToAValidationError, match="Spreading factor"):
        calculate_sx1276_toa(ToAInput(sf=5, bw_hz=125_000, cr=1, payload_bytes=10))
    with pytest.raises(ToAValidationError, match="Spreading factor"):
        calculate_sx1276_toa(ToAInput(sf=13, bw_hz=125_000, cr=1, payload_bytes=10))

    # Invalid BW
    with pytest.raises(ToAValidationError, match="Bandwidth"):
        calculate_sx1276_toa(ToAInput(sf=7, bw_hz=0, cr=1, payload_bytes=10))
    with pytest.raises(ToAValidationError, match="Bandwidth"):
        calculate_sx1276_toa(ToAInput(sf=7, bw_hz=-125000, cr=1, payload_bytes=10))

    # Invalid CR
    with pytest.raises(ToAValidationError, match="Coding rate"):
        calculate_sx1276_toa(ToAInput(sf=7, bw_hz=125_000, cr=0, payload_bytes=10))
    with pytest.raises(ToAValidationError, match="Coding rate"):
        calculate_sx1276_toa(ToAInput(sf=7, bw_hz=125_000, cr=5, payload_bytes=10))

    # Invalid Payload length
    with pytest.raises(ToAValidationError, match="Payload length"):
        calculate_sx1276_toa(ToAInput(sf=7, bw_hz=125_000, cr=1, payload_bytes=-1))
    with pytest.raises(ToAValidationError, match="Payload length"):
        calculate_sx1276_toa(ToAInput(sf=7, bw_hz=125_000, cr=1, payload_bytes=256))

    # Invalid Preamble length
    with pytest.raises(ToAValidationError, match="Preamble length"):
        calculate_sx1276_toa(ToAInput(sf=7, bw_hz=125_000, cr=1, payload_bytes=10, preamble_len=5))

    # SF6 with explicit header is forbidden
    with pytest.raises(ToAValidationError, match="SF6 requires implicit header"):
        calculate_sx1276_toa(ToAInput(sf=6, bw_hz=125_000, cr=1, payload_bytes=10, header_explicit=True))

    # Prohibited LoRaWAN sync word
    with pytest.raises(ToAValidationError, match="LoRaWAN public sync word 0x34 is prohibited"):
        calculate_sx1276_toa(ToAInput(sf=7, bw_hz=125_000, cr=1, payload_bytes=10, sync_word=0x34))


def test_matrix_generation_and_export():
    matrix = generate_profile_matrix(
        payload_sizes=(12, 24, 32, 48),
        spreading_factors=(7, 8),
        bandwidths=(125_000,),
    )
    assert len(matrix) == 8

    # JSON export
    json_str = export_matrix_to_json(matrix)
    loaded_json = json.loads(json_str)
    assert loaded_json["schema_version"] == "1.0.0"
    assert loaded_json["provenance"] == "CALCULATED"
    assert len(loaded_json["profiles"]) == 8

    # CSV export
    csv_str = export_matrix_to_csv(matrix)
    reader = csv.DictReader(csv_str.splitlines())
    rows = list(reader)
    assert len(rows) == 8
    assert rows[0]["provenance"] == "CALCULATED"
    assert rows[0]["sf"] == "7"
    assert rows[0]["payload_bytes"] == "12"
