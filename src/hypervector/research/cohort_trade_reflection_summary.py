"""Cumulative report-only summaries for cohort trade reflections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import mapping, number, text

Record = Mapping[str, object]
_TIMER_REASONS = frozenset({"maximum_hold", "maximum_hold_seconds"})
_TIMER_CONTEXTS = (
    "still_directionally_supported",
    "directionally_opposed",
    "mixed_or_transition",
    "unavailable",
)


def build_exit_reason_summary(
    trades: Sequence[Record], horizons: Sequence[int]
) -> dict[str, object]:
    """Group closed-trade economics and later paths by exit reason."""
    grouped: dict[str, list[Record]] = {}
    for trade in trades:
        reason = _exit_reason(trade)
        grouped.setdefault(reason, []).append(trade)
    return {
        reason: _trade_summary(values, horizons)
        for reason, values in sorted(grouped.items())
    }


def build_maximum_hold_context_journal(
    trades: Sequence[Record], horizons: Sequence[int]
) -> dict[str, object]:
    """Summarize timer exits by the causal regime context present at exit."""
    summary = _maximum_hold_summary(trades, horizons)
    return {
        "schema_version": 1,
        "mode": "maximum_hold_regime_context_journal",
        "contract": _contract(),
        **summary,
        "provider_symbols": _provider_symbol_summaries(trades, horizons),
        "limitations": [
            "post-exit paths are descriptive completed-candle evidence",
            "continuation does not estimate executable counterfactual PnL",
            "context groups cannot alter the configured maximum-hold policy",
        ],
    }


def _maximum_hold_summary(
    trades: Sequence[Record], horizons: Sequence[int]
) -> dict[str, object]:
    timer_trades = [trade for trade in trades if _exit_reason(trade) in _TIMER_REASONS]
    grouped: dict[str, list[Record]] = {context: [] for context in _TIMER_CONTEXTS}
    for trade in timer_trades:
        assessment = mapping(
            trade.get("exit_regime_assessment"), "exit regime assessment"
        )
        context = text(assessment.get("maximum_hold_context"), "maximum-hold context")
        if context not in grouped:
            raise ValueError(f"unsupported maximum-hold context: {context}")
        grouped[context].append(trade)
    return {
        "timer_exits": len(timer_trades),
        "non_timer_exits": len(trades) - len(timer_trades),
        "contexts": {
            context: _trade_summary(grouped[context], horizons)
            for context in _TIMER_CONTEXTS
        },
    }


def _provider_symbol_summaries(
    trades: Sequence[Record], horizons: Sequence[int]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[Record]] = {}
    for trade in trades:
        key = (
            text(trade.get("strategy_id"), "timer-journal strategy"),
            text(trade.get("symbol"), "timer-journal symbol"),
        )
        grouped.setdefault(key, []).append(trade)
    return [
        {
            "strategy_id": strategy,
            "symbol": symbol,
            **_maximum_hold_summary(values, horizons),
        }
        for (strategy, symbol), values in sorted(grouped.items())
    ]


def _exit_reason(trade: Record) -> str:
    value = trade.get("exit_reason")
    return value.strip() if isinstance(value, str) and value.strip() else "unreported"


def _trade_summary(
    trades: Sequence[Record], horizons: Sequence[int]
) -> dict[str, object]:
    pnls = [number(trade.get("net_pnl_usd"), "trade net PnL") for trade in trades]
    return {
        "closed_trades": len(trades),
        "wins": sum(value > 0.0 for value in pnls),
        "losses": sum(value < 0.0 for value in pnls),
        "net_pnl_usd": sum(pnls),
        "horizons": {
            str(horizon): _exit_horizon_counts(trades, horizon) for horizon in horizons
        },
    }


def _exit_horizon_counts(trades: Sequence[Record], horizon: int) -> dict[str, int]:
    counts = {
        "resolved": 0,
        "continued_original_direction": 0,
        "reversed_against_original_direction": 0,
        "unchanged": 0,
        "censored": 0,
        "missing_data": 0,
    }
    for trade in trades:
        paths = mapping(trade.get("post_exit_path"), "post-exit paths")
        path = mapping(paths.get(str(horizon)), "post-exit horizon")
        status = text(path.get("status"), "post-exit path status")
        _count_path(counts, path, status)
    return counts


def _count_path(counts: dict[str, int], path: Record, status: str) -> None:
    if status == "resolved":
        counts["resolved"] += 1
        interpretation = text(path.get("interpretation"), "path interpretation")
        if interpretation not in counts:
            raise ValueError("unsupported post-exit path interpretation")
        counts[interpretation] += 1
    elif status in {"censored", "missing_data"}:
        counts[status] += 1
    else:
        raise ValueError("unsupported post-exit path status")


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }
