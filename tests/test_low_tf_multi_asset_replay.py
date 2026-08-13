"""One-minute-path replay tests for one frozen low-timeframe variant."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.low_tf_multi_asset_replay import evaluate_low_tf_replay
from hypervector.research.low_tf_multi_asset_replay_models import LowTfReplayConfig


def _minutes(rows: int = 20) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-01-01", periods=rows, freq="1min", tz="UTC"
            ),
            "open": [100.0] * rows,
            "high": [100.2] * rows,
            "low": [99.8] * rows,
            "close": [100.0] * rows,
            "volume": [10.0] * rows,
            "funding_rate": [0.0] * rows,
        }
    )


def _features(rows: int = 4) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=rows, freq="5min", tz="UTC"
            ),
            "close": [100.0] * rows,
            "ema_fast_5m": [101.0] * rows,
            "ema_slow_5m": [100.0] * rows,
            "rsi": [55.0] * rows,
            "rsi_signal": [50.0] * rows,
            "rsi_bearish_divergence": [False] * rows,
            "rsi_bullish_divergence": [False] * rows,
            "pmarp": [50.0] * rows,
        }
    )


def _signal(
    *,
    side: str = "long",
    variant: str = "range_wick_atr_stop",
    stop: float = 99.0,
    target: float = 101.0,
    max_hold: int = 4,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "decision_time_utc": "2026-01-01T00:05:00+00:00",
                "decision_position": 0,
                "symbol": "BTC",
                "family": "range_reclaim_v1",
                "side": side,
                "exit_variant": variant,
                "trigger_price": 100.0,
                "stop_anchor_price": stop,
                "target_anchor_price": target,
                "invalidation_mode": (
                    "completed_bar_close"
                    if variant == "range_close_invalidation"
                    else "intrabar_stop"
                ),
                "max_hold_bars": max_hold,
                "execution_authority": "none",
            }
        ]
    )


def test_next_five_minute_open_entry_and_target_use_adverse_slippage() -> None:
    minutes = _minutes()
    minutes.loc[6, "high"] = 102.0

    report = evaluate_low_tf_replay(minutes, _features(), _signal())
    trade = report.trades[0]

    assert trade.entry_time_utc == "2026-01-01T00:05:00+00:00"
    assert trade.exit_time_utc == "2026-01-01T00:06:00+00:00"
    assert trade.entry_price == pytest.approx(100.02)
    assert trade.exit_price == pytest.approx(101.0 * (1.0 - 0.0002))
    assert trade.exit_reason == "target"
    assert report.completed_trades == 1


def test_same_minute_stop_and_target_resolves_adversely_and_is_counted() -> None:
    minutes = _minutes()
    minutes.loc[6, ["high", "low"]] = [102.0, 98.0]

    report = evaluate_low_tf_replay(minutes, _features(), _signal())
    trade = report.trades[0]

    assert trade.exit_reason == "stop"
    assert trade.same_minute_ambiguous is True
    assert report.same_minute_ambiguities == 1


def test_close_invalidation_waits_for_completed_bar_and_next_open() -> None:
    minutes = _minutes()
    minutes.loc[6, "low"] = 97.0
    minutes.loc[10, "open"] = 98.0
    features = _features()
    features.loc[1, "close"] = 98.5
    signal = _signal(variant="range_close_invalidation", target=105.0)

    report = evaluate_low_tf_replay(minutes, features, signal)

    assert report.trades[0].exit_reason == "close_invalidation"
    assert report.trades[0].exit_time_utc == "2026-01-01T00:10:00+00:00"


def test_rsi_reversal_is_close_known_and_executes_at_next_open() -> None:
    minutes = _minutes()
    features = _features()
    features.loc[1, ["rsi", "rsi_signal"]] = [45.0, 50.0]
    signal = _signal(variant="rsi_reversal_exit", target=float("nan"))
    signal["family"] = "trend_expansion_v1"

    report = evaluate_low_tf_replay(minutes, features, signal)

    assert report.trades[0].exit_reason == "rsi_reversal"
    assert report.trades[0].exit_time_utc == "2026-01-01T00:10:00+00:00"


def test_rsi_exit_requires_a_fresh_completed_cross() -> None:
    features = _features()
    features.loc[0, ["rsi", "rsi_signal"]] = [45.0, 50.0]
    features.loc[1, ["rsi", "rsi_signal"]] = [44.0, 49.0]
    signal = _signal(variant="rsi_reversal_exit", target=float("nan"), max_hold=2)
    signal["family"] = "trend_expansion_v1"

    report = evaluate_low_tf_replay(_minutes(), features, signal)

    assert report.trades[0].exit_reason == "max_hold"
    assert report.trades[0].exit_time_utc == "2026-01-01T00:15:00+00:00"


def test_krown_pullback_exits_on_completed_pmarp_80_state() -> None:
    features = _features()
    features.loc[1, "pmarp"] = 85.0
    signal = _signal(variant="krown_hard_stop_pmarp80", target=float("nan"), max_hold=4)
    signal["family"] = "krown_pullback_long_v1"

    report = evaluate_low_tf_replay(_minutes(), features, signal)

    assert report.trades[0].exit_reason == "pmarp_opposite_extreme"
    assert report.trades[0].exit_time_utc == "2026-01-01T00:10:00+00:00"


def test_krown_close_stop_preserves_completed_close_invalidation() -> None:
    features = _features()
    features.loc[1, "close"] = 98.0
    signal = _signal(
        variant="krown_close_stop_pmarp80", target=float("nan"), max_hold=4
    )
    signal["family"] = "krown_pullback_long_v1"
    signal["invalidation_mode"] = "completed_bar_close"

    report = evaluate_low_tf_replay(_minutes(), features, signal)

    assert report.trades[0].exit_reason == "close_invalidation"
    assert report.trades[0].exit_time_utc == "2026-01-01T00:10:00+00:00"


@pytest.mark.parametrize(
    ("side", "event_column"),
    [
        ("long", "rsi_bearish_divergence"),
        ("short", "rsi_bullish_divergence"),
    ],
)
def test_krown_touch_exits_on_confirmed_opposing_rsi_divergence(
    side: str, event_column: str
) -> None:
    features = _features()
    features.loc[1, event_column] = True
    stop = 99.0 if side == "long" else 101.0
    signal = _signal(
        side=side,
        variant="krown_touch_hard_stop_rsi_div",
        stop=stop,
        target=float("nan"),
        max_hold=4,
    )
    signal["family"] = "krown_ema55_touch_v1"

    report = evaluate_low_tf_replay(_minutes(), features, signal)

    assert report.trades[0].exit_reason == "rsi_divergence"
    assert report.trades[0].exit_time_utc == "2026-01-01T00:10:00+00:00"


def test_krown_touch_close_stop_uses_completed_bar_and_next_open() -> None:
    features = _features()
    features.loc[1, "close"] = 98.0
    signal = _signal(
        variant="krown_touch_close_stop_rsi_div",
        target=float("nan"),
        max_hold=4,
    )
    signal["family"] = "krown_ema55_touch_v1"
    signal["invalidation_mode"] = "completed_bar_close"

    report = evaluate_low_tf_replay(_minutes(), features, signal)

    assert report.trades[0].exit_reason == "close_invalidation"
    assert report.trades[0].exit_time_utc == "2026-01-01T00:10:00+00:00"


def test_hourly_funding_is_signed_and_reconciled() -> None:
    minutes = _minutes()
    minutes.loc[6, "funding_rate"] = 0.001
    minutes.loc[8, "high"] = 102.0

    report = evaluate_low_tf_replay(minutes, _features(), _signal())
    trade = report.trades[0]

    assert trade.funding_cashflow_usd < 0.0
    assert report.funding_cashflow_usd == pytest.approx(trade.funding_cashflow_usd)
    assert report.final_equity == pytest.approx(
        report.initial_equity
        + report.gross_pnl_usd
        - report.total_fees_usd
        + report.funding_cashflow_usd
        - report.liquidation_penalties_usd
    )


def test_liquidation_is_evaluated_before_a_deeper_stop() -> None:
    minutes = _minutes()
    minutes.loc[6, "low"] = 98.0
    config = LowTfReplayConfig(
        leverage=40.0,
        venue_max_leverage=40.0,
        risk_fraction=0.001,
    )

    report = evaluate_low_tf_replay(
        minutes, _features(), _signal(stop=90.0, target=110.0), config
    )

    assert report.trades[0].exit_reason == "liquidation"
    assert report.liquidations == 1
    assert report.trades[0].liquidation_penalty_usd > 0.0


def test_maximum_hold_closes_at_the_deadline_open() -> None:
    report = evaluate_low_tf_replay(
        _minutes(), _features(), _signal(target=110.0, max_hold=1)
    )

    assert report.trades[0].exit_reason == "max_hold"
    assert report.trades[0].exit_time_utc == "2026-01-01T00:10:00+00:00"


def test_round_trip_cost_contract_is_not_double_counted() -> None:
    config = LowTfReplayConfig(round_trip_cost_bps=13.0, fee_round_trip_bps=9.0)

    assert config.fee_rate_per_side == pytest.approx(0.00045)
    assert config.slippage_bps_per_side == pytest.approx(2.0)


def test_position_open_signals_are_reported_as_rejections() -> None:
    signals = pd.concat(
        [
            _signal(target=110.0),
            _signal(target=110.0).assign(
                decision_time_utc="2026-01-01T00:10:00+00:00",
                decision_position=1,
            ),
        ],
        ignore_index=True,
    )

    report = evaluate_low_tf_replay(_minutes(), _features(), signals)

    assert any(
        rejection.reason == "symbol_position_open" for rejection in report.rejections
    )


def test_close_stop_quantity_is_capped_instead_of_rejecting_tight_risk() -> None:
    signal = _signal(stop=99.99, target=110.0)

    report = evaluate_low_tf_replay(_minutes(), _features(), signal)
    trade = report.trades[0]

    assert report.completed_trades == 1
    assert not any(
        rejection.reason == "maximum_isolated_margin_exceeded"
        for rejection in report.rejections
    )
    assert trade.isolated_margin_usd <= report.initial_equity * 0.70 + 1e-6
    assert trade.risk_budget_usd < report.initial_equity * 0.005


def test_replay_rejects_mixed_variant_input() -> None:
    signals = pd.concat(
        [_signal(), _signal(variant="range_close_invalidation")],
        ignore_index=True,
    )

    with pytest.raises(ValueError, match="exactly one strategy cell"):
        evaluate_low_tf_replay(_minutes(), _features(), signals)
