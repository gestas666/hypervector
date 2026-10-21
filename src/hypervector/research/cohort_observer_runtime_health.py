"""Runtime continuity checks for disarmed cohort observer evidence."""

from __future__ import annotations

from collections.abc import Sequence

from hypervector.research.cohort_live_audit_values import provider_cadence_minutes
from hypervector.research.cohort_signal_candidates import is_technical_unavailability
from hypervector.research.cohort_observer_audit_values import (
    Evaluation,
    Pair,
    Record,
    _cycle_evaluations,
    _event_rows,
    _integer,
    _is_preactivation_seed,
    _number,
    _object_list,
    _pair,
    _payload,
    _text,
    _text_list,
    _timestamp,
)

_POLL_GAP = "observer_heartbeat_gap_exceeds_entry_delay"
Schedule = tuple[int, int]


def observer_runtime_coverage_gaps(
    records: Sequence[Record], identity: Record
) -> list[str]:
    """Return gaps when prospective runtime coverage cannot be proven."""
    schedules = _provider_schedules(identity)
    if schedules is not None:
        return (
            []
            if _scheduled_coverage_complete(records, identity, schedules)
            else [_POLL_GAP]
        )
    return _heartbeat_coverage_gaps(records, identity)


def _provider_schedules(identity: Record) -> dict[Pair, Schedule] | None:
    cadences = provider_cadence_minutes(identity)
    if cadences is None:
        return None
    providers = _object_list(_payload(identity), "providers")
    if any(
        provider.get("maximum_entry_delay_seconds") is None for provider in providers
    ):
        return None
    schedules: dict[Pair, Schedule] = {}
    for provider in providers:
        strategy = _text(provider.get("strategy_id"), "provider strategy")
        delay_ms = _positive_delay_ms(provider)
        cadence_ms = cadences[strategy] * 60_000
        for symbol in _text_list(provider.get("symbols"), "provider symbols"):
            schedules[(strategy, symbol)] = cadence_ms, delay_ms
    return schedules


def _positive_delay_ms(provider: Record) -> int:
    delay = _number(provider.get("maximum_entry_delay_seconds"), "maximum entry delay")
    if delay <= 0:
        raise ValueError("maximum entry delay must be positive")
    return int(delay * 1_000)


def _scheduled_coverage_complete(
    records: Sequence[Record],
    identity: Record,
    schedules: dict[Pair, Schedule],
) -> bool:
    evaluations = _prospective_evaluations(records)
    if any(_pair(value) not in schedules for _, value in evaluations):
        return False
    start_ms = _timestamp_ms(identity)
    end_ms = max(_timestamp_ms(record) for record in records)
    return all(
        _pair_schedule_complete(evaluations, pair, schedule, start_ms, end_ms)
        for pair, schedule in schedules.items()
    )


def _prospective_evaluations(records: Sequence[Record]) -> list[Evaluation]:
    cycles = _event_rows(records, "intent_routing")
    return [
        (cycle, evaluation)
        for cycle in cycles
        if not _is_preactivation_cycle(cycle)
        for evaluation in _cycle_evaluations(cycle)
    ]


def _is_preactivation_cycle(cycle: Record) -> bool:
    return any(
        _is_preactivation_seed(evaluation) for evaluation in _cycle_evaluations(cycle)
    )


def _pair_schedule_complete(
    evaluations: Sequence[Evaluation],
    pair: Pair,
    schedule: Schedule,
    start_ms: int,
    end_ms: int,
) -> bool:
    cadence_ms, delay_ms = schedule
    first_ms = _ceil_boundary(start_ms, cadence_ms)
    due_end_ms = end_ms - delay_ms
    expected = set(range(first_ms, due_end_ms + 1, cadence_ms))
    observations = _pair_schedule_observations(
        evaluations, pair, cadence_ms, delay_ms, first_ms, due_end_ms
    )
    if observations is None:
        return False
    observed, polling_status_arrivals = observations
    return all(
        decision_ms in observed
        or _has_timely_polling_status(polling_status_arrivals, decision_ms, delay_ms)
        for decision_ms in expected
    )


def _pair_schedule_observations(
    evaluations: Sequence[Evaluation],
    pair: Pair,
    cadence_ms: int,
    delay_ms: int,
    first_ms: int,
    due_end_ms: int,
) -> tuple[set[int], list[int]] | None:
    observed: set[int] = set()
    polling_status_arrivals: list[int] = []
    for arrival, evaluation in evaluations:
        if _pair(evaluation) != pair:
            continue
        decision_ms = _integer(evaluation.get("decision_time_ms"), "decision time")
        arrival_ms = _timestamp_ms(arrival)
        if decision_ms % cadence_ms:
            if not _is_polling_status(evaluation):
                return None
            polling_status_arrivals.append(arrival_ms)
            continue
        if decision_ms < first_ms:
            return None
        if decision_ms <= due_end_ms and arrival_ms > decision_ms + delay_ms:
            return None
        observed.add(decision_ms)
    return observed, polling_status_arrivals


def _is_polling_status(evaluation: Record) -> bool:
    """An off-cadence provider-source outage row still proves the provider polled."""
    return is_technical_unavailability(evaluation)


def _has_timely_polling_status(
    arrivals: Sequence[int], decision_ms: int, delay_ms: int
) -> bool:
    return any(
        decision_ms <= arrival_ms <= decision_ms + delay_ms for arrival_ms in arrivals
    )


def _ceil_boundary(value_ms: int, cadence_ms: int) -> int:
    return ((value_ms + cadence_ms - 1) // cadence_ms) * cadence_ms


def _timestamp_ms(record: Record) -> int:
    return int(_timestamp(record).timestamp() * 1_000)


def _heartbeat_coverage_gaps(records: Sequence[Record], identity: Record) -> list[str]:
    providers = _object_list(_payload(identity), "providers")
    delays = [
        _number(provider.get("maximum_entry_delay_seconds"), "maximum entry delay")
        for provider in providers
        if provider.get("maximum_entry_delay_seconds") is not None
    ]
    if not delays:
        return []
    heartbeats = _event_rows(records, "heartbeat")
    intervals = [
        (_timestamp(right) - _timestamp(left)).total_seconds()
        for left, right in zip(heartbeats, heartbeats[1:])
    ]
    return [_POLL_GAP] if intervals and max(intervals) > min(delays) else []


def successful_poll_streak(heartbeats: Sequence[Record]) -> int:
    """Count successful heartbeat rows since the latest degraded poll."""
    last_degraded = max(
        (
            index
            for index, row in enumerate(heartbeats)
            if _payload(row).get("status") == "degraded"
        ),
        default=-1,
    )
    return len(heartbeats) - last_degraded - 1
