"""Development-only evidence binding for BTC liquidation covariate replay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from hypervector.research.btc_liquidation_covariate_inputs import ArchiveHour
from hypervector.research.btc_liquidation_covariate_models import ReplayEpisode
from hypervector.research.btc_liquidation_covariate_windows import (
    MergedCovariateWindow,
)

_MODE = "v58_btc_liquidation_covariate_acquisition_plan"
_DEVELOPMENT_START_MS = 1_764_547_200_000
_DEVELOPMENT_END_MS = 1_780_272_000_000
_BRANCHES = frozenset({"continuation_long", "exhaustion_reclaim_long"})
_ARMS = frozenset({"5s_p95", "5s_p99", "15s_p95", "15s_p99"})


def development_windows(
    plan: Mapping[str, object],
) -> tuple[MergedCovariateWindow, ...]:
    """Select and validate only the frozen development plan windows."""
    _require_outcome_blind_plan(plan)
    _require_development_partition(plan.get("partitions"))
    rows = _sequence(plan.get("windows"), "plan windows")
    windows = tuple(
        _window(row)
        for row in rows
        if _mapping(row, "plan window").get("partition") == "development"
    )
    if not windows:
        raise ValueError("development plan contains no windows")
    ordered = tuple(sorted(windows, key=lambda row: (row.start_ms, row.end_ms)))
    if ordered != windows or any(
        prior.end_ms >= current.start_ms for prior, current in zip(ordered, ordered[1:])
    ):
        raise ValueError("development windows must be ordered and disjoint")
    episode_ids = tuple(identity for row in windows for identity in row.episode_ids)
    if len(episode_ids) != len(set(episode_ids)):
        raise ValueError("development windows contain duplicate episode identities")
    return windows


def bind_development_episodes(
    rows: tuple[Mapping[str, object], ...],
    windows: tuple[MergedCovariateWindow, ...],
) -> tuple[ReplayEpisode, ...]:
    """Bind outcome-blind treatment rows to exact development identities."""
    desired = tuple(identity for window in windows for identity in window.episode_ids)
    by_id: dict[str, Mapping[str, object]] = {}
    for row in rows:
        identity = _text(row.get("episode_id"), "treatment episode identity")
        if identity in by_id:
            raise ValueError("treatment rows contain duplicate episode identities")
        by_id[identity] = row
    if any(identity not in by_id for identity in desired):
        raise ValueError("treatment rows do not provide exact development coverage")
    episodes = tuple(_episode(by_id[identity]) for identity in desired)
    if tuple(row.episode_id for row in episodes) != desired:
        raise ValueError("development episode coverage does not reconcile")
    return episodes


def hours_for_window(
    hours: tuple[ArchiveHour, ...],
    window: MergedCovariateWindow,
    *,
    required_end_ms: int,
) -> tuple[ArchiveHour, ...]:
    """Return exact contiguous acquired hours covering a replay interval."""
    if required_end_ms <= window.start_ms:
        raise ValueError("required archive end must follow the window start")
    selected = tuple(
        sorted(
            (
                row
                for row in hours
                if row.start_ms < required_end_ms and row.end_ms > window.start_ms
            ),
            key=lambda row: row.start_ms,
        )
    )
    complete = (
        selected
        and selected[0].start_ms <= window.start_ms
        and selected[-1].end_ms >= required_end_ms
        and all(
            left.end_ms == right.start_ms for left, right in zip(selected, selected[1:])
        )
    )
    if not complete:
        raise ValueError("archive hours do not provide contiguous requested coverage")
    return selected


def _require_outcome_blind_plan(plan: Mapping[str, object]) -> None:
    contract = _mapping(plan.get("contract"), "plan contract")
    valid = (
        plan.get("schema_version") == 1
        and plan.get("mode") == _MODE
        and contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("strategy_outcomes_inspected") is False
    )
    if not valid:
        raise ValueError("covariate plan is not outcome-blind report-only evidence")


def _require_development_partition(value: object) -> None:
    partitions = _sequence(value, "plan partitions")
    matches = [
        _mapping(row, "plan partition")
        for row in partitions
        if _mapping(row, "plan partition").get("name") == "development"
    ]
    expected = {
        "name": "development",
        "start_ms": _DEVELOPMENT_START_MS,
        "end_ms": _DEVELOPMENT_END_MS,
    }
    if len(matches) != 1 or any(
        matches[0].get(key) != item for key, item in expected.items()
    ):
        raise ValueError("frozen development partition identity is invalid")


def _window(value: object) -> MergedCovariateWindow:
    row = _mapping(value, "development window")
    start_ms = _integer(row.get("start_ms"), "window start")
    end_ms = _integer(row.get("end_ms"), "window end")
    ids = tuple(
        _text(item, "window episode identity")
        for item in _sequence(row.get("episode_ids"), "window episode identities")
    )
    if (
        row.get("partition") != "development"
        or not _DEVELOPMENT_START_MS <= start_ms < end_ms <= _DEVELOPMENT_END_MS
        or not ids
    ):
        raise ValueError("development window identity or bounds are invalid")
    return MergedCovariateWindow("development", start_ms, end_ms, ids)


def _episode(row: Mapping[str, object]) -> ReplayEpisode:
    if (
        row.get("schema_version") != "btc_liquidation_treatment_episode_v1"
        or row.get("symbol") != "BTC"
    ):
        raise ValueError("treatment episode source identity is invalid")
    branch = _text(row.get("candidate_branch"), "candidate branch")
    if branch not in _BRANCHES:
        raise ValueError("candidate branch is unsupported")
    arms = tuple(
        _text(item, "eligible arm")
        for item in _sequence(row.get("eligible_arms"), "eligible arms")
    )
    if not arms or any(arm not in _ARMS for arm in arms):
        raise ValueError("eligible arms are invalid")
    return ReplayEpisode(
        episode_id=_text(row.get("episode_id"), "episode identity"),
        partition="development",
        branch=branch,
        end_ms=_integer(row.get("end_ms"), "episode end"),
        volume_weighted_price=Decimal(
            _text(row.get("volume_weighted_price"), "episode VWAP")
        ),
        eligible_arms=arms,
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be nonempty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
