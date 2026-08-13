"""Acceptance metrics for Hypervelocity-specific regime evaluation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.regime.hypervelocity_eval import (
    _hard_30m_state,
    evaluate_breakout_quality,
    evaluate_entry_alignment,
    evaluate_hypervelocity_regimes,
    evaluate_range_quality,
)
from hypervector.strategies.hypervelocity_contract import faithful_regime_config


def _decisions() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=6, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "primary_regime": [
                "TREND_UP",
                "TREND_UP",
                "TREND_DOWN",
                "RANGE",
                "BREAKOUT",
                "BREAKOUT",
            ],
            "breakout_direction": [None, None, None, None, "BK_UPWARD", "BK_DOWNWARD"],
            "state_1m": ["TREND_UP"] * 6,
            "state_5m": ["TREND_UP"] * 6,
            "context_15m": ["TREND_UP"] * 6,
            "confidence": [1.0] * 6,
            "reason": ["fixture"] * 6,
        },
        index=index,
    )


def _positions(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time_utc": [
                index[0] + pd.Timedelta(minutes=1),
                index[2] + pd.Timedelta(minutes=1),
                index[3] + pd.Timedelta(minutes=1),
            ],
            "side": ["long", "short", "long"],
            "symbol": ["BTC", "BTC", "BTC"],
        }
    )


def test_entry_alignment_reports_false_range_without_aborting() -> None:
    decisions = _decisions()

    result = evaluate_entry_alignment(decisions, _positions(decisions.index))

    assert result.total_entries == 3
    assert result.direction_matches == 2
    assert result.direction_recall_pct == 200.0 / 3.0
    assert result.false_range_at_entries == 1
    assert result.no_entry_state_at_entries == 1
    assert result.recorded_positions == 3
    assert result.unique_entry_decisions == 3


def test_entry_alignment_clusters_split_fills_into_one_decision() -> None:
    decisions = _decisions()
    positions = pd.DataFrame(
        {
            "open_time_utc": [
                decisions.index[0] + pd.Timedelta(minutes=1),
                decisions.index[0] + pd.Timedelta(minutes=1, milliseconds=500),
                decisions.index[2] + pd.Timedelta(minutes=1),
            ],
            "side": ["long", "long", "short"],
            "symbol": ["BTC", "BTC", "BTC"],
        }
    )

    result = evaluate_entry_alignment(decisions, positions)

    assert result.recorded_positions == 3
    assert result.unique_entry_decisions == 2
    assert result.total_entries == 2
    assert result.direction_matches == 2


def test_entry_alignment_accepts_mixed_iso_timestamp_precision() -> None:
    decisions = _decisions()
    positions = pd.DataFrame(
        {
            "open_time_utc": [
                "2026-01-01T00:01:00.250000+00:00",
                "2026-01-01T00:03:00+00:00",
            ],
            "side": ["long", "short"],
            "symbol": ["BTC", "BTC"],
        }
    )

    result = evaluate_entry_alignment(decisions, positions)

    assert result.total_entries == 2
    assert result.direction_matches == 2


def test_entry_alignment_reconciles_peak_and_trade_duplicate() -> None:
    decisions = _decisions()
    positions = pd.DataFrame(
        {
            "record_source": ["position_peak_only", "trade_only"],
            "symbol": ["BTC", "BTC"],
            "side": ["long", "long"],
            "open_time_utc": [decisions.index[0], decisions.index[1]],
            "close_time_utc": [decisions.index[4], decisions.index[4]],
            "entry_price": [100.0, 100.0],
            "quantity": [0.01, 0.01],
        }
    )

    result = evaluate_entry_alignment(decisions, positions)

    assert result.recorded_positions == 2
    assert result.unique_entry_decisions == 1


def test_entry_alignment_uses_tactical_direction_when_backend_publishes_it() -> None:
    decisions = _decisions()
    decisions["primary_regime"] = "TREND_UP"
    decisions["entry_direction"] = [None, None, "short", None, None, None]
    positions = pd.DataFrame(
        {
            "open_time_utc": [
                decisions.index[0] + pd.Timedelta(minutes=1),
                decisions.index[2] + pd.Timedelta(minutes=1),
            ],
            "side": ["long", "short"],
            "symbol": ["BTC", "BTC"],
        }
    )

    result = evaluate_entry_alignment(decisions, positions)

    assert result.direction_matches == 1
    assert result.no_entry_state_at_entries == 1


def test_entry_alignment_reports_resting_order_lookback_separately() -> None:
    decisions = _decisions()
    positions = pd.DataFrame(
        {
            "open_time_utc": [decisions.index[3] + pd.Timedelta(minutes=1)],
            "side": ["short"],
            "symbol": ["BTC"],
        }
    )

    result = evaluate_entry_alignment(decisions, positions, lookback_minutes=(0, 2))

    assert result.direction_recall_by_lookback_pct == {"0m": 0.0, "2m": 100.0}
    assert result.range_only_entries_by_lookback == {"0m": 1, "2m": 0}


def test_zero_minute_window_does_not_use_still_open_candle() -> None:
    decisions = _decisions()
    positions = pd.DataFrame(
        {
            "open_time_utc": [decisions.index[2] + pd.Timedelta(seconds=30)],
            "side": ["short"],
            "symbol": ["BTC"],
        }
    )

    result = evaluate_entry_alignment(decisions, positions, lookback_minutes=(0,))

    assert result.direction_recall_by_lookback_pct == {"0m": 0.0}


def test_zero_minute_window_uses_candle_at_its_close_time() -> None:
    decisions = _decisions()
    positions = pd.DataFrame(
        {
            "open_time_utc": [decisions.index[2] + pd.Timedelta(minutes=1)],
            "side": ["short"],
            "symbol": ["BTC"],
        }
    )

    result = evaluate_entry_alignment(decisions, positions, lookback_minutes=(0,))

    assert result.direction_recall_by_lookback_pct == {"0m": 100.0}


def test_alignment_normalizes_microsecond_fill_against_millisecond_bars() -> None:
    decisions = _decisions()
    decisions.index = decisions.index.as_unit("ms")
    fill = pd.Timestamp("2026-01-01T00:03:00.123456Z")
    positions = pd.DataFrame(
        {"open_time_utc": [fill], "side": ["short"], "symbol": ["BTC"]}
    )

    result = evaluate_entry_alignment(decisions, positions, lookback_minutes=(0,))

    assert result.direction_recall_by_lookback_pct == {"0m": 100.0}


def test_breakout_quality_reports_target_misses() -> None:
    decisions = _decisions()
    decisions["primary_regime"] = "RANGE"
    decisions["breakout_direction"] = None
    decisions.loc[decisions.index[1], ["primary_regime", "breakout_direction"]] = [
        "BREAKOUT",
        "BK_UPWARD",
    ]
    decisions.loc[decisions.index[3], ["primary_regime", "breakout_direction"]] = [
        "BREAKOUT",
        "BK_DOWNWARD",
    ]
    close = np.full(6, 100.0)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": [100.0, 100.0, 100.25, 100.0, 100.05, 100.05],
            "low": [100.0, 100.0, 99.95, 100.0, 99.95, 99.95],
            "close": close,
            "volume": 100.0,
        },
        index=decisions.index,
    )

    result = evaluate_breakout_quality(
        bars,
        decisions,
        target_price_fraction=0.002,
        forward_horizon=2,
    )

    assert result.breakout_events == 2
    assert result.false_breakouts == 1
    assert result.false_breakout_pct == 50.0


def test_breakout_quality_counts_consecutive_labels_as_one_episode() -> None:
    decisions = _decisions()
    decisions["primary_regime"] = "RANGE"
    decisions["breakout_direction"] = None
    decisions.loc[decisions.index[1:3], "primary_regime"] = "BREAKOUT"
    decisions.loc[decisions.index[1:3], "breakout_direction"] = "BK_UPWARD"
    close = np.full(6, 100.0)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": [100.0, 100.0, 100.0, 100.3, 100.0, 100.0],
            "low": close,
            "close": close,
            "volume": 100.0,
        },
        index=decisions.index,
    )

    result = evaluate_breakout_quality(
        bars,
        decisions,
        target_price_fraction=0.002,
        forward_horizon=2,
    )

    assert result.breakout_bars == 2
    assert result.breakout_events == 1
    assert result.false_breakouts == 0


def test_breakout_quality_ignores_awaiting_direction_confirmation() -> None:
    decisions = _decisions()
    decisions["primary_regime"] = "BREAKOUT"
    decisions["breakout_direction"] = None
    close = np.full(len(decisions), 100.0)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 100.0,
        },
        index=decisions.index,
    )

    result = evaluate_breakout_quality(
        bars,
        decisions,
        target_price_fraction=0.002,
        forward_horizon=2,
    )

    assert result.breakout_bars == 0
    assert result.breakout_events == 0
    assert result.false_breakouts == 0
    assert result.false_breakout_pct == 0.0


def test_range_quality_separates_directional_oscillating_and_quiet_outcomes() -> None:
    index = pd.date_range("2026-01-01", periods=8, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "primary_regime": [
                "RANGE",
                "TREND_UP",
                "RANGE",
                "TREND_UP",
                "RANGE",
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
            ]
        },
        index=index,
    )
    close = np.full(8, 100.0)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": [100.0, 100.3, 100.0, 100.3, 100.0, 100.1, 100.0, 100.0],
            "low": [100.0, 99.95, 100.0, 99.7, 100.0, 99.9, 100.0, 100.0],
            "close": close,
            "volume": 100.0,
        },
        index=index,
    )

    result = evaluate_range_quality(
        bars,
        decisions,
        target_price_fraction=0.002,
        forward_horizon=1,
    )

    assert result.range_events == 3
    assert result.one_sided_expansions == 1
    assert result.two_sided_oscillations == 1
    assert result.quiet_ranges == 1
    assert result.one_sided_expansion_pct == 100.0 / 3.0


def test_full_report_records_source_limitations() -> None:
    n = 240
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close = np.linspace(100.0, 110.0, n)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
            "source": "binance",
        },
        index=index,
    )
    positions = pd.DataFrame(
        {
            "open_time_utc": [index[-1] + pd.Timedelta(minutes=1)],
            "side": ["long"],
            "symbol": ["BTC"],
        }
    )

    result = evaluate_hypervelocity_regimes(bars, positions)

    assert result.total_bars == n
    assert result.bar_sources == ("binance",)
    assert result.source_limited is True
    assert sum(result.state_distribution.values()) == n
    assert result.label_churn >= 0
    assert result.mean_transition_latency_bars >= 0.0
    assert set(result.context_direction_recall_pct) == {
        "canonical_5m_primary",
        "hard_5m",
        "hard_15m",
        "hard_30m",
    }
    assert result.position_regime_performance["status"] == "unavailable"
    assert result.cost_sensitivity["status"] == "unavailable"

    unknown_source = evaluate_hypervelocity_regimes(
        bars.drop(columns="source"),
        positions,
    )
    assert unknown_source.bar_sources == ()
    assert unknown_source.source_limited is True


def test_report_slices_realized_positions_and_execution_cost_scenarios() -> None:
    n = 240
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close = np.linspace(100.0, 110.0, n)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
            "source": "hl",
        },
        index=index,
    )
    positions = pd.DataFrame(
        {
            "open_time_utc": [index[-1] + pd.Timedelta(minutes=1)],
            "side": ["long"],
            "symbol": ["BTC"],
            "net_margin_pnl_pct": [8.0],
            "fees_usd": [3.0],
            "approx_margin_usd": [1_000.0],
            "leverage": [40.0],
        }
    )

    result = evaluate_hypervelocity_regimes(bars, positions)

    performance = result.position_regime_performance
    assert performance["status"] == "completed"
    states = performance["states"]
    assert isinstance(states, dict)
    assert sum(state["positions"] for state in states.values()) == 1
    scenarios = result.cost_sensitivity["scenarios"]
    assert scenarios["maker_1_5bps_per_side"][
        "mean_net_margin_pnl_pct"
    ] == pytest.approx(7.1)
    assert scenarios["taker_4_5bps_per_side"][
        "mean_net_margin_pnl_pct"
    ] == pytest.approx(4.7)


def test_report_slices_exclude_superseded_peak_record() -> None:
    n = 240
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close = np.linspace(100.0, 110.0, n)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
            "source": "hl",
        },
        index=index,
    )
    positions = pd.DataFrame(
        {
            "record_source": ["position_peak_only", "trade_only"],
            "open_time_utc": [index[-3], index[-2]],
            "close_time_utc": [index[-1], index[-1]],
            "side": ["long", "long"],
            "symbol": ["BTC", "BTC"],
            "entry_price": [109.0, 109.0],
            "quantity": [0.01, 0.01],
            "net_margin_pnl_pct": [float("nan"), 8.0],
            "fees_usd": [float("nan"), 3.0],
            "approx_margin_usd": [float("nan"), 1_000.0],
            "leverage": [40.0, 40.0],
        }
    )

    result = evaluate_hypervelocity_regimes(bars, positions)

    states = result.position_regime_performance["states"]
    assert sum(state["positions"] for state in states.values()) == 1
    maker = result.cost_sensitivity["scenarios"]["maker_1_5bps_per_side"]
    assert maker["win_rate_pct"] == 100.0


def test_default_evaluation_uses_deployed_faithful_profile() -> None:
    n = 240
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close = np.linspace(100.0, 110.0, n)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
            "source": "hl",
        },
        index=index,
    )
    positions = pd.DataFrame(
        {
            "open_time_utc": [index[-1] + pd.Timedelta(minutes=1)],
            "side": ["long"],
            "symbol": ["BTC"],
        }
    )

    implicit = evaluate_hypervelocity_regimes(bars, positions)
    explicit = evaluate_hypervelocity_regimes(
        bars,
        positions,
        config=faithful_regime_config(),
    )

    assert implicit == explicit


def test_hard_30m_state_is_available_after_last_constituent_bar() -> None:
    n = 1800
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close = np.linspace(100.0, 130.0, n)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
        },
        index=index,
    )

    state = _hard_30m_state(bars)

    assert state.iloc[-2] == "UNKNOWN"
    assert state.iloc[-1] == "TREND_UP"
