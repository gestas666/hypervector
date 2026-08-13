"""Report-only provider episode and re-entry attribution."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from hypervector.research.cohort_provider_episode_reporting import (
    build_coverage,
    build_open_report,
    build_resolved_report,
    marked_economics,
    report_contract,
    report_limitations,
    resolved_economics,
)
from hypervector.research.cohort_provider_episode_values import (
    boolean as _boolean,
    cadence_ms as _cadence_ms,
    choice as _choice,
    integer as _integer,
    mapping as _mapping,
    optional_integer as _optional_integer,
    optional_mapping as _optional_mapping,
    optional_text as _optional_text,
    sequence as _sequence,
    technical_boundary as _technical_boundary,
    text as _text,
)

Record = Mapping[str, object]
_SIDES = frozenset({"long", "short"})
_ENTRY_MODES = frozenset({"state", "onset"})
_HIP3_SWING_STRATEGIES = frozenset(
    {
        "hip3_swing_ha_sp500_spcx_bidirectional_v2",
        "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
    }
)
_CONFIRMATION_BLOCKERS = frozenset(
    {
        "ema_alignment_missing",
        "pivot_break_state_missing",
        "heikin_ashi_color_mismatch",
        "order_block_agreement_missing",
    }
)


@dataclass(frozen=True)
class _Observation:
    strategy_id: str
    symbol: str
    decision_time_ms: int
    side: str
    aligned: bool
    entry_mode: str
    profile_fingerprint: str
    cadence_ms: int
    run_ids: tuple[str, ...]


@dataclass
class _Episode:
    strategy_id: str
    symbol: str
    side: str
    profile_fingerprint: str
    start_decision_time_ms: int
    end_decision_time_ms: int
    decision_count: int = 1
    run_ids: set[str] = field(default_factory=set)

    @property
    def episode_id(self) -> str:
        """Return a deterministic source/profile/onset identity."""
        return (
            f"{self.strategy_id}|{self.symbol}|{self.side}|"
            f"{self.start_decision_time_ms}|{self.profile_fingerprint}"
        )

    def as_record(self) -> dict[str, object]:
        """Serialize bounded episode evidence."""
        run_ids = sorted(self.run_ids)
        return {
            "episode_id": self.episode_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "profile_fingerprint": self.profile_fingerprint,
            "start_decision_time_ms": self.start_decision_time_ms,
            "end_decision_time_ms": self.end_decision_time_ms,
            "decision_count": self.decision_count,
            "run_ids": run_ids,
            "restart_spanning": len(run_ids) > 1,
        }


@dataclass(frozen=True)
class _EntryCandidate:
    kind: str
    trade: Record
    lifecycle_id: str
    source_run_id: str | None
    strategy_id: str
    symbol: str
    side: str
    decision_time_ms: int | None
    episode: _Episode | None
    unavailable_reason: str | None


def build_provider_episode_reentry(
    cohort_records: Sequence[Record],
    closed_trades: Sequence[Record],
    *,
    open_trades: Sequence[Record] = (),
) -> dict[str, object]:
    """Attribute live HIP-3 entries to causal state episodes and ordinals."""
    observations, raw_count, unavailable, boundaries, missing = _collect_observations(
        cohort_records
    )
    deduplicated = _deduplicate_observations(observations)
    episodes, lookup, gap_resets = _build_episodes(deduplicated)
    profile_resets = _profile_boundary_resets(deduplicated)
    candidates = _entry_candidates(closed_trades, open_trades, lookup)
    attributed = _attributed_rows(candidates)
    resolved_rows = [row for row in attributed if row["entry_status"] == "resolved"]
    open_rows = [row for row in attributed if row["entry_status"] == "open"]
    return {
        "schema_version": 1,
        "mode": "provider_alignment_episode_reentry_v1",
        "scope": "all_live_history_mixed_profiles",
        "contract": report_contract(),
        "evaluation_coverage": build_coverage(
            raw_count,
            len(deduplicated),
            unavailable,
            boundaries,
            missing,
            [len(row.run_ids) for row in episodes],
            profile_resets,
            gap_resets,
        ),
        "episodes": [row.as_record() for row in episodes],
        "resolved": build_resolved_report(resolved_rows),
        "provisional_open": build_open_report(open_rows),
        "limitations": report_limitations(),
    }


def _collect_observations(
    records: Sequence[Record],
) -> tuple[list[_Observation], int, int, int, int]:
    observations: list[_Observation] = []
    matching_rows = 0
    unavailable_rows = 0
    technical_boundaries = 0
    missing_evaluations = 0
    for record in records:
        if record.get("event_type") != "intent_routing":
            continue
        payload = _mapping(record.get("payload"), "routing payload")
        raw = payload.get("evaluations")
        if raw is None:
            missing_evaluations += 1
            continue
        evaluations = _sequence(raw, "provider evaluations")
        for value in evaluations:
            evaluation = _mapping(value, "provider evaluation")
            if evaluation.get("strategy_id") not in _HIP3_SWING_STRATEGIES:
                continue
            matching_rows += 1
            observation = _observation(record, evaluation)
            if observation is None:
                unavailable_rows += 1
            else:
                observations.append(observation)
                technical_boundaries += int(_technical_boundary(evaluation))
    return (
        observations,
        matching_rows,
        unavailable_rows,
        technical_boundaries,
        missing_evaluations,
    )


def _observation(record: Record, evaluation: Record) -> _Observation | None:
    required = (
        record.get("run_id"),
        record.get("profile_fingerprint"),
        evaluation.get("symbol"),
        evaluation.get("decision_time_ms"),
        evaluation.get("eligible"),
        evaluation.get("readiness"),
    )
    if any(value is None for value in required):
        return None
    readiness = _mapping(evaluation.get("readiness"), "provider readiness")
    metrics_value = readiness.get("metrics")
    blockers_value = readiness.get("blockers")
    if metrics_value is None or blockers_value is None:
        return None
    metrics = _mapping(metrics_value, "provider metrics")
    entry_mode = metrics.get("entry_mode")
    timeframe = metrics.get("source_timeframe")
    side_value = evaluation.get("side") or readiness.get("side")
    if entry_mode is None or timeframe is None or side_value is None:
        return None
    side = _choice(side_value, _SIDES, "provider side")
    readiness_side = readiness.get("side")
    if (
        readiness_side is not None
        and _choice(readiness_side, _SIDES, "readiness side") != side
    ):
        raise ValueError("provider evaluation and readiness sides conflict")
    blockers = tuple(
        _text(value, "provider blocker")
        for value in _sequence(blockers_value, "provider blockers")
    )
    eligible = _boolean(evaluation.get("eligible"), "provider eligibility")
    mode = _choice(entry_mode, _ENTRY_MODES, "provider entry mode")
    aligned = _native_alignment(mode, eligible, blockers)
    if aligned is None:
        return None
    profile = _text(record.get("profile_fingerprint"), "profile fingerprint")
    return _Observation(
        strategy_id=_text(evaluation.get("strategy_id"), "strategy id"),
        symbol=_text(evaluation.get("symbol"), "symbol"),
        decision_time_ms=_integer(evaluation.get("decision_time_ms"), "decision time"),
        side=side,
        aligned=aligned,
        entry_mode=mode,
        profile_fingerprint=profile,
        cadence_ms=_cadence_ms(_text(timeframe, "source timeframe")),
        run_ids=(_text(record.get("run_id"), "run id"),),
    )


def _native_alignment(
    entry_mode: str, eligible: bool, blockers: Sequence[str]
) -> bool | None:
    if eligible:
        return True
    if "indicator_warmup" in blockers:
        return False
    if entry_mode == "state":
        return False
    if any(blocker in _CONFIRMATION_BLOCKERS for blocker in blockers):
        return False
    if "fresh_entry_onset_absent" in blockers:
        return True
    return None


def _deduplicate_observations(
    observations: Sequence[_Observation],
) -> list[_Observation]:
    grouped: dict[tuple[str, str, str, int], _Observation] = {}
    for row in observations:
        key = (
            row.strategy_id,
            row.symbol,
            row.profile_fingerprint,
            row.decision_time_ms,
        )
        prior = grouped.get(key)
        if prior is None:
            grouped[key] = row
            continue
        if replace(prior, run_ids=row.run_ids) != row:
            raise ValueError("conflicting provider decision for one causal identity")
        grouped[key] = _Observation(
            **{
                **row.__dict__,
                "run_ids": tuple(sorted(set(prior.run_ids) | set(row.run_ids))),
            }
        )
    return sorted(
        grouped.values(),
        key=lambda row: (
            row.strategy_id,
            row.symbol,
            row.profile_fingerprint,
            row.decision_time_ms,
        ),
    )


def _build_episodes(
    observations: Sequence[_Observation],
) -> tuple[
    list[_Episode],
    dict[tuple[str, str, str, int], _Episode],
    int,
]:
    grouped: defaultdict[tuple[str, str, str], list[_Observation]] = defaultdict(list)
    for row in observations:
        grouped[(row.strategy_id, row.symbol, row.profile_fingerprint)].append(row)
    episodes: list[_Episode] = []
    lookup: dict[tuple[str, str, str, int], _Episode] = {}
    gap_resets = 0
    for rows in grouped.values():
        created, created_lookup, resets = _group_episodes(
            sorted(rows, key=lambda row: row.decision_time_ms)
        )
        episodes.extend(created)
        gap_resets += resets
        for key, episode in created_lookup.items():
            if key in lookup and lookup[key].episode_id != episode.episode_id:
                raise ValueError("provider run decision maps to conflicting episodes")
            lookup[key] = episode
    episodes.sort(key=lambda row: (row.start_decision_time_ms, row.episode_id))
    return episodes, lookup, gap_resets


def _group_episodes(
    rows: Sequence[_Observation],
) -> tuple[list[_Episode], dict[tuple[str, str, str, int], _Episode], int]:
    episodes: list[_Episode] = []
    lookup: dict[tuple[str, str, str, int], _Episode] = {}
    active: _Episode | None = None
    previous: _Observation | None = None
    gap_resets = 0
    for row in rows:
        gap = (
            previous is not None
            and row.decision_time_ms - previous.decision_time_ms != row.cadence_ms
        )
        if gap:
            gap_resets += int(active is not None and row.aligned)
            active = None
        if not row.aligned:
            active = None
        elif active is None or active.side != row.side:
            active = _new_episode(row)
            episodes.append(active)
        else:
            active.end_decision_time_ms = row.decision_time_ms
            active.decision_count += 1
            active.run_ids.update(row.run_ids)
        if active is not None:
            for run_id in row.run_ids:
                lookup[(run_id, row.strategy_id, row.symbol, row.decision_time_ms)] = (
                    active
                )
        previous = row
    return episodes, lookup, gap_resets


def _new_episode(row: _Observation) -> _Episode:
    return _Episode(
        strategy_id=row.strategy_id,
        symbol=row.symbol,
        side=row.side,
        profile_fingerprint=row.profile_fingerprint,
        start_decision_time_ms=row.decision_time_ms,
        end_decision_time_ms=row.decision_time_ms,
        run_ids=set(row.run_ids),
    )


def _profile_boundary_resets(observations: Sequence[_Observation]) -> int:
    grouped: defaultdict[tuple[str, str], list[_Observation]] = defaultdict(list)
    for row in observations:
        grouped[(row.strategy_id, row.symbol)].append(row)
    resets = 0
    for rows in grouped.values():
        ordered = sorted(rows, key=lambda row: row.decision_time_ms)
        resets += sum(
            prior.aligned
            and current.aligned
            and prior.profile_fingerprint != current.profile_fingerprint
            for prior, current in zip(ordered, ordered[1:])
        )
    return resets


def _entry_candidates(
    closed: Sequence[Record],
    opened: Sequence[Record],
    lookup: Mapping[tuple[str, str, str, int], _Episode],
) -> list[_EntryCandidate]:
    candidates: list[_EntryCandidate] = []
    identities: set[str] = set()
    for kind, rows in (("resolved", closed), ("open", opened)):
        for trade in rows:
            if trade.get("strategy_id") not in _HIP3_SWING_STRATEGIES:
                continue
            candidate = _entry_candidate(kind, trade, lookup)
            if candidate.lifecycle_id in identities:
                raise ValueError("duplicate lifecycle in provider episode attribution")
            identities.add(candidate.lifecycle_id)
            candidates.append(candidate)
    return candidates


def _entry_candidate(
    kind: str,
    trade: Record,
    lookup: Mapping[tuple[str, str, str, int], _Episode],
) -> _EntryCandidate:
    lifecycle = _text(trade.get("lifecycle_id"), "lifecycle id")
    strategy = _text(trade.get("strategy_id"), "strategy id")
    symbol = _text(trade.get("symbol"), "symbol")
    side = _choice(trade.get("side"), _SIDES, "trade side")
    source_run = _optional_text(trade.get("source_run_id"), "source run id")
    provider = _provider_context(trade)
    decision = _optional_integer(
        provider.get("decision_time_ms"), "entry decision time"
    )
    episode = None
    reason = "no_exact_provider_episode_evidence"
    if source_run is not None and decision is not None:
        episode = lookup.get((source_run, strategy, symbol, decision))
    if episode is not None:
        if episode.side != side:
            raise ValueError("provider episode side conflicts with executed lifecycle")
        source_profile = _optional_text(
            trade.get("source_profile_fingerprint"), "source profile fingerprint"
        )
        if source_profile is not None and source_profile != episode.profile_fingerprint:
            raise ValueError("provider episode profile conflicts with lifecycle source")
        reason = None
    return _EntryCandidate(
        kind,
        trade,
        lifecycle,
        source_run,
        strategy,
        symbol,
        side,
        decision,
        episode,
        reason,
    )


def _attributed_rows(candidates: Sequence[_EntryCandidate]) -> list[dict[str, object]]:
    ordinals: Counter[str] = Counter()
    rows: list[dict[str, object]] = []
    ordered = sorted(
        candidates,
        key=lambda row: (
            row.decision_time_ms if row.decision_time_ms is not None else math.inf,
            row.lifecycle_id,
        ),
    )
    for candidate in ordered:
        ordinal = None
        if candidate.episode is not None:
            ordinals[candidate.episode.episode_id] += 1
            ordinal = ordinals[candidate.episode.episode_id]
        rows.append(_attribution_row(candidate, ordinal))
    return rows


def _attribution_row(
    candidate: _EntryCandidate, ordinal: int | None
) -> dict[str, object]:
    episode_id = None if candidate.episode is None else candidate.episode.episode_id
    row: dict[str, object] = {
        "entry_status": candidate.kind,
        "lifecycle_id": candidate.lifecycle_id,
        "strategy_id": candidate.strategy_id,
        "symbol": candidate.symbol,
        "side": candidate.side,
        "source_run_id": candidate.source_run_id,
        "decision_time_ms": candidate.decision_time_ms,
        "attribution_status": "attributed" if episode_id is not None else "unavailable",
        "unavailable_reason": candidate.unavailable_reason,
        "episode_id": episode_id,
        "reentry_ordinal": ordinal,
        "entry_class": None
        if ordinal is None
        else "first_entry"
        if ordinal == 1
        else "repeat_entry",
    }
    if candidate.kind == "resolved":
        row.update(resolved_economics(candidate.trade))
    else:
        row.update(marked_economics(candidate.trade))
    return row


def _provider_context(trade: Record) -> Record:
    entry = _optional_mapping(trade.get("entry_context"), "entry context")
    provider = _optional_mapping(entry.get("signal_provider"), "signal provider")
    strategy = provider.get("strategy_id")
    if strategy is not None and strategy != trade.get("strategy_id"):
        raise ValueError("signal-provider strategy conflicts with lifecycle")
    return provider
