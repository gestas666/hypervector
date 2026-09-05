"""Validated prospective lifecycle status for external research candidates."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path

Record = Mapping[str, object]

_WATCH_STATES = {
    "LIFECYCLE_REPLAY_CANDIDATE_DUE",
    "OPEN_LIFECYCLE_CENSORED",
    "WAITING_ELIGIBLE_ONSET",
    "TECHNICAL_COVERAGE_GAP",
    "TECHNICALLY_UNRESOLVED",
    "PROSPECTIVE_SAMPLE_RESOLVED",
}


def load_external_lifecycle_status(
    catalog_path: Path,
    record: Record,
    symbol: str,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Load one optional, fail-closed report-only lifecycle status."""
    value = record.get("lifecycle_status_path")
    if value is None:
        return None, None
    path = _resolve(catalog_path, value)
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), "external lifecycle status")
    _require_contract(payload, symbol)
    timestamp, age = _status_age(payload, observed_at)
    status = _status(payload, age, maximum_age_seconds)
    status["observed_at_utc"] = timestamp.isoformat()
    return status, _evidence(path, raw)


def _require_contract(payload: Record, symbol: str) -> None:
    expected = {
        "symbol": symbol,
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    if any(payload.get(field) != value for field, value in expected.items()):
        raise ValueError(f"external lifecycle contract is invalid: {symbol}")
    technical = _mapping(payload.get("technical_assessment"), "technical assessment")
    if technical.get("live_change_supported") is not False:
        raise ValueError(f"external lifecycle grants live authority: {symbol}")
    state = _text(payload.get("watch_state"), "lifecycle watch state")
    if state not in _WATCH_STATES:
        raise ValueError(f"external lifecycle watch state is invalid: {state}")


def _status_age(payload: Record, observed_at: datetime) -> tuple[datetime, float]:
    observed_ms = _integer(payload.get("observed_at_ms"), "lifecycle observed at")
    timestamp = datetime.fromtimestamp(observed_ms / 1000.0, tz=UTC)
    age = (observed_at - timestamp).total_seconds()
    if age < 0.0:
        raise ValueError("external lifecycle status is from the future")
    return timestamp, age


def _status(
    payload: Record, age_seconds: float, maximum_age_seconds: float
) -> dict[str, object]:
    source = _mapping(payload.get("source"), "lifecycle source")
    nominal = _summary(payload, "nominal")
    stress = _summary(payload, "stress")
    observed = _integer(source.get("observed_decisions"), "observed decisions")
    eligible = _integer(source.get("eligible_decisions"), "eligible decisions")
    if eligible > observed:
        raise ValueError("external lifecycle decision counts are invalid")
    _require_scenario_counts(nominal, stress, eligible)
    technical = _mapping(payload.get("technical_assessment"), "technical assessment")
    status = {
        "watch_state": payload["watch_state"],
        "freshness_status": "stale" if age_seconds > maximum_age_seconds else "fresh",
        "age_seconds": age_seconds,
        "observed_decisions": observed,
        "eligible_decisions": eligible,
        **_scenario_status("nominal", nominal),
        **_scenario_status("stress", stress),
        "all_observed_paths_resolved": _boolean(
            technical.get("all_observed_paths_resolved"), "all paths resolved"
        ),
        "live_change_supported": False,
    }
    status.update(_independent_window_fields(payload, eligible))
    status.update(_sp500_lifecycle_fields(payload, eligible))
    return status


def _independent_window_fields(payload: Record, eligible: int) -> dict[str, object]:
    if payload.get("schema_version") != "mu_source_native_independent_window_status_v1":
        return {}
    state = _text(payload.get("collection_state"), "MU collection state")
    allowed = {
        "collecting_minimum_onsets",
        "lifecycle_replay_candidate_due",
        "collection_deadline_reached",
        "technical_coverage_gap",
    }
    if state not in allowed:
        raise ValueError("external MU collection state is invalid")
    sides = _mapping(payload.get("eligible_onsets_by_side"), "MU side onsets")
    side_counts = {
        side: _integer(sides.get(side), f"MU {side} eligible onsets")
        for side in ("long", "short")
    }
    if sum(side_counts.values()) != eligible:
        raise ValueError("external MU side onset counts do not reconcile")
    due = _boolean(payload.get("lifecycle_replay_candidate_due"), "MU replay due")
    deadline = _boolean(
        payload.get("collection_deadline_reached"), "MU deadline reached"
    )
    schedule = _mu_schedule_fields(payload, state, due)
    return {
        "collection_state": state,
        "eligible_decisions_by_side": side_counts,
        "lifecycle_replay_candidate_due": due,
        "collection_deadline_reached": deadline,
        **schedule,
    }


def _mu_schedule_fields(payload: Record, state: str, due: bool) -> dict[str, object]:
    technical = _mapping(payload.get("technical_assessment"), "technical assessment")
    raw_complete = technical.get("decision_schedule_complete")
    is_gap = state == "technical_coverage_gap"
    if is_gap and raw_complete is not False:
        raise ValueError("external MU technical gap requires an incomplete schedule")
    if is_gap and due:
        raise ValueError("external MU technical gap cannot be replay-ready")
    if raw_complete is None:
        return {}
    complete = _boolean(raw_complete, "MU decision schedule completeness")
    if not complete and not is_gap:
        raise ValueError("external MU incomplete schedule must be a technical gap")
    return {"decision_schedule_complete": complete}


def _sp500_lifecycle_fields(payload: Record, eligible: int) -> dict[str, object]:
    if payload.get("schema_version") != "sp500_fresh15_lifecycle_watch_status_v1":
        return {}
    if payload.get("orders_supported") is not False:
        raise ValueError("external SP500 lifecycle can place orders")
    if payload.get("signing_client_constructed") is not False:
        raise ValueError("external SP500 lifecycle constructed a signing client")
    if eligible < 1:
        raise ValueError("external SP500 lifecycle requires an eligible entry")
    due = _boolean(payload.get("lifecycle_replay_candidate_due"), "SP500 replay due")
    state = _text(payload.get("watch_state"), "SP500 lifecycle state")
    expected_state = (
        "LIFECYCLE_REPLAY_CANDIDATE_DUE" if due else "OPEN_LIFECYCLE_CENSORED"
    )
    if state != expected_state:
        raise ValueError("external SP500 replay state is contradictory")
    reasons = _trigger_reasons(payload, due)
    lifecycle = _mapping(payload.get("lifecycle"), "SP500 lifecycle")
    path = _mapping(payload.get("path"), "SP500 lifecycle path")
    return {
        "lifecycle_replay_candidate_due": due,
        "trigger_reasons": reasons,
        **_sp500_event(lifecycle),
        **_sp500_path(path),
        "pnl_claimed": False,
    }


def _trigger_reasons(payload: Record, due: bool) -> list[str]:
    value = payload.get("trigger_reasons")
    if not isinstance(value, list) or not all(isinstance(row, str) for row in value):
        raise ValueError("external SP500 trigger reasons must be text")
    allowed = {
        "protective_stop_candidate",
        "completed_bar_profit_lock",
        "opposite_eligible_intent",
        "maximum_hold_elapsed",
        "profit_lock_source_gap",
        "profit_lock_source_stale",
    }
    reasons = list(value)
    if len(reasons) != len(set(reasons)) or any(row not in allowed for row in reasons):
        raise ValueError("external SP500 trigger reasons are invalid")
    if bool(reasons) != due:
        raise ValueError("external SP500 trigger reasons contradict replay state")
    return reasons


def _sp500_event(value: Record) -> dict[str, object]:
    side = _text(value.get("side"), "SP500 lifecycle side")
    decision = _integer(value.get("decision_time_ms"), "SP500 decision time")
    entry = _integer(value.get("entry_time_ms"), "SP500 entry time")
    entry_price = _positive_number(value.get("entry_price"), "SP500 entry price")
    stop_price = _positive_number(value.get("stop_price"), "SP500 stop price")
    if side not in {"long", "short"} or decision == 0 or entry < decision:
        raise ValueError("external SP500 lifecycle event is invalid")
    if (side == "short") != (stop_price > entry_price):
        raise ValueError("external SP500 lifecycle stop is invalid")
    return {
        "side": side,
        "decision_time_ms": decision,
        "entry_time_ms": entry,
        "entry_price": entry_price,
        "stop_price": stop_price,
    }


def _sp500_path(value: Record) -> dict[str, object]:
    completed = _integer(value.get("completed_candles"), "SP500 completed candles")
    last_close_ms = _integer(value.get("last_bar_close_ms"), "SP500 last bar close")
    if completed == 0 or last_close_ms == 0:
        raise ValueError("external SP500 lifecycle path is empty")
    return {
        "completed_candles": completed,
        "last_bar_close_ms": last_close_ms,
        "last_close": _positive_number(value.get("last_close"), "SP500 last close"),
        "minimum_low": _positive_number(value.get("minimum_low"), "SP500 minimum low"),
        "maximum_high": _positive_number(
            value.get("maximum_high"), "SP500 maximum high"
        ),
        "profit_lock_activated": _boolean(
            value.get("profit_lock_activated"), "SP500 profit lock activated"
        ),
        "profit_lock_triggered": _boolean(
            value.get("profit_lock_triggered"), "SP500 profit lock triggered"
        ),
        "source_gap": _boolean(value.get("source_gap"), "SP500 source gap"),
        "source_stale": _boolean(value.get("source_stale"), "SP500 source stale"),
    }


def _summary(payload: Record, name: str) -> Record:
    scenario = _mapping(payload.get(name), f"{name} lifecycle")
    return _mapping(scenario.get("summary"), f"{name} lifecycle summary")


def _require_scenario_counts(nominal: Record, stress: Record, eligible: int) -> None:
    counts = []
    for summary in (nominal, stress):
        resolved = _integer(summary.get("resolved"), "resolved lifecycles")
        censored = _integer(summary.get("censored"), "censored lifecycles")
        if resolved + censored > eligible:
            raise ValueError(
                "external lifecycle scenario counts exceed eligible signals"
            )
        counts.append((resolved, censored))
    if counts[0] != counts[1]:
        raise ValueError("external lifecycle scenario path counts differ")


def _scenario_status(prefix: str, summary: Record) -> dict[str, object]:
    return {
        f"{prefix}_resolved": _integer(summary.get("resolved"), "resolved"),
        f"{prefix}_censored": _integer(summary.get("censored"), "censored"),
        f"{prefix}_net_usd_excluding_funding": _number(
            summary.get("modeled_net_usd_excluding_funding"), "modeled net"
        ),
    }


def _resolve(catalog_path: Path, value: object) -> Path:
    text = _text(value, "lifecycle status path")
    path = Path(text)
    return path if path.is_absolute() else (catalog_path.parent / path).resolve()


def _evidence(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"external {label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"external {label} must be non-empty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"external {label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"external {label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"external {label} must be finite")
    return number


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise ValueError(f"external {label} must be positive")
    return number


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"external {label} must be boolean")
    return value
