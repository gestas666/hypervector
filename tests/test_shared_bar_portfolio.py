"""Causal shared-portfolio screening tests for strategy challengers."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.cohort_profit_lock_policy import ProfitLockPolicy
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.mu_hip3_archive_reporting import report_summary
from hypervector.research.shared_portfolio_completed_peak_lock import (
    CompletedBarPeakLockPolicy,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig


def _bars(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float] | None = None,
    funding: list[float] | None = None,
) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(opens), freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes or opens,
            "funding_rate": funding or [0.0] * len(opens),
        },
        index=index,
    )


def _signals(
    bars: pd.DataFrame,
    entries: list[str | None],
    exits: list[bool] | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "entry_direction": entries,
            "exit_signal": exits or [False] * len(bars),
            "signal_name": ["test"] * len(bars),
        },
        index=bars.index,
    )


def _zero_friction_config(**overrides: object) -> SharedPortfolioConfig:
    values: dict[str, object] = {
        "initial_equity": 15_000.0,
        "margin_fraction": 0.10,
        "leverage": 10.0,
        "target_margin_pct": 10.0,
        "stop_margin_pct": 5.0,
        "entry_fee_rate": 0.0,
        "target_fee_rate": 0.0,
        "market_exit_fee_rate": 0.0,
        "liquidation_fee_rate": 0.0,
        "entry_slippage_bps": 0.0,
        "market_exit_slippage_bps": 0.0,
    }
    values.update(overrides)
    return SharedPortfolioConfig(**values)


def test_completed_bar_profit_lock_closes_at_next_executable_open() -> None:
    """A prior active lock may trigger on a completed bar, then exit causally."""
    bars = _bars(
        [100.0, 100.0, 99.0, 99.6, 99.6],
        [100.0, 100.0, 99.5, 99.7, 99.6],
        [100.0, 99.0, 98.8, 99.5, 99.6],
    )
    policy = ProfitLockPolicy("test_60_20_30", 60.0, 20.0, 30.0)

    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["short", None, None, None, None]),
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=10.0,
            completed_bar_profit_lock=policy,
        ),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "profit_lock"
    assert trade.exit_position == 3
    assert trade.exit_price == pytest.approx(99.6)


def test_completed_bar_profit_lock_cannot_activate_and_trigger_same_bar() -> None:
    """The activation bar cannot use its own later path to claim a lock exit."""
    bars = _bars(
        [100.0, 100.0, 99.1, 99.1],
        [100.0, 100.0, 99.1, 99.1],
        [100.0, 99.0, 99.0, 99.1],
    )
    policy = ProfitLockPolicy("test_60_20_30", 60.0, 20.0, 30.0)

    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["short", None, None, None]),
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=10.0,
            completed_bar_profit_lock=policy,
        ),
    )

    assert report.trades[0].exit_reason == "end_of_data"


def test_completed_close_peak_lock_exits_at_next_open() -> None:
    """A prior gate-close peak may trigger only after a later completed close."""
    bars = _bars(
        [100.0, 100.0, 100.5, 100.4],
        [100.0, 100.5, 100.5, 100.4],
        [100.0, 100.0, 100.4, 100.4],
        [100.0, 100.5, 100.4, 100.4],
    )
    policy = CompletedBarPeakLockPolicy("gate_2pct_lock85", 2.0, 0.85)

    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", None, None, None]),
        _zero_friction_config(
            leverage=5.0,
            target_margin_pct=None,
            stop_margin_pct=None,
            completed_bar_peak_lock=policy,
        ),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "profit_lock"
    assert trade.exit_position == 3
    assert trade.exit_price == pytest.approx(100.4)


def test_completed_close_peak_lock_ignores_intrabar_wicks() -> None:
    """An unclosed wick cannot activate the gate-basis ratchet."""
    bars = _bars(
        [100.0, 100.0, 100.0, 99.9],
        [100.0, 110.0, 100.0, 99.9],
        [100.0, 100.0, 99.9, 99.9],
        [100.0, 100.0, 99.9, 99.9],
    )

    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", None, None, None]),
        _zero_friction_config(
            leverage=5.0,
            target_margin_pct=None,
            stop_margin_pct=None,
            completed_bar_peak_lock=CompletedBarPeakLockPolicy(
                "gate_2pct_lock85",
                2.0,
                0.85,
            ),
        ),
    )

    assert report.trades[0].exit_reason == "end_of_data"


def test_entry_is_causal_and_uses_only_one_shared_equity_pool() -> None:
    bars = _bars(
        [100.0, 101.0, 102.0, 103.0],
        [100.0, 102.1, 102.0, 103.0],
        [100.0, 101.0, 102.0, 103.0],
    )
    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", "short", None, None]),
        _zero_friction_config(close_on_opposite_signal=False),
    )

    assert report.completed_trades == 1
    assert report.maximum_concurrent_positions == 1
    assert report.trades[0].signal_position == 0
    assert report.trades[0].entry_position == 1
    assert report.trades[0].entry_price == pytest.approx(101.0)
    assert report.trades[0].exit_reason == "target"
    assert report.final_equity == pytest.approx(15_150.0)


def test_optional_notional_cap_limits_margin_without_changing_leverage() -> None:
    """A venue/profile cap must bind before quantity and entry fees are derived."""
    bars = _bars(
        [100.0, 100.0, 100.0],
        [100.0, 101.1, 100.0],
        [100.0, 100.0, 100.0],
    )
    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", None, None]),
        _zero_friction_config(maximum_notional_usd=5_000.0),
    )

    trade = report.trades[0]
    assert trade.notional_usd == pytest.approx(5_000.0)
    assert trade.margin_usd == pytest.approx(500.0)
    assert trade.leverage == pytest.approx(10.0)


def test_same_bar_stop_and_target_uses_conservative_stop_first() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0],
        [100.0, 101.1, 100.0],
        [100.0, 99.4, 100.0],
    )
    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", None, None]),
        _zero_friction_config(),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.same_bar_ambiguous is True
    assert trade.net_pnl_usd == pytest.approx(-75.0)
    assert report.maximum_drawdown_pct <= -0.5


def test_risk_barriers_can_use_venue_mark_path_separate_from_signal_ohlc() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0],
    )
    bars["mark_high"] = [100.0, 100.0, 100.0]
    bars["mark_low"] = [100.0, 99.4, 100.0]

    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", None, None]),
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=5.0,
            risk_high_column="mark_high",
            risk_low_column="mark_low",
        ),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.net_pnl_usd == pytest.approx(-75.0)


@pytest.mark.parametrize(
    ("entry_risk_low", "expected_reason"),
    [(100.0, "end_of_data"), (80.0, "liquidation")],
)
def test_entry_bar_risk_uses_only_post_fill_mark_extrema(
    entry_risk_low: float,
    expected_reason: str,
) -> None:
    bars = _bars(
        [100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0],
    )
    bars["mark_high"] = 100.0
    bars["mark_low"] = [100.0, 1.0, 100.0]
    bars["entry_mark_high"] = 100.0
    bars["entry_mark_low"] = [100.0, entry_risk_low, 100.0]

    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", None, None]),
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=None,
            risk_high_column="mark_high",
            risk_low_column="mark_low",
            entry_risk_high_column="entry_mark_high",
            entry_risk_low_column="entry_mark_low",
        ),
    )

    assert report.trades[0].exit_reason == expected_reason


@pytest.mark.parametrize(
    ("direction", "gap_open", "gap_high", "gap_low"),
    [
        ("long", 99.0, 99.2, 98.8),
        ("short", 101.0, 101.2, 100.8),
    ],
)
def test_stop_market_fills_at_adverse_open_after_a_gap(
    direction: str,
    gap_open: float,
    gap_high: float,
    gap_low: float,
) -> None:
    """A stop-market fill must not claim a better price than the next open."""
    bars = _bars(
        [100.0, 100.0, gap_open, gap_open],
        [100.0, 100.0, gap_high, gap_high],
        [100.0, 100.0, gap_low, gap_low],
    )
    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, [direction, None, None, None]),
        _zero_friction_config(target_margin_pct=None),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.exit_price == pytest.approx(gap_open)


@pytest.mark.parametrize(
    ("direction", "entry", "high", "low", "signal_stop", "expected_stop"),
    [
        ("long", 101.0, 101.1, 100.0, 98.8, 101.0 * 0.992),
        ("short", 99.0, 100.0, 98.9, 101.2, 99.0 * 1.008),
    ],
)
def test_fill_time_stop_ceiling_clamps_structural_stop_after_adverse_gap(
    direction: str,
    entry: float,
    high: float,
    low: float,
    signal_stop: float,
    expected_stop: float,
) -> None:
    """A close-anchored structural stop cannot exceed its fill-time ceiling."""
    bars = _bars(
        [100.0, entry, entry],
        [100.0, high, entry],
        [100.0, low, entry],
    )
    signals = _signals(bars, [direction, None, None])
    signals["stop_price"] = [signal_stop, None, None]

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(
            target_margin_pct=None,
            maximum_stop_distance_bps=80.0,
        ),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.stop_price == pytest.approx(expected_stop)


@pytest.mark.parametrize(
    (
        "direction",
        "signal_stop",
        "exit_high",
        "exit_low",
        "expected_stop",
        "expected_target",
    ),
    [
        ("long", 99.9, 100.7, 100.0, 99.8, 100.6),
        ("short", 100.1, 100.0, 99.3, 100.2, 99.4),
    ],
)
def test_fill_time_stop_band_derives_reward_risk_target(
    direction: str,
    signal_stop: float,
    exit_high: float,
    exit_low: float,
    expected_stop: float,
    expected_target: float,
) -> None:
    """The live-compatible stop band must set an exact fill-time R target."""
    bars = _bars(
        [100.0, 100.0, 100.0],
        [100.0, 100.0, exit_high],
        [100.0, 100.0, exit_low],
    )
    signals = _signals(bars, [direction, None, None])
    signals["stop_price"] = [signal_stop, None, None]

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=None,
            minimum_stop_distance_bps=20.0,
            maximum_stop_distance_bps=75.0,
            target_r_multiple=3.0,
        ),
    )

    trade = report.trades[0]
    assert trade.stop_price == pytest.approx(expected_stop)
    assert trade.target_price == pytest.approx(expected_target)
    assert trade.exit_reason == "target"


def test_reward_risk_contract_rejects_ambiguous_or_inverted_bounds() -> None:
    """Malformed exit contracts must fail before the simulator runs."""
    with pytest.raises(ValueError, match="target_margin_pct"):
        _zero_friction_config(target_margin_pct=10.0, target_r_multiple=3.0)
    with pytest.raises(ValueError, match="minimum_stop_distance_bps"):
        _zero_friction_config(
            minimum_stop_distance_bps=80.0,
            maximum_stop_distance_bps=75.0,
        )


@pytest.mark.parametrize(
    ("direction", "signal_stop"),
    [("long", 98.0), ("short", 102.0)],
)
def test_native_stop_sizes_notional_from_fixed_equity_risk(
    direction: str,
    signal_stop: float,
) -> None:
    """Native stop distance, not leverage, must determine bankroll risk."""
    bars = _bars(
        [100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0],
    )
    signals = _signals(bars, [direction, None, None])
    signals["stop_price"] = [signal_stop, None, None]

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=None,
            risk_fraction_per_position=0.0075,
        ),
    )

    trade = report.trades[0]
    assert trade.notional_usd == pytest.approx(5_625.0)
    assert trade.margin_usd == pytest.approx(562.5)
    assert trade.notional_usd * 0.02 == pytest.approx(112.5)


def test_fixed_risk_sizing_still_obeys_margin_and_notional_caps() -> None:
    """A tight native stop cannot enlarge exposure beyond operational caps."""
    bars = _bars([100.0] * 3, [100.0] * 3, [100.0] * 3)
    signals = _signals(bars, ["long", None, None])
    signals["stop_price"] = [99.9, None, None]

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=None,
            risk_fraction_per_position=0.0075,
            maximum_notional_usd=5_000.0,
        ),
    )

    assert report.trades[0].notional_usd == pytest.approx(5_000.0)


def test_fixed_risk_sizing_requires_a_resolved_adverse_stop() -> None:
    """Risk sizing must fail closed when no price risk can be measured."""
    bars = _bars([100.0] * 3, [100.0] * 3, [100.0] * 3)

    with pytest.raises(ValueError, match="risk_fraction_per_position"):
        evaluate_shared_bar_portfolio(
            bars,
            _signals(bars, ["long", None, None]),
            _zero_friction_config(
                target_margin_pct=None,
                stop_margin_pct=None,
                risk_fraction_per_position=0.0075,
            ),
        )


def test_wall_clock_max_hold_exits_at_first_quote_after_archive_gap() -> None:
    before_gap = pd.date_range("2026-01-01", periods=81, freq="15min", tz="UTC")
    after_gap = pd.date_range("2026-01-02T04:00:00Z", periods=3, freq="15min")
    index = before_gap.append(after_gap)
    bars = _bars(
        [100.0] * len(index),
        [100.0] * len(index),
        [100.0] * len(index),
    )
    bars.index = index
    signals = _signals(bars, ["long", *([None] * (len(bars) - 1))])

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=None,
            max_hold_bars=96,
            max_hold_seconds=86_400,
        ),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "max_hold"
    assert trade.exit_time_utc == index[81].isoformat()
    elapsed = pd.Timestamp(trade.exit_time_utc) - pd.Timestamp(trade.entry_time_utc)
    assert elapsed > pd.Timedelta(hours=24)
    summary = report_summary(report, index[0], index[-1] + pd.Timedelta(minutes=15))
    assert summary["maximum_hold_gap_censored_exits"] == 1
    assert summary["maximum_hold_lateness_seconds_max"] == pytest.approx(13_500.0)


def test_entry_and_wall_clock_hold_use_first_executable_quote_time() -> None:
    index = pd.date_range("2026-01-01", periods=99, freq="15min", tz="UTC")
    bars = _bars([100.0] * 99, [100.0] * 99, [100.0] * 99)
    bars.index = index
    bars["first_boundary_delay_ms"] = [0, 10_000, *([5_000] * 97)]
    signals = _signals(bars, ["long", *([None] * 98)])

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=None,
            max_hold_seconds=86_400,
        ),
    )

    trade = report.trades[0]
    assert trade.entry_time_utc == "2026-01-01T00:15:10+00:00"
    assert trade.exit_time_utc == "2026-01-02T00:30:05+00:00"


def test_pending_entry_expires_causally_when_next_observation_has_gap() -> None:
    bars = _bars(
        [100.0, 100.0, 101.0, 101.0],
        [100.0, 100.0, 101.0, 101.0],
        [100.0, 100.0, 101.0, 101.0],
    )
    bars["gap_before_bars"] = [0, 0, 4, 0]
    signals = _signals(bars, [None, "long", None, None])

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(target_margin_pct=None, stop_margin_pct=None),
    )

    assert report.completed_trades == 0
    assert report.gap_expired_entries == 1


def test_open_position_is_gap_censored_at_first_recovery_quote() -> None:
    bars = _bars(
        [100.0, 100.0, 97.0, 97.0],
        [100.0, 100.0, 97.0, 97.0],
        [100.0, 100.0, 97.0, 97.0],
    )
    bars.index = pd.DatetimeIndex(
        [
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:15:00Z",
            "2026-01-01T04:15:00Z",
            "2026-01-01T04:30:00Z",
        ]
    )
    bars["gap_before_bars"] = [0, 0, 15, 0]
    signals = _signals(bars, ["long", None, None, None])

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(target_margin_pct=None, stop_margin_pct=None),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "data_gap"
    assert trade.exit_time_utc == bars.index[2].isoformat()


def test_gap_recovery_funding_settles_before_position_is_censored() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0, 100.0],
        funding=[0.0, 0.0, 0.004, 0.0],
    )
    bars["gap_before_bars"] = [0, 0, 15, 0]

    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", None, None, None]),
        _zero_friction_config(target_margin_pct=None, stop_margin_pct=None),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "data_gap"
    assert trade.funding_cashflow_usd == pytest.approx(-60.0)


def test_new_next_open_entry_does_not_pay_prior_boundary_funding() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0],
        funding=[0.0, 0.004, 0.0],
    )

    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", None, None]),
        _zero_friction_config(target_margin_pct=None, stop_margin_pct=None),
    )

    assert report.trades[0].funding_cashflow_usd == 0.0


def test_liquidation_precedes_other_barriers_and_retains_unallocated_cash() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0],
        [100.0, 102.0, 100.0],
        [100.0, 90.0, 100.0],
    )
    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", None, None]),
        _zero_friction_config(
            leverage=40.0,
            target_margin_pct=8.0,
            stop_margin_pct=None,
        ),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "liquidation"
    assert report.liquidations == 1
    assert 13_000.0 < report.final_equity < 15_000.0
    assert report.insolvent is False


@pytest.mark.parametrize(
    ("direction", "funding_rate", "expected_sign"),
    [("long", 0.001, -1), ("short", 0.001, 1)],
)
def test_signed_funding_is_applied_once_at_the_observed_boundary(
    direction: str,
    funding_rate: float,
    expected_sign: int,
) -> None:
    bars = _bars(
        [100.0, 100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0, 100.0],
        funding=[0.0, 0.0, funding_rate, 0.0],
    )
    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, [direction, None, None, None]),
        _zero_friction_config(target_margin_pct=None, stop_margin_pct=None),
    )

    assert report.funding_cashflow_usd == pytest.approx(expected_sign * 15.0)
    assert report.trades[0].funding_cashflow_usd == pytest.approx(expected_sign * 15.0)


def test_opposite_signal_closes_then_reverses_at_next_open() -> None:
    bars = _bars(
        [100.0, 100.0, 101.0, 100.0, 99.0],
        [100.0, 100.5, 101.0, 100.0, 99.0],
        [100.0, 100.0, 100.5, 99.0, 98.0],
    )
    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", "short", None, None, None]),
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=None,
            close_on_opposite_signal=True,
            reverse_on_opposite_signal=True,
        ),
    )

    assert [trade.direction for trade in report.trades] == ["long", "short"]
    assert report.trades[0].exit_reason == "opposite_signal"
    assert report.trades[0].exit_position == report.trades[1].entry_position == 2
    assert report.maximum_concurrent_positions == 1


def test_profit_factor_and_monthly_pnl_come_from_one_trade_stream() -> None:
    bars = _bars(
        [100.0] * 7,
        [100.0, 101.1, 100.0, 100.0, 100.0, 100.0, 100.0],
        [100.0, 100.0, 100.0, 100.0, 99.4, 100.0, 100.0],
    )
    signals = _signals(
        bars,
        ["long", None, None, "long", None, None, None],
    )
    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(reentry_cooldown_bars=1),
    )

    assert report.completed_trades == 2
    assert report.gross_profit_usd == pytest.approx(150.0)
    assert report.gross_loss_usd == pytest.approx(75.75)
    assert report.profit_factor == pytest.approx(150.0 / 75.75)
    assert sum(report.monthly_net_pnl_usd.values()) == pytest.approx(report.net_pnl_usd)


def test_same_direction_reentry_waits_for_signal_reset_when_configured() -> None:
    bars = _bars(
        [100.0] * 7,
        [100.0, 101.1, 100.0, 100.0, 100.0, 101.1, 100.0],
        [100.0] * 7,
    )
    signals = _signals(
        bars,
        ["long", "long", "long", None, "long", "long", "long"],
    )

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(same_direction_reentry_requires_reset=True),
    )

    assert report.completed_trades == 2
    assert [trade.signal_position for trade in report.trades] == [0, 4]


def test_invalid_leverage_above_btc_venue_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="venue_max_leverage"):
        SharedPortfolioConfig(leverage=41.0, venue_max_leverage=40.0)


@pytest.mark.parametrize(
    "field",
    [
        "signal_exit_max_age_bars",
        "signal_exit_max_mfe_bps",
        "signal_exit_min_adverse_bps",
    ],
)
def test_invalid_conditional_signal_exit_value_is_rejected(field: str) -> None:
    """Conditional signal-exit thresholds must be positive when configured."""
    with pytest.raises(ValueError, match=field):
        SharedPortfolioConfig(**{field: 0})


def test_side_specific_exit_does_not_close_the_opposite_position() -> None:
    bars = _bars(
        [100.0, 100.0, 101.0, 102.0],
        [100.0, 100.5, 101.0, 102.0],
        [100.0, 100.0, 100.0, 101.0],
    )
    signals = pd.DataFrame(
        {
            "long_entry": [True, False, False, False],
            "short_entry": [False] * 4,
            "long_exit": [False, False, True, False],
            "short_exit": [False, True, False, False],
            "long_signal_name": ["long-test"] * 4,
            "short_signal_name": ["short-test"] * 4,
        },
        index=bars.index,
    )

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(target_margin_pct=None, stop_margin_pct=None),
    )

    assert report.trades[0].signal_name == "long-test"
    assert report.trades[0].exit_reason == "signal"
    assert report.trades[0].exit_position == 3


def test_conditional_signal_exit_honors_early_adverse_failed_onset() -> None:
    """A close-known early loser below the MFE ceiling exits at the next open."""
    bars = _bars(
        [100.0] * 5,
        [100.0, 100.1, 100.1, 100.0, 100.0],
        [100.0, 99.7, 99.7, 100.0, 100.0],
        [100.0, 99.8, 99.8, 100.0, 100.0],
    )
    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(
            bars,
            ["long", None, None, None, None],
            [False, False, True, False, False],
        ),
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=None,
            signal_exit_max_age_bars=8,
            signal_exit_max_mfe_bps=20.0,
            signal_exit_min_adverse_bps=13.0,
        ),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "signal"
    assert trade.entry_position == 1
    assert trade.exit_position == 3


@pytest.mark.parametrize(
    ("highs", "closes", "exit_position", "overrides"),
    [
        (
            [100.0, 100.3, 100.1, 100.0, 100.0],
            [100.0, 99.8, 99.8, 100.0, 100.0],
            2,
            {},
        ),
        (
            [100.0, 100.1, 100.1, 100.0, 100.0],
            [100.0, 99.95, 99.95, 100.0, 100.0],
            2,
            {},
        ),
        (
            [100.0, 100.1, 100.1, 100.1, 100.0],
            [100.0, 99.8, 99.8, 99.8, 100.0],
            3,
            {"signal_exit_max_age_bars": 1},
        ),
    ],
)
def test_conditional_signal_exit_rejects_nonmatching_path(
    highs: list[float],
    closes: list[float],
    exit_position: int,
    overrides: dict[str, object],
) -> None:
    """MFE, adverse-return, and age conditions must each be authoritative."""
    bars = _bars([100.0] * 5, highs, [99.7] * 5, closes)
    exits = [False] * 5
    exits[exit_position] = True
    config = {
        "target_margin_pct": None,
        "stop_margin_pct": None,
        "signal_exit_max_age_bars": 8,
        "signal_exit_max_mfe_bps": 20.0,
        "signal_exit_min_adverse_bps": 13.0,
        **overrides,
    }

    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", None, None, None, None], exits),
        _zero_friction_config(**config),
    )

    assert report.trades[0].exit_reason == "end_of_data"


def test_insolvent_portfolio_does_not_schedule_another_entry() -> None:
    bars = _bars(
        [100.0] * 5,
        [100.0, 100.0, 100.0, 100.0, 100.0],
        [100.0, 90.0, 100.0, 100.0, 100.0],
    )
    signals = _signals(bars, ["long", None, "long", "long", None])

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(
            margin_fraction=1.0,
            leverage=40.0,
            target_margin_pct=None,
            stop_margin_pct=None,
            liquidation_fee_rate=0.01,
            liquidation_slippage_bps=100.0,
        ),
    )

    assert report.completed_trades == 1
    assert report.liquidations == 1
    assert report.insolvent is True


@pytest.mark.parametrize(
    ("direction", "expected_entry", "expected_exit"),
    [("long", 100.2, 100.1), ("short", 99.8, 100.3)],
)
def test_optional_boundary_quotes_replace_midpoint_execution(
    direction: str,
    expected_entry: float,
    expected_exit: float,
) -> None:
    bars = _bars([100.0] * 4, [101.0] * 4, [99.0] * 4)
    bars["entry_bid"] = [99.8, 99.8, 100.1, 100.1]
    bars["entry_ask"] = [100.2, 100.2, 100.3, 100.3]
    bars["decision_bid"] = [99.9] * 4
    bars["decision_ask"] = [100.1] * 4
    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, [direction, None, None, None], [False, True, False, False]),
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=None,
            open_bid_column="entry_bid",
            open_ask_column="entry_ask",
            close_bid_column="decision_bid",
            close_ask_column="decision_ask",
        ),
    )

    assert report.trades[0].entry_price == pytest.approx(expected_entry)
    assert report.trades[0].exit_price == pytest.approx(expected_exit)


@pytest.mark.parametrize(
    ("direction", "expected_exit"),
    [("long", 101.4), ("short", 101.6)],
)
def test_terminal_exit_uses_last_executable_close_quote(
    direction: str,
    expected_exit: float,
) -> None:
    bars = _bars([100.0] * 3, [102.0] * 3, [98.0] * 3)
    bars["entry_bid"] = [99.8] * 3
    bars["entry_ask"] = [100.2] * 3
    bars["decision_bid"] = [99.9, 100.9, 101.4]
    bars["decision_ask"] = [100.1, 101.1, 101.6]
    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, [direction, None, None]),
        _zero_friction_config(
            target_margin_pct=None,
            stop_margin_pct=None,
            open_bid_column="entry_bid",
            open_ask_column="entry_ask",
            close_bid_column="decision_bid",
            close_ask_column="decision_ask",
        ),
    )

    assert report.trades[0].exit_reason == "end_of_data"
    assert report.trades[0].exit_price == pytest.approx(expected_exit)


def test_terminal_exit_records_close_quote_observation_time() -> None:
    bars = _bars([100.0] * 3, [101.0] * 3, [99.0] * 3)
    bars["first_boundary_delay_ms"] = 200.0
    bars["end_boundary_age_ms"] = 300.0

    report = evaluate_shared_bar_portfolio(
        bars,
        _signals(bars, ["long", None, None]),
        _zero_friction_config(target_margin_pct=None, stop_margin_pct=None),
    )

    trade = report.trades[0]
    expected = bars.index[-1] + pd.Timedelta(minutes=1, milliseconds=-300)
    assert trade.exit_reason == "end_of_data"
    assert pd.Timestamp(trade.exit_time_utc) == expected


def test_configured_crossed_quote_columns_are_rejected() -> None:
    bars = _bars([100.0] * 3, [101.0] * 3, [99.0] * 3)
    bars["entry_bid"] = [100.2] * 3
    bars["entry_ask"] = [100.1] * 3
    signals = _signals(bars, ["long", None, None])

    with pytest.raises(ValueError, match="entry_bid.*entry_ask"):
        evaluate_shared_bar_portfolio(
            bars,
            signals,
            _zero_friction_config(
                open_bid_column="entry_bid",
                open_ask_column="entry_ask",
            ),
        )


def test_next_bar_quote_beyond_signal_stop_invalidates_entry() -> None:
    bars = _bars([100.0, 99.0, 99.0], [100.0, 99.2, 99.0], [100.0, 98.8, 99.0])
    signals = _signals(bars, ["long", None, None])
    signals["stop_price"] = [99.5, None, None]

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _zero_friction_config(target_margin_pct=None, stop_margin_pct=None),
    )

    assert report.completed_trades == 0
    assert report.barrier_invalidated_entries == 1
    assert report.final_equity == report.initial_equity
