"""Disclose executable provider contention omitted by breakout path replay."""

from __future__ import annotations

from collections.abc import Sequence

from hypervector.research.cohort_breakout_policy_models import (
    BreakoutPolicyForwardSpec,
)
from hypervector.research.cohort_signal_candidates import SignalCandidate


def contention_summary(
    candidates: Sequence[SignalCandidate], spec: BreakoutPolicyForwardSpec
) -> dict[str, object]:
    """Count eligible non-breakout providers with staged execution authority."""
    count = sum(
        candidate.eligible
        and candidate.strategy_id
        in spec.competing_execution_providers_by_symbol.get(candidate.symbol, ())
        for candidate in candidates
    )
    return {
        "competing_executable_eligible_signals": count,
        "router_contention_status": "clear" if count == 0 else "not_modeled",
    }
