"""Run the standalone report-only HYPE L2 Ridge prospective observer."""

from __future__ import annotations

import argparse
import json
import os
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
from types import FrameType
from typing import Protocol

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_events import L2SnapshotEvent
from hypervector.data.hl_rest_l2_recorder import REST_L2_SOURCE
from hypervector.data.oxa_storage import file_evidence
from hypervector.ml.hype_l2_ridge_bundle import HypeL2RidgeBundle
from hypervector.research.hype_l2_prospective_observer import (
    HypeL2ProspectiveObserver,
)
from hypervector.research.hype_l2_model_outcomes import (
    summarize_hype_l2_model_outcomes,
    unavailable_hype_l2_model_outcomes,
)

_DEFAULT_BUNDLE = Path("data/models/hype_l2_ridge_observe_v1.json")
_DEFAULT_LEDGER = Path("data/live/bidirectional_cohort/hype.jsonl")
_DEFAULT_CURSOR = Path("data/runtime/research/hype_l2_ridge_observer_cursor.json")
_DEFAULT_JOURNAL = Path("data/live/research/hype_l2_ridge_observations.jsonl")
_DEFAULT_STATUS = Path("data/runtime/research/hype_l2_ridge_observer_latest.json")
_DEFAULT_COHORT_CHECKPOINT = Path(
    "data/runtime/bidirectional_cohort/latest_checkpoint.json"
)
_ARCHIVE_NAMESPACE = "hyperliquid_rest_1s"


class ArchiveProtocol(Protocol):
    """Read-only event archive boundary required by the sidecar."""

    def replay_window(self, start: datetime, end: datetime) -> tuple[object, ...]:
        """Return evidence inside one UTC interval."""


class ObserverProtocol(Protocol):
    """No-submit prospective annotation boundary."""

    def warm(self, event: L2SnapshotEvent) -> None:
        """Warm the causal market buffer without reading decisions."""

    def observe(self, event: L2SnapshotEvent) -> tuple[dict[str, object], ...]:
        """Observe one book and return newly scored decisions."""


@dataclass(frozen=True)
class ObserverConfig:
    """Validated runtime boundaries for the report-only sidecar."""

    data_root: Path = Path("data")
    bundle: Path = _DEFAULT_BUNDLE
    decision_ledger: Path = _DEFAULT_LEDGER
    cursor: Path = _DEFAULT_CURSOR
    journal: Path = _DEFAULT_JOURNAL
    status: Path = _DEFAULT_STATUS
    cohort_checkpoint: Path = _DEFAULT_COHORT_CHECKPOINT
    poll_seconds: float = 5.0
    lookback_seconds: int = 180
    max_polls: int | None = None

    def __post_init__(self) -> None:
        if self.poll_seconds <= 0.0:
            raise ValueError("HYPE L2 observer poll_seconds must be positive")
        if self.lookback_seconds < 120:
            raise ValueError("HYPE L2 observer lookback_seconds must be at least 120")
        if self.max_polls is not None and self.max_polls <= 0:
            raise ValueError("HYPE L2 observer max_polls must be positive")


@dataclass
class _RunState:
    polls: int = 0
    durable_books: int = 0
    last_exchange_ts_ms: int | None = None
    latest_observation: dict[str, object] | None = None
    outcome_summary: dict[str, object] | None = None


def build_parser() -> argparse.ArgumentParser:
    """Build the research-only observer command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--bundle", type=Path, default=_DEFAULT_BUNDLE)
    parser.add_argument("--decision-ledger", type=Path, default=_DEFAULT_LEDGER)
    parser.add_argument("--cursor", type=Path, default=_DEFAULT_CURSOR)
    parser.add_argument("--journal", type=Path, default=_DEFAULT_JOURNAL)
    parser.add_argument("--status", type=Path, default=_DEFAULT_STATUS)
    parser.add_argument(
        "--cohort-checkpoint",
        type=Path,
        default=_DEFAULT_COHORT_CHECKPOINT,
    )
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--lookback-seconds", type=int, default=180)
    parser.add_argument("--max-polls", type=int)
    return parser


def config_from_args(args: argparse.Namespace) -> ObserverConfig:
    """Resolve command-line values into validated observer boundaries."""
    return ObserverConfig(
        data_root=args.data_root,
        bundle=args.bundle,
        decision_ledger=args.decision_ledger,
        cursor=args.cursor,
        journal=args.journal,
        status=args.status,
        cohort_checkpoint=args.cohort_checkpoint,
        poll_seconds=args.poll_seconds,
        lookback_seconds=args.lookback_seconds,
        max_polls=args.max_polls,
    )


def run_observer(
    config: ObserverConfig,
    *,
    observer: ObserverProtocol | None = None,
    archive: ArchiveProtocol | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleeper: Callable[[float], None] = time.sleep,
    stop_requested: Callable[[], bool] = lambda: False,
) -> int:
    """Replay new durable books and journal future entry annotations once."""
    active_observer = observer or _build_observer(config)
    active_archive = archive or EventArchive(
        data_root=config.data_root,
        symbol="HYPE",
        batch_size=1,
        namespace=_ARCHIVE_NAMESPACE,
    )
    state = _initial_state(config)
    _print_status("hype_l2_observer_started", config, state.polls)
    while not stop_requested() and not _reached_limit(config, state.polls):
        _poll_once(config, active_observer, active_archive, state, clock)
        if not _reached_limit(config, state.polls) and not stop_requested():
            sleeper(config.poll_seconds)
    _print_status("hype_l2_observer_stopped", config, state.polls)
    _write_status(config, lifecycle="stopped", state=state)
    return 0


def _poll_once(
    config: ObserverConfig,
    observer: ObserverProtocol,
    archive: ArchiveProtocol,
    state: _RunState,
    clock: Callable[[], datetime],
) -> None:
    end = clock()
    start = end - timedelta(seconds=config.lookback_seconds)
    events = _new_books(archive.replay_window(start, end), state.last_exchange_ts_ms)
    observations = _consume(events, observer)
    if events:
        state.last_exchange_ts_ms = events[-1].exchange_ts_ms
        state.durable_books += len(events)
    for row in observations:
        _print_observation(row)
        state.latest_observation = row
    state.outcome_summary = _load_outcome_summary(config)
    state.polls += 1
    _write_status(config, lifecycle="running", state=state)


def _new_books(
    events: tuple[object, ...],
    last_exchange_ts_ms: int | None,
) -> tuple[L2SnapshotEvent, ...]:
    books = tuple(
        event
        for event in events
        if isinstance(event, L2SnapshotEvent)
        and event.source == REST_L2_SOURCE
        and (last_exchange_ts_ms is None or event.exchange_ts_ms > last_exchange_ts_ms)
    )
    return tuple(sorted(books, key=lambda event: event.exchange_ts_ms))


def _consume(
    events: tuple[L2SnapshotEvent, ...], observer: ObserverProtocol
) -> tuple[dict[str, object], ...]:
    if not events:
        return ()
    for event in events[:-1]:
        observer.warm(event)
    return observer.observe(events[-1])


def _build_observer(config: ObserverConfig) -> HypeL2ProspectiveObserver:
    payload: object = json.loads(config.bundle.read_text(encoding="utf-8"))
    bundle = HypeL2RidgeBundle.from_payload(payload)
    evidence = file_evidence(config.bundle)
    sha = evidence.get("sha256")
    if not isinstance(sha, str):
        raise ValueError("HYPE L2 observer bundle has no SHA-256")
    return HypeL2ProspectiveObserver(
        bundle=bundle,
        bundle_sha256=sha,
        decision_ledger=config.decision_ledger,
        cursor_path=config.cursor,
        journal_path=config.journal,
    )


def _print_observation(row: dict[str, object]) -> None:
    output = {
        "event_type": "hype_l2_model_observation",
        "execution_authority": "none",
        "status": row.get("status"),
        "decision_time_ms": row.get("decision_time_ms"),
        "side": row.get("side"),
        "predicted_gross_return_bps": row.get("predicted_gross_return_bps"),
        "training_score_percentile": row.get("training_score_percentile"),
        "score_band": row.get("score_band"),
        "reason": row.get("reason"),
    }
    print(json.dumps(output, separators=(",", ":"), sort_keys=True), flush=True)


def _print_status(event_type: str, config: ObserverConfig, polls: int) -> None:
    row = {
        "event_type": event_type,
        "execution_authority": "none",
        "report_only": True,
        "polls": polls,
        "bundle": str(config.bundle),
        "journal": str(config.journal),
        "recorded_at_utc": datetime.now(UTC).isoformat(),
    }
    print(json.dumps(row, separators=(",", ":"), sort_keys=True), flush=True)


def _write_status(
    config: ObserverConfig,
    *,
    lifecycle: str,
    state: _RunState,
) -> None:
    payload = {
        "schema_version": 1,
        "mode": "hype_l2_ridge_prospective_observer_status",
        "state": lifecycle,
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
        "bundle": str(config.bundle),
        "journal": str(config.journal),
        "polls": state.polls,
        "durable_books_observed": state.durable_books,
        "last_book_exchange_ts_ms": state.last_exchange_ts_ms,
        "latest_observation": state.latest_observation,
        "outcome_summary": state.outcome_summary,
        "updated_at_utc": datetime.now(UTC).isoformat(),
    }
    _atomic_json(config.status, payload)


def _initial_state(config: ObserverConfig) -> _RunState:
    observations = _load_observations(config.journal)
    return _RunState(
        latest_observation=observations[-1] if observations else None,
        outcome_summary=_load_outcome_summary(config, observations=observations),
    )


def _load_outcome_summary(
    config: ObserverConfig,
    *,
    observations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    try:
        rows = (
            observations
            if observations is not None
            else _load_observations(config.journal)
        )
        checkpoint = _load_json_object(config.cohort_checkpoint, "cohort checkpoint")
        return summarize_hype_l2_model_outcomes(rows, checkpoint)
    except (
        FileNotFoundError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        return unavailable_hype_l2_model_outcomes(f"{type(exc).__name__}: {exc}")


def _load_observations(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"HYPE L2 journal line {line_number} is empty")
            value: object = json.loads(line)
            if not isinstance(value, dict) or not all(
                isinstance(key, str) for key in value
            ):
                raise ValueError(f"HYPE L2 journal line {line_number} is not an object")
            rows.append(value)
    return rows


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
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


def _reached_limit(config: ObserverConfig, polls: int) -> bool:
    return config.max_polls is not None and polls >= config.max_polls


def main() -> int:
    """Install clean stop handlers and run the standalone observer."""
    config = config_from_args(build_parser().parse_args())
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stopping.set()

    previous = {
        signal.SIGINT: signal.signal(signal.SIGINT, request_stop),
        signal.SIGTERM: signal.signal(signal.SIGTERM, request_stop),
    }
    try:
        return run_observer(config, stop_requested=stopping.is_set)
    finally:
        for current, handler in previous.items():
            signal.signal(current, handler)


if __name__ == "__main__":
    raise SystemExit(main())
