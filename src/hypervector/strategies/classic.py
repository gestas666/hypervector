"""Classic trend baselines: MA cross long (uptrend) / short (downtrend)."""

from __future__ import annotations

import pandas as pd

from hypervector.strategies.registry import StrategySpec, register


def _ma_cross_signals(
    df: pd.DataFrame,
    *,
    fast: int,
    slow: int,
    direction: str,
) -> tuple[pd.Series, pd.Series, str]:
    if fast >= slow:
        raise ValueError("fast must be < slow")
    close = df["close"].astype(float)
    ma_f = close.rolling(fast, min_periods=fast).mean()
    ma_s = close.rolling(slow, min_periods=slow).mean()
    cross_up = (ma_f > ma_s) & (ma_f.shift(1) <= ma_s.shift(1))
    cross_dn = (ma_f < ma_s) & (ma_f.shift(1) >= ma_s.shift(1))
    if direction == "long":
        entries = cross_up.fillna(False)
        exits = cross_dn.fillna(False)
    elif direction == "short":
        # Short on cross down; cover on cross up
        entries = cross_dn.fillna(False)
        exits = cross_up.fillna(False)
    else:
        raise ValueError(f"direction must be long|short, got {direction}")
    return entries.astype(bool), exits.astype(bool), direction


def ma_cross_long(
    df: pd.DataFrame, fast: int = 10, slow: int = 30
) -> tuple[pd.Series, pd.Series, str]:
    return _ma_cross_signals(df, fast=fast, slow=slow, direction="long")


def ma_cross_short(
    df: pd.DataFrame, fast: int = 10, slow: int = 30
) -> tuple[pd.Series, pd.Series, str]:
    return _ma_cross_signals(df, fast=fast, slow=slow, direction="short")


def register_classic_baselines() -> None:
    """Idempotent registration of start-track classic strategies."""
    register(
        StrategySpec(
            name="ma_cross_long",
            role="uptrend",
            param_grid={"fast": [5, 10], "slow": [20, 30]},
            build_signals=ma_cross_long,
            description="SMA cross long-only uptrend baseline",
        )
    )
    register(
        StrategySpec(
            name="ma_cross_short",
            role="downtrend",
            param_grid={"fast": [5, 10], "slow": [20, 30]},
            build_signals=ma_cross_short,
            description="SMA cross short-only downtrend baseline",
        )
    )
