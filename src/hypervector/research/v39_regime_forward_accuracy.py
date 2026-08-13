"""Causal forward diagnostics for exact v39 canonical regime observations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import math
from statistics import mean, median

from hypervector.research.v39_forward_evidence_contract import (
    PROFILE_FINGERPRINT,
    PROFILE_ID,
)

Record = Mapping[str, object]

_SYMBOLS = frozenset(("BTC", "ETH", "SOL", "HYPE"))
_STATE_FIELDS = ("primary_regime", "state_1m", "state_5m", "context_15m")
_STATES = frozenset(
    ("TREND_UP", "TREND_DOWN", "RANGE", "BREAKOUT", "TRANSITION", "UNKNOWN")
)
_REGIME_STRATEGY = "canonical_regime_telemetry_v1"
_REGIME_CONTRACT = {
    "configured_route": False,
    "execution_authority": "none",
    "intents_emitted": False,
}


@dataclass(frozen=True)
class _Observation:
    symbol: str
    decision_time_ms: int
    reference_price: float
    states: tuple[str, str, str, str]


@dataclass(frozen=True)
class _Resolved:
    observation: _Observation
    forward_return_bps: float


def build_v39_regime_forward_accuracy(
    rows: Sequence[Record],
    *,
    run_id: str,
    horizons_minutes: Sequence[int] = (5, 15, 30, 60),
    range_thresholds_bps: Sequence[float] = (10.0, 25.0, 50.0),
) -> dict[str, object]:
    """Score exact later observations without imputing unresolved horizons."""
    run = _text(run_id, "v39 regime run id")
    horizons = _positive_unique_ints(horizons_minutes, "regime horizons")
    thresholds = _positive_unique_numbers(
        range_thresholds_bps, "range movement thresholds"
    )
    selected = [row for row in rows if row.get("run_id") == run]
    _require_runtime_identity(selected)
    observations, event_count, duplicate_count = _observations(selected)
    episodes, left_censored_count = _episode_onsets(observations)
    return {
        "schema_version": "v39_canonical_regime_forward_accuracy_v4",
        "mode": "exact_v39_canonical_regime_forward_diagnostic",
        "contract": _contract(),
        "source": _source(
            run,
            observations,
            event_count,
            duplicate_count,
            left_censored_count,
        ),
        "horizons": {
            f"{horizon}m": _horizon_report(
                observations,
                episodes,
                horizon,
                thresholds,
            )
            for horizon in horizons
        },
        "interpretation": _interpretation(),
        "limitations": _limitations(),
    }


def _require_runtime_identity(rows: Sequence[Record]) -> None:
    identities = [
        row for row in rows if row.get("event_type") == "configuration_identity"
    ]
    if not identities:
        raise ValueError("v39 regime evidence lacks runtime identity")
    for row in identities:
        payload = _mapping(row.get("payload"), "v39 runtime identity")
        valid = (
            row.get("live_armed") is True
            and row.get("execution_mode") == "live"
            and row.get("profile_id") == PROFILE_ID
            and row.get("profile_fingerprint") == PROFILE_FINGERPRINT
            and payload.get("profile_fingerprint") == PROFILE_FINGERPRINT
        )
        if not valid:
            raise ValueError(
                "regime evidence does not match exact v39 runtime identity"
            )


def _observations(
    rows: Sequence[Record],
) -> tuple[tuple[_Observation, ...], int, int]:
    indexed: dict[tuple[str, int], _Observation] = {}
    event_count = 0
    duplicates = 0
    for row in rows:
        if row.get("event_type") != "canonical_regime_evaluations":
            continue
        event_count += 1
        payload = _mapping(row.get("payload"), "canonical regime event")
        if payload.get("contract") != _REGIME_CONTRACT:
            raise ValueError("canonical regime event contract is invalid")
        received_ms = _timestamp_ms(row.get("observed_at_utc"))
        values = _records(payload.get("evaluations"), "canonical evaluations")
        if {
            _text(value.get("symbol"), "canonical symbol") for value in values
        } != _SYMBOLS:
            raise ValueError("canonical regime event symbol coverage is incomplete")
        for value in values:
            observation = _observation(value, received_ms)
            key = (observation.symbol, observation.decision_time_ms)
            prior = indexed.get(key)
            if prior is not None and prior != observation:
                raise ValueError("conflicting canonical regime duplicate")
            duplicates += prior is not None
            indexed[key] = observation
    if not indexed:
        raise ValueError("v39 run has no canonical regime observations")
    return (
        tuple(sorted(indexed.values(), key=_observation_key)),
        event_count,
        duplicates,
    )


def _observation(value: Record, received_ms: int) -> _Observation:
    symbol = _text(value.get("symbol"), "canonical symbol")
    decision_ms = _nonnegative_int(value.get("decision_time_ms"), "decision time")
    if decision_ms > received_ms:
        raise ValueError("future canonical regime evidence")
    valid = (
        symbol in _SYMBOLS
        and value.get("strategy_id") == _REGIME_STRATEGY
        and value.get("decision_action") == "regime_observation"
        and value.get("backend_non_action_reason")
        == "telemetry_only_no_execution_authority"
    )
    if not valid:
        raise ValueError("canonical regime observation contract is invalid")
    states = tuple(_state(value.get(field), field) for field in _STATE_FIELDS)
    return _Observation(
        symbol=symbol,
        decision_time_ms=decision_ms,
        reference_price=_positive_number(
            value.get("reference_price"), "reference price"
        ),
        states=states,  # type: ignore[arg-type]
    )


def _horizon_report(
    observations: Sequence[_Observation],
    episodes: frozenset[tuple[str, int, str]],
    horizon_minutes: int,
    thresholds: Sequence[float],
) -> dict[str, object]:
    resolved, coverage = _resolve_horizon(observations, horizon_minutes)
    return {
        "horizon_minutes": horizon_minutes,
        "coverage": coverage,
        "state_fields": {
            field: _field_report(resolved, episodes, field, thresholds)
            for field in _STATE_FIELDS
        },
    }


def _resolve_horizon(
    observations: Sequence[_Observation], horizon_minutes: int
) -> tuple[tuple[_Resolved, ...], dict[str, int]]:
    lookup = {(row.symbol, row.decision_time_ms): row for row in observations}
    maxima = _maximum_times(observations)
    delta_ms = horizon_minutes * 60_000
    resolved: list[_Resolved] = []
    missing = tail = 0
    for row in observations:
        target_ms = row.decision_time_ms + delta_ms
        future = lookup.get((row.symbol, target_ms))
        if future is None:
            tail += target_ms > maxima[row.symbol]
            missing += target_ms <= maxima[row.symbol]
            continue
        value = (future.reference_price / row.reference_price - 1.0) * 10_000.0
        resolved.append(_Resolved(row, value))
    coverage = {
        "candidate_observations": len(observations),
        "resolved_observations": len(resolved),
        "unresolved_tail_observations": tail,
        "missing_exact_future_observations": missing,
    }
    return tuple(resolved), coverage


def _field_report(
    rows: Sequence[_Resolved],
    episodes: frozenset[tuple[str, int, str]],
    field: str,
    thresholds: Sequence[float],
) -> dict[str, object]:
    index = _STATE_FIELDS.index(field)
    pooled = _group_metrics(rows, index, thresholds)
    onset_rows = [
        row
        for row in rows
        if (row.observation.symbol, row.observation.decision_time_ms, field) in episodes
    ]
    by_symbol = {
        symbol: _group_metrics(
            [row for row in rows if row.observation.symbol == symbol],
            index,
            thresholds,
        )
        for symbol in sorted(_SYMBOLS)
    }
    return {
        "pooled": pooled,
        "by_symbol": by_symbol,
        "episode_onsets": _group_metrics(onset_rows, index, thresholds),
        "episode_onset_clusters": _episode_cluster_metrics(
            onset_rows, index, thresholds
        ),
        "episode_onsets_by_symbol": {
            symbol: _group_metrics(
                [row for row in onset_rows if row.observation.symbol == symbol],
                index,
                thresholds,
            )
            for symbol in sorted(_SYMBOLS)
        },
    }


def _episode_cluster_metrics(
    rows: Sequence[_Resolved], index: int, thresholds: Sequence[float]
) -> dict[str, object]:
    clusters: dict[tuple[int, str], list[float]] = defaultdict(list)
    asset_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        state = row.observation.states[index]
        key = (row.observation.decision_time_ms, state)
        clusters[key].append(row.forward_return_bps)
        asset_counts[state] += 1
    grouped: dict[str, list[float]] = defaultdict(list)
    for (_, state), values in clusters.items():
        grouped[state].append(mean(values))
    output: dict[str, object] = {}
    for state, values in sorted(grouped.items()):
        metrics = _metrics(state, values, thresholds)
        metrics["asset_observations"] = asset_counts[state]
        output[state] = metrics
    return output


def _group_metrics(
    rows: Sequence[_Resolved], index: int, thresholds: Sequence[float]
) -> dict[str, object]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row.observation.states[index]].append(row.forward_return_bps)
    return {
        state: _metrics(state, values, thresholds)
        for state, values in sorted(grouped.items())
    }


def _metrics(
    state: str, values: Sequence[float], thresholds: Sequence[float]
) -> dict[str, object]:
    absolute = [abs(value) for value in values]
    directional = _directional_accuracy(state, values)
    return {
        "observations": len(values),
        "mean_forward_return_bps": mean(values),
        "median_forward_return_bps": median(values),
        "mean_absolute_return_bps": mean(absolute),
        "median_absolute_return_bps": median(absolute),
        "directional_accuracy_pct": directional,
        "quiet_rate_by_threshold_pct": {
            _threshold_key(threshold): _percentage(
                sum(value < threshold for value in absolute), len(absolute)
            )
            for threshold in thresholds
        },
    }


def _directional_accuracy(state: str, values: Sequence[float]) -> float | None:
    if state == "TREND_UP":
        return _percentage(sum(value > 0.0 for value in values), len(values))
    if state == "TREND_DOWN":
        return _percentage(sum(value < 0.0 for value in values), len(values))
    return None


def _episode_onsets(
    observations: Sequence[_Observation],
) -> tuple[frozenset[tuple[str, int, str]], int]:
    prior: dict[tuple[str, str], str] = {}
    onsets: set[tuple[str, int, str]] = set()
    left_censored = 0
    for row in observations:
        for index, field in enumerate(_STATE_FIELDS):
            key = (row.symbol, field)
            state = row.states[index]
            if key not in prior:
                left_censored += 1
            elif prior[key] != state:
                onsets.add((row.symbol, row.decision_time_ms, field))
            prior[key] = state
    return frozenset(onsets), left_censored


def _source(
    run_id: str,
    observations: Sequence[_Observation],
    event_count: int,
    duplicate_count: int,
    left_censored_count: int,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "profile_id": PROFILE_ID,
        "profile_fingerprint": PROFILE_FINGERPRINT,
        "symbols": sorted(_SYMBOLS),
        "canonical_events": event_count,
        "unique_observations": len(observations),
        "identical_duplicates_dropped": duplicate_count,
        "left_censored_initial_state_series": left_censored_count,
        "first_decision_time_ms": min(row.decision_time_ms for row in observations),
        "last_decision_time_ms": max(row.decision_time_ms for row in observations),
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "performance_gate": False,
        "automatic_retuning": False,
        "unresolved_horizon_policy": "exclude_without_imputation",
        "future_price_policy": "exact_later_canonical_observation_only",
    }


def _interpretation() -> dict[str, object]:
    return {
        "directional_states": ["TREND_UP", "TREND_DOWN"],
        "nondirectional_states": ["RANGE", "BREAKOUT", "TRANSITION", "UNKNOWN"],
        "range_measure": "absolute_forward_move_below_explicit_threshold",
        "episode_onsets": "observed_state_change_after_prior_in_run",
        "episode_clusters": "equal_weight_assets_by_decision_time_and_state",
    }


def _limitations() -> list[str]:
    return [
        "overlapping observations are autocorrelated and are descriptive only",
        "initial state per symbol and field is left-censored and excluded from episode onsets",
        "episode onsets reduce repetition but are not statistically independent trials",
        "per-symbol episode samples can be too small for stable inference",
        "simultaneous asset onsets are summarized as dependent market clusters",
        "reference prices are canonical completed-bar observations, not executable fills",
        "BREAKOUT lacks a direction field and is reported as nondirectional movement",
        "the live prefix can identify defects but cannot establish stable route edge",
    ]


def _maximum_times(observations: Sequence[_Observation]) -> dict[str, int]:
    output: dict[str, int] = {}
    for row in observations:
        output[row.symbol] = max(output.get(row.symbol, 0), row.decision_time_ms)
    return output


def _observation_key(row: _Observation) -> tuple[int, str]:
    return row.decision_time_ms, row.symbol


def _positive_unique_ints(values: Sequence[int], label: str) -> tuple[int, ...]:
    parsed = tuple(values)
    if not parsed or any(isinstance(value, bool) or value <= 0 for value in parsed):
        raise ValueError(f"{label} must contain positive integers")
    if len(set(parsed)) != len(parsed):
        raise ValueError(f"{label} must be unique")
    return tuple(sorted(parsed))


def _positive_unique_numbers(values: Sequence[float], label: str) -> tuple[float, ...]:
    parsed = tuple(float(value) for value in values if not isinstance(value, bool))
    valid = len(parsed) == len(values) and all(
        math.isfinite(value) and value > 0 for value in parsed
    )
    if not valid or len(set(parsed)) != len(parsed):
        raise ValueError(f"{label} must contain unique positive finite numbers")
    return tuple(sorted(parsed))


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return list(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _state(value: object, label: str) -> str:
    state = _text(value, label)
    if state not in _STATES:
        raise ValueError(f"{label} is not a canonical regime state")
    return state


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return parsed


def _timestamp_ms(value: object) -> int:
    raw = _text(value, "canonical observation time").replace("Z", "+00:00")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("canonical observation time must include a timezone")
    return int(parsed.timestamp() * 1_000)


def _percentage(count: int, total: int) -> float:
    return 100.0 * count / total


def _threshold_key(value: float) -> str:
    return f"{value:g}bps"
