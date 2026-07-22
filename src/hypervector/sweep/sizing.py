"""Conviction-scaled risk: 1%–5% of equity per trade (not notional % by default).

High conviction → risk toward max; low → toward min.
size_frac of equity for VectorBT = risk_pct / stop_distance_frac (capped).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RiskConfig:
    risk_pct_min: float = 0.01  # 1% of equity at risk
    risk_pct_max: float = 0.05  # 5% of equity at risk
    default_conviction: float = 0.5  # mid → ~3%
    # Cap position notional as multiple of equity (soft 1x default; raise later for lev)
    max_size_frac: float = 1.0

    def __post_init__(self) -> None:
        if not (0 < self.risk_pct_min <= self.risk_pct_max <= 1.0):
            raise ValueError("require 0 < risk_pct_min <= risk_pct_max <= 1")
        if not (0.0 <= self.default_conviction <= 1.0):
            raise ValueError("conviction must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def risk_pct_from_conviction(
    conviction: float | pd.Series,
    cfg: RiskConfig,
) -> float | pd.Series:
    """Map conviction in [0, 1] → risk fraction of equity in [min, max]."""
    lo, hi = cfg.risk_pct_min, cfg.risk_pct_max
    if isinstance(conviction, pd.Series):
        c = conviction.astype(float).clip(0.0, 1.0)
        return lo + c * (hi - lo)
    c = float(np.clip(conviction, 0.0, 1.0))
    return lo + c * (hi - lo)


def size_frac_from_risk(
    risk_pct: float | pd.Series,
    stop_frac: pd.Series,
    cfg: RiskConfig,
) -> pd.Series:
    """Equity fraction to deploy: risk / stop_distance, capped at max_size_frac."""
    sf = stop_frac.astype(float).replace(0.0, np.nan).clip(lower=1e-6)
    if isinstance(risk_pct, pd.Series):
        r = risk_pct.astype(float).reindex(sf.index)
    else:
        r = float(risk_pct)
    size = r / sf
    return size.clip(upper=cfg.max_size_frac).fillna(0.0)


def conviction_series(
    index: pd.Index,
    conviction: float | pd.Series | None,
    cfg: RiskConfig,
) -> pd.Series:
    if conviction is None:
        return pd.Series(cfg.default_conviction, index=index, dtype=float)
    if isinstance(conviction, pd.Series):
        return conviction.reindex(index).fillna(cfg.default_conviction).clip(0.0, 1.0)
    return pd.Series(float(conviction), index=index, dtype=float)
