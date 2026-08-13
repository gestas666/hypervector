"""Path-dependent shared-account mark-to-market tests."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.concurrent_mtm_portfolio import (
    MarkedLifecycle,
    replay_concurrent_mark_to_market,
)


def _bars(
    times_ms: list[int],
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> pd.DataFrame:
    index = pd.to_datetime(times_ms, unit="ms", utc=True)
    return pd.DataFrame(
        {"close": closes, "high": highs, "low": lows},
        index=index,
    )


def _trade(
    trade_id: str,
    symbol: str,
    side: str,
    entry_ms: int,
    exit_ms: int,
    entry: float,
    exit_price: float,
    quantity: float,
    entry_fee: float,
    exit_fee: float,
    funding: float = 0.0,
) -> MarkedLifecycle:
    sign = 1.0 if side == "long" else -1.0
    gross = sign * quantity * (exit_price - entry)
    net = gross - entry_fee - exit_fee + funding
    return MarkedLifecycle(
        trade_id=trade_id,
        strategy_id="test",
        symbol=symbol,
        side=side,
        entry_time_ms=entry_ms,
        exit_time_ms=exit_ms,
        entry_price=entry,
        exit_price=exit_price,
        quantity=quantity,
        entry_fee_usd=entry_fee,
        exit_fee_usd=exit_fee,
        funding_cashflow_usd=funding,
        net_pnl_usd=net,
    )


def test_concurrent_marks_capture_open_losses_and_reconcile_terminal_equity() -> None:
    trades = (
        _trade("a", "A", "long", 100, 300, 100.0, 105.0, 1.0, 1.0, 1.0),
        _trade("b", "B", "short", 200, 400, 200.0, 190.0, 0.5, 0.5, 0.5),
    )
    marks = {
        "A": _bars([150, 250], [90.0, 102.0], [95.0, 104.0], [80.0, 98.0]),
        "B": _bars([250, 350], [210.0, 195.0], [220.0, 205.0], [205.0, 190.0]),
    }

    report, path = replay_concurrent_mark_to_market(trades, marks, 500.0)

    assert report.final_equity_usd == pytest.approx(507.0)
    assert path.iloc[-1]["close_mark_equity_usd"] == pytest.approx(507.0)
    assert report.close_mark_maximum_drawdown_pct < -2.0
    assert report.adverse_intrabar_maximum_drawdown_pct < -4.0
    assert report.maximum_concurrent_positions == 2
    assert report.unobserved_lifecycles == 0
    assert (
        report.adverse_intrabar_maximum_drawdown_pct
        <= report.close_mark_maximum_drawdown_pct
    )


def test_funding_accrues_only_while_position_is_open() -> None:
    trade = _trade(
        "funded",
        "A",
        "long",
        100,
        300,
        100.0,
        100.0,
        1.0,
        0.0,
        0.0,
        funding=-2.0,
    )
    marks = {"A": _bars([200], [100.0], [100.0], [100.0])}

    report, path = replay_concurrent_mark_to_market((trade,), marks, 500.0)

    midpoint = path.loc[path["timestamp_ms"].eq(200)].iloc[0]
    assert midpoint["close_mark_equity_usd"] == pytest.approx(499.0)
    assert report.final_equity_usd == pytest.approx(498.0)


def test_missing_intratrade_marks_are_named_not_silently_filled() -> None:
    trade = _trade("missing", "A", "long", 100, 200, 100.0, 101.0, 1.0, 0.0, 0.0)

    report, _path = replay_concurrent_mark_to_market(
        (trade,),
        {"A": _bars([250], [101.0], [101.0], [101.0])},
        500.0,
    )

    assert report.unobserved_lifecycles == 1
    assert report.unobserved_trade_ids == ("missing",)
    assert report.missing_mark_lifecycles == 1
    assert report.instant_exit_lifecycles == 0


def test_completed_exit_bar_is_observed_before_exact_exit_cashflow() -> None:
    trade = _trade("exit-bar", "A", "long", 100, 200, 100.0, 101.0, 1.0, 0.0, 0.0)
    marks = {"A": _bars([200], [101.0], [102.0], [95.0])}

    report, _path = replay_concurrent_mark_to_market((trade,), marks, 500.0)

    assert report.observed_lifecycles == 1
    assert report.adverse_intrabar_maximum_drawdown_pct == pytest.approx(
        100.0 * (495.0 / 501.0 - 1.0)
    )


def test_one_millisecond_normalized_exit_is_classified_as_instant() -> None:
    trade = _trade("instant", "A", "long", 100, 101, 100.0, 99.0, 1.0, 0.0, 0.0)

    report, _path = replay_concurrent_mark_to_market(
        (trade,), {"A": _bars([200], [99.0], [99.0], [99.0])}, 500.0
    )

    assert report.instant_exit_lifecycles == 1
    assert report.missing_mark_lifecycles == 0


def test_lifecycle_net_must_reconcile_to_price_fees_and_funding() -> None:
    with pytest.raises(ValueError, match="does not reconcile"):
        MarkedLifecycle(
            trade_id="bad",
            strategy_id="test",
            symbol="A",
            side="long",
            entry_time_ms=100,
            exit_time_ms=200,
            entry_price=100.0,
            exit_price=101.0,
            quantity=1.0,
            entry_fee_usd=0.0,
            exit_fee_usd=0.0,
            funding_cashflow_usd=0.0,
            net_pnl_usd=2.0,
        )
