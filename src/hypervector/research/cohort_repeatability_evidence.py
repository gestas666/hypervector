"""Report-only repeatability evidence from resolved live lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import mean, median, stdev

from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
    text,
)

Record = Mapping[str, object]
_HOUR_MS = 3_600_000
_HOURS_PER_DAY = 24.0


def build_repeatability_evidence(trades: Sequence[Record]) -> dict[str, object]:
    """Build descriptive live-sample repeatability evidence."""
    grouped: dict[str, list[Record]] = {}
    for trade in trades:
        strategy_id = text(trade.get("strategy_id"), "repeatability strategy")
        symbol = text(trade.get("symbol"), "repeatability symbol")
        grouped.setdefault(f"{strategy_id}|{symbol}", []).append(trade)
    return {
        "schema_version": 1,
        "mode": "cohort_live_repeatability_v1",
        "scope": "compatible_profile_history",
        "contract": _contract(),
        "by_provider_symbol": {
            key: _provider_summary(key, values)
            for key, values in sorted(grouped.items())
        },
        "limitations": [
            "observed cadence describes only the elapsed compatible live window",
            "trade outcomes are serial and share one portfolio",
            "no value is annualized or treated as a profit forecast",
            "sample size, balance, and performance do not gate execution",
        ],
    }


def _provider_summary(key: str, trades: Sequence[Record]) -> dict[str, object]:
    strategy_id, separator, symbol = key.rpartition("|")
    if not separator or not strategy_id or not symbol:
        raise ValueError("repeatability key must be strategy|symbol")
    grouped: dict[str, list[Record]] = {}
    for trade in trades:
        side = text(trade.get("side"), "repeatability side")
        if side not in {"long", "short"}:
            raise ValueError("repeatability side must be long or short")
        grouped.setdefault(side, []).append(trade)
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        **_summary(trades),
        "by_side": {side: _summary(values) for side, values in sorted(grouped.items())},
        "profit_forecast": None,
    }


def _summary(trades: Sequence[Record]) -> dict[str, object]:
    pnls = tuple(
        number(trade.get("net_pnl_usd"), "repeatability net PnL") for trade in trades
    )
    windows = tuple(_trade_window(trade) for trade in trades)
    first_entry = min(entry for entry, _ in windows)
    last_exit = max(exit_ms for _, exit_ms in windows)
    span_hours = (last_exit - first_entry) / _HOUR_MS
    gross_profit = sum(value for value in pnls if value > 0.0)
    gross_loss = -sum(value for value in pnls if value < 0.0)
    largest_winner = max((value for value in pnls if value > 0.0), default=None)
    return {
        "closed_trades": len(trades),
        "evidence_state": (
            "descriptive_multi_trade_sample" if len(trades) > 1 else "single_trade_only"
        ),
        "first_entry_timestamp_ms": first_entry,
        "last_exit_timestamp_ms": last_exit,
        "observation_span_hours": span_hours,
        "trades_per_24h_observed": (
            len(trades) * _HOURS_PER_DAY / span_hours
            if len(trades) > 1 and span_hours > 0.0
            else None
        ),
        "net_pnl_usd": sum(pnls),
        "mean_net_pnl_usd": float(mean(pnls)),
        "median_net_pnl_usd": float(median(pnls)),
        "sample_stddev_net_pnl_usd": float(stdev(pnls)) if len(pnls) > 1 else None,
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "largest_winner_usd": largest_winner,
        "largest_winner_share_of_gross_profit_pct": (
            largest_winner / gross_profit * 100.0
            if largest_winner is not None and gross_profit > 0.0
            else None
        ),
        "net_pnl_excluding_largest_winner_usd": (
            sum(pnls) - largest_winner if largest_winner is not None else None
        ),
    }


def _trade_window(trade: Record) -> tuple[int, int]:
    entry = mapping(trade.get("entry"), "repeatability entry")
    exit_leg = mapping(trade.get("exit"), "repeatability exit")
    entry_ms = nonnegative_int(
        entry.get("venue_timestamp_ms"), "repeatability entry timestamp"
    )
    exit_ms = nonnegative_int(
        exit_leg.get("venue_timestamp_ms"), "repeatability exit timestamp"
    )
    if exit_ms <= entry_ms:
        raise ValueError("repeatability exit must follow entry")
    return entry_ms, exit_ms


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
        "trade_count_gate": False,
    }
