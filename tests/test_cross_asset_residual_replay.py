"""Atomic two-leg lifecycle tests for residual replay."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from hypervector.research.cross_asset_residual_models import (
    CrossAssetResidualConfig,
    ResidualSignal,
)
from hypervector.research.cross_asset_residual_replay import (
    evaluate_residual_pair,
)


def _minutes(
    symbol: str,
    *,
    start: str = "2026-01-01T00:00:00Z",
    periods: int = 31,
    price: float = 100.0,
) -> pd.DataFrame:
    times = pd.date_range(start, periods=periods, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": times,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "funding_rate": 0.0,
            "symbol": symbol,
        }
    )


def _signal(
    decision: str = "2026-01-01T00:05:00+00:00",
    *,
    direction: str = "long_spread",
    hedge_ratio: float = 2.0,
    zscore: float = -2.5,
) -> ResidualSignal:
    return ResidualSignal(
        decision_time_utc=decision,
        left_symbol="BTC",
        right_symbol="ETH",
        direction=direction,
        hedge_ratio=hedge_ratio,
        intercept=0.0,
        residual=-0.02,
        residual_mean=0.0,
        residual_std=0.01,
        zscore=zscore,
        error_correction_t=-3.0,
        fit_start_utc="2025-12-01T00:00:00+00:00",
        fit_end_utc="2026-01-01T00:05:00+00:00",
    )


def _states(*values: tuple[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "decision_time_utc": [value[0] for value in values],
            "zscore": [value[1] for value in values],
        }
    )


def _bars() -> dict[str, pd.DataFrame]:
    return {"BTC": _minutes("BTC"), "ETH": _minutes("ETH", price=50.0)}


def test_pair_entry_uses_next_minute_and_charges_four_execution_sides() -> None:
    """An atomic pair lifecycle sizes both legs and pays entry plus exit costs."""
    report = evaluate_residual_pair(
        minute_bars=_bars(),
        states=_states(("2026-01-01T00:10:00+00:00", 0.1)),
        signals=(_signal(),),
        config=CrossAssetResidualConfig(maximum_hold_bars=12),
    )

    trade = report.trades[0]
    assert trade.entry_time_utc == "2026-01-01T00:05:00+00:00"
    assert trade.exit_time_utc == "2026-01-01T00:10:00+00:00"
    assert trade.exit_reason == "mean_reversion"
    left_notional = trade.left_quantity * trade.left_entry_price
    right_notional = trade.right_quantity * trade.right_entry_price
    assert left_notional / right_notional == pytest.approx(0.5)
    assert trade.isolated_margin_usd == pytest.approx(1_500.0)
    assert trade.report_only is True
    assert trade.execution_authority == "none"
    expected_fees = (
        left_notional
        + right_notional
        + trade.left_quantity * trade.left_exit_price
        + trade.right_quantity * trade.right_exit_price
    ) * 0.00045
    assert trade.fees_usd == pytest.approx(expected_fees)
    assert report.net_pnl_usd == pytest.approx(trade.net_pnl_usd)


@pytest.mark.parametrize(
    ("exit_z", "maximum_hold", "expected"),
    [((-5.0,), 12, "residual_stop"), ((), 1, "maximum_hold")],
)
def test_pair_exits_on_residual_stop_or_maximum_hold(
    exit_z: tuple[float, ...],
    maximum_hold: int,
    expected: str,
) -> None:
    """Residual and time boundaries close both legs atomically."""
    rows = _states(("2026-01-01T00:10:00+00:00", exit_z[0])) if exit_z else _states()
    report = evaluate_residual_pair(
        minute_bars=_bars(),
        states=rows,
        signals=(_signal(),),
        config=CrossAssetResidualConfig(maximum_hold_bars=maximum_hold),
    )

    assert report.trades[0].exit_reason == expected


def test_pair_settles_signed_hourly_funding_on_both_legs() -> None:
    """Longs pay positive funding while shorts receive it at exact settlements."""
    bars = {
        "BTC": _minutes("BTC", start="2026-01-01T00:50:00Z", periods=31),
        "ETH": _minutes("ETH", start="2026-01-01T00:50:00Z", periods=31, price=50.0),
    }
    bars["BTC"].loc[bars["BTC"]["timestamp"].dt.minute.eq(0), "funding_rate"] = 0.001
    bars["ETH"].loc[bars["ETH"]["timestamp"].dt.minute.eq(0), "funding_rate"] = 0.002
    report = evaluate_residual_pair(
        minute_bars=bars,
        states=_states(),
        signals=(
            _signal(
                "2026-01-01T00:55:00+00:00",
                hedge_ratio=1.0,
            ),
        ),
        config=CrossAssetResidualConfig(maximum_hold_bars=3),
    )

    assert report.trades[0].funding_cashflow_usd > 0.0
    assert report.funding_cashflow_usd == pytest.approx(
        report.trades[0].funding_cashflow_usd
    )


def test_pair_liquidation_and_overlapping_signal_are_explicit() -> None:
    """Either isolated leg can close the pair; overlapping entries are rejected."""
    bars = _bars()
    bars["BTC"].loc[6, ["low", "close"]] = 70.0
    bars["ETH"].loc[6, "close"] = 40.0
    report = evaluate_residual_pair(
        minute_bars=bars,
        states=_states(),
        signals=(
            _signal(hedge_ratio=1.0),
            _signal("2026-01-01T00:06:00+00:00", hedge_ratio=1.0),
        ),
        config=replace(
            CrossAssetResidualConfig(),
            reentry_cooldown_bars=1,
        ),
    )

    assert report.trades[0].exit_reason == "liquidation"
    assert report.trades[0].exit_time_utc == "2026-01-01T00:07:00+00:00"
    assert report.trades[0].right_exit_price == pytest.approx(40.008)
    assert report.liquidations == 1
    assert report.conflict_rejections == 1
    assert report.liquidation_penalties_usd > 0.0


def test_end_of_data_uses_last_close_after_the_final_minute() -> None:
    """A forced close cannot execute retroactively at the final minute's open."""
    bars = _bars()
    bars["BTC"].loc[30, "close"] = 110.0
    bars["ETH"].loc[30, "close"] = 45.0

    report = evaluate_residual_pair(
        minute_bars=bars,
        states=_states(),
        signals=(_signal(hedge_ratio=1.0),),
        config=CrossAssetResidualConfig(maximum_hold_bars=288),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "end_of_data"
    assert trade.exit_time_utc == "2026-01-01T00:31:00+00:00"
    assert trade.left_exit_price == pytest.approx(109.978)
    assert trade.right_exit_price == pytest.approx(45.009)


def test_open_drawdown_uses_cost_adjusted_liquidation_value() -> None:
    """Open-position drawdown reserves adverse close slippage and exit fees."""
    bars = _bars()
    bars["BTC"].loc[6, ["low", "close"]] = 90.0
    bars["BTC"].loc[10, ["open", "high", "low", "close"]] = 120.0
    config = CrossAssetResidualConfig(maximum_hold_bars=12)

    report = evaluate_residual_pair(
        minute_bars=bars,
        states=_states(("2026-01-01T00:10:00+00:00", 0.1)),
        signals=(_signal(hedge_ratio=1.0),),
        config=config,
    )

    trade = report.trades[0]
    left_mark = 90.0 * (1.0 - config.slippage_bps_per_side / 10_000.0)
    right_mark = 50.0 * (1.0 + config.slippage_bps_per_side / 10_000.0)
    gross = trade.left_quantity * (left_mark - trade.left_entry_price)
    gross -= trade.right_quantity * (right_mark - trade.right_entry_price)
    exit_fee = (
        trade.left_quantity * left_mark + trade.right_quantity * right_mark
    ) * config.fee_rate_per_side
    entry_fee = (
        trade.left_quantity * trade.left_entry_price
        + trade.right_quantity * trade.right_entry_price
    ) * config.fee_rate_per_side
    marked_equity = config.initial_equity - entry_fee + gross - exit_fee
    expected = (config.initial_equity - marked_equity) / config.initial_equity * 100.0

    assert report.maximum_drawdown_pct == pytest.approx(expected)
