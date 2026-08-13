"""Frozen development assessment for flow-exhaustion research."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Iterable

from hypervector.research.flow_exhaustion_replay_models import (
    FlowExhaustionReplayReport,
    FlowExhaustionTrade,
)


_TECHNICAL_REJECTION_REASONS = frozenset(
    {"entry_minute_unavailable", "outcome_path_incomplete"}
)


def assess_flow_exhaustion_development(
    nominal: FlowExhaustionReplayReport,
    stress: FlowExhaustionReplayReport,
    start_utc: datetime,
    end_utc: datetime,
) -> dict[str, object]:
    """Evaluate the preregistered cadence, economics, and integrity criteria."""
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("development assessment requires aware timestamps")
    duration_days = (end_utc - start_utc).total_seconds() / 86_400.0
    if duration_days <= 0.0:
        raise ValueError("development assessment requires a positive duration")
    cadence = nominal.completed_trades / duration_days
    directions = {
        direction: _trade_metrics(
            trade for trade in nominal.trades if trade.direction == direction
        )
        for direction in ("long", "short")
    }
    technical_rejections = _technical_rejection_count(nominal) + (
        _technical_rejection_count(stress)
    )
    criteria = _development_criteria(
        nominal, stress, cadence, directions, technical_rejections
    )
    return {
        "passed": all(bool(item["passed"]) for item in criteria.values()),
        "calendar_days": duration_days,
        "completed_trades_per_day": cadence,
        "criteria": criteria,
        "by_direction": directions,
        "by_symbol": {
            symbol: _trade_metrics(
                trade for trade in nominal.trades if trade.symbol == symbol
            )
            for symbol in ("BTC", "SOL")
        },
        "nominal_rejection_reasons": _rejection_counts(nominal),
        "stress_rejection_reasons": _rejection_counts(stress),
    }


def _development_criteria(
    nominal: FlowExhaustionReplayReport,
    stress: FlowExhaustionReplayReport,
    cadence: float,
    directions: dict[str, dict[str, object]],
    technical_rejections: int,
) -> dict[str, dict[str, object]]:
    return {
        "minimum_trades": _criterion(
            nominal.completed_trades >= 100,
            nominal.completed_trades,
            ">= 100 completed trades",
        ),
        "cadence_range": _criterion(
            0.5 <= cadence <= 5.0,
            cadence,
            "0.5 to 5.0 completed trades/calendar day",
        ),
        "nominal_edge": _criterion(
            nominal.net_pnl_usd > 0.0
            and nominal.profit_factor is not None
            and nominal.profit_factor > 1.15,
            {
                "net_pnl_usd": nominal.net_pnl_usd,
                "profit_factor": nominal.profit_factor,
            },
            "positive net PnL and PF > 1.15 at 13 bps",
        ),
        "stress_edge": _criterion(
            stress.profit_factor is not None and stress.profit_factor > 1.0,
            {
                "net_pnl_usd": stress.net_pnl_usd,
                "profit_factor": stress.profit_factor,
            },
            "PF > 1.00 at 20 bps",
        ),
        "long_sleeve": _sleeve_criterion(directions["long"]),
        "short_sleeve": _sleeve_criterion(directions["short"]),
        "technical_integrity": _criterion(
            technical_rejections == 0
            and nominal.liquidations == 0
            and stress.liquidations == 0,
            {
                "technical_rejections": technical_rejections,
                "nominal_liquidations": nominal.liquidations,
                "stress_liquidations": stress.liquidations,
            },
            "zero impacted lifecycle gaps and zero modeled liquidations",
        ),
    }


def _criterion(passed: bool, observed: object, required: str) -> dict[str, object]:
    return {"passed": bool(passed), "observed": observed, "required": required}


def _sleeve_criterion(metrics: dict[str, object]) -> dict[str, object]:
    count = int(metrics["completed_trades"])
    net = float(metrics["net_pnl_usd"])
    return _criterion(
        count >= 20 and net > 0.0,
        metrics,
        ">= 20 completed trades and positive net PnL",
    )


def _trade_metrics(trades: Iterable[FlowExhaustionTrade]) -> dict[str, object]:
    selected = tuple(trades)
    profits = [
        trade.scaled_net_pnl_usd for trade in selected if trade.scaled_net_pnl_usd > 0.0
    ]
    losses = [
        -trade.scaled_net_pnl_usd
        for trade in selected
        if trade.scaled_net_pnl_usd < 0.0
    ]
    return {
        "completed_trades": len(selected),
        "wins": len(profits),
        "losses": len(losses),
        "net_pnl_usd": sum(profits) - sum(losses),
        "profit_factor": sum(profits) / sum(losses) if losses else None,
        "liquidations": sum(trade.exit_reason == "liquidation" for trade in selected),
    }


def _technical_rejection_count(report: FlowExhaustionReplayReport) -> int:
    return sum(
        rejection.reason in _TECHNICAL_REJECTION_REASONS
        for rejection in report.rejections
    )


def _rejection_counts(report: FlowExhaustionReplayReport) -> dict[str, int]:
    return dict(sorted(Counter(item.reason for item in report.rejections).items()))
