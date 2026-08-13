"""Append-only monitoring for source-long counterfactual outcomes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, Protocol, cast

from hypervector.data.hl_event_stream import RecordedEvent
from hypervector.regime.source_follow_runtime import SourceLongRecipeId
from hypervector.research.source_follow_portfolio_models import (
    SourcePortfolioReplayConfig,
)
from hypervector.research.source_long_forward import (
    ForwardStatus,
    SourceLongForwardResult,
    SourceLongForwardSpec,
    evaluate_source_long_forward,
)

_RESOLVED_STATUSES: frozenset[ForwardStatus] = frozenset(
    {"no_fill", "target_completed", "time_exited", "liquidated"}
)


class RecordedEventArchive(Protocol):
    """Bounded persisted-event source required by the monitor."""

    def replay_window(
        self,
        start: datetime,
        end: datetime,
    ) -> tuple[RecordedEvent, ...]:
        """Return cross-channel evidence inside one UTC interval."""


@dataclass(frozen=True)
class ObservedLongCandidate:
    """One source observation plus account equity available at decision time."""

    spec: SourceLongForwardSpec
    initial_equity_usd: float
    source_run_id: str

    def __post_init__(self) -> None:
        if self.initial_equity_usd <= 0.0:
            raise ValueError("source-long observation equity must be positive")
        if not self.source_run_id.strip():
            raise ValueError("source-long observation run ID must be non-empty")


class SourceLongOutcomeLedger:
    """Deduplicate append-only point-in-time observer outcomes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fingerprints: dict[str, str] = {}
        self._resolved: set[str] = set()
        self._restore()

    def is_resolved(self, observation_id: str) -> bool:
        """Return whether a terminal outcome is already durable."""
        return observation_id in self._resolved

    def append_if_changed(
        self,
        candidate: ObservedLongCandidate,
        result: SourceLongForwardResult,
        recorded_at: datetime,
    ) -> dict[str, object] | None:
        """Append a changed projection and return the written row."""
        payload = {
            **result.to_dict(),
            "source_run_id": candidate.source_run_id,
            "counterfactual_initial_equity_usd": candidate.initial_equity_usd,
            "portfolio_interaction": "independent_observer_not_shared_execution",
        }
        fingerprint = _fingerprint(payload)
        if self._fingerprints.get(result.observation_id) == fingerprint:
            return None
        row: dict[str, object] = {
            "schema_version": 1,
            "event_type": "source_long_forward_outcome",
            "observed_at_utc": _utc(recorded_at).isoformat(),
            "execution_authority": "none",
            "payload": payload,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
        self._fingerprints[result.observation_id] = fingerprint
        if result.status in _RESOLVED_STATUSES:
            self._resolved.add(result.observation_id)
        return row

    def _restore(self) -> None:
        if not self._path.is_file():
            return
        for row in _jsonl_rows(self._path):
            if row.get("event_type") != "source_long_forward_outcome":
                continue
            payload = _mapping(row.get("payload"), "outcome payload")
            identity = _text(payload, "observation_id")
            status = _text(payload, "status")
            self._fingerprints[identity] = _fingerprint(payload)
            if status in _RESOLVED_STATUSES:
                self._resolved.add(identity)


class SourceLongForwardMonitor:
    """Resolve new observe-only long labels from persisted venue evidence."""

    def __init__(
        self,
        *,
        backend_ledger: Path,
        archive: RecordedEventArchive,
        outcome_ledger: SourceLongOutcomeLedger,
        base_config: SourcePortfolioReplayConfig,
    ) -> None:
        self._backend_ledger = backend_ledger
        self._archive = archive
        self._outcomes = outcome_ledger
        self._base_config = base_config

    def poll(self, observed_at: datetime) -> tuple[dict[str, object], ...]:
        """Evaluate every unresolved observation through current durable tape."""
        now = _utc(observed_at)
        rows: list[dict[str, object]] = []
        for candidate in discover_source_long_candidates(self._backend_ledger):
            identity = candidate.spec.observation_id
            if self._outcomes.is_resolved(identity):
                continue
            signal_at = _parse_utc(candidate.spec.signal_time_utc)
            if signal_at >= now:
                continue
            events = self._archive.replay_window(signal_at, now)
            config = replace(
                self._base_config,
                initial_equity=candidate.initial_equity_usd,
            )
            result = evaluate_source_long_forward(events, candidate.spec, config)
            row = self._outcomes.append_if_changed(candidate, result, now)
            if row is not None:
                rows.append(row)
        return tuple(rows)


def discover_source_long_candidates(
    backend_ledger: Path,
) -> tuple[ObservedLongCandidate, ...]:
    """Extract unique exact source-long labels with causal account equity."""
    if not backend_ledger.is_file():
        raise FileNotFoundError(f"backend ledger is missing: {backend_ledger}")
    equity: float | None = None
    candidates: dict[str, ObservedLongCandidate] = {}
    for row in _jsonl_rows(backend_ledger):
        payload = _mapping(row.get("payload"), "backend payload")
        if row.get("event_type") == "reconciliation":
            equity = _positive_number(payload, "account_value_usd")
            continue
        observer = payload.get("source_long_observer")
        if row.get("event_type") != "regime_decision" or observer is None:
            continue
        if equity is None:
            raise ValueError("source-long observation has no prior account equity")
        candidate = _candidate(
            row, payload, _mapping(observer, "long observer"), equity
        )
        candidates.setdefault(candidate.spec.observation_id, candidate)
    return tuple(candidates.values())


def _candidate(
    row: Mapping[str, object],
    payload: Mapping[str, object],
    observer: Mapping[str, object],
    equity: float,
) -> ObservedLongCandidate:
    if _text(observer, "side") != "long":
        raise ValueError("source-long observer side must be long")
    if _text(observer, "authority") != "observe_only":
        raise ValueError("source-long observer authority must be observe_only")
    recipe = _text(observer, "recipe_id")
    if recipe not in {
        "bk_up_asia_conf06",
        "fade_td_eu",
        "bk_up_24h_challenger",
        "trend_up_24h_challenger",
        "trend_down_24h_direction_challenger",
    }:
        raise ValueError(f"unsupported source-long recipe {recipe!r}")
    spec = SourceLongForwardSpec(
        recipe_id=cast(SourceLongRecipeId, recipe),
        signal_time_utc=_text(payload, "available_at_utc"),
        maximum_hold_seconds=_positive_number(observer, "maximum_hold_seconds"),
    )
    return ObservedLongCandidate(spec, equity, _text(row, "run_id"))


def _jsonl_rows(path: Path) -> tuple[Mapping[str, object], ...]:
    rows: list[Mapping[str, object]] = []
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value: object = json.loads(line)
        except json.JSONDecodeError as exc:
            is_in_progress_tail = line_number == len(lines) and not content.endswith(
                "\n"
            )
            if is_in_progress_tail:
                break
            raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
        rows.append(_mapping(value, f"JSONL row {line_number}"))
    return tuple(rows)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _positive_number(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    result = float(value)
    if result <= 0.0:
        raise ValueError(f"{key} must be positive")
    return result


def _fingerprint(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _parse_utc(value: str) -> datetime:
    return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("forward monitor timestamps must be timezone-aware")
    return value.astimezone(UTC)
