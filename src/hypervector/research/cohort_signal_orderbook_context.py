"""Causal order-book context for provider entries and signal opportunities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite

from hypervector.research.cohort_causal_book_context import (
    CausalBookSnapshot,
    build_causal_book_indexes,
    latest_prior_book,
)
from hypervector.research.cohort_eligible_signal_context import (
    build_eligible_signal_context,
)
from hypervector.research.cohort_forward_paths import (
    Candle,
    DirectionalPath,
    build_candle_index,
    resolve_directional_path,
    validated_horizons,
)
from hypervector.research.cohort_opportunity_capture import (
    DEFAULT_ESTIMATED_ROUND_TRIP_FRICTION_BPS,
    DEFAULT_ROBUST_GROSS_MOVE_BPS,
    OpportunityHurdles,
    opportunity_hurdles,
    summarize_path_opportunities,
)
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)
from hypervector.research.cohort_signal_pressure_translation import (
    build_signal_pressure_translation,
)

Record = Mapping[str, object]
_DEFAULT_HORIZONS = (5, 15, 30, 60)
_DEFAULT_MAX_BOOK_AGE_MS = 30_000


@dataclass(frozen=True)
class _BookPath:
    path: DirectionalPath
    directional_opi: float
    directional_depth_ratio: float
    spread_bps: float
    book_age_ms: int


@dataclass
class _HorizonEvidence:
    observations: list[_BookPath] = field(default_factory=list)
    censored: int = 0
    missing_data: int = 0


@dataclass
class _Coverage:
    exact_one_blocker_candidates: int = 0
    book_matched: int = 0
    book_stale: int = 0
    book_missing: int = 0

    def as_payload(self) -> dict[str, int]:
        """Return explicit decision-time book coverage counts."""
        return {
            "exact_one_blocker_candidates": self.exact_one_blocker_candidates,
            "book_matched": self.book_matched,
            "book_stale": self.book_stale,
            "book_missing": self.book_missing,
        }


@dataclass
class _PressureClockCoverage:
    pressure_unavailable_evaluations: int = 0
    causal_book_available: int = 0
    book_absent_or_stale: int = 0

    def observe(self, causal_book_available: bool) -> None:
        self.pressure_unavailable_evaluations += 1
        if causal_book_available:
            self.causal_book_available += 1
        else:
            self.book_absent_or_stale += 1

    def as_payload(self) -> dict[str, int]:
        return {
            "pressure_unavailable_evaluations": self.pressure_unavailable_evaluations,
            "causal_book_available": self.causal_book_available,
            "book_absent_or_stale": self.book_absent_or_stale,
        }


def build_orderbook_opportunity_diagnostics(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    *,
    horizons_minutes: Sequence[int] = _DEFAULT_HORIZONS,
    maximum_book_age_ms: int = _DEFAULT_MAX_BOOK_AGE_MS,
    estimated_round_trip_friction_bps: float = (
        DEFAULT_ESTIMATED_ROUND_TRIP_FRICTION_BPS
    ),
    robust_gross_move_bps: float = DEFAULT_ROBUST_GROSS_MOVE_BPS,
    provider_cadence_minutes: Mapping[str, int] | None = None,
) -> dict[str, object]:
    """Relate causal one-blocker paths to the latest prior L2 observation."""
    horizons = validated_horizons(horizons_minutes)
    maximum_age = _validated_book_age(maximum_book_age_ms)
    hurdles = opportunity_hurdles(
        estimated_round_trip_friction_bps,
        robust_gross_move_bps,
    )
    candidates, _, _ = evaluation_candidates(cohort_records)
    books = build_causal_book_indexes(asset_records)
    candles = build_candle_index(cohort_records)
    coverage = _Coverage()
    buckets: dict[tuple[str, str, str, str], dict[int, _HorizonEvidence]] = {}
    for candidate in candidates:
        _observe_candidate(
            candidate,
            books,
            candles,
            horizons,
            maximum_age,
            coverage,
            buckets,
        )
    return _report(
        horizons,
        maximum_age,
        hurdles,
        coverage,
        candidates,
        books,
        buckets,
        provider_cadence_minutes,
    )


def _validated_book_age(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("maximum book age must be a positive integer")
    return value


def _report(
    horizons: Sequence[int],
    maximum_book_age_ms: int,
    hurdles: OpportunityHurdles,
    coverage: _Coverage,
    candidates: Sequence[SignalCandidate],
    books: Mapping[str, tuple[CausalBookSnapshot, ...]],
    buckets: Mapping[tuple[str, str, str, str], Mapping[int, _HorizonEvidence]],
    provider_cadence_minutes: Mapping[str, int] | None,
) -> dict[str, object]:
    return {
        "contract": _contract(),
        "horizons_minutes": list(horizons),
        "maximum_book_age_ms": maximum_book_age_ms,
        "opportunity_hurdles_bps": hurdles.as_payload(),
        "coverage": coverage.as_payload(),
        "provider_pressure_clock": _provider_pressure_clock(
            candidates,
            books,
            maximum_book_age_ms,
        ),
        "eligible_signal_context": build_eligible_signal_context(
            candidates,
            books,
            maximum_book_age_ms,
            horizons_minutes=horizons,
            provider_cadence_minutes=provider_cadence_minutes,
        ),
        "eligible_pressure_translation": build_signal_pressure_translation(
            candidates,
            books,
            maximum_book_age_ms,
        ),
        "by_provider_symbol": _summaries(buckets, horizons, hurdles),
        "limitations": _limitations(),
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "fills_assumed": False,
        "pnl_claimed": False,
        "thresholds_selected": False,
        "orderbook_alignment_rule": (
            "directional_opi_above_zero_at_routing_publication"
        ),
        "path_start_policy": "first_full_minute_at_or_after_candidate_availability",
    }


def _limitations() -> list[str]:
    return [
        "L2 snapshots are observations, not proof of queue position or fills",
        "OPI sign is predeclared context and is not a fitted trading threshold",
        "only non-overlapping paths support aligned-versus-opposed comparisons",
        "small or one-sided samples remain descriptive rather than promotable",
        "a partial availability minute is excluded from forward candle paths",
    ]


def _provider_pressure_clock(
    candidates: Sequence[SignalCandidate],
    books: Mapping[str, tuple[CausalBookSnapshot, ...]],
    maximum_book_age_ms: int,
) -> dict[str, object]:
    total = _PressureClockCoverage()
    by_provider: dict[str, _PressureClockCoverage] = {}
    for candidate in candidates:
        if not _pressure_metrics_unavailable(candidate):
            continue
        status, snapshot = latest_prior_book(
            books.get(candidate.symbol, ()),
            candidate.available_time_ms,
            maximum_book_age_ms,
        )
        causal = (
            status == "matched"
            and snapshot is not None
            and snapshot.recv_ts_ms >= candidate.decision_time_ms
        )
        total.observe(causal)
        key = f"{candidate.strategy_id}|{candidate.symbol}"
        by_provider.setdefault(key, _PressureClockCoverage()).observe(causal)
    return {
        **total.as_payload(),
        "by_provider_symbol": {
            key: value.as_payload() for key, value in sorted(by_provider.items())
        },
    }


def _pressure_metrics_unavailable(candidate: SignalCandidate) -> bool:
    if "order_pressure_unavailable" not in candidate.blockers:
        return False
    return (
        candidate.metrics.get("imbalance_10") is None
        or candidate.metrics.get("pressure_age_seconds") is None
    )


def _observe_candidate(
    candidate: SignalCandidate,
    books: Mapping[str, tuple[CausalBookSnapshot, ...]],
    candles: Mapping[str, Mapping[int, Candle]],
    horizons: Sequence[int],
    maximum_book_age_ms: int,
    coverage: _Coverage,
    buckets: dict[tuple[str, str, str, str], dict[int, _HorizonEvidence]],
) -> None:
    if candidate.side is None or candidate.eligible or len(candidate.blockers) != 1:
        return
    coverage.exact_one_blocker_candidates += 1
    match_status, snapshot = latest_prior_book(
        books.get(candidate.symbol, ()),
        candidate.available_time_ms,
        maximum_book_age_ms,
    )
    if match_status != "matched" or snapshot is None:
        if match_status == "stale":
            coverage.book_stale += 1
        else:
            coverage.book_missing += 1
        return
    coverage.book_matched += 1
    blocker = candidate.blockers[0]
    key = (candidate.strategy_id, candidate.symbol, blocker, candidate.side)
    evidence = buckets.setdefault(
        key, {horizon: _HorizonEvidence() for horizon in horizons}
    )
    for horizon in horizons:
        status, path = resolve_directional_path(
            decision_time_ms=candidate.decision_time_ms,
            available_time_ms=candidate.available_time_ms,
            reference_price=candidate.reference_price,
            side=candidate.side,
            candles=candles.get(candidate.symbol, {}),
            horizon_minutes=horizon,
        )
        _record_path(
            evidence[horizon],
            status,
            path,
            snapshot,
            candidate,
        )


def _record_path(
    evidence: _HorizonEvidence,
    status: str,
    path: DirectionalPath | None,
    snapshot: CausalBookSnapshot,
    candidate: SignalCandidate,
) -> None:
    if status == "censored":
        evidence.censored += 1
        return
    if status == "missing_data":
        evidence.missing_data += 1
        return
    if path is None or candidate.side is None:
        raise RuntimeError("resolved order-book path requires direction and outcome")
    direction = 1.0 if candidate.side == "long" else -1.0
    depth_ratio = (
        snapshot.bid_depth_ratio if direction > 0.0 else 1.0 / snapshot.bid_depth_ratio
    )
    evidence.observations.append(
        _BookPath(
            path=path,
            directional_opi=direction * snapshot.opi,
            directional_depth_ratio=depth_ratio,
            spread_bps=snapshot.spread_bps,
            book_age_ms=candidate.available_time_ms - snapshot.recv_ts_ms,
        )
    )


def _summaries(
    buckets: Mapping[tuple[str, str, str, str], Mapping[int, _HorizonEvidence]],
    horizons: Sequence[int],
    hurdles: OpportunityHurdles,
) -> dict[str, object]:
    output: dict[str, object] = {}
    for (strategy, symbol, blocker, side), evidence in sorted(buckets.items()):
        provider = output.setdefault(f"{strategy}|{symbol}", {"by_blocker": {}})
        provider_map = _object(provider)
        blockers = _object(provider_map["by_blocker"])
        blocker_group = blockers.setdefault(blocker, {"by_side": {}})
        sides = _object(_object(blocker_group)["by_side"])
        sides[side] = {
            "horizons": {
                str(horizon): _horizon_summary(evidence[horizon], horizon, hurdles)
                for horizon in horizons
            }
        }
    return output


def _horizon_summary(
    evidence: _HorizonEvidence,
    horizon_minutes: int,
    hurdles: OpportunityHurdles,
) -> dict[str, object]:
    independent = _non_overlapping(evidence.observations, horizon_minutes)
    aligned = tuple(item for item in independent if item.directional_opi > 0.0)
    opposed = tuple(item for item in independent if item.directional_opi <= 0.0)
    return {
        "resolved": len(evidence.observations),
        "independent_resolved": len(independent),
        "censored": evidence.censored,
        "missing_data": evidence.missing_data,
        "all": _group_summary(independent, hurdles),
        "aligned": _group_summary(aligned, hurdles),
        "opposed": _group_summary(opposed, hurdles),
    }


def _non_overlapping(
    observations: Sequence[_BookPath], horizon_minutes: int
) -> tuple[_BookPath, ...]:
    output: list[_BookPath] = []
    next_available = -1
    for observation in sorted(
        observations, key=lambda item: item.path.decision_time_ms
    ):
        if observation.path.decision_time_ms < next_available:
            continue
        output.append(observation)
        next_available = observation.path.decision_time_ms + horizon_minutes * 60_000
    return tuple(output)


def _group_summary(
    observations: Sequence[_BookPath], hurdles: OpportunityHurdles
) -> dict[str, object]:
    return {
        "paths": len(observations),
        "mean_directional_opi": _mean([item.directional_opi for item in observations]),
        "mean_directional_depth_ratio": _mean(
            [item.directional_depth_ratio for item in observations]
        ),
        "mean_spread_bps": _mean([item.spread_bps for item in observations]),
        "mean_book_age_ms": _mean([float(item.book_age_ms) for item in observations]),
        "opportunity_capture": summarize_path_opportunities(
            [item.path for item in observations], hurdles
        ),
    }


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    result = sum(values) / len(values)
    if not isfinite(result):
        raise ValueError("order-book diagnostic mean must be finite")
    return result


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("internal order-book summary must be a mapping")
    return value
