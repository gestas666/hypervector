"""Hypervelocity reverse-engineered scalper signals (docs/external plan)."""

from __future__ import annotations

import pandas as pd

from hypervector.data.sources import fixture_ohlcv
from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.strategies.hypervelocity import (
    build_hypervelocity_signals,
    current_hypervelocity_entry_allowed,
    hypervelocity_long,
    hypervelocity_short,
    register_hypervelocity,
)
from hypervector.strategies.registry import clear_registry, get_strategy
from hypervector.sweep.search import run_grid_search


def test_hypervelocity_long_returns_bool_series():
    df = fixture_ohlcv(n_bars=3000, drift=8.0, wave_period=120)
    entries, exits, direction = hypervelocity_long(df)
    assert direction == "long"
    assert entries.dtype == bool
    assert exits.dtype == bool
    assert len(entries) == len(df)
    assert not (entries & exits).any()


def test_hypervelocity_short_mirrors_long():
    df = fixture_ohlcv(n_bars=3000, drift=-8.0, wave_period=120)
    entries, exits, direction = hypervelocity_short(df)
    assert direction == "short"
    assert entries.dtype == bool
    assert len(exits) == len(df)


def _regime_decisions(
    index: pd.Index,
    primary: list[PrimaryRegime],
    breakout: list[BreakoutDirection | None] | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "primary_regime": [state.value for state in primary],
            "breakout_direction": [
                direction.value if direction else None
                for direction in (breakout or [None] * len(primary))
            ],
        },
        index=index,
    )


def test_long_entries_use_backend_regime_without_range_entries(monkeypatch):
    df = fixture_ohlcv(n_bars=6, drift=0.0, wave_period=100)
    decisions = _regime_decisions(
        df.index,
        [
            PrimaryRegime.RANGE,
            PrimaryRegime.TREND_UP,
            PrimaryRegime.TREND_UP,
            PrimaryRegime.RANGE,
            PrimaryRegime.TREND_DOWN,
            PrimaryRegime.UNKNOWN,
        ],
    )
    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        lambda _bars, config: decisions,
    )

    entries, exits, _ = hypervelocity_long(df)

    assert entries.tolist() == [False, True, False, False, False, False]
    assert not exits.any()


def test_direction_confirmed_breakout_is_entry_eligible(monkeypatch):
    df = fixture_ohlcv(n_bars=4, drift=0.0, wave_period=100)
    decisions = _regime_decisions(
        df.index,
        [PrimaryRegime.RANGE, PrimaryRegime.BREAKOUT] * 2,
        [None, BreakoutDirection.UPWARD, None, BreakoutDirection.DOWNWARD],
    )
    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        lambda _bars, config: decisions,
    )

    long_entries, _, _ = hypervelocity_long(df)
    short_entries, _, _ = hypervelocity_short(df)

    assert long_entries.tolist() == [False, True, False, False]
    assert short_entries.tolist() == [False, False, False, True]


def test_target_margin_maps_to_price_move(monkeypatch):
    """8% margin at 40x == 0.2% price target; barrier exit must fire after entry."""
    index = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0] * 5,
            "high": [100.0, 100.0, 100.21, 100.0, 100.0],
            "low": [100.0] * 5,
            "close": [100.0] * 5,
            "volume": [100.0] * 5,
        },
        index=index,
    )
    decisions = _regime_decisions(index, [PrimaryRegime.TREND_UP] * 5)
    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        lambda _bars, config: decisions,
    )
    entries, exits, _ = build_hypervelocity_signals(
        df, direction="long", target_margin_pct=8.0, leverage=40.0
    )
    assert entries.tolist() == [True, False, False, True, False]
    assert exits.tolist() == [False, False, True, False, False]


def test_adverse_move_does_not_invent_unobserved_stop(monkeypatch):
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0] * 3,
            "high": [100.0] * 3,
            "low": [100.0, 90.0, 90.0],
            "close": [100.0] * 3,
            "volume": [100.0] * 3,
        },
        index=index,
    )
    decisions = _regime_decisions(index, [PrimaryRegime.TREND_UP] * 3)
    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        lambda _bars, config: decisions,
    )

    _, exits, _ = hypervelocity_long(df)

    assert not exits.any()


def test_hypervelocity_grid_runs():
    clear_registry()
    register_hypervelocity()
    df = fixture_ohlcv(n_bars=6000, drift=10.0, wave_period=100)
    strat = get_strategy("hypervelocity_1m_scalper_long")
    results = run_grid_search(
        df,
        strat,
        param_grid={
            "target_margin_pct": [8.0],
            "leverage": [40.0],
        },
    )
    assert results
    ok = [r for r in results if r.status == "ok"]
    assert ok
    assert "net_pnl" in ok[0].metrics
    assert ok[0].metrics["position_notional_fraction"] == 28.0
    assert ok[0].metrics["strategy_managed_exits"] is True
    clear_registry()
def test_current_entry_allowed_uses_latest_canonical_regime(monkeypatch) -> None:
    df = fixture_ohlcv(n_bars=80)
    decisions = pd.DataFrame(
        {
            "primary_regime": [PrimaryRegime.RANGE.value] * 79
            + [PrimaryRegime.TREND_DOWN.value],
            "breakout_direction": [None] * 80,
        },
        index=df.index,
    )
    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        lambda frame, config: decisions,
    )

    assert current_hypervelocity_entry_allowed(df, direction="short") is True
    assert current_hypervelocity_entry_allowed(df, direction="long") is False
