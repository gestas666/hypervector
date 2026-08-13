"""Frozen report-only observer for aligned zero-opposition timer exits."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from hypervector.research.cohort_exit_extension_projection import (
    project_incremental_gross_pnl,
)
from hypervector.research.cohort_live_audit_values import mapping, number, text

Record = Mapping[str, object]
_TIMER_REASONS = frozenset({"maximum_hold", "maximum_hold_seconds"})
_OPPOSITION_MODE = "causal_regime_opposition_persistence_v1"


def build_aligned_timer_extension_observer(
    trades: Sequence[Record], *, horizon_minutes: int = 5
) -> dict[str, object]:
    """Measure a five-minute extension without granting execution authority."""
    if horizon_minutes <= 0:
        raise ValueError("aligned timer extension horizon must be positive")
    timer_trades = [trade for trade in trades if _is_timer_exit(trade)]
    reasons = [_eligibility_reason(trade) for trade in timer_trades]
    observations = [
        _observation(trade, horizon_minutes)
        for trade, reason in zip(timer_trades, reasons, strict=True)
        if reason == "eligible"
    ]
    return {
        "schema_version": 1,
        "mode": "aligned_zero_opposition_timer_extension_observer_v1",
        "contract": _contract(),
        "policy": {
            "horizon_minutes": horizon_minutes,
            "requires_15m_context_alignment": True,
            "requires_complete_zero_opposition": True,
            "retains_protective_stop": True,
        },
        "decisions": _decision_summary(timer_trades, reasons),
        "horizon": _horizon_summary(observations),
        "latest_observations": observations[-20:],
        "limitations": _limitations(),
    }


def _eligibility_reason(trade: Record) -> str:
    side = text(trade.get("side"), "aligned extension side")
    if side not in {"long", "short"}:
        raise ValueError("aligned extension side must be long or short")
    context = _nested_mapping(trade, "exit_context", "signal_provider")
    context_15m = _optional_text(context.get("context_15m"))
    if context_15m is None:
        return "context_15m_unavailable"
    expected = "TREND_UP" if side == "long" else "TREND_DOWN"
    if context_15m != expected:
        return "context_15m_not_aligned"
    opposition = _optional_mapping(trade.get("regime_opposition_episode"))
    if opposition is None or opposition.get("mode") != _OPPOSITION_MODE:
        return "opposition_evidence_unavailable"
    if _count(opposition, "completed_decisions") == 0:
        return "opposition_evidence_unavailable"
    if (
        _count(opposition, "coverage_gap_decisions") > 0
        or _count(opposition, "unavailable_decisions") > 0
    ):
        return "opposition_coverage_incomplete"
    if (
        _count(opposition, "opposed_decisions") > 0
        or _count(opposition, "maximum_consecutive_opposed") > 0
    ):
        return "opposition_observed"
    if trade.get("protective_stop") is None:
        return "protection_unavailable"
    return "eligible"


def _observation(trade: Record, horizon: int) -> dict[str, object]:
    path = mapping(
        mapping(trade.get("post_exit_path"), "post-exit paths").get(str(horizon)),
        "aligned extension path",
    )
    status = text(path.get("status"), "aligned extension path status")
    result: dict[str, object] = {
        "lifecycle_id": text(trade.get("lifecycle_id"), "lifecycle identity"),
        "strategy_id": text(trade.get("strategy_id"), "strategy identity"),
        "symbol": text(trade.get("symbol"), "trade symbol"),
        "side": text(trade.get("side"), "trade side"),
        "status": status,
        **_opposition_counts(trade),
    }
    if status in {"censored", "missing_data"}:
        return result
    if status != "resolved":
        raise ValueError(f"unsupported aligned extension path status: {status}")
    projection = project_incremental_gross_pnl(trade, path)
    if projection is None:
        raise ValueError(
            "eligible aligned extension is missing protective-stop evidence"
        )
    projected, stop_hit = projection
    return {
        **result,
        "directional_close_return_bps": number(
            path.get("directional_close_return_bps"), "directional close return"
        ),
        "adverse_excursion_bps": _optional_number(path.get("adverse_excursion_bps")),
        "favorable_excursion_bps": _optional_number(
            path.get("favorable_excursion_bps")
        ),
        "protective_stop_hit": stop_hit,
        "incremental_gross_pnl_usd": projected,
    }


def _horizon_summary(observations: Sequence[Record]) -> dict[str, object]:
    counts = Counter(str(row.get("status")) for row in observations)
    resolved = [row for row in observations if row.get("status") == "resolved"]
    pnls = [
        number(row.get("incremental_gross_pnl_usd"), "incremental gross PnL")
        for row in resolved
    ]
    return {
        "eligible_extensions": len(observations),
        "resolved": len(resolved),
        "positive": sum(value > 0.0 for value in pnls),
        "negative": sum(value < 0.0 for value in pnls),
        "unchanged": sum(value == 0.0 for value in pnls),
        "protective_stop_hits": sum(
            row.get("protective_stop_hit") is True for row in resolved
        ),
        "censored": counts["censored"],
        "missing_data": counts["missing_data"],
        "incremental_gross_pnl_usd": sum(pnls),
    }


def _decision_summary(
    timer_trades: Sequence[Record], reasons: Sequence[str]
) -> dict[str, object]:
    counts = Counter(reasons)
    return {
        "timer_exits": len(timer_trades),
        "eligible": counts["eligible"],
        "ineligible": len(timer_trades) - counts["eligible"],
        "by_reason": dict(sorted(counts.items())),
    }


def _opposition_counts(trade: Record) -> dict[str, int]:
    opposition = mapping(
        trade.get("regime_opposition_episode"), "regime opposition episode"
    )
    return {
        "completed_decisions": _count(opposition, "completed_decisions"),
        "opposed_decisions": _count(opposition, "opposed_decisions"),
        "maximum_consecutive_opposed": _count(
            opposition, "maximum_consecutive_opposed"
        ),
    }


def _nested_mapping(trade: Record, group: str, item: str) -> Record:
    outer = _optional_mapping(trade.get(group))
    return {} if outer is None else _optional_mapping(outer.get(item)) or {}


def _optional_mapping(value: object) -> Record | None:
    return value if isinstance(value, Mapping) else None


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_number(value: object) -> float | None:
    return (
        float(value)
        if isinstance(value, int | float) and not isinstance(value, bool)
        else None
    )


def _count(values: Record, key: str) -> int:
    value = values.get(key, 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"aligned extension {key} must be a non-negative integer")
    return value


def _is_timer_exit(trade: Record) -> bool:
    value = trade.get("exit_reason")
    return isinstance(value, str) and value.strip() in _TIMER_REASONS


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "performance_gate": False,
        "balance_gate": False,
    }


def _limitations() -> list[str]:
    return [
        "the extension is a completed-candle path rather than a submitted order",
        "incremental PnL is gross of later fees, funding, and execution slippage",
        "the original protective stop is retained but intrabar queue behavior is unknown",
        "the observer cannot retain, close, resize, route, or submit a live position",
    ]
