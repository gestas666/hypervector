"""Faithful backend Hypervelocity strategy driven by canonical regime telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from hypervector.regime.models import PrimaryRegime
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
    structural_direction: Direction | None
    entry_direction: Direction | None
    state_1m: str
    state_5m: str
    context_15m: str
    confidence: float
    regime_strength_score: float
    regime_score_source: str
    reason: str
    bbwp_percentile: float | None
    compression_ready: bool
    ema_gap_bps_signed: float | None
    rsi: float | None
    rsi_ema: float | None
    rsi_cross_direction: str | None
    tactical_breakout_direction: str | None
    breakout_volume_ratio: float | None
    prior_range_high: float | None
    prior_range_low: float | None


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


def _latest_contiguous_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Return the latest uninterrupted one-minute segment for live inference."""
    if isinstance(df.index, pd.DatetimeIndex):
        timestamps = df.index
    elif "timestamp" in df.columns:
        timestamps = pd.DatetimeIndex(pd.to_datetime(df["timestamp"], utc=True))
    else:
        raise ValueError(
            "Hypervelocity bars require a DatetimeIndex or timestamp column"
        )
    if len(timestamps) < 2:
        return df
    gaps = pd.Series(timestamps).diff().ne(pd.Timedelta(minutes=1)).to_numpy()
    gap_positions = np.flatnonzero(gaps)
    start = int(gap_positions[-1]) if len(gap_positions) else 0
    return df.iloc[start:]


def _entry_eligibility(decisions: pd.DataFrame, direction: Direction) -> pd.Series:
    required = {"primary_regime", "breakout_direction", "entry_direction"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"regime decisions missing columns: {sorted(missing)}")
    return decisions["entry_direction"].eq(direction).astype(bool)


def _optional_direction(value: object) -> Direction | None:
    if value == "long":
        return "long"
    if value == "short":
        return "short"
    return None


def _optional_text(value: object) -> str | None:
    return None if value is None or pd.isna(value) else str(value)


def _optional_float(value: object) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


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
    decisions = _classify_regimes(
        _latest_contiguous_bars(df),
        regime_config or faithful_regime_config(),
    )
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
    decisions = _classify_regimes(
        _latest_contiguous_bars(df),
        regime_config or faithful_regime_config(),
    )
    latest = decisions.iloc[-1]
    breakout = latest["breakout_direction"]
    breakout_value = None if pd.isna(breakout) else str(breakout)
    direction = _optional_direction(latest.get("entry_direction"))
    structural = _optional_direction(latest.get("structural_direction"))
    return HypervelocityMarketObservation(
        primary_regime=str(latest["primary_regime"]),
        breakout_direction=breakout_value,
        structural_direction=structural,
        entry_direction=direction,
        state_1m=str(latest.get("state_1m", latest["primary_regime"])),
        state_5m=str(latest.get("state_5m", latest["primary_regime"])),
        context_15m=str(latest.get("context_15m", PrimaryRegime.UNKNOWN.value)),
        confidence=float(latest.get("confidence", 0.0)),
        regime_strength_score=float(
            latest.get("regime_strength_score", latest.get("confidence", 0.0))
        ),
        regime_score_source=str(
            latest.get("regime_score_source", "legacy_confidence_alias")
        ),
        reason=str(latest.get("reason", "not_reported")),
        bbwp_percentile=_optional_float(latest.get("bbwp_percentile")),
        compression_ready=bool(latest.get("compression_ready", False)),
        ema_gap_bps_signed=_optional_float(latest.get("ema_gap_bps_signed")),
        rsi=_optional_float(latest.get("rsi")),
        rsi_ema=_optional_float(latest.get("rsi_ema")),
        rsi_cross_direction=_optional_text(latest.get("rsi_cross_direction")),
        tactical_breakout_direction=_optional_text(
            latest.get("tactical_breakout_direction")
        ),
        breakout_volume_ratio=_optional_float(latest.get("breakout_volume_ratio")),
        prior_range_high=_optional_float(latest.get("prior_range_high")),
        prior_range_low=_optional_float(latest.get("prior_range_low")),
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
    leverage: float = 30.0,
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
    leverage: float = 30.0,
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
    leverage: float = 30.0,
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
    "leverage": [30.0],
}


def register_hypervelocity() -> None:
    """Register fixed-contract Hypervelocity strategy specs."""
    shared = {
        "description": (
            "BTC 1m canonical-regime scalper, fixed 30x and 8% margin target"
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
