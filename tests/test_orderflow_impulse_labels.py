"""Lifecycle, cost, funding, and occupancy tests for order-flow impulse arms."""

from __future__ import annotations

import pandas as pd

from hypervector.research.orderflow_impulse_contract import OrderFlowImpulseConfig
from hypervector.research.orderflow_impulse_labels import (
    label_orderflow_arms,
    serialize_orderflow_outcomes,
)


def _bars(*, both_barriers: bool = False) -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=20, freq="1min", tz="UTC")
    high = [100.0] * 20
    low = [100.0] * 20
    if both_barriers:
        high[1] = 101.0
        low[1] = 99.0
    return pd.DataFrame(
        {
            "bar_open_at": times,
            "open": [100.0] * 20,
            "high": high,
            "low": low,
            "close": [100.0] * 20,
        }
    )


def _events(count: int = 1) -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=count, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "event_id": [f"BTC:{stamp.isoformat()}" for stamp in times],
            "symbol": ["BTC"] * count,
            "bar_open_at": times,
            "available_at_utc": times + pd.Timedelta(minutes=1),
            "arm": ["continuation_all"] * count,
            "side": ["long"] * count,
        }
    )


def test_label_enters_next_bar_and_uses_stop_first_ordering() -> None:
    """A simultaneous target/stop touch must resolve adversely."""
    outcomes = label_orderflow_arms(
        _bars(both_barriers=True),
        _events(),
        pd.DataFrame(columns=["timestamp", "funding_rate"]),
        OrderFlowImpulseConfig(warmup_minutes=5),
    )

    row = outcomes.iloc[0]
    assert row["entry_time_utc"] == pd.Timestamp("2026-01-01T00:01:00Z")
    assert row["status"] == "ambiguous_stop_first"
    assert row["gross_return_bps"] < -20.0


def test_flat_timeout_reconciles_to_thirteen_bps_nominal_cost() -> None:
    """A flat raw path must lose exactly modeled fee plus slippage friction."""
    outcomes = label_orderflow_arms(
        _bars(),
        _events(),
        pd.DataFrame(columns=["timestamp", "funding_rate"]),
        OrderFlowImpulseConfig(warmup_minutes=5),
    )

    row = outcomes.iloc[0]
    assert row["status"] == "timeout"
    assert abs(float(row["net_return_bps_nominal"]) + 13.0) < 0.01
    assert abs(float(row["net_return_bps_stress"]) + 20.0) < 0.01


def test_positive_funding_is_paid_by_long_and_received_by_short() -> None:
    """Funding cashflow direction must follow the Hyperliquid convention."""
    events = pd.concat(
        [_events(), _events().assign(event_id="BTC:short", side="short")],
        ignore_index=True,
    )
    funding = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-01T00:05:00Z")],
            "funding_rate": [0.001],
        }
    )
    outcomes = label_orderflow_arms(
        _bars(), events, funding, OrderFlowImpulseConfig(warmup_minutes=5)
    )

    by_side = outcomes.set_index("side")["funding_bps"]
    assert by_side["long"] == -10.0
    assert by_side["short"] == 10.0


def test_serialization_prevents_overlapping_positions_per_arm_and_symbol() -> None:
    """Later events are displaced until the prior lifecycle resolves."""
    outcomes = label_orderflow_arms(
        _bars(),
        _events(count=3),
        pd.DataFrame(columns=["timestamp", "funding_rate"]),
        OrderFlowImpulseConfig(warmup_minutes=5),
    )

    serialized = serialize_orderflow_outcomes(outcomes)

    assert serialized["accepted"].sum() == 1
    assert serialized["displacement_reason"].eq("symbol_position_open").sum() == 2
