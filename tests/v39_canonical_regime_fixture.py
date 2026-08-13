"""Complete telemetry-only canonical regime fixture for v39 tests."""

from __future__ import annotations

from datetime import datetime

from hypervector.live.sol_range_onset_decision_source import (
    CANONICAL_COMPONENT_CATEGORICAL_FIELDS,
    CANONICAL_COMPONENT_METRIC_FIELDS,
    CANONICAL_REGIME_BOOLEAN_METRIC_FIELDS,
    CANONICAL_REGIME_METRIC_FIELDS,
    CANONICAL_REGIME_TEXT_METRIC_FIELDS,
)


def canonical_regime_summary(observed: datetime) -> dict[str, object]:
    """Return four fresh, complete canonical telemetry rows."""
    decision_time_ms = int(observed.timestamp() * 1_000)
    return {
        "schema_version": 1,
        "strategy_id": "canonical_regime_telemetry_v1",
        "contract": {
            "execution_authority": "none",
            "intents_emitted": False,
            "configured_route": False,
        },
        "evaluations": 4,
        "symbols": 4,
        "by_symbol": {
            symbol: {
                "evaluations": 1,
                "latest_observed_at_utc": observed.isoformat(),
                "latest": _evaluation(symbol, decision_time_ms),
            }
            for symbol in ("BTC", "ETH", "SOL", "HYPE")
        },
    }


def _evaluation(symbol: str, decision_time_ms: int) -> dict[str, object]:
    return {
        "strategy_id": "canonical_regime_telemetry_v1",
        "symbol": symbol,
        "decision_time_ms": decision_time_ms,
        "reference_price": 100.0,
        "decision_action": "regime_observation",
        "eligible": False,
        "reason": "canonical_regime_observation",
        "side": None,
        "primary_regime": "RANGE",
        "state_1m": "RANGE",
        "state_5m": "RANGE",
        "context_15m": "RANGE",
        "confidence": 0.5,
        "backend_non_action_reason": "telemetry_only_no_execution_authority",
        "readiness": {
            "side": None,
            "conditions_met": 2,
            "conditions_required": 3,
            "readiness_fraction": 2 / 3,
            "blockers": ["awaiting_hourly_sma_cross"],
            "indicators": ["5m RANGE"],
            "metrics": _metrics(),
        },
    }


def _metrics() -> dict[str, object]:
    metrics: dict[str, object] = {
        "raw_long_cross": False,
        "raw_short_cross": False,
        "regime_admitted": True,
        "sma_fast": 101.0,
        "sma_gap_bps": 1.0,
        "sma_slow": 100.0,
        "structural_direction": "neutral",
        "component_authority": "observe_only",
        "component_provenance": "causal_completed_1m_v1",
        "component_weight_mode": "unweighted_observe_v1",
    }
    metrics.update(
        {name: _regime_metric(name) for name in CANONICAL_REGIME_METRIC_FIELDS}
    )
    metrics.update(
        {
            name: -1 if name in CANONICAL_COMPONENT_CATEGORICAL_FIELDS else 1.0
            for name in CANONICAL_COMPONENT_METRIC_FIELDS
        }
    )
    return metrics


def _regime_metric(name: str) -> object:
    if name in CANONICAL_REGIME_TEXT_METRIC_FIELDS:
        return "fixture"
    if name in CANONICAL_REGIME_BOOLEAN_METRIC_FIELDS:
        return False
    return 1.0
