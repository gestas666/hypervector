"""Prospective no-submit journal for the frozen HYPE L2 Ridge model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Literal, Mapping, cast

from hypervector.data.hl_events import L2SnapshotEvent
from hypervector.data.hl_rest_l2_recorder import REST_L2_SOURCE
from hypervector.ml.hype_l2_ridge_bundle import HypeL2RidgeBundle
from hypervector.research.hype_entry_l2_features import (
    hype_l2_features_at_decision,
)

_STRATEGY = "hype_breakout_onset_bidirectional_v1"
_WINDOW_MS = 60_000
_BUFFER_MS = 180_000
_MINIMUM_BOOKS = 50
_MAXIMUM_BOUNDARY_AGE_MS = 2_000
_MAXIMUM_INTERVAL_MS = 2_500
EntrySide = Literal["long", "short"]


@dataclass(frozen=True)
class _EntryDecision:
    run_id: str
    sequence: int
    decision_time_ms: int
    observed_at_utc: str
    side: EntrySide
    strategy_id: str


class HypeL2ProspectiveObserver:
    """Tail future HYPE entries and append causal Ridge annotations only."""

    def __init__(
        self,
        *,
        bundle: HypeL2RidgeBundle,
        bundle_sha256: str,
        decision_ledger: Path,
        cursor_path: Path,
        journal_path: Path,
    ) -> None:
        if len(bundle_sha256) != 64 or not _is_hex(bundle_sha256):
            raise ValueError("HYPE L2 observer bundle SHA-256 is invalid")
        if not decision_ledger.is_file():
            raise FileNotFoundError(
                f"HYPE decision ledger is missing: {decision_ledger}"
            )
        self._bundle = bundle
        self._bundle_sha256 = bundle_sha256
        self._ledger = decision_ledger
        self._cursor = cursor_path
        self._journal = journal_path
        self._events: list[L2SnapshotEvent] = []
        self._offset = self._load_or_initialize_cursor()

    def observe(self, event: L2SnapshotEvent) -> tuple[dict[str, object], ...]:
        """Retain one book and score any newly journaled future entries."""
        self._accept_book(event)
        rows = tuple(
            self._score(decision)
            for value in self._read_new_ledger_rows()
            if (decision := _entry_decision(value)) is not None
        )
        for row in rows:
            self._append_journal(row)
        return rows

    def warm(self, event: L2SnapshotEvent) -> None:
        """Warm the causal book buffer without advancing the decision cursor."""
        self._accept_book(event)

    def _accept_book(self, event: L2SnapshotEvent) -> None:
        if event.symbol != "HYPE" or event.source != REST_L2_SOURCE:
            raise ValueError("HYPE L2 observer accepts only isolated REST HYPE books")
        if self._events and event.exchange_ts_ms <= self._events[-1].exchange_ts_ms:
            raise ValueError("HYPE L2 observer books must be strictly ordered")
        self._events.append(event)
        cutoff = event.exchange_ts_ms - _BUFFER_MS
        self._events = [
            value for value in self._events if value.exchange_ts_ms >= cutoff
        ]

    def _score(self, decision: _EntryDecision) -> dict[str, object]:
        coverage, reason = self._coverage(decision.decision_time_ms)
        base = _journal_base(decision, self._bundle_sha256, coverage)
        if reason is not None:
            return {**base, "status": "coverage_unavailable", "reason": reason}
        features = hype_l2_features_at_decision(
            self._events,
            decision_time_ms=decision.decision_time_ms,
            side=decision.side,
        )
        score = self._bundle.score(features)
        percentile = self._bundle.score_percentile(features)
        return {
            **base,
            "status": "scored",
            "predicted_gross_return_bps": score,
            "training_score_percentile": percentile,
            "score_band": _score_band(percentile),
            "features": features,
        }

    def _coverage(self, decision_ms: int) -> tuple[dict[str, object], str | None]:
        selected = [
            event
            for event in self._events
            if decision_ms - _WINDOW_MS <= event.exchange_ts_ms < decision_ms
        ]
        if not selected:
            return {"books": 0}, "snapshot_count=0"
        timestamps = [event.exchange_ts_ms for event in selected]
        intervals = [right - left for left, right in zip(timestamps, timestamps[1:])]
        coverage: dict[str, object] = {
            "books": len(selected),
            "first_exchange_ts_ms": timestamps[0],
            "last_exchange_ts_ms": timestamps[-1],
            "start_boundary_age_ms": timestamps[0] - (decision_ms - _WINDOW_MS),
            "end_boundary_age_ms": decision_ms - timestamps[-1],
            "maximum_interval_ms": max(intervals, default=0),
        }
        reason = _coverage_reason(coverage)
        return coverage, reason

    def _read_new_ledger_rows(self) -> tuple[Mapping[str, object], ...]:
        rows: list[Mapping[str, object]] = []
        with self._ledger.open("rb") as handle:
            handle.seek(self._offset)
            while line := handle.readline():
                if not line.endswith(b"\n"):
                    handle.seek(-len(line), os.SEEK_CUR)
                    break
                value: object = json.loads(line)
                rows.append(_mapping(value, "decision ledger row"))
            self._offset = handle.tell()
        self._write_cursor()
        return tuple(rows)

    def _load_or_initialize_cursor(self) -> int:
        stat = self._ledger.stat()
        if not self._cursor.exists():
            self._offset = stat.st_size
            self._write_cursor()
            return stat.st_size
        payload = _mapping(
            json.loads(self._cursor.read_text(encoding="utf-8")), "cursor"
        )
        identity = (payload.get("device"), payload.get("inode"))
        if identity != (stat.st_dev, stat.st_ino):
            raise ValueError("HYPE L2 observer decision ledger identity changed")
        offset = payload.get("offset")
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise ValueError("HYPE L2 observer cursor offset is invalid")
        if offset < 0 or offset > stat.st_size:
            raise ValueError("HYPE L2 observer cursor exceeds decision ledger")
        return offset

    def _write_cursor(self) -> None:
        stat = self._ledger.stat()
        payload = {
            "schema_version": 1,
            "mode": "hype_l2_prospective_observer_cursor",
            "ledger_path": str(self._ledger.resolve()),
            "device": stat.st_dev,
            "inode": stat.st_ino,
            "offset": self._offset,
            "execution_authority": "none",
        }
        _atomic_json(self._cursor, payload)

    def _append_journal(self, row: dict[str, object]) -> None:
        self._journal.parent.mkdir(parents=True, exist_ok=True)
        with self._journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def _entry_decision(value: Mapping[str, object]) -> _EntryDecision | None:
    if value.get("event_type") != "regime_decision":
        return None
    payload = _mapping(value.get("payload"), "regime decision payload")
    relevant = (
        payload.get("routing_action") == "enter"
        and payload.get("symbol") == "HYPE"
        and payload.get("strategy_id") == _STRATEGY
    )
    if not relevant:
        return None
    side = payload.get("side")
    if side not in {"long", "short"}:
        raise ValueError("HYPE L2 prospective entry side is invalid")
    return _EntryDecision(
        run_id=_text(value.get("run_id"), "run_id"),
        sequence=_integer(value.get("sequence"), "sequence"),
        decision_time_ms=_integer(payload.get("decision_time_ms"), "decision_time_ms"),
        observed_at_utc=_text(value.get("observed_at_utc"), "observed_at_utc"),
        side=cast(EntrySide, side),
        strategy_id=_STRATEGY,
    )


def _coverage_reason(coverage: Mapping[str, object]) -> str | None:
    books = _integer(coverage.get("books"), "books")
    start = _integer(coverage.get("start_boundary_age_ms"), "start age")
    end = _integer(coverage.get("end_boundary_age_ms"), "end age")
    interval = _integer(coverage.get("maximum_interval_ms"), "maximum interval")
    if books < _MINIMUM_BOOKS:
        return f"snapshot_count={books}<{_MINIMUM_BOOKS}"
    if start > _MAXIMUM_BOUNDARY_AGE_MS:
        return f"start_boundary_age_ms={start}>{_MAXIMUM_BOUNDARY_AGE_MS}"
    if end > _MAXIMUM_BOUNDARY_AGE_MS:
        return f"end_boundary_age_ms={end}>{_MAXIMUM_BOUNDARY_AGE_MS}"
    if interval > _MAXIMUM_INTERVAL_MS:
        return f"maximum_interval_ms={interval}>{_MAXIMUM_INTERVAL_MS}"
    return None


def _journal_base(
    decision: _EntryDecision,
    bundle_sha256: str,
    coverage: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_l2_ridge_prospective_observe_v1",
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
        "run_id": decision.run_id,
        "ledger_sequence": decision.sequence,
        "decision_time_ms": decision.decision_time_ms,
        "decision_observed_at_utc": decision.observed_at_utc,
        "scored_at_utc": datetime.now(UTC).isoformat(),
        "side": decision.side,
        "strategy_id": decision.strategy_id,
        "bundle_sha256": bundle_sha256,
        "coverage": dict(coverage),
    }


def _score_band(percentile: float) -> str:
    if percentile >= 0.8:
        return "top_20pct_annotation"
    if percentile <= 0.2:
        return "bottom_20pct_annotation"
    return "middle_60pct_annotation"


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(raw, path)
    finally:
        Path(raw).unlink(missing_ok=True)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HYPE L2 observer {label} must be an object")
    return cast(dict[str, object], value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"HYPE L2 observer {label} must be an integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"HYPE L2 observer {label} must be text")
    return value


def _is_hex(value: str) -> bool:
    return all(character in "0123456789abcdef" for character in value)
