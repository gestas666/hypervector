"""Causal 30m/2h/6h regime telemetry for rebuilt Hulk Smash."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig, classify_timeframe
from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.strategies.hypervelocity_contract import faithful_regime_config

_BAR_COLUMNS = {"open", "high", "low", "close", "volume"}


def build_hulk_regime_frame(
    bars: pd.DataFrame,
    config: RegimeClassifierConfig | None = None,
) -> pd.DataFrame:
    """Build point-in-time 30m execution, 2h primary, and 6h context states."""
    frame = _validated_bars(bars)
    cfg = config or faithful_regime_config()
    gaps = frame.index.to_series().diff().ne(pd.Timedelta(minutes=30))
    blocks = [
        _build_contiguous(block, cfg)
        for _, block in frame.groupby(gaps.cumsum().to_numpy(), sort=True)
    ]
    return pd.concat(blocks).sort_index()


def _build_contiguous(
    frame: pd.DataFrame,
    config: RegimeClassifierConfig,
) -> pd.DataFrame:
    tactical = classify_timeframe(frame, config)
    primary = _aligned_higher_state(frame, config, minutes=120, prefix="2h")
    context = _aligned_higher_state(frame, config, minutes=360, prefix="6h")
    return pd.DataFrame(
        {
            "regime_30m": tactical["primary_regime"],
            "regime_30m_breakout": tactical["breakout_direction"],
            "regime_30m_strength": tactical["regime_strength_score"],
            "regime_2h_primary": primary["state"],
            "regime_2h_breakout": primary["breakout"],
            "regime_2h_strength": primary["strength"],
            "regime_2h_available_at": primary["available_at"],
            "regime_6h_context": context["state"],
            "regime_6h_breakout": context["breakout"],
            "regime_6h_strength": context["strength"],
            "regime_6h_available_at": context["available_at"],
        },
        index=frame.index,
    )


def annotate_hulk_signal_regimes(
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
) -> pd.DataFrame:
    """Attach exact decision-time regime alignment without changing eligibility."""
    required = {"signal_time_utc", "side", "eligible"}
    missing = sorted(required.difference(signals.columns))
    if missing:
        raise ValueError(f"Hulk regime signals missing columns: {missing}")
    _validate_regime_frame(regimes)
    times = pd.to_datetime(signals["signal_time_utc"], utc=True, errors="raise")
    if not pd.DatetimeIndex(times).isin(regimes.index).all():
        raise ValueError("Hulk signal regime timestamp is unavailable")
    aligned = regimes.reindex(pd.DatetimeIndex(times)).reset_index(drop=True)
    result = signals.copy(deep=True)
    for column in aligned.columns:
        result[column] = aligned[column].to_numpy()
    result["regime_primary_alignment"] = _alignment(
        result["side"], result["regime_2h_primary"], result["regime_2h_breakout"]
    )
    result["regime_context_alignment"] = _alignment(
        result["side"], result["regime_6h_context"], result["regime_6h_breakout"]
    )
    result["regime_execution_authority"] = "none"
    return result


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_BAR_COLUMNS.difference(bars.columns))
    index = pd.DatetimeIndex(bars.index)
    aligned = index.floor("30min").equals(index)
    if bars.empty or missing or index.tz is None or not aligned:
        raise ValueError(
            f"Hulk regime requires complete aligned 30m bars: missing={missing}"
        )
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("Hulk regime bar index must be ordered and unique")
    frame = bars.loc[:, ["open", "high", "low", "close", "volume"]].astype(float)
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError("Hulk regime bars must be finite")
    return frame


def _aligned_higher_state(
    bars: pd.DataFrame,
    config: RegimeClassifierConfig,
    *,
    minutes: int,
    prefix: str,
) -> pd.DataFrame:
    higher = _complete_resample(bars, minutes)
    if higher.empty:
        return _empty_higher_state(bars.index, prefix)
    classified = classify_timeframe(higher, config)
    available = classified.index + pd.Timedelta(minutes=minutes)
    right = pd.DataFrame(
        {
            "available_at": available,
            "state": classified["primary_regime"].to_numpy(),
            "breakout": classified["breakout_direction"].to_numpy(),
            "strength": classified["regime_strength_score"].to_numpy(float),
        }
    )
    decisions = pd.DataFrame(
        {
            "bar_open_at": bars.index,
            "decision_at": bars.index + pd.Timedelta(minutes=30),
        }
    )
    merged = pd.merge_asof(
        decisions,
        right,
        left_on="decision_at",
        right_on="available_at",
    )
    merged.index = bars.index
    merged["state"] = merged["state"].fillna(PrimaryRegime.UNKNOWN.value)
    merged["strength"] = merged["strength"].fillna(0.0)
    merged.attrs["timeframe"] = prefix
    return merged.loc[:, ["state", "breakout", "strength", "available_at"]]


def _empty_higher_state(index: pd.DatetimeIndex, prefix: str) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "state": PrimaryRegime.UNKNOWN.value,
            "breakout": None,
            "strength": 0.0,
            "available_at": pd.Series(pd.NaT, index=index, dtype="datetime64[ns, UTC]"),
        },
        index=index,
    )
    result.attrs["timeframe"] = prefix
    return result


def _complete_resample(bars: pd.DataFrame, minutes: int) -> pd.DataFrame:
    expected = minutes // 30
    grouped = bars.resample(f"{minutes}min", label="left", closed="left")
    output = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        source_bars=("close", "count"),
    )
    return output.loc[output["source_bars"].eq(expected)].drop(columns="source_bars")


def _validate_regime_frame(regimes: pd.DataFrame) -> None:
    required = {
        "regime_30m",
        "regime_2h_primary",
        "regime_2h_breakout",
        "regime_6h_context",
        "regime_6h_breakout",
    }
    missing = sorted(required.difference(regimes.columns))
    valid = isinstance(regimes.index, pd.DatetimeIndex) and regimes.index.tz
    if regimes.empty or missing or not valid or not regimes.index.is_unique:
        raise ValueError(f"invalid Hulk regime frame: missing={missing}")


def _alignment(
    sides: pd.Series,
    states: pd.Series,
    breakouts: pd.Series,
) -> pd.Series:
    directions = pd.Series(None, index=sides.index, dtype=object)
    directions = directions.mask(states.eq(PrimaryRegime.TREND_UP.value), "long")
    directions = directions.mask(states.eq(PrimaryRegime.TREND_DOWN.value), "short")
    breakout = states.eq(PrimaryRegime.BREAKOUT.value)
    directions = directions.mask(
        breakout & breakouts.eq(BreakoutDirection.UPWARD.value), "long"
    )
    directions = directions.mask(
        breakout & breakouts.eq(BreakoutDirection.DOWNWARD.value), "short"
    )
    result = pd.Series("non_directional", index=sides.index, dtype=object)
    result = result.mask(directions.eq(sides), "aligned")
    return result.mask(directions.notna() & directions.ne(sides), "opposed")
