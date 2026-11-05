"""Conservative, non-double-counted Guard Time and TDMA Slot Feasibility Calculator.

Conforms to Issue #11 Deliverable C:
- Theoretical / symbolic budget formulation with explicit units and uncertainty.
- Feasibility modeling for up to 10-15 Nodes/Gateway with ToA inputs.
- Status labeled explicitly: CALCULATED / SCENARIO.
- Numerical parameters marked as theoretical candidates; physical measurements reserved for #169.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
import sys
from typing import Any

# Ensure local toa import
CURRENT_DIR = Path(__file__).resolve().parent
TOA_DIR = CURRENT_DIR.parent / "toa"
if str(TOA_DIR) not in sys.path:
    sys.path.insert(0, str(TOA_DIR))

from sx1276_toa import ToAInput, calculate_sx1276_toa

SPEED_OF_LIGHT_KM_S = 299_792.458  # km/s (~3.3356 us/km)


@dataclass(frozen=True)
class GuardBudgetInputs:
    ppm_crystal_max: float = 20.0        # Max crystal tolerance in PPM (e.g. +-20 PPM)
    sync_interval_s: float = 10.0        # Beacon holdover window (seconds)
    sync_uncertainty_us: float = 25.0    # Beacon receive latch jitter in ISR
    task_jitter_us: float = 100.0        # FreeRTOS dispatch / scheduling jitter
    rx_turnaround_us: float = 60.0       # Radio PLL settling Standby -> RX mode
    distance_km: float = 5.0             # Max RF link radius (km)
    safety_margin_factor: float = 1.25   # 25% conservative engineering margin multiplier


@dataclass(frozen=True)
class GuardBudgetResult:
    drift_budget_us: float
    sync_uncertainty_us: float
    task_jitter_us: float
    rx_turnaround_us: float
    prop_delay_us: float
    base_guard_us: float
    safety_margin_us: float
    total_guard_us: float
    total_guard_ms: float
    provenance: str = "CALCULATED"
    status: str = "THEORETICAL_MODEL / PENDING_BENCH_MEASUREMENT"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_guard_budget(inputs: GuardBudgetInputs) -> GuardBudgetResult:
    """Calculate conservative, non-double-counted Guard Time budget.

    Equation:
      T_drift = 2 * PPM_max * 1e-6 * T_sync_s * 1e6 us = 2 * PPM_max * T_sync_s (us)
      T_prop  = (Distance_km / c) * 1e6 us
      Base    = T_drift + T_sync + T_task + T_rx + T_prop
      Total   = Base * safety_margin_factor
    """
    if inputs.ppm_crystal_max < 0 or inputs.sync_interval_s <= 0:
        raise ValueError("Crystal PPM and sync interval must be positive")
    if inputs.safety_margin_factor < 1.0:
        raise ValueError("Safety margin factor must be >= 1.0")

    # Worst-case relative drift between Node and Gateway oscillators:
    # Gateway can drift +PPM while Node drifts -PPM -> relative drift is 2 * PPM
    drift_us = 2.0 * inputs.ppm_crystal_max * inputs.sync_interval_s

    # RF speed of light propagation
    prop_us = (inputs.distance_km / SPEED_OF_LIGHT_KM_S) * 1_000_000.0

    base_us = (
        drift_us
        + inputs.sync_uncertainty_us
        + inputs.task_jitter_us
        + inputs.rx_turnaround_us
        + prop_us
    )

    total_us = base_us * inputs.safety_margin_factor
    safety_margin_us = total_us - base_us

    return GuardBudgetResult(
        drift_budget_us=round(drift_us, 3),
        sync_uncertainty_us=round(inputs.sync_uncertainty_us, 3),
        task_jitter_us=round(inputs.task_jitter_us, 3),
        rx_turnaround_us=round(inputs.rx_turnaround_us, 3),
        prop_delay_us=round(prop_us, 3),
        base_guard_us=round(base_us, 3),
        safety_margin_us=round(safety_margin_us, 3),
        total_guard_us=round(total_us, 3),
        total_guard_ms=round(total_us / 1000.0, 3),
    )


@dataclass(frozen=True)
class SlotFeasibilityInput:
    node_count: int                       # 1 to 15 Nodes
    uplink_payload_bytes: int = 24        # 12, 24, 32, 48 B
    ack_payload_bytes: int = 8            # Slotted Gateway ACK
    sf: int = 7                           # 7 or 8
    bw_hz: int = 125_000                  # 125 kHz
    cr: int = 1                           # 4/5
    superframe_period_s: float = 10.0     # Target superframe cycle (e.g. 10s or 300s)
    beacon_payload_bytes: int = 16        # Periodic SYNC beacon
    guard_inputs: GuardBudgetInputs = GuardBudgetInputs()
    regulatory_duty_limit_pct: float = 1.0 # 1% ETSI/VN920 regulatory duty cycle limit


@dataclass(frozen=True)
class SlotFeasibilityResult:
    node_count: int
    uplink_toa_ms: float
    ack_toa_ms: float
    beacon_toa_ms: float
    guard_time_ms: float
    slot_duration_ms: float
    beacon_phase_ms: float
    total_data_phase_ms: float
    total_active_ms: float
    superframe_period_ms: float
    slack_margin_ms: float
    node_duty_cycle_pct: float
    is_feasible: bool
    rejection_reason: str | None
    slot_timetable: list[dict[str, Any]]
    provenance: str = "CALCULATED / SCENARIO"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_slot_feasibility(params: SlotFeasibilityInput) -> SlotFeasibilityResult:
    """Evaluate TDMA slot feasibility and timetable for candidate deployment."""
    if params.node_count < 1 or params.node_count > 30:
        raise ValueError(f"Node count {params.node_count} out of supported bounds [1, 30]")
    if params.superframe_period_s <= 0:
        raise ValueError("Superframe period must be positive")

    # 1. Calculate ToA for each frame type using theoretical calculator
    uplink_toa = calculate_sx1276_toa(ToAInput(
        sf=params.sf, bw_hz=params.bw_hz, cr=params.cr, payload_bytes=params.uplink_payload_bytes
    ))
    ack_toa = calculate_sx1276_toa(ToAInput(
        sf=params.sf, bw_hz=params.bw_hz, cr=params.cr, payload_bytes=params.ack_payload_bytes
    ))
    beacon_toa = calculate_sx1276_toa(ToAInput(
        sf=params.sf, bw_hz=params.bw_hz, cr=params.cr, payload_bytes=params.beacon_payload_bytes
    ))

    # 2. Calculate Guard Time
    guard_res = calculate_guard_budget(params.guard_inputs)
    guard_ms = guard_res.total_guard_ms

    # 3. Formulate individual slot duration:
    # Slot = Uplink_ToA + Turnaround(TX->RX) + ACK_ToA + Guard_Time
    # Note: Turnaround from TX to RX is already factored in guard budget or minimum settling
    slot_ms = round(uplink_toa.toa_calculated_ms + ack_toa.toa_calculated_ms + guard_ms, 3)

    # 4. Superframe phases
    beacon_phase_ms = round(beacon_toa.toa_calculated_ms + guard_ms, 3)
    total_data_phase_ms = round(params.node_count * slot_ms, 3)
    total_active_ms = round(beacon_phase_ms + total_data_phase_ms, 3)
    superframe_period_ms = round(params.superframe_period_s * 1000.0, 3)
    slack_margin_ms = round(superframe_period_ms - total_active_ms, 3)

    # 5. Duty cycle check per node
    # Each node transmits only 1 uplink per superframe
    node_airtime_s = uplink_toa.toa_calculated_ms / 1000.0
    duty_cycle_pct = round((node_airtime_s / params.superframe_period_s) * 100.0, 4)

    # 6. Feasibility validation
    is_feasible = True
    rejection_reason = None

    if total_active_ms > superframe_period_ms:
        is_feasible = False
        rejection_reason = (
            f"Superframe overrun: active time {total_active_ms} ms exceeds period {superframe_period_ms} ms"
        )
    elif duty_cycle_pct > params.regulatory_duty_limit_pct:
        is_feasible = False
        rejection_reason = (
            f"Duty cycle violation: node duty {duty_cycle_pct}% exceeds limit {params.regulatory_duty_limit_pct}%"
        )

    # 7. Generate non-overlapping timetable
    timetable: list[dict[str, Any]] = []
    # Beacon slot
    timetable.append({
        "slot_index": 0,
        "phase": "BEACON",
        "entity": "GATEWAY",
        "start_ms": 0.0,
        "end_ms": beacon_phase_ms,
        "duration_ms": beacon_phase_ms,
        "tx_toa_ms": beacon_toa.toa_calculated_ms,
        "guard_ms": guard_ms,
    })

    curr_ms = beacon_phase_ms
    for i in range(params.node_count):
        slot_start = curr_ms
        slot_end = round(curr_ms + slot_ms, 3)
        timetable.append({
            "slot_index": i + 1,
            "phase": "DATA_UPLINK_AND_ACK",
            "entity": f"NODE_{i+1:02d}",
            "start_ms": slot_start,
            "end_ms": slot_end,
            "duration_ms": slot_ms,
            "uplink_toa_ms": uplink_toa.toa_calculated_ms,
            "ack_toa_ms": ack_toa.toa_calculated_ms,
            "guard_ms": guard_ms,
        })
        curr_ms = slot_end

    return SlotFeasibilityResult(
        node_count=params.node_count,
        uplink_toa_ms=uplink_toa.toa_calculated_ms,
        ack_toa_ms=ack_toa.toa_calculated_ms,
        beacon_toa_ms=beacon_toa.toa_calculated_ms,
        guard_time_ms=guard_ms,
        slot_duration_ms=slot_ms,
        beacon_phase_ms=beacon_phase_ms,
        total_data_phase_ms=total_data_phase_ms,
        total_active_ms=total_active_ms,
        superframe_period_ms=superframe_period_ms,
        slack_margin_ms=slack_margin_ms,
        node_duty_cycle_pct=duty_cycle_pct,
        is_feasible=is_feasible,
        rejection_reason=rejection_reason,
        slot_timetable=timetable,
    )
