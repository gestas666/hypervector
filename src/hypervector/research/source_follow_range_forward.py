"""Forward path diagnostics for live source-follow RANGE decisions."""

from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path
from statistics import median

import duckdb


@dataclass(frozen=True)
class RangeDecision:
    """One completed live RANGE decision with no hypothetical trade side."""

    sequence: int
    feed_at_utc: datetime
    available_at_utc: datetime
    reference_price: float

    def __post_init__(self) -> None:
        _require_utc(self.feed_at_utc, "RANGE feed time")
        _require_utc(self.available_at_utc, "RANGE availability time")
        if self.available_at_utc <= self.feed_at_utc:
            raise ValueError("RANGE availability must follow its feed time")
        if not math.isfinite(self.reference_price) or self.reference_price <= 0.0:
            raise ValueError("RANGE reference price must be positive and finite")


@dataclass(frozen=True)
class _Trade:
    exchange_ts_ms: int
    trade_id: int
    price: float


@dataclass(frozen=True)
class _MarketEvidence:
    trades: tuple[_Trade, ...]
    timestamps_ms: tuple[int, ...]
    gaps: tuple[tuple[int | None, int | None], ...]
    latest_trade_ms: int


def extract_range_decisions(
    rows: Sequence[Mapping[str, object]],
    *,
    run_id: str,
) -> tuple[RangeDecision, ...]:
    """Extract ordered RANGE decisions from exactly one live run."""
    if not run_id.strip():
        raise ValueError("RANGE forward audit run_id must be non-empty")
    selected: list[RangeDecision] = []
    for row in rows:
        if row.get("run_id") != run_id or row.get("event_type") != "regime_decision":
            continue
        payload = _mapping(row.get("payload"), "regime decision payload")
        if payload.get("primary_regime") != "RANGE":
            continue
        selected.append(_range_decision(row, payload))
    if not selected:
        raise ValueError(f"live run has no RANGE decisions: {run_id}")
    ordered = tuple(sorted(selected, key=lambda item: item.available_at_utc))
    times = [item.available_at_utc for item in ordered]
    if len(times) != len(set(times)):
        raise ValueError("live run contains duplicate RANGE decision timestamps")
    return ordered


def audit_range_forward_paths(
    database_path: Path,
    decisions: Sequence[RangeDecision],
    *,
    symbol: str,
    target_price_fraction: float,
    horizons_minutes: Sequence[int] = (5, 15, 30, 60),
) -> dict[str, object]:
    """Measure future RANGE paths without constructing hypothetical entries."""
    horizons = _validated_horizons(horizons_minutes)
    if not decisions:
        raise ValueError("RANGE forward audit requires at least one decision")
    if not symbol.strip():
        raise ValueError("RANGE forward audit symbol must be non-empty")
    if not math.isfinite(target_price_fraction) or target_price_fraction <= 0.0:
        raise ValueError("target price fraction must be positive and finite")
    market = _load_market_evidence(database_path, decisions, symbol, horizons)
    paths = tuple(
        _decision_path(item, market, horizons, target_price_fraction)
        for item in decisions
    )
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "symbol": symbol,
        "decision_rows": len(decisions),
        "target_price_fraction": target_price_fraction,
        "target_bps": target_price_fraction * 10_000.0,
        "latest_trade_at_utc": _iso_from_ms(market.latest_trade_ms),
        "range_episodes": _range_episode_summary(decisions),
        "horizons": {str(value): _horizon_summary(paths, value) for value in horizons},
        "paths": list(paths),
        "limitations": _limitations(),
    }


def _range_decision(
    row: Mapping[str, object],
    payload: Mapping[str, object],
) -> RangeDecision:
    sequence = row.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise ValueError("RANGE decision sequence must be an integer")
    return RangeDecision(
        sequence=sequence,
        feed_at_utc=_utc(payload.get("feed_ts"), "RANGE feed timestamp"),
        available_at_utc=_utc(
            payload.get("available_at_utc"), "RANGE availability timestamp"
        ),
        reference_price=_finite(payload.get("reference_price"), "reference price"),
    )


def _validated_horizons(values: Sequence[int]) -> tuple[int, ...]:
    if not values:
        raise ValueError("RANGE forward horizons must be non-empty")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("RANGE forward horizons must be integer minutes")
    if any(value <= 0 for value in values):
        raise ValueError("RANGE forward horizons must be positive")
    if len(values) != len(set(values)):
        raise ValueError("RANGE forward horizons must be unique")
    return tuple(sorted(values))


def _load_market_evidence(
    database_path: Path,
    decisions: Sequence[RangeDecision],
    symbol: str,
    horizons: Sequence[int],
) -> _MarketEvidence:
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    start_ms = _milliseconds(min(item.available_at_utc for item in decisions))
    end_at = max(item.available_at_utc for item in decisions) + timedelta(
        minutes=max(horizons)
    )
    end_ms = _milliseconds(end_at)
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(_TRADE_SQL, [symbol, start_ms, end_ms]).fetchall()
        latest = connection.execute(_LATEST_TRADE_SQL, [symbol]).fetchone()
        gaps = connection.execute(_GAP_SQL, [symbol, start_ms, end_ms]).fetchall()
    if latest is None or latest[0] is None:
        raise ValueError(f"research database has no live trades for {symbol}")
    trades = tuple(_trade(row) for row in rows)
    return _MarketEvidence(
        trades=trades,
        timestamps_ms=tuple(item.exchange_ts_ms for item in trades),
        gaps=tuple((_optional_int(row[0]), _optional_int(row[1])) for row in gaps),
        latest_trade_ms=int(latest[0]),
    )


def _decision_path(
    decision: RangeDecision,
    market: _MarketEvidence,
    horizons: Sequence[int],
    target_fraction: float,
) -> dict[str, object]:
    return {
        "sequence": decision.sequence,
        "feed_at_utc": decision.feed_at_utc.isoformat(),
        "available_at_utc": decision.available_at_utc.isoformat(),
        "reference_price": decision.reference_price,
        "horizons": {
            str(value): _horizon_path(
                decision,
                market,
                minutes=value,
                target_fraction=target_fraction,
            )
            for value in horizons
        },
    }


def _horizon_path(
    decision: RangeDecision,
    market: _MarketEvidence,
    *,
    minutes: int,
    target_fraction: float,
) -> dict[str, object]:
    start_ms = _milliseconds(decision.available_at_utc)
    end_ms = start_ms + minutes * 60_000
    start_index = bisect_left(market.timestamps_ms, start_ms)
    end_index = bisect_left(market.timestamps_ms, end_ms)
    trades = market.trades[start_index:end_index]
    gaps = sum(_gap_overlaps(item, start_ms, end_ms) for item in market.gaps)
    complete = market.latest_trade_ms >= end_ms
    usable = complete and bool(trades) and gaps == 0
    metrics = _path_metrics(trades, decision.reference_price, target_fraction)
    if not complete:
        metrics = _empty_metrics()
    return {
        "minutes": minutes,
        "complete": complete,
        "quality_usable": usable,
        "explicit_stream_gaps": gaps,
        "trade_count": len(trades),
        **metrics,
    }


def _path_metrics(
    trades: Sequence[_Trade],
    reference_price: float,
    target_fraction: float,
) -> dict[str, object]:
    if not trades:
        return _empty_metrics()
    prices = [item.price for item in trades]
    maximum_up = max(0.0, (max(prices) / reference_price - 1.0) * 10_000.0)
    maximum_down = max(0.0, (1.0 - min(prices) / reference_price) * 10_000.0)
    target = target_fraction * 10_000.0
    direction, timestamp = _first_target(trades, reference_price, target_fraction)
    return {
        "maximum_up_bps": maximum_up,
        "maximum_down_bps": maximum_down,
        "path_span_bps": (max(prices) - min(prices)) / reference_price * 10_000.0,
        "ending_displacement_bps": (prices[-1] / reference_price - 1.0) * 10_000.0,
        "long_target_hit": maximum_up >= target,
        "short_target_hit": maximum_down >= target,
        "first_target_direction": direction,
        "first_target_at_utc": None if timestamp is None else _iso_from_ms(timestamp),
    }


def _first_target(
    trades: Sequence[_Trade],
    reference_price: float,
    target_fraction: float,
) -> tuple[str | None, int | None]:
    upper = reference_price * (1.0 + target_fraction)
    lower = reference_price * (1.0 - target_fraction)
    for item in trades:
        if item.price >= upper:
            return "long", item.exchange_ts_ms
        if item.price <= lower:
            return "short", item.exchange_ts_ms
    return None, None


def _empty_metrics() -> dict[str, object]:
    return {
        "maximum_up_bps": None,
        "maximum_down_bps": None,
        "path_span_bps": None,
        "ending_displacement_bps": None,
        "long_target_hit": None,
        "short_target_hit": None,
        "first_target_direction": None,
        "first_target_at_utc": None,
    }


def _range_episode_summary(
    decisions: Sequence[RangeDecision],
) -> dict[str, object]:
    ordered = sorted(decisions, key=lambda item: item.available_at_utc)
    rows: list[dict[str, object]] = []
    start = ordered[0].available_at_utc
    end = start
    count = 1
    for item in ordered[1:]:
        if item.available_at_utc == end + timedelta(minutes=5):
            end = item.available_at_utc
            count += 1
            continue
        rows.append(_episode_row(len(rows) + 1, start, end, count))
        start = item.available_at_utc
        end = start
        count = 1
    rows.append(_episode_row(len(rows) + 1, start, end, count))
    return {"count": len(rows), "rows": rows}


def _episode_row(
    episode: int,
    start: datetime,
    end: datetime,
    decision_rows: int,
) -> dict[str, object]:
    return {
        "episode": episode,
        "start_at_utc": start.isoformat(),
        "end_at_utc": end.isoformat(),
        "decision_rows": decision_rows,
    }


def _horizon_summary(
    paths: Sequence[Mapping[str, object]],
    minutes: int,
) -> dict[str, object]:
    rows = [_horizon_row(item, minutes) for item in paths]
    usable = [item for item in rows if item.get("quality_usable") is True]
    first = Counter(
        str(item.get("first_target_direction") or "none") for item in usable
    )
    return {
        "decision_rows": len(rows),
        "complete_rows": sum(item.get("complete") is True for item in rows),
        "censored_rows": sum(item.get("complete") is False for item in rows),
        "usable_rows": len(usable),
        "gap_rows": sum(
            int(item.get("explicit_stream_gaps") or 0) > 0 for item in rows
        ),
        "long_target_rows": sum(item.get("long_target_hit") is True for item in usable),
        "short_target_rows": sum(
            item.get("short_target_hit") is True for item in usable
        ),
        "first_target_distribution": dict(sorted(first.items())),
        "median_absolute_ending_displacement_bps": _median_absolute(usable),
        "median_path_span_bps": _median_numeric(usable, "path_span_bps"),
    }


def _horizon_row(path: Mapping[str, object], minutes: int) -> Mapping[str, object]:
    horizons = _mapping(path.get("horizons"), "path horizons")
    return _mapping(horizons.get(str(minutes)), "path horizon")


def _median_absolute(rows: Sequence[Mapping[str, object]]) -> float | None:
    values = [
        abs(value)
        for row in rows
        if (value := _number(row, "ending_displacement_bps")) is not None
    ]
    return None if not values else float(median(values))


def _median_numeric(
    rows: Sequence[Mapping[str, object]],
    name: str,
) -> float | None:
    values = [value for row in rows if (value := _number(row, name)) is not None]
    return None if not values else float(median(values))


def _number(row: Mapping[str, object], name: str) -> float | None:
    value = row.get(name)
    return None if value is None else _finite(value, name)


def _trade(row: Sequence[object]) -> _Trade:
    if len(row) != 3:
        raise RuntimeError("live trade query returned an invalid row")
    timestamp, trade_id, price = row
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        raise RuntimeError("live trade timestamp must be an integer")
    if isinstance(trade_id, bool) or not isinstance(trade_id, int):
        raise RuntimeError("live trade id must be an integer")
    return _Trade(timestamp, trade_id, _finite(price, "live trade price"))


def _gap_overlaps(
    gap: tuple[int | None, int | None],
    start_ms: int,
    end_ms: int,
) -> bool:
    previous, following = gap
    gap_start = previous if previous is not None else following
    gap_end = following if following is not None else previous
    return bool(
        gap_start is not None
        and gap_end is not None
        and gap_end >= start_ms
        and gap_start < end_ms
    )


def _limitations() -> list[str]:
    return [
        "RANGE paths are diagnostics, not hypothetical strategy entries.",
        "Contiguous RANGE decisions have overlapping, non-independent horizons.",
        "A target touch in either direction does not establish a causal side signal.",
        "Incomplete future horizons are censored and excluded from summaries.",
        "Any explicit recorder gap makes that decision horizon unusable.",
    ]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty ISO-8601 text")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    _require_utc(result, label)
    return result.astimezone(UTC)


def _require_utc(value: datetime, label: str) -> None:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC")


def _milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


def _iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000.0, tz=UTC).isoformat()


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError("stream-gap timestamp must be an integer")
    return value


_TRADE_SQL = """
SELECT exchange_ts_ms, trade_id, price
FROM replay_live_public_trades
WHERE symbol = ? AND exchange_ts_ms >= ? AND exchange_ts_ms < ?
ORDER BY exchange_ts_ms, trade_id
"""


_LATEST_TRADE_SQL = """
SELECT max(exchange_ts_ms) FROM replay_live_public_trades WHERE symbol = ?
"""


_GAP_SQL = """
SELECT previous_exchange_ts_ms, next_exchange_ts_ms
FROM live_stream_gaps
WHERE symbol = ?
  AND coalesce(next_exchange_ts_ms, previous_exchange_ts_ms) >= ?
  AND coalesce(previous_exchange_ts_ms, next_exchange_ts_ms) < ?
ORDER BY coalesce(previous_exchange_ts_ms, next_exchange_ts_ms)
"""
