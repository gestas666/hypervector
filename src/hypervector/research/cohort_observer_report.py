"""Assembly helpers for observer audit reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_canonical_regime_telemetry import (
    build_canonical_regime_telemetry_summary,
)
from hypervector.research.cohort_strategy_scorecard import build_strategy_scorecard

Record = Mapping[str, object]
Pair = tuple[str, str]


def observer_audit_payload(
    selected: Sequence[Record],
    run: Mapping[str, object],
    runtime: Mapping[str, object],
    technical: Mapping[str, object],
    signals: Mapping[str, object],
    readiness: Mapping[str, object],
    signal_outcomes: Mapping[str, object],
    regime_accuracy: Mapping[str, object],
    expected: frozenset[Pair],
) -> dict[str, object]:
    """Assemble one report-only observer audit payload."""
    providers = _mapping(readiness.get("by_provider_symbol"), "readiness providers")
    return {
        "schema_version": 3,
        "mode": "multi_asset_bidirectional_observer_audit",
        "observer_contract": observer_contract(),
        "run": dict(run),
        "runtime": dict(runtime),
        "technical": dict(technical),
        "signals": dict(signals),
        "readiness": dict(readiness),
        "canonical_regime_telemetry": build_canonical_regime_telemetry_summary(
            selected
        ),
        "signal_outcomes": dict(signal_outcomes),
        "regime_forward_accuracy": dict(regime_accuracy),
        "strategy_scorecard": build_strategy_scorecard(
            expected, providers, signal_outcomes
        ),
        "learning": learning_summary(),
        "limitations": limitations(),
    }


def observer_contract() -> dict[str, object]:
    """Return the fixed observer-only authority contract."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "orders_observed": False,
        "fills_observed": False,
        "profitability_measured": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
    }


def learning_summary() -> dict[str, object]:
    """Return the fixed interpretation boundary for observer evidence."""
    return {
        "evidence_state": "setup_and_signal_paths_only_no_execution_outcomes",
        "signal_path_descriptives_identifiable": True,
        "strategy_edge_identifiable": False,
        "profitability_identifiable": False,
        "execution_quality_identifiable": False,
        "valid_uses": [
            "technical_parity",
            "signal_cadence",
            "setup_progression",
            "blocker_attribution",
        ],
    }


def limitations() -> list[str]:
    """Return immutable limitations for observer evidence."""
    return [
        "No orders, fills, fees, funding, slippage, markout, or realized PnL were observed.",
        "Forward candle paths are counterfactual signal diagnostics, not execution outcomes.",
        "Readiness is prerequisite completion, not win probability or expected return.",
        "This audit cannot promote, filter, size, pause, or retune a strategy.",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value
