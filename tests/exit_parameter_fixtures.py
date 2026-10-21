"""Test-only adaptive and retention exit parameter tables.

The exit mechanisms take every threshold from the profile; these values exist
only so the mechanism tests have concrete, stable numbers.
"""

from __future__ import annotations

from hypervector.live.cohort_adaptive_exit_policy import (
    AdaptiveExitParameters,
    RetentionExitParameters,
)

ADAPTIVE_PARAMETERS = AdaptiveExitParameters(
    minimum_activation_bps=60.0,
    activation_atr_multiple=2.0,
    net_buffer_bps=20.0,
    maximum_giveback_fraction=0.5,
    regime_support=0.5,
    opposing_pressure=-0.35,
    book_confirmations=3,
    supported_allowance_bps=50.0,
    supported_allowance_atr=3.0,
    confirmed_allowance_bps=20.0,
    confirmed_allowance_atr=1.0,
    opposed_allowance_bps=25.0,
    opposed_allowance_atr=1.0,
    default_allowance_bps=35.0,
    default_allowance_atr=2.0,
)
RETENTION_PARAMETERS = RetentionExitParameters(
    activation_r=0.5,
    giveback_r=0.5,
    opposed_alignment=-0.5,
    floor_activation_r=2.0,
    floor_r=0.5,
    breakeven_offset_bps=25.0,
)
