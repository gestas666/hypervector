"""Causality and event-family tests for one-minute order-flow impulse research."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from hypervector.research.orderflow_impulse_contract import OrderFlowImpulseConfig
from hypervector.research.orderflow_impulse_events import (
    build_orderflow_event_arms,
    build_orderflow_feature_rows,
)


def _inputs(rows: int = 30) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    times = pd.date_range("2026-01-01", periods=rows, freq="1min", tz="UTC")
    close = np.linspace(100.0, 101.0, rows)
    bars = pd.DataFrame(
        {
            "bar_open_at": times,
            "open": close - 0.01,
            "high": close + 0.02,
            "low": close - 0.02,
            "close": close,
            "volume": np.linspace(10.0, 20.0, rows),
            "trade_count": np.arange(rows) + 10,
        }
    )
    trades = pd.DataFrame(
        {
            "bar_open_at": times,
            "buy_volume": np.linspace(8.0, 16.0, rows),
            "sell_volume": np.linspace(2.0, 4.0, rows),
        }
    )
    books = pd.DataFrame(
        {
            "bar_open_at": times,
            "last_book_at": times + pd.Timedelta(seconds=59),
            "imbalance_5_last": np.full(rows, 0.3),
            "imbalance_5_delta": np.full(rows, 0.1),
            "micro_price_delta_bps": np.full(rows, 0.2),
            "spread_bps_last": np.full(rows, 0.5),
            "bid_depth_10_last": np.full(rows, 100.0),
            "ask_depth_10_last": np.full(rows, 80.0),
        }
    )
    return bars, trades, books


def test_feature_rows_are_prefix_invariant() -> None:
    """Appending future inputs must not change earlier completed features."""
    bars, trades, books = _inputs()
    config = OrderFlowImpulseConfig(warmup_minutes=5)

    prefix = build_orderflow_feature_rows(
        bars.iloc[:20], trades.iloc[:20], books.iloc[:20], config
    )
    full = build_orderflow_feature_rows(bars, trades, books, config)

    pdt.assert_frame_equal(prefix, full.iloc[: len(prefix)].reset_index(drop=True))


def test_feature_rows_reject_future_book_observation() -> None:
    """An L2 observation after the decision boundary is leakage."""
    bars, trades, books = _inputs()
    books.loc[10, "last_book_at"] = bars.loc[10, "bar_open_at"] + pd.Timedelta(
        minutes=1, seconds=1
    )

    with pytest.raises(ValueError, match="future book"):
        build_orderflow_feature_rows(
            bars, trades, books, OrderFlowImpulseConfig(warmup_minutes=5)
        )


def test_event_family_reports_continuation_and_reversion_without_side_gate() -> None:
    """Every base event retains symmetric causal continuation/reversion arms."""
    bars, trades, books = _inputs()
    bars.loc[20, ["open", "close", "high"]] = [100.0, 102.0, 102.1]
    trades.loc[20, ["buy_volume", "sell_volume"]] = [100.0, 1.0]
    features = build_orderflow_feature_rows(
        bars, trades, books, OrderFlowImpulseConfig(warmup_minutes=5)
    )

    arms = build_orderflow_event_arms(features, symbol="BTC")
    event = arms.loc[arms["bar_open_at"].eq(bars.loc[20, "bar_open_at"])]

    assert set(event["arm"]) == {
        "continuation_all",
        "continuation_l2_aligned",
        "reversion_all",
    }
    assert set(event["side"]) == {"long", "short"}
    assert not event["arm"].eq("reversion_l2_opposed").any()
