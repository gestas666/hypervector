"""Development-gate tests for the flow-exhaustion challenger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hypervector.research.flow_exhaustion_replay_models import (
    FlowExhaustionRejection,
    FlowExhaustionReplayReport,
    FlowExhaustionTrade,
)
from hypervector.research.flow_exhaustion_reporting import (
    assess_flow_exhaustion_development,
)


def _trade(index: int, direction: str, pnl: float) -> FlowExhaustionTrade:
    entry = datetime(2025, 8, 4, tzinfo=UTC) + timedelta(hours=index)
    return FlowExhaustionTrade(
        f"trade-{index}",
        "BTC" if index % 2 == 0 else "SOL",
        direction,
        entry.isoformat(),
        entry.isoformat(),
        (entry + timedelta(minutes=5)).isoformat(),
        100.0,
        100.1,
        99.0,
        101.0,
        80.0,
        1.0,
        100.0,
        20.0,
        37.5,
        pnl + 0.1,
        0.05,
        0.05,
        0.1,
        0.0,
        pnl,
        pnl,
        "target" if pnl > 0 else "stop",
        False,
    )


def _report(
    *, stress: bool = False, technical_gap: bool = False
) -> FlowExhaustionReplayReport:
    loss = -8.0 if stress else -5.0
    trades = tuple(
        _trade(
            index, "long" if index < 50 else "short", 10.0 if index % 2 == 0 else loss
        )
        for index in range(100)
    )
    gross_profit = sum(
        trade.scaled_net_pnl_usd for trade in trades if trade.scaled_net_pnl_usd > 0.0
    )
    gross_loss = -sum(
        trade.scaled_net_pnl_usd for trade in trades if trade.scaled_net_pnl_usd < 0.0
    )
    net = gross_profit - gross_loss
    rejections = (
        (
            FlowExhaustionRejection(
                "BTC", trades[0].entry_time_utc, "long", "outcome_path_incomplete"
            ),
        )
        if technical_gap
        else ()
    )
    return FlowExhaustionReplayReport(
        15_000.0,
        15_000.0 + net,
        net,
        net / 150.0,
        100,
        50,
        50,
        gross_profit / gross_loss,
        -2.0,
        2,
        10.0,
        0.0,
        0,
        trades,
        rejections,
    )


def test_development_gate_requires_cadence_economics_and_both_sides() -> None:
    """A balanced 100-trade nominal/stress survivor must pass the frozen gate."""
    start = datetime(2025, 8, 4, tzinfo=UTC)
    end = start + timedelta(days=100)

    assessment = assess_flow_exhaustion_development(
        _report(), _report(stress=True), start, end
    )

    assert assessment["passed"] is True
    assert assessment["completed_trades_per_day"] == 1.0
    assert assessment["by_direction"]["long"]["completed_trades"] == 50
    assert all(item["passed"] for item in assessment["criteria"].values())


def test_development_gate_fails_an_impacted_lifecycle_gap() -> None:
    """A missing minute crossed by a candidate lifecycle must block promotion."""
    start = datetime(2025, 8, 4, tzinfo=UTC)
    end = start + timedelta(days=100)

    assessment = assess_flow_exhaustion_development(
        _report(technical_gap=True), _report(stress=True), start, end
    )

    assert assessment["passed"] is False
    assert assessment["criteria"]["technical_integrity"]["passed"] is False
