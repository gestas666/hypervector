"""Adapters from registered strategy builders to one shared signal stream."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from hypervector.strategies.registry import StrategySpec


def build_registered_strategy_pair_signals(
    bars: pd.DataFrame,
    *,
    long_strategy_name: str | None,
    short_strategy_name: str | None,
    long_params: Mapping[str, object] | None = None,
    short_params: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    """Resolve a registered long and short strategy into side-specific causal signals."""
    from hypervector.strategies import register_all_strategies
    from hypervector.strategies.registry import get_strategy

    register_all_strategies()
    return build_strategy_pair_signals_from_specs(
        bars,
        long_spec=get_strategy(long_strategy_name) if long_strategy_name else None,
        short_spec=get_strategy(short_strategy_name) if short_strategy_name else None,
        long_params=long_params,
        short_params=short_params,
    )


def build_registered_strategy_pair_on_timeframe(
    bars: pd.DataFrame,
    *,
    timeframe: str,
    long_strategy_name: str,
    short_strategy_name: str,
    long_params: Mapping[str, object] | None = None,
    short_params: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    """Build completed higher-timeframe signals for 1-minute execution."""
    from hypervector.strategies import register_all_strategies
    from hypervector.strategies.registry import get_strategy

    register_all_strategies()
    return build_strategy_pair_signals_on_timeframe_from_specs(
        bars,
        timeframe=timeframe,
        long_spec=get_strategy(long_strategy_name),
        short_spec=get_strategy(short_strategy_name),
        long_params=long_params,
        short_params=short_params,
    )


def build_strategy_pair_signals_on_timeframe_from_specs(
    bars: pd.DataFrame,
    *,
    timeframe: str,
    long_spec: StrategySpec,
    short_spec: StrategySpec,
    long_params: Mapping[str, object] | None = None,
    short_params: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    """Project completed higher-timeframe decisions onto causal minute closes."""
    delta, source_bars = _resample_complete_bars(bars, timeframe)
    source_signals = build_strategy_pair_signals_from_specs(
        source_bars,
        long_spec=long_spec,
        short_spec=short_spec,
        long_params=long_params,
        short_params=short_params,
    )
    return _project_completed_signals(
        bars, source_signals, delta, long_spec.name, short_spec.name, timeframe
    )


def build_strategy_pair_signals_from_specs(
    bars: pd.DataFrame,
    *,
    long_spec: StrategySpec | None,
    short_spec: StrategySpec | None,
    long_params: Mapping[str, object] | None = None,
    short_params: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    """Build and validate a long/short pair without funding separate accounts."""
    if long_spec is None and short_spec is None:
        raise ValueError("at least one strategy side must be active")
    long_entry, long_exit = _build_optional_side(
        bars, long_spec, "long", long_params or {}
    )
    short_entry, short_exit = _build_optional_side(
        bars, short_spec, "short", short_params or {}
    )
    return pd.DataFrame(
        {
            "long_entry": long_entry,
            "short_entry": short_entry,
            "long_exit": long_exit,
            "short_exit": short_exit,
            "long_signal_name": long_spec.name if long_spec else "inactive_long",
            "short_signal_name": short_spec.name if short_spec else "inactive_short",
        },
        index=bars.index,
    )


def _build_optional_side(
    bars: pd.DataFrame,
    spec: StrategySpec | None,
    expected_direction: str,
    params: Mapping[str, object],
) -> tuple[pd.Series, pd.Series]:
    if spec is None:
        inactive = pd.Series(False, index=bars.index, dtype=bool)
        return inactive.copy(), inactive
    return _build_side(bars, spec, expected_direction, params)


def _build_side(
    bars: pd.DataFrame,
    spec: StrategySpec,
    expected_direction: str,
    params: Mapping[str, object],
) -> tuple[pd.Series, pd.Series]:
    entries, exits, direction = spec.build_signals(bars, **dict(params))
    clean = "short" if "short" in str(direction).lower() else "long"
    if clean != expected_direction:
        raise ValueError(
            f"strategy {spec.name} must report {expected_direction} direction"
        )
    return _boolean_signal(entries, bars, spec.name), _boolean_signal(
        exits, bars, spec.name
    )


def _boolean_signal(
    signal: pd.Series,
    bars: pd.DataFrame,
    strategy_name: str,
) -> pd.Series:
    if not signal.index.equals(bars.index):
        raise ValueError(f"strategy {strategy_name} returned a misaligned signal")
    return signal.fillna(False).astype(bool)


def _resample_complete_bars(
    bars: pd.DataFrame,
    timeframe: str,
) -> tuple[pd.Timedelta, pd.DataFrame]:
    delta = pd.Timedelta(timeframe)
    minute = pd.Timedelta(minutes=1)
    if delta < minute or delta % minute != pd.Timedelta(0):
        raise ValueError("strategy timeframe must be whole positive minutes")
    ratio = int(delta / minute)
    grouped = bars.resample(timeframe, label="left", closed="left")
    result = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    complete = grouped.size().eq(ratio)
    return delta, result.loc[complete].dropna()


def _project_completed_signals(
    bars: pd.DataFrame,
    source: pd.DataFrame,
    delta: pd.Timedelta,
    long_name: str,
    short_name: str,
    timeframe: str,
) -> pd.DataFrame:
    columns = ("long_entry", "short_entry", "long_exit", "short_exit")
    projected = pd.DataFrame(False, index=bars.index, columns=columns)
    endpoints = source.index + delta - pd.Timedelta(minutes=1)
    valid = endpoints.isin(projected.index)
    for column in columns:
        projected.loc[endpoints[valid], column] = source.loc[valid, column].to_numpy()
    projected["long_signal_name"] = f"{long_name}@{timeframe}"
    projected["short_signal_name"] = f"{short_name}@{timeframe}"
    return projected
