"""Fail-closed freshness checks at the automatic order-submission boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Protocol

from hypervector.live.bidirectional_intents import (
    RoutingAction,
    StrategyIntent,
    WithheldIntent,
)
from hypervector.live.entry_submission_deadline import (
    EntryDeadlineExpired,
    EntrySubmissionDeadline,
    EntrySubmissionObservation,
)
from hypervector.live.asset_engine_contract import AssetEntryNotFilledError

EntryDelayMap = Mapping[tuple[str, str], int]


class EntryDelayProviderProtocol(Protocol):
    """Configured provider fields needed to bind submission freshness."""

    strategy_id: str
    execution_symbols: tuple[str, ...]
    maximum_entry_delay_seconds: int


def entry_delays_from_providers(
    providers: tuple[EntryDelayProviderProtocol, ...],
) -> dict[tuple[str, str], int]:
    """Project configured seconds into exact provider-symbol milliseconds."""
    return {
        (provider.strategy_id, symbol): provider.maximum_entry_delay_seconds * 1_000
        for provider in providers
        for symbol in provider.execution_symbols
    }


def validate_entry_delays(
    delays: EntryDelayMap,
    executable_pairs: frozenset[tuple[str, str]],
) -> dict[tuple[str, str], int]:
    """Require one positive millisecond ceiling for every executable route."""
    if set(delays) != set(executable_pairs):
        raise ValueError("entry-delay policy must exactly cover executable routes")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in delays.values()
    ):
        raise ValueError("entry-delay ceilings must be positive integers")
    return dict(delays)


def stale_entry_before_submission(
    action: RoutingAction,
    observed_ms: int,
    delays: EntryDelayMap,
) -> WithheldIntent | None:
    """Return explicit non-action evidence when a routed entry has expired."""
    if action.action != "enter":
        return None
    age_ms, limit_ms = _submission_age(action, observed_ms, delays)
    if age_ms <= limit_ms:
        return None
    return WithheldIntent(
        _intent_from_action(action),
        "stale_before_submission",
        observed_ms,
        age_ms,
        limit_ms,
    )


def execute_fresh_routed_actions(
    actions: tuple[RoutingAction, ...],
    *,
    now_ms: Callable[[], int],
    delays: EntryDelayMap,
    execute: Callable[[RoutingAction, EntrySubmissionDeadline | None], None],
) -> tuple[tuple[RoutingAction, ...], tuple[WithheldIntent, ...]]:
    """Execute exits and fresh entries while retaining every stale non-action."""
    submitted: list[RoutingAction] = []
    withheld: list[WithheldIntent] = []
    for action in actions:
        if action.action != "enter":
            execute(action, None)
            submitted.append(action)
            continue
        deadline = EntrySubmissionDeadline(
            action.decision_time_ms,
            _entry_limit(action, delays),
            now_ms,
        )
        try:
            observation = deadline.check("engine_admission")
            execute(_annotate_submission(action, observation), deadline)
        except EntryDeadlineExpired as exc:
            observed = exc.observation
            withheld.append(
                WithheldIntent(
                    _intent_from_action(action),
                    "stale_before_submission",
                    observed.observed_at_ms,
                    observed.age_ms,
                    observed.limit_ms,
                    observed.boundary,
                )
            )
            continue
        except AssetEntryNotFilledError:
            withheld.append(
                _ioc_no_fill(_annotate_submission(action, deadline.last_observation))
            )
            continue
        submitted.append(_annotate_submission(action, deadline.last_observation))
    return tuple(submitted), tuple(withheld)


def _annotate_submission(
    action: RoutingAction,
    observation: EntrySubmissionObservation,
) -> RoutingAction:
    return replace(
        action,
        submission_observed_at_ms=observation.observed_at_ms,
        submission_age_ms=observation.age_ms,
        submission_limit_ms=observation.limit_ms,
        submission_boundary=observation.boundary,
    )


def _submission_age(
    action: RoutingAction,
    observed_ms: int,
    delays: EntryDelayMap,
) -> tuple[int, int]:
    limit = _entry_limit(action, delays)
    age_ms = observed_ms - action.decision_time_ms
    if age_ms < 0:
        raise ValueError("entry submission clock precedes the decision")
    return age_ms, limit


def _entry_limit(action: RoutingAction, delays: EntryDelayMap) -> int:
    key = (action.strategy_id, action.symbol)
    try:
        return delays[key]
    except KeyError as exc:
        raise ValueError(f"entry-delay policy is missing route {key}") from exc


def _intent_from_action(action: RoutingAction) -> StrategyIntent:
    return StrategyIntent(
        strategy_id=action.strategy_id,
        symbol=action.symbol,
        side=action.side,
        decision_time_ms=action.decision_time_ms,
        reference_price=action.reference_price,
        reason="routed_entry_revalidated_before_submission",
        stop_anchor=action.stop_anchor,
        target_anchor=action.target_anchor,
        regime_alignment_score=action.regime_alignment_score,
        regime_alignment_stance=action.regime_alignment_stance,
        regime_decision_time_ms=action.regime_decision_time_ms,
        regime_alignment_basis=action.regime_alignment_basis,
    )


def _ioc_no_fill(action: RoutingAction) -> WithheldIntent:
    """Project a safely flat IOC no-fill without claiming execution."""
    if action.action != "enter":
        raise ValueError("IOC no-fill applies only to entry actions")
    return WithheldIntent(
        _intent_from_action(action),
        "entry_ioc_no_fill",
        action.submission_observed_at_ms,
        action.submission_age_ms,
        action.submission_limit_ms,
        action.submission_boundary,
    )
