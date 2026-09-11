"""Streaming low-memory projections for rolling live checkpoints."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Protocol

from hypervector.research.live_ledger_snapshot import ProjectedLedgerRows

Record = dict[str, object]
_ASSET_CYCLE_EVENTS = frozenset(
    ("book_observation", "liquidation_price", "position", "reconciliation")
)


class _ProjectionState(Protocol):
    """Incremental selector over a validated stable ledger prefix."""

    def accept(self, row: Record) -> None: ...

    def finish(self) -> list[Record]: ...


@dataclass
class _SnapshotRunState:
    minimum_equity: float = float("inf")
    maximum_equity: float = float("-inf")
    equity_peak: float = float("-inf")
    maximum_drawdown: float = float("-inf")
    maximum_open: int = -1
    maximum_margin: float = float("-inf")
    maximum_notional: float = float("-inf")
    fills_signature: str | None = None
    assets_signature: str | None = None


@dataclass
class _CohortProjection:
    selected: dict[int, Record] = field(default_factory=dict)
    latest: dict[str, Record] = field(default_factory=dict)
    runs: dict[str, _SnapshotRunState] = field(default_factory=dict)

    def accept(self, row: Record) -> None:
        """Retain every non-snapshot event and material portfolio snapshots."""
        if row.get("event_type") != "cohort_snapshot":
            self._select(row)
            return
        run_id = _text(row.get("run_id"), "cohort run_id")
        values = _payload(row)
        state = self.runs.setdefault(run_id, _SnapshotRunState())
        material = _material_snapshot(values, state)
        self.latest[run_id] = row
        if material:
            self._select(row)

    def finish(self) -> list[Record]:
        """Return source-ordered material rows plus each run's latest snapshot."""
        for row in self.latest.values():
            self._select(row)
        return [self.selected[key] for key in sorted(self.selected)]

    def _select(self, row: Record) -> None:
        self.selected[_sequence(row)] = row


@dataclass
class _AssetProjection:
    current_run_id: str
    as_of: datetime | None = None
    selected: dict[int, Record] = field(default_factory=dict)
    latest_current: dict[str, Record] = field(default_factory=dict)
    pending_reconciliation: Record | None = None
    position_signature: str | None = None
    need_post_close_reconciliation: bool = False
    need_entry_liquidation: bool = False
    markout_thresholds: list[int] = field(default_factory=list)

    def accept(self, row: Record) -> None:
        """Retain execution facts and only lifecycle-relevant cycle samples."""
        if self.as_of is not None and _timestamp(row) > self.as_of:
            return
        event_type = _text(row.get("event_type"), "asset event type")
        if (
            row.get("run_id") == self.current_run_id
            and event_type in _ASSET_CYCLE_EVENTS
        ):
            self.latest_current[event_type] = row
        if event_type == "reconciliation":
            self._accept_reconciliation(row)
        elif event_type == "position":
            self._accept_position(row)
        elif event_type == "liquidation_price":
            self._accept_liquidation(row)
        elif event_type == "book_observation":
            self._accept_book(row)
        else:
            self._accept_execution(row, event_type)

    def finish(self) -> list[Record]:
        """Return source-ordered execution evidence with latest current state."""
        for row in self.latest_current.values():
            self._select(row)
        return [self.selected[key] for key in sorted(self.selected)]

    def _accept_reconciliation(self, row: Record) -> None:
        self.pending_reconciliation = row
        if self.need_post_close_reconciliation:
            self._select(row)
            self.need_post_close_reconciliation = False

    def _accept_position(self, row: Record) -> None:
        signature = _stable_json(_payload(row).get("size_signed"))
        if signature != self.position_signature:
            self._select(row)
            self.position_signature = signature

    def _accept_liquidation(self, row: Record) -> None:
        if self.need_entry_liquidation:
            self._select(row)
            self.need_entry_liquidation = False

    def _accept_book(self, row: Record) -> None:
        observed = _integer(_payload(row).get("exchange_ts_ms"), "book timestamp")
        if any(observed >= threshold for threshold in self.markout_thresholds):
            self._select(row)
            self.markout_thresholds = [
                threshold
                for threshold in self.markout_thresholds
                if threshold > observed
            ]

    def _accept_execution(self, row: Record, event_type: str) -> None:
        values = _payload(row)
        if event_type == "order_acknowledgement" and _accepted_entry(values):
            if self.pending_reconciliation is not None:
                self._select(self.pending_reconciliation)
            self.need_entry_liquidation = True
        if event_type == "fill":
            timestamp = _integer(values.get("venue_timestamp_ms"), "fill timestamp")
            self.markout_thresholds.append(timestamp + 5_000)
        if event_type == "close":
            self.need_post_close_reconciliation = True
        self._select(row)

    def _select(self, row: Record) -> None:
        self.selected[_sequence(row)] = row


def compact_cohort_ledger_rows(path: Path | Iterable[str]) -> ProjectedLedgerRows:
    """Retain exact cohort events while collapsing repeated portfolio states."""
    return _project_rows(path, _CohortProjection())


def compact_asset_ledger_rows(
    path: Path | Iterable[str],
    *,
    current_run_id: str,
    as_of: datetime | None = None,
) -> ProjectedLedgerRows:
    """Retain exact asset lifecycles without materializing every poll sample."""
    if not current_run_id.strip():
        raise ValueError("current_run_id must be non-empty")
    if as_of is not None and (as_of.tzinfo is None or as_of.utcoffset() is None):
        raise ValueError("asset projection cutoff must be timezone-aware")
    return _project_rows(path, _AssetProjection(current_run_id.strip(), as_of))


def _project_rows(
    path: Path | Iterable[str], state: _ProjectionState
) -> ProjectedLedgerRows:
    source_start: int | None = None
    source_end: int | None = None
    source = (
        path.open(encoding="utf-8") if isinstance(path, Path) else nullcontext(path)
    )
    with source as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            value: object = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError(f"decision row must be object at {path}:{line_number}")
            sequence = _sequence(value)
            if source_start is None:
                source_start = sequence
            elif source_end is not None and sequence != source_end + 1:
                raise ValueError(
                    f"ledger source sequence is not contiguous at {sequence}"
                )
            source_end = sequence
            state.accept(value)
    if source_start is None or source_end is None:
        raise ValueError("checkpoint ledger projection requires source rows")
    return ProjectedLedgerRows(state.finish(), source_start, source_end)


def _material_snapshot(values: Mapping[str, object], state: _SnapshotRunState) -> bool:
    equity = _number(values.get("account_value_usd"), "account value")
    opens = _integer(values.get("open_position_count"), "open positions")
    margin = _number(values.get("total_margin_used_usd"), "margin used")
    notional = _number(values.get("total_notional_position_usd"), "notional")
    fills = _stable_json(values.get("recent_fills", []))
    assets = _asset_state_signature(values.get("assets", []))
    peak = max(state.equity_peak, equity)
    drawdown = 0.0 if peak <= 0.0 else (peak - equity) / peak
    material = any(
        (
            equity < state.minimum_equity,
            equity > state.maximum_equity,
            drawdown > state.maximum_drawdown,
            opens > state.maximum_open,
            margin > state.maximum_margin,
            notional > state.maximum_notional,
            fills != state.fills_signature,
            assets != state.assets_signature,
        )
    )
    state.minimum_equity = min(state.minimum_equity, equity)
    state.maximum_equity = max(state.maximum_equity, equity)
    state.equity_peak = peak
    state.maximum_drawdown = max(state.maximum_drawdown, drawdown)
    state.maximum_open = max(state.maximum_open, opens)
    state.maximum_margin = max(state.maximum_margin, margin)
    state.maximum_notional = max(state.maximum_notional, notional)
    state.fills_signature, state.assets_signature = fills, assets
    return material


def _asset_state_signature(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("snapshot assets must be an array")
    state = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("snapshot asset must be an object")
        state.append(
            tuple(
                item.get(key)
                for key in (
                    "symbol",
                    "position_size_signed",
                    "protective_stop_oid",
                    "target_oid",
                )
            )
        )
    return _stable_json(state)


def _accepted_entry(values: Mapping[str, object]) -> bool:
    return values.get("operation") == "entry" and values.get("accepted") is True


def _payload(row: Mapping[str, object]) -> Mapping[str, object]:
    value = row.get("payload")
    if not isinstance(value, Mapping):
        raise ValueError("checkpoint ledger payload must be an object")
    return value


def _sequence(row: Mapping[str, object]) -> int:
    return _integer(row.get("sequence"), "ledger sequence")


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _timestamp(row: Mapping[str, object]) -> datetime:
    value = _text(row.get("observed_at_utc"), "asset observation timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("asset observation timestamp must be timezone-aware")
    return parsed


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
