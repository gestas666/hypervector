"""Causal forward outcomes for exact live HIP-3 price-only blockers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

import pandas as pd

Record = Mapping[str, object]
MutableRecord = dict[str, object]
_BAR_MINUTES = 15
_BAR_MS = 900_000
_SIDES = frozenset(("long", "short"))
_CONTRACT = {
    "report_only": True,
    "execution_authority": "none",
    "automatic_live_change": False,
    "runtime_strategy_changed": False,
    "execution_claim": False,
}


def build_hip3_index_price_blocker_outcomes(
    *,
    condition_report: Record,
    candles: pd.DataFrame,
    side: str,
    horizons_minutes: Sequence[int],
    round_trip_friction_bps: float,
    stop_bps: float,
) -> MutableRecord:
    """Measure completed paths after exact price-only blocker observations."""
    scope = _validate_condition_report(condition_report, side)
    horizons = _horizons(horizons_minutes)
    friction = _positive_number(round_trip_friction_bps, "round-trip friction")
    stop = _positive_number(stop_bps, "stop bps")
    frame = _candle_frame(candles)
    candidates = _candidates(condition_report, side)
    outcomes = [
        _outcome(row, frame, side, horizon, friction, stop)
        for row in candidates
        for horizon in horizons
    ]
    return {
        "schema_version": "hip3_index_price_blocker_outcomes_v1",
        "contract": dict(_CONTRACT),
        "scope": {
            **scope,
            "side": side,
            "candidate_observations": len(candidates),
            "horizons_minutes": list(horizons),
            "round_trip_friction_bps": friction,
            "stop_bps": stop,
        },
        "outcomes": outcomes,
        "by_horizon": {
            str(horizon): _summary(outcomes, horizon) for horizon in horizons
        },
        "assessment": _assessment(candidates, outcomes),
        "limitations": _limitations(),
    }


def _validate_condition_report(report: Record, side: str) -> MutableRecord:
    if side not in _SIDES:
        raise ValueError("price-blocker side must be long or short")
    contract = _mapping(report.get("contract"), "condition report contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("condition report contract is invalid")
    if report.get("schema_version") != "hip3_index_live_condition_diagnostic_v1":
        raise ValueError("condition report schema is invalid")
    scope = _mapping(report.get("scope"), "condition report scope")
    required = ("symbol", "provider_id", "profile_id", "profile_fingerprint", "run_id")
    result = {field: _text(scope.get(field), field) for field in required}
    if scope.get("timeframe") != "15m":
        raise ValueError("condition report timeframe must be 15m")
    return {**result, "timeframe": "15m"}


def _candidates(report: Record, side: str) -> list[MutableRecord]:
    raw = report.get("observations")
    if not isinstance(raw, list):
        raise ValueError("condition report observations must be an array")
    output: list[MutableRecord] = []
    seen: set[int] = set()
    for value in raw:
        row = _mapping(value, "condition observation")
        boundary = _integer(row.get("decision_time_ms"), "decision time")
        if boundary in seen:
            raise ValueError("condition observations contain duplicate decisions")
        seen.add(boundary)
        conditions = _mapping(row.get(side), f"{side} conditions")
        if _is_price_only_blocker(conditions):
            output.append(dict(row))
    if not output:
        raise ValueError("condition report has no exact price-only blocker")
    return sorted(output, key=lambda row: int(row["decision_time_ms"]))


def _is_price_only_blocker(conditions: Record) -> bool:
    return (
        conditions.get("price_breakout") is False
        and conditions.get("ema_alignment") is True
        and conditions.get("pressure_confirmation") is True
    )


def _candle_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"price-blocker candles missing columns: {sorted(missing)}")
    result = frame.loc[:, sorted(required)].copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
    result = result.set_index("timestamp").sort_index()
    if result.empty or not result.index.is_unique:
        raise ValueError("price-blocker candles require unique rows")
    prices = result.loc[:, ["open", "high", "low", "close"]].astype(float)
    if not prices.map(math.isfinite).to_numpy().all() or prices.le(0).any().any():
        raise ValueError("price-blocker candle prices must be finite and positive")
    if prices["high"].lt(prices[["open", "low", "close"]].max(axis=1)).any():
        raise ValueError("price-blocker candle highs are inconsistent")
    if prices["low"].gt(prices[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError("price-blocker candle lows are inconsistent")
    return result


def _outcome(
    candidate: Record,
    frame: pd.DataFrame,
    side: str,
    horizon: int,
    friction: float,
    stop: float,
) -> MutableRecord:
    boundary = _integer(candidate.get("decision_time_ms"), "decision time")
    entry = _positive_number(candidate.get("close"), "condition close")
    start = pd.to_datetime(boundary, unit="ms", utc=True)
    expected = pd.date_range(start, periods=horizon // _BAR_MINUTES, freq="15min")
    path = frame.reindex(expected)
    if path["close"].isna().any():
        return _censored_outcome(boundary, horizon, len(path.dropna()))
    gross, favorable, adverse = _path_metrics(path, entry, side)
    return {
        "decision_time_ms": boundary,
        "horizon_minutes": horizon,
        "status": "resolved",
        "reference_close": entry,
        "exit_close": float(path.iloc[-1]["close"]),
        "gross_close_return_bps": gross,
        "round_trip_friction_bps": friction,
        "after_friction_bps": gross - friction,
        "maximum_favorable_excursion_bps": favorable,
        "maximum_adverse_excursion_bps": adverse,
        "stop_touched": adverse <= -stop,
    }


def _path_metrics(path: pd.DataFrame, entry: float, side: str) -> tuple[float, ...]:
    sign = 1.0 if side == "long" else -1.0
    exit_close = float(path.iloc[-1]["close"])
    gross = sign * (exit_close - entry) / entry * 10_000.0
    if side == "long":
        favorable = (float(path["high"].max()) - entry) / entry * 10_000.0
        adverse = (float(path["low"].min()) - entry) / entry * 10_000.0
    else:
        favorable = (entry - float(path["low"].min())) / entry * 10_000.0
        adverse = (entry - float(path["high"].max())) / entry * 10_000.0
    return gross, favorable, adverse


def _censored_outcome(boundary: int, horizon: int, observed: int) -> MutableRecord:
    return {
        "decision_time_ms": boundary,
        "horizon_minutes": horizon,
        "status": "censored_incomplete_future_path",
        "observed_bars": observed,
        "expected_bars": horizon // _BAR_MINUTES,
    }


def _summary(outcomes: list[MutableRecord], horizon: int) -> MutableRecord:
    rows = [row for row in outcomes if row["horizon_minutes"] == horizon]
    resolved = [row for row in rows if row["status"] == "resolved"]
    after = [float(row["after_friction_bps"]) for row in resolved]
    independent = _independent(resolved, horizon)
    return {
        "observations": len(rows),
        "resolved": len(resolved),
        "censored": len(rows) - len(resolved),
        "cost_clearing": sum(value > 0.0 for value in after),
        "stop_touched": sum(row["stop_touched"] is True for row in resolved),
        "mean_after_friction_bps": _mean(after),
        "median_after_friction_bps": _median(after),
        "mean_excluding_largest_bps": _without_largest(after),
        "independent_resolved": len(independent),
        "independent_mean_after_friction_bps": _mean(
            [float(row["after_friction_bps"]) for row in independent]
        ),
    }


def _independent(rows: list[MutableRecord], horizon: int) -> list[MutableRecord]:
    output: list[MutableRecord] = []
    next_boundary = -1
    for row in sorted(rows, key=lambda item: int(item["decision_time_ms"])):
        boundary = int(row["decision_time_ms"])
        if boundary >= next_boundary:
            output.append(row)
            next_boundary = boundary + horizon * 60_000
    return output


def _assessment(
    candidates: list[MutableRecord], outcomes: list[MutableRecord]
) -> MutableRecord:
    resolved = sum(row["status"] == "resolved" for row in outcomes)
    return {
        "status": "descriptive_counterfactual_only",
        "parameter_change_supported": False,
        "economic_edge_established": False,
        "candidate_observations": len(candidates),
        "resolved_paths": resolved,
        "reason": "price-only blocker paths do not reproduce executable entries or exits",
    }


def _limitations() -> list[str]:
    return [
        "decision close is a reference price rather than an executable entry quote",
        "round-trip friction is a declared symmetric sensitivity",
        "overlapping horizons are reported separately from greedy independent paths",
        "the counterfactual does not alter the active breakout requirement",
    ]


def _horizons(values: Sequence[int]) -> tuple[int, ...]:
    output = tuple(values)
    valid = output and output == tuple(sorted(set(output)))
    if not valid or any(value <= 0 or value % _BAR_MINUTES for value in output):
        raise ValueError("horizons must be unique positive ordered 15m multiples")
    return output


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _median(values: list[float]) -> float | None:
    return float(pd.Series(values, dtype=float).median()) if values else None


def _without_largest(values: list[float]) -> float | None:
    return (
        _mean(
            values[: values.index(max(values))]
            + values[values.index(max(values)) + 1 :]
        )
        if len(values) > 1
        else None
    )


def _mapping(value: object, label: str) -> MutableRecord:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return result
