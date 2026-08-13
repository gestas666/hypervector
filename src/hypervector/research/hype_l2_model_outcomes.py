"""Join prospective HYPE L2 annotations to authoritative venue lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

_OBSERVATION_MODE = "hype_l2_ridge_prospective_observe_v1"
_CHECKPOINT_MODE = "multi_asset_bidirectional_live_checkpoint"
_OUTCOME_MODE = "hype_l2_ridge_prospective_outcomes_v1"
_STRATEGY = "hype_breakout_onset_bidirectional_v1"
_ENTRY_MATCH_WINDOW_MS = 120_000
Record = Mapping[str, object]


def summarize_hype_l2_model_outcomes(
    observations: Sequence[Record],
    checkpoint: Record,
) -> dict[str, object]:
    """Build report-only calibration evidence from exact compatible live fills."""
    execution = _checkpoint_execution(checkpoint)
    fills = _mapping_rows(execution.get("fill_details"), "fill details")
    positions = _mapping_rows(execution.get("open_positions"), "open positions")
    reflections = _checkpoint_trade_reflections(checkpoint)
    outcomes = [
        _resolve_observation(row, fills, positions, reflections) for row in observations
    ]
    resolved = [row for row in outcomes if row["status"] == "resolved"]
    return {
        "schema_version": 1,
        "mode": _OUTCOME_MODE,
        "status": "observed",
        "contract": _report_only_contract(),
        "counts": _outcome_counts(outcomes),
        "latest_outcome": max(
            outcomes,
            key=lambda row: _integer(row.get("decision_time_ms"), "decision time"),
            default=None,
        ),
        "resolved_performance": _performance(resolved),
        "resolved_by_score_band": _performance_by(resolved, "score_band"),
        "resolved_by_side": _performance_by(resolved, "side"),
        "gross_calibration": _gross_calibration(resolved),
        "confidence": "low" if resolved else "none_no_resolved_outcomes",
    }


def unavailable_hype_l2_model_outcomes(issue: str) -> dict[str, object]:
    """Describe unavailable outcome evidence without manufacturing measurements."""
    if not issue.strip():
        raise ValueError("HYPE L2 outcome issue must not be empty")
    return {
        "schema_version": 1,
        "mode": _OUTCOME_MODE,
        "status": "unavailable",
        "technical_issue": issue,
        "contract": _report_only_contract(),
        "counts": None,
        "latest_outcome": None,
        "resolved_performance": None,
        "resolved_by_score_band": None,
        "resolved_by_side": None,
        "gross_calibration": None,
        "confidence": "none_unavailable",
    }


def _checkpoint_execution(checkpoint: Record) -> Record:
    if (
        checkpoint.get("schema_version") != 1
        or checkpoint.get("mode") != _CHECKPOINT_MODE
    ):
        raise ValueError("HYPE L2 outcome checkpoint identity is invalid")
    contract = _mapping(checkpoint.get("checkpoint_contract"), "checkpoint contract")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
        or contract.get("runtime_strategy_changed") is not False
    ):
        raise ValueError("HYPE L2 outcome checkpoint violates report-only contract")
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    return _mapping(audit.get("execution"), "checkpoint execution")


def _checkpoint_trade_reflections(checkpoint: Record) -> list[Record]:
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    value = audit.get("trade_reflections")
    if value is None:
        return []
    reflections = _mapping(value, "checkpoint trade reflections")
    all_time = _mapping(reflections.get("all_time_live"), "all-time reflections")
    return _mapping_rows(all_time.get("trades"), "all-time reflection trades")


def _resolve_observation(
    observation: Record,
    fills: Sequence[Record],
    positions: Sequence[Record],
    reflections: Sequence[Record],
) -> dict[str, object]:
    _validate_observation(observation)
    base = _outcome_base(observation)
    if observation.get("status") == "coverage_unavailable":
        return {**base, "status": "coverage_unavailable"}
    reflection = _closed_trade_reflection(observation, reflections)
    if reflection is not None:
        return {
            **base,
            **_resolved_reflection_economics(reflection),
            "status": "resolved",
        }
    entry = _entry_fill(observation, fills)
    if entry is None:
        return {**base, **_empty_economics(), "status": "awaiting_entry_fill"}
    closes = _close_fills(entry, observation, fills)
    if closes:
        return {**base, **_resolved_economics(entry, closes), "status": "resolved"}
    position = _open_position(observation, positions)
    if position is None:
        return {**base, **_entry_economics(entry), "status": "unreconciled"}
    return {**base, **_open_economics(entry, position), "status": "open"}


def _validate_observation(observation: Record) -> None:
    if (
        observation.get("schema_version") != 1
        or observation.get("mode") != _OBSERVATION_MODE
    ):
        raise ValueError("HYPE L2 outcome observation identity is invalid")
    if (
        observation.get("execution_authority") != "none"
        or observation.get("report_only") is not True
        or observation.get("runtime_strategy_changed") is not False
        or observation.get("automatic_promotion") is not False
    ):
        raise ValueError("HYPE L2 outcome observation violates report-only contract")
    if observation.get("strategy_id") != _STRATEGY:
        raise ValueError("HYPE L2 outcome observation strategy is invalid")
    if observation.get("side") not in {"long", "short"}:
        raise ValueError("HYPE L2 outcome observation side is invalid")
    if observation.get("status") not in {"scored", "coverage_unavailable"}:
        raise ValueError("HYPE L2 outcome observation status is invalid")


def _entry_fill(observation: Record, fills: Sequence[Record]) -> Record | None:
    decision_ms = _integer(observation.get("decision_time_ms"), "decision time")
    direction = f"Open {_text(observation.get('side'), 'side').title()}"
    matches = [
        fill
        for fill in fills
        if fill.get("symbol") == "HYPE"
        and fill.get("strategy_id") == _STRATEGY
        and fill.get("origin_run_id") == observation.get("run_id")
        and fill.get("direction") == direction
        and decision_ms
        <= _integer(fill.get("venue_timestamp_ms"), "entry time")
        <= decision_ms + _ENTRY_MATCH_WINDOW_MS
    ]
    if len(matches) > 1:
        raise ValueError("HYPE L2 outcome matched multiple entry fills")
    return matches[0] if matches else None


def _closed_trade_reflection(
    observation: Record,
    reflections: Sequence[Record],
) -> Record | None:
    decision_ms = _integer(observation.get("decision_time_ms"), "decision time")
    matches: list[Record] = []
    for row in reflections:
        if (
            row.get("symbol") != "HYPE"
            or row.get("strategy_id") != _STRATEGY
            or row.get("source_run_id") != observation.get("run_id")
            or row.get("side") != observation.get("side")
        ):
            continue
        entry = _mapping(row.get("entry"), "trade reflection entry")
        entry_ms = _integer(entry.get("venue_timestamp_ms"), "entry time")
        if decision_ms <= entry_ms <= decision_ms + _ENTRY_MATCH_WINDOW_MS:
            matches.append(row)
    if len(matches) > 1:
        raise ValueError("HYPE L2 outcome matched multiple trade reflections")
    return matches[0] if matches else None


def _close_fills(
    entry: Record,
    observation: Record,
    fills: Sequence[Record],
) -> list[Record]:
    entry_time = _integer(entry.get("venue_timestamp_ms"), "entry time")
    direction = f"Close {_text(observation.get('side'), 'side').title()}"
    return [
        fill
        for fill in fills
        if fill.get("symbol") == "HYPE"
        and fill.get("strategy_id") == _STRATEGY
        and fill.get("direction") == direction
        and fill.get("entry_venue_timestamp_ms") == entry_time
    ]


def _open_position(observation: Record, positions: Sequence[Record]) -> Record | None:
    matches = [
        row
        for row in positions
        if row.get("symbol") == "HYPE"
        and row.get("side") == observation.get("side")
        and row.get("status") == "provisional_open"
    ]
    if len(matches) > 1:
        raise ValueError("HYPE L2 outcome matched multiple open HYPE positions")
    return matches[0] if matches else None


def _resolved_economics(entry: Record, closes: Sequence[Record]) -> dict[str, object]:
    entry_price, entry_size, notional = _entry_terms(entry)
    gross_pnl = sum(_number(row.get("closed_pnl_usd"), "closed PnL") for row in closes)
    lifecycle = closes[-1]
    net_pnl = _consistent_number(closes, "net_pnl_usd", "net PnL")
    fees = _consistent_number(closes, "lifecycle_fees_usd", "lifecycle fees")
    funding = _consistent_number(closes, "lifecycle_funding_usd", "funding")
    return {
        **_entry_economics(entry),
        "entry_price": entry_price,
        "entry_size": entry_size,
        "exit_timestamp_ms": max(
            _integer(row.get("venue_timestamp_ms"), "exit time") for row in closes
        ),
        "exit_reason": lifecycle.get("exit_reason"),
        "holding_time_ms": lifecycle.get("holding_time_ms"),
        "actual_gross_return_bps": gross_pnl / notional * 10_000.0,
        "actual_net_return_bps": net_pnl / notional * 10_000.0,
        "marked_gross_return_bps": None,
        "marked_net_return_bps": None,
        "marked_net_pnl_usd": None,
        "fees_usd": fees,
        "funding_usd": funding,
        "net_pnl_usd": net_pnl,
    }


def _resolved_reflection_economics(reflection: Record) -> dict[str, object]:
    entry = _mapping(reflection.get("entry"), "trade reflection entry")
    exit_row = _mapping(reflection.get("exit"), "trade reflection exit")
    entry_price, entry_size, notional = _entry_terms(entry)
    net_pnl = _number(reflection.get("net_pnl_usd"), "net PnL")
    fees = _number(reflection.get("fees_usd"), "lifecycle fees")
    funding = _number(reflection.get("funding_usd"), "funding")
    gross_pnl = net_pnl + fees - funding
    return {
        "entry_trade_id": None,
        "entry_timestamp_ms": _integer(entry.get("venue_timestamp_ms"), "entry time"),
        "entry_price": entry_price,
        "entry_size": entry_size,
        "exit_timestamp_ms": _integer(exit_row.get("venue_timestamp_ms"), "exit time"),
        "exit_reason": reflection.get("exit_reason"),
        "holding_time_ms": reflection.get("holding_time_ms"),
        "actual_gross_return_bps": gross_pnl / notional * 10_000.0,
        "actual_net_return_bps": net_pnl / notional * 10_000.0,
        "marked_gross_return_bps": None,
        "marked_net_return_bps": None,
        "marked_net_pnl_usd": None,
        "fees_usd": fees,
        "funding_usd": funding,
        "net_pnl_usd": net_pnl,
    }


def _open_economics(entry: Record, position: Record) -> dict[str, object]:
    entry_price, _, notional = _entry_terms(entry)
    mark = _number(position.get("mark_price"), "mark price")
    side = _text(position.get("side"), "position side")
    sign = 1.0 if side == "long" else -1.0
    marked_net = _number(
        position.get("active_lifecycle_marked_net_pnl_usd"),
        "marked net PnL",
    )
    return {
        **_entry_economics(entry),
        "exit_timestamp_ms": None,
        "exit_reason": None,
        "holding_time_ms": None,
        "actual_gross_return_bps": None,
        "actual_net_return_bps": None,
        "marked_gross_return_bps": sign * (mark / entry_price - 1.0) * 10_000.0,
        "marked_net_return_bps": marked_net / notional * 10_000.0,
        "marked_net_pnl_usd": marked_net,
        "fees_usd": _number(position.get("fees_usd"), "open fees"),
        "funding_usd": _number(position.get("funding_usd"), "open funding"),
        "net_pnl_usd": None,
    }


def _entry_economics(entry: Record) -> dict[str, object]:
    price, size, _ = _entry_terms(entry)
    return {
        "entry_trade_id": _integer(entry.get("trade_id"), "entry trade id"),
        "entry_timestamp_ms": _integer(entry.get("venue_timestamp_ms"), "entry time"),
        "entry_price": price,
        "entry_size": size,
    }


def _empty_economics() -> dict[str, object]:
    return {
        "entry_trade_id": None,
        "entry_timestamp_ms": None,
        "entry_price": None,
        "entry_size": None,
        "exit_timestamp_ms": None,
        "exit_reason": None,
        "holding_time_ms": None,
        "actual_gross_return_bps": None,
        "actual_net_return_bps": None,
        "marked_gross_return_bps": None,
        "marked_net_return_bps": None,
        "marked_net_pnl_usd": None,
        "fees_usd": None,
        "funding_usd": None,
        "net_pnl_usd": None,
    }


def _outcome_base(observation: Record) -> dict[str, object]:
    return {
        "decision_time_ms": _integer(
            observation.get("decision_time_ms"), "decision time"
        ),
        "run_id": _text(observation.get("run_id"), "run id"),
        "side": _text(observation.get("side"), "side"),
        "score_band": observation.get("score_band"),
        "predicted_gross_return_bps": observation.get("predicted_gross_return_bps"),
        "training_score_percentile": observation.get("training_score_percentile"),
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
    }


def _outcome_counts(outcomes: Sequence[Record]) -> dict[str, int]:
    return {
        "observations": len(outcomes),
        "scored": sum(row.get("score_band") is not None for row in outcomes),
        "coverage_unavailable": _status_count(outcomes, "coverage_unavailable"),
        "awaiting_entry_fill": _status_count(outcomes, "awaiting_entry_fill"),
        "open": _status_count(outcomes, "open"),
        "resolved": _status_count(outcomes, "resolved"),
        "unreconciled": _status_count(outcomes, "unreconciled"),
    }


def _performance(resolved: Sequence[Record]) -> dict[str, object]:
    returns = [
        _number(row.get("actual_net_return_bps"), "net return") for row in resolved
    ]
    profits = sum(value for value in returns if value > 0.0)
    losses = -sum(value for value in returns if value < 0.0)
    return {
        "resolved": len(returns),
        "wins": sum(value > 0.0 for value in returns),
        "losses": sum(value < 0.0 for value in returns),
        "net_return_bps": sum(returns) if returns else None,
        "mean_net_return_bps": sum(returns) / len(returns) if returns else None,
        "profit_factor": profits / losses if losses else None,
    }


def _performance_by(
    resolved: Sequence[Record],
    field: str,
) -> dict[str, dict[str, object]]:
    groups: dict[str, list[Record]] = {}
    for row in resolved:
        value = _text(row.get(field), field.replace("_", " "))
        groups.setdefault(value, []).append(row)
    return {value: _performance(groups[value]) for value in sorted(groups)}


def _gross_calibration(resolved: Sequence[Record]) -> dict[str, object]:
    pairs = [
        (
            _number(row.get("predicted_gross_return_bps"), "predicted gross return"),
            _number(row.get("actual_gross_return_bps"), "actual gross return"),
        )
        for row in resolved
    ]
    if not pairs:
        return {
            "resolved": 0,
            "mean_predicted_gross_return_bps": None,
            "mean_actual_gross_return_bps": None,
            "mean_prediction_error_bps": None,
            "mean_absolute_prediction_error_bps": None,
            "directional_sign_agreement_rate": None,
        }
    errors = [actual - predicted for predicted, actual in pairs]
    agreements = [
        (predicted > 0.0) == (actual > 0.0) and (predicted < 0.0) == (actual < 0.0)
        for predicted, actual in pairs
    ]
    count = len(pairs)
    return {
        "resolved": count,
        "mean_predicted_gross_return_bps": sum(row[0] for row in pairs) / count,
        "mean_actual_gross_return_bps": sum(row[1] for row in pairs) / count,
        "mean_prediction_error_bps": sum(errors) / count,
        "mean_absolute_prediction_error_bps": sum(abs(value) for value in errors)
        / count,
        "directional_sign_agreement_rate": sum(agreements) / count,
    }


def _report_only_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
        "performance_gate": False,
    }


def _entry_terms(entry: Record) -> tuple[float, float, float]:
    price = _number(entry.get("price"), "entry price")
    size = _number(entry.get("size"), "entry size")
    if price <= 0.0 or size <= 0.0:
        raise ValueError("HYPE L2 outcome entry terms must be positive")
    return price, size, price * size


def _consistent_number(rows: Sequence[Record], key: str, label: str) -> float:
    values = {_number(row.get(key), label) for row in rows}
    if len(values) != 1:
        raise ValueError(f"HYPE L2 outcome {label} differs across close fills")
    return next(iter(values))


def _mapping_rows(value: object, label: str) -> list[Record]:
    if not isinstance(value, list):
        raise ValueError(f"HYPE L2 outcome {label} must be a list")
    return [_mapping(row, label) for row in value]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HYPE L2 outcome {label} must be an object")
    return cast(dict[str, object], value)


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HYPE L2 outcome {label} must be numeric")
    number = float(value)
    if not (-float("inf") < number < float("inf")):
        raise ValueError(f"HYPE L2 outcome {label} must be finite")
    return number


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"HYPE L2 outcome {label} must be an integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"HYPE L2 outcome {label} must be text")
    return value


def _status_count(outcomes: Sequence[Record], status: str) -> int:
    return sum(row.get("status") == status for row in outcomes)
