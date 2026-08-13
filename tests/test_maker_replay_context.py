"""Authentic mark/oracle and funding tests for causal maker replay."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.maker_replay import MakerReplayConfig, replay_maker_orders
from hypervector.research.maker_replay_context import MakerReplayContext


def _decisions(direction: str, periods: int = 3) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=periods, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"primary_regime": [direction] * periods, "breakout_direction": None},
        index=index,
    )


def _book(seconds: list[int], bids: list[float], asks: list[float]) -> pd.DataFrame:
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    times = [origin + pd.Timedelta(seconds=value) for value in seconds]
    return pd.DataFrame(
        {
            "ts_ms": [int(value.timestamp() * 1000) for value in times],
            "best_bid": bids,
            "best_ask": asks,
        }
    )


def _context(
    price_seconds: list[int],
    marks: list[float],
    *,
    funding_second: int | None = None,
    funding_rate: float = 0.0,
) -> MakerReplayContext:
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    prices = pd.DataFrame(
        {
            "ts_ms": [
                int((origin + pd.Timedelta(seconds=value)).timestamp() * 1000)
                for value in price_seconds
            ],
            "mark_price": marks,
            "oracle_price": [100.0] * len(marks),
        }
    )
    funding = pd.DataFrame(columns=["event_ts_ms", "funding_rate"])
    if funding_second is not None:
        funding = pd.DataFrame(
            {
                "event_ts_ms": [
                    int(
                        (origin + pd.Timedelta(seconds=funding_second)).timestamp()
                        * 1000
                    )
                ],
                "funding_rate": [funding_rate],
            }
        )
    return MakerReplayContext(prices, funding)


def test_authentic_mark_triggers_liquidation_at_last_adverse_bbo() -> None:
    """Mark is the trigger while executable BBO remains the liquidation fill."""
    report = replay_maker_orders(
        _book([60, 70, 80], [100.0, 99.0, 99.0], [101.0, 100.0, 100.0]),
        _decisions("TREND_UP"),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
        ),
        context=_context([69, 75], [100.0, 98.0]),
    )

    assert report.liquidation_model == "hyperliquid_mark_bbo_execution_v1"
    assert report.liquidations == 1
    assert report.trades[0].exit_price == pytest.approx(99.0)
    assert report.authentic_price_updates == 2


@pytest.mark.parametrize(
    ("direction", "expected_sign"),
    [("TREND_UP", -1.0), ("TREND_DOWN", 1.0)],
)
def test_funding_long_pays_and_short_receives_once(
    direction: str, expected_sign: float
) -> None:
    """Signed funding uses backward-known oracle notional once per settlement."""
    bids = [100.0, 99.0, 100.2]
    asks = [101.0, 100.0, 100.3]
    if direction == "TREND_DOWN":
        bids, asks = [100.0, 102.0, 100.6], [101.0, 103.0, 100.7]
    report = replay_maker_orders(
        _book([60, 70, 80], bids, asks),
        _decisions(direction),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
        ),
        context=_context(
            [69, 79], [100.0, 100.0], funding_second=75, funding_rate=0.00001
        ),
    )

    assert report.funding_settlements == 1
    expected_cashflow = expected_sign * report.trades[0].quantity * 100.0 * 0.00001
    assert report.funding_cashflow == pytest.approx(expected_cashflow)
    assert report.trades[0].funding_cashflow == pytest.approx(expected_cashflow)
    assert report.trades[0].net_pnl == pytest.approx(
        report.trades[0].gross_pnl - report.trades[0].fees + expected_cashflow
    )


def test_stale_oracle_funding_is_reported_and_not_zero_filled() -> None:
    """A stale oracle cannot produce a fabricated neutral funding settlement."""
    report = replay_maker_orders(
        _book([60, 70, 90], [100.0, 99.0, 100.2], [101.0, 100.0, 100.3]),
        _decisions("TREND_UP"),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            context_max_age_seconds=5.0,
        ),
        context=_context([69, 89], [100.0, 100.0], funding_second=80, funding_rate=0.1),
    )

    assert report.funding_settlements == 0
    assert report.stale_oracle_settlements == 1
    assert report.funding_cashflow == 0.0
    assert not report.execution_economics_conclusive


def test_stale_mark_while_position_is_open_marks_replay_inconclusive() -> None:
    """An unobserved liquidation interval cannot retain a conclusive result."""
    report = replay_maker_orders(
        _book([60, 70, 80], [100.0, 99.0, 99.0], [101.0, 100.0, 100.0]),
        _decisions("TREND_UP"),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            context_max_age_seconds=5.0,
        ),
        context=_context([69], [100.0]),
    )

    assert report.stale_mark_events > 0
    assert not report.execution_economics_conclusive
    assert any("mark" in limitation for limitation in report.limitations)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf")])
def test_context_rejects_non_finite_price_or_funding(invalid: float) -> None:
    """NaN or infinity cannot bypass causal context validation."""
    prices = pd.DataFrame(
        {"ts_ms": [1], "mark_price": [invalid], "oracle_price": [100.0]}
    )
    funding = pd.DataFrame({"event_ts_ms": [1], "funding_rate": [invalid]})

    with pytest.raises(ValueError, match="finite"):
        MakerReplayContext(prices, pd.DataFrame(columns=funding.columns))
    with pytest.raises(ValueError, match="finite"):
        MakerReplayContext(
            prices.assign(mark_price=100.0),
            funding,
        )
