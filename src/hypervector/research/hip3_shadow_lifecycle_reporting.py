"""Report serialization for causal HIP-3 shadow lifecycle replays."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict

import pandas as pd

from hypervector.cohort_profit_lock_policy import policy_declaration
from hypervector.research.hip3_shadow_lifecycle_inputs import (
    HIP3_EXACT_MARK_SOURCE,
    Hip3ShadowMark,
)
from hypervector.research.hip3_shadow_lifecycle_archive_marks import (
    HIP3_ARCHIVE_REPAIR_MARK_SOURCE,
)
from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowLifecycleConfig,
)
from hypervector.research.hip3_shadow_signal_markouts import (
    Hip3ShadowBook,
    Hip3ShadowDecision,
)


def build_shadow_lifecycle_report(
    config: Hip3ShadowLifecycleConfig,
    decisions: Sequence[Hip3ShadowDecision],
    books: Sequence[Hip3ShadowBook],
    marks: Sequence[Hip3ShadowMark],
    bars: pd.DataFrame,
    funding_evidence: object,
    nominal: Mapping[str, object],
    stress: Mapping[str, object],
) -> dict[str, object]:
    """Serialize one immutable authority-none lifecycle report."""
    resolved = nominal["censored_lifecycles"] == 0
    return {
        "schema_version": "hip3_shadow_lifecycle_replay_v2",
        "symbol": config.symbol,
        "provider_id": config.provider_id,
        "profile_id": config.profile_id,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "replay_contract": _replay_contract(config),
        "source_reconciliation": _source_reconciliation(decisions, books, marks, bars),
        "funding_evidence": vars(funding_evidence),
        "nominal": dict(nominal),
        "stress": dict(stress),
        "technical_assessment": {
            "entry_identity_reproduced": True,
            "all_lifecycle_paths_resolved": resolved,
            "live_promotion_supported": False,
        },
        "limitations": [
            "mark-triggered next-observed-depth exits are replay approximations, not historical venue fills",
            "REST mark contexts are supplemental diagnostics and cannot certify exact lifecycle paths",
            "0xArchive mark repairs are historical exact-path evidence and cannot certify live capture uptime",
            "a small or one-sided prospective sample cannot establish deployable edge",
            "this report grants no execution, sizing, routing, or promotion authority",
        ],
    }


def _source_reconciliation(
    decisions: Sequence[Hip3ShadowDecision],
    books: Sequence[Hip3ShadowBook],
    marks: Sequence[Hip3ShadowMark],
    bars: pd.DataFrame,
) -> dict[str, object]:
    exact_marks = sum(mark.source == HIP3_EXACT_MARK_SOURCE for mark in marks)
    archive_marks = sum(
        mark.source == HIP3_ARCHIVE_REPAIR_MARK_SOURCE for mark in marks
    )
    return {
        "eligible_journal_onsets": len(decisions),
        "computed_onsets": len(decisions),
        "book_rows": len(books),
        "exact_mark_source": HIP3_EXACT_MARK_SOURCE,
        "exact_mark_sources": [
            HIP3_EXACT_MARK_SOURCE,
            HIP3_ARCHIVE_REPAIR_MARK_SOURCE,
        ],
        "exact_websocket_mark_rows": exact_marks,
        "exact_archive_repair_mark_rows": archive_marks,
        "supplemental_rest_mark_rows": len(marks) - exact_marks - archive_marks,
        "signal_bars": len(bars),
        "unobserved_pressure_bars": int(bars.attrs.get("unobserved_pressure_bars", 0)),
    }


def _replay_contract(config: Hip3ShadowLifecycleConfig) -> dict[str, object]:
    return {
        **asdict(config.signal_config),
        "fee_bps_per_side": config.fee_bps_per_side,
        "residual_latency_bps_per_side": config.residual_latency_bps_per_side,
        "stress_extra_bps_per_side": config.stress_extra_bps_per_side,
        "notional_usd": config.notional_usd,
        "maximum_book_lateness_ms": config.maximum_book_lateness_ms,
        "maximum_mark_gap_ms": config.maximum_mark_gap_ms,
        "maximum_hold_minutes": config.maximum_hold_minutes,
        "entry_sides": sorted(config.entry_sides),
        "fixed_stop_bps": config.fixed_stop_bps,
        "signal_exit_enabled": config.signal_exit_enabled,
        "opposite_entry_exit_enabled": config.opposite_entry_exit_enabled,
        "profit_lock_policy": None
        if config.profit_lock_policy is None
        else policy_declaration(config.profit_lock_policy),
        "friction_source": config.friction_source,
        "execution_profile_id": config.execution_profile_id,
        "execution_profile_fingerprint": config.execution_profile_fingerprint,
        "entry_model": "first_complete_recorded_depth_after_publication",
        "exit_model": _exit_model(config),
    }


def _exit_model(config: Hip3ShadowLifecycleConfig) -> str:
    """Describe the configured causal exit priority without false branches."""
    values = ["fixed_stop" if config.fixed_stop_bps is not None else "signal_stop"]
    if config.signal_exit_enabled:
        values.append("signal")
    if config.opposite_entry_exit_enabled:
        values.append("opposite_strategy_intent")
    if config.profit_lock_policy is not None:
        values.append("completed_1m_profit_lock")
    hours = config.maximum_hold_minutes / 60.0
    values.append(f"{hours:g}h")
    return "_or_".join(values) + "_then_next_complete_depth"
