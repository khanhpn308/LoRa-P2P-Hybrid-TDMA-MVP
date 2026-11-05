"""Unit and regression tests for timing statistical analysis and Guard Time calculator."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from tests.hil.rf_timing.host.host_collector import HostCollector
from tests.hil.rf_timing.host.log_schema import LogRecord
from tests.hil.rf_timing.analysis.timing_stats import (
    ProvenanceError,
    analyze_timing_stream,
    calculate_distribution_stats,
)
from tests.hil.rf_timing.analysis.guard_budget_calculator import (
    GuardBudgetInputs,
    SlotFeasibilityInput,
    calculate_guard_budget,
    calculate_slot_feasibility,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "host" / "fixtures"


def test_distribution_stats_calculation():
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    stats = calculate_distribution_stats("test_metric", vals)
    assert stats.n == 5
    assert stats.min_us == 10.0
    assert stats.max_us == 50.0
    assert stats.mean_us == 30.0
    assert stats.p50_us == 30.0
    assert stats.p90_us == 46.0
    assert stats.p99_us == 49.6


def test_nominal_fixture_analysis():
    nominal_path = FIXTURES_DIR / "synthetic_nominal_run.jsonl"
    assert nominal_path.exists()

    collector = HostCollector(allow_synthetic=True)
    with open(nominal_path, "r", encoding="utf-8") as f:
        collector.process_stream(f)

    assert collector.summary.valid_records > 100
    assert collector.summary.invalid_records == 0
    assert collector.summary.dropped_samples == 0

    analysis = analyze_timing_stream(collector.records)
    assert analysis.valid_records == collector.summary.valid_records
    assert analysis.evidence_classes_present == ["HOST_SYNTHETIC"]

    # Verify transition stats populated
    assert analysis.tx_dispatch_latency.n > 0
    assert analysis.tx_dispatch_latency.min_us > 0
    assert analysis.tx_to_rx_turnaround.n > 0
    assert analysis.tx_to_rx_turnaround.p50_us > 0


def test_dropped_overflow_fixture_analysis():
    dropped_path = FIXTURES_DIR / "synthetic_dropped_overflow.jsonl"
    assert dropped_path.exists()

    collector = HostCollector(allow_synthetic=True)
    with open(dropped_path, "r", encoding="utf-8") as f:
        collector.process_stream(f)

    assert collector.summary.dropped_samples == 10
    analysis = analyze_timing_stream(collector.records)
    assert analysis.overflow_count == 1


def test_uncertified_rf_measurement_rejection():
    """Verify that uncertified claims of EXTERNAL_RF_MEASURED fail closed."""
    fake_record = LogRecord(
        ver="1.0.0",
        seq=1,
        role="NODE",
        dev_id="NODE_HIL_01",
        evt="TX_DONE",
        ts_us=1000000,
        evidence_class="EXTERNAL_RF_MEASURED",
    )
    with pytest.raises(ProvenanceError, match="EXTERNAL_RF_MEASURED without calibrated equipment"):
        analyze_timing_stream([fake_record], require_certified_rf=False)


def test_guard_budget_calculation():
    # 20 PPM over 10 s sync interval
    inputs = GuardBudgetInputs(
        ppm_crystal_max=20.0,
        sync_interval_s=10.0,
        sync_uncertainty_us=25.0,
        task_jitter_us=100.0,
        rx_turnaround_us=60.0,
        distance_km=5.0,
        safety_margin_factor=1.25,
    )
    res = calculate_guard_budget(inputs)

    # Drift = 2 * 20 * 10 = 400 us
    assert abs(res.drift_budget_us - 400.0) < 1e-3
    # Prop delay for 5 km: 5 / 299792.458 * 1e6 ~= 16.678 us
    assert abs(res.prop_delay_us - 16.678) < 1e-2
    # Base = 400 + 25 + 100 + 60 + 16.678 = 601.678 us
    assert abs(res.base_guard_us - 601.678) < 1e-2
    # Total with 25% margin = 601.678 * 1.25 = 752.097 us = 0.752 ms
    assert abs(res.total_guard_us - 752.098) < 1e-2
    assert res.provenance == "CALCULATED"
    assert "PENDING_BENCH_MEASUREMENT" in res.status


def test_slot_feasibility_10_nodes_sf7():
    params = SlotFeasibilityInput(
        node_count=10,
        uplink_payload_bytes=24,
        ack_payload_bytes=8,
        sf=7,
        bw_hz=125_000,
        superframe_period_s=10.0,
    )
    res = calculate_slot_feasibility(params)
    assert res.is_feasible is True
    assert res.rejection_reason is None
    assert res.node_count == 10
    assert res.uplink_toa_ms == 61.696
    assert res.ack_toa_ms == 36.096
    # Slot duration = 61.696 + 36.096 + guard (~0.752 ms) ~= 98.544 ms
    assert res.slot_duration_ms > 95.0
    assert res.total_data_phase_ms < 1500.0  # ~1.0 s out of 10.0 s
    assert res.slack_margin_ms > 8000.0     # >8.0 s unallocated slack
    assert res.node_duty_cycle_pct < 1.0    # 61.696 ms / 10000 ms = ~0.617%
    assert len(res.slot_timetable) == 11   # 1 beacon + 10 nodes
    assert res.provenance == "CALCULATED / SCENARIO"


def test_slot_feasibility_15_nodes_sf7():
    params = SlotFeasibilityInput(
        node_count=15,
        uplink_payload_bytes=24,
        ack_payload_bytes=8,
        sf=7,
        bw_hz=125_000,
        superframe_period_s=10.0,
    )
    res = calculate_slot_feasibility(params)
    assert res.is_feasible is True
    assert res.node_count == 15
    assert res.total_active_ms < 2000.0
    assert res.slack_margin_ms > 8000.0


def test_slot_feasibility_overrun_rejection():
    # Attempting 20 nodes with 48B payload at SF8 (slot ~250 ms) in a 2-second superframe
    params = SlotFeasibilityInput(
        node_count=20,
        uplink_payload_bytes=48,
        ack_payload_bytes=16,
        sf=8,
        bw_hz=125_000,
        superframe_period_s=2.0,  # Only 2.0 s total
    )
    res = calculate_slot_feasibility(params)
    assert res.is_feasible is False
    assert res.rejection_reason is not None
    assert "Superframe overrun" in res.rejection_reason


def test_slot_feasibility_duty_cycle_violation():
    # If superframe period is only 1.0 s, a 61.7 ms transmission is 6.17% duty cycle (> 1.0%)
    params = SlotFeasibilityInput(
        node_count=2,
        uplink_payload_bytes=24,
        sf=7,
        bw_hz=125_000,
        superframe_period_s=1.0,
        regulatory_duty_limit_pct=1.0,
    )
    res = calculate_slot_feasibility(params)
    assert res.is_feasible is False
    assert res.rejection_reason is not None
    assert "Duty cycle violation" in res.rejection_reason
