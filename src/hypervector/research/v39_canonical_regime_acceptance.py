"""Fail-closed v39 acceptance for canonical regime telemetry."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import math

from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
    LEGACY_CANONICAL_REGIME_STRATEGY,
    canonical_regime_symbols,
)
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.live.sol_range_onset_decision_source import (
    CANONICAL_COMPONENT_CATEGORICAL_FIELDS,
    CANONICAL_COMPONENT_METRIC_FIELDS,
    CANONICAL_REGIME_BOOLEAN_METRIC_FIELDS,
    CANONICAL_REGIME_METRIC_FIELDS,
    CANONICAL_REGIME_TEXT_METRIC_FIELDS,
)
from hypervector.research.cohort_canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_CONTRACT,
)

Record = Mapping[str, object]

_SYMBOLS = frozenset(("BTC", "ETH", "SOL", "HYPE"))
_STATES = frozenset(
    ("TREND_UP", "TREND_DOWN", "RANGE", "BREAKOUT", "TRANSITION", "UNKNOWN")
)
_BASE_METRICS = (
    "raw_long_cross",
    "raw_short_cross",
    "regime_admitted",
    "sma_fast",
    "sma_gap_bps",
    "sma_slow",
    "structural_direction",
)
_PROVENANCE_METRICS = {
    "component_authority": "observe_only",
    "component_provenance": "causal_completed_1m_v1",
    "component_weight_mode": "unweighted_observe_v1",
}
_MTF_BIAS_FIELDS = frozenset(("mtf_5m_bias", "mtf_15m_bias"))
_REQUIRED_METRICS = (
    *_BASE_METRICS,
    *CANONICAL_REGIME_METRIC_FIELDS,
    *_PROVENANCE_METRICS,
    *CANONICAL_COMPONENT_METRIC_FIELDS,
)


def independent_regime_symbols(config: MultiAssetLiveConfig) -> frozenset[str]:
    """Return core symbols not already covered by executable Range telemetry."""
    supported = frozenset(canonical_regime_symbols(config.symbols))
    legacy = frozenset(
        symbol
        for provider in config.providers
        if provider.strategy_id == LEGACY_CANONICAL_REGIME_STRATEGY
        for symbol in provider.execution_symbols
    )
    return supported.difference(legacy)


def build_canonical_regime_check(
    checkpoint: Record,
    audit: Record,
    *,
    maximum_age_seconds: float,
    expected_symbols: frozenset[str] = _SYMBOLS,
) -> dict[str, object]:
    """Require fresh, causal, complete telemetry-only rows for four symbols."""
    raw = audit.get("canonical_regime_telemetry")
    if not isinstance(raw, Mapping):
        return _check(["canonical_regime_telemetry_missing"], symbols=0)
    generated = _timestamp(checkpoint.get("generated_at_utc"))
    reasons = _summary_reasons(raw)
    by_symbol = raw.get("by_symbol")
    if not isinstance(by_symbol, Mapping):
        reasons.append("canonical_regime_symbol_coverage_mismatch")
        return _check(reasons, symbols=0)
    if set(by_symbol) != expected_symbols:
        reasons.append("canonical_regime_symbol_coverage_mismatch")
    for symbol in sorted(expected_symbols.intersection(by_symbol)):
        reasons.extend(
            _symbol_reasons(
                symbol,
                by_symbol[symbol],
                generated,
                maximum_age_seconds,
            )
        )
    reasons.extend(_count_reasons(raw, by_symbol))
    return _check(
        reasons, symbols=len(by_symbol), maximum_age_seconds=maximum_age_seconds
    )


def _summary_reasons(summary: Record) -> list[str]:
    valid = (
        summary.get("schema_version") == 1
        and summary.get("strategy_id") == CANONICAL_REGIME_TELEMETRY_STRATEGY
        and summary.get("contract") == CANONICAL_REGIME_TELEMETRY_CONTRACT
    )
    return [] if valid else ["canonical_regime_contract_invalid"]


def _symbol_reasons(
    symbol: str,
    raw: object,
    generated: datetime,
    maximum_age: float,
) -> list[str]:
    if not isinstance(raw, Mapping):
        return [f"canonical_regime_fields_incomplete:{symbol}"]
    observed = _optional_timestamp(raw.get("latest_observed_at_utc"))
    latest = raw.get("latest")
    if observed is None or not isinstance(latest, Mapping):
        return [f"canonical_regime_fields_incomplete:{symbol}"]
    reasons = _evaluation_reasons(symbol, latest)
    decision_time = _integer(latest.get("decision_time_ms"))
    decision_age = (
        None if decision_time is None else generated.timestamp() - decision_time / 1_000
    )
    if observed > generated or (
        decision_time is not None and decision_time > int(observed.timestamp() * 1_000)
    ):
        reasons.append(f"canonical_regime_future_evidence:{symbol}")
    elif (generated - observed).total_seconds() > maximum_age or (
        decision_age is not None and decision_age > maximum_age
    ):
        reasons.append(f"canonical_regime_stale:{symbol}")
    return reasons


def _evaluation_reasons(symbol: str, evaluation: Record) -> list[str]:
    contract_valid = (
        evaluation.get("strategy_id") == CANONICAL_REGIME_TELEMETRY_STRATEGY
        and evaluation.get("symbol") == symbol
        and evaluation.get("eligible") is False
        and evaluation.get("side") is None
        and evaluation.get("decision_action") == "regime_observation"
        and evaluation.get("reason") == "canonical_regime_observation"
        and evaluation.get("backend_non_action_reason")
        == "telemetry_only_no_execution_authority"
    )
    if not contract_valid:
        return ["canonical_regime_contract_invalid"]
    states = tuple(evaluation.get(name) for name in _state_fields())
    confidence = _fraction(evaluation.get("confidence"))
    readiness = evaluation.get("readiness")
    complete = (
        _integer(evaluation.get("decision_time_ms")) is not None
        and confidence is not None
        and all(state in _STATES for state in states)
        and isinstance(readiness, Mapping)
        and _metrics_complete(readiness.get("metrics"))
    )
    if not complete:
        return [f"canonical_regime_fields_incomplete:{symbol}"]
    return [f"canonical_regime_unavailable:{symbol}"] if "UNKNOWN" in states else []


def _metrics_complete(raw: object) -> bool:
    if not isinstance(raw, Mapping):
        return False
    if any(raw.get(name) is None for name in _REQUIRED_METRICS):
        return False
    provenance = all(
        raw.get(name) == value for name, value in _PROVENANCE_METRICS.items()
    )
    return provenance and _metric_types_valid(raw)


def _metric_types_valid(metrics: Record) -> bool:
    base_valid = (
        all(isinstance(metrics.get(name), bool) for name in _BASE_METRICS[:3])
        and all(_finite(metrics.get(name)) for name in _BASE_METRICS[3:6])
        and metrics.get("structural_direction") in {"long", "short", "neutral"}
    )
    regimes_valid = all(
        isinstance(metrics.get(name), str)
        if name in CANONICAL_REGIME_TEXT_METRIC_FIELDS
        else isinstance(metrics.get(name), bool)
        if name in CANONICAL_REGIME_BOOLEAN_METRIC_FIELDS
        else _finite(metrics.get(name))
        for name in CANONICAL_REGIME_METRIC_FIELDS
    )
    components_valid = all(
        _component_category_valid(name, metrics.get(name))
        if name in CANONICAL_COMPONENT_CATEGORICAL_FIELDS
        else _finite(metrics.get(name))
        for name in CANONICAL_COMPONENT_METRIC_FIELDS
    )
    return base_valid and regimes_valid and components_valid


def _count_reasons(summary: Record, by_symbol: Mapping[object, object]) -> list[str]:
    counts = [
        _integer(value.get("evaluations"))
        for value in by_symbol.values()
        if isinstance(value, Mapping)
    ]
    valid = (
        len(counts) == len(by_symbol)
        and all(value is not None and value > 0 for value in counts)
        and _integer(summary.get("symbols")) == len(by_symbol)
        and _integer(summary.get("evaluations")) == sum(value or 0 for value in counts)
    )
    return [] if valid else ["canonical_regime_evaluation_count_mismatch"]


def _state_fields() -> tuple[str, ...]:
    return ("primary_regime", "state_1m", "state_5m", "context_15m")


def _integer(value: object) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else None
    )


def _fraction(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) and 0.0 <= parsed <= 1.0 else None


def _finite(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _direction_code(value: object) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool) and value in {-1, 0, 1}
    )


def _component_category_valid(name: str, value: object) -> bool:
    """Validate direction codes and the distinct three-vote MTF bias sums."""
    if name not in _MTF_BIAS_FIELDS:
        return _direction_code(value)
    return isinstance(value, int) and not isinstance(value, bool) and -3 <= value <= 3


def _timestamp(value: object) -> datetime:
    parsed = _optional_timestamp(value)
    if parsed is None:
        raise ValueError("checkpoint generation must be RFC3339")
    return parsed


def _optional_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _check(reasons: list[str], **evidence: object) -> dict[str, object]:
    return {"passed": not reasons, "reasons": reasons, **evidence}
