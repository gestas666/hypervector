"""Report-only condition diagnostics for live HIP-3 index decisions."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import math

import pandas as pd

from hypervector.data.oxa_api import validate_market_symbol
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)

Record = dict[str, object]
_BAR_MS = 900_000
_CONTRACT = {
    "report_only": True,
    "execution_authority": "none",
    "automatic_live_change": False,
    "performance_gate": False,
    "runtime_strategy_changed": False,
}


@dataclass(frozen=True)
class Hip3IndexLiveConditionConfig:
    """Freeze one live route and the exact current-run lower bound."""

    symbol: str
    provider_id: str
    profile_id: str
    run_started_at_ms: int
    breakout: Hip3BreakoutPressureConfig

    def __post_init__(self) -> None:
        """Reject incomplete or aliased route identities."""
        validate_market_symbol(self.symbol, "hip3")
        if not self.provider_id.strip() or not self.profile_id.strip():
            raise ValueError("live condition diagnostic requires route identity")
        if isinstance(self.run_started_at_ms, bool) or self.run_started_at_ms <= 0:
            raise ValueError("run_started_at_ms must be positive")


def build_hip3_index_live_condition_diagnostic(
    *,
    candles: pd.DataFrame,
    observer_rows: list[Record],
    config: Hip3IndexLiveConditionConfig,
) -> Record:
    """Explain exact current-run route conditions without execution authority."""
    features = _candle_features(candles, config)
    decisions, excluded = _current_decisions(observer_rows, config)
    observations = [_observation(row, features, config) for row in decisions]
    if not observations:
        raise ValueError("live condition diagnostic has no current-run decisions")
    return {
        "schema_version": "hip3_index_live_condition_diagnostic_v1",
        "contract": _CONTRACT.copy(),
        "scope": _scope(config, observations),
        "coverage": _coverage(observations, excluded),
        "observer_outcomes": _observer_outcomes(observations),
        "pressure": _pressure_summary(observations),
        "sides": {
            side: _side_summary(observations, side) for side in ("long", "short")
        },
        "observations": observations,
        "assessment": {
            "status": "collecting_source_native_forward_evidence",
            "parameter_change_supported": False,
            "economic_edge_established": False,
            "reason": "condition telemetry has no completed costed lifecycle evidence",
        },
        "limitations": [
            "condition proximity is not realized profit or executable fill evidence",
            "the observer decision is authoritative for fresh-onset eligibility",
            "no strategy, leverage, sizing, exit, or execution parameter is changed",
        ],
    }


def _candle_features(
    frame: pd.DataFrame, config: Hip3IndexLiveConditionConfig
) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"live condition candles missing columns: {sorted(missing)}")
    values = frame.loc[:, ["timestamp", "open", "high", "low", "close"]].copy()
    values["timestamp"] = pd.to_datetime(values["timestamp"], utc=True)
    values = values.set_index("timestamp").sort_index()
    _validate_candles(values)
    params = config.breakout
    values["prior_high"] = (
        values["high"].shift(1).rolling(params.breakout_lookback_bars).max()
    )
    values["prior_low"] = (
        values["low"].shift(1).rolling(params.breakout_lookback_bars).min()
    )
    values["fast_ema"] = (
        values["close"]
        .ewm(span=params.fast_ema, adjust=False, min_periods=params.fast_ema)
        .mean()
    )
    values["slow_ema"] = (
        values["close"]
        .ewm(span=params.slow_ema, adjust=False, min_periods=params.slow_ema)
        .mean()
    )
    return values


def _validate_candles(values: pd.DataFrame) -> None:
    if values.empty or not values.index.is_unique:
        raise ValueError("live condition candles require unique rows")
    gaps = values.index.to_series().diff().dropna()
    if not gaps.eq(pd.Timedelta(minutes=15)).all():
        raise ValueError("live condition candles require continuous completed 15m rows")
    prices = values.loc[:, ["open", "high", "low", "close"]].astype(float)
    if not prices.map(math.isfinite).to_numpy().all() or prices.le(0).any().any():
        raise ValueError("live condition candle prices must be finite and positive")
    if prices["high"].lt(prices[["open", "low", "close"]].max(axis=1)).any():
        raise ValueError("live condition candle highs are inconsistent")
    if prices["low"].gt(prices[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError("live condition candle lows are inconsistent")


def _current_decisions(
    rows: list[Record], config: Hip3IndexLiveConditionConfig
) -> tuple[list[Record], int]:
    selected: list[Record] = []
    excluded = 0
    seen: set[int] = set()
    for row in rows:
        decision = _decision(row, config)
        boundary = _integer(decision, "decision_time_ms")
        if boundary < config.run_started_at_ms:
            excluded += 1
            continue
        if boundary in seen:
            raise ValueError(
                "live condition observer has duplicate decision boundaries"
            )
        seen.add(boundary)
        selected.append(decision)
    return sorted(
        selected, key=lambda item: _integer(item, "decision_time_ms")
    ), excluded


def _decision(row: Record, config: Hip3IndexLiveConditionConfig) -> Record:
    raw = row.get("decision")
    if not isinstance(raw, dict):
        raise ValueError("live condition observer decision must be an object")
    decision = dict(raw)
    valid = (
        row.get("report_only") is True
        and row.get("execution_authority") == "none"
        and row.get("runtime_strategy_changed") is False
        and row.get("intents") == []
        and decision.get("execution_authority") == "none"
        and decision.get("prospective") is True
        and decision.get("symbol") == config.symbol
        and decision.get("provider_id") == config.provider_id
        and decision.get("profile_id") == config.profile_id
    )
    if not valid:
        raise ValueError("live condition observer identity or authority is invalid")
    return decision


def _observation(
    decision: Record,
    features: pd.DataFrame,
    config: Hip3IndexLiveConditionConfig,
) -> Record:
    boundary = _integer(decision, "decision_time_ms")
    if boundary % _BAR_MS:
        raise ValueError("live condition decision boundary must be 15m aligned")
    bar_open = pd.to_datetime(boundary - _BAR_MS, unit="ms", utc=True)
    if bar_open not in features.index:
        raise ValueError("live condition decision has no matching completed candle")
    candle = features.loc[bar_open]
    required = ("prior_high", "prior_low", "fast_ema", "slow_ema")
    if any(pd.isna(candle[field]) for field in required):
        raise ValueError("live condition decision lacks required indicator history")
    pressure = _number(decision, "decision_imbalance_10")
    fresh = decision.get("pressure_fresh") is True
    history = decision.get("pressure_state_history_complete") is True
    long = _conditions(candle, pressure, fresh and history, config, "long")
    short = _conditions(candle, pressure, fresh and history, config, "short")
    return {
        "decision_time_ms": boundary,
        "bar_open_ms": boundary - _BAR_MS,
        "close": float(candle["close"]),
        "decision_imbalance_10": pressure,
        "pressure_fresh": fresh,
        "pressure_state_history_complete": history,
        "authoritative_eligible": _boolean(decision, "eligible"),
        "authoritative_side": decision.get("side"),
        "long": long,
        "short": short,
    }


def _conditions(
    candle: pd.Series,
    pressure: float,
    pressure_valid: bool,
    config: Hip3IndexLiveConditionConfig,
    side: str,
) -> Record:
    close = float(candle["close"])
    if side == "long":
        price = close > float(candle["prior_high"])
        ema = float(candle["fast_ema"]) > float(candle["slow_ema"])
        book = pressure_valid and pressure >= config.breakout.minimum_abs_imbalance
        distance = (float(candle["prior_high"]) - close) / close * 10_000.0
    else:
        price = close < float(candle["prior_low"])
        ema = float(candle["fast_ema"]) < float(candle["slow_ema"])
        book = pressure_valid and pressure <= -config.breakout.minimum_abs_imbalance
        distance = (close - float(candle["prior_low"])) / close * 10_000.0
    return {
        "price_breakout": price,
        "ema_alignment": ema,
        "pressure_confirmation": book,
        "raw_condition": price and ema and book,
        "breakout_distance_bps": distance,
    }


def _side_summary(observations: list[Record], side: str) -> Record:
    rows = [_mapping(row, side) for row in observations]
    fields = ("price_breakout", "ema_alignment", "pressure_confirmation")
    blockers: Counter[str] = Counter()
    for row in rows:
        missing = [field for field in fields if row.get(field) is not True]
        if len(missing) == 1:
            blockers[missing[0]] += 1
    distances = [_number(row, "breakout_distance_bps") for row in rows]
    return {
        "price_breakout_true": _true_count(rows, "price_breakout"),
        "ema_alignment_true": _true_count(rows, "ema_alignment"),
        "pressure_confirmation_true": _true_count(rows, "pressure_confirmation"),
        "raw_condition_true": _true_count(rows, "raw_condition"),
        "one_blocker": dict(sorted(blockers.items())),
        "nearest_breakout_distance_bps": min(distances),
    }


def _coverage(observations: list[Record], excluded: int) -> Record:
    return {
        "current_run_decisions": len(observations),
        "excluded_pre_run_decisions": excluded,
        "fresh_pressure_decisions": sum(
            row["pressure_fresh"] is True for row in observations
        ),
        "complete_pressure_history_decisions": sum(
            row["pressure_state_history_complete"] is True for row in observations
        ),
    }


def _observer_outcomes(observations: list[Record]) -> Record:
    eligible = [row for row in observations if row["authoritative_eligible"] is True]
    return {
        "eligible": len(eligible),
        "long": sum(row["authoritative_side"] == "long" for row in eligible),
        "short": sum(row["authoritative_side"] == "short" for row in eligible),
    }


def _pressure_summary(observations: list[Record]) -> Record:
    values = [float(row["decision_imbalance_10"]) for row in observations]
    series = pd.Series(values, dtype=float)
    return {
        "minimum": min(values),
        "median": float(series.median()),
        "maximum": max(values),
    }


def _scope(config: Hip3IndexLiveConditionConfig, observations: list[Record]) -> Record:
    return {
        "symbol": config.symbol,
        "provider_id": config.provider_id,
        "profile_id": config.profile_id,
        "run_started_at_ms": config.run_started_at_ms,
        "first_decision_time_ms": observations[0]["decision_time_ms"],
        "last_decision_time_ms": observations[-1]["decision_time_ms"],
        "timeframe": "15m",
        "signal": asdict(config.breakout),
    }


def _true_count(rows: list[Record], key: str) -> int:
    return sum(row.get(key) is True for row in rows)


def _mapping(row: Record, key: str) -> Record:
    value = row.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"live condition {key} must be an object")
    return dict(value)


def _integer(row: Record, key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"live condition {key} must be an integer")
    return value


def _number(row: Record, key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"live condition {key} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"live condition {key} must be finite")
    return result


def _boolean(row: Record, key: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"live condition {key} must be boolean")
    return value
