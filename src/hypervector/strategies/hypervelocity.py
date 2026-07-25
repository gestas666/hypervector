"""Faithful backend Hypervelocity strategy driven by canonical regime telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.strategies.hypervelocity_contract import (
    HypervelocityContract,
    faithful_regime_config,
)
from hypervector.strategies.registry import StrategySpec, register

if TYPE_CHECKING:
    from hypervector.regime.classifier import RegimeClassifierConfig

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class HypervelocityRegimeObservation:
    """Latest causal regime state used for a Hypervelocity entry decision."""

    primary_regime: str
    breakout_direction: str | None
    direction: Direction
    entry_allowed: bool


@dataclass(frozen=True)
class HypervelocityMarketObservation:
    """Latest regime state and its single eligible entry direction."""

    primary_regime: str
    breakout_direction: str | None
    entry_direction: Direction | None


def _classify_regimes(
    df: pd.DataFrame,
    config: RegimeClassifierConfig,
) -> pd.DataFrame:
    from hypervector.regime.composite import classify_multitimeframe

    if isinstance(df.index, pd.DatetimeIndex):
        indexed = df
    elif "timestamp" in df.columns:
        indexed = df.copy()
        indexed.index = pd.DatetimeIndex(pd.to_datetime(indexed["timestamp"], utc=True))
    else:
        raise ValueError(
            "Hypervelocity bars require a DatetimeIndex or timestamp column"
        )
    decisions = classify_multitimeframe(indexed, config=config)
    decisions.index = df.index
    return decisions


def _entry_eligibility(decisions: pd.DataFrame, direction: Direction) -> pd.Series:
    required = {"primary_regime", "breakout_direction"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"regime decisions missing columns: {sorted(missing)}")
    primary = decisions["primary_regime"].astype(str)
    breakout = decisions["breakout_direction"].astype(object)
    if direction == "long":
        trend = primary.eq(PrimaryRegime.TREND_UP.value)
        confirmed = breakout.eq(BreakoutDirection.UPWARD.value)
    else:
        trend = primary.eq(PrimaryRegime.TREND_DOWN.value)
        confirmed = breakout.eq(BreakoutDirection.DOWNWARD.value)
    return (trend | (primary.eq(PrimaryRegime.BREAKOUT.value) & confirmed)).astype(bool)


def _target_hit(
    high: float,
    low: float,
    target: float,
    direction: Direction,
) -> bool:
    return high >= target if direction == "long" else low <= target


def current_hypervelocity_entry_allowed(
    df: pd.DataFrame,
    *,
    direction: Direction,
    regime_config: RegimeClassifierConfig | None = None,
) -> bool:
    """Return whether the latest completed bar permits the requested side."""
    if df.empty:
        return False
    observation = current_hypervelocity_regime(
        df,
        direction=direction,
        regime_config=regime_config,
    )
    return observation.entry_allowed


def current_hypervelocity_regime(
    df: pd.DataFrame,
    *,
    direction: Direction,
    regime_config: RegimeClassifierConfig | None = None,
) -> HypervelocityRegimeObservation:
    """Return the latest causal regime state and side-specific eligibility."""
    if df.empty:
        raise ValueError("Hypervelocity regime observation requires at least one bar")
    decisions = _classify_regimes(df, regime_config or faithful_regime_config())
    latest = decisions.iloc[-1]
    breakout = latest["breakout_direction"]
    breakout_value = None if pd.isna(breakout) else str(breakout)
    return HypervelocityRegimeObservation(
        primary_regime=str(latest["primary_regime"]),
        breakout_direction=breakout_value,
        direction=direction,
        entry_allowed=bool(_entry_eligibility(decisions, direction).iloc[-1]),
    )


def current_hypervelocity_market(
    df: pd.DataFrame,
    *,
    regime_config: RegimeClassifierConfig | None = None,
) -> HypervelocityMarketObservation:
    """Return one causal direction, or none while no real trend is eligible."""
    if df.empty:
        raise ValueError("Hypervelocity market observation requires at least one bar")
    decisions = _classify_regimes(df, regime_config or faithful_regime_config())
    latest = decisions.iloc[-1]
    breakout = latest["breakout_direction"]
    breakout_value = None if pd.isna(breakout) else str(breakout)
    long_allowed = bool(_entry_eligibility(decisions, "long").iloc[-1])
    short_allowed = bool(_entry_eligibility(decisions, "short").iloc[-1])
    direction: Direction | None = None
    if long_allowed and not short_allowed:
        direction = "long"
    elif short_allowed and not long_allowed:
        direction = "short"
    return HypervelocityMarketObservation(
        primary_regime=str(latest["primary_regime"]),
        breakout_direction=breakout_value,
        entry_direction=direction,
    )


def _entry_target_signals(
    df: pd.DataFrame,
    eligible: pd.Series,
    *,
    direction: Direction,
    target_price_fraction: float,
) -> tuple[pd.Series, pd.Series]:
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    allowed = eligible.to_numpy(dtype=bool)
    entries = np.zeros(len(df), dtype=bool)
    exits = np.zeros(len(df), dtype=bool)
    in_position = False
    target = np.nan
    multiplier = (
        1.0 + target_price_fraction
        if direction == "long"
        else 1.0 - target_price_fraction
    )
    for position in range(len(df)):
        if in_position and _target_hit(
            high[position], low[position], target, direction
        ):
            exits[position] = True
            in_position = False
            continue
        if not in_position and allowed[position]:
            entries[position] = True
            in_position = True
            target = close[position] * multiplier
    return pd.Series(entries, index=df.index), pd.Series(exits, index=df.index)


def build_hypervelocity_signals(
    df: pd.DataFrame,
    *,
    direction: Direction = "long",
    target_margin_pct: float = 8.0,
    leverage: float = 40.0,
    regime_config: RegimeClassifierConfig | None = None,
) -> tuple[pd.Series, pd.Series, str]:
    """Build TP-only signals from authoritative trend and confirmed-breakout states."""
    contract = HypervelocityContract(
        leverage=float(leverage),
        target_margin_pct=float(target_margin_pct),
    )
    config = regime_config or faithful_regime_config()
    decisions = _classify_regimes(df, config)
    eligible = _entry_eligibility(decisions, direction)
    entries, exits = _entry_target_signals(
        df,
        eligible,
        direction=direction,
        target_price_fraction=contract.target_price_fraction,
    )
    return entries.astype(bool), exits.astype(bool), direction


def hypervelocity_long(
    df: pd.DataFrame,
    *,
    target_margin_pct: float = 8.0,
    leverage: float = 40.0,
    regime_config: RegimeClassifierConfig | None = None,
) -> tuple[pd.Series, pd.Series, str]:
    """Build the faithful long-side Hypervelocity signals."""
    return build_hypervelocity_signals(
        df,
        direction="long",
        target_margin_pct=target_margin_pct,
        leverage=leverage,
        regime_config=regime_config,
    )


def hypervelocity_short(
    df: pd.DataFrame,
    *,
    target_margin_pct: float = 8.0,
    leverage: float = 40.0,
    regime_config: RegimeClassifierConfig | None = None,
) -> tuple[pd.Series, pd.Series, str]:
    """Build the faithful short-side Hypervelocity signals."""
    return build_hypervelocity_signals(
        df,
        direction="short",
        target_margin_pct=target_margin_pct,
        leverage=leverage,
        regime_config=regime_config,
    )


_PARAM_GRID: dict[str, list[float]] = {
    "target_margin_pct": [8.0],
    "leverage": [40.0],
}


def register_hypervelocity() -> None:
    """Register fixed-contract Hypervelocity strategy specs."""
    shared = {
        "description": (
            "BTC 1m canonical-regime scalper, fixed 40x and 8% margin target"
        ),
        "param_grid": dict(_PARAM_GRID),
    }
    register(
        StrategySpec(
            name="hypervelocity_1m_scalper",
            role="regime",
            build_signals=hypervelocity_long,
            **shared,
        )
    )
    register(
        StrategySpec(
            name="hypervelocity_1m_scalper_long",
            role="uptrend",
            build_signals=hypervelocity_long,
            **shared,
        )
    )
    register(
        StrategySpec(
            name="hypervelocity_1m_scalper_short",
            role="downtrend",
            build_signals=hypervelocity_short,
            **shared,
        )
    )
