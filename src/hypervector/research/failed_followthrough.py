"""Frozen report-only early-failure hypothesis, using signed completed returns."""

import math

MINIMUM_AGE_SECONDS = 30 * 60
ADVERSE_R_MULTIPLE = 0.5
MAXIMUM_FAVORABLE_R_MULTIPLE = 0.25


def failed_followthrough(
    *,
    age_seconds: float,
    current_bps: float,
    peak_close_bps: float,
    initial_stop_bps: float,
) -> bool:
    """Exit a mature adverse entry that never demonstrated the frozen followthrough."""
    values = (age_seconds, current_bps, peak_close_bps, initial_stop_bps)
    if any(isinstance(v, bool) or not math.isfinite(v) for v in values):
        raise ValueError("failed-followthrough inputs must be finite numeric")
    if age_seconds < 0 or peak_close_bps < 0 or initial_stop_bps <= 0:
        raise ValueError(
            "failed-followthrough age/peak must be nonnegative and risk positive"
        )
    return (
        age_seconds >= MINIMUM_AGE_SECONDS
        and current_bps <= -ADVERSE_R_MULTIPLE * initial_stop_bps
        and peak_close_bps < MAXIMUM_FAVORABLE_R_MULTIPLE * initial_stop_bps
    )
