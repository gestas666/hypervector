"""Causal report-only replay of v2 retests over recorded v1 live decisions."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math

from hypervector.live.hype_breakout_retest_policy import (
    BreakoutRetestBar,
    BreakoutRetestResult,
    HypeBreakoutRetestPolicy,
)

_CONTROL = "hype_breakout_onset_bidirectional_v1"
_CHALLENGER = "hype_breakout_retest_bidirectional_v2"
_MINUTE_MS = 60_000
_PRIOR_BARS = 20
_TERMINAL_STATES = frozenset({"confirmed", "expired", "unavailable"})


@dataclass(frozen=True)
class _Candle:
    timestamp_ms: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float


@dataclass(frozen=True)
class _Series:
    times: tuple[int, ...]
    candles: Mapping[int, _Candle]


@dataclass(frozen=True)
class _Evaluation:
    symbol: str
    decision_time_ms: int
    reference_price: float
    breakout_onset: bool
    breakout_side: str | None
    structural_side: str | None
    relation: str
    state_1m: str
    state_5m: str
    side: str | None


@dataclass(frozen=True)
class _Route:
    status: str
    reason: str | None = None

    def as_payload(self) -> dict[str, object]:
        """Return a compact route record without success-shaped null reasons."""
        payload: dict[str, object] = {"status": self.status}
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


@dataclass
class _Onset:
    evaluation: _Evaluation
    route: _Route
    onset_result: BreakoutRetestResult | None
    resolution_time_ms: int | None = None
    resolution_reference_price: float | None = None
    resolution: BreakoutRetestResult | None = None
    disposition: str = "armed"


def build_hype_breakout_retest_replay(
    rows: Iterable[Mapping[str, object]],
    *,
    run_id: str,
    window_bars: int = 3,
) -> dict[str, object]:
    """Replay v2 causally over recorded completed bars with no execution authority."""
    normalized_run = _required_text(run_id, "run_id")
    records = tuple(row for row in rows if row.get("run_id") == normalized_run)
    evaluations, routes = _collect_decisions(records)
    series = _collect_series(records)
    onsets = _replay(evaluations, routes, series, window_bars)
    missing_routes = sum(onset.route.status == "not_routed" for onset in onsets)
    return {
        "schema_version": 1,
        "mode": "hype_breakout_retest_recorded_live_replay_v1",
        "run_id": normalized_run,
        "contract": _contract(window_bars),
        "coverage": {
            "control_evaluations": len(evaluations),
            "market_candles": sum(len(value.times) for value in series.values()),
            "missing_onset_routes": missing_routes,
            "symbols": sorted({evaluation.symbol for evaluation in evaluations}),
        },
        "summary": _summary(onsets),
        "onsets": [_onset_payload(onset) for onset in onsets],
        "limitations": _limitations(),
    }


def _collect_decisions(
    rows: tuple[Mapping[str, object], ...],
) -> tuple[tuple[_Evaluation, ...], dict[tuple[str, int], _Route]]:
    evaluations: dict[tuple[str, int], _Evaluation] = {}
    routes: dict[tuple[str, int], _Route] = {}
    for row in rows:
        if row.get("event_type") != "intent_routing":
            continue
        payload = _mapping(row.get("payload"), "intent routing payload")
        for raw in _mapping_rows(payload.get("evaluations"), "evaluations"):
            if raw.get("strategy_id") != _CONTROL:
                continue
            evaluation = _evaluation(raw)
            _put_exact(
                evaluations, _evaluation_key(evaluation), evaluation, "evaluation"
            )
        _collect_routes(payload, routes)
    ordered = tuple(
        sorted(
            evaluations.values(),
            key=lambda value: (value.decision_time_ms, value.symbol),
        )
    )
    if not ordered:
        raise ValueError(f"run has no {_CONTROL} evaluations")
    return ordered, routes


def _collect_routes(
    payload: Mapping[str, object],
    routes: dict[tuple[str, int], _Route],
) -> None:
    for raw in _mapping_rows(payload.get("actions", []), "actions"):
        if raw.get("strategy_id") != _CONTROL or raw.get("action") != "enter":
            continue
        key = _route_key(raw)
        _put_exact(routes, key, _Route("routed_enter"), "route")
    for raw in _mapping_rows(payload.get("withheld", []), "withheld"):
        if raw.get("strategy_id") != _CONTROL:
            continue
        key = _route_key(raw)
        route = _Route("withheld", _required_text(raw.get("reason"), "withheld reason"))
        _put_exact(routes, key, route, "route")


def _evaluation(raw: Mapping[str, object]) -> _Evaluation:
    readiness = _mapping(raw.get("readiness"), "evaluation readiness")
    metrics = _mapping(readiness.get("metrics"), "evaluation metrics")
    breakout = _optional_side(metrics.get("breakout_side"), "breakout_side")
    structural = _optional_side(
        metrics.get("structural_direction"),
        "structural_direction",
    )
    relation = metrics.get("breakout_side_relation")
    if relation not in {"aligned", "opposed", "unavailable"}:
        relation = _relation(breakout, structural)
    return _Evaluation(
        symbol=_symbol(raw.get("symbol")),
        decision_time_ms=_nonnegative_int(
            raw.get("decision_time_ms"), "decision_time_ms"
        ),
        reference_price=_price(raw.get("reference_price"), "reference_price"),
        breakout_onset=_flag(metrics.get("breakout_onset"), "breakout_onset"),
        breakout_side=breakout,
        structural_side=structural,
        relation=relation,
        state_1m=_required_text(raw.get("state_1m"), "state_1m"),
        state_5m=_required_text(raw.get("state_5m"), "state_5m"),
        side=_optional_side(raw.get("side"), "side"),
    )


def _collect_series(
    rows: tuple[Mapping[str, object], ...],
) -> dict[str, _Series]:
    candles: dict[str, dict[int, _Candle]] = {}
    for row in rows:
        if row.get("event_type") != "market_candles":
            continue
        payload = _mapping(row.get("payload"), "market candles payload")
        if payload.get("timeframe") != "1m":
            continue
        raw_by_symbol = _mapping(payload.get("bars"), "market candle symbols")
        for raw_symbol, raw_bars in raw_by_symbol.items():
            symbol = _symbol(raw_symbol)
            output = candles.setdefault(symbol, {})
            for raw in _mapping_rows(raw_bars, f"{symbol} market candles"):
                candle = _candle(raw)
                _put_exact(output, candle.timestamp_ms, candle, f"{symbol} candle")
    return {
        symbol: _Series(tuple(sorted(values)), values)
        for symbol, values in candles.items()
    }


def _candle(raw: Mapping[str, object]) -> _Candle:
    candle = _Candle(
        timestamp_ms=_nonnegative_int(raw.get("timestamp_ms"), "candle timestamp_ms"),
        open_price=_price(raw.get("open"), "candle open"),
        high_price=_price(raw.get("high"), "candle high"),
        low_price=_price(raw.get("low"), "candle low"),
        close_price=_price(raw.get("close"), "candle close"),
    )
    if candle.low_price > min(candle.open_price, candle.close_price, candle.high_price):
        raise ValueError("candle low exceeds observed body")
    if candle.high_price < max(candle.open_price, candle.close_price, candle.low_price):
        raise ValueError("candle high is below observed body")
    return candle


def _replay(
    evaluations: tuple[_Evaluation, ...],
    routes: Mapping[tuple[str, int], _Route],
    series: Mapping[str, _Series],
    window_bars: int,
) -> list[_Onset]:
    policy = HypeBreakoutRetestPolicy(window_bars=window_bars)
    active: dict[str, _Onset] = {}
    onsets: list[_Onset] = []
    for evaluation in evaluations:
        bar, boundary = _policy_inputs(evaluation, series)
        prior = active.get(evaluation.symbol)
        result = policy.evaluate(
            symbol=evaluation.symbol,
            bar=bar,
            breakout_onset=evaluation.breakout_onset,
            breakout_boundary_price=boundary,
        )
        if prior is not None:
            _advance_onset(prior, evaluation, result, active)
        if evaluation.breakout_onset:
            onset = _start_onset(evaluation, routes, result, prior is not None)
            onsets.append(onset)
            if onset.disposition == "armed":
                active[evaluation.symbol] = onset
    return onsets


def _policy_inputs(
    evaluation: _Evaluation,
    series: Mapping[str, _Series],
) -> tuple[BreakoutRetestBar, float | None]:
    values = series.get(evaluation.symbol)
    if values is None:
        raise ValueError(f"market candles unavailable for {evaluation.symbol}")
    candle_time = evaluation.decision_time_ms - _MINUTE_MS
    candle = values.candles.get(candle_time)
    if candle is None:
        raise ValueError(
            f"completed candle unavailable for {evaluation.symbol} at {candle_time}"
        )
    boundary = _boundary(values, candle_time, evaluation.breakout_side)
    bar = BreakoutRetestBar(
        decision_time_ms=evaluation.decision_time_ms,
        open_price=candle.open_price,
        high_price=candle.high_price,
        low_price=candle.low_price,
        close_price=candle.close_price,
        state_5m=evaluation.state_5m,
        breakout_side=evaluation.breakout_side,
        structural_side=evaluation.structural_side,
    )
    return bar, boundary if evaluation.breakout_onset else None


def _boundary(series: _Series, candle_time: int, side: str | None) -> float | None:
    if side not in {"long", "short"}:
        return None
    position = bisect_left(series.times, candle_time)
    prior_times = series.times[max(0, position - _PRIOR_BARS) : position]
    if len(prior_times) < _PRIOR_BARS:
        return None
    values = [series.candles[timestamp] for timestamp in prior_times]
    if side == "long":
        return max(value.high_price for value in values)
    return min(value.low_price for value in values)


def _start_onset(
    evaluation: _Evaluation,
    routes: Mapping[tuple[str, int], _Route],
    result: BreakoutRetestResult,
    existing_pending: bool,
) -> _Onset:
    key = _evaluation_key(evaluation)
    route = routes.get(key, _Route("not_routed", "routing_record_absent"))
    if existing_pending:
        return _Onset(
            evaluation,
            route,
            None,
            disposition="existing_pending_retest_advanced",
        )
    disposition = "armed" if result.state == "armed" else "not_armed"
    onset = _Onset(evaluation, route, result, disposition=disposition)
    if result.state in _TERMINAL_STATES:
        onset.resolution_time_ms = evaluation.decision_time_ms
        onset.resolution_reference_price = evaluation.reference_price
        onset.resolution = result
    return onset


def _advance_onset(
    onset: _Onset,
    evaluation: _Evaluation,
    result: BreakoutRetestResult,
    active: dict[str, _Onset],
) -> None:
    onset.resolution_time_ms = evaluation.decision_time_ms
    onset.resolution_reference_price = evaluation.reference_price
    onset.resolution = result
    if result.state in _TERMINAL_STATES:
        active.pop(onset.evaluation.symbol, None)


def _summary(onsets: list[_Onset]) -> dict[str, int]:
    states = [_resolution_state(onset) for onset in onsets]
    return {
        "aligned_onsets": sum(
            value.evaluation.relation == "aligned" for value in onsets
        ),
        "control_onsets": len(onsets),
        "opposed_onsets": sum(
            value.evaluation.relation == "opposed" for value in onsets
        ),
        "retest_confirmed": states.count("confirmed"),
        "retest_expired": states.count("expired") + states.count("unavailable"),
        "retest_pending": sum(state not in _TERMINAL_STATES for state in states),
        "routed_entries": sum(value.route.status == "routed_enter" for value in onsets),
        "withheld_onsets": sum(value.route.status == "withheld" for value in onsets),
    }


def _onset_payload(onset: _Onset) -> dict[str, object]:
    evaluation = onset.evaluation
    return {
        "symbol": evaluation.symbol,
        "decision_time_ms": evaluation.decision_time_ms,
        "v1_reference_price": evaluation.reference_price,
        "v1_side": evaluation.side,
        "state_1m": evaluation.state_1m,
        "state_5m": evaluation.state_5m,
        "breakout_side": evaluation.breakout_side,
        "structural_side": evaluation.structural_side,
        "breakout_side_relation": evaluation.relation,
        "v1_route": onset.route.as_payload(),
        "retest_disposition": onset.disposition,
        "retest_onset": _result_payload(onset.onset_result),
        "retest_resolution": _resolution_payload(onset),
    }


def _result_payload(result: BreakoutRetestResult | None) -> dict[str, object]:
    if result is None:
        return {"state": "not_independently_armed"}
    return {
        "age_bars": result.age_bars,
        "boundary_price": result.boundary_price,
        "breakout_side": result.breakout_side,
        "eligible": result.eligible,
        "mode": result.mode,
        "reason": result.reason,
        "side": result.side,
        "state": result.state,
        "structural_side": result.structural_side,
    }


def _resolution_payload(onset: _Onset) -> dict[str, object]:
    result = onset.resolution
    if result is None:
        return {"state": "pending_at_snapshot"}
    return {
        "age_bars": result.age_bars,
        "decision_time_ms": onset.resolution_time_ms,
        "reason": result.reason,
        "reference_price": onset.resolution_reference_price,
        "side": result.side,
        "state": result.state,
    }


def _resolution_state(onset: _Onset) -> str:
    if onset.resolution is None:
        return "pending_at_snapshot"
    return onset.resolution.state


def _contract(window_bars: int) -> dict[str, object]:
    return {
        "challenger_strategy_id": _CHALLENGER,
        "classifier_recomputed": False,
        "control_strategy_id": _CONTROL,
        "execution_authority": "none",
        "immediate_onset_entry": False,
        "recorded_completed_bars_only": True,
        "report_only": True,
        "retest_window_bars": window_bars,
    }


def _limitations() -> list[str]:
    return [
        "replay establishes policy timing, not venue fill or realized PnL",
        "recorded v1 metrics are reused without recomputing the classifier",
        "open live outcomes remain unresolved and cannot establish edge",
        "the challenger has no execution, sizing, filtering, or promotion authority",
    ]


def _evaluation_key(value: _Evaluation) -> tuple[str, int]:
    return value.symbol, value.decision_time_ms


def _route_key(raw: Mapping[str, object]) -> tuple[str, int]:
    return (
        _symbol(raw.get("symbol")),
        _nonnegative_int(raw.get("decision_time_ms"), "route decision_time_ms"),
    )


def _relation(breakout: str | None, structural: str | None) -> str:
    if breakout is None or structural is None:
        return "unavailable"
    return "aligned" if breakout == structural else "opposed"


def _put_exact[K, V](output: dict[K, V], key: K, value: V, label: str) -> None:
    prior = output.get(key)
    if prior is not None and prior != value:
        raise ValueError(f"conflicting duplicate {label}: {key}")
    output[key] = value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _mapping_rows(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return tuple(_mapping(item, f"{label} item") for item in value)


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _symbol(value: object) -> str:
    return _required_text(value, "symbol").upper()


def _optional_side(value: object, label: str) -> str | None:
    if value is None:
        return None
    side = _required_text(value, label).lower()
    if side not in {"long", "short"}:
        raise ValueError(f"{label} must be long, short, or null")
    return side


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _flag(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _price(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be numeric")
    output = float(value)
    if not math.isfinite(output) or output <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return output
