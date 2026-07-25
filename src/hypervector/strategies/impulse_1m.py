"""Hypertrader 1m Impulse Strategy Port for Hypervector.

Generates mean-reversion & momentum impulse entries based on 1m candle metrics:
  - close_vs_ema21_bps: (close - EMA(21)) / EMA(21) * 10,000
  - di_delta: Plus_DI(14) - Minus_DI(14)
  - roc_5: Rate of Change (5-bar lookback %)

Default Hypertrader Thresholds:
  - Long:  close_vs_ema21_bps <= -25.0 bps, di_delta <= -30.0, roc_5 <= -0.25%
  - Short: close_vs_ema21_bps >=  20.0 bps, di_delta >=  25.0, roc_5 >=  0.20%
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hypervector.regime.detectors import detect_regime_ema
from hypervector.strategies.indicators import ema
from hypervector.strategies.registry import SignalBuilder, StrategySpec, register


def build_impulse_1m_signals(
    df: pd.DataFrame,
    *,
    direction: str = "long",
    ema_period: int = 21,
    di_period: int = 14,
    roc_period: int = 5,
    long_ema: float = -25.0,
    long_di: float = -30.0,
    long_roc: float = -0.25,
    short_ema: float = 20.0,
    short_di: float = 25.0,
    short_roc: float = 0.20,
    range_only: bool = False,
    regime_fast: int = 12,
    regime_slow: int = 48,
    regime_band: float = 0.001,
    **kwargs: Any,
) -> tuple[pd.Series, pd.Series, str]:
    """Build 1m Impulse signals for Long or Short track matching Hypertrader."""
    if direction not in ("long", "short"):
        raise ValueError("direction must be 'long' or 'short'")

    close = df["close"].astype(float)

    # 1. EMA(21) & Close vs EMA in basis points
    ema_val = ema(close, length=ema_period)
    close_vs_ema_bps = (close - ema_val) / ema_val * 10_000.0

    # 2. DI Delta (Plus DI - Minus DI) via build_feature_matrix
    from hypervector.ml.feature_matrix import build_feature_matrix

    feats = build_feature_matrix(df)
    if "di_delta_1m" in feats.columns:
        di_delta = feats["di_delta_1m"]
    else:
        di_delta = pd.Series(0.0, index=df.index)

    # 3. ROC (5-bar lookback %)
    roc_5 = (close - close.shift(roc_period)) / close.shift(roc_period) * 100.0

    if direction == "long":
        # Long gate: oversold impulse stretch
        entries = (
            (close_vs_ema_bps <= long_ema) & (di_delta <= long_di) & (roc_5 <= long_roc)
        )
        # Standard continuation exit on EMA recovery
        exits = close >= ema_val
    else:
        # Short gate: overbought impulse stretch
        entries = (
            (close_vs_ema_bps >= short_ema)
            & (di_delta >= short_di)
            & (roc_5 >= short_roc)
        )
        # Standard continuation exit on EMA recovery
        exits = close <= ema_val

    if range_only:
        labels = detect_regime_ema(
            close,
            fast=int(regime_fast),
            slow=int(regime_slow),
            range_band=float(regime_band),
        )
        range_mask = labels == "range"
        entries = entries & range_mask
        exits = exits | (~range_mask)

    # Ensure boolean Series
    entries = entries.fillna(False).astype(bool)
    exits = exits.fillna(False).astype(bool)

    tag = f"impulse_1m_range_{direction}" if range_only else f"impulse_1m_{direction}"
    return entries, exits, tag


_LONG_PARAM_GRID: dict[str, list[Any]] = {
    "long_ema": [-50.0, -35.0, -25.0, -15.0],
    "long_di": [-40.0, -30.0, -20.0],
    "long_roc": [-0.50, -0.25, -0.10],
}
_SHORT_PARAM_GRID: dict[str, list[Any]] = {
    "short_ema": [15.0, 20.0, 30.0, 45.0],
    "short_di": [15.0, 25.0, 35.0],
    "short_roc": [0.10, 0.20, 0.40],
}
_RANGE_PARAM_GRID: dict[str, list[Any]] = {
    "regime_fast": [9, 12],
    "regime_slow": [36, 48],
    "regime_band": [0.0005, 0.001, 0.002],
}


def _impulse_builder(direction: str, *, range_only: bool = False) -> SignalBuilder:
    """Bind direction and range policy while retaining tunable keyword args."""
    return lambda df, **kw: build_impulse_1m_signals(
        df,
        direction=direction,
        range_only=range_only,
        **kw,
    )


def register_impulse_1m() -> None:
    """Explicitly register impulse_1m strategy specs (idempotent across registry clears)."""
    register(
        StrategySpec(
            name="impulse_1m_long",
            role="uptrend",
            description="1m Impulse Long Strategy (Close vs EMA21 + DI Delta + ROC)",
            build_signals=_impulse_builder("long"),
            param_grid=dict(_LONG_PARAM_GRID),
        )
    )

    register(
        StrategySpec(
            name="impulse_1m_short",
            role="downtrend",
            description="1m Impulse Short Strategy (Close vs EMA21 + DI Delta + ROC)",
            build_signals=_impulse_builder("short"),
            param_grid=dict(_SHORT_PARAM_GRID),
        )
    )
    register(
        StrategySpec(
            name="impulse_1m_range_long",
            role="regime",
            description="Range-only 1m impulse mean-reversion, long component",
            build_signals=_impulse_builder("long", range_only=True),
            param_grid={**_LONG_PARAM_GRID, **_RANGE_PARAM_GRID},
        )
    )
    register(
        StrategySpec(
            name="impulse_1m_range_short",
            role="regime",
            description="Range-only 1m impulse mean-reversion, short component",
            build_signals=_impulse_builder("short", range_only=True),
            param_grid={**_SHORT_PARAM_GRID, **_RANGE_PARAM_GRID},
        )
    )


# Register on initial import
register_impulse_1m()
