"""Executable-BBO markouts for report-only eligible signal diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_causal_book_context import (
    CausalBookSnapshot,
    earliest_at_or_after_book,
)
from hypervector.research.cohort_eligible_signal_markout_models import (
    ExecutableMarkout,
    MarkoutCoverage,
    MarkoutEvidence,
    MarkoutFriction,
)
from hypervector.research.cohort_eligible_signal_markout_summary import (
    summarize_executable_markouts,
)
from hypervector.research.cohort_forward_paths import validated_horizons
from hypervector.research.cohort_friction_contracts import modeled_contract
from hypervector.research.cohort_signal_candidates import SignalCandidate

BookIndex = Mapping[str, Sequence[CausalBookSnapshot]]
AnnotatedSignal = tuple[SignalCandidate, Mapping[str, object]]
_EpisodeKey = tuple[str | None, str, str, int, str]
_EpisodeStream = tuple[str | None, str, str]
_MINUTE_MS = 60_000
_STANCES = ("aligned", "neutral", "opposed", "unavailable")


def build_executable_bbo_markouts(
    annotated_signals: Sequence[AnnotatedSignal],
    books: BookIndex,
    *,
    horizons_minutes: Sequence[int],
    maximum_book_lateness_ms: int,
    provider_cadence_minutes: Mapping[str, int] | None = None,
) -> dict[str, dict[str, object]]:
    """Measure post-publication BBO paths without claiming orders or fills."""
    horizons = validated_horizons(horizons_minutes)
    episode_onsets = _episode_onset_keys(
        annotated_signals,
        provider_cadence_minutes,
    )
    grouped: dict[str, dict[int, MarkoutEvidence]] = {}
    cadences: dict[str, int | None] = {}
    for candidate, annotation in annotated_signals:
        key = f"{candidate.strategy_id}|{candidate.symbol}"
        cadence = _provider_cadence(candidate, provider_cadence_minutes)
        cadences[key] = cadence
        evidence = grouped.setdefault(key, _evidence(horizons))
        _observe(
            evidence,
            candidate,
            annotation,
            books.get(candidate.symbol, ()),
            horizons,
            maximum_book_lateness_ms,
            None
            if episode_onsets is None
            else _episode_key(candidate) in episode_onsets,
        )
    return {
        key: summarize_executable_markouts(
            value,
            horizons,
            maximum_book_lateness_ms,
            cadences[key],
        )
        for key, value in sorted(grouped.items())
    }


def _episode_onset_keys(
    annotated_signals: Sequence[AnnotatedSignal],
    cadences: Mapping[str, int] | None,
) -> set[_EpisodeKey] | None:
    if cadences is None:
        return None
    prior_by_stream: dict[_EpisodeStream, SignalCandidate] = {}
    onsets: set[_EpisodeKey] = set()
    candidates = sorted(
        (candidate for candidate, _ in annotated_signals),
        key=lambda item: (
            item.source_run_id or "",
            item.strategy_id,
            item.symbol,
            item.decision_time_ms,
        ),
    )
    for candidate in candidates:
        cadence = _provider_cadence(candidate, cadences)
        if cadence is None:
            raise RuntimeError("validated provider cadence cannot be unavailable")
        stream = (candidate.source_run_id, candidate.strategy_id, candidate.symbol)
        prior = prior_by_stream.get(stream)
        contiguous = (
            prior is not None
            and prior.side == candidate.side
            and candidate.decision_time_ms - prior.decision_time_ms
            == cadence * _MINUTE_MS
        )
        if not contiguous:
            onsets.add(_episode_key(candidate))
        prior_by_stream[stream] = candidate
    return onsets


def _provider_cadence(
    candidate: SignalCandidate,
    cadences: Mapping[str, int] | None,
) -> int | None:
    if cadences is None:
        return None
    value = cadences.get(candidate.strategy_id)
    if value is None:
        raise ValueError(f"provider cadence is missing for {candidate.strategy_id}")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("provider cadence must be a positive integer")
    return value


def _episode_key(candidate: SignalCandidate) -> _EpisodeKey:
    if candidate.side not in {"long", "short"}:
        raise RuntimeError("eligible episode onset requires a direction")
    return (
        candidate.source_run_id,
        candidate.strategy_id,
        candidate.symbol,
        candidate.decision_time_ms,
        candidate.side,
    )


def _evidence(horizons: Sequence[int]) -> dict[int, MarkoutEvidence]:
    return {horizon: MarkoutEvidence() for horizon in horizons}


def _observe(
    evidence: Mapping[int, MarkoutEvidence],
    candidate: SignalCandidate,
    annotation: Mapping[str, object],
    books: Sequence[CausalBookSnapshot],
    horizons: Sequence[int],
    maximum_lateness_ms: int,
    episode_onset: bool | None,
) -> None:
    entry_status, entry = earliest_at_or_after_book(
        books,
        candidate.available_time_ms,
        maximum_lateness_ms,
    )
    friction = _friction(candidate)
    for horizon in horizons:
        bucket = evidence[horizon]
        coverages = [bucket.coverage]
        if episode_onset is True:
            coverages.append(bucket.episode_coverage)
        for coverage in coverages:
            coverage.eligible_signals += 1
        if entry is None:
            for coverage in coverages:
                _increment(coverage, f"entry_{entry_status}")
            continue
        for coverage in coverages:
            coverage.entry_matched += 1
        _observe_exit(
            bucket,
            candidate,
            annotation,
            books,
            entry,
            friction,
            horizon,
            maximum_lateness_ms,
            coverages,
            episode_onset,
        )


def _observe_exit(
    evidence: MarkoutEvidence,
    candidate: SignalCandidate,
    annotation: Mapping[str, object],
    books: Sequence[CausalBookSnapshot],
    entry: CausalBookSnapshot,
    friction: MarkoutFriction | None,
    horizon_minutes: int,
    maximum_lateness_ms: int,
    coverages: Sequence[MarkoutCoverage],
    episode_onset: bool | None,
) -> None:
    target = entry.recv_ts_ms + horizon_minutes * 60_000
    status, exit_book = earliest_at_or_after_book(books, target, maximum_lateness_ms)
    if exit_book is None:
        for coverage in coverages:
            _increment(coverage, f"exit_{status}")
        return
    outcome = _markout(
        candidate,
        annotation,
        entry,
        exit_book,
        friction,
        horizon_minutes,
        episode_onset,
    )
    for coverage in coverages:
        coverage.resolved += 1
    if outcome.after_modeled_friction_bps is None:
        for coverage in coverages:
            coverage.friction_contract_missing += 1
    evidence.outcomes.append(outcome)


def _increment(coverage: MarkoutCoverage, name: str) -> None:
    if name not in {"entry_censored", "entry_gap", "exit_censored", "exit_gap"}:
        raise RuntimeError("unexpected executable-book coverage state")
    setattr(coverage, name, getattr(coverage, name) + 1)


def _friction(candidate: SignalCandidate) -> MarkoutFriction | None:
    contract = modeled_contract(candidate.strategy_id, candidate.symbol)
    if contract is None:
        return None
    return MarkoutFriction(
        fee_bps_per_side=contract.entry_fee_bps,
        residual_slippage_bps_per_side=contract.entry_slippage_bps,
        source=contract.evidence_source,
    )


def _markout(
    candidate: SignalCandidate,
    annotation: Mapping[str, object],
    entry: CausalBookSnapshot,
    exit_book: CausalBookSnapshot,
    friction: MarkoutFriction | None,
    horizon_minutes: int,
    episode_onset: bool | None,
) -> ExecutableMarkout:
    if candidate.side not in {"long", "short"}:
        raise RuntimeError("eligible executable markout requires a direction")
    entry_price = entry.best_ask if candidate.side == "long" else entry.best_bid
    exit_price = exit_book.best_bid if candidate.side == "long" else exit_book.best_ask
    direction = 1.0 if candidate.side == "long" else -1.0
    gross = direction * (exit_price / entry_price - 1.0) * 10_000.0
    cost_scale = 1.0 + exit_price / entry_price
    after_fee = _after_fee(gross, cost_scale, friction)
    modeled = _after_modeled_friction(after_fee, cost_scale, friction)
    return ExecutableMarkout(
        source_run_id=candidate.source_run_id,
        decision_time_ms=candidate.decision_time_ms,
        horizon_minutes=horizon_minutes,
        signal_available_time_ms=candidate.available_time_ms,
        entry_book_time_ms=entry.recv_ts_ms,
        exit_book_time_ms=exit_book.recv_ts_ms,
        side=candidate.side,
        pressure_stance=_stance(annotation, "pressure_stance"),
        state_5m_stance=_stance(annotation, "state_5m_stance"),
        context_15m_stance=_stance(annotation, "context_15m_stance"),
        entry_price=entry_price,
        exit_price=exit_price,
        gross_bbo_bps=gross,
        after_fee_bps=after_fee,
        after_modeled_friction_bps=modeled,
        fee_bps_per_side=(friction.fee_bps_per_side if friction else None),
        residual_slippage_bps_per_side=(
            friction.residual_slippage_bps_per_side if friction else None
        ),
        friction_source=friction.source if friction else None,
        episode_onset=episode_onset,
    )


def _after_fee(
    gross_bps: float, cost_scale: float, friction: MarkoutFriction | None
) -> float | None:
    if friction is None:
        return None
    return gross_bps - friction.fee_bps_per_side * cost_scale


def _after_modeled_friction(
    after_fee_bps: float | None,
    cost_scale: float,
    friction: MarkoutFriction | None,
) -> float | None:
    if (
        after_fee_bps is None
        or friction is None
        or friction.residual_slippage_bps_per_side is None
    ):
        return None
    return after_fee_bps - friction.residual_slippage_bps_per_side * cost_scale


def _stance(annotation: Mapping[str, object], name: str) -> str:
    value = annotation.get(name)
    if not isinstance(value, str) or value not in _STANCES:
        raise RuntimeError(f"eligible signal {name} is invalid")
    return value
