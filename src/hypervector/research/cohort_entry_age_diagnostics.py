"""Report-only entry-age evidence from exact cohort routing boundaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from hypervector.live.entry_submission_deadline import SUBMISSION_BOUNDARIES
from hypervector.research.cohort_live_audit_values import (
    nonnegative_int,
    object_list,
    payload,
    positive_int,
    text,
    text_list,
    timestamp,
)

Record = Mapping[str, object]
_OPERATOR_PREFIX = "operator_override:"
_READINESS_SEED_REASON = "pre_activation_readiness_seed"
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def build_entry_age_diagnostics(
    records: Sequence[Record],
    identity: Record,
) -> dict[str, object]:
    """Measure cutoff and routing-emission age without inferring submit time."""
    limits = _provider_limits(identity)
    aggregates = {route: _empty_route(limit) for route, limit in limits.items()}
    pairs = _paired_cycles(records)
    for routing, funding in pairs:
        _consume_cycle(routing, funding, limits, aggregates)
    routes = {route: _finalize_route(row) for route, row in aggregates.items()}
    submitted = sum(int(row["submitted_entries"]) for row in routes.values())
    stale = sum(int(row["stale_entries_withheld"]) for row in routes.values())
    late = sum(int(row["sdk_dispatches_over_limit"]) for row in routes.values())
    dispatch_checks = sum(int(row["sdk_dispatch_checks"]) for row in routes.values())
    enter_actions = sum(int(row["enter_actions"]) for row in routes.values())
    observed = submitted + stale > 0
    enforcement = dispatch_checks > 0 and dispatch_checks == enter_actions and late == 0
    return {
        "contract": _contract(),
        "paired_cycles": len(pairs),
        "evaluations": sum(int(row["evaluations"]) for row in routes.values()),
        "eligible_evaluations": sum(
            int(row["eligible_evaluations"]) for row in routes.values()
        ),
        "excluded_pre_activation_readiness_seeds": sum(
            int(row["excluded_pre_activation_readiness_seeds"])
            for row in routes.values()
        ),
        "enter_actions": enter_actions,
        "enter_actions_routing_emission_over_limit": sum(
            int(row["enter_actions_routing_emission_over_limit"])
            for row in routes.values()
        ),
        "submitted_entries": submitted,
        "sdk_dispatch_checks": dispatch_checks,
        "stale_entries_withheld": stale,
        "executed_late_entries_proven": late > 0,
        "submission_timestamp_observed": observed,
        "entry_submission_enforcement_observed": enforcement,
        "by_provider_symbol": routes,
        "limitations": _limitations(),
    }


def _consume_cycle(
    routing: Record,
    funding: Record,
    limits: Mapping[str, int],
    aggregates: dict[str, dict[str, object]],
) -> None:
    routing_payload = payload(routing)
    funding_payload = payload(funding)
    evaluations = object_list(routing_payload, "evaluations")
    actions = object_list(routing_payload, "actions")
    withheld = object_list(routing_payload, "withheld")
    cutoff_ms = nonnegative_int(
        funding_payload.get("provider_cutoff_time_ms"), "provider cutoff"
    )
    routing_ms = _timestamp_ms(routing)
    if routing_ms < cutoff_ms:
        raise ValueError("routing emission precedes provider cutoff")
    if nonnegative_int(funding_payload.get("action_count"), "action count") != len(
        actions
    ):
        raise ValueError("routing and funding action counts do not reconcile")
    eligible = _eligible_identities(evaluations, limits)
    for evaluation in evaluations:
        _consume_evaluation(evaluation, cutoff_ms, routing_ms, limits, aggregates)
    for action in actions:
        _consume_enter_action(action, routing_ms, limits, eligible, aggregates)
    for item in withheld:
        _consume_stale_withheld(item, limits, eligible, aggregates)


def _consume_evaluation(
    evaluation: Record,
    cutoff_ms: int,
    routing_ms: int,
    limits: Mapping[str, int],
    aggregates: dict[str, dict[str, object]],
) -> None:
    route = _route(evaluation)
    limit = _required_limit(route, limits)
    if evaluation.get("backend_non_action_reason") == _READINESS_SEED_REASON:
        row = aggregates[route]
        row["excluded_pre_activation_readiness_seeds"] = (
            int(row["excluded_pre_activation_readiness_seeds"]) + 1
        )
        return
    decision_ms = nonnegative_int(evaluation.get("decision_time_ms"), "decision time")
    initial_age = cutoff_ms - decision_ms
    routing_age = routing_ms - decision_ms
    if initial_age < 0 or routing_age < initial_age:
        raise ValueError("entry-age evidence has non-causal timestamps")
    is_eligible = evaluation.get("eligible")
    if not isinstance(is_eligible, bool):
        raise ValueError("evaluation eligible must be boolean")
    row = aggregates[route]
    row["evaluations"] = int(row["evaluations"]) + 1
    row["eligible_evaluations"] = int(row["eligible_evaluations"]) + int(is_eligible)
    _update_extrema(row, initial_age, routing_age, routing_ms - cutoff_ms, limit)
    if is_eligible and initial_age > limit:
        row["eligible_initial_cutoff_over_limit"] = (
            int(row["eligible_initial_cutoff_over_limit"]) + 1
        )
    if is_eligible and routing_age > limit:
        row["eligible_routing_emission_over_limit"] = (
            int(row["eligible_routing_emission_over_limit"]) + 1
        )
    if not is_eligible and routing_age > limit:
        row["latent_over_limit_ineligible_evaluations"] = (
            int(row["latent_over_limit_ineligible_evaluations"]) + 1
        )


def _consume_enter_action(
    action: Record,
    routing_ms: int,
    limits: Mapping[str, int],
    eligible: frozenset[tuple[str, int]],
    aggregates: dict[str, dict[str, object]],
) -> None:
    if action.get("action") != "enter":
        return
    strategy = text(action.get("strategy_id"), "action strategy")
    if strategy.startswith(_OPERATOR_PREFIX):
        return
    route = _route(action)
    limit = _required_limit(route, limits)
    decision_ms = nonnegative_int(action.get("decision_time_ms"), "action decision")
    if (route, decision_ms) not in eligible:
        raise ValueError("automatic enter action lacks matching eligible evaluation")
    routing_age = routing_ms - decision_ms
    if routing_age < 0:
        raise ValueError("entry action has a future decision timestamp")
    row = aggregates[route]
    row["enter_actions"] = int(row["enter_actions"]) + 1
    evidence = _submission_evidence(action, decision_ms, limit)
    if evidence is not None:
        submission_age, headroom = evidence
        row["submitted_entries"] = int(row["submitted_entries"]) + 1
        _update_submission_extrema(row, submission_age, headroom)
        _count_submission_boundary(row, action.get("submission_boundary"), headroom)
        if headroom < 0:
            row["submitted_entries_over_limit"] = (
                int(row["submitted_entries_over_limit"]) + 1
            )
    if routing_age > limit:
        row["enter_actions_routing_emission_over_limit"] = (
            int(row["enter_actions_routing_emission_over_limit"]) + 1
        )


def _consume_stale_withheld(
    item: Record,
    limits: Mapping[str, int],
    eligible: frozenset[tuple[str, int]],
    aggregates: dict[str, dict[str, object]],
) -> None:
    if item.get("reason") != "stale_before_submission":
        return
    route = _route(item)
    limit = _required_limit(route, limits)
    decision_ms = nonnegative_int(item.get("decision_time_ms"), "decision time")
    if (route, decision_ms) not in eligible:
        raise ValueError("stale entry lacks matching eligible evaluation")
    evidence = _submission_evidence(item, decision_ms, limit)
    if evidence is None or evidence[1] >= 0:
        raise ValueError("stale entry lacks over-limit submission evidence")
    row = aggregates[route]
    row["stale_entries_withheld"] = int(row["stale_entries_withheld"]) + 1
    _update_withheld_extrema(row, evidence[0])


def _submission_evidence(
    row: Record,
    decision_ms: int,
    configured_limit: int,
) -> tuple[int, int] | None:
    keys = (
        "submission_observed_at_ms",
        "submission_age_ms",
        "submission_limit_ms",
    )
    values = tuple(row.get(key) for key in keys)
    boundary = row.get("submission_boundary")
    if boundary is not None and (
        not isinstance(boundary, str) or boundary not in SUBMISSION_BOUNDARIES
    ):
        raise ValueError("unsupported submission boundary")
    if all(value is None for value in values):
        if boundary is not None:
            raise ValueError("submission boundary lacks clock evidence")
        return None
    if any(value is None for value in values):
        raise ValueError("submission evidence must be complete")
    observed = nonnegative_int(values[0], "submission observed time")
    age = nonnegative_int(values[1], "submission age")
    limit = positive_int(values[2], "submission limit")
    if limit != configured_limit or observed - decision_ms != age:
        raise ValueError("submission evidence does not reconcile")
    return age, limit - age


def _count_submission_boundary(
    row: dict[str, object], boundary: object, headroom: int
) -> None:
    if boundary == "sdk_dispatch":
        row["sdk_dispatch_checks"] = int(row["sdk_dispatch_checks"]) + 1
        row["sdk_dispatches_over_limit"] = int(row["sdk_dispatches_over_limit"]) + int(
            headroom < 0
        )
    elif boundary == "adapter_dispatch":
        row["adapter_dispatch_checks"] = int(row["adapter_dispatch_checks"]) + 1
    else:
        row["admission_or_legacy_checks"] = int(row["admission_or_legacy_checks"]) + 1


def _update_submission_extrema(
    row: dict[str, object], age_ms: int, headroom_ms: int
) -> None:
    prior_age = row["maximum_submission_age_ms"]
    prior_headroom = row["minimum_submission_headroom_ms"]
    row["maximum_submission_age_ms"] = (
        age_ms if prior_age is None else max(int(prior_age), age_ms)
    )
    row["minimum_submission_headroom_ms"] = (
        headroom_ms if prior_headroom is None else min(int(prior_headroom), headroom_ms)
    )


def _update_withheld_extrema(row: dict[str, object], age_ms: int) -> None:
    prior = row["maximum_withheld_submission_age_ms"]
    row["maximum_withheld_submission_age_ms"] = (
        age_ms if prior is None else max(int(prior), age_ms)
    )


def _provider_limits(identity: Record) -> dict[str, int]:
    limits: dict[str, int] = {}
    for provider in object_list(payload(identity), "providers"):
        strategy = text(provider.get("strategy_id"), "provider strategy")
        delay_ms = (
            positive_int(
                provider.get("maximum_entry_delay_seconds"), "maximum entry delay"
            )
            * 1_000
        )
        for symbol in text_list(provider.get("symbols"), "provider symbols"):
            route = f"{strategy}|{symbol}"
            if route in limits:
                raise ValueError(f"duplicate provider-symbol entry delay: {route}")
            limits[route] = delay_ms
    if not limits:
        raise ValueError("cohort identity has no provider entry delays")
    return dict(sorted(limits.items()))


def _paired_cycles(records: Sequence[Record]) -> list[tuple[Record, Record]]:
    pairs: list[tuple[Record, Record]] = []
    pending: Record | None = None
    for row in records:
        event_type = row.get("event_type")
        if event_type == "intent_routing":
            if pending is not None:
                raise ValueError("routing cycle is missing funding boundary")
            pending = row
        elif event_type == "funding_reconciliation_window":
            if pending is None:
                raise ValueError("funding boundary has no routing cycle")
            pairs.append((pending, row))
            pending = None
    if pending is not None:
        raise ValueError("routing cycle is missing funding boundary")
    return pairs


def _eligible_identities(
    evaluations: Sequence[Record], limits: Mapping[str, int]
) -> frozenset[tuple[str, int]]:
    result: set[tuple[str, int]] = set()
    for evaluation in evaluations:
        route = _route(evaluation)
        _required_limit(route, limits)
        if evaluation.get("backend_non_action_reason") == _READINESS_SEED_REASON:
            continue
        if evaluation.get("eligible") is True:
            identity = (
                route,
                nonnegative_int(evaluation.get("decision_time_ms"), "decision time"),
            )
            if identity in result:
                raise ValueError("duplicate eligible provider decision")
            result.add(identity)
    return frozenset(result)


def _update_extrema(
    row: dict[str, object],
    initial_age: int,
    routing_age: int,
    processing_ms: int,
    limit: int,
) -> None:
    values = {
        "maximum_initial_cutoff_age_ms": initial_age,
        "maximum_routing_emission_age_ms": routing_age,
        "maximum_post_cutoff_processing_ms": processing_ms,
    }
    for key, value in values.items():
        prior = row[key]
        row[key] = value if prior is None else max(int(prior), value)
    headrooms = {
        "minimum_initial_cutoff_headroom_ms": limit - initial_age,
        "minimum_routing_emission_headroom_ms": limit - routing_age,
    }
    for key, value in headrooms.items():
        prior = row[key]
        row[key] = value if prior is None else min(int(prior), value)


def _empty_route(limit_ms: int) -> dict[str, object]:
    return {
        "maximum_entry_delay_ms": limit_ms,
        "evaluations": 0,
        "eligible_evaluations": 0,
        "excluded_pre_activation_readiness_seeds": 0,
        "enter_actions": 0,
        "submitted_entries": 0,
        "sdk_dispatch_checks": 0,
        "sdk_dispatches_over_limit": 0,
        "adapter_dispatch_checks": 0,
        "admission_or_legacy_checks": 0,
        "stale_entries_withheld": 0,
        "submitted_entries_over_limit": 0,
        "maximum_submission_age_ms": None,
        "minimum_submission_headroom_ms": None,
        "maximum_withheld_submission_age_ms": None,
        "maximum_initial_cutoff_age_ms": None,
        "maximum_routing_emission_age_ms": None,
        "maximum_post_cutoff_processing_ms": None,
        "minimum_initial_cutoff_headroom_ms": None,
        "minimum_routing_emission_headroom_ms": None,
        "eligible_initial_cutoff_over_limit": 0,
        "eligible_routing_emission_over_limit": 0,
        "latent_over_limit_ineligible_evaluations": 0,
        "enter_actions_routing_emission_over_limit": 0,
    }


def _finalize_route(row: Mapping[str, object]) -> dict[str, object]:
    if int(row["sdk_dispatches_over_limit"]):
        status = "executed_submission_contract_breach"
    elif int(row["submitted_entries_over_limit"]):
        status = "recorded_check_contract_breach"
    elif (
        int(row["sdk_dispatch_checks"])
        and row["sdk_dispatch_checks"] == row["enter_actions"]
    ):
        status = "sdk_dispatch_contract_observed"
    elif (
        int(row["adapter_dispatch_checks"])
        and row["adapter_dispatch_checks"] == row["enter_actions"]
    ):
        status = "adapter_dispatch_check_observed"
    elif int(row["sdk_dispatch_checks"]) or int(row["adapter_dispatch_checks"]):
        status = "mixed_submission_boundaries_observed"
    elif int(row["submitted_entries"]):
        status = "admission_check_observed"
    elif int(row["stale_entries_withheld"]):
        status = "stale_entry_withholding_observed"
    elif int(row["enter_actions_routing_emission_over_limit"]):
        status = "potential_submission_contract_breach"
    else:
        status = "measured_no_action_breach"
    return {
        **row,
        "status": status,
    }


def _required_limit(route: str, limits: Mapping[str, int]) -> int:
    try:
        return limits[route]
    except KeyError as exc:
        raise ValueError(f"entry-age route is absent from identity: {route}") from exc


def _route(row: Record) -> str:
    return f"{text(row.get('strategy_id'), 'strategy')}|{text(row.get('symbol'), 'symbol')}"


def _timestamp_ms(row: Record) -> int:
    delta = timestamp(row).astimezone(UTC) - _EPOCH
    return delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "automatic_pause": False,
        "entry_enforcement_changed": False,
    }


def _limitations() -> list[str]:
    return [
        "legacy routing rows without submission evidence remain timing inferences",
        "legacy or admission-stage timestamps do not prove final dispatch checks",
        "over-limit ineligible evaluations expose cycle headroom rather than missed trades",
        "SDK signing, scheduling, transmission and acknowledgement follow the SDK-dispatch check",
    ]
