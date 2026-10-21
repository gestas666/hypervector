"""Compare immutable cohort live-audit prefixes without execution authority."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import math

from hypervector.research.cohort_live_audit_bbo_delta import (
    build_executable_bbo_maturity_delta,
)
from hypervector.research.cohort_live_audit_signal_delta import (
    build_signal_maturity_delta,
)

Record = Mapping[str, object]

_REPORT_ONLY_CONTRACT: dict[str, object] = {
    "automatic_promotion": False,
    "execution_authority": "none",
    "report_only": True,
    "runtime_strategy_changed": False,
}


def build_live_audit_delta(before: Record, after: Record) -> dict[str, object]:
    """Build one strict report-only delta between comparable audit prefixes."""
    before_run = _validated_run(before, "before")
    after_run = _validated_run(after, "after")
    _require_same_identity(before_run, after_run)
    identity = _identity_delta(before_run, after_run)
    before_closed = _trade_index(before, "trade_reflections", "before closed")
    after_closed = _trade_index(after, "trade_reflections", "after closed")
    before_open = _trade_index(before, "open_trade_reflections", "before open")
    after_open = _trade_index(after, "open_trade_reflections", "after open")
    resolved = _resolved_delta(before, after, before_closed, after_closed)
    technical = _technical_delta(before, after)
    open_delta = _open_delta(before_open, after_open, after_closed)
    signal_maturity = build_signal_maturity_delta(before, after)
    bbo_maturity = build_executable_bbo_maturity_delta(before, after)
    return {
        "schema_version": 2,
        "mode": "cohort_live_audit_prefix_delta",
        "contract": dict(_REPORT_ONLY_CONTRACT),
        "identity": identity,
        "resolved_execution": resolved,
        "technical_coverage": technical,
        "signal_outcome_maturity": signal_maturity,
        "executable_bbo_episode_maturity": bbo_maturity,
        "open_lifecycles": open_delta,
        "assessment": _assessment(
            resolved,
            technical,
            open_delta,
            signal_maturity,
            bbo_maturity,
        ),
        "limitations": _limitations(),
    }


def _validated_run(audit: Record, label: str) -> Record:
    contract = _mapping(audit.get("experiment_contract"), f"{label} contract")
    if contract.get("execution_authority") != "none":
        raise ValueError(f"{label} audit must have no execution authority")
    if contract.get("report_only") is not True:
        raise ValueError(f"{label} audit must be report-only")
    if contract.get("runtime_strategy_changed") is not False:
        raise ValueError(f"{label} audit cannot change runtime strategy")
    return _mapping(audit.get("run"), f"{label} run")


def _require_same_identity(before: Record, after: Record) -> None:
    for field in ("run_id", "profile_id", "profile_fingerprint"):
        if _text(before.get(field), f"before {field}") != _text(
            after.get(field), f"after {field}"
        ):
            raise ValueError(f"audit prefixes must have the same {field}")
    before_rows = _nonnegative_int(before.get("row_count"), "before row_count")
    after_rows = _nonnegative_int(after.get("row_count"), "after row_count")
    if after_rows < before_rows:
        raise ValueError("after row_count cannot move backwards")
    if _timestamp(after.get("last_observed_at_utc"), "after timestamp") < _timestamp(
        before.get("last_observed_at_utc"), "before timestamp"
    ):
        raise ValueError("after timestamp cannot move backwards")


def _identity_delta(before: Record, after: Record) -> dict[str, object]:
    before_rows = _nonnegative_int(before.get("row_count"), "before row_count")
    after_rows = _nonnegative_int(after.get("row_count"), "after row_count")
    return {
        "run_id": _text(after.get("run_id"), "run id"),
        "profile_id": _text(after.get("profile_id"), "profile id"),
        "profile_fingerprint": _text(
            after.get("profile_fingerprint"), "profile fingerprint"
        ),
        "before_last_observed_at_utc": _text(
            before.get("last_observed_at_utc"), "before timestamp"
        ),
        "after_last_observed_at_utc": _text(
            after.get("last_observed_at_utc"), "after timestamp"
        ),
        "before_row_count": before_rows,
        "after_row_count": after_rows,
        "row_count_delta": after_rows - before_rows,
    }


def _resolved_delta(
    before: Record,
    after: Record,
    before_closed: Mapping[str, Record],
    after_closed: Mapping[str, Record],
) -> dict[str, object]:
    before_execution = _mapping(before.get("execution"), "before execution")
    after_execution = _mapping(after.get("execution"), "after execution")
    result: dict[str, object] = {
        "newly_closed_lifecycle_ids": sorted(after_closed.keys() - before_closed.keys())
    }
    for field in ("closed_trades", "wins", "losses", "fills"):
        before_value = _nonnegative_int(before_execution.get(field), f"before {field}")
        after_value = _nonnegative_int(after_execution.get(field), f"after {field}")
        result[f"{field}_delta"] = after_value - before_value
    for field in ("net_pnl_usd", "fees_usd", "funding_usd"):
        result[f"{field}_delta"] = _required_number(
            after_execution.get(field), f"after {field}"
        ) - _required_number(before_execution.get(field), f"before {field}")
    return result


def _technical_delta(before: Record, after: Record) -> dict[str, object]:
    before_coverage = _mapping(before.get("coverage"), "before coverage")
    after_coverage = _mapping(after.get("coverage"), "after coverage")
    before_signal = _signal_coverage(before, "before")
    after_signal = _signal_coverage(after, "after")
    before_gaps = set(_text_list(before_coverage.get("technical_gaps"), "before gaps"))
    after_gaps = set(_text_list(after_coverage.get("technical_gaps"), "after gaps"))
    return {
        "before_complete": _boolean(before_coverage.get("complete"), "before complete"),
        "after_complete": _boolean(after_coverage.get("complete"), "after complete"),
        "technical_gaps_added": sorted(after_gaps - before_gaps),
        "technical_gaps_removed": sorted(before_gaps - after_gaps),
        "metric_value_gaps_delta": _integer_delta(
            before_signal, after_signal, "metric_value_gaps"
        ),
        "right_censored_observations_delta": _integer_delta(
            before_signal, after_signal, "right_censored_observations"
        ),
    }


def _signal_coverage(audit: Record, label: str) -> Record:
    outcomes = _mapping(audit.get("signal_outcomes"), f"{label} signal outcomes")
    return _mapping(outcomes.get("coverage"), f"{label} signal coverage")


def _integer_delta(before: Record, after: Record, field: str) -> int:
    return _nonnegative_int(after.get(field), f"after {field}") - _nonnegative_int(
        before.get(field), f"before {field}"
    )


def _open_delta(
    before: Mapping[str, Record],
    after: Mapping[str, Record],
    after_closed: Mapping[str, Record],
) -> dict[str, object]:
    added = sorted(after.keys() - before.keys())
    removed = sorted(before.keys() - after.keys())
    matched = [
        _matched_open_delta(before[key], after[key])
        for key in sorted(before.keys() & after.keys())
    ]
    return {
        "added": added,
        "removed": removed,
        "removed_without_close": sorted(set(removed) - after_closed.keys()),
        "matched": matched,
    }


def _matched_open_delta(before: Record, after: Record) -> dict[str, object]:
    before_path = _mapping(before.get("path_since_entry"), "before entry path")
    after_path = _mapping(after.get("path_since_entry"), "after entry path")
    return {
        "lifecycle_id": _text(after.get("lifecycle_id"), "lifecycle id"),
        "symbol": _text(after.get("symbol"), "symbol"),
        "strategy_id": _text(after.get("strategy_id"), "strategy id"),
        "side": _text(after.get("side"), "side"),
        "holding_time_ms_delta": _optional_number_delta(
            before.get("holding_time_ms"), after.get("holding_time_ms")
        ),
        "marked_net_pnl_usd_delta": _nested_number_delta(
            before, after, "marked_economics", "active_lifecycle_marked_net_pnl_usd"
        ),
        "current_directional_return_bps_delta": _field_number_delta(
            before_path, after_path, "current_directional_return_bps"
        ),
        "maximum_favorable_excursion_bps_delta": _field_number_delta(
            before_path, after_path, "maximum_favorable_excursion_bps"
        ),
        "maximum_adverse_excursion_bps_delta": _field_number_delta(
            before_path, after_path, "maximum_adverse_excursion_bps"
        ),
        "peak_giveback_bps_delta": _field_number_delta(
            before_path, after_path, "peak_giveback_bps"
        ),
        "decision_action_before": _decision_action(before),
        "decision_action_after": _decision_action(after),
    }


def _decision_action(trade: Record) -> str | None:
    context = _optional_mapping(trade.get("current_context"))
    provider = (
        None if context is None else _optional_mapping(context.get("signal_provider"))
    )
    if provider is None or provider.get("decision_action") is None:
        return None
    return _text(provider.get("decision_action"), "decision action")


def _trade_index(audit: Record, field: str, label: str) -> dict[str, Record]:
    section = _mapping(audit.get(field), label)
    trades = section.get("trades")
    if not isinstance(trades, list):
        raise TypeError(f"{label} trades must be a list")
    result: dict[str, Record] = {}
    for value in trades:
        trade = _mapping(value, f"{label} trade")
        lifecycle_id = _text(trade.get("lifecycle_id"), f"{label} lifecycle id")
        if lifecycle_id in result:
            raise ValueError(f"{label} has duplicate lifecycle_id: {lifecycle_id}")
        result[lifecycle_id] = trade
    return result


def _assessment(
    resolved: Record,
    technical: Record,
    open_delta: Record,
    signal_maturity: Record,
    bbo_maturity: Record,
) -> dict[str, object]:
    resolved_change = _nonzero(resolved.get("closed_trades_delta"))
    technical_identity_change = bool(technical.get("technical_gaps_added")) or bool(
        technical.get("technical_gaps_removed")
    )
    removed_without_close = bool(open_delta.get("removed_without_close"))
    bbo_change = bool(bbo_maturity.get("newly_matured_episode_onsets"))
    return {
        "resolved_economic_change": resolved_change,
        "technical_gap_identity_change": technical_identity_change,
        "known_technical_gap_count_changed": _nonzero(
            technical.get("metric_value_gaps_delta")
        ),
        "provisional_open_change": _has_open_change(open_delta),
        "signal_outcome_maturity_change": bool(
            signal_maturity.get("newly_matured_paths")
        ),
        "executable_bbo_episode_maturity_change": bbo_change,
        "journal_revision_recommended": (
            resolved_change
            or technical_identity_change
            or removed_without_close
            or bbo_change
        ),
    }


def _has_open_change(delta: Record) -> bool:
    if delta.get("added") or delta.get("removed"):
        return True
    matched = delta.get("matched")
    if not isinstance(matched, list):
        raise TypeError("matched open deltas must be a list")
    return any(
        _record_has_nonzero_delta(_mapping(row, "matched open delta"))
        for row in matched
    )


def _record_has_nonzero_delta(row: Record) -> bool:
    return any(key.endswith("_delta") and _nonzero(value) for key, value in row.items())


def _limitations() -> list[str]:
    return [
        "open-lifecycle marks and paths are provisional and cannot establish exit edge",
        "a removed open lifecycle without a matching closed identity is an evidence gap",
        "known metric-gap growth is technical coverage evidence, not an economic result",
        "matured signal paths describe opportunity capture and are not hypothetical fills",
        "executable BBO paths are markouts, not orders, fills, or realized PnL",
        "the delta cannot place, cancel, resize, close, route, or promote a trade",
    ]


def _nested_number_delta(
    before: Record, after: Record, section: str, field: str
) -> float | None:
    return _field_number_delta(
        _mapping(before.get(section), f"before {section}"),
        _mapping(after.get(section), f"after {section}"),
        field,
    )


def _field_number_delta(before: Record, after: Record, field: str) -> float | None:
    return _optional_number_delta(before.get(field), after.get(field))


def _optional_number_delta(before: object, after: object) -> float | None:
    before_number = _optional_number(before)
    after_number = _optional_number(after)
    if before_number is None or after_number is None:
        return None
    return after_number - before_number


def _optional_number(value: object) -> float | None:
    return None if value is None else _required_number(value, "number")


def _required_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _nonzero(value: object) -> bool:
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0
    )


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _optional_mapping(value: object) -> Record | None:
    if value is None:
        return None
    return _mapping(value, "optional mapping")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    return [_text(item, label) for item in value]


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be boolean")
    return value


def _timestamp(value: object, label: str) -> datetime:
    text = _text(value, label)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a UTC offset")
    return parsed.astimezone(UTC)
