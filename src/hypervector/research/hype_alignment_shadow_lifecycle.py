"""Exact-depth report-only lifecycle evidence for V58 HYPE alignment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
)
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.hype_compression_alignment_provider import (
    HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
)
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    StrategyProviderConfig,
)
from hypervector.research.cohort_eligible_exact_depth_forward import (
    build_eligible_exact_depth_forward_report,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
)
from hypervector.research.cohort_exact_depth_books import (
    book_time,
    first_book,
    latest_book_time,
    validated_books,
)
from hypervector.research.cohort_live_audit_values import (
    event_rows,
    mapping,
    nonnegative_int,
    number,
    object_list,
    payload,
    text,
    timestamp,
)
from hypervector.research.cohort_observer_exact_books import (
    extract_observer_asset_books,
    select_compatible_report_only_observer_runs,
)
from hypervector.research.cohort_prospective_records import (
    prospective_observer_records,
)
from hypervector.research.cohort_regime_assessment import build_regime_assessment
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)
from hypervector.research.v58_hype_rejected_onset_context import (
    build_hype_rejected_onset_context,
)

Record = Mapping[str, object]
_SYMBOL = "HYPE"
_CANDIDATE = "hype_alignment_v58_exact_depth_shadow_v1"
_MAXIMUM_BOOK_DELAY_MS = 60_000
_SUPPORT_THRESHOLD = 0.5
_ESTIMATED_ROUND_TRIP_FRICTION_BPS = 13.0


@dataclass(frozen=True)
class _Context:
    strategy_id: str
    decision_time_ms: int
    available_time_ms: int
    values: Record


def build_hype_alignment_shadow_resolution(
    records: Sequence[Record],
    *,
    config: MultiAssetLiveConfig,
    run_id: str,
    prospective_start_ms: int,
    funding_evidence: EligiblePolicyFundingEvidence | None,
    taker_fee_rate: float,
) -> dict[str, object]:
    """Replay frozen V58 HYPE signals without execution authority."""
    selected, identities = select_compatible_report_only_observer_runs(records, run_id)
    scoped = prospective_observer_records(
        selected,
        prospective_start_ms,
        label="HYPE",
    )
    provider, asset = _route(config)
    execution = provider.execution_for(_SYMBOL)
    compatible = tuple(text(row.get("run_id"), "observer run id") for row in identities)
    extracted = extract_observer_asset_books(scoped, (_SYMBOL,))[_SYMBOL]
    books = validated_books(extracted, symbol=_SYMBOL, run_ids=compatible)
    candidates, _, _ = evaluation_candidates(scoped)
    entries = _entries(candidates, run_id, prospective_start_ms)
    policy_exits = _policy_exits(scoped, entries, books, execution)
    policy = _policy_report(config, run_id, compatible, asset, execution, policy_exits)
    report = build_eligible_exact_depth_forward_report(
        scoped,
        books,
        policy_report=policy,
        funding_evidence=funding_evidence,
        taker_fee_rate=taker_fee_rate,
        maximum_entry_delay_ms=_MAXIMUM_BOOK_DELAY_MS,
        maximum_exit_delay_ms=_MAXIMUM_BOOK_DELAY_MS,
    )
    report["identity"] = _identity(config, run_id, compatible, prospective_start_ms)
    report["timer_evidence"] = {"policy_exits": policy_exits}
    report["rejected_onset_diagnostic"] = build_hype_rejected_onset_context(
        scoped,
        strategy_id=HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
        symbol=_SYMBOL,
        prospective_start_ms=prospective_start_ms,
        estimated_round_trip_friction_bps=_ESTIMATED_ROUND_TRIP_FRICTION_BPS,
    )
    return report


def _route(
    config: MultiAssetLiveConfig,
) -> tuple[StrategyProviderConfig, AssetLiveConfig]:
    providers = [
        row
        for row in config.providers
        if row.strategy_id == HYPE_COMPRESSION_ALIGNMENT_STRATEGY
        and _SYMBOL in row.symbols
    ]
    assets = [row for row in config.assets if row.symbol == _SYMBOL]
    if len(providers) != 1 or len(assets) != 1:
        raise ValueError("V58 HYPE alignment route must be unique")
    provider, asset = providers[0], assets[0]
    execution = provider.execution_for(_SYMBOL)
    valid = (
        provider.symbols == (_SYMBOL,)
        and provider.sides == frozenset({"long", "short"})
        and provider.execution_symbols == (_SYMBOL,)
        and provider.position_policy == "enter_and_close"
        and provider.timeframe == "1m"
        and provider.maximum_entry_delay_seconds == 60
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 80.0
        and execution.target_policy == "none"
        and execution.maximum_hold_seconds == 28_800
        and execution.maximum_hold_policy == "extend_while_regime_supported"
        and execution.hard_maximum_hold_seconds == 86_400
        and execution.maximum_hold_evidence_maximum_age_seconds == 60
        and execution.provider_recipe_exit_policy == "ignore"
        and execution.profit_lock_policy == "none"
    )
    if not valid:
        raise ValueError("V58 HYPE alignment execution contract is unsupported")
    return provider, asset


def _entries(
    candidates: Sequence[SignalCandidate], run_id: str, prospective_start_ms: int
) -> tuple[SignalCandidate, ...]:
    return tuple(
        row
        for row in candidates
        if row.source_run_id == run_id
        and row.decision_time_ms >= prospective_start_ms
        and row.strategy_id == HYPE_COMPRESSION_ALIGNMENT_STRATEGY
        and row.symbol == _SYMBOL
        and row.eligible
    )


def _policy_exits(
    records: Sequence[Record],
    entries: Sequence[SignalCandidate],
    books: Sequence[Record],
    execution: ProviderExecutionContract,
) -> list[dict[str, object]]:
    soft_seconds = execution.maximum_hold_seconds
    if execution.hard_maximum_hold_seconds is None:
        raise ValueError("V58 HYPE hard maximum hold must be configured")
    hard_seconds = execution.hard_maximum_hold_seconds
    if execution.maximum_hold_evidence_maximum_age_seconds is None:
        raise ValueError("V58 HYPE maximum-hold evidence age must be configured")
    maximum_age = execution.maximum_hold_evidence_maximum_age_seconds
    contexts = _contexts(records)
    cycles = _routing_cycles(records)
    output: list[dict[str, object]] = []
    for entry in entries:
        book = first_book(books, entry.available_time_ms, _MAXIMUM_BOOK_DELAY_MS)
        if book is None:
            continue
        selected = _timer_exit(
            entry,
            book_time(book),
            latest_book_time(books),
            contexts,
            cycles,
            soft_seconds,
            hard_seconds,
            maximum_age,
        )
        if selected is not None:
            output.append(selected)
    return output


def _timer_exit(
    entry: SignalCandidate,
    entry_time_ms: int,
    latest_book_ms: int,
    contexts: Sequence[_Context],
    cycles: Sequence[int],
    soft_seconds: int,
    hard_seconds: int,
    maximum_age_seconds: int,
) -> dict[str, object] | None:
    soft = entry_time_ms + soft_seconds * 1_000
    hard = entry_time_ms + hard_seconds * 1_000
    candidates = [value for value in cycles if soft <= value <= hard]
    soft_decision: dict[str, object] | None = None
    if not candidates and latest_book_ms >= soft:
        evidence = _missing_cycle_evidence(soft, maximum_age_seconds)
        return _policy_exit(entry, soft, "maximum_hold_evidence_missing", evidence)
    for cycle in candidates:
        result = _timer_decision(entry, cycle, contexts, maximum_age_seconds)
        if soft_decision is None:
            soft_decision = _soft_decision(cycle, result)
        if result["reason"] is not None:
            evidence = {**result, "soft_decision": soft_decision}
            return _policy_exit(entry, cycle, str(result["reason"]), evidence)
    return None


def _timer_decision(
    entry: SignalCandidate,
    cycle_ms: int,
    contexts: Sequence[_Context],
    maximum_age_seconds: int,
) -> dict[str, object]:
    provider = _latest_context(contexts, HYPE_COMPRESSION_ALIGNMENT_STRATEGY, cycle_ms)
    canonical = _latest_context(contexts, CANONICAL_REGIME_TELEMETRY_STRATEGY, cycle_ms)
    ages = _evidence_ages(provider, canonical, cycle_ms)
    reason = _evidence_failure(provider, canonical, ages, maximum_age_seconds)
    score: float | None = None
    if reason is None:
        score = _structure_score(entry.side or "", provider, canonical)
        if score is None or score < _SUPPORT_THRESHOLD:
            reason = "maximum_hold_seconds"
    return {
        "reason": reason,
        "decision_time_ms": cycle_ms,
        "provider_decision_time_ms": provider.decision_time_ms if provider else None,
        "canonical_decision_time_ms": canonical.decision_time_ms if canonical else None,
        "provider_evidence_age_ms": ages[0],
        "canonical_evidence_age_ms": ages[1],
        "maximum_hold_evidence_maximum_age_ms": maximum_age_seconds * 1_000,
        "structure_alignment_score": score,
        "structure_alignment_threshold": _SUPPORT_THRESHOLD,
    }


def _contexts(records: Sequence[Record]) -> tuple[_Context, ...]:
    selected: dict[tuple[str, int], _Context] = {}
    for event_type in ("intent_routing", "canonical_regime_evaluations"):
        for row in event_rows(records, event_type):
            available = int(timestamp(row).timestamp() * 1_000)
            for values in object_list(payload(row), "evaluations", required=False):
                strategy = values.get("strategy_id")
                if (
                    strategy
                    not in {
                        HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
                        CANONICAL_REGIME_TELEMETRY_STRATEGY,
                    }
                    or values.get("symbol") != _SYMBOL
                ):
                    continue
                context = _context(values, available)
                key = (context.strategy_id, context.decision_time_ms)
                prior = selected.get(key)
                if prior is not None and prior != context:
                    raise ValueError("conflicting duplicate HYPE timer context")
                selected[key] = context
    return tuple(sorted(selected.values(), key=lambda row: row.available_time_ms))


def _context(values: Record, available_ms: int) -> _Context:
    strategy = text(values.get("strategy_id"), "timer context strategy")
    decision = nonnegative_int(values.get("decision_time_ms"), "timer decision")
    if available_ms < decision:
        raise ValueError("HYPE timer context predates its decision")
    number(values.get("reference_price"), "timer reference price")
    mapping(values.get("readiness"), "timer readiness")
    return _Context(strategy, decision, available_ms, values)


def _routing_cycles(records: Sequence[Record]) -> tuple[int, ...]:
    values = tuple(
        int(timestamp(row).timestamp() * 1_000)
        for row in event_rows(records, "intent_routing")
    )
    return tuple(sorted(set(values)))


def _latest_context(
    contexts: Sequence[_Context], strategy_id: str, cycle_ms: int
) -> _Context | None:
    eligible = (
        row
        for row in contexts
        if row.strategy_id == strategy_id
        and row.available_time_ms <= cycle_ms
        and row.decision_time_ms <= cycle_ms
    )
    return max(eligible, key=lambda row: row.decision_time_ms, default=None)


def _evidence_ages(
    provider: _Context | None, canonical: _Context | None, cycle_ms: int
) -> tuple[int | None, int | None]:
    return (
        None if provider is None else cycle_ms - provider.decision_time_ms,
        None if canonical is None else cycle_ms - canonical.decision_time_ms,
    )


def _evidence_failure(
    provider: _Context | None,
    canonical: _Context | None,
    ages: tuple[int | None, int | None],
    maximum_age_seconds: int,
) -> str | None:
    if provider is None or canonical is None:
        return "maximum_hold_evidence_missing"
    if any(value is not None and value < 0 for value in ages):
        return "maximum_hold_evidence_future"
    maximum = maximum_age_seconds * 1_000
    if any(value is not None and value > maximum for value in ages):
        return "maximum_hold_evidence_stale"
    return None


def _structure_score(
    side: str, provider: _Context | None, canonical: _Context | None
) -> float | None:
    assessment = build_regime_assessment(
        side,
        {
            "signal_provider": _regime_context(provider),
            "canonical_regime": _regime_context(canonical),
        },
    )
    value = assessment["structure_support_score"]
    return float(value) if isinstance(value, (int, float)) else None


def _regime_context(context: _Context | None) -> dict[str, object]:
    if context is None:
        return {"status": "unavailable"}
    values = context.values
    return {
        "status": "observed",
        "side": values.get("side"),
        "primary_regime": values.get("primary_regime"),
        "state_1m": values.get("state_1m"),
        "state_5m": values.get("state_5m"),
        "context_15m": values.get("context_15m"),
        "confidence": values.get("confidence"),
        "readiness": values.get("readiness"),
    }


def _soft_decision(cycle_ms: int, result: Record) -> dict[str, object]:
    return {
        "decision_time_ms": cycle_ms,
        "outcome": "extend" if result.get("reason") is None else "exit",
        "structure_alignment_score": result.get("structure_alignment_score"),
        "structure_alignment_threshold": _SUPPORT_THRESHOLD,
    }


def _missing_cycle_evidence(cycle_ms: int, maximum_age: int) -> dict[str, object]:
    return {
        "reason": "maximum_hold_evidence_missing",
        "decision_time_ms": cycle_ms,
        "provider_decision_time_ms": None,
        "canonical_decision_time_ms": None,
        "provider_evidence_age_ms": None,
        "canonical_evidence_age_ms": None,
        "maximum_hold_evidence_maximum_age_ms": maximum_age * 1_000,
        "structure_alignment_score": None,
        "structure_alignment_threshold": _SUPPORT_THRESHOLD,
        "soft_decision": {"decision_time_ms": cycle_ms, "outcome": "exit"},
        "decision_source": "missing_route_cycle_fail_closed_proxy",
    }


def _policy_exit(
    entry: SignalCandidate, available_ms: int, reason: str, evidence: Record
) -> dict[str, object]:
    return {
        "opening_decision_time_ms": entry.decision_time_ms,
        "available_time_ms": available_ms,
        "reason": reason,
        "evidence": dict(evidence),
    }


def _policy_report(
    config: MultiAssetLiveConfig,
    run_id: str,
    compatible: Sequence[str],
    asset: AssetLiveConfig,
    execution: ProviderExecutionContract,
    policy_exits: Sequence[Record],
) -> dict[str, object]:
    return {
        "mode": "cohort_config_bound_eligible_policy_forward_report",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
            "source_strategy_id": HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
            "candidate_strategy_id": _CANDIDATE,
            "symbol": _SYMBOL,
            "source_run_id": run_id,
            "profile_fingerprint": config.profile_fingerprint,
            "compatible_run_ids": list(compatible),
            "stop_bps": execution.stop_bps,
            "notional_usd": asset.max_notional_usd,
            "soft_maximum_hold_minutes": 480,
            "maximum_hold_minutes": 1_440,
            "maximum_hold_evidence_maximum_age_seconds": 60,
            "close_on_eligible_opposite_signal": True,
            "same_cycle_reversal": False,
            "policy_exits": list(policy_exits),
        },
    }


def _identity(
    config: MultiAssetLiveConfig,
    run_id: str,
    compatible: Sequence[str],
    prospective_start_ms: int,
) -> dict[str, object]:
    return {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "source_run_id": run_id,
        "compatible_run_ids": list(compatible),
        "strategy_id": HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
        "symbol": _SYMBOL,
        "prospective_start_ms": prospective_start_ms,
    }
