"""Hypervelocity reverse-engineered scalper signals (docs/external plan)."""

from __future__ import annotations

import pandas as pd

from hypervector.data.sources import fixture_ohlcv
from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.strategies.hypervelocity import (
    build_hypervelocity_signals,
    current_hypervelocity_entry_allowed,
    current_hypervelocity_market,
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
    entries: list[str | None] | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "primary_regime": [state.value for state in primary],
            "breakout_direction": [
                direction.value if direction else None
                for direction in (breakout or [None] * len(primary))
            ],
            "entry_direction": entries or [None] * len(primary),
            "structural_direction": [
                "long"
                if state is PrimaryRegime.TREND_UP
                else "short"
                if state is PrimaryRegime.TREND_DOWN
                else None
                for state in primary
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
        entries=[None, "long", None, None, None, None],
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
        [None, "long", None, "short"],
    )
    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        lambda _bars, config: decisions,
    )

    long_entries, _, _ = hypervelocity_long(df)
    short_entries, _, _ = hypervelocity_short(df)

    assert long_entries.tolist() == [False, True, False, False]
    assert short_entries.tolist() == [False, False, False, True]


def test_structural_trend_does_not_require_tactical_annotation_to_enter(
    monkeypatch,
) -> None:
    df = fixture_ohlcv(n_bars=4, drift=0.0, wave_period=100)
    decisions = _regime_decisions(
        df.index,
        [PrimaryRegime.TREND_UP] * 4,
        entries=["long"] * 4,
    )
    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        lambda _bars, config: decisions,
    )

    entries, _, _ = hypervelocity_long(df)

    assert entries.tolist() == [True, False, False, False]


def test_target_margin_maps_to_price_move(monkeypatch):
    """8% margin at 30x maps to a 0.2667% target after entry."""
    index = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0] * 5,
            "high": [100.0, 100.0, 100.27, 100.0, 100.0],
            "low": [100.0] * 5,
            "close": [100.0] * 5,
            "volume": [100.0] * 5,
        },
        index=index,
    )
    decisions = _regime_decisions(
        index,
        [PrimaryRegime.TREND_UP] * 5,
        entries=["long", None, None, "long", None],
    )
    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        lambda _bars, config: decisions,
    )
    entries, exits, _ = build_hypervelocity_signals(
        df, direction="long", target_margin_pct=8.0, leverage=30.0
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
    decisions = _regime_decisions(
        index,
        [PrimaryRegime.TREND_UP] * 3,
        entries=["long", None, None],
    )
    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        lambda _bars, config: decisions,
    )

    _, exits, _ = hypervelocity_long(df)

    assert not exits.any()


def test_open_position_holds_through_range_until_fixed_target(monkeypatch):
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0] * 4,
            "high": [100.0, 100.1, 100.25, 100.27],
            "low": [100.0] * 4,
            "close": [100.0] * 4,
            "volume": [100.0] * 4,
        },
        index=index,
    )
    decisions = _regime_decisions(
        index,
        [PrimaryRegime.TREND_UP] + [PrimaryRegime.RANGE] * 3,
        entries=["long", None, None, None],
    )
    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        lambda _bars, config: decisions,
    )

    entries, exits, _ = hypervelocity_long(df)

    assert entries.tolist() == [True, False, False, False]
    assert exits.tolist() == [False, False, False, True]


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
            "leverage": [30.0],
        },
    )
    assert results
    ok = [r for r in results if r.status == "ok"]
    assert ok
    assert "net_pnl" in ok[0].metrics
    assert ok[0].metrics["position_notional_fraction"] == 21.0
    assert ok[0].metrics["strategy_managed_exits"] is True
    clear_registry()


def test_current_entry_allowed_uses_latest_canonical_regime(monkeypatch) -> None:
    df = fixture_ohlcv(n_bars=80)
    decisions = pd.DataFrame(
        {
            "primary_regime": [PrimaryRegime.RANGE.value] * 79
            + [PrimaryRegime.TREND_DOWN.value],
            "breakout_direction": [None] * 80,
            "entry_direction": [None] * 79 + ["short"],
            "structural_direction": [None] * 79 + ["short"],
        },
        index=df.index,
    )
    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        lambda frame, config: decisions,
    )

    assert current_hypervelocity_entry_allowed(df, direction="short") is True
    assert current_hypervelocity_entry_allowed(df, direction="long") is False
    observation = current_hypervelocity_market(df)
    assert observation.structural_direction == "short"
    assert observation.entry_direction == "short"


def test_current_regime_observation_reports_range_as_ineligible(monkeypatch) -> None:
    from hypervector.strategies import hypervelocity as module

    bars = fixture_ohlcv(n_bars=3)
    decisions = _regime_decisions(
        bars.index,
        [PrimaryRegime.TREND_UP, PrimaryRegime.TREND_UP, PrimaryRegime.RANGE],
    )
    monkeypatch.setattr(
        module,
        "_classify_regimes",
        lambda _bars, config: decisions,
    )

    observation = module.current_hypervelocity_regime(bars, direction="long")

    assert observation.primary_regime == PrimaryRegime.RANGE.value
    assert observation.breakout_direction is None
    assert observation.direction == "long"
    assert observation.entry_allowed is False


def test_live_observation_fails_closed_after_bar_gap() -> None:
    bars = fixture_ohlcv(n_bars=80)
    latest = bars.iloc[-1:].copy()
    latest.loc[:, "timestamp"] = pd.Timestamp(
        bars["timestamp"].iloc[-1]
    ) + pd.Timedelta(hours=2)
    gapped = pd.concat([bars, latest], ignore_index=True)

    observation = current_hypervelocity_market(gapped)

    assert observation.primary_regime == PrimaryRegime.UNKNOWN.value
    assert observation.entry_direction is None
