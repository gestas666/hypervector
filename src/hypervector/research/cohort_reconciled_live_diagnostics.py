"""Orchestrate live diagnostics against durable research decisions."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.research.cohort_live_opportunity_diagnostics import (
    build_live_opportunity_diagnostics,
)

Record = Mapping[str, object]


def build_reconciled_live_diagnostics(
    audit: Record, research_decision_overrides: object
) -> dict[str, object]:
    """Build live diagnostics and honor explicit closed-path dispositions."""
    required = ("readiness", "signal_outcomes", "strategy_scorecard")
    missing = [field for field in required if audit.get(field) is None]
    if missing:
        return _unavailable(missing)
    decisions: object = []
    if research_decision_overrides is not None:
        overrides = _mapping(research_decision_overrides, "research decision overrides")
        decisions = overrides.get("hypothesis_decisions", [])
    return build_live_opportunity_diagnostics(audit, hypothesis_decisions=decisions)


def _unavailable(missing: list[str]) -> dict[str, object]:
    return {
        "status": "unavailable_missing_legacy_sources",
        "missing_sources": missing,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
        },
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value
