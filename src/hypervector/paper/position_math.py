"""Shared numerical boundaries for paper position accounting."""

from __future__ import annotations

import math

POSITION_QUANTITY_ABS_TOLERANCE = 1e-12


def normalized_position_quantity(quantity: float) -> float:
    """Return exact zero for finite position residue within fill precision."""
    value = float(quantity)
    if not math.isfinite(value):
        raise ValueError("position quantity must be finite")
    if abs(value) <= POSITION_QUANTITY_ABS_TOLERANCE:
        return 0.0
    return value
