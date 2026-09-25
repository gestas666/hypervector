#!/usr/bin/env python3
"""Read-only size-ladder evidence for the Donchian routes (V94 plan item D).

Report-only. execution_authority: none. Standard library only: this tool imports
nothing from ``hypervector`` and nothing that could construct an execution
client, sign a request or reach a venue. It reads the live JSONL ledgers and
writes one JSON report plus a short text summary.

For one profile id and/or explicit run ids, since a start time, it reports:

- every Donchian lifecycle: entry and exit, side, R from the lifecycle's own
  initial stop distance, net dollars including fees and funding, exit reason;
- count, mean R and ex-top-3 net at measured (realized) cost;
- holds longer than the configured maximum hold, flagged and reported capped at
  the executable mark observed at ``opened_at + maximum_hold``;
- equity high-water and drawdown from the rung high;
- the pre-registered advance and step-down evaluation of
  ``docs/plans/2026-09-24-v94-size-ladder.md``;
- breakout extension in ATR for every Donchian entry (weak shorts < 1.0 ATR),
  from the journaled ``intent_routing`` readiness metrics;
- the floor-armed 24h-timer counterfactual along the observed book path;
- post-exit marks at 240 and 1,440 minutes;
- time-in-market-scaled buy-and-hold from observed marks.

The ledgers are multi-GB. The reader bisects each append-only file to the start
time, filters raw bytes by event type and by run or profile substring before any
JSON decoding, and extracts book marks with byte regexes without decoding them.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
import csv
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import re
import sys
from typing import BinaryIO

DEFAULT_LEDGER_DIR = Path("data/live/bidirectional_cohort")
COHORT_LEDGER = "decisions.jsonl"
DEFAULT_SYMBOLS = ("SOL", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA")
DEFAULT_STRATEGY_PREFIX = "hourly_donchian_20_10_"
TIMER_EXIT_REASON = "maximum_hold_seconds"
RECIPE_EXIT_REASON = "hourly_price_recipe_exit"
PROFIT_FLOOR_EXIT = "profit_floor"

# Pre-registered ladder rules (docs/plans/2026-09-24-v94-size-ladder.md).
ADVANCE_CLOSES = 30
STEP_DOWN_CLOSES = 50
STEP_DOWN_DRAWDOWN = -0.12
EXCLUDED_TOP = 3
WEAK_SHORT_ATR = 1.0
POST_EXIT_MINUTES = (240, 1_440)
# v2 floor in units of the lifecycle's own R, used only when the journaled
# adaptive state lacks an explicit floor (cohort_adaptive_exit_policy.FLOOR_R).
FLOOR_R = 0.5

DEFAULT_MAXIMUM_HOLD_SECONDS = 86_400
DEFAULT_HOLD_GRACE_SECONDS = 900.0
DEFAULT_MARK_TOLERANCE_SECONDS = 900.0
DEFAULT_COUNTERFACTUAL_HORIZON_HOURS = 168.0
MINUTE_MS = 60_000
HOUR_MS = 3_600_000
SEEK_MARGIN_MS = HOUR_MS
SEEK_CHUNK_BYTES = 4 << 20
HEAD_BYTES = 400
BPS = 10_000.0
SIZE_TOLERANCE = 1e-9

_EVENT = re.compile(rb'"event_type":\s*"([a-z_]+)"')
_OBSERVED = re.compile(rb'"observed_at_utc":\s*"([^"]+)"')
_NUMBER = rb"(-?[0-9][0-9.eE+-]*)"
_ACCOUNT = re.compile(rb'"account_value_usd":\s*' + _NUMBER)
_EXCHANGE_MS = re.compile(rb'"exchange_ts_ms":\s*([0-9]+)')
_MID = re.compile(rb'"mid_px":\s*' + _NUMBER)
_BID = re.compile(rb'"bids":\s*\[\s*\{\s*"price":\s*' + _NUMBER)
_ASK = re.compile(rb'"asks":\s*\[\s*\{\s*"price":\s*' + _NUMBER)
_LIFECYCLE_EVENTS = frozenset(
    {
        "regime_decision",
        "order_acknowledgement",
        "order_intent",
        "stop_order",
        "state_transition",
        "close",
        "entry_not_filled",
    }
)

Record = dict[str, object]


# ---------------------------------------------------------------- selection


@dataclass(frozen=True)
class Selection:
    """Rows must match every given constraint: run ids, profile id, time window."""

    profile_id: str | None
    run_ids: frozenset[str]
    since_ms: int
    until_ms: int | None

    def raw_match(self, line: bytes, asset_profile: str | None) -> bool:
        """Cheap exact-value substring test before any JSON decoding."""
        if self.run_ids and not any(
            f'"{run}"'.encode() in line for run in self.run_ids
        ):
            return False
        if self.profile_id is not None:
            expected = asset_profile or self.profile_id
            if f'"{expected}"'.encode() not in line:
                return False
        return True

    def row_match(self, row: Mapping[str, object], asset_profile: str | None) -> bool:
        """Exact field test after decoding."""
        if self.run_ids and row.get("run_id") not in self.run_ids:
            return False
        if self.profile_id is not None:
            return row.get("profile_id") == (asset_profile or self.profile_id)
        return True

    def asset_profile(self, symbol: str) -> str | None:
        """Per-symbol ledgers carry ``<profile>_<symbol lower>`` as profile id."""
        if self.profile_id is None:
            return None
        return f"{self.profile_id}_{symbol.lower()}"

    def in_window(self, ms: int) -> bool:
        """Return whether a row falls inside the selected window."""
        return ms >= self.since_ms and (self.until_ms is None or ms <= self.until_ms)


# ---------------------------------------------------------------- raw reading


def seek_offset(
    path: Path, target_ms: int, *, chunk_bytes: int = SEEK_CHUNK_BYTES
) -> int:
    """Return a byte offset at or before the first row observed at or after target.

    The ledgers are append-only and time-ordered. Invariant: the first complete
    row after the returned offset is observed before ``target_ms`` (or the offset
    is 0), so reading from it never skips a row at or after the target.
    """
    low, high = 0, path.stat().st_size
    with path.open("rb") as handle:
        while high - low > chunk_bytes:
            middle = (low + high) // 2
            stamp = _first_stamp_after(handle, middle)
            if stamp is None or stamp >= target_ms:
                high = middle
            else:
                low = middle
    return low


def _first_stamp_after(handle: BinaryIO, offset: int) -> int | None:
    handle.seek(offset)
    if offset:
        handle.readline()
    line = handle.readline()
    return _observed_ms(line) if line else None


def _lines(path: Path, start_ms: int) -> Iterator[bytes]:
    offset = seek_offset(path, start_ms - SEEK_MARGIN_MS)
    with path.open("rb") as handle:
        handle.seek(offset)
        if offset:
            handle.readline()
        yield from handle


def _event_type(line: bytes) -> str | None:
    match = _EVENT.search(line, 0, HEAD_BYTES)
    return match.group(1).decode() if match else None


def _observed_ms(line: bytes) -> int | None:
    match = _OBSERVED.search(line, 0, HEAD_BYTES)
    if match is None:
        return None
    try:
        return _iso_ms(match.group(1).decode())
    except ValueError:
        return None


def _iso_ms(value: str) -> int:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return int(round(stamp.timestamp() * 1000))


def _utc(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def _float(match: re.Match[bytes] | None) -> float | None:
    if match is None:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _decode(line: bytes, stats: Counter[str]) -> Record | None:
    try:
        row = json.loads(line)
    except ValueError:
        # A row being appended while we read, or a torn write.
        stats["undecodable_rows"] += 1
        return None
    if not isinstance(row, dict):
        stats["undecodable_rows"] += 1
        return None
    stats["decoded_rows"] += 1
    return row


def _payload(row: Mapping[str, object]) -> Mapping[str, object]:
    value = row.get("payload")
    return value if isinstance(value, Mapping) else {}


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _f(row: Mapping[str, object], key: str) -> float:
    """Read a float the report itself wrote; a missing value is a programming error."""
    value = _num(row.get(key))
    if value is None:
        raise KeyError(f"lifecycle row lacks numeric {key}")
    return value


def _i(row: Mapping[str, object], key: str) -> int:
    """Read an integer the report itself wrote."""
    value = _int(row.get(key))
    if value is None:
        raise KeyError(f"lifecycle row lacks integer {key}")
    return value


# ---------------------------------------------------------------- marks


@dataclass(frozen=True, slots=True)
class Mark:
    """One observed executable quote."""

    ms: int
    bid: float
    ask: float
    mid: float
    source: str

    def exit_price(self, side: str) -> float:
        """Closing a long sells at the bid; closing a short buys at the ask."""
        return self.bid if side == "long" else self.ask


@dataclass
class MarkSeries:
    """Time-sorted marks for one symbol."""

    marks: list[Mark] = field(default_factory=list)
    _times: list[int] = field(default_factory=list)

    def add(self, mark: Mark) -> None:
        """Append one mark; ``finish`` restores order if rows were unordered."""
        self.marks.append(mark)

    def finish(self) -> None:
        """Sort once after loading and index the timestamps."""
        self.marks.sort(key=lambda mark: mark.ms)
        self._times = [mark.ms for mark in self.marks]

    def at_or_after(self, target_ms: int, tolerance_ms: int) -> Mark | None:
        """Return the first mark at or after target, if within tolerance."""
        index = bisect_left(self._times, target_ms)
        if index >= len(self.marks):
            return None
        mark = self.marks[index]
        return mark if mark.ms - target_ms <= tolerance_ms else None

    def after(self, start_ms: int, end_ms: int) -> list[Mark]:
        """Return marks strictly after start and at or before end."""
        return self.marks[
            bisect_right(self._times, start_ms) : bisect_right(self._times, end_ms)
        ]

    def within(self, start_ms: int, end_ms: int) -> list[Mark]:
        """Return marks inside the closed interval."""
        return self.marks[
            bisect_left(self._times, start_ms) : bisect_right(self._times, end_ms)
        ]

    @property
    def last_ms(self) -> int | None:
        """Return the newest mark time."""
        return self.marks[-1].ms if self.marks else None


def _book_mark(line: bytes, observed_ms: int) -> Mark | None:
    mid = _float(_MID.search(line))
    bid = _float(_BID.search(line))
    ask = _float(_ASK.search(line))
    if mid is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2
    if mid is None:
        return None
    exchange = _EXCHANGE_MS.search(line)
    ms = int(exchange.group(1)) if exchange else observed_ms
    return Mark(
        ms,
        bid if bid is not None else mid,
        ask if ask is not None else mid,
        mid,
        "book",
    )


def load_supplemental_marks(path: Path) -> dict[str, MarkSeries]:
    """Read ``symbol,time,price`` rows (time ISO-8601 or epoch ms) for gaps."""
    series: dict[str, MarkSeries] = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            raw_time = (row.get("time") or "").strip()
            ms = int(raw_time) if raw_time.isdigit() else _iso_ms(raw_time)
            price = float(row["price"])
            if not math.isfinite(price) or price <= 0:
                raise ValueError(f"supplemental mark price must be positive: {row}")
            symbol = (row.get("symbol") or "").strip()
            series.setdefault(symbol, MarkSeries()).add(
                Mark(ms, price, price, price, "supplemental")
            )
    for values in series.values():
        values.finish()
    return series


# ---------------------------------------------------------------- asset ledgers


@dataclass(frozen=True, slots=True)
class Fill:
    """One deduplicated venue fill leg."""

    oid: int
    price: float
    size: float
    fee_usd: float
    closed_pnl_usd: float
    venue_ms: int
    direction: str


@dataclass
class Lifecycle:
    """Everything the journal says about one entry order's position."""

    symbol: str
    entry_oid: int
    strategy_id: str | None = None
    side: str | None = None
    decision_time_ms: int | None = None
    opened_at_ms: int | None = None
    plan: Mapping[str, object] | None = None
    initial_stop: float | None = None
    stop_source: str | None = None
    exit_oids: set[int] = field(default_factory=set)
    pending_reason: str | None = None
    exit_reason: str | None = None
    verified_flat: bool = False
    flat_observed_ms: int | None = None
    entry_acknowledged: bool = False
    run_ids: set[str] = field(default_factory=set)


@dataclass
class AssetEvidence:
    """Lifecycles, fills, funding and marks from one per-symbol ledger."""

    symbol: str
    lifecycles: dict[int, Lifecycle] = field(default_factory=dict)
    fills: dict[int, dict[int, Fill]] = field(default_factory=dict)
    funding: dict[int, float] = field(default_factory=dict)
    marks: MarkSeries = field(default_factory=MarkSeries)
    stats: Counter[str] = field(default_factory=Counter)


def scan_asset_ledger(
    path: Path,
    symbol: str,
    selection: Selection,
    *,
    marks_until_ms: int | None,
) -> AssetEvidence:
    """Stream one per-symbol ledger once, decoding only lifecycle rows."""
    evidence = AssetEvidence(symbol)
    if not path.exists():
        evidence.stats["missing_ledger"] += 1
        return evidence
    asset_profile = selection.asset_profile(symbol)
    state = _AssetState(evidence)
    for line in _lines(path, selection.since_ms):
        evidence.stats["bytes"] += len(line)
        event = _event_type(line)
        if event is None:
            continue
        observed = _observed_ms(line)
        if observed is None or observed < selection.since_ms - SEEK_MARGIN_MS:
            continue
        if event == "book_observation":
            # Prices are prices: marks are kept whichever run journaled them.
            if marks_until_ms is None or observed <= marks_until_ms:
                mark = _book_mark(line, observed)
                if mark is not None:
                    evidence.marks.add(mark)
            continue
        if event in ("fill", "funding"):
            row = _decode(line, evidence.stats)
            if row is not None:
                state.cash(event, _payload(row))
            continue
        if event not in _LIFECYCLE_EVENTS:
            continue
        if selection.until_ms is not None and observed > selection.until_ms:
            continue
        if not selection.raw_match(line, asset_profile):
            continue
        row = _decode(line, evidence.stats)
        if row is None or not selection.row_match(row, asset_profile):
            continue
        state.lifecycle_event(event, row)
    evidence.marks.finish()
    return evidence


class _AssetState:
    """Per-symbol journal state machine; exit fills are joined by order id later."""

    def __init__(self, evidence: AssetEvidence) -> None:
        self._evidence = evidence
        self._pending: Mapping[str, object] | None = None
        self._current: Lifecycle | None = None

    def cash(self, event: str, payload: Mapping[str, object]) -> None:
        evidence = self._evidence
        if event == "funding":
            stamp = _int(payload.get("venue_timestamp_ms"))
            delta = _num(payload.get("usdc_delta"))
            if stamp is not None and delta is not None:
                evidence.funding.setdefault(stamp, delta)
            return
        oid, trade = _int(payload.get("oid")), _int(payload.get("trade_id"))
        price, size = _num(payload.get("price")), _num(payload.get("size"))
        stamp = _int(payload.get("venue_timestamp_ms"))
        if (
            oid is None
            or trade is None
            or price is None
            or size is None
            or stamp is None
        ):
            evidence.stats["malformed_fills"] += 1
            return
        fill = Fill(
            oid,
            price,
            size,
            _num(payload.get("fee_usd")) or 0.0,
            _num(payload.get("closed_pnl_usd")) or 0.0,
            stamp,
            str(payload.get("direction") or ""),
        )
        legs = evidence.fills.setdefault(fill.oid, {})
        prior = legs.setdefault(trade, fill)
        if prior != fill:
            evidence.stats["conflicting_fill_duplicates"] += 1

    def lifecycle_event(self, event: str, row: Mapping[str, object]) -> None:
        payload = _payload(row)
        run_id = str(row.get("run_id") or "")
        if event == "regime_decision":
            if payload.get("routing_action") == "enter":
                self._pending = payload
            return
        if event == "entry_not_filled":
            self._pending = None
            return
        if event == "order_acknowledgement":
            self._entry_ack(payload, run_id)
            return
        if event == "state_transition":
            self._state(payload, run_id)
            return
        current = self._current
        if current is None:
            return
        current.run_ids.add(run_id)
        oid = _int(payload.get("oid"))
        if event == "order_intent":
            trigger = _num(payload.get("trigger_price"))
            if (
                payload.get("operation") == "protective_stop"
                and trigger is not None
                and current.initial_stop is None
            ):
                current.initial_stop = trigger
                current.stop_source = "protective_stop_intent"
        elif event == "stop_order":
            if oid is not None and payload.get("accepted") is not False:
                current.exit_oids.add(oid)
        elif event == "close":
            if oid is not None:
                current.exit_oids.add(oid)
            reason = payload.get("reason")
            if isinstance(reason, str) and payload.get("intent"):
                current.pending_reason = reason
            if payload.get("verified_flat") is True:
                current.exit_reason = (
                    reason if isinstance(reason, str) else current.pending_reason
                )
                current.verified_flat = True
                observed = row.get("observed_at_utc")
                if isinstance(observed, str):
                    current.flat_observed_ms = _iso_ms(observed)
                self._current = None

    def _entry_ack(self, payload: Mapping[str, object], run_id: str) -> None:
        oid = _int(payload.get("oid"))
        if (
            payload.get("operation") != "entry"
            or payload.get("accepted") is not True
            or oid is None
        ):
            return
        lifecycle = self._lifecycle(oid)
        lifecycle.entry_acknowledged = True
        lifecycle.run_ids.add(run_id)
        pending = self._pending
        decided = _int(payload.get("decision_time_ms"))
        if pending is not None and (
            decided is None or decided == _int(pending.get("decision_time_ms"))
        ):
            strategy = pending.get("strategy_id")
            lifecycle.strategy_id = strategy if isinstance(strategy, str) else None
            side = pending.get("side")
            lifecycle.side = side if side in ("long", "short") else None
            lifecycle.decision_time_ms = _int(pending.get("decision_time_ms"))
            plan = pending.get("execution_plan")
            if isinstance(plan, Mapping):
                lifecycle.plan = plan
        self._pending = None
        self._current = lifecycle

    def _state(self, payload: Mapping[str, object], run_id: str) -> None:
        entry_oid = _int(payload.get("entry_oid"))
        if entry_oid is None:
            return
        lifecycle = self._lifecycle(entry_oid)
        lifecycle.run_ids.add(run_id)
        if lifecycle.opened_at_ms is None:
            lifecycle.opened_at_ms = _int(payload.get("opened_at_ms"))
        plan = payload.get("execution_plan")
        if lifecycle.plan is None and isinstance(plan, Mapping):
            lifecycle.plan = plan
        if lifecycle.strategy_id is None and isinstance(plan, Mapping):
            strategy = plan.get("strategy_id")
            lifecycle.strategy_id = strategy if isinstance(strategy, str) else None
        size = _num(payload.get("position_size_signed"))
        if lifecycle.side is None and size:
            lifecycle.side = "long" if size > 0 else "short"
        for key in ("stop_oid", "close_oid", "target_oid"):
            oid = _int(payload.get(key))
            if oid is not None:
                lifecycle.exit_oids.add(oid)
        if not lifecycle.verified_flat:
            self._current = lifecycle

    def _lifecycle(self, entry_oid: int) -> Lifecycle:
        lifecycles = self._evidence.lifecycles
        if entry_oid not in lifecycles:
            lifecycles[entry_oid] = Lifecycle(self._evidence.symbol, entry_oid)
        return lifecycles[entry_oid]


# ---------------------------------------------------------------- cohort ledger


@dataclass
class CohortEvidence:
    """Readiness metrics, recipe exits, v2 exit state and equity."""

    entries: dict[tuple[str, str, int], Mapping[str, object]] = field(
        default_factory=dict
    )
    recipe_exits: dict[tuple[str, str], list[int]] = field(default_factory=dict)
    adaptive: dict[tuple[str, int], Record] = field(default_factory=dict)
    equity: list[tuple[int, float]] = field(default_factory=list)
    stats: Counter[str] = field(default_factory=Counter)


def scan_cohort_ledger(
    path: Path,
    selection: Selection,
    *,
    strategy_prefix: str,
    evaluations_until_ms: int | None,
) -> CohortEvidence:
    """Stream the cohort ledger once; only Donchian and v2 rows are decoded."""
    evidence = CohortEvidence()
    if not path.exists():
        evidence.stats["missing_ledger"] += 1
        return evidence
    prefix = strategy_prefix.encode()
    for line in _lines(path, selection.since_ms):
        evidence.stats["bytes"] += len(line)
        event = _event_type(line)
        if event not in (
            "cohort_snapshot",
            "intent_routing",
            "adaptive_exit_observation",
        ):
            continue
        observed = _observed_ms(line)
        if observed is None or observed < selection.since_ms - SEEK_MARGIN_MS:
            continue
        if not selection.raw_match(line, None):
            continue
        if event == "cohort_snapshot":
            value = _float(_ACCOUNT.search(line))
            if value is not None and selection.in_window(observed):
                evidence.equity.append((observed, value))
            continue
        if prefix not in line:
            continue
        if evaluations_until_ms is not None and observed > evaluations_until_ms:
            continue
        row = _decode(line, evidence.stats)
        if row is None or not selection.row_match(row, None):
            continue
        if event == "intent_routing":
            _routing_row(evidence, _payload(row), strategy_prefix)
        else:
            _adaptive_row(evidence, _payload(row), strategy_prefix)
    evidence.equity.sort()
    for exits in evidence.recipe_exits.values():
        exits.sort()
    return evidence


def _routing_row(
    evidence: CohortEvidence, payload: Mapping[str, object], prefix: str
) -> None:
    evaluations = payload.get("evaluations")
    if not isinstance(evaluations, list):
        return
    for evaluation in evaluations:
        if not isinstance(evaluation, Mapping):
            continue
        strategy, symbol = evaluation.get("strategy_id"), evaluation.get("symbol")
        decided = _int(evaluation.get("decision_time_ms"))
        if (
            not isinstance(strategy, str)
            or not strategy.startswith(prefix)
            or not isinstance(symbol, str)
            or decided is None
        ):
            continue
        if evaluation.get("eligible") is True:
            evidence.entries.setdefault((strategy, symbol, decided), evaluation)
        exit_sides = evaluation.get("exit_sides")
        if isinstance(exit_sides, list):
            for side in exit_sides:
                if side in ("long", "short"):
                    evidence.recipe_exits.setdefault((symbol, side), []).append(decided)


def _adaptive_row(
    evidence: CohortEvidence, payload: Mapping[str, object], prefix: str
) -> None:
    strategy, symbol = payload.get("strategy_id"), payload.get("symbol")
    entry_oid = _int(payload.get("entry_oid"))
    state = payload.get("state")
    if (
        not isinstance(strategy, str)
        or not strategy.startswith(prefix)
        or not isinstance(symbol, str)
        or entry_oid is None
        or not isinstance(state, Mapping)
    ):
        return
    key = (symbol, entry_oid)
    prior = evidence.adaptive.get(key, {})
    floor_armed = bool(state.get("floor_armed")) or bool(prior.get("floor_armed"))
    evidence.adaptive[key] = {
        "risk_bps": _num(payload.get("risk_bps")),
        "floor_armed": floor_armed,
        "floor_bps": _num(state.get("floor_bps")) or prior.get("floor_bps"),
        "peak_bps": max(
            _num(state.get("peak_bps")) or 0.0, _num(prior.get("peak_bps")) or 0.0
        ),
    }


# ---------------------------------------------------------------- lifecycle rows


@dataclass(frozen=True)
class Options:
    """Report parameters with their documented defaults."""

    strategy_prefix: str = DEFAULT_STRATEGY_PREFIX
    hold_grace_ms: int = int(DEFAULT_HOLD_GRACE_SECONDS * 1000)
    mark_tolerance_ms: int = int(DEFAULT_MARK_TOLERANCE_SECONDS * 1000)
    counterfactual_horizon_ms: int = int(DEFAULT_COUNTERFACTUAL_HORIZON_HOURS * HOUR_MS)


def _aggregate(fills: Sequence[Fill]) -> tuple[float, float, float, float, int, int]:
    size = sum(fill.size for fill in fills)
    notional = sum(fill.price * fill.size for fill in fills)
    fee = sum(fill.fee_usd for fill in fills)
    pnl = sum(fill.closed_pnl_usd for fill in fills)
    first = min(fill.venue_ms for fill in fills)
    last = max(fill.venue_ms for fill in fills)
    return size, notional, fee, pnl, first, last


def _plan_stop(
    plan: Mapping[str, object] | None, entry: float, side: str
) -> float | None:
    """Mirror BoundExecutionPlan.stop_price for the two configured stop policies."""
    if plan is None:
        return None
    sign = -1.0 if side == "long" else 1.0
    if plan.get("stop_policy") == "fixed_bps":
        bps = _num(plan.get("stop_bps"))
        return None if bps is None else entry * (1 + sign * bps / BPS)
    anchor = _num(plan.get("stop_anchor"))
    low, high = _num(plan.get("minimum_stop_bps")), _num(plan.get("maximum_stop_bps"))
    if anchor is None or low is None or high is None:
        return None
    distance = sign * (anchor - entry) / entry * BPS
    return entry * (1 + sign * min(max(distance, low), high) / BPS)


def _maximum_hold_seconds(plan: Mapping[str, object] | None) -> int:
    if plan is None:
        return DEFAULT_MAXIMUM_HOLD_SECONDS
    hard = _int(plan.get("hard_maximum_hold_seconds"))
    if plan.get("maximum_hold_policy") == "extend_while_regime_supported" and hard:
        return hard
    return _int(plan.get("maximum_hold_seconds")) or DEFAULT_MAXIMUM_HOLD_SECONDS


def _funding(evidence: AssetEvidence, start_ms: int, end_ms: int) -> float:
    return sum(
        delta
        for stamp, delta in evidence.funding.items()
        if start_ms <= stamp <= end_ms
    )


def _mark(
    symbol: str,
    target_ms: int,
    evidence: AssetEvidence,
    supplemental: Mapping[str, MarkSeries],
    options: Options,
) -> Mark | None:
    mark = evidence.marks.at_or_after(target_ms, options.mark_tolerance_ms)
    if mark is None and symbol in supplemental:
        mark = supplemental[symbol].at_or_after(target_ms, options.mark_tolerance_ms)
    return mark


def _lifecycle_row(
    lifecycle: Lifecycle,
    evidence: AssetEvidence,
    supplemental: Mapping[str, MarkSeries],
    options: Options,
    now_ms: int,
) -> Record | None:
    entry_fills = list(evidence.fills.get(lifecycle.entry_oid, {}).values())
    side = lifecycle.side
    if not entry_fills or side is None:
        return None
    size, notional, entry_fee, _, entry_ms, _ = _aggregate(entry_fills)
    entry = notional / size
    opened = lifecycle.opened_at_ms or lifecycle.decision_time_ms or entry_ms
    stop, stop_source = lifecycle.initial_stop, lifecycle.stop_source
    if stop is None:
        stop, stop_source = _plan_stop(lifecycle.plan, entry, side), "execution_plan"
    stop_bps = abs(entry - stop) / entry * BPS if stop is not None else None
    risk = size * abs(entry - stop) if stop is not None else None
    exits, attribution = _exit_fills(lifecycle, evidence, size, entry_ms)
    maximum_hold = _maximum_hold_seconds(lifecycle.plan)
    row: Record = {
        "lifecycle_id": f"{lifecycle.symbol}:{lifecycle.entry_oid}:{opened}",
        "symbol": lifecycle.symbol,
        "strategy_id": lifecycle.strategy_id,
        "side": side,
        "entry_oid": lifecycle.entry_oid,
        "decision_time_ms": lifecycle.decision_time_ms,
        "opened_at_ms": opened,
        "opened_at_utc": _utc(opened),
        "entry_time_utc": _utc(entry_ms),
        "entry_ms": entry_ms,
        "entry_price": entry,
        "size": size,
        "notional_usd": notional,
        "entry_fee_usd": entry_fee,
        "initial_stop": stop,
        "stop_source": stop_source,
        "stop_bps": stop_bps,
        "risk_usd": risk,
        "maximum_hold_seconds": maximum_hold,
        "run_ids": sorted(run for run in lifecycle.run_ids if run),
    }
    row["exit_attribution"] = attribution
    exit_size = sum(fill.size for fill in exits)
    if not lifecycle.verified_flat or not exits:
        flat = lifecycle.flat_observed_ms if lifecycle.verified_flat else None
        held_to = now_ms if flat is None else flat
        row.update(
            status="open" if not lifecycle.verified_flat else "closed_without_fills",
            exit_reason=lifecycle.exit_reason,
            funding_usd=_funding(evidence, entry_ms, held_to),
            in_market_until_ms=held_to,
        )
        if lifecycle.verified_flat:
            # Ordered into the ladder sample at its verified-flat time, or at its
            # opening when none was journaled, so it cannot slide out of a window.
            closed_ms = opened if flat is None else flat
            row.update(exit_ms=closed_ms, exit_time_utc=_utc(closed_ms))
        return row
    _, exit_notional, exit_fee, pnl, _, exit_ms = _aggregate(exits)
    exit_price = exit_notional / exit_size
    funding = _funding(evidence, entry_ms, exit_ms)
    net = pnl - entry_fee - exit_fee + funding
    reconciled = math.isclose(exit_size, size, rel_tol=1e-6, abs_tol=SIZE_TOLERANCE)
    hold_ms = exit_ms - opened
    outage = hold_ms > maximum_hold * 1000 + options.hold_grace_ms
    row.update(
        status="closed" if reconciled else "closed_size_mismatch",
        exit_reason=lifecycle.exit_reason,
        exit_time_utc=_utc(exit_ms),
        exit_ms=exit_ms,
        exit_price=exit_price,
        exit_size=exit_size,
        exit_fee_usd=exit_fee,
        venue_pnl_usd=pnl,
        funding_usd=funding,
        net_usd=net,
        gross_r=pnl / risk if risk else None,
        r_multiple=net / risk if risk else None,
        hold_seconds=hold_ms / 1000,
        outage_hold=outage,
        in_market_until_ms=exit_ms,
    )
    exit_fee_rate = exit_fee / exit_notional if exit_notional else 0.0
    row["capped"] = _capped(row, evidence, supplemental, options, exit_fee_rate, outage)
    row["post_exit_marks"] = {
        str(minutes): _post_exit_mark(
            row, exit_ms + minutes * MINUTE_MS, evidence, supplemental, options
        )
        for minutes in POST_EXIT_MINUTES
    }
    row["exit_fee_rate"] = exit_fee_rate
    return row


def _exit_fills(
    lifecycle: Lifecycle, evidence: AssetEvidence, size: float, entry_ms: int
) -> tuple[list[Fill], str]:
    """Join closing fills by the order ids the journal announced for the lifecycle.

    If a verified-flat lifecycle is still short of its entry size, closing fills
    from unannounced orders between the entry and the verified-flat row are added,
    so a future journal shape cannot silently drop an exit.
    """
    exits = [
        fill
        for oid in sorted(lifecycle.exit_oids - {lifecycle.entry_oid})
        for fill in evidence.fills.get(oid, {}).values()
        if fill.direction.startswith("Close")
    ]
    flat_ms = lifecycle.flat_observed_ms
    if (
        not lifecycle.verified_flat
        or flat_ms is None
        or sum(fill.size for fill in exits) >= size - SIZE_TOLERANCE
    ):
        return exits, "order_ids"
    entries = set(evidence.lifecycles)
    extra = [
        fill
        for oid, legs in evidence.fills.items()
        if oid not in lifecycle.exit_oids and oid not in entries
        for fill in legs.values()
        if fill.direction.startswith("Close") and entry_ms < fill.venue_ms <= flat_ms
    ]
    return exits + extra, "order_ids_plus_time_window" if extra else "order_ids"


def _capped(
    row: Mapping[str, object],
    evidence: AssetEvidence,
    supplemental: Mapping[str, MarkSeries],
    options: Options,
    exit_fee_rate: float,
    outage: bool,
) -> Record:
    if not outage:
        return {
            "status": "not_capped",
            "net_usd": row["net_usd"],
            "r_multiple": row["r_multiple"],
        }
    cap_ms = _i(row, "opened_at_ms") + _i(row, "maximum_hold_seconds") * 1000
    mark = _mark(str(row["symbol"]), cap_ms, evidence, supplemental, options)
    if mark is None:
        return {
            "status": "cap_mark_unavailable",
            "cap_time_utc": _utc(cap_ms),
            "net_usd": None,
            "r_multiple": None,
        }
    side, entry, size = str(row["side"]), _f(row, "entry_price"), _f(row, "size")
    price = mark.exit_price(side)
    sign = 1.0 if side == "long" else -1.0
    net = (
        sign * (price - entry) * size
        - _f(row, "entry_fee_usd")
        - exit_fee_rate * price * size
        + _funding(evidence, _i(row, "entry_ms"), cap_ms)
    )
    risk = row["risk_usd"]
    return {
        "status": "capped",
        "cap_time_utc": _utc(cap_ms),
        "mark_time_utc": _utc(mark.ms),
        "mark_source": mark.source,
        "exit_price": price,
        "net_usd": net,
        "r_multiple": net / risk if isinstance(risk, float) and risk else None,
    }


def _post_exit_mark(
    row: Mapping[str, object],
    target_ms: int,
    evidence: AssetEvidence,
    supplemental: Mapping[str, MarkSeries],
    options: Options,
) -> Record:
    mark = _mark(str(row["symbol"]), target_ms, evidence, supplemental, options)
    if mark is None:
        last = evidence.marks.last_ms
        pending = last is None or last < target_ms
        return {
            "status": "pending" if pending else "unavailable",
            "target_utc": _utc(target_ms),
        }
    sign = 1.0 if row["side"] == "long" else -1.0
    move = sign * (mark.mid / _f(row, "exit_price") - 1) * BPS
    stop_bps = row.get("stop_bps")
    return {
        "status": "observed",
        "target_utc": _utc(target_ms),
        "mark_time_utc": _utc(mark.ms),
        "mark_source": mark.source,
        "mid": mark.mid,
        "move_bps": move,
        "move_r": move / stop_bps if isinstance(stop_bps, float) and stop_bps else None,
    }


# ---------------------------------------------------------------- analyses


def _extension(row: Mapping[str, object], cohort: CohortEvidence) -> Record:
    decided = _int(row.get("decision_time_ms"))
    evaluation = (
        cohort.entries.get((str(row["strategy_id"]), str(row["symbol"]), decided))
        if decided is not None
        else None
    )
    base: Record = {
        "entry_oid": row["entry_oid"],
        "symbol": row["symbol"],
        "side": row["side"],
        "decision_time_utc": _utc(decided),
        "status": row["status"],
        "net_usd": row.get("net_usd"),
        "r_multiple": row.get("r_multiple"),
    }
    if evaluation is None:
        return {**base, "extension_atr": None, "weak": None, "evidence": "missing"}
    readiness = evaluation.get("readiness")
    metrics = readiness.get("metrics") if isinstance(readiness, Mapping) else None
    metrics = metrics if isinstance(metrics, Mapping) else {}
    close = _num(evaluation.get("reference_price"))
    atr = _num(metrics.get("atr"))
    low, high = (
        _num(metrics.get("prior_entry_low")),
        _num(metrics.get("prior_entry_high")),
    )
    extension = None
    if close is not None and atr and atr > 0:
        if row["side"] == "short" and low is not None:
            extension = (low - close) / atr
        elif row["side"] == "long" and high is not None:
            extension = (close - high) / atr
    weak = (
        extension < WEAK_SHORT_ATR
        if row["side"] == "short" and extension is not None
        else None
    )
    return {
        **base,
        "signal_close": close,
        "atr": atr,
        "prior_entry_low": low,
        "prior_entry_high": high,
        "extension_atr": extension,
        "weak": weak,
        "evidence": "intent_routing_readiness_metrics",
    }


def _timer_counterfactual(
    row: Mapping[str, object],
    evidence: AssetEvidence,
    cohort: CohortEvidence,
    reentries: Sequence[Mapping[str, object]],
    options: Options,
) -> Record | None:
    state = cohort.adaptive.get((str(row["symbol"]), _i(row, "entry_oid")))
    if state is None or not state.get("floor_armed"):
        return None
    side, entry = str(row["side"]), _f(row, "entry_price")
    size, exit_ms = _f(row, "size"), _i(row, "exit_ms")
    sign = 1.0 if side == "long" else -1.0
    stop_bps = row.get("stop_bps")
    floor = _num(state.get("floor_bps"))
    if floor is None:
        risk_bps = _num(state.get("risk_bps")) or (
            stop_bps if isinstance(stop_bps, float) else None
        )
        floor = FLOOR_R * risk_bps if risk_bps is not None else None
    recipe_ms = next(
        (
            decided
            for decided in cohort.recipe_exits.get((str(row["symbol"]), side), [])
            if decided > exit_ms
        ),
        None,
    )
    horizon_end = exit_ms + options.counterfactual_horizon_ms
    reason, exit_mark, favorable, adverse = "unresolved", None, None, None
    for mark in evidence.marks.after(exit_ms, horizon_end):
        price = mark.exit_price(side)
        pnl = sign * (price / entry - 1) * BPS
        favorable = pnl if favorable is None else max(favorable, pnl)
        adverse = pnl if adverse is None else min(adverse, pnl)
        exit_mark = mark
        if recipe_ms is not None and mark.ms >= recipe_ms:
            reason = RECIPE_EXIT_REASON
            break
        if floor is not None and pnl <= floor:
            reason = PROFIT_FLOOR_EXIT
            break
    result: Record = {
        "entry_oid": row["entry_oid"],
        "symbol": row["symbol"],
        "side": side,
        "floor_armed": True,
        "floor_bps": floor,
        "timer_exit_time_utc": row["exit_time_utc"],
        "timer_exit_price": row["exit_price"],
        "timer_net_usd": row["net_usd"],
        "counterfactual_exit_reason": reason,
        "counterfactual_exit_time_utc": _utc(exit_mark.ms) if exit_mark else None,
        "counterfactual_exit_price": exit_mark.exit_price(side) if exit_mark else None,
        "counterfactual_net_usd": None,
        "delta_vs_timer_usd": None,
        "max_favorable_bps": favorable,
        "max_adverse_bps": adverse,
        "post_exit_marks": row.get("post_exit_marks"),
        "omitted": "regime-flip ratchet and post-exit funding are not simulated",
    }
    if exit_mark is not None:
        price = exit_mark.exit_price(side)
        net = (
            sign * (price - entry) * size
            - _f(row, "entry_fee_usd")
            - _f(row, "exit_fee_rate") * price * size
            + _f(row, "funding_usd")
        )
        result["counterfactual_net_usd"] = net
        result["delta_vs_timer_usd"] = net - _f(row, "net_usd")
        result["reentries_before_counterfactual_exit"] = [
            other["entry_oid"]
            for other in reentries
            if other["symbol"] == row["symbol"]
            and exit_ms < _i(other, "opened_at_ms") <= exit_mark.ms
        ]
    return result


def _buy_and_hold(
    rows: Sequence[Mapping[str, object]],
    assets: Mapping[str, AssetEvidence],
    selection: Selection,
) -> dict[str, Record]:
    output: dict[str, Record] = {}
    for symbol, evidence in assets.items():
        end = (
            selection.until_ms
            if selection.until_ms is not None
            else evidence.marks.last_ms
        )
        if end is None:
            continue
        marks = evidence.marks.within(selection.since_ms, end)
        if len(marks) < 2 or marks[-1].ms <= marks[0].ms:
            continue
        first, last = marks[0], marks[-1]
        window = last.ms - first.ms
        change = last.mid / first.mid - 1
        in_market, scaled_usd, strategy_net = 0, 0.0, 0.0
        for row in rows:
            if row["symbol"] != symbol:
                continue
            start = max(_i(row, "entry_ms"), first.ms)
            stop = min(_i(row, "in_market_until_ms"), last.ms)
            overlap = max(0, stop - start)
            in_market += overlap
            scaled_usd += _f(row, "notional_usd") * change * overlap / window
            strategy_net += _num(row.get("net_usd")) or 0.0
        fraction = in_market / window
        output[symbol] = {
            "window_start_utc": _utc(first.ms),
            "window_end_utc": _utc(last.ms),
            "first_mid": first.mid,
            "last_mid": last.mid,
            "window_bps": change * BPS,
            "time_in_market_fraction": fraction,
            "time_scaled_bps": change * BPS * fraction,
            "time_scaled_usd": scaled_usd,
            "strategy_net_usd": strategy_net,
        }
    return output


def _equity(series: Sequence[tuple[int, float]]) -> Record:
    if not series:
        return {"observations": 0}
    high, worst, high_ms = -math.inf, 0.0, series[0][0]
    for ms, value in series:
        if value > high:
            high, high_ms = value, ms
        worst = min(worst, value / high - 1)
    last_ms, last = series[-1]
    return {
        "observations": len(series),
        "first_usd": series[0][1],
        "first_utc": _utc(series[0][0]),
        "last_usd": last,
        "last_utc": _utc(last_ms),
        "high_water_usd": high,
        "high_water_utc": _utc(high_ms),
        "drawdown_from_high": last / high - 1,
        "max_drawdown_from_high": worst,
    }


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _ex_top(values: Sequence[float]) -> float:
    return sum(values) - sum(sorted(values, reverse=True)[:EXCLUDED_TOP])


def _basis(rows: Sequence[Mapping[str, object]], capped: bool) -> list[float | None]:
    if not capped:
        return [_num(row.get("r_multiple")) for row in rows]
    values: list[float | None] = []
    for row in rows:
        cap = row.get("capped")
        values.append(_num(cap.get("r_multiple")) if isinstance(cap, Mapping) else None)
    return values


def _nets(rows: Sequence[Mapping[str, object]], capped: bool) -> list[float | None]:
    if not capped:
        return [_num(row.get("net_usd")) for row in rows]
    values: list[float | None] = []
    for row in rows:
        cap = row.get("capped")
        values.append(_num(cap.get("net_usd")) if isinstance(cap, Mapping) else None)
    return values


def _reconciled(row: Mapping[str, object]) -> bool:
    return row.get("status") == "closed" and _num(row.get("r_multiple")) is not None


def _ladder_basis(
    rows: Sequence[Mapping[str, object]], capped: bool
) -> tuple[list[float | None], list[float | None]]:
    """Return R and net per close, unknown for a close without a reconciled R."""
    known = [_reconciled(row) for row in rows]
    r_values = [
        value if keep else None
        for value, keep in zip(_basis(rows, capped), known, strict=True)
    ]
    nets = [
        value if keep else None
        for value, keep in zip(_nets(rows, capped), known, strict=True)
    ]
    return r_values, nets


def evaluate_ladder(
    closed: Sequence[Mapping[str, object]],
    equity: Sequence[tuple[int, float]],
) -> Record:
    """Apply the pre-registered advance and step-down rules to closes in exit order.

    ``closed`` holds every verified-flat lifecycle, reconciled or not. A close
    that is unreconciled, or whose R is unknown, keeps its place in the sample
    with unknown values, so the advance stays indeterminate until it is resolved.
    """
    window = list(closed[:ADVANCE_CLOSES])
    unreconciled = sum(not _reconciled(row) for row in window)
    capped_r, capped_net = _ladder_basis(window, True)
    missing = sum(
        _reconciled(row) and (r is None or net is None)
        for row, r, net in zip(window, capped_r, capped_net, strict=True)
    )
    known_r = [value for value in capped_r if value is not None]
    known_net = [value for value in capped_net if value is not None]
    mean_r = _mean(known_r)
    ex_top = _ex_top(known_net)
    if len(window) < ADVANCE_CLOSES:
        status = "pending"
    elif missing or unreconciled:
        status = "indeterminate"
    elif mean_r is not None and mean_r > 0 and ex_top >= 0:
        status = "advance"
    else:
        status = "not_met"
    realized_r, realized_net = _ladder_basis(window, False)
    actual_r = [value for value in realized_r if value is not None]
    actual_net = [value for value in realized_net if value is not None]
    advance: Record = {
        "status": status,
        "closed": len(window),
        "required": ADVANCE_CLOSES,
        "basis": "capped (holds beyond the configured maximum hold capped)",
        "mean_r": mean_r,
        "net_usd": sum(known_net),
        "ex_top3_net_usd": ex_top,
        "capped_mark_unavailable": missing,
        "unreconciled": unreconciled,
        "actual_mean_r": _mean(actual_r),
        "actual_ex_top3_net_usd": _ex_top(actual_net),
        "rule": "first 30 Donchian closes since rung start: mean R > 0 and "
        "ex-top-3 net >= 0 at measured cost",
    }
    # Step-down is risk-reducing, so it fires on either basis; a missing capped
    # value falls back to the realized R of the same close.
    realized = _ladder_basis(closed, False)[0]
    capped_all = [
        value if value is not None else actual
        for value, actual in zip(_ladder_basis(closed, True)[0], realized, strict=True)
    ]
    worst: float | None = None
    for values in (capped_all, realized):
        for start in range(len(values) - STEP_DOWN_CLOSES + 1):
            block = [
                value
                for value in values[start : start + STEP_DOWN_CLOSES]
                if value is not None
            ]
            if len(block) < STEP_DOWN_CLOSES:
                continue
            mean = sum(block) / STEP_DOWN_CLOSES
            worst = mean if worst is None else min(worst, mean)
    equity_summary = _equity(equity)
    max_drawdown = _num(equity_summary.get("max_drawdown_from_high"))
    drawdown_triggered = (
        max_drawdown is not None and max_drawdown <= STEP_DOWN_DRAWDOWN + 1e-12
    )
    window_triggered = worst is not None and worst < 0
    step_down: Record = {
        "triggered": drawdown_triggered or window_triggered,
        "drawdown_triggered": drawdown_triggered,
        "max_drawdown_from_high": max_drawdown,
        "drawdown_limit": STEP_DOWN_DRAWDOWN,
        "window_triggered": window_triggered,
        "worst_window_mean_r": worst,
        "window": STEP_DOWN_CLOSES,
        "closed": len(closed),
        "unreconciled": sum(not _reconciled(row) for row in closed),
        "rule": "step down to rung 0 on -12% from the rung high, or mean R < 0 "
        "over any 50 consecutive closes (capped or realized basis)",
    }
    return {"advance": advance, "step_down": step_down}


def _summary(rows: Sequence[Mapping[str, object]]) -> Record:
    closed = [row for row in rows if row["status"] == "closed"]
    nets = [value for value in _nets(closed, False) if value is not None]
    capped_nets = [value for value in _nets(closed, True) if value is not None]
    r_values = [value for value in _basis(closed, False) if value is not None]
    capped_r = [value for value in _basis(closed, True) if value is not None]
    return {
        "closed": len(closed),
        "open": sum(row["status"] == "open" for row in rows),
        "unreconciled": sum(
            row["status"] in ("closed_size_mismatch", "closed_without_fills")
            for row in rows
        ),
        "wins": sum(value > 0 for value in nets),
        "net_usd": sum(nets),
        "mean_r": _mean(r_values),
        "ex_top3_net_usd": _ex_top(nets),
        "capped_net_usd": sum(capped_nets),
        "capped_mean_r": _mean(capped_r),
        "capped_ex_top3_net_usd": _ex_top(capped_nets),
        "outage_holds": sum(bool(row.get("outage_hold")) for row in closed),
        "capped_mark_unavailable": sum(value is None for value in _nets(closed, True)),
        "exit_reasons": dict(Counter(str(row.get("exit_reason")) for row in closed)),
        "net_usd_by_symbol": {
            symbol: sum(
                _num(row.get("net_usd")) or 0.0
                for row in closed
                if row["symbol"] == symbol
            )
            for symbol in sorted({str(row["symbol"]) for row in closed})
        },
        "cost_basis": "measured: realized venue PnL, fees and funding",
    }


def build_report(
    *,
    ledger_dir: Path,
    profile_id: str | None,
    run_ids: Sequence[str],
    since: str,
    until: str | None,
    symbols: Sequence[str] = DEFAULT_SYMBOLS,
    strategy_prefix: str = DEFAULT_STRATEGY_PREFIX,
    hold_grace_seconds: float = DEFAULT_HOLD_GRACE_SECONDS,
    mark_tolerance_seconds: float = DEFAULT_MARK_TOLERANCE_SECONDS,
    counterfactual_horizon_hours: float = DEFAULT_COUNTERFACTUAL_HORIZON_HOURS,
    supplemental_marks: Path | None = None,
) -> Record:
    """Scan the ledgers once and assemble the full ladder evidence report."""
    if profile_id is None and not run_ids:
        raise ValueError("select at least one run id or a profile id")
    selection = Selection(
        profile_id,
        frozenset(run_ids),
        _iso_ms(since),
        _iso_ms(until) if until else None,
    )
    options = Options(
        strategy_prefix,
        int(hold_grace_seconds * 1000),
        int(mark_tolerance_seconds * 1000),
        int(counterfactual_horizon_hours * HOUR_MS),
    )
    horizon = max(POST_EXIT_MINUTES) * MINUTE_MS + options.counterfactual_horizon_ms
    marks_until = selection.until_ms + horizon if selection.until_ms else None
    assets = {
        symbol: scan_asset_ledger(
            ledger_dir / f"{symbol.lower()}.jsonl",
            symbol,
            selection,
            marks_until_ms=marks_until,
        )
        for symbol in symbols
    }
    cohort = scan_cohort_ledger(
        ledger_dir / COHORT_LEDGER,
        selection,
        strategy_prefix=strategy_prefix,
        evaluations_until_ms=marks_until,
    )
    supplemental = (
        load_supplemental_marks(supplemental_marks) if supplemental_marks else {}
    )
    now_ms = selection.until_ms or int(datetime.now(tz=UTC).timestamp() * 1000)
    rows: list[Record] = []
    for evidence in assets.values():
        for lifecycle in evidence.lifecycles.values():
            if not (lifecycle.strategy_id or "").startswith(strategy_prefix):
                continue
            if not lifecycle.entry_acknowledged:
                continue
            row = _lifecycle_row(lifecycle, evidence, supplemental, options, now_ms)
            if row is not None and selection.in_window(_i(row, "opened_at_ms")):
                rows.append(row)
    rows.sort(key=lambda row: (_i(row, "opened_at_ms"), str(row["symbol"])))
    closed = sorted(
        (row for row in rows if row["status"] == "closed"),
        key=lambda row: _i(row, "exit_ms"),
    )
    # The ladder sample is every verified-flat lifecycle in exit order, so an
    # unreconciled close keeps its place instead of pulling a later one in.
    ladder_sample = sorted(
        (row for row in rows if row["status"] != "open"),
        key=lambda row: _i(row, "exit_ms"),
    )
    extensions = [_extension(row, cohort) for row in rows]
    timer_exits = [row for row in closed if row.get("exit_reason") == TIMER_EXIT_REASON]
    counterfactuals = [
        result
        for row in timer_exits
        if (
            result := _timer_counterfactual(
                row, assets[str(row["symbol"])], cohort, rows, options
            )
        )
        is not None
    ]
    return {
        "execution_authority": "none",
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "selection": {
            "ledger_dir": str(ledger_dir),
            "profile_id": profile_id,
            "run_ids": sorted(run_ids),
            "since_utc": _utc(selection.since_ms),
            "until_utc": _utc(selection.until_ms),
            "symbols": list(symbols),
            "strategy_prefix": strategy_prefix,
            "hold_grace_seconds": hold_grace_seconds,
            "mark_tolerance_seconds": mark_tolerance_seconds,
            "counterfactual_horizon_hours": counterfactual_horizon_hours,
            "supplemental_marks": str(supplemental_marks)
            if supplemental_marks
            else None,
        },
        "ledger_stats": {
            COHORT_LEDGER: dict(cohort.stats),
            **{
                f"{symbol.lower()}.jsonl": dict(assets[symbol].stats)
                for symbol in symbols
            },
            "book_marks": {
                symbol: len(assets[symbol].marks.marks) for symbol in symbols
            },
        },
        "summary": _summary(rows),
        "ladder": evaluate_ladder(ladder_sample, cohort.equity),
        "equity": _equity(cohort.equity),
        "lifecycles": rows,
        "donchian_entry_extension": extensions,
        "donchian_short_extension": [
            row for row in extensions if row["side"] == "short"
        ],
        "timer_counterfactual": counterfactuals,
        "timer_exits": {
            "total": len(timer_exits),
            "floor_armed": len(counterfactuals),
        },
        "buy_and_hold": _buy_and_hold(rows, assets, selection),
    }


# ---------------------------------------------------------------- output


def _fmt(value: object, pattern: str = "{:+.2f}") -> str:
    return "n/a" if not isinstance(value, (int, float)) else pattern.format(value)


def summary_text(report: Mapping[str, object]) -> str:
    """Return the short operator summary printed to stdout."""
    summary = report["summary"]
    ladder = report["ladder"]
    equity = report["equity"]
    assert isinstance(summary, Mapping) and isinstance(ladder, Mapping)
    assert isinstance(equity, Mapping)
    advance, step = ladder["advance"], ladder["step_down"]
    assert isinstance(advance, Mapping) and isinstance(step, Mapping)
    selection = report["selection"]
    assert isinstance(selection, Mapping)
    runs = selection["run_ids"]
    assert isinstance(runs, list)
    shorts = report["donchian_short_extension"]
    assert isinstance(shorts, list)
    weak = [row for row in shorts if row.get("weak") is True]
    counterfactuals = report["timer_counterfactual"]
    assert isinstance(counterfactuals, list)
    lines = [
        "cohort ladder evidence (execution_authority: none)",
        f"selection: runs={','.join(map(str, runs)) or '-'} "
        f"profile={selection['profile_id'] or '-'} since={selection['since_utc']}",
        f"closed Donchian lifecycles: {summary['closed']} (open {summary['open']}); "
        f"net ${_fmt(summary['net_usd'])}; mean R {_fmt(summary['mean_r'], '{:+.3f}')}; "
        f"ex-top-3 net ${_fmt(summary['ex_top3_net_usd'])}",
        f"capped basis: {summary['outage_holds']} outage hold(s), "
        f"{summary['capped_mark_unavailable']} without a cap mark; net "
        f"${_fmt(summary['capped_net_usd'])}; mean R "
        f"{_fmt(summary['capped_mean_r'], '{:+.3f}')}",
        f"unreconciled lifecycles: {summary['unreconciled']} (verified flat, exit "
        f"fills incomplete; {advance['unreconciled']} in the advance window without "
        "a reconciled R)",
        f"equity: last ${_fmt(equity.get('last_usd'), '{:.2f}')}, high-water "
        f"${_fmt(equity.get('high_water_usd'), '{:.2f}')}, drawdown from high "
        f"{_fmt(equity.get('drawdown_from_high'), '{:+.2%}')}",
        f"advance: {advance['status']} ({advance['closed']}/{advance['required']} "
        f"closes; mean R {_fmt(advance['mean_r'], '{:+.3f}')}; ex-top-3 net "
        f"${_fmt(advance['ex_top3_net_usd'])})",
        f"step-down: {'TRIGGERED' if step['triggered'] else 'not triggered'} "
        f"(max drawdown {_fmt(step['max_drawdown_from_high'], '{:+.2%}')}; worst "
        f"50-close mean R {_fmt(step['worst_window_mean_r'], '{:+.3f}')})",
        f"Donchian shorts: {len(shorts)}, weak (< {WEAK_SHORT_ATR:.1f} ATR): "
        f"{len(weak)} "
        + "["
        + ", ".join(
            f"{row['symbol']} {_fmt(row.get('extension_atr'), '{:.2f}')}"
            for row in shorts
        )
        + "]",
        f"floor-armed 24h-timer exits: {len(counterfactuals)}; counterfactual delta "
        f"${_fmt(sum(float(row.get('delta_vs_timer_usd') or 0.0) for row in counterfactuals))}",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ledger-dir", type=Path, default=DEFAULT_LEDGER_DIR)
    parser.add_argument("--profile-id")
    parser.add_argument("--run-id", action="append", default=[])
    parser.add_argument("--since", required=True, help="ISO-8601 UTC rung start")
    parser.add_argument("--until", help="ISO-8601 UTC end (default: ledger end)")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--strategy-prefix", default=DEFAULT_STRATEGY_PREFIX)
    parser.add_argument(
        "--hold-grace-seconds", type=float, default=DEFAULT_HOLD_GRACE_SECONDS
    )
    parser.add_argument(
        "--mark-tolerance-seconds", type=float, default=DEFAULT_MARK_TOLERANCE_SECONDS
    )
    parser.add_argument(
        "--counterfactual-horizon-hours",
        type=float,
        default=DEFAULT_COUNTERFACTUAL_HORIZON_HOURS,
    )
    parser.add_argument(
        "--supplemental-marks",
        type=Path,
        help="CSV symbol,time,price used only where no book observation exists",
    )
    parser.add_argument("--out", type=Path, help="write the JSON report here")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Write the JSON report (when --out is given) and print the summary."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.run_id and not args.profile_id:
        parser.error("select at least one --run-id or a --profile-id")
    report = build_report(
        ledger_dir=args.ledger_dir,
        profile_id=args.profile_id,
        run_ids=tuple(args.run_id),
        since=args.since,
        until=args.until,
        symbols=tuple(
            symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()
        ),
        strategy_prefix=args.strategy_prefix,
        hold_grace_seconds=args.hold_grace_seconds,
        mark_tolerance_seconds=args.mark_tolerance_seconds,
        counterfactual_horizon_hours=args.counterfactual_horizon_hours,
        supplemental_marks=args.supplemental_marks,
    )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(summary_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
