"""One-minute lifecycle contracts for flow-exhaustion reversion."""

from __future__ import annotations

import pandas as pd

from hypervector.research.flow_exhaustion_replay import (
    FlowExhaustionReplayConfig,
    replay_flow_exhaustion_signals,
)


def _signal(*, side: str = "long", target: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["BTC"],
            "bar_open_at": [pd.Timestamp("2026-01-01T00:00:00Z")],
            "available_at_utc": [pd.Timestamp("2026-01-01T00:05:00Z")],
            "side": [side],
            "target_price": [target],
            "stop_price": [99.0 if side == "long" else 101.0],
            "rank_score": [2.0],
        }
    )


def _minutes(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    times = pd.date_range("2026-01-01T00:05:00Z", periods=len(rows), freq="1min")
    return pd.DataFrame(
        {
            "timestamp": times,
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
            "funding_rate": [0.0] * len(rows),
        }
    )


def test_replay_prices_target_after_adverse_entry_and_exit_costs() -> None:
    """A target fill must retain fees, slippage, risk sizing, and identity."""
    minutes = _minutes([(99.70, 100.05, 99.60, 100.0)])

    report = replay_flow_exhaustion_signals(
        {"BTC": minutes}, _signal(), FlowExhaustionReplayConfig()
    )

    assert report.completed_trades == 1
    trade = report.trades[0]
    assert trade.exit_reason == "target"
    assert trade.entry_price > 99.70
    assert trade.exit_price < 100.0
    assert trade.fees_usd > 0.0
    assert trade.net_pnl_usd < trade.gross_pnl_usd
    assert report.execution_authority == "none"


def test_replay_orders_liquidation_stop_before_target_in_same_minute() -> None:
    """Ambiguous one-minute paths must resolve pessimistically."""
    minutes = _minutes([(99.70, 100.10, 98.90, 99.5)])

    report = replay_flow_exhaustion_signals(
        {"BTC": minutes}, _signal(), FlowExhaustionReplayConfig()
    )

    trade = report.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.same_minute_ambiguous is True


def test_replay_rejects_entry_when_target_edge_has_dissipated() -> None:
    """A gap that leaves less than 26 gross bps cannot be backfilled."""
    minutes = _minutes([(99.80, 99.90, 99.70, 99.85)])

    report = replay_flow_exhaustion_signals(
        {"BTC": minutes}, _signal(), FlowExhaustionReplayConfig()
    )

    assert report.completed_trades == 0
    assert report.rejections[0].reason == "entry_edge_dissipated"


def test_replay_applies_only_funding_strictly_after_entry() -> None:
    """An exact entry-time settlement predates ownership of the position."""
    minutes = _minutes([(99.60, 99.70, 99.50, 99.60), (99.60, 100.05, 99.55, 100.0)])
    minutes.loc[0, "funding_rate"] = 0.01
    minutes.loc[1, "funding_rate"] = 0.001

    report = replay_flow_exhaustion_signals(
        {"BTC": minutes}, _signal(), FlowExhaustionReplayConfig()
    )

    trade = report.trades[0]
    assert trade.funding_cashflow_usd < 0.0
    assert abs(trade.funding_cashflow_usd) < trade.notional_usd * 0.002


def test_replay_enforces_one_position_per_symbol() -> None:
    """A second BTC event must expire while the first lifecycle is open."""
    signals = pd.concat(
        [
            _signal(),
            _signal().assign(
                bar_open_at=pd.Timestamp("2026-01-01T00:05:00Z"),
                available_at_utc=pd.Timestamp("2026-01-01T00:10:00Z"),
            ),
        ],
        ignore_index=True,
    )
    rows = [(99.60, 99.70, 99.50, 99.60)] * 30
    rows.append((99.60, 100.05, 99.55, 100.0))

    report = replay_flow_exhaustion_signals(
        {"BTC": _minutes(rows)}, signals, FlowExhaustionReplayConfig()
    )

    assert report.completed_trades == 1
    assert any(item.reason == "symbol_position_open" for item in report.rejections)


def test_replay_allows_path_gap_after_trade_has_already_closed() -> None:
    """An unrelated later archive gap must not invalidate an earlier exit."""
    minutes = _minutes([(99.70, 100.05, 99.60, 100.0), (99.70, 99.80, 99.60, 99.7)])
    minutes.loc[1, "timestamp"] += pd.Timedelta(minutes=1)

    report = replay_flow_exhaustion_signals(
        {"BTC": minutes}, _signal(), FlowExhaustionReplayConfig()
    )

    assert report.completed_trades == 1
    assert report.trades[0].exit_reason == "target"


def test_replay_rejects_lifecycle_that_crosses_missing_minute() -> None:
    """A gap before resolution must remain a technical lifecycle rejection."""
    minutes = _minutes([(99.60, 99.70, 99.50, 99.60), (99.60, 100.05, 99.55, 100.0)])
    minutes.loc[1, "timestamp"] += pd.Timedelta(minutes=1)

    report = replay_flow_exhaustion_signals(
        {"BTC": minutes}, _signal(), FlowExhaustionReplayConfig()
    )

    assert report.completed_trades == 0
    assert report.rejections[0].reason == "outcome_path_incomplete"
