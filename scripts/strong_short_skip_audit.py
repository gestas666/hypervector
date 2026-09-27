#!/usr/bin/env python3
"""Read-only audit of the shorts the V94 strong-short rule skipped (review SIG-2).

Report-only. execution_authority: none. It builds no venue client, signs
nothing and makes no network call. It reads completed venue 1m candles already
on disk, rebuilds the live 15m source bars with the live resampler, and replays
the live publication path (``HourlyPriceCollector``) twice per symbol: once for
the unfiltered Donchian 20/10 identity and once for the V94 strong-short
identity. Every completed-hour decision (keyed at hh:00) where the unfiltered
identity enters short and the strong-short identity does not is a skip. Longs,
exit sides and the stop anchors of shared entries must match between the two
identities, and kept shorts must reach the threshold; the audit counts every
divergence.

The router holds one position per symbol (``enter_and_close``): a short routed
while a position is open is withheld (same side) or only closes it (opposite
side). So a skip is an independent trade only if the symbol is flat. Skips are
walked from the start of the data, before ``--since`` too: a skip fired while an
earlier scored skip is still open (``overlaps_prior_skip``), or while a live
lifecycle from an optional ladder evidence report holds the symbol
(``live_position_open``), is listed but never scored, and it counts neither in
the summary nor in the falsifier. An overlapping skip is never entered, so it
does not extend the block. Without a ladder report the kept longs and strong
shorts the book would hold are not modeled.

Each independent skip is scored as one hypothetical position under the live
stop and exit geometry of the hourly price contract (``hourly_price_contract.py``):

- entry at the open of the 1m candle at the decision time (the live IOC fills
  about 10-20 s later);
- structural stop at the signal's 2 x ATR anchor, clamped to 20-250 bps from
  the entry, filled at the stop or at a worse candle open;
- the channel recipe exit at the next completed hour whose exit side includes
  short, at that 1m open;
- the fixed 24 h maximum hold, at the first 1m open at or after it;
- the v2 profit floor (``advance_retention_exit``: armed at a 2R peak, exits at
  0.5R), evaluated on candle open, adverse extreme and favorable extreme in that
  order. The regime-flip giveback needs live regime alignment and is omitted.

Costs are modeled: a round-trip taker fee per venue class plus a stop slippage
on stop exits. R is net bps over the skip's own stop distance.

Candles older than ``--since`` minus ``--lookback-hours`` are ignored in every
input format; a JSONL ledger is bisected to that time instead of being streamed
whole. A gap in the 1m candles restarts the channel's warm-up, where live would
have backfilled it from the venue, so the coverage lists gaps per symbol.

The pre-registered falsifier (review SIG-2): after at least 40 resolved
independent skips, re-open the weak-short rule only if the skipped shorts' net R
is > 0 and their ex-top-3 net R is >= 0. Re-opening is a new identity and its
own transition; this tool only reports.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import sys

from cohort_ladder_evidence import seek_offset
import numpy as np
from numpy.typing import NDArray
import pandas as pd

from hypervector.live.cohort_adaptive_exit_policy import (
    RetentionExitObservation,
    RetentionExitState,
    advance_retention_exit,
)
from hypervector.live.hourly_price_provider import (
    DONCHIAN20_STRATEGY,
    STRONG_SHORT_DONCHIAN20_STRATEGY,
    STRONG_SHORT_MINIMUM_EXTENSION_ATR,
    HourlyPriceCollector,
)
from hypervector.live.multi_asset_market_bars import resample_one_minute_bars
from hypervector.live.multi_asset_signal_source import ProviderEvaluation

DEFAULT_SYMBOLS = ("SOL", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA")
# The hourly price contract pins these (hourly_price_contract.py).
MINIMUM_STOP_BPS = 20.0
MAXIMUM_STOP_BPS = 250.0
MAXIMUM_HOLD_MS = 86_400_000
# Modeled costs (docs/plans/2026-09-24-v94-size-ladder.md section 1): taker fees
# round trip, and the measured stop slip (SNDK median 9.3 bps) rounded up.
DEFAULT_HIP3_ROUND_TRIP_BPS = 1.7
DEFAULT_CRYPTO_ROUND_TRIP_BPS = 8.6
DEFAULT_STOP_SLIPPAGE_BPS = 10.0
FALSIFIER_MINIMUM_SKIPS = 40
EXCLUDED_TOP = 3
ENTRY_TOLERANCE_MS = 5 * 60_000
MINUTE_MS = 60_000
HOUR_MS = 3_600_000
BPS = 10_000.0
# Warm-up to the first ready decision (about 21 h), the 24 h hold of a skip that
# can still block the first one after --since, and at least the ~83 h of 1m
# history the live collector holds after a restart (review SIG-3).
DEFAULT_LOOKBACK_HOURS = 96.0
REQUIRED_COLUMNS = ("open", "high", "low", "close")
PROTECTIVE_STOP = "protective_stop"
RECIPE_EXIT = "hourly_price_recipe_exit"
MAXIMUM_HOLD = "maximum_hold_seconds"
# Skips the router could never have entered: listed, not scored or counted.
PRIOR_SKIP_OPEN = "overlaps_prior_skip"
LIVE_POSITION_OPEN = "live_position_open"
OVERLAP_STATUSES = frozenset({PRIOR_SKIP_OPEN, LIVE_POSITION_OPEN})
SIDES = ("long", "short")

Record = dict[str, object]
FloatArray = NDArray[np.float64]


# ---------------------------------------------------------------- candles


def _utc(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def _iso_ms(value: str) -> int:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return int(round(stamp.timestamp() * 1000))


def _event_bars(
    payload: object, symbols: frozenset[str] | None = None
) -> Iterator[dict[str, object]]:
    """Flatten one ``market_candles`` payload into symbol-tagged 1m bars."""
    if isinstance(payload, (str, bytes)):
        payload = json.loads(payload)
    if not isinstance(payload, Mapping) or payload.get("timeframe") != "1m":
        return
    bars = payload.get("bars")
    if not isinstance(bars, Mapping):
        return
    for symbol, rows in bars.items():
        if not isinstance(rows, list) or (
            symbols is not None and symbol not in symbols
        ):
            continue
        for row in rows:
            if isinstance(row, Mapping):
                yield {"symbol": symbol, **row}


def _jsonl_bars(
    path: Path, start_ms: int | None, symbols: frozenset[str] | None
) -> Iterator[dict[str, object]]:
    """Stream ``market_candles`` rows, bisected to rows observed at ``start_ms``.

    A completed candle is journaled after it closes, so no bar at or after
    ``start_ms`` sits in a row observed before it.
    """
    offset = seek_offset(path, start_ms) if start_ms is not None else 0
    with path.open("rb") as handle:
        handle.seek(offset)
        if offset:
            handle.readline()
        for line in handle:
            if b'"market_candles"' not in line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, Mapping) and row.get("event_type") == "market_candles":
                yield from _event_bars(row.get("payload"), symbols)


def load_candles(
    path: Path,
    *,
    start_ms: int | None = None,
    symbols: Sequence[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Completed 1m candles per symbol, sorted and de-duplicated (last wins).

    Accepts journaled ``market_candles`` events (a JSONL ledger, or a parquet or
    CSV extract with ``event_type`` and ``payload`` columns) or a flat table with
    ``symbol``, ``timestamp_ms`` (or ``timestamp``) and OHLC columns. Candles
    before ``start_ms`` and symbols outside ``symbols`` are dropped in every
    format.
    """
    wanted = frozenset(symbols) if symbols is not None else None
    if path.suffix == ".jsonl":
        frame = pd.DataFrame(list(_jsonl_bars(path, start_ms, wanted)))
    else:
        if path.suffix == ".parquet":
            table = pd.read_parquet(path)
        elif path.suffix == ".csv":
            table = pd.read_csv(path)
        else:
            raise ValueError(f"unsupported candle file: {path}")
        if "payload" in table.columns:
            if "event_type" in table.columns:
                table = table[table["event_type"] == "market_candles"]
            frame = pd.DataFrame(
                [
                    bar
                    for payload in table["payload"]
                    for bar in _event_bars(payload, wanted)
                ]
            )
        else:
            frame = table
    if wanted is not None and "symbol" in frame.columns:
        frame = frame[frame["symbol"].isin(wanted)]
    if frame.empty:
        return {}
    if "timestamp_ms" in frame.columns:
        stamps = pd.to_datetime(
            frame["timestamp_ms"].astype("int64"), unit="ms", utc=True
        )
    elif "timestamp" in frame.columns:
        stamps = pd.to_datetime(frame["timestamp"], utc=True)
    else:
        raise ValueError(f"{path} candles lack timestamp_ms or timestamp")
    missing = {"symbol", *REQUIRED_COLUMNS}.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} candles lack columns: {sorted(missing)}")
    frame = frame.assign(timestamp=stamps)
    if start_ms is not None:
        frame = frame[frame["timestamp"] >= pd.Timestamp(start_ms, unit="ms", tz="UTC")]
    if "volume" not in frame.columns:
        frame = frame.assign(volume=0.0)
    frame = frame.loc[:, ["symbol", "timestamp", *REQUIRED_COLUMNS, "volume"]]
    frame = frame.sort_values(["symbol", "timestamp"], kind="stable").drop_duplicates(
        subset=["symbol", "timestamp"], keep="last"
    )
    return {
        str(symbol): group.drop(columns="symbol").reset_index(drop=True)
        for symbol, group in frame.groupby("symbol", sort=True)
    }


# ---------------------------------------------------------------- replay


@dataclass(frozen=True)
class Replay:
    """Both identities' evaluations for one symbol, keyed by decision time."""

    baseline: dict[int, ProviderEvaluation]
    filtered: dict[int, ProviderEvaluation]
    fifteen_minute_bars: int


def replay_symbol(
    symbol: str, one_minute: pd.DataFrame, observed_at: pd.Timestamp
) -> Replay:
    """Run the live publication path for both identities over the same bars."""
    fifteen = resample_one_minute_bars(one_minute, minutes=15)
    fifteen = fifteen.loc[
        fifteen["timestamp"] + pd.Timedelta(minutes=15) <= observed_at
    ]
    if fifteen.empty:
        return Replay({}, {}, 0)
    evaluations = {}
    for strategy in (DONCHIAN20_STRATEGY, STRONG_SHORT_DONCHIAN20_STRATEGY):
        batch = HourlyPriceCollector(strategy_id=strategy)(
            fifteen,
            symbol=symbol,
            observed_at=observed_at,
            after_decision_time_ms=None,
        )
        evaluations[strategy] = {row.decision_time_ms: row for row in batch.evaluations}
    return Replay(
        evaluations[DONCHIAN20_STRATEGY],
        evaluations[STRONG_SHORT_DONCHIAN20_STRATEGY],
        len(fifteen),
    )


def _metric(evaluation: ProviderEvaluation, name: str) -> float | None:
    value = evaluation.readiness.metrics.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _enters(evaluation: ProviderEvaluation | None, side: str) -> bool:
    return evaluation is not None and evaluation.eligible and evaluation.side == side


def short_extension_atr(evaluation: ProviderEvaluation) -> float | None:
    """Breakdown depth beyond the prior 20-bar low, in ATR (live metric names)."""
    low, atr = _metric(evaluation, "prior_entry_low"), _metric(evaluation, "atr")
    if low is None or atr is None or atr <= 0:
        return None
    return (low - evaluation.reference_price) / atr


def identity_check(replay: Replay) -> Counter[str]:
    """Count every divergence other than a filtered weak short."""
    counts: Counter[str] = Counter()
    for decided in sorted(set(replay.baseline) | set(replay.filtered)):
        base, kept = replay.baseline.get(decided), replay.filtered.get(decided)
        if _enters(base, "long") != _enters(kept, "long"):
            counts["long_mismatches"] += 1
        if _enters(kept, "short") and not _enters(base, "short"):
            counts["filtered_only_shorts"] += 1
        if base is not None and kept is not None and base.exit_sides != kept.exit_sides:
            counts["exit_mismatches"] += 1
        if (
            base is not None
            and kept is not None
            and any(_enters(base, side) and _enters(kept, side) for side in SIDES)
            and _metric(base, "stop_price") != _metric(kept, "stop_price")
        ):
            counts["stop_mismatches"] += 1
        if _enters(kept, "short"):
            extension = short_extension_atr(kept)
            if extension is None or extension < STRONG_SHORT_MINIMUM_EXTENSION_ATR:
                counts["kept_shorts_below_threshold"] += 1
    return counts


# ---------------------------------------------------------------- outcome


@dataclass(frozen=True)
class CostModel:
    """Round-trip fees by venue class and slippage on stop exits, in bps."""

    hip3_round_trip_bps: float = DEFAULT_HIP3_ROUND_TRIP_BPS
    crypto_round_trip_bps: float = DEFAULT_CRYPTO_ROUND_TRIP_BPS
    stop_slippage_bps: float = DEFAULT_STOP_SLIPPAGE_BPS

    def fees_bps(self, symbol: str) -> float:
        """HIP-3 markets carry the ``xyz:`` prefix."""
        if symbol.startswith("xyz:"):
            return self.hip3_round_trip_bps
        return self.crypto_round_trip_bps


@dataclass(frozen=True)
class Candles:
    """One symbol's 1m candles as arrays for the path walk."""

    times: NDArray[np.int64]
    open: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> Candles:
        """Index by candle open time in epoch ms."""
        stamps = pd.DatetimeIndex(frame["timestamp"])
        return cls(
            stamps.as_unit("ms").asi8.astype(np.int64),
            frame["open"].to_numpy(dtype=np.float64),
            frame["high"].to_numpy(dtype=np.float64),
            frame["low"].to_numpy(dtype=np.float64),
            frame["close"].to_numpy(dtype=np.float64),
        )


def clamped_short_stop(entry: float, anchor: float) -> tuple[float, float]:
    """The structural_clamped_bps stop for a short: (stop price, distance bps)."""
    distance = (anchor - entry) / entry * BPS
    distance = min(max(distance, MINIMUM_STOP_BPS), MAXIMUM_STOP_BPS)
    return entry * (1 + distance / BPS), distance


def score_short(
    *,
    decision_ms: int,
    anchor: float,
    candles: Candles,
    recipe_exits_ms: Sequence[int],
    fees_bps: float,
    stop_slippage_bps: float,
) -> Record:
    """Walk one hypothetical short through the live stop and exit geometry."""
    start = int(np.searchsorted(candles.times, decision_ms, side="left"))
    if (
        start >= len(candles.times)
        or candles.times[start] - decision_ms > ENTRY_TOLERANCE_MS
    ):
        return {"status": "entry_unavailable"}
    entry_ms = int(candles.times[start])
    entry = float(candles.open[start])
    stop, risk_bps = clamped_short_stop(entry, anchor)
    recipe_ms = next((ms for ms in sorted(recipe_exits_ms) if ms > decision_ms), None)
    hold_end_ms = decision_ms + MAXIMUM_HOLD_MS

    def pnl(price: float) -> float:
        return (entry - price) / entry * BPS

    state = RetentionExitState()
    favorable = adverse = 0.0
    exit_ms = exit_price = reason = None
    for index in range(start, len(candles.times)):
        bar_ms = int(candles.times[index])
        opened = float(candles.open[index])
        if recipe_ms is not None and bar_ms >= recipe_ms:
            exit_ms, exit_price, reason = bar_ms, opened, RECIPE_EXIT
            break
        if bar_ms >= hold_end_ms:
            exit_ms, exit_price, reason = bar_ms, opened, MAXIMUM_HOLD
            break
        high, low = float(candles.high[index]), float(candles.low[index])
        adverse = min(adverse, pnl(high))
        if opened >= stop:
            # A gap through the resting venue stop fills at the open.
            exit_ms, exit_price, reason = bar_ms, opened, PROTECTIVE_STOP
            break
        # Open, then the adverse extreme, then the favorable one: a peak made
        # inside this candle only arms the floor from the next candle on.
        state = _retention(state, bar_ms + 1, pnl(opened), risk_bps)
        if state.exit_reason is not None:
            exit_ms, exit_price, reason = bar_ms, opened, state.exit_reason
            break
        state = _retention(state, bar_ms + 2, pnl(high), risk_bps)
        if state.exit_reason is not None and state.floor_bps is not None:
            floor_price = entry * (1 - state.floor_bps / BPS)
            exit_ms, exit_price, reason = bar_ms, floor_price, state.exit_reason
            break
        if high >= stop:
            exit_ms, exit_price, reason = bar_ms, stop, PROTECTIVE_STOP
            break
        favorable = max(favorable, pnl(low))
        state = _retention(state, bar_ms + 3, pnl(low), risk_bps)
    result: Record = {
        "entry_time_utc": _utc(entry_ms),
        "entry_price": entry,
        "stop_price": stop,
        "stop_bps": risk_bps,
        "max_favorable_bps": favorable,
        "max_adverse_bps": adverse,
        "floor_armed": state.floor_armed,
    }
    if reason is None or exit_price is None:
        last = float(candles.close[-1])
        return {
            **result,
            "status": "open",
            "exit_reason": None,
            "mark_time_utc": _utc(int(candles.times[-1]) + MINUTE_MS),
            "mark_price": last,
            "mark_gross_bps": pnl(last),
        }
    gross = pnl(exit_price)
    slippage = stop_slippage_bps if reason == PROTECTIVE_STOP else 0.0
    net = gross - fees_bps - slippage
    return {
        **result,
        "status": "closed",
        "exit_reason": reason,
        "exit_time_ms": exit_ms,
        "exit_time_utc": _utc(exit_ms),
        "exit_price": exit_price,
        "hold_hours": ((exit_ms or entry_ms) - decision_ms) / 3_600_000,
        "gross_bps": gross,
        "cost_bps": fees_bps + slippage,
        "net_bps": net,
        "gross_r": gross / risk_bps,
        "net_r": net / risk_bps,
    }


def _retention(
    state: RetentionExitState, observed_ms: int, pnl_bps: float, risk_bps: float
) -> RetentionExitState:
    return advance_retention_exit(
        state, RetentionExitObservation(observed_ms, pnl_bps, risk_bps, None)
    )


# ---------------------------------------------------------------- report


def _ex_top(values: Sequence[float]) -> float | None:
    """Sum without the three largest; None while nothing is left after them."""
    if len(values) <= EXCLUDED_TOP:
        return None
    return sum(values) - sum(sorted(values, reverse=True)[:EXCLUDED_TOP])


def _value(row: Mapping[str, object], key: str) -> float:
    """Read a number this report wrote itself."""
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise KeyError(f"skip row lacks numeric {key}")
    return float(value)


def falsifier(net_r: Sequence[float]) -> Record:
    """The pre-registered re-open test on resolved independent skips, in R units."""
    total, ex_top = sum(net_r), _ex_top(net_r)
    if len(net_r) < FALSIFIER_MINIMUM_SKIPS:
        status = "pending"
    elif total > 0 and ex_top is not None and ex_top >= 0:
        status = "reopen_candidate"
    else:
        status = "keep_rule"
    return {
        "rule": f"after >= {FALSIFIER_MINIMUM_SKIPS} resolved independent skipped "
        "shorts, re-open the weak-short rule only if their net R > 0 and ex-top-3 "
        "net R >= 0 (modeled costs); re-opening is a new identity and transition",
        "minimum_skips": FALSIFIER_MINIMUM_SKIPS,
        "resolved_skips": len(net_r),
        "net_r": total,
        "ex_top3_net_r": ex_top,
        "status": status,
    }


def _summary(skips: Sequence[Mapping[str, object]]) -> Record:
    """Totals over independent skips; overlapping skips are only counted."""
    closed = [row for row in skips if row["status"] == "closed"]
    net_r = [_value(row, "net_r") for row in closed]
    net_bps = [_value(row, "net_bps") for row in closed]
    by_symbol: dict[str, Record] = {}
    for symbol in sorted({str(row["symbol"]) for row in skips}):
        rows = [row for row in closed if row["symbol"] == symbol]
        by_symbol[symbol] = {
            "skips": sum(row["symbol"] == symbol for row in skips),
            "overlapping": sum(
                row["symbol"] == symbol and row["status"] in OVERLAP_STATUSES
                for row in skips
            ),
            "resolved": len(rows),
            "net_r": sum(_value(row, "net_r") for row in rows),
        }
    return {
        "skips": len(skips),
        "independent": sum(row["status"] not in OVERLAP_STATUSES for row in skips),
        "overlaps_prior_skip": sum(row["status"] == PRIOR_SKIP_OPEN for row in skips),
        "live_position_open": sum(row["status"] == LIVE_POSITION_OPEN for row in skips),
        "resolved": len(closed),
        "open": sum(row["status"] == "open" for row in skips),
        "entry_unavailable": sum(row["status"] == "entry_unavailable" for row in skips),
        "wins": sum(value > 0 for value in net_r),
        "net_r": sum(net_r),
        "mean_net_r": sum(net_r) / len(net_r) if net_r else None,
        "ex_top3_net_r": _ex_top(net_r),
        "net_bps": sum(net_bps),
        "exit_reasons": dict(Counter(str(row["exit_reason"]) for row in closed)),
        "by_symbol": by_symbol,
    }


# ---------------------------------------------------------------- overlap


Hold = tuple[int, float]


def _whole(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if math.isfinite(value) else None


def load_live_holds(paths: Sequence[Path]) -> dict[str, list[Hold]]:
    """When live held each symbol, from ``cohort_ladder_evidence`` reports.

    A lifecycle holds its symbol from its entry fill to its exit; one still open,
    or whose exit is unknown, holds it to the end of the data. The same
    lifecycle in several reports counts once.
    """
    holds: dict[str, set[Hold]] = {}
    for path in paths:
        report = json.loads(path.read_text())
        rows = report.get("lifecycles") if isinstance(report, Mapping) else None
        if not isinstance(rows, list):
            raise ValueError(f"{path} is not a cohort ladder evidence report")
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            symbol, start = row.get("symbol"), _whole(row.get("entry_ms"))
            if not isinstance(symbol, str) or start is None:
                continue
            end = None if row.get("status") == "open" else _whole(row.get("exit_ms"))
            holds.setdefault(symbol, set()).add(
                (start, math.inf if end is None else float(end))
            )
    return {symbol: sorted(values) for symbol, values in holds.items()}


def _live_hold(holds: Sequence[Hold], decided: int) -> Record | None:
    for start, end in holds:
        if start <= decided <= end:
            return {
                "entry_time_utc": _utc(start),
                "exit_time_utc": _utc(int(end)) if math.isfinite(end) else None,
            }
    return None


def _held_until(decided: int, outcome: Mapping[str, object]) -> float:
    """When a scored skip frees its symbol: at its exit, never while open.

    An entry the candles cannot price is bounded by the fixed 24 h hold.
    """
    if outcome["status"] == "closed":
        return _value(outcome, "exit_time_ms")
    if outcome["status"] == "open":
        return math.inf
    return float(decided + MAXIMUM_HOLD_MS)


def symbol_skips(
    symbol: str,
    replay: Replay,
    candles: Candles,
    *,
    since_ms: int,
    until_ms: int | None,
    fees_bps: float,
    stop_slippage_bps: float,
    live_holds: Sequence[Hold] = (),
) -> list[Record]:
    """Every skip from ``since_ms`` on, scored or marked as never enterable.

    The walk starts at the first decision in the data, so a skip scored before
    ``since_ms`` still blocks the skips it overlaps after it. A skip at or before
    the exit of the last scored skip overlaps it: the router saw that position
    open. An overlapping skip is never entered, so it does not extend the block.
    """
    recipe_exits = sorted(
        decided for decided, row in replay.baseline.items() if "short" in row.exit_sides
    )
    busy_until, busy_by = -math.inf, None
    rows: list[Record] = []
    for decided, base in sorted(replay.baseline.items()):
        if until_ms is not None and decided > until_ms:
            break
        if not _enters(base, "short") or _enters(replay.filtered.get(decided), "short"):
            continue
        anchor = _metric(base, "stop_price")
        live = _live_hold(live_holds, decided)
        outcome: Record
        if busy_by is not None and decided <= busy_until:
            outcome = {"status": PRIOR_SKIP_OPEN, "overlaps_skip_at_utc": _utc(busy_by)}
        elif live is not None:
            outcome = {"status": LIVE_POSITION_OPEN, "live_position": live}
        else:
            outcome = (
                score_short(
                    decision_ms=decided,
                    anchor=anchor,
                    candles=candles,
                    recipe_exits_ms=recipe_exits,
                    fees_bps=fees_bps,
                    stop_slippage_bps=stop_slippage_bps,
                )
                if anchor is not None
                else {"status": "entry_unavailable"}
            )
            busy_by, busy_until = decided, _held_until(decided, outcome)
        if decided < since_ms:
            continue
        rows.append(
            {
                "symbol": symbol,
                "decision_time_ms": decided,
                "decision_time_utc": _utc(decided),
                "signal_close": base.reference_price,
                "prior_entry_low": _metric(base, "prior_entry_low"),
                "atr": _metric(base, "atr"),
                "extension_atr": short_extension_atr(base),
                "stop_anchor": anchor,
                **outcome,
            }
        )
    return rows


def _gaps(frame: pd.DataFrame) -> Record:
    """Missing 1m candles between the first and last one."""
    steps = frame["timestamp"].diff().dropna() / pd.Timedelta(minutes=1) - 1
    missing = steps[steps > 0]
    return {
        "gaps": len(missing),
        "missing_one_minute_bars": int(missing.sum()),
        "largest_gap_minutes": int(missing.max()) if len(missing) else 0,
    }


def build_report(
    *,
    candles_path: Path,
    since: str,
    until: str | None = None,
    symbols: Sequence[str] = DEFAULT_SYMBOLS,
    costs: CostModel | None = None,
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    ladder_reports: Sequence[Path] = (),
) -> Record:
    """Replay both identities, list every skipped short and score each one."""
    if not math.isfinite(lookback_hours) or lookback_hours < 0:
        raise ValueError("lookback_hours must be finite and non-negative")
    cost_model = costs or CostModel()
    since_ms = _iso_ms(since)
    until_ms = _iso_ms(until) if until else None
    # Hour-aligned, so the first 15m source bar is never a partial one.
    start_ms = (since_ms - int(lookback_hours * HOUR_MS)) // HOUR_MS * HOUR_MS
    candles = load_candles(candles_path, start_ms=start_ms, symbols=symbols)
    live_holds = load_live_holds(ladder_reports)
    skips: list[Record] = []
    coverage: dict[str, Record] = {}
    checks: Counter[str] = Counter()
    for symbol in symbols:
        frame = candles.get(symbol)
        if frame is None or frame.empty:
            coverage[symbol] = {"one_minute_bars": 0}
            continue
        last_ms = int(pd.Timestamp(frame["timestamp"].iloc[-1]).timestamp() * 1000)
        # The replay is causal, so it runs to the data end: a skip before
        # ``until`` still sees the recipe exits that follow it.
        observed = pd.Timestamp(last_ms + MINUTE_MS, unit="ms", tz="UTC")
        replay = replay_symbol(symbol, frame, observed)
        checks.update(identity_check(replay))
        ready = [
            decided
            for decided, row in sorted(replay.baseline.items())
            if _metric(row, "atr") is not None
            and _metric(row, "prior_entry_low") is not None
        ]
        hourly = [
            decided
            for decided in ready
            if decided >= since_ms and decided % HOUR_MS == 0
        ]
        coverage[symbol] = {
            "first_one_minute_utc": _utc(
                int(pd.Timestamp(frame["timestamp"].iloc[0]).timestamp() * 1000)
            ),
            "last_one_minute_utc": _utc(last_ms),
            "one_minute_bars": len(frame),
            **_gaps(frame),
            "fifteen_minute_bars": replay.fifteen_minute_bars,
            "first_ready_decision_utc": _utc(ready[0]) if ready else None,
            "ready_hourly_decisions_since": len(hourly),
        }
        skips.extend(
            symbol_skips(
                symbol,
                replay,
                Candles.from_frame(frame),
                since_ms=since_ms,
                until_ms=until_ms,
                fees_bps=cost_model.fees_bps(symbol),
                stop_slippage_bps=cost_model.stop_slippage_bps,
                live_holds=live_holds.get(symbol, ()),
            )
        )
    at_or_above = sum(
        isinstance(row["extension_atr"], float)
        and row["extension_atr"] >= STRONG_SHORT_MINIMUM_EXTENSION_ATR
        for row in skips
    )
    summary = _summary(skips)
    resolved = [_value(row, "net_r") for row in skips if row["status"] == "closed"]
    return {
        "execution_authority": "none",
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "selection": {
            "candles": str(candles_path),
            "since_utc": _utc(since_ms),
            "until_utc": _utc(until_ms),
            "symbols": list(symbols),
            "lookback_hours": lookback_hours,
            "candles_from_utc": _utc(start_ms),
        },
        "identities": {
            "baseline": DONCHIAN20_STRATEGY,
            "filtered": STRONG_SHORT_DONCHIAN20_STRATEGY,
            "minimum_short_extension_atr": STRONG_SHORT_MINIMUM_EXTENSION_ATR,
        },
        "geometry": {
            "stop": f"2 x ATR anchor clamped to {MINIMUM_STOP_BPS:g}-"
            f"{MAXIMUM_STOP_BPS:g} bps from the entry",
            "exits": "channel recipe exit at the next completed hour, fixed 24 h "
            "maximum hold, v2 profit floor (2R arm, 0.5R floor)",
            "entry": "open of the 1m candle at the decision time",
            "omitted": "regime-flip giveback (needs live regime alignment); the "
            "kept longs and strong shorts the book would hold on the symbol, unless "
            "a ladder evidence report supplies the live book",
        },
        "overlap": {
            "rule": "one position per symbol (enter_and_close routing): a skip at "
            "or before the exit of an earlier scored skip, or while a live "
            "lifecycle holds the symbol, is never an independent trade; it is "
            "listed, not scored, and excluded from the summary totals and the "
            "falsifier",
            "ladder_reports": [str(path) for path in ladder_reports],
            "live_lifecycles": sum(len(values) for values in live_holds.values()),
        },
        "costs": {
            "hip3_round_trip_bps": cost_model.hip3_round_trip_bps,
            "crypto_round_trip_bps": cost_model.crypto_round_trip_bps,
            "stop_slippage_bps": cost_model.stop_slippage_bps,
        },
        "coverage": coverage,
        "identity_check": {
            "long_mismatches": checks["long_mismatches"],
            "exit_mismatches": checks["exit_mismatches"],
            "stop_mismatches": checks["stop_mismatches"],
            "filtered_only_shorts": checks["filtered_only_shorts"],
            "kept_shorts_below_threshold": checks["kept_shorts_below_threshold"],
            "skips_at_or_above_threshold": at_or_above,
        },
        "summary": summary,
        "falsifier": falsifier(resolved),
        "skips": skips,
    }


R_FORMAT = "{:+.2f}R"


def _fmt(value: object, pattern: str = "{:+.2f}") -> str:
    return "n/a" if not isinstance(value, (int, float)) else pattern.format(value)


def summary_text(report: Mapping[str, object]) -> str:
    """Return the short operator summary printed to stdout."""
    selection, summary = report["selection"], report["summary"]
    check, rule = report["identity_check"], report["falsifier"]
    skips, overlap = report["skips"], report["overlap"]
    assert isinstance(selection, Mapping) and isinstance(summary, Mapping)
    assert isinstance(check, Mapping) and isinstance(rule, Mapping)
    assert isinstance(skips, list) and isinstance(overlap, Mapping)
    symbols, reports = selection["symbols"], overlap["ladder_reports"]
    assert isinstance(symbols, list) and isinstance(reports, list)
    live_book = (
        f"{overlap['live_lifecycles']} live lifecycle(s) from {len(reports)} "
        "ladder report(s)"
        if reports
        else "not checked (pass --ladder-report)"
    )
    lines = [
        "strong-short skip audit (execution_authority: none)",
        f"since {selection['since_utc']}; symbols {','.join(map(str, symbols))}",
        f"identity check: {check['long_mismatches']} long, {check['exit_mismatches']} "
        f"exit, {check['stop_mismatches']} stop and {check['filtered_only_shorts']} "
        "filtered-only short mismatch(es); "
        f"{check['skips_at_or_above_threshold']} skip(s) at or above "
        f"{STRONG_SHORT_MINIMUM_EXTENSION_ATR:g} ATR",
        f"live book: {live_book}",
        f"skipped shorts: {summary['skips']} ({summary['independent']} independent: "
        f"{summary['resolved']} resolved, {summary['open']} open; "
        f"{summary['overlaps_prior_skip']} overlap a prior skip, "
        f"{summary['live_position_open']} a live position); independent net "
        f"{_fmt(summary['net_r'])}R, ex-top-3 {_fmt(summary['ex_top3_net_r'], R_FORMAT)}, "
        f"{_fmt(summary['net_bps'], '{:+.0f}')} bps",
    ]
    for row in skips:
        assert isinstance(row, Mapping)
        head = (
            f"  {row['decision_time_utc']} {row['symbol']} ext "
            f"{_fmt(row['extension_atr'], '{:.3f}')} ATR -> {row['status']}"
        )
        if row["status"] == PRIOR_SKIP_OPEN:
            lines.append(f"{head} (skip at {row['overlaps_skip_at_utc']} still open)")
        elif row["status"] == LIVE_POSITION_OPEN:
            held = row["live_position"]
            assert isinstance(held, Mapping)
            lines.append(f"{head} (live entry {held['entry_time_utc']})")
        else:
            lines.append(
                f"{head} {row.get('exit_reason') or ''} net "
                f"{_fmt(row.get('net_bps'), '{:+.0f}')} bps "
                f"({_fmt(row.get('net_r'), '{:+.2f}')}R)"
            )
    lines.append(
        f"falsifier (pre-registered): after >= {rule['minimum_skips']} independent "
        "skips, re-open the weak-short rule only if skipped-short net > 0 and "
        "ex-top-3 >= 0; now "
        f"{rule['resolved_skips']}/{rule['minimum_skips']}, net "
        f"{_fmt(rule['net_r'])}R, ex-top-3 {_fmt(rule['ex_top3_net_r'], R_FORMAT)}: "
        f"{rule['status']}"
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--candles",
        type=Path,
        required=True,
        help="1m candles: market_candles events (jsonl/parquet/csv) or a flat "
        "table; a JSONL ledger is bisected to --since minus the lookback, but "
        "prefer a parquet extract on the live host",
    )
    parser.add_argument("--since", required=True, help="ISO-8601 UTC audit start")
    parser.add_argument(
        "--until", help="ISO-8601 UTC last decision (default: data end)"
    )
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--lookback-hours",
        type=float,
        default=DEFAULT_LOOKBACK_HOURS,
        help="candle history read before --since (warm-up and prior skips)",
    )
    parser.add_argument(
        "--ladder-report",
        type=Path,
        action="append",
        default=[],
        help="cohort_ladder_evidence JSON; its lifecycles mark when live held "
        "each symbol, and a skip then is excluded (repeatable)",
    )
    parser.add_argument(
        "--hip3-round-trip-bps", type=float, default=DEFAULT_HIP3_ROUND_TRIP_BPS
    )
    parser.add_argument(
        "--crypto-round-trip-bps", type=float, default=DEFAULT_CRYPTO_ROUND_TRIP_BPS
    )
    parser.add_argument(
        "--stop-slippage-bps", type=float, default=DEFAULT_STOP_SLIPPAGE_BPS
    )
    parser.add_argument("--out", type=Path, help="write the JSON report here")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Write the JSON report (when --out is given) and print the summary."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not math.isfinite(args.lookback_hours) or args.lookback_hours < 0:
        parser.error("--lookback-hours must be finite and non-negative")
    report = build_report(
        candles_path=args.candles,
        since=args.since,
        until=args.until,
        symbols=tuple(part.strip() for part in args.symbols.split(",") if part.strip()),
        costs=CostModel(
            args.hip3_round_trip_bps, args.crypto_round_trip_bps, args.stop_slippage_bps
        ),
        lookback_hours=args.lookback_hours,
        ladder_reports=args.ladder_report,
    )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(summary_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
