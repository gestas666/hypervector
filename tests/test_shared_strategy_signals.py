"""Signal adapter tests for shared-portfolio strategy pairs."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.shared_strategy_signals import (
    build_strategy_pair_signals_on_timeframe_from_specs,
    build_strategy_pair_signals_from_specs,
)
from hypervector.strategies.registry import SignalBuilder, StrategySpec


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * 4,
            "high": [101.0] * 4,
            "low": [99.0] * 4,
            "close": [100.0] * 4,
            "volume": [1.0] * 4,
        },
        index=index,
    )


def _builder(
    direction: str,
    entry_position: int,
    exit_position: int,
) -> SignalBuilder:
    def build(
        bars: pd.DataFrame,
        **_params: object,
    ) -> tuple[pd.Series, pd.Series, str]:
        entries = pd.Series(False, index=bars.index)
        exits = pd.Series(False, index=bars.index)
        entries.iloc[entry_position] = True
        exits.iloc[exit_position] = True
        return entries, exits, direction

    return build


def test_pair_adapter_supports_one_active_side_in_the_shared_account() -> None:
    bars = _bars()
    short_spec = StrategySpec("short_only", "downtrend", {}, _builder("short", 1, 3))

    signals = build_strategy_pair_signals_from_specs(
        bars,
        long_spec=None,
        short_spec=short_spec,
    )

    assert not signals["long_entry"].any()
    assert not signals["long_exit"].any()
    assert set(signals["long_signal_name"]) == {"inactive_long"}
    assert signals["short_entry"].iloc[1]
    assert set(signals["short_signal_name"]) == {"short_only"}


def test_pair_adapter_rejects_two_inactive_sides() -> None:
    with pytest.raises(ValueError, match="at least one strategy side"):
        build_strategy_pair_signals_from_specs(
            _bars(),
            long_spec=None,
            short_spec=None,
        )


def test_pair_adapter_preserves_side_specific_entries_exits_and_attribution() -> None:
    bars = _bars()
    long_spec = StrategySpec("alpha_long", "uptrend", {}, _builder("long", 0, 2))
    short_spec = StrategySpec("beta_short", "downtrend", {}, _builder("short", 1, 3))

    signals = build_strategy_pair_signals_from_specs(
        bars,
        long_spec=long_spec,
        short_spec=short_spec,
    )

    assert list(signals["long_entry"]) == [True, False, False, False]
    assert list(signals["short_entry"]) == [False, True, False, False]
    assert list(signals["long_exit"]) == [False, False, True, False]
    assert list(signals["short_exit"]) == [False, False, False, True]
    assert set(signals["long_signal_name"]) == {"alpha_long"}
    assert set(signals["short_signal_name"]) == {"beta_short"}


def test_pair_adapter_rejects_a_builder_reporting_the_wrong_side() -> None:
    bars = _bars()
    long_spec = StrategySpec("broken_long", "uptrend", {}, _builder("short", 0, 1))
    short_spec = StrategySpec("valid_short", "downtrend", {}, _builder("short", 0, 1))

    with pytest.raises(ValueError, match="broken_long.*long"):
        build_strategy_pair_signals_from_specs(
            bars,
            long_spec=long_spec,
            short_spec=short_spec,
        )


def test_five_minute_signal_appears_only_after_the_completed_source_bar() -> None:
    index = pd.date_range("2026-01-01", periods=10, freq="1min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": range(100, 110),
            "high": range(101, 111),
            "low": range(99, 109),
            "close": range(100, 110),
            "volume": [1.0] * 10,
        },
        index=index,
    )
    long_spec = StrategySpec("slow_long", "uptrend", {}, _builder("long", 0, 1))
    short_spec = StrategySpec("slow_short", "downtrend", {}, _builder("short", 1, 0))

    signals = build_strategy_pair_signals_on_timeframe_from_specs(
        bars,
        timeframe="5min",
        long_spec=long_spec,
        short_spec=short_spec,
    )

    assert signals["long_entry"].iloc[:4].sum() == 0
    assert signals["long_entry"].iloc[4]
    assert signals["short_exit"].iloc[4]
    assert signals["short_entry"].iloc[9]
    assert signals["long_signal_name"].iloc[4] == "slow_long@5min"
