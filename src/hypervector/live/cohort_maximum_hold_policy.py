"""Bounded maximum-hold decisions from causal completed-bar regime evidence."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.canonical_regime_telemetry import latest_canonical_evaluation
from hypervector.live.multi_asset_live_runner_support import entry_provider_strategy_id
from hypervector.live.multi_asset_signal_source import ProviderEvaluation

EvaluationKey = tuple[str, str]
EvaluationMap = Mapping[EvaluationKey, ProviderEvaluation]

_STANCE_THRESHOLD = 0.5


def update_latest_evaluations(
    prior: EvaluationMap,
    observed: tuple[ProviderEvaluation, ...],
) -> dict[EvaluationKey, ProviderEvaluation]:
    """Retain the newest completed-bar evaluation for every provider-symbol."""
    latest = dict(prior)
    for evaluation in observed:
        key = (evaluation.strategy_id, evaluation.symbol)
        current = latest.get(key)
        if current is None or evaluation.decision_time_ms > current.decision_time_ms:
            latest[key] = evaluation
    return latest


def maximum_hold_evaluations(
    plan: BoundExecutionPlan,
    symbol: str,
    evaluations: EvaluationMap,
) -> tuple[ProviderEvaluation | None, ProviderEvaluation | None]:
    """Return the plan provider and canonical context for one open lifecycle."""
    provider = entry_provider_strategy_id(plan.strategy_id)
    return (
        evaluations.get((provider, symbol)),
        latest_canonical_evaluation(evaluations.values(), symbol),
    )


def maximum_hold_decision_payload(
    *,
    plan: BoundExecutionPlan,
    symbol: str,
    entry_oid: int,
    side: str,
    opened_at_ms: int,
    observed_ms: int,
    evaluations: EvaluationMap,
) -> dict[str, object] | None:
    """Build one causal soft-deadline decision for durable journaling."""
    elapsed_ms = observed_ms - opened_at_ms
    if elapsed_ms < plan.maximum_hold_seconds * 1_000:
        return None
    provider, canonical = maximum_hold_evaluations(plan, symbol, evaluations)
    score = _structure_alignment(side, provider, canonical)
    reason = maximum_hold_exit_reason(plan, elapsed_ms, side, provider, canonical)
    hard = plan.hard_maximum_hold_seconds
    return {
        "decision_id": f"{symbol}:{entry_oid}:soft_maximum_hold",
        "decision_stage": "soft",
        "lifecycle_id": f"{symbol}:{entry_oid}",
        "symbol": symbol,
        "strategy_id": plan.strategy_id,
        "side": side,
        "decision_time_ms": observed_ms,
        "opened_at_ms": opened_at_ms,
        "elapsed_ms": elapsed_ms,
        "soft_deadline_timestamp_ms": opened_at_ms + plan.maximum_hold_seconds * 1_000,
        "hard_deadline_timestamp_ms": (
            opened_at_ms + hard * 1_000 if hard is not None else None
        ),
        "outcome": "extend" if reason is None else "exit",
        "exit_reason": reason,
        "structure_alignment_score": score,
        "structure_alignment_threshold": _STANCE_THRESHOLD,
        "provider_evaluation": provider.as_payload() if provider else None,
        "canonical_evaluation": canonical.as_payload() if canonical else None,
    }


def maximum_hold_terminal_decision_payload(
    *,
    plan: BoundExecutionPlan,
    symbol: str,
    entry_oid: int,
    side: str,
    opened_at_ms: int,
    observed_ms: int,
    evaluations: EvaluationMap,
    soft_decision_id: str,
) -> dict[str, object]:
    """Build the immutable exit decision that terminates an extension."""
    payload = maximum_hold_decision_payload(
        plan=plan,
        symbol=symbol,
        entry_oid=entry_oid,
        side=side,
        opened_at_ms=opened_at_ms,
        observed_ms=observed_ms,
        evaluations=evaluations,
    )
    if payload is None or payload.get("outcome") != "exit":
        raise ValueError("terminal maximum-hold decision requires an exit outcome")
    soft_deadline = opened_at_ms + plan.maximum_hold_seconds * 1_000
    return payload | {
        "decision_id": f"{symbol}:{entry_oid}:terminal_maximum_hold",
        "decision_stage": "terminal",
        "trigger_decision_id": soft_decision_id,
        "extension_duration_ms": observed_ms - soft_deadline,
    }


def resolve_maximum_hold_exit_reason(
    *,
    plan: BoundExecutionPlan | None,
    symbol: str,
    side: str,
    elapsed_ms: int,
    fallback_hold_ms: int,
    evaluations: EvaluationMap,
) -> str | None:
    """Resolve a persisted provider policy or a legacy asset timer."""
    if plan is None:
        return "maximum_hold_seconds" if elapsed_ms >= fallback_hold_ms else None
    provider, canonical = maximum_hold_evaluations(plan, symbol, evaluations)
    return maximum_hold_exit_reason(plan, elapsed_ms, side, provider, canonical)


def maximum_hold_exit_reason(
    plan: BoundExecutionPlan,
    elapsed_ms: int,
    side: str,
    provider: ProviderEvaluation | None,
    canonical: ProviderEvaluation | None,
) -> str | None:
    """Resolve a soft exit, bounded extension, or unconditional hard exit."""
    if (
        isinstance(elapsed_ms, bool)
        or not isinstance(elapsed_ms, int)
        or elapsed_ms < 0
    ):
        raise ValueError("elapsed_ms must be a nonnegative integer")
    if side not in {"long", "short"}:
        raise ValueError("maximum-hold side must be long or short")
    if elapsed_ms < plan.maximum_hold_seconds * 1_000:
        return None
    if plan.maximum_hold_policy == "fixed":
        return "maximum_hold_seconds"
    hard = plan.hard_maximum_hold_seconds
    if hard is None:
        raise ValueError("regime-supported extension lacks a hard maximum hold")
    if elapsed_ms >= hard * 1_000:
        return "hard_maximum_hold_seconds"
    score = _structure_alignment(side, provider, canonical)
    return (
        None
        if score is not None and score >= _STANCE_THRESHOLD
        else "maximum_hold_seconds"
    )


def _structure_alignment(
    side: str,
    provider: ProviderEvaluation | None,
    canonical: ProviderEvaluation | None,
) -> float | None:
    side_sign = 1 if side == "long" else -1
    weighted, observed = 0.0, 0.0
    evidence = (
        (provider, "primary_regime", 3.0),
        (canonical, "primary_regime", 3.0),
        (canonical, "state_1m", 1.0),
        (canonical, "state_5m", 3.0),
        (canonical, "context_15m", 2.0),
    )
    for evaluation, field, weight in evidence:
        direction = _evaluation_direction(evaluation, field)
        if direction is None:
            continue
        weighted += direction * side_sign * weight
        observed += weight
    return None if observed == 0.0 else weighted / observed


def _evaluation_direction(
    evaluation: ProviderEvaluation | None,
    field: str,
) -> int | None:
    if evaluation is None:
        return None
    state = getattr(evaluation, field)
    if state is None:
        return None
    if state == "TREND_UP":
        return 1
    if state == "TREND_DOWN":
        return -1
    if state in {"RANGE", "TRANSITION"}:
        return 0
    if state == "UNKNOWN":
        return None
    if state == "BREAKOUT":
        structural = evaluation.readiness.metrics.get("structural_direction")
        return 1 if structural == "long" else -1 if structural == "short" else 0
    raise ValueError(f"unsupported maximum-hold regime state: {state}")
