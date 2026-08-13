"""Portfolio-level deduplication for counterfactual provider opportunities."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from statistics import median

from hypervector.research.cohort_forward_paths import (
    MINUTE_MS,
    Candle,
    DirectionalPath,
    non_overlapping_paths,
    resolve_directional_path,
)
from hypervector.research.cohort_opportunity_capture import (
    OpportunityHurdles,
    summarize_path_opportunities,
)
from hypervector.research.cohort_signal_candidates import SignalCandidate

_GroupKey = tuple[str | None, str, int, str]
_ProviderKey = tuple[str, str]
_AttributionKey = tuple[str | None, str, str, tuple[_ProviderKey, ...]]


@dataclass
class _OpportunityGroup:
    source_run_id: str | None
    symbol: str
    decision_time_ms: int
    side: str
    candidates: list[SignalCandidate] = field(default_factory=list)


def build_portfolio_opportunity_dedup(
    candidates: Sequence[SignalCandidate],
    candles: Mapping[str, Mapping[int, Candle]],
    horizons: Sequence[int],
    hurdles: OpportunityHurdles,
) -> dict[str, object]:
    """Count each one-blocker directional market path once across providers."""
    groups = _opportunity_groups(candidates)
    observations = sum(len(group.candidates) for group in groups)
    cross_provider = [group for group in groups if _provider_count(group) > 1]
    reference_conflicts = sum(not _reference_consistent(group) for group in groups)
    return {
        "contract": {
            "counterfactual_only": True,
            "fills_assumed": False,
            "pnl_claimed": False,
            "execution_authority": "none",
            "identity_fields": [
                "source_run_id",
                "symbol",
                "decision_time_ms",
                "side",
            ],
            "scope": "directional_one_blocker_readiness_annotations",
        },
        "provider_observations": observations,
        "unique_directional_paths": len(groups),
        "duplicate_provider_observations_removed": observations - len(groups),
        "cross_provider_path_groups": len(cross_provider),
        "direction_competition_groups": _direction_competition_count(groups),
        "reference_price_conflict_groups": reference_conflicts,
        "provider_overlap": _provider_overlap(cross_provider),
        "by_attribution": _by_attribution(groups, candles, horizons, hurdles),
        "horizons": {
            str(horizon): _horizon_summary(groups, candles, horizon, hurdles)
            for horizon in horizons
        },
        "limitations": [
            "deduplicated paths remain counterfactual and are not fills or PnL",
            "opposing directions remain separate hypotheses rather than duplicates",
            "reference-price conflicts are excluded from resolved path statistics",
            "independence is measured within each run, symbol, and direction",
        ],
    }


def _opportunity_groups(
    candidates: Sequence[SignalCandidate],
) -> tuple[_OpportunityGroup, ...]:
    grouped: dict[_GroupKey, _OpportunityGroup] = {}
    for candidate in candidates:
        if candidate.eligible or candidate.side is None or len(candidate.blockers) != 1:
            continue
        key = (
            candidate.source_run_id,
            candidate.symbol,
            candidate.decision_time_ms,
            candidate.side,
        )
        group = grouped.setdefault(
            key,
            _OpportunityGroup(
                candidate.source_run_id,
                candidate.symbol,
                candidate.decision_time_ms,
                candidate.side,
            ),
        )
        group.candidates.append(candidate)
    return tuple(sorted(grouped.values(), key=_group_sort_key))


def _group_sort_key(group: _OpportunityGroup) -> tuple[str, str, int, str]:
    return (
        group.source_run_id or "",
        group.symbol,
        group.decision_time_ms,
        group.side,
    )


def _provider_count(group: _OpportunityGroup) -> int:
    return len({candidate.strategy_id for candidate in group.candidates})


def _direction_competition_count(groups: Sequence[_OpportunityGroup]) -> int:
    sides: dict[tuple[str | None, str, int], set[str]] = defaultdict(set)
    for group in groups:
        key = (group.source_run_id, group.symbol, group.decision_time_ms)
        sides[key].add(group.side)
    return sum(len(values) > 1 for values in sides.values())


def _reference_consistent(group: _OpportunityGroup) -> bool:
    return len({candidate.reference_price for candidate in group.candidates}) == 1


def _provider_overlap(groups: Sequence[_OpportunityGroup]) -> list[dict[str, object]]:
    counts: Counter[tuple[_ProviderKey, ...]] = Counter()
    for group in groups:
        counts[_group_members(group)] += 1
    return [
        {
            "group_count": count,
            "providers": _provider_rows(members),
        }
        for members, count in sorted(counts.items())
    ]


def _by_attribution(
    groups: Sequence[_OpportunityGroup],
    candles: Mapping[str, Mapping[int, Candle]],
    horizons: Sequence[int],
    hurdles: OpportunityHurdles,
) -> list[dict[str, object]]:
    buckets: dict[_AttributionKey, list[_OpportunityGroup]] = defaultdict(list)
    for group in groups:
        key = (
            group.source_run_id,
            group.symbol,
            group.side,
            _group_members(group),
        )
        buckets[key].append(group)
    return [
        {
            "source_run_id": source_run_id,
            "symbol": symbol,
            "side": side,
            "path_groups": len(values),
            "decision_cadence": _decision_cadence(values),
            "providers": _provider_rows(members),
            "horizons": {
                str(horizon): _attribution_horizon_summary(
                    values, candles, horizon, hurdles
                )
                for horizon in horizons
            },
        }
        for (source_run_id, symbol, side, members), values in sorted(
            buckets.items(), key=_attribution_sort_key
        )
    ]


def _attribution_sort_key(
    item: tuple[_AttributionKey, list[_OpportunityGroup]],
) -> tuple[str, str, str, tuple[_ProviderKey, ...]]:
    source_run_id, symbol, side, members = item[0]
    return source_run_id or "", symbol, side, members


def _decision_cadence(groups: Sequence[_OpportunityGroup]) -> dict[str, object]:
    times = sorted({group.decision_time_ms for group in groups})
    if not times:
        raise ValueError("attribution cadence requires at least one opportunity group")
    episodes = _decision_episodes(groups)
    durations = [len(episode) for episode in episodes]
    minute_boundaries = (times[-1] - times[0]) // MINUTE_MS + 1
    intervals = [
        (later - earlier) / MINUTE_MS
        for earlier, later in zip(times, times[1:], strict=False)
    ]
    return {
        "coverage_rate": len(times) / minute_boundaries,
        "decision_minutes": len(times),
        "episode_count": len(episodes),
        "maximum_episode_duration_minutes": max(durations),
        "maximum_interval_minutes": max(intervals) if intervals else None,
        "median_episode_duration_minutes": float(median(durations)),
        "median_interval_minutes": median(intervals) if intervals else None,
        "minute_boundaries_in_span": minute_boundaries,
        "single_minute_episodes": sum(duration == 1 for duration in durations),
    }


def _decision_episodes(
    groups: Sequence[_OpportunityGroup],
) -> tuple[tuple[_OpportunityGroup, ...], ...]:
    ordered = sorted(groups, key=lambda group: group.decision_time_ms)
    episodes: list[tuple[_OpportunityGroup, ...]] = []
    current: list[_OpportunityGroup] = []
    for group in ordered:
        is_discontinuous = (
            bool(current)
            and group.decision_time_ms - current[-1].decision_time_ms != MINUTE_MS
        )
        if is_discontinuous:
            episodes.append(tuple(current))
            current = []
        current.append(group)
    if current:
        episodes.append(tuple(current))
    return tuple(episodes)


def _group_members(group: _OpportunityGroup) -> tuple[_ProviderKey, ...]:
    return tuple(
        sorted(
            {
                (candidate.strategy_id, candidate.blockers[0])
                for candidate in group.candidates
            }
        )
    )


def _provider_rows(members: Sequence[_ProviderKey]) -> list[dict[str, str]]:
    return [
        {"strategy_id": strategy_id, "blocker": blocker}
        for strategy_id, blocker in members
    ]


def _horizon_summary(
    groups: Sequence[_OpportunityGroup],
    candles: Mapping[str, Mapping[int, Candle]],
    horizon: int,
    hurdles: OpportunityHurdles,
) -> dict[str, object]:
    outcomes: list[tuple[_OpportunityGroup, DirectionalPath]] = []
    censored = 0
    missing = 0
    conflicts = 0
    for group in groups:
        status, path = _resolve_group(group, candles, horizon)
        if status == "reference_price_conflict":
            conflicts += 1
        elif status == "censored":
            censored += 1
        elif status == "missing_data":
            missing += 1
        elif path is not None:
            outcomes.append((group, path))
    paths = [path for _, path in outcomes]
    independent = _independent_paths(outcomes, horizon)
    return {
        "resolved": len(paths),
        "non_overlapping_resolved": len(independent),
        "censored": censored,
        "missing_data": missing,
        "reference_price_conflicts": conflicts,
        "opportunity_capture": summarize_path_opportunities(paths, hurdles),
        "independent_opportunity_capture": summarize_path_opportunities(
            independent, hurdles
        ),
    }


def _attribution_horizon_summary(
    groups: Sequence[_OpportunityGroup],
    candles: Mapping[str, Mapping[int, Candle]],
    horizon: int,
    hurdles: OpportunityHurdles,
) -> dict[str, object]:
    summary = _horizon_summary(groups, candles, horizon, hurdles)
    outcomes = _resolved_outcomes(groups, candles, horizon)
    summary["independent_paths"] = [
        _path_evidence(group, path)
        for group, path in _independent_outcomes(outcomes, horizon)
    ]
    summary["episode_onsets"] = _episode_onset_horizon_summary(
        groups, candles, horizon, hurdles
    )
    return summary


def _episode_onset_horizon_summary(
    groups: Sequence[_OpportunityGroup],
    candles: Mapping[str, Mapping[int, Candle]],
    horizon: int,
    hurdles: OpportunityHurdles,
) -> dict[str, object]:
    onsets = tuple(episode[0] for episode in _decision_episodes(groups))
    summary = _horizon_summary(onsets, candles, horizon, hurdles)
    outcomes = _resolved_outcomes(onsets, candles, horizon)
    summary["independent_paths"] = [
        _path_evidence(group, path)
        for group, path in _independent_outcomes(outcomes, horizon)
    ]
    return summary


def _resolved_outcomes(
    groups: Sequence[_OpportunityGroup],
    candles: Mapping[str, Mapping[int, Candle]],
    horizon: int,
) -> list[tuple[_OpportunityGroup, DirectionalPath]]:
    outcomes: list[tuple[_OpportunityGroup, DirectionalPath]] = []
    for group in groups:
        _, path = _resolve_group(group, candles, horizon)
        if path is not None:
            outcomes.append((group, path))
    return outcomes


def _path_evidence(
    group: _OpportunityGroup, path: DirectionalPath
) -> dict[str, object]:
    return {
        "source_run_id": group.source_run_id,
        "decision_time_ms": group.decision_time_ms,
        "reference_price": group.candidates[0].reference_price,
        "directional_close_return_bps": path.directional_close_return_bps,
        "favorable_excursion_bps": path.favorable_excursion_bps,
        "adverse_excursion_bps": path.adverse_excursion_bps,
    }


def _resolve_group(
    group: _OpportunityGroup,
    candles: Mapping[str, Mapping[int, Candle]],
    horizon: int,
) -> tuple[str, DirectionalPath | None]:
    if not _reference_consistent(group):
        return "reference_price_conflict", None
    candidate = group.candidates[0]
    return resolve_directional_path(
        decision_time_ms=group.decision_time_ms,
        reference_price=candidate.reference_price,
        side=group.side,
        candles=candles.get(group.symbol, {}),
        horizon_minutes=horizon,
    )


def _independent_paths(
    outcomes: Sequence[tuple[_OpportunityGroup, DirectionalPath]], horizon: int
) -> tuple[DirectionalPath, ...]:
    return tuple(path for _, path in _independent_outcomes(outcomes, horizon))


def _independent_outcomes(
    outcomes: Sequence[tuple[_OpportunityGroup, DirectionalPath]], horizon: int
) -> tuple[tuple[_OpportunityGroup, DirectionalPath], ...]:
    buckets: dict[tuple[str | None, str, str], list[DirectionalPath]] = defaultdict(
        list
    )
    indexed: dict[
        tuple[str | None, str, str], list[tuple[_OpportunityGroup, DirectionalPath]]
    ] = defaultdict(list)
    for group, path in outcomes:
        key = (group.source_run_id, group.symbol, group.side)
        buckets[key].append(path)
        indexed[key].append((group, path))
    selected: list[tuple[_OpportunityGroup, DirectionalPath]] = []
    for key in sorted(buckets, key=lambda value: (value[0] or "", *value[1:])):
        selected_times = {
            path.decision_time_ms
            for path in non_overlapping_paths(buckets[key], horizon)
        }
        selected.extend(
            item for item in indexed[key] if item[1].decision_time_ms in selected_times
        )
    return tuple(selected)
