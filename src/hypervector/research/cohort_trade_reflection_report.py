"""Assemble bounded report-only evidence for resolved cohort trades."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_exit_controller_attribution import (
    build_exit_controller_attribution,
)
from hypervector.research.cohort_live_audit_values import mapping
from hypervector.research.cohort_repeatability_evidence import (
    build_repeatability_evidence,
)
from hypervector.research.cohort_trade_performance import (
    build_all_time_trade_performance,
    build_trade_performance,
)
from hypervector.research.cohort_trade_reflection_contract import (
    trade_reflection_contract,
    trade_reflection_limitations,
)
from hypervector.research.cohort_trade_reflection_summary import (
    build_exit_reason_summary,
    build_maximum_hold_context_journal,
)

Record = Mapping[str, object]
ALL_TIME_REFLECTION_HISTORY_SCHEMA_VERSION = 1


def build_all_time_reflection_report(
    trades: Sequence[Record], horizons: Sequence[int]
) -> dict[str, object]:
    """Build mixed-profile live history with report-only diagnostic summaries."""
    return {
        "history_schema_version": ALL_TIME_REFLECTION_HISTORY_SCHEMA_VERSION,
        "scope": "all_live_history",
        "closed_trades": len(trades),
        "performance": build_all_time_trade_performance(trades),
        "maximum_hold_context_journal": build_maximum_hold_context_journal(
            trades, horizons
        ),
        "trades": trades,
        "limitations": [
            "all-time live history may combine materially different strategy profiles",
            "lifecycle context remains point-in-time but is not policy-comparable",
            "all-time summaries are descriptive and have no execution authority",
        ],
    }


def build_reflection_report(
    trades: Sequence[Record],
    horizons: Sequence[int],
    entry_followthrough_horizons: Sequence[int],
    current_profile_fingerprint: str,
    current_run_id: str,
) -> dict[str, object]:
    """Build closed trades with explicit run, profile, and archive scopes."""
    return {
        "schema_version": 1,
        "mode": "cohort_trade_reflections",
        "contract": trade_reflection_contract(),
        "scope": "compatible_profile_history",
        "horizons_minutes": list(horizons),
        "entry_followthrough_horizons_minutes": list(entry_followthrough_horizons),
        "closed_trades": len(trades),
        "context_coverage": _context_coverage(trades),
        "by_exit_reason": build_exit_reason_summary(trades, horizons),
        "maximum_hold_context_journal": build_maximum_hold_context_journal(
            trades, horizons
        ),
        "exit_controller_attribution": build_exit_controller_attribution(trades),
        "repeatability": build_repeatability_evidence(trades),
        "performance": build_trade_performance(
            trades,
            current_profile_fingerprint=current_profile_fingerprint,
            current_run_id=current_run_id,
        ),
        "trades": trades,
        "limitations": trade_reflection_limitations(),
    }


def _context_coverage(trades: Sequence[Record]) -> dict[str, object]:
    locations = {
        "entry_signal_provider": ("entry_context", "signal_provider"),
        "entry_canonical_regime": ("entry_context", "canonical_regime"),
        "exit_signal_provider": ("exit_context", "signal_provider"),
        "exit_canonical_regime": ("exit_context", "canonical_regime"),
    }
    observed = {
        label: sum(_context_observed(trade, group, item) for trade in trades)
        for label, (group, item) in locations.items()
    }
    missing = {label: len(trades) - count for label, count in observed.items()}
    return {
        "complete": all(count == 0 for count in missing.values()),
        "closed_trades": len(trades),
        "observed": observed,
        "missing": missing,
    }


def _context_observed(trade: Record, group: str, item: str) -> bool:
    context = mapping(trade.get(group), group)
    values = mapping(context.get(item), item)
    return values.get("status") == "observed"
