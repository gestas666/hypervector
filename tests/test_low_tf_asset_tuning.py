from __future__ import annotations

from dataclasses import replace

import pandas as pd

from hypervector.research.low_tf_asset_tuning import (
    declared_tuning_trials,
    evaluate_tuning_trial,
    feature_config_for_entry,
    order_trial_results,
    screen_tuning_trial,
    select_development_trials,
    summarize_development_results,
)
from hypervector.research.low_tf_asset_tuning_models import (
    LowTfAssetTrial,
    TrendEntryShape,
    TrendExitShape,
    TuningScenario,
    TuningTrialResult,
)


def _trial(symbol: str, side: str, lookback: int) -> LowTfAssetTrial:
    return LowTfAssetTrial(
        symbol,
        side,  # type: ignore[arg-type]
        TrendEntryShape(lookback, 13, 34, 20.0, 8.0),
        TrendExitShape(80.0, 2.0, 24),
    )


def _result(
    trial: LowTfAssetTrial,
    *,
    net: float,
    drawdown: float,
    trades: int,
    monthly: tuple[tuple[str, float], ...],
    liquidations: int = 0,
) -> TuningTrialResult:
    return TuningTrialResult(
        trial_id=trial.trial_id,
        symbol=trial.symbol,
        side=trial.side,
        segment="development",
        scenario="nominal",
        signal_count=trades,
        completed_trades=trades,
        wins=max(0, trades - 1),
        losses=min(1, trades),
        net_pnl_usd=net,
        profit_factor=2.0 if net > 0.0 else 0.5,
        maximum_drawdown_pct=drawdown,
        total_fees_usd=float(trades),
        funding_cashflow_usd=0.0,
        liquidations=liquidations,
        rejection_count=0,
        monthly_net_pnl_usd=monthly,
    )


def test_development_ranking_is_separate_by_asset_and_side() -> None:
    eth_long = _trial("ETH", "long", 24)
    eth_short = _trial("ETH", "short", 24)
    sol_long = _trial("SOL", "long", 24)
    results = (
        _result(
            eth_long,
            net=100.0,
            drawdown=2.0,
            trades=12,
            monthly=(("a", 50.0), ("b", 50.0)),
        ),
        _result(eth_short, net=50.0, drawdown=1.0, trades=10, monthly=(("a", 50.0),)),
        _result(sol_long, net=75.0, drawdown=1.5, trades=8, monthly=(("a", 75.0),)),
    )

    summaries = summarize_development_results((eth_long, eth_short, sol_long), results)

    assert [(row.symbol, row.side, row.rank) for row in summaries] == [
        ("ETH", "long", 1),
        ("ETH", "short", 1),
        ("SOL", "long", 1),
    ]


def test_declared_trials_cover_both_assets_sides_and_complete_surface() -> None:
    trials = declared_tuning_trials()

    assert len(trials) == 1_728
    assert len({trial.trial_id for trial in trials}) == len(trials)
    assert {(trial.symbol, trial.side) for trial in trials} == {
        ("ETH", "long"),
        ("ETH", "short"),
        ("SOL", "long"),
        ("SOL", "short"),
    }


def test_development_selection_is_bounded_and_separate_by_asset_side() -> None:
    trials = tuple(
        _trial(symbol, side, lookback)
        for symbol in ("ETH", "SOL")
        for side in ("long", "short")
        for lookback in (24, 48, 120)
    )
    results = tuple(
        _result(
            trial,
            net=float(200 - trial.entry.breakout_lookback),
            drawdown=2.0,
            trades=10,
            monthly=(("a", 10.0),),
        )
        for trial in trials
    )
    summaries = summarize_development_results(trials, results)

    selected = select_development_trials(trials, summaries, per_group=2)

    assert len(selected) == 8
    assert all(
        sum(item.symbol == symbol and item.side == side for item in selected) == 2
        for symbol in ("ETH", "SOL")
        for side in ("long", "short")
    )


def test_parallel_results_are_restored_to_declared_trial_order() -> None:
    first = _trial("ETH", "long", 24)
    second = _trial("ETH", "long", 48)
    first_result = _result(
        first, net=1.0, drawdown=1.0, trades=1, monthly=(("a", 1.0),)
    )
    second_result = _result(
        second, net=2.0, drawdown=1.0, trades=1, monthly=(("a", 2.0),)
    )

    ordered = order_trial_results((first, second), (second_result, first_result))

    assert [result.trial_id for result in ordered] == [
        first.trial_id,
        second.trial_id,
    ]


def test_ranking_retains_losing_and_zero_trade_trials() -> None:
    winner = _trial("SOL", "short", 24)
    loser = _trial("SOL", "short", 48)
    zero = _trial("SOL", "short", 120)
    results = (
        _result(
            winner,
            net=100.0,
            drawdown=2.0,
            trades=12,
            monthly=(("a", 60.0), ("b", 40.0)),
        ),
        _result(loser, net=-25.0, drawdown=3.0, trades=5, monthly=(("a", -25.0),)),
        _result(zero, net=0.0, drawdown=0.0, trades=0, monthly=()),
    )

    summaries = summarize_development_results((winner, loser, zero), results)

    assert len(summaries) == 3
    assert [row.trial_id for row in summaries] == [
        winner.trial_id,
        zero.trial_id,
        loser.trial_id,
    ]
    assert summaries[1].completed_trades == 0
    assert summaries[2].net_pnl_usd == -25.0


def test_liquidation_is_ranked_below_otherwise_equal_result() -> None:
    safe = _trial("ETH", "long", 24)
    liquidated = _trial("ETH", "long", 48)
    safe_result = _result(
        safe, net=50.0, drawdown=4.0, trades=8, monthly=(("a", 50.0),)
    )
    liquidated_result = replace(
        _result(
            liquidated,
            net=100.0,
            drawdown=4.0,
            trades=8,
            monthly=(("a", 100.0),),
        ),
        liquidations=1,
    )

    summaries = summarize_development_results(
        (safe, liquidated), (safe_result, liquidated_result)
    )

    assert summaries[0].trial_id == safe.trial_id
    assert summaries[1].trial_id == liquidated.trial_id


def test_positive_net_ranks_above_losing_trial_with_more_positive_months() -> None:
    profitable = _trial("SOL", "long", 24)
    losing = _trial("SOL", "long", 48)
    results = (
        _result(
            profitable,
            net=10.0,
            drawdown=2.0,
            trades=8,
            monthly=(("a", -5.0), ("b", 15.0)),
        ),
        _result(
            losing,
            net=-100.0,
            drawdown=2.0,
            trades=8,
            monthly=(("a", 1.0), ("b", 1.0), ("c", -102.0)),
        ),
    )

    summaries = summarize_development_results((profitable, losing), results)

    assert summaries[0].trial_id == profitable.trial_id


def test_feature_config_maps_the_trial_entry_shape() -> None:
    entry = TrendEntryShape(48, 13, 34, 35.0, 4.0)

    config = feature_config_for_entry(entry)

    assert config.breakout_lookback == 48
    assert config.ema_fast == 13
    assert config.ema_slow == 34


def test_tuning_trial_replays_fixed_contract_and_reports_monthly_result() -> None:
    trial = _trial("ETH", "long", 48)
    features = _replay_features()
    minutes = _profitable_long_minutes()

    result = evaluate_tuning_trial(
        minute_bars=minutes,
        features=features,
        trial=trial,
        segment="development",
        scenario=TuningScenario("nominal", 13.0),
        venue_max_leverage=25.0,
    )

    assert result.trial_id == trial.trial_id
    assert result.signal_count == 1
    assert result.completed_trades == 1
    assert result.wins == 1
    assert result.net_pnl_usd > 0.0
    assert result.total_fees_usd > 0.0
    assert result.liquidations == 0
    assert result.monthly_net_pnl_usd[0][0] == "2026-01"


def test_broad_screen_uses_next_bar_entry_and_fixed_runtime_barriers() -> None:
    trial = _trial("SOL", "long", 48)
    features = _screen_features()
    bars = _screen_bars()

    result = screen_tuning_trial(
        bars=bars,
        features=features,
        trial=trial,
        segment="development",
        scenario=TuningScenario("nominal", 13.0),
        venue_max_leverage=20.0,
    )

    assert result.signal_count == 1
    assert result.completed_trades == 1
    assert result.wins == 1
    assert result.net_pnl_usd > 0.0
    assert result.liquidations == 0


def _replay_features() -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=4, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "bar_open_at": times,
            "close": [100.0, 100.0, 100.0, 101.0],
            "breakout_high_120": [100.0] * 4,
            "breakout_low_120": [100.0] * 4,
            "ema_fast_5m": [100.0, 100.0, 100.0, 100.5],
            "ema_slow_5m": [100.0] * 4,
            "bbwp_percentile": [50.0, 50.0, 10.0, 40.0],
            "bbwp_signal": [30.0, 30.0, 20.0, 25.0],
            "context_direction": [0, 0, 0, 1],
            "context_fast_slope_bps": [0.0, 0.0, 0.0, 1.0],
            "rsi": [50.0] * 4,
            "rsi_signal": [50.0] * 4,
            "pmarp": [50.0] * 4,
        }
    )


def _profitable_long_minutes() -> pd.DataFrame:
    times = pd.date_range("2026-01-01T00:20:00Z", periods=10, freq="1min")
    frame = pd.DataFrame(
        {
            "timestamp": times,
            "open": [101.0] * 10,
            "high": [101.2] * 10,
            "low": [100.9] * 10,
            "close": [101.1] * 10,
            "funding_rate": [0.0] * 10,
        }
    )
    frame.loc[5, ["high", "close"]] = [103.0, 102.8]
    return frame


def _screen_features() -> pd.DataFrame:
    frame = _replay_features()
    future = frame.iloc[[-1]].copy()
    future["bar_open_at"] = pd.Timestamp("2026-01-01T00:20:00Z")
    future["bbwp_percentile"] = 40.0
    future_two = future.copy()
    future_two["bar_open_at"] = pd.Timestamp("2026-01-01T00:25:00Z")
    return pd.concat([frame, future, future_two], ignore_index=True)


def _screen_bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=6, freq="5min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 101.0, 101.0, 102.8],
            "high": [100.2, 100.2, 100.2, 101.2, 103.0, 103.0],
            "low": [99.8, 99.8, 99.8, 100.8, 100.9, 102.5],
            "close": [100.0, 100.0, 100.0, 101.0, 102.8, 102.8],
            "volume": [1.0] * 6,
            "funding_rate": [0.0] * 6,
        },
        index=index,
    )
    return frame
