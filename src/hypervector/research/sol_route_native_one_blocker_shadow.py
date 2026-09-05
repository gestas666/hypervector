"""Report-only route-native replay for the SOL hourly-cross near miss."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Sequence

from hypervector.data.hl_events import StreamGap
from hypervector.research.cohort_one_blocker_execution_contract import (
    OneBlockerExecutionContract,
)
from hypervector.research.cohort_one_blocker_execution_liquidity import (
    entry_execution,
    exit_execution,
)
from hypervector.research.cohort_one_blocker_execution_payloads import (
    direction,
    execution_payload,
)
from hypervector.research.cohort_one_blocker_execution_types import Book
from hypervector.research.cohort_signal_candidates import SignalCandidate
from hypervector.research.sol_route_native_one_blocker_models import (
    MarkObservation,
    SolFundingEvidence,
    SolRouteNativeShadowSpec,
)
from hypervector.research.sol_route_native_one_blocker_attempts import (
    basic_attempt,
    covered_funding,
    pending_candidate,
)
from hypervector.research.sol_route_native_one_blocker_path import (
    has_unresolved_stream_gap,
)

_STRATEGY = "range_onset_bidirectional_v1"
_SYMBOL = "SOL"
_BLOCKER = "awaiting_hourly_sma_cross"
_STOP_BPS = 80.0
_MAXIMUM_HOLD_MS = 172_800_000
_MAXIMUM_CONTEXT_AGE_MS = 30_000
_MAXIMUM_ENTRY_DELAY_MS = 60_000
_MAXIMUM_EXIT_DELAY_MS = 60_000
_EXIT_RULE = "first venue-mark stop, eligible opposite signal, then 48h maximum hold"


def build_sol_route_native_one_blocker_shadow(
    *,
    candidates: Sequence[SignalCandidate],
    books: Sequence[Book],
    marks: Sequence[MarkObservation],
    funding_evidence: SolFundingEvidence | None,
    gaps: Sequence[StreamGap],
    spec: SolRouteNativeShadowSpec,
) -> dict[str, object]:
    """Replay exact post-cutoff candidates without order or live-change authority."""
    ordered_books = tuple(sorted(books, key=lambda row: row.recv_ts_ms))
    ordered_marks = _validated_marks(marks)
    ordered_candidates = tuple(
        sorted(candidates, key=lambda row: row.available_time_ms)
    )
    episode_onsets = _episode_onsets(ordered_candidates, spec)
    executions: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    next_available_ms = spec.cutoff_time_ms
    for candidate in episode_onsets:
        if not _entry_candidate(candidate, spec, next_available_ms):
            continue
        attempt, execution = _replay_candidate(
            candidate,
            ordered_candidates,
            ordered_books,
            ordered_marks,
            funding_evidence,
            gaps,
            spec,
        )
        attempts.append(attempt)
        if execution is not None:
            executions.append(execution)
            next_available_ms = int(execution["exit_time_ms"])
        elif "entry_time_ms" in attempt:
            break
    return _report(spec, ordered_candidates, attempts, executions)


def _validated_marks(
    marks: Sequence[MarkObservation],
) -> tuple[MarkObservation, ...]:
    """Order exact receipt observations and reject conflicting duplicates."""
    unique: dict[int, MarkObservation] = {}
    for mark in marks:
        receipt_ns = mark.causal_receipt_ns
        existing = unique.get(receipt_ns)
        if existing is not None and existing.mark_price != mark.mark_price:
            raise ValueError("SOL shadow mark timestamps contain conflicting prices")
        unique[receipt_ns] = mark
    return tuple(unique[timestamp] for timestamp in sorted(unique))


def _replay_candidate(
    candidate: SignalCandidate,
    candidates: Sequence[SignalCandidate],
    books: Sequence[Book],
    marks: Sequence[MarkObservation],
    funding: SolFundingEvidence | None,
    gaps: Sequence[StreamGap],
    spec: SolRouteNativeShadowSpec,
) -> tuple[dict[str, object], dict[str, object] | None]:
    context = _latest_book(books, candidate.available_time_ms)
    entry = _first_book(books, candidate.available_time_ms, _MAXIMUM_ENTRY_DELAY_MS)
    if (
        context is None
        or candidate.available_time_ms - context.recv_ts_ms > _MAXIMUM_CONTEXT_AGE_MS
    ):
        return basic_attempt(candidate, "context_unavailable"), None
    if entry is None:
        return basic_attempt(candidate, "entry_unavailable"), None
    contract = _execution_contract(spec)
    entry_price, entry_size = entry_execution(entry, direction(candidate), contract)
    if entry_price * entry_size + 1e-12 < spec.notional_usd:
        return basic_attempt(candidate, "entry_capacity_failure"), None
    return _resolve_candidate(
        candidate,
        candidates,
        books,
        marks,
        funding,
        context,
        entry,
        entry_price,
        contract,
        gaps,
        spec,
    )


def _resolve_candidate(
    candidate: SignalCandidate,
    candidates: Sequence[SignalCandidate],
    books: Sequence[Book],
    marks: Sequence[MarkObservation],
    funding_evidence: SolFundingEvidence | None,
    context: Book,
    entry: Book,
    entry_price: float,
    contract: OneBlockerExecutionContract,
    gaps: Sequence[StreamGap],
    spec: SolRouteNativeShadowSpec,
) -> tuple[dict[str, object], dict[str, object] | None]:
    deadline = entry.recv_ts_ms + _MAXIMUM_HOLD_MS
    trigger_ms, reason = _first_exit_trigger(
        candidate, candidates, marks, entry_price, entry.recv_ts_ms, deadline
    )
    if (
        reason == "maximum_hold"
        and _evidence_end(candidates, books, marks) < trigger_ms
    ):
        return pending_candidate(
            candidate=candidate,
            books=books,
            funding_evidence=funding_evidence,
            context=context,
            entry=entry,
            entry_price=entry_price,
            deadline_ms=trigger_ms,
            contract=contract,
        )
    if has_unresolved_stream_gap(gaps, marks, books, entry.recv_ts_ms, trigger_ms):
        return basic_attempt(
            candidate, "technical_gap_unresolved", entry.recv_ts_ms
        ), None
    exit_book = _first_book(books, trigger_ms, _MAXIMUM_EXIT_DELAY_MS)
    if exit_book is None:
        return basic_attempt(candidate, "exit_unavailable", entry.recv_ts_ms), None
    return _completed_execution(
        candidate,
        books,
        funding_evidence,
        context,
        entry,
        exit_book,
        entry_price,
        reason,
        contract,
        spec,
    )


def _completed_execution(
    candidate: SignalCandidate,
    books: Sequence[Book],
    funding_evidence: SolFundingEvidence | None,
    context: Book,
    entry: Book,
    exit_book: Book,
    entry_price: float,
    reason: str,
    contract: OneBlockerExecutionContract,
    spec: SolRouteNativeShadowSpec,
) -> tuple[dict[str, object], dict[str, object] | None]:
    funding = covered_funding(
        funding_evidence,
        entry.recv_ts_ms,
        exit_book.recv_ts_ms,
    )
    if funding is None:
        return basic_attempt(
            candidate, "funding_coverage_unresolved", entry.recv_ts_ms
        ), None
    position_size = spec.notional_usd / entry_price
    exit_price, exit_size = exit_execution(
        exit_book, direction(candidate), position_size, contract
    )
    if exit_size + 1e-12 < position_size:
        return basic_attempt(candidate, "exit_capacity_failure", entry.recv_ts_ms), None
    execution = execution_payload(
        candidate,
        context,
        books,
        funding,
        entry,
        exit_book,
        entry_price,
        exit_price,
        position_size,
        reason,
        contract,
    )
    execution["crossed_stop_proxy"] = reason == "venue_mark_stop"
    return basic_attempt(candidate, "resolved", entry.recv_ts_ms), execution


def _evidence_end(
    candidates: Sequence[SignalCandidate],
    books: Sequence[Book],
    marks: Sequence[MarkObservation],
) -> int:
    """Return the latest causal timestamp available to the shadow replay."""
    values = [row.available_time_ms for row in candidates]
    values.extend(row.recv_ts_ms for row in books)
    values.extend(row.observed_ts_ms for row in marks)
    return max(values, default=0)


def _first_exit_trigger(
    candidate: SignalCandidate,
    candidates: Sequence[SignalCandidate],
    marks: Sequence[MarkObservation],
    entry_price: float,
    entry_ms: int,
    deadline_ms: int,
) -> tuple[int, str]:
    options = [(deadline_ms, "maximum_hold", 2)]
    opposite = _opposite_signal(candidate, candidates, entry_ms, deadline_ms)
    stop = _stop_cross(candidate, marks, entry_price, entry_ms, deadline_ms)
    if stop is not None:
        options.append((stop, "venue_mark_stop", 0))
    if opposite is not None:
        options.append((opposite, "opposite_signal", 1))
    return min(options, key=lambda item: (item[0], item[2]))[:2]


def _opposite_signal(
    opened: SignalCandidate,
    candidates: Sequence[SignalCandidate],
    entry_ms: int,
    deadline_ms: int,
) -> int | None:
    times = [
        row.available_time_ms
        for row in candidates
        if row.source_run_id == opened.source_run_id
        and row.strategy_id == _STRATEGY
        and row.symbol == _SYMBOL
        and row.eligible
        and row.side in {"long", "short"}
        and row.side != opened.side
        and entry_ms <= row.available_time_ms <= deadline_ms
    ]
    return min(times) if times else None


def _stop_cross(
    candidate: SignalCandidate,
    marks: Sequence[MarkObservation],
    entry_price: float,
    entry_ms: int,
    deadline_ms: int,
) -> int | None:
    signed = direction(candidate)
    for mark in marks:
        if not entry_ms <= mark.observed_ts_ms <= deadline_ms:
            continue
        move_bps = signed * (mark.mark_price / entry_price - 1.0) * 10_000.0
        if move_bps <= -_STOP_BPS:
            return mark.observed_ts_ms
    return None


def _entry_candidate(
    candidate: SignalCandidate,
    spec: SolRouteNativeShadowSpec,
    next_available_ms: int,
) -> bool:
    return (
        candidate.source_run_id == spec.source_run_id
        and candidate.strategy_id == _STRATEGY
        and candidate.symbol == _SYMBOL
        and candidate.side in {"long", "short"}
        and not candidate.eligible
        and candidate.blockers == (_BLOCKER,)
        and candidate.available_time_ms >= max(spec.cutoff_time_ms, next_available_ms)
    )


def _first_book(books: Sequence[Book], target_ms: int, delay_ms: int) -> Book | None:
    index = bisect_left([row.recv_ts_ms for row in books], target_ms)
    if index >= len(books) or books[index].recv_ts_ms - target_ms > delay_ms:
        return None
    return books[index]


def _latest_book(books: Sequence[Book], target_ms: int) -> Book | None:
    index = bisect_right([row.recv_ts_ms for row in books], target_ms) - 1
    return books[index] if index >= 0 else None


def _execution_contract(spec: SolRouteNativeShadowSpec) -> OneBlockerExecutionContract:
    return OneBlockerExecutionContract(
        strategy_id=_STRATEGY,
        symbol=_SYMBOL,
        blocker=_BLOCKER,
        horizon_minutes=_MAXIMUM_HOLD_MS // 60_000,
        maximum_context_age_ms=_MAXIMUM_CONTEXT_AGE_MS,
        maximum_entry_delay_ms=_MAXIMUM_ENTRY_DELAY_MS,
        maximum_exit_delay_ms=_MAXIMUM_EXIT_DELAY_MS,
        notional_usd=spec.notional_usd,
        taker_fee_rate=spec.taker_fee_rate,
        stop_proxy_bps=_STOP_BPS,
        opi_cohort="all",
        minimum_available_time_ms=spec.cutoff_time_ms,
        liquidity_policy="visible_depth",
    )


def _report(
    spec: SolRouteNativeShadowSpec,
    candidates: Sequence[SignalCandidate],
    attempts: Sequence[dict[str, object]],
    executions: Sequence[dict[str, object]],
) -> dict[str, object]:
    coverage = _candidate_coverage(candidates, spec)
    coverage.update(
        {
            "attempts": len(attempts),
            "resolved_executions": len(executions),
            "pending_or_unresolved": len(attempts) - len(executions),
        }
    )
    return {
        "schema_version": 1,
        "mode": "v51_sol_route_native_one_blocker_shadow",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "source_run_id": spec.source_run_id,
            "source_profile_id": spec.source_profile_id,
            "source_profile_fingerprint": spec.source_profile_fingerprint,
            "execution": _route_execution_payload(spec),
            "exit_precedence": ["venue_mark_stop", "opposite_signal", "maximum_hold"],
            "exit_rule": _EXIT_RULE,
        },
        "coverage": coverage,
        "attempts": list(attempts),
        "executions": list(executions),
    }


def _route_execution_payload(spec: SolRouteNativeShadowSpec) -> dict[str, object]:
    payload = _execution_contract(spec).as_payload()
    payload.pop("alignment_rule")
    payload.pop("minimum_entry_spacing_minutes")
    payload.pop("opi_cohort")
    payload.update(
        {
            "candidate_rule": (
                "exact v51 SOL evaluation blocked only by awaiting_hourly_sma_cross"
            ),
            "entry_rule": (
                "first visible-depth L2 at/after availability within 60s; "
                "context age <=30s"
            ),
            "exit_rule": _EXIT_RULE,
            "reentry_rule": (
                "one SOL position at a time; next independent episode onset after exit"
            ),
        }
    )
    return payload


def _candidate_coverage(
    candidates: Sequence[SignalCandidate],
    spec: SolRouteNativeShadowSpec,
) -> dict[str, int]:
    """Count exact candidates and each identity/condition exclusion."""
    relevant = [
        row
        for row in candidates
        if row.strategy_id == _STRATEGY and row.symbol == _SYMBOL
    ]
    wrong_run = [row for row in relevant if row.source_run_id != spec.source_run_id]
    same_run = [row for row in relevant if row.source_run_id == spec.source_run_id]
    raw_exact = [row for row in same_run if _is_exact_candidate(row, spec)]
    onsets = _episode_onsets(candidates, spec)
    return {
        "observed_candidates": len(relevant),
        "raw_exact_evaluations": len(raw_exact),
        "exact_candidates": len(onsets),
        "wrong_run_excluded": len(wrong_run),
        "inexact_condition_excluded": len(same_run) - len(raw_exact),
    }


def _episode_onsets(
    candidates: Sequence[SignalCandidate],
    spec: SolRouteNativeShadowSpec,
) -> tuple[SignalCandidate, ...]:
    onsets: list[SignalCandidate] = []
    active_side: str | None = None
    for candidate in candidates:
        if not _same_route(candidate, spec):
            continue
        if not _matches_exact_condition(candidate):
            active_side = None
            continue
        if (
            candidate.side != active_side
            and candidate.available_time_ms >= spec.cutoff_time_ms
        ):
            onsets.append(candidate)
        active_side = candidate.side
    return tuple(onsets)


def _is_exact_candidate(
    candidate: SignalCandidate, spec: SolRouteNativeShadowSpec
) -> bool:
    return (
        _same_route(candidate, spec)
        and _matches_exact_condition(candidate)
        and candidate.available_time_ms >= spec.cutoff_time_ms
    )


def _matches_exact_condition(candidate: SignalCandidate) -> bool:
    return (
        candidate.side in {"long", "short"}
        and not candidate.eligible
        and candidate.blockers == (_BLOCKER,)
    )


def _same_route(candidate: SignalCandidate, spec: SolRouteNativeShadowSpec) -> bool:
    return (
        candidate.source_run_id == spec.source_run_id
        and candidate.strategy_id == _STRATEGY
        and candidate.symbol == _SYMBOL
    )
