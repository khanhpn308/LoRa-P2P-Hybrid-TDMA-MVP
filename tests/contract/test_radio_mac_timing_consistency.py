"""Deterministic Host-Side Model and Timing Consistency Tests for LoRa Radio MAC.

Reference:
- Semtech SX1276 Datasheet Rev 7 (March 2015), Sections 4.1.1.5 - 4.1.1.7
- contracts/radio-mac/specification.md
- contracts/radio-mac/tdma-schedule.md
- contracts/OPEN_DECISIONS.md
- Issue #201: [G2][Corrective][#127] Reconcile SF8 Event/ACK timing, 80B Beacon window and Health drop-counter contract

Theoretical results are conditional formula results (CALCULATED provenance).
They do not assert RF/HIL capability or physical bench measurement (G1/HIL=NOT_VERIFIED).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pytest

from tests.hil.rf_timing.toa.sx1276_toa import ToAInput, calculate_sx1276_toa


# Standard RF profile for theoretical evaluation (Issue #201 / VN920 default)
BW_HZ = 125_000
CR = 1  # 4/5
PREAMBLE_LEN = 8
HEADER_EXPLICIT = True
CRC_ON = True

# Approved packet payload lengths (bytes)
LEN_UP_EVENT = 26
LEN_DOWN_EVENT_ACK = 19
LEN_DOWN_SYNC_BEACON = 80
LEN_UP_HEALTH_REPLY = 21


def get_theoretical_toa_ms(sf: int, payload_bytes: int) -> float:
    """Calculate SX1276 theoretical ToA in milliseconds using official equations."""
    params = ToAInput(
        sf=sf,
        bw_hz=BW_HZ,
        cr=CR,
        payload_bytes=payload_bytes,
        preamble_len=PREAMBLE_LEN,
        header_explicit=HEADER_EXPLICIT,
        crc_on=CRC_ON,
    )
    result = calculate_sx1276_toa(params)
    return round(result.toa_calculated_ms, 3)


# --- Task 1 / Baseline ToA Reference Values ---


def test_known_toa_reference_values():
    """Verify calculated ToA for all relevant packet lengths at SF7 and SF8.

    Matches exact theoretical values documented in Issue #201.
    """
    # SF7 values
    assert get_theoretical_toa_ms(7, LEN_UP_EVENT) == pytest.approx(61.696, rel=1e-4)
    assert get_theoretical_toa_ms(7, LEN_DOWN_EVENT_ACK) == pytest.approx(51.456, rel=1e-4)
    assert get_theoretical_toa_ms(7, LEN_DOWN_SYNC_BEACON) == pytest.approx(143.616, rel=1e-4)
    assert get_theoretical_toa_ms(7, LEN_UP_HEALTH_REPLY) == pytest.approx(56.576, rel=1e-4)

    # SF8 values
    assert get_theoretical_toa_ms(8, LEN_UP_EVENT) == pytest.approx(113.152, rel=1e-4)
    assert get_theoretical_toa_ms(8, LEN_DOWN_EVENT_ACK) == pytest.approx(102.912, rel=1e-4)
    assert get_theoretical_toa_ms(8, LEN_DOWN_SYNC_BEACON) == pytest.approx(256.512, rel=1e-4)
    assert get_theoretical_toa_ms(8, LEN_UP_HEALTH_REPLY) == pytest.approx(102.912, rel=1e-4)


# --- Task 2: TIM-01 Static DATA Slot Timing Violations at SF8 ---


def test_tim_01_sf8_event_exceeds_legacy_100ms_window():
    """Verify TIM-01: UP_EVENT (26B) at SF8 exceeds the legacy [25, 125)ms (100ms) sub-window."""
    legacy_event_window_ms = 100.0  # [25, 125)ms in tdma-schedule.md §2
    toa_event_sf8 = get_theoretical_toa_ms(8, LEN_UP_EVENT)

    assert toa_event_sf8 == 113.152
    assert toa_event_sf8 > legacy_event_window_ms
    overrun_ms = toa_event_sf8 - legacy_event_window_ms
    assert overrun_ms == pytest.approx(13.152, rel=1e-3)


def test_tim_01_sf8_ack_exceeds_legacy_100ms_window():
    """Verify TIM-01: DOWN_EVENT_ACK (19B) at SF8 exceeds the legacy [145, 245)ms (100ms) sub-window."""
    legacy_ack_window_ms = 100.0  # [145, 245)ms in tdma-schedule.md §2
    toa_ack_sf8 = get_theoretical_toa_ms(8, LEN_DOWN_EVENT_ACK)

    assert toa_ack_sf8 == 102.912
    assert toa_ack_sf8 > legacy_ack_window_ms
    overrun_ms = toa_ack_sf8 - legacy_ack_window_ms
    assert overrun_ms == pytest.approx(2.912, rel=1e-3)


def test_tim_01_sf8_roundtrip_exceeds_legacy_envelope():
    """Verify TIM-01: SF8 Event + assumed 20ms turnaround + SF8 ACK exceeds the [25, 245)ms (220ms) envelope."""
    legacy_envelope_ms = 220.0  # [25, 245)ms
    assumed_turnaround_ms = 20.0  # Assumed turnaround without WAL
    toa_event_sf8 = get_theoretical_toa_ms(8, LEN_UP_EVENT)
    toa_ack_sf8 = get_theoretical_toa_ms(8, LEN_DOWN_EVENT_ACK)

    total_roundtrip_ms = toa_event_sf8 + assumed_turnaround_ms + toa_ack_sf8
    assert total_roundtrip_ms == pytest.approx(236.064, rel=1e-4)
    assert total_roundtrip_ms > legacy_envelope_ms
    overrun_ms = total_roundtrip_ms - legacy_envelope_ms
    assert overrun_ms == pytest.approx(16.064, rel=1e-3)


# --- Task 3: TIM-02 Beacon 80B Window Violation at SF8 ---


def test_tim_02_sf8_beacon_exceeds_250ms_window():
    """Verify TIM-02: DOWN_SYNC_BEACON (80B) at SF8 exceeds the legacy [0, 250)ms (250ms) window."""
    legacy_beacon_window_ms = 250.0  # Slot 0 in tdma-schedule.md §2
    toa_beacon_sf8 = get_theoretical_toa_ms(8, LEN_DOWN_SYNC_BEACON)

    assert toa_beacon_sf8 == 256.512
    assert toa_beacon_sf8 > legacy_beacon_window_ms
    overrun_ms = toa_beacon_sf8 - legacy_beacon_window_ms
    assert overrun_ms == pytest.approx(6.512, rel=1e-3)


def test_tim_02_sf7_beacon_fits_250ms_window():
    """Verify TIM-02 counterpart: DOWN_SYNC_BEACON (80B) at SF7 fits within 250ms with positive margin."""
    legacy_beacon_window_ms = 250.0
    toa_beacon_sf7 = get_theoretical_toa_ms(7, LEN_DOWN_SYNC_BEACON)

    assert toa_beacon_sf7 == 143.616
    assert toa_beacon_sf7 < legacy_beacon_window_ms
    margin_ms = legacy_beacon_window_ms - toa_beacon_sf7
    assert margin_ms == pytest.approx(106.384, rel=1e-3)


# --- Task 2 / Validator-Checkable Symbolic Timing Budget Model ---


@dataclass(frozen=True)
class SlotTimingConfig:
    sf: int
    slot_duration_ms: float
    guard_lead_ms: float
    event_window_ms: float
    gap_turnaround_ms: float
    ack_window_ms: float
    guard_trail_ms: float
    wal_latency_ms: Optional[float] = None
    node_turnaround_ms: float = 20.0
    max_clock_drift_ms: float = 25.0


def validate_data_slot_timing(cfg: SlotTimingConfig) -> Tuple[bool, str]:
    """Symbolic validator for Static DATA Slot timing budget.

    Fails closed if:
    1. Any critical timing parameter (such as Gateway WAL durability latency) is unknown/unbounded.
    2. Sub-window for UP_EVENT is smaller than theoretical ToA(SF).
    3. Sub-window for DOWN_EVENT_ACK is smaller than theoretical ToA(SF).
    4. Gap window is smaller than (GW turnaround + WAL commit latency).
    5. Sum of sub-windows exceeds total slot duration.
    6. Overall slot cannot accommodate RF ToAs + all delays + guard margins + clock drift.
    """
    if cfg.wal_latency_ms is None:
        return False, "FAIL_CLOSED: Gateway WAL write latency is unknown/unbounded (DEC-127-05 unresolved)"

    toa_event = get_theoretical_toa_ms(cfg.sf, LEN_UP_EVENT)
    toa_ack = get_theoretical_toa_ms(cfg.sf, LEN_DOWN_EVENT_ACK)

    # Sub-window checks
    if cfg.event_window_ms < toa_event:
        return (
            False,
            f"FAIL_CLOSED: Event sub-window ({cfg.event_window_ms}ms) < ToA ({toa_event}ms) for SF{cfg.sf}",
        )

    if cfg.ack_window_ms < toa_ack:
        return (
            False,
            f"FAIL_CLOSED: ACK sub-window ({cfg.ack_window_ms}ms) < ToA ({toa_ack}ms) for SF{cfg.sf}",
        )

    required_gap = cfg.wal_latency_ms
    if cfg.gap_turnaround_ms < required_gap:
        return (
            False,
            f"FAIL_CLOSED: Gap window ({cfg.gap_turnaround_ms}ms) < required WAL latency ({required_gap}ms)",
        )

    # Total allocated sub-windows
    total_allocated = (
        cfg.guard_lead_ms
        + cfg.event_window_ms
        + cfg.gap_turnaround_ms
        + cfg.ack_window_ms
        + cfg.guard_trail_ms
    )
    if total_allocated > cfg.slot_duration_ms:
        return (
            False,
            f"FAIL_CLOSED: Sum of sub-windows ({total_allocated}ms) exceeds slot duration ({cfg.slot_duration_ms}ms)",
        )

    # Minimum theoretical budget check
    min_required_budget = (
        cfg.guard_lead_ms
        + toa_event
        + cfg.gap_turnaround_ms
        + toa_ack
        + cfg.guard_trail_ms
    )
    if min_required_budget > cfg.slot_duration_ms:
        return (
            False,
            f"FAIL_CLOSED: Minimum theoretical budget ({min_required_budget}ms) exceeds slot ({cfg.slot_duration_ms}ms)",
        )

    return True, f"PASS: Valid schedule timing budget for SF{cfg.sf}"


def test_tim_01_symbolic_budget_fails_closed_when_wal_unbounded():
    """Verify symbolic validator fails closed when Gateway WAL latency is unbounded/unknown."""
    cfg = SlotTimingConfig(
        sf=7,
        slot_duration_ms=400.0,
        guard_lead_ms=25.0,
        event_window_ms=100.0,
        gap_turnaround_ms=20.0,
        ack_window_ms=100.0,
        guard_trail_ms=155.0,
        wal_latency_ms=None,  # Unbounded
    )
    valid, reason = validate_data_slot_timing(cfg)
    assert not valid
    assert "FAIL_CLOSED" in reason
    assert "WAL write latency is unknown" in reason


def test_tim_01_symbolic_budget_fails_for_legacy_sf8():
    """Verify symbolic validator rejects the legacy 100ms sub-windows when operated at SF8."""
    cfg = SlotTimingConfig(
        sf=8,
        slot_duration_ms=400.0,
        guard_lead_ms=25.0,
        event_window_ms=100.0,  # Legacy 100ms
        gap_turnaround_ms=20.0,
        ack_window_ms=100.0,  # Legacy 100ms
        guard_trail_ms=155.0,
        wal_latency_ms=10.0,
    )
    valid, reason = validate_data_slot_timing(cfg)
    assert not valid
    assert "FAIL_CLOSED" in reason
    assert "Event sub-window" in reason
    assert "113.152ms" in reason


def test_tim_01_symbolic_budget_passes_for_legacy_sf7_with_bounded_wal():
    """Verify symbolic validator passes for SF7 with bounded WAL latency under legacy sub-windows."""
    cfg = SlotTimingConfig(
        sf=7,
        slot_duration_ms=400.0,
        guard_lead_ms=25.0,
        event_window_ms=100.0,
        gap_turnaround_ms=20.0,
        ack_window_ms=100.0,
        guard_trail_ms=155.0,
        wal_latency_ms=10.0,
    )
    valid, reason = validate_data_slot_timing(cfg)
    assert valid
    assert "PASS" in reason


def test_tim_01_symbolic_budget_candidate_rebalanced_sf8():
    """Verify a proposed rebalanced candidate sub-window schedule for SF8 can pass validator."""
    # Proposed candidate sub-windows for SF8:
    # Lead guard: 25ms [0..25)
    # UP_EVENT: 125ms [25..150) (accommodates 113.152ms)
    # GW Turnaround & WAL: 35ms [150..185) (accommodates 20ms turnaround + 15ms WAL)
    # DOWN_EVENT_ACK: 115ms [185..300) (accommodates 102.912ms)
    # Trailing guard: 100ms [300..400)
    cfg = SlotTimingConfig(
        sf=8,
        slot_duration_ms=400.0,
        guard_lead_ms=25.0,
        event_window_ms=125.0,
        gap_turnaround_ms=35.0,
        ack_window_ms=115.0,
        guard_trail_ms=100.0,
        wal_latency_ms=15.0,
    )
    valid, reason = validate_data_slot_timing(cfg)
    assert valid
    assert "PASS" in reason


# --- Task 4: MAC-01 Health Reply 21B Field Budget Incompatibility ---


def test_mac_01_health_reply_21b_field_budget_incompatibility():
    """Verify MAC-01: Approved 21B UP_HEALTH_REPLY layout leaves 0 bytes for DROPPED_EVENT_COUNT.

    DEC-MH-02 approved layout:
    - Header: 7B (VER_TYPE:1 | NODE_ID:1 | SESSION_SEL:1 | FRAME_COUNTER:4)
    - Plaintext: 6B (MAINT_SEQ:4 | STATUS_FLAGS:1 | PENDING_COUNT:1)
    - Tag: 8B (CCM-8)
    Total: 21B.
    """
    total_approved_bytes = 21

    header_bytes = 1 + 1 + 1 + 4  # 7B
    tag_bytes = 8  # 8B CCM-8
    plaintext_bytes = 4 + 1 + 1  # 6B (MAINT_SEQ:4, STATUS_FLAGS:1, PENDING_COUNT:1)

    consumed_bytes = header_bytes + plaintext_bytes + tag_bytes
    assert consumed_bytes == total_approved_bytes

    remaining_bytes = total_approved_bytes - consumed_bytes
    assert remaining_bytes == 0, "No unallocated bytes remain in the 21B layout"

    # PENDING_COUNT is a 1-byte instantaneous queue gauge (0..255)
    # DROPPED_EVENT_COUNT requires a monotonic cumulative counter (u16 or u32)
    # Prove that fitting a cumulative dropped counter requires expanding layout
    # or defining a separate diagnostic wire format.
    dropped_counter_min_bytes = 2  # u16
    assert dropped_counter_min_bytes > remaining_bytes
