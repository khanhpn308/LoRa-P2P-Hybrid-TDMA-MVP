"""Timing analysis, statistics, and Guard Time budget calculator package."""

from .timing_stats import (
    TimingIntervalStats,
    TimingRunAnalysis,
    analyze_timing_stream,
)
from .guard_budget_calculator import (
    GuardBudgetInputs,
    GuardBudgetResult,
    SlotFeasibilityInput,
    SlotFeasibilityResult,
    calculate_guard_budget,
    calculate_slot_feasibility,
)

__all__ = [
    "TimingIntervalStats",
    "TimingRunAnalysis",
    "analyze_timing_stream",
    "GuardBudgetInputs",
    "GuardBudgetResult",
    "SlotFeasibilityInput",
    "SlotFeasibilityResult",
    "calculate_guard_budget",
    "calculate_slot_feasibility",
]
