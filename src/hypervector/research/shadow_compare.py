"""Report-only reconciliation between backend shadow and real strategy logs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd


@dataclass(frozen=True)
class _Observation:
    timestamp: pd.Timestamp
    direction: str
    primary_regime: str
    entry_allowed: bool


@dataclass
class _Trade:
    timestamp: pd.Timestamp
    direction: str
    entry_price: float | None
    submit_timestamp: pd.Timestamp | None = None
    close_timestamp: pd.Timestamp | None = None
    exit_price: float | None = None
    fill_type: str = ""


def load_shadow_ledger(path: Path | str) -> list[dict[str, object]]:
    """Load a JSONL backend ledger and reject malformed rows explicitly."""
    ledger_path = Path(path)
    if not ledger_path.is_file():
        raise FileNotFoundError(f"shadow ledger not found: {ledger_path}")
    rows: list[dict[str, object]] = []
    for line_number, raw in enumerate(ledger_path.read_text().splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"shadow ledger line {line_number} is not an object")
        rows.append(value)
    return rows


def load_real_positions(path: Path | str) -> pd.DataFrame:
    """Load the real-strategy position CSV used for reconciliation."""
    positions_path = Path(path)
    if not positions_path.is_file():
        raise FileNotFoundError(f"real positions file not found: {positions_path}")
    return pd.read_csv(positions_path)


def compare_shadow_to_positions(
    shadow_rows: Sequence[Mapping[str, object]],
    positions: pd.DataFrame,
    *,
    run_ids: Sequence[str],
    entry_tolerance_seconds: float = 120.0,
) -> dict[str, object]:
    """Compare same-window entries and exits without creating an execution gate."""
    selected_ids = tuple(dict.fromkeys(str(run_id) for run_id in run_ids))
    if not selected_ids:
        raise ValueError("at least one explicit shadow run_id is required")
    tolerance = float(entry_tolerance_seconds)
    if tolerance < 0.0:
        raise ValueError("entry_tolerance_seconds must be non-negative")
    selected = [row for row in shadow_rows if str(row.get("run_id")) in selected_ids]
    observations = _parse_observations(selected)
    window_start = min(item.timestamp for item in observations)
    window_end = max(item.timestamp for item in observations)
    real_trades = _parse_real_trades(positions)
    _validate_overlap(real_trades, window_start, window_end)
    covered = {item.direction for item in observations}
    real_window = [
        trade
        for trade in real_trades
        if window_start <= trade.timestamp <= window_end and trade.direction in covered
    ]
    shadow_trades = _parse_shadow_trades(selected)
    matches, shadow_left, real_left = _match_entries(
        shadow_trades,
        real_window,
        tolerance_seconds=tolerance,
    )
    direction_mismatches, _, _ = _match_by_direction(
        shadow_left,
        real_left,
        tolerance_seconds=tolerance,
        same_direction=False,
    )
    match_rows = [_match_row(shadow, real) for shadow, real in matches]
    real_unmatched = [_real_unmatched_row(trade, observations) for trade in real_left]
    real_context = [_real_unmatched_row(trade, observations) for trade in real_window]
    summary = _summary(
        shadow_trades,
        real_window,
        matches,
        direction_mismatches,
        real_context,
    )
    return {
        "ok": True,
        "report_only": True,
        "run_ids": list(selected_ids),
        "entry_tolerance_seconds": tolerance,
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
        "summary": summary,
        "matches": match_rows,
        "direction_mismatches": [
            _direction_mismatch_row(shadow, real)
            for shadow, real in direction_mismatches
        ],
        "shadow_unmatched": [_trade_row(trade) for trade in shadow_left],
        "real_unmatched": real_unmatched,
    }


def _parse_observations(rows: Sequence[Mapping[str, object]]) -> list[_Observation]:
    observations = [
        _Observation(
            timestamp=_timestamp(row.get("feed_ts"), field="feed_ts"),
            direction=_direction(row.get("entry_direction")),
            primary_regime=str(row.get("primary_regime")),
            entry_allowed=bool(row.get("entry_allowed")),
        )
        for row in rows
        if row.get("action") == "regime_observation"
    ]
    if not observations:
        raise ValueError("selected shadow run has no live regime_observation rows")
    return observations


def _parse_real_trades(positions: pd.DataFrame) -> list[_Trade]:
    required = {"symbol", "side", "open_time_utc", "entry_price", "fill_type"}
    missing = required.difference(positions.columns)
    if missing:
        raise ValueError(f"real positions missing columns: {sorted(missing)}")
    trades: list[_Trade] = []
    for record in positions.to_dict(orient="records"):
        if str(record.get("symbol", "")).upper() != "BTC":
            continue
        trades.append(
            _Trade(
                timestamp=_timestamp(
                    record.get("open_time_utc"), field="open_time_utc"
                ),
                direction=_direction(record.get("side")),
                entry_price=_optional_float(record.get("entry_price")),
                close_timestamp=_optional_timestamp(record.get("close_time_utc")),
                exit_price=_optional_float(record.get("exit_price")),
                fill_type=str(record.get("fill_type", "")),
            )
        )
    if not trades:
        raise ValueError("real positions contain no BTC trades")
    return trades


def _parse_shadow_trades(rows: Sequence[Mapping[str, object]]) -> list[_Trade]:
    sorted_rows = sorted(
        (row for row in rows if row.get("feed_ts") != "session_start"),
        key=lambda row: _timestamp(row.get("feed_ts"), field="feed_ts"),
    )
    pending: dict[tuple[str, str], pd.Timestamp] = {}
    open_by_run: dict[str, _Trade] = {}
    trades: list[_Trade] = []
    for row in sorted_rows:
        action = str(row.get("action", ""))
        run_id = str(row.get("run_id", ""))
        timestamp = _timestamp(row.get("feed_ts"), field="feed_ts")
        side = _side_direction(row.get("side"))
        if action == "submit_entry" and side is not None:
            pending[(run_id, side)] = timestamp
        elif action in {"enter_long", "enter_short"} and not bool(row.get("skipped")):
            direction = "long" if action == "enter_long" else "short"
            trade = _Trade(
                timestamp=timestamp,
                direction=direction,
                entry_price=_optional_float(row.get("fill_px")),
                submit_timestamp=pending.pop((run_id, direction), None),
            )
            trades.append(trade)
            open_by_run[run_id] = trade
        elif action == "close" and run_id in open_by_run:
            trade = open_by_run.pop(run_id)
            trade.close_timestamp = timestamp
            trade.exit_price = _optional_float(row.get("fill_px"))
    return trades


def _match_entries(
    shadow: Sequence[_Trade],
    real: Sequence[_Trade],
    *,
    tolerance_seconds: float,
) -> tuple[list[tuple[_Trade, _Trade]], list[_Trade], list[_Trade]]:
    return _match_by_direction(
        shadow,
        real,
        tolerance_seconds=tolerance_seconds,
        same_direction=True,
    )


def _match_by_direction(
    shadow: Sequence[_Trade],
    real: Sequence[_Trade],
    *,
    tolerance_seconds: float,
    same_direction: bool,
) -> tuple[list[tuple[_Trade, _Trade]], list[_Trade], list[_Trade]]:
    candidates = sorted(
        (
            (abs((left.timestamp - right.timestamp).total_seconds()), left_i, right_i)
            for left_i, left in enumerate(shadow)
            for right_i, right in enumerate(real)
            if (left.direction == right.direction) is same_direction
        ),
        key=lambda item: item[0],
    )
    used_shadow: set[int] = set()
    used_real: set[int] = set()
    matches: list[tuple[_Trade, _Trade]] = []
    for distance, left_i, right_i in candidates:
        if distance > tolerance_seconds:
            break
        if left_i in used_shadow or right_i in used_real:
            continue
        used_shadow.add(left_i)
        used_real.add(right_i)
        matches.append((shadow[left_i], real[right_i]))
    shadow_left = [
        item for index, item in enumerate(shadow) if index not in used_shadow
    ]
    real_left = [item for index, item in enumerate(real) if index not in used_real]
    return matches, shadow_left, real_left


def _match_row(shadow: _Trade, real: _Trade) -> dict[str, object]:
    entry_delta = (shadow.timestamp - real.timestamp).total_seconds()
    row: dict[str, object] = {
        "direction": shadow.direction,
        "shadow_entry_time": shadow.timestamp.isoformat(),
        "real_entry_time": real.timestamp.isoformat(),
        "entry_timing_seconds": entry_delta,
        "entry_abs_timing_seconds": abs(entry_delta),
        "entry_price_diff_bps": _price_diff_bps(shadow.entry_price, real.entry_price),
        "shadow_submit_to_fill_seconds": _time_delta(
            shadow.timestamp,
            shadow.submit_timestamp,
        ),
        "exit_timing_seconds": _time_delta(
            shadow.close_timestamp,
            real.close_timestamp,
        ),
        "exit_price_diff_bps": _price_diff_bps(shadow.exit_price, real.exit_price),
    }
    return row


def _real_unmatched_row(
    trade: _Trade,
    observations: Sequence[_Observation],
) -> dict[str, object]:
    eligible = [item for item in observations if item.direction == trade.direction]
    nearest = min(
        eligible,
        key=lambda item: abs((item.timestamp - trade.timestamp).total_seconds()),
    )
    return {
        **_trade_row(trade),
        "nearest_regime_time": nearest.timestamp.isoformat(),
        "nearest_primary_regime": nearest.primary_regime,
        "nearest_entry_allowed": nearest.entry_allowed,
    }


def _direction_mismatch_row(shadow: _Trade, real: _Trade) -> dict[str, object]:
    return {
        "shadow_direction": shadow.direction,
        "real_direction": real.direction,
        "shadow_entry_time": shadow.timestamp.isoformat(),
        "real_entry_time": real.timestamp.isoformat(),
        "abs_timing_seconds": abs((shadow.timestamp - real.timestamp).total_seconds()),
    }


def _summary(
    shadow: Sequence[_Trade],
    real: Sequence[_Trade],
    matches: Sequence[tuple[_Trade, _Trade]],
    direction_mismatches: Sequence[tuple[_Trade, _Trade]],
    real_context: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    matched = len(matches)
    return {
        "shadow_entries": len(shadow),
        "real_entries": len(real),
        "matched_entries": matched,
        "direction_matches": matched,
        "direction_mismatches": len(direction_mismatches),
        "shadow_unmatched": len(shadow) - matched,
        "real_unmatched": len(real) - matched,
        "false_range_at_real_entries": sum(
            row.get("nearest_primary_regime") == "RANGE" for row in real_context
        ),
        "real_maker_entries": sum(trade.fill_type.lower() == "maker" for trade in real),
        "entry_precision_pct": _percentage(matched, len(shadow)),
        "entry_recall_pct": _percentage(matched, len(real)),
    }


def _validate_overlap(
    real: Sequence[_Trade],
    shadow_start: pd.Timestamp,
    shadow_end: pd.Timestamp,
) -> None:
    real_start = min(item.timestamp for item in real)
    real_end = max(item.close_timestamp or item.timestamp for item in real)
    if real_end < shadow_start or real_start > shadow_end:
        raise ValueError(
            "real-strategy log does not overlap the selected shadow observation window"
        )


def _trade_row(trade: _Trade) -> dict[str, object]:
    return {
        "direction": trade.direction,
        "entry_time": trade.timestamp.isoformat(),
        "entry_price": trade.entry_price,
        "close_time": (
            trade.close_timestamp.isoformat()
            if trade.close_timestamp is not None
            else None
        ),
        "exit_price": trade.exit_price,
    }


def _timestamp(value: object, *, field: str) -> pd.Timestamp:
    if value is None or str(value).strip() in {"", "nan", "NaT"}:
        raise ValueError(f"{field} must contain a UTC timestamp")
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _optional_timestamp(value: object) -> pd.Timestamp | None:
    if value is None or pd.isna(value) or str(value).strip() in {"", "nan", "NaT"}:
        return None
    return _timestamp(value, field="close_time_utc")


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value) or str(value).strip() in {"", "nan"}:
        return None
    return float(value)


def _direction(value: object) -> str:
    direction = str(value).strip().lower()
    if direction not in {"long", "short"}:
        raise ValueError(f"direction must be long|short, got {value!r}")
    return direction


def _side_direction(value: object) -> str | None:
    side = str(value).strip().lower()
    if side == "buy":
        return "long"
    if side == "sell":
        return "short"
    return None


def _time_delta(
    later: pd.Timestamp | None, earlier: pd.Timestamp | None
) -> float | None:
    if later is None or earlier is None:
        return None
    return (later - earlier).total_seconds()


def _price_diff_bps(left: float | None, right: float | None) -> float | None:
    if left is None or right is None or right == 0.0:
        return None
    return (left - right) / right * 10_000.0


def _percentage(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator * 100.0
