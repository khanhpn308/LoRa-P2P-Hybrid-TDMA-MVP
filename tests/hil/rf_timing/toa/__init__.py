"""Semtech SX1276 Theoretical Time-on-Air (ToA) calculator package."""

from .sx1276_toa import (
    ToAInput,
    ToAResult,
    calculate_sx1276_toa,
    calculate_sx1276_toa_secondary,
    generate_profile_matrix,
)

__all__ = [
    "ToAInput",
    "ToAResult",
    "calculate_sx1276_toa",
    "calculate_sx1276_toa_secondary",
    "generate_profile_matrix",
]
