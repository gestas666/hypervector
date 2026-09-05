"""Completed-close graduated profit lock for shared portfolio research."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import numpy as np
import pandas as pd

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class CompletedBarPeakLockPolicy:
    """Lock a ratio of peak return on margin observed at completed closes."""

    policy_id: str
    activation_roe_pct: float
    locked_peak_ratio: float

    def __post_init__(self) -> None:
        """Reject non-finite or mechanically incoherent lock parameters."""
        if not self.policy_id.strip():
            raise ValueError("completed peak-lock policy_id must be non-empty")
        if not math.isfinite(self.activation_roe_pct) or self.activation_roe_pct <= 0.0:
            raise ValueError("completed peak-lock activation must be positive")
        if (
            not math.isfinite(self.locked_peak_ratio)
            or not 0.0 < self.locked_peak_ratio < 1.0
        ):
            raise ValueError("completed peak-lock ratio must be between zero and one")


def completed_close_peak_lock_triggered(
    bars: pd.DataFrame,
    *,
    entry_position: int,
    current_position: int,
    direction: Direction,
    entry_price: float,
    leverage: float,
    policy: CompletedBarPeakLockPolicy | None,
) -> bool:
    """Return whether the current completed close crosses its active peak floor."""
    if policy is None:
        return False
    _validate_evaluation(
        bars,
        entry_position,
        current_position,
        direction,
        entry_price,
        leverage,
    )
    closes = (
        bars["close"]
        .iloc[entry_position : current_position + 1]
        .to_numpy(dtype=np.float64)
    )
    sign = 1.0 if direction == "long" else -1.0
    returns = sign * (closes / entry_price - 1.0) * leverage * 100.0
    peak = float(np.max(returns))
    current = float(returns[-1])
    return (
        peak >= policy.activation_roe_pct
        and current < peak
        and current <= peak * policy.locked_peak_ratio
    )


def _validate_evaluation(
    bars: pd.DataFrame,
    entry_position: int,
    current_position: int,
    direction: Direction,
    entry_price: float,
    leverage: float,
) -> None:
    positions_valid = (
        not isinstance(entry_position, bool)
        and not isinstance(current_position, bool)
        and 0 <= entry_position <= current_position < len(bars)
    )
    if not positions_valid or "close" not in bars:
        raise ValueError("completed peak-lock positions or close column are invalid")
    if direction not in ("long", "short"):
        raise ValueError("completed peak-lock direction is invalid")
    if not math.isfinite(entry_price) or entry_price <= 0.0:
        raise ValueError("completed peak-lock entry price must be positive")
    if not math.isfinite(leverage) or leverage <= 0.0:
        raise ValueError("completed peak-lock leverage must be positive")
    closes = bars["close"].iloc[entry_position : current_position + 1].astype(float)
    if not closes.map(math.isfinite).all() or closes.le(0.0).any():
        raise ValueError("completed peak-lock closes must be finite and positive")
