"""Fail-closed status for the first V58 SP500 fresh15 lifecycle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from hypervector.cohort_profit_lock_policy import (
    ProfitLockPolicy,
    evaluate_profit_lock_path,
)
from hypervector.live.multi_asset_market_bars import CohortMarketBar

Record = dict[str, object]

_PREREGISTRATION_SCHEMA = "v58_sp500_fresh15_lifecycle_watch_preregistration_v1"
_DECISION_EVENT = "sp500_hip3_breakout_shadow_decision"
_CANDLE_EVENT = "sp500_hip3_breakout_shadow_profit_lock_candle_observation"
_CANDLE_SOURCE = "hyperliquid_public_candleSnapshot_1m"


def build_sp500_fresh15_lifecycle_status(
    preregistration: Mapping[str, object],
    decisions: Sequence[Mapping[str, object]],
    candles: Sequence[Mapping[str, object]],
    *,
    observed_at_ms: int,
) -> dict[str, object]:
    """Return the report-only status of the frozen first lifecycle."""
    _require_safe_preregistration(preregistration)
    observed_at = _positive_integer(observed_at_ms, "observed at")
    event = _event(preregistration)
    included = _included_decisions(preregistration, decisions, event, observed_at)
    bars, last_observed, source_gap = _completed_bars(
        preregistration, candles, event, observed_at
    )
    policy = _profit_lock_policy(preregistration)
    lock = evaluate_profit_lock_path(
        policy, str(event["side"]), bars, float(event["entry_price"])
    )
    stale = observed_at - last_observed > _positive_integer(
        preregistration.get("maximum_candle_age_ms"), "maximum candle age"
    )
    reasons = _trigger_reasons(
        preregistration,
        event,
        included,
        bars,
        lock.trigger is not None,
        source_gap,
        stale,
        observed_at,
    )
    return _status(
        observed_at,
        event,
        included,
        bars,
        lock.activation_timestamp_ms,
        lock.trigger is not None,
        source_gap,
        stale,
        reasons,
    )


def _require_safe_preregistration(preregistration: Mapping[str, object]) -> None:
    expected = {
        "schema_version": _PREREGISTRATION_SCHEMA,
        "status": "prospective_collecting",
        "symbol": "xyz:SP500",
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    if any(preregistration.get(field) != value for field, value in expected.items()):
        raise ValueError("SP500 lifecycle preregistration contract is invalid")


def _event(preregistration: Mapping[str, object]) -> Record:
    event = _mapping(preregistration.get("event"), "event")
    side = _text(event.get("side"), "event side")
    if side not in {"long", "short"}:
        raise ValueError("SP500 lifecycle side must be long or short")
    decision = _positive_integer(event.get("decision_time_ms"), "decision time")
    entry = _positive_integer(event.get("entry_time_ms"), "entry time")
    entry_price = _positive_number(event.get("entry_price"), "entry price")
    stop_price = _positive_number(event.get("stop_price"), "stop price")
    if entry < decision or (side == "short") != (stop_price > entry_price):
        raise ValueError("SP500 lifecycle event contract is inconsistent")
    return {
        "decision_time_ms": decision,
        "entry_time_ms": entry,
        "side": side,
        "entry_price": entry_price,
        "stop_price": stop_price,
    }


def _included_decisions(
    preregistration: Mapping[str, object],
    rows: Sequence[Mapping[str, object]],
    event: Mapping[str, object],
    observed_at_ms: int,
) -> list[Record]:
    included = []
    seen: set[int] = set()
    for row in rows:
        decision = _mapping(row.get("decision"), "decision")
        decision_ms = _positive_integer(
            decision.get("decision_time_ms"), "decision time"
        )
        if decision_ms < int(event["decision_time_ms"]):
            continue
        _require_decision(preregistration, row, decision, observed_at_ms)
        if decision_ms in seen:
            raise ValueError("SP500 lifecycle contains a duplicate decision boundary")
        seen.add(decision_ms)
        included.append(dict(decision))
    included.sort(key=lambda value: int(value["decision_time_ms"]))
    _require_entry_decision(included, event)
    return included


def _require_decision(
    preregistration: Mapping[str, object],
    row: Mapping[str, object],
    decision: Mapping[str, object],
    observed_at_ms: int,
) -> None:
    expected = {
        "symbol": preregistration["symbol"],
        "provider_id": preregistration["provider_id"],
        "profile_id": preregistration["profile_id"],
        "prospective": True,
        "execution_authority": "none",
    }
    if row.get("event_type") != _DECISION_EVENT or any(
        decision.get(field) != value for field, value in expected.items()
    ):
        raise ValueError("SP500 lifecycle decision identity is invalid")
    observed = _positive_integer(decision.get("observed_at_ms"), "decision observed at")
    if observed > observed_at_ms or not isinstance(decision.get("eligible"), bool):
        raise ValueError("SP500 lifecycle decision availability is invalid")
    eligible, side = decision["eligible"], decision.get("side")
    if (eligible and side not in {"long", "short"}) or (
        not eligible and side is not None
    ):
        raise ValueError("SP500 lifecycle decision side is inconsistent")


def _require_entry_decision(
    rows: Sequence[Mapping[str, object]], event: Mapping[str, object]
) -> None:
    matches = [
        row
        for row in rows
        if row["decision_time_ms"] == event["decision_time_ms"]
        and row["observed_at_ms"] == event["entry_time_ms"]
        and row["eligible"] is True
        and row["side"] == event["side"]
    ]
    if len(matches) != 1:
        raise ValueError("SP500 lifecycle entry decision is missing or duplicated")


def _completed_bars(
    preregistration: Mapping[str, object],
    rows: Sequence[Mapping[str, object]],
    event: Mapping[str, object],
    observed_at_ms: int,
) -> tuple[tuple[CohortMarketBar, ...], int, bool]:
    selected = []
    for row in rows:
        if _retrospective_candle(preregistration, row):
            continue
        open_ms = _positive_integer(row.get("bar_open_ms"), "bar open")
        if open_ms < int(event["decision_time_ms"]):
            continue
        selected.append(_market_bar(preregistration, row, observed_at_ms))
    selected.sort(key=lambda value: value[0].timestamp_ms)
    if not selected:
        raise ValueError("SP500 lifecycle has no completed profit-lock candles")
    prefix, source_gap = _contiguous_prefix(selected, int(event["decision_time_ms"]))
    if not prefix:
        raise ValueError(
            "SP500 lifecycle first completed profit-lock candle is missing"
        )
    return tuple(value[0] for value in prefix), prefix[-1][1], source_gap


def _retrospective_candle(
    preregistration: Mapping[str, object], row: Mapping[str, object]
) -> bool:
    if row.get("prospective") is not False:
        return False
    safe = (
        row.get("event_type") == _CANDLE_EVENT
        and row.get("symbol") == preregistration["symbol"]
        and row.get("source") == _CANDLE_SOURCE
        and row.get("execution_authority") == "none"
    )
    if not safe:
        raise ValueError("SP500 retrospective candle contract is invalid")
    return True


def _market_bar(
    preregistration: Mapping[str, object],
    row: Mapping[str, object],
    observed_at_ms: int,
) -> tuple[CohortMarketBar, int]:
    open_ms = _positive_integer(row.get("bar_open_ms"), "bar open")
    close_ms = _positive_integer(row.get("bar_close_ms"), "bar close")
    observed = _positive_integer(row.get("observed_at_ms"), "bar observed at")
    safe = (
        row.get("event_type") == _CANDLE_EVENT
        and row.get("symbol") == preregistration["symbol"]
        and row.get("source") == _CANDLE_SOURCE
        and row.get("prospective") is True
        and row.get("execution_authority") == "none"
        and close_ms == open_ms + 60_000
        and observed <= observed_at_ms
    )
    if not safe:
        raise ValueError("SP500 lifecycle candle contract is invalid")
    bar = CohortMarketBar(
        str(preregistration["symbol"]),
        open_ms,
        _positive_number(row.get("open"), "open"),
        _positive_number(row.get("high"), "high"),
        _positive_number(row.get("low"), "low"),
        _positive_number(row.get("close"), "close"),
        0.0,
    )
    return bar, observed


def _contiguous_prefix(
    rows: Sequence[tuple[CohortMarketBar, int]], first: int
) -> tuple[list[tuple[CohortMarketBar, int]], bool]:
    timestamps = [row[0].timestamp_ms for row in rows]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("SP500 lifecycle profit-lock candles contain duplicates")
    prefix = []
    expected = first
    for row in rows:
        if row[0].timestamp_ms != expected:
            return prefix, True
        prefix.append(row)
        expected += 60_000
    return prefix, False


def _profit_lock_policy(preregistration: Mapping[str, object]) -> ProfitLockPolicy:
    policy = _mapping(preregistration.get("profit_lock"), "profit lock")
    return ProfitLockPolicy(
        _text(policy.get("policy_id"), "profit lock policy"),
        _positive_number(policy.get("activation_bps"), "activation bps"),
        _positive_number(policy.get("floor_bps"), "floor bps"),
        _positive_number(policy.get("trailing_giveback_bps"), "giveback bps"),
    )


def _trigger_reasons(
    preregistration: Mapping[str, object],
    event: Mapping[str, object],
    decisions: Sequence[Mapping[str, object]],
    bars: Sequence[CohortMarketBar],
    profit_lock_triggered: bool,
    source_gap: bool,
    stale: bool,
    observed_at_ms: int,
) -> list[str]:
    side = str(event["side"])
    stop = float(event["stop_price"])
    stop_crossed = any(
        bar.low <= stop if side == "long" else bar.high >= stop for bar in bars
    )
    opposite = any(
        row["eligible"] is True
        and row["side"] != side
        and int(row["observed_at_ms"]) > int(event["entry_time_ms"])
        for row in decisions
    )
    hold = _positive_integer(preregistration.get("maximum_hold_minutes"), "hold")
    max_hold = observed_at_ms >= int(event["decision_time_ms"]) + hold * 60_000
    flags = (
        (stop_crossed, "protective_stop_candidate"),
        (profit_lock_triggered, "completed_bar_profit_lock"),
        (opposite, "opposite_eligible_intent"),
        (max_hold, "maximum_hold_elapsed"),
        (source_gap, "profit_lock_source_gap"),
        (stale, "profit_lock_source_stale"),
    )
    return [reason for triggered, reason in flags if triggered]


def _status(
    observed_at_ms: int,
    event: Mapping[str, object],
    decisions: Sequence[Mapping[str, object]],
    bars: Sequence[CohortMarketBar],
    activation_ms: int | None,
    profit_lock_triggered: bool,
    source_gap: bool,
    stale: bool,
    reasons: Sequence[str],
) -> Record:
    scenario = {"resolved": 0, "censored": 1, "modeled_net_usd_excluding_funding": 0.0}
    due = bool(reasons)
    return {
        "schema_version": "sp500_fresh15_lifecycle_watch_status_v1",
        "symbol": "xyz:SP500",
        "observed_at_ms": observed_at_ms,
        "watch_state": (
            "LIFECYCLE_REPLAY_CANDIDATE_DUE" if due else "OPEN_LIFECYCLE_CENSORED"
        ),
        "lifecycle_replay_candidate_due": due,
        "trigger_reasons": list(reasons),
        "source": {
            "observed_decisions": len(decisions),
            "eligible_decisions": sum(row["eligible"] is True for row in decisions),
        },
        "lifecycle": _event_status(event),
        "nominal": {"summary": dict(scenario)},
        "stress": {"summary": dict(scenario)},
        "path": _path_status(
            bars, activation_ms, profit_lock_triggered, source_gap, stale
        ),
        "technical_assessment": {
            "all_observed_paths_resolved": False,
            "live_change_supported": False,
        },
        "report_only": True,
        "execution_authority": "none",
        "orders_supported": False,
        "signing_client_constructed": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def _event_status(event: Mapping[str, object]) -> Record:
    fields = ("side", "decision_time_ms", "entry_time_ms", "entry_price", "stop_price")
    return {field: event[field] for field in fields}


def _path_status(
    bars: Sequence[CohortMarketBar],
    activation_ms: int | None,
    profit_lock_triggered: bool,
    source_gap: bool,
    stale: bool,
) -> Record:
    return {
        "completed_candles": len(bars),
        "last_bar_close_ms": bars[-1].timestamp_ms + 60_000,
        "last_close": bars[-1].close,
        "minimum_low": min(bar.low for bar in bars),
        "maximum_high": max(bar.high for bar in bars),
        "profit_lock_activated": activation_ms is not None,
        "profit_lock_activation_ms": activation_ms,
        "profit_lock_triggered": profit_lock_triggered,
        "source_gap": source_gap,
        "source_stale": stale,
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"SP500 lifecycle {label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"SP500 lifecycle {label} must be non-empty text")
    return value.strip()


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"SP500 lifecycle {label} must be a positive integer")
    return value


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"SP500 lifecycle {label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"SP500 lifecycle {label} must be positive and finite")
    return number
