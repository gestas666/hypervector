from __future__ import annotations

import pytest

from hypervector.data.hl_events import (
    AssetContextEvent,
    BookLevel,
    L2SnapshotEvent,
)
from hypervector.research.sol_range_onset_backend_telemetry import (
    build_sol_backend_rows,
)
from hypervector.research.sol_range_onset_shadow_models import (
    SharedCapitalSnapshot,
    SolShadowPosition,
    SolShadowSnapshot,
)


def _book(timestamp_ms: int) -> L2SnapshotEvent:
    return L2SnapshotEvent(
        symbol="SOL",
        exchange_ts_ms=timestamp_ms,
        received_ts_ns=(timestamp_ms + 5) * 1_000_000,
        bids=(BookLevel(99.9, 10.0, 1), BookLevel(99.8, 5.0, 1)),
        asks=(BookLevel(100.1, 5.0, 1), BookLevel(100.2, 5.0, 1)),
    )


def _context(timestamp_ms: int) -> AssetContextEvent:
    return AssetContextEvent(
        symbol="SOL",
        observed_ts_ms=timestamp_ms,
        received_ts_ns=timestamp_ms * 1_000_000,
        mark_price=101.0,
        oracle_price=100.9,
        funding_rate_hourly=0.0001,
        open_interest=1_000_000.0,
        mid_price=100.0,
    )


def _open_snapshot() -> SolShadowSnapshot:
    position = SolShadowPosition(
        direction="long",
        entry_decision_time_ms=1_000,
        entry_time_ms=1_100,
        entry_price=100.1,
        reference_price=100.0,
        quantity=2.0,
        notional_usd=200.2,
        margin_usd=40.04,
        entry_fee_usd=0.09,
        stop_price=99.4994,
        liquidation_price=82.0,
    )
    return SolShadowSnapshot("active", -0.09, position, None, None, None, ())


def test_backend_rows_project_position_book_and_mark_without_authority() -> None:
    rows = build_sol_backend_rows(
        records=(
            {
                "action": "entry_filled",
                "event_time_ms": 1_100,
                "direction": "long",
                "fill_px": 100.1,
                "fill_qty": 2.0,
                "fee_usd": 0.09,
                "position_qty": 2.0,
                "position_avg_px": 100.1,
                "liquidation_price": 82.0,
                "equity_delta_usd": -0.09,
                "execution_authority": "none",
                "submitted": False,
                "place_attempted": False,
            },
        ),
        snapshot=_open_snapshot(),
        capital=SharedCapitalSnapshot(1_000, 15_000.0, 0.0, "btc-run"),
        latest_book=_book(1_200),
        latest_context=_context(1_150),
        recorded_at_ms=1_300,
    )

    assert [row["action"] for row in rows] == [
        "enter_long",
        "book_observation",
        "shadow_state",
    ]
    entry = rows[0]
    assert entry["position_qty"] == 2.0
    assert entry["realized_pnl"] == -0.09
    assert entry["equity"] == 14_999.91
    book = rows[1]
    assert book["mid_px"] == 100.0
    assert book["spread_bps"] == pytest.approx(20.0)
    assert book["bid_depth_ratio"] == 1.5
    assert book["opi"] == 0.2
    state = rows[2]
    assert state["mark_px"] == 101.0
    assert state["unrealized_pnl"] == pytest.approx(1.8)
    assert state["equity"] == pytest.approx(15_001.71)
    assert state["position_qty"] == 2.0
    assert state["liquidation_price"] == 82.0
    assert all(row["execution_authority"] == "none" for row in rows)
    assert all(row["submitted"] is False for row in rows)
    assert all(row["place_attempted"] is False for row in rows)


def test_backend_rows_project_close_as_flat_lifecycle_row() -> None:
    snapshot = SolShadowSnapshot("active", 12.0, None, None, None, None, ())
    rows = build_sol_backend_rows(
        records=(
            {
                "action": "position_closed",
                "event_time_ms": 2_000,
                "fill_px": 106.0,
                "fill_qty": 2.0,
                "fee_usd": 0.1,
                "position_qty": 0.0,
                "position_avg_px": 0.0,
                "exit_reason": "opposite_signal",
                "equity_delta_usd": 12.0,
                "execution_authority": "none",
                "submitted": False,
                "place_attempted": False,
            },
        ),
        snapshot=snapshot,
        capital=SharedCapitalSnapshot(1_900, 15_000.0, 0.0, "btc-run"),
        latest_book=None,
        latest_context=None,
        recorded_at_ms=2_100,
    )

    assert rows[0]["action"] == "close"
    assert rows[0]["position_qty"] == 0.0
    assert rows[0]["realized_pnl"] == 12.0
    assert rows[0]["equity"] == 15_012.0
    assert rows[-1]["action"] == "shadow_state"
    assert rows[-1]["position_qty"] == 0.0
