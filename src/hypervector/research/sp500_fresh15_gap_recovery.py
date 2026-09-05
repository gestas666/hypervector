"""Audit exact SP500 outage marks without retroactive execution claims."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import math

import pandas as pd

from hypervector.cohort_profit_lock_policy import (
    ProfitLockPolicy,
    evaluate_profit_lock_path,
)
from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.research.hip3_prospective_path_audit import hip3_bar_path_quality

Record = dict[str, object]

_SYMBOL = "xyz:SP500"
_PRICE_SOURCE = "0xarchive_hyperliquid_prices"
_CANDLE_SOURCE = "hyperliquid_public_candleSnapshot_1m"
_CANDLE_EVENT = "sp500_hip3_breakout_shadow_profit_lock_candle_observation"
_DECISION_INTERVAL_MS = 15 * 60_000


@dataclass(frozen=True)
class Sp500Fresh15GapRecoveryConfig:
    """Frozen technical thresholds for one SP500 outage recovery audit."""

    maximum_mark_gap_ms: int = 5_000

    def __post_init__(self) -> None:
        if (
            isinstance(self.maximum_mark_gap_ms, bool)
            or not isinstance(self.maximum_mark_gap_ms, int)
            or self.maximum_mark_gap_ms <= 0
        ):
            raise ValueError("SP500 recovery maximum mark gap must be positive")


def build_sp500_fresh15_gap_recovery(
    *,
    preregistration: Mapping[str, object],
    watcher_status: Mapping[str, object],
    decisions: Sequence[Mapping[str, object]],
    candles: Sequence[Mapping[str, object]],
    price_manifest: Mapping[str, object],
    prices: pd.DataFrame,
    config: Sp500Fresh15GapRecoveryConfig,
) -> Record:
    """Return a no-authority mark repair while preserving decision censoring."""
    event = _validated_contract(preregistration, watcher_status)
    gap_start = _gap_start(watcher_status)
    recovered = _recovered_candles(candles, gap_start)
    gap_end = int(recovered[-1]["bar_close_ms"])
    marks = _verified_marks(price_manifest, prices, gap_start, gap_end)
    mark = _mark_recovery(marks, gap_start, gap_end, event, config)
    candle = _candle_recovery(recovered, event, preregistration)
    decision = _decision_recovery(decisions, gap_start, gap_end)
    disposition = _disposition(mark, candle, decision)
    return _report(event, gap_start, gap_end, mark, candle, decision, disposition)


def _validated_contract(
    preregistration: Mapping[str, object], watcher: Mapping[str, object]
) -> Mapping[str, object]:
    expected = {
        "schema_version": "v58_sp500_fresh15_lifecycle_watch_preregistration_v1",
        "symbol": _SYMBOL,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    if any(preregistration.get(key) != value for key, value in expected.items()):
        raise ValueError("SP500 recovery preregistration contract is invalid")
    event = _mapping(preregistration.get("event"), "event")
    watcher_event = _mapping(watcher.get("lifecycle"), "watcher lifecycle")
    safe = (
        watcher.get("schema_version") == "sp500_fresh15_lifecycle_watch_status_v1"
        and watcher.get("symbol") == _SYMBOL
        and watcher.get("execution_authority") == "none"
        and watcher_event == event
    )
    if not safe:
        raise ValueError("SP500 recovery watcher identity is invalid")
    _require_event(event)
    return event


def _require_event(event: Mapping[str, object]) -> None:
    side = event.get("side")
    entry = _positive_number(event.get("entry_price"), "entry price")
    stop = _positive_number(event.get("stop_price"), "stop price")
    if side not in {"long", "short"} or (side == "short") != (stop > entry):
        raise ValueError("SP500 recovery event is inconsistent")


def _gap_start(watcher: Mapping[str, object]) -> int:
    path = _mapping(watcher.get("path"), "watcher path")
    reasons = watcher.get("trigger_reasons")
    safe = (
        path.get("source_gap") is True
        and path.get("profit_lock_activated") is False
        and isinstance(reasons, list)
        and "profit_lock_source_gap" in reasons
    )
    if not safe:
        raise ValueError("SP500 recovery requires an inactive source-gap boundary")
    return _positive_integer(path.get("last_bar_close_ms"), "gap start")


def _recovered_candles(
    rows: Sequence[Mapping[str, object]], start_ms: int
) -> tuple[Record, ...]:
    selected = sorted(
        (_validated_candle(row) for row in rows if row.get("prospective") is False),
        key=lambda row: int(row["bar_open_ms"]),
    )
    selected = [row for row in selected if int(row["bar_open_ms"]) >= start_ms]
    if not selected or int(selected[0]["bar_open_ms"]) != start_ms:
        raise ValueError("SP500 recovery first retrospective candle is missing")
    opens = [int(row["bar_open_ms"]) for row in selected]
    if len(opens) != len(set(opens)):
        raise ValueError("SP500 recovery candles contain a duplicate boundary")
    contiguous = [selected[0]]
    for row in selected[1:]:
        if int(row["bar_open_ms"]) != int(contiguous[-1]["bar_close_ms"]):
            break
        contiguous.append(row)
    return tuple(contiguous)


def _validated_candle(row: Mapping[str, object]) -> Record:
    opened = _positive_integer(row.get("bar_open_ms"), "bar open")
    closed = _positive_integer(row.get("bar_close_ms"), "bar close")
    observed = _positive_integer(row.get("observed_at_ms"), "bar observed at")
    safe = (
        row.get("event_type") == _CANDLE_EVENT
        and row.get("symbol") == _SYMBOL
        and row.get("source") == _CANDLE_SOURCE
        and row.get("prospective") is False
        and row.get("execution_authority") == "none"
        and closed == opened + 60_000
        and observed >= closed
    )
    if not safe:
        raise ValueError("SP500 recovery candle identity is invalid")
    output = dict(row)
    for key in ("open", "high", "low", "close"):
        output[key] = _positive_number(row.get(key), f"candle {key}")
    return output


def _verified_marks(
    manifest: Mapping[str, object],
    prices: pd.DataFrame,
    start_ms: int,
    end_ms: int,
) -> tuple[tuple[int, float], ...]:
    _require_manifest(manifest, prices, start_ms, end_ms)
    required = {"ts_ms", "mark_price", "source"}
    if not required.issubset(prices.columns):
        raise ValueError("SP500 recovery prices are missing required columns")
    times = pd.to_numeric(prices["ts_ms"], errors="raise")
    marks = pd.to_numeric(prices["mark_price"], errors="raise")
    if prices["source"].ne(_PRICE_SOURCE).any() or marks.isna().any():
        raise ValueError("SP500 recovery mark source or values are invalid")
    rows = tuple((int(ts), float(mark)) for ts, mark in zip(times, marks, strict=True))
    if any(mark <= 0 for _, mark in rows) or len({ts for ts, _ in rows}) != len(rows):
        raise ValueError("SP500 recovery marks must be positive and unique")
    return tuple(sorted(rows))


def _require_manifest(
    manifest: Mapping[str, object], prices: pd.DataFrame, start_ms: int, end_ms: int
) -> None:
    expected = {
        "schema_version": 1,
        "complete": True,
        "continuation_cursor": None,
        "market_family": "hip3",
        "source": _PRICE_SOURCE,
        "symbol": _SYMBOL,
        "row_count": len(prices),
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("SP500 recovery price manifest is invalid")
    requested_start = _timestamp_ms(manifest.get("requested_start"), "archive start")
    requested_end = _timestamp_ms(manifest.get("requested_end"), "archive end")
    if requested_start > start_ms or requested_end < end_ms:
        raise ValueError("SP500 recovery price archive does not cover the outage")


def _mark_recovery(
    rows: tuple[tuple[int, float], ...],
    start_ms: int,
    end_ms: int,
    event: Mapping[str, object],
    config: Sp500Fresh15GapRecoveryConfig,
) -> Record:
    selected = tuple(row for row in rows if start_ms <= row[0] < end_ms)
    if not selected:
        raise ValueError("SP500 recovery has no marks inside the outage window")
    quality = hip3_bar_path_quality(
        tuple(row[0] for row in selected),
        start_ms=start_ms,
        end_ms=end_ms,
        maximum_gap_ms=config.maximum_mark_gap_ms,
    )
    side, stop = str(event["side"]), float(event["stop_price"])
    crossed = (
        tuple(row for row in selected if row[1] <= stop)
        if side == "long"
        else tuple(row for row in selected if row[1] >= stop)
    )
    return {
        **quality,
        "source": _PRICE_SOURCE,
        "stop_price": stop,
        "stop_crossed": bool(crossed),
        "first_stop_cross_ms": None if not crossed else crossed[0][0],
        "minimum_mark": min(row[1] for row in selected),
        "maximum_mark": max(row[1] for row in selected),
    }


def _candle_recovery(
    rows: Sequence[Mapping[str, object]],
    event: Mapping[str, object],
    preregistration: Mapping[str, object],
) -> Record:
    policy = _mapping(preregistration.get("profit_lock"), "profit lock")
    bars = tuple(_market_bar(row) for row in rows)
    result = evaluate_profit_lock_path(
        ProfitLockPolicy(
            str(policy["policy_id"]),
            _positive_number(policy.get("activation_bps"), "activation bps"),
            _positive_number(policy.get("floor_bps"), "floor bps"),
            _positive_number(policy.get("trailing_giveback_bps"), "giveback bps"),
        ),
        str(event["side"]),
        bars,
        float(event["entry_price"]),
    )
    return {
        "source": _CANDLE_SOURCE,
        "retrospective": True,
        "completed_bars": len(bars),
        "profit_lock_activated": result.activation_timestamp_ms is not None,
        "profit_lock_triggered": result.trigger is not None,
    }


def _market_bar(row: Mapping[str, object]) -> CohortMarketBar:
    return CohortMarketBar(
        _SYMBOL,
        int(row["bar_open_ms"]),
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        0.0,
    )


def _decision_recovery(
    rows: Sequence[Mapping[str, object]], start_ms: int, end_ms: int
) -> Record:
    observed = {
        int(decision["decision_time_ms"])
        for row in rows
        for decision in (_mapping(row.get("decision"), "decision"),)
        if "decision_time_ms" in decision
    }
    first = math.ceil(start_ms / _DECISION_INTERVAL_MS) * _DECISION_INTERVAL_MS
    expected = tuple(range(first, end_ms, _DECISION_INTERVAL_MS))
    missing = [value for value in expected if value not in observed]
    return {
        "expected_boundaries_ms": list(expected),
        "missing_boundaries_ms": missing,
        "prospective_complete": not missing,
    }


def _disposition(mark: Record, candle: Record, decision: Record) -> str:
    if mark["stop_crossed"] is True or candle["profit_lock_triggered"] is True:
        return "EXACT_EXIT_REPLAY_REQUIRED"
    if mark["complete"] is not True:
        return "OPEN_LIFECYCLE_CENSORED_MARK_GAP"
    if decision["prospective_complete"] is not True:
        return "OPEN_LIFECYCLE_CENSORED_DECISION_GAP"
    return "OPEN_LIFECYCLE_CENSORED_NO_EXIT"


def _report(
    event: Mapping[str, object],
    start_ms: int,
    end_ms: int,
    mark: Record,
    candle: Record,
    decision: Record,
    disposition: str,
) -> Record:
    return {
        "schema_version": "sp500_fresh15_gap_recovery_v1",
        "symbol": _SYMBOL,
        "gap": {"start_ms": start_ms, "end_ms": end_ms},
        "lifecycle": dict(event),
        "mark_recovery": mark,
        "recovered_candles": candle,
        "decision_recovery": decision,
        "disposition": disposition,
        "technical_assessment": {
            "mark_risk_path_resolved": mark["complete"] is True,
            "historical_candle_path_resolved": True,
            "prospective_decision_path_resolved": decision["prospective_complete"]
            is True,
            "full_lifecycle_path_resolved": False,
            "live_change_supported": False,
        },
        "report_only": True,
        "execution_authority": "none",
        "orders_supported": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"SP500 recovery {label} must be an object")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"SP500 recovery {label} must be a positive integer")
    return value


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"SP500 recovery {label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"SP500 recovery {label} must be positive and finite")
    return number


def _timestamp_ms(value: object, label: str) -> int:
    if not isinstance(value, str):
        raise ValueError(f"SP500 recovery {label} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError(f"SP500 recovery {label} must include a UTC offset")
    return int(parsed.timestamp() * 1_000)
