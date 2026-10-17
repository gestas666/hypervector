"""Conviction-scaled risk: 1%–5% of equity per trade (not notional % by default).

High conviction → risk toward max; low → toward min.
size_frac of equity for VectorBT = risk_pct / stop_distance_frac, capped at
``max_size_frac`` — the leverage (position notional / equity). With typical
1m ATR stops (~0.1%) the cap binds on nearly every entry, so the leverage, not
the conviction, sets the exposure; trial metrics report the effective risk.

Hyperliquid venue leverage caps (SRS_HV1_VENUE_SPEC) live here as the single
research table: BTC 40x, ETH 25x, SOL 20x, HYPE 10x, other perps 10x unless the
venue metadata (``maxLeverage``) says otherwise. Maintenance margin on
Hyperliquid is half the initial margin at maximum leverage.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

VENUE_LEVERAGE_CAPS: dict[str, float] = {
    "BTC": 40.0,
    "ETH": 25.0,
    "SOL": 20.0,
    "HYPE": 10.0,
}
DEFAULT_ALT_LEVERAGE_CAP = 10.0
# Highest cap in the charter table; bounds any request whose symbol is unknown.
MAX_VENUE_LEVERAGE = max(VENUE_LEVERAGE_CAPS.values())


def _symbol_key(symbol: str) -> str:
    key = str(symbol).strip().upper()
    for suffix in ("-PERP", "-USD", "-USDC", "/USD", "/USDC", "/USDT"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    return key


def venue_leverage_cap(
    symbol: str | None, venue_max_leverage: float | None = None
) -> float:
    """Maximum position leverage for ``symbol``.

    Venue metadata (``maxLeverage``) is authoritative for assets outside the
    charter table and can only lower a charter cap. With no symbol the
    charter maximum applies.
    """
    if symbol is None or not str(symbol).strip():
        cap = MAX_VENUE_LEVERAGE
        charter = True
    else:
        key = _symbol_key(symbol)
        charter = key in VENUE_LEVERAGE_CAPS
        cap = VENUE_LEVERAGE_CAPS.get(key, DEFAULT_ALT_LEVERAGE_CAP)
    if venue_max_leverage is not None:
        venue = float(venue_max_leverage)
        if not math.isfinite(venue) or venue <= 0.0:
            raise ValueError(f"venue max leverage must be positive, got {venue_max_leverage!r}")
        cap = min(cap, venue) if charter else venue
    return float(cap)


def maintenance_margin_rate(venue_cap: float) -> float:
    """Hyperliquid maintenance margin: half the initial margin at max leverage."""
    return 1.0 / (2.0 * float(venue_cap))


def validate_leverage(
    leverage: float,
    *,
    symbol: str | None = None,
    venue_max_leverage: float | None = None,
) -> float:
    """Return ``leverage`` or raise ValueError when it is invalid for the venue."""
    value = float(leverage)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"leverage must be finite and positive, got {leverage!r}")
    cap = venue_leverage_cap(symbol, venue_max_leverage)
    if value > cap:
        where = _symbol_key(symbol) if symbol else "any symbol"
        raise ValueError(
            f"leverage {value:g}x exceeds the Hyperliquid venue cap of {cap:g}x for {where}"
        )
    return value


@dataclass(frozen=True)
class RiskConfig:
    risk_pct_min: float = 0.01  # 1% of equity at risk
    risk_pct_max: float = 0.05  # 5% of equity at risk
    default_conviction: float = 0.5  # mid → ~3%
    # Leverage: cap on position notional as a multiple of equity (1x default)
    max_size_frac: float = 1.0

    def __post_init__(self) -> None:
        if not (0 < self.risk_pct_min <= self.risk_pct_max <= 1.0):
            raise ValueError("require 0 < risk_pct_min <= risk_pct_max <= 1")
        if not (0.0 <= self.default_conviction <= 1.0):
            raise ValueError("conviction must be in [0, 1]")
        size = float(self.max_size_frac)
        if not math.isfinite(size) or size <= 0.0:
            raise ValueError(
                f"max_size_frac (leverage) must be finite and positive, got {self.max_size_frac!r}"
            )

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
