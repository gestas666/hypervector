"""Report-only projection of canonical regime telemetry ledger rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from types import MappingProxyType

from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
)
from hypervector.research.cohort_live_audit_values import (
    event_rows,
    mapping,
    mapping_list,
    nonnegative_int,
    payload,
    text,
    timestamp,
)

Record = Mapping[str, object]
ObservedEvaluation = tuple[datetime, Record]

CANONICAL_REGIME_TELEMETRY_CONTRACT: Mapping[str, object] = MappingProxyType(
    {
        "execution_authority": "none",
        "intents_emitted": False,
        "configured_route": False,
    }
)


def build_canonical_regime_telemetry_summary(
    records: Sequence[Record],
) -> dict[str, object]:
    """Summarize causal telemetry-only rows without creating route authority."""
    grouped: dict[str, list[ObservedEvaluation]] = {}
    identities: set[tuple[str, int]] = set()
    for row in event_rows(records, "canonical_regime_evaluations"):
        observed = timestamp(row)
        values = _event_evaluations(row)
        _require_ordered(values)
        for evaluation in values:
            symbol, decision_time = _identity(evaluation)
            identity = (symbol, decision_time)
            if identity in identities:
                raise ValueError("duplicate canonical regime evaluation identity")
            identities.add(identity)
            if decision_time > int(observed.timestamp() * 1_000):
                raise ValueError("canonical regime decision follows observation")
            grouped.setdefault(symbol, []).append((observed, evaluation))
    by_symbol = {
        symbol: _symbol_summary(values) for symbol, values in sorted(grouped.items())
    }
    return {
        "schema_version": 1,
        "strategy_id": CANONICAL_REGIME_TELEMETRY_STRATEGY,
        "contract": dict(CANONICAL_REGIME_TELEMETRY_CONTRACT),
        "evaluations": len(identities),
        "symbols": len(by_symbol),
        "by_symbol": by_symbol,
    }


def _event_evaluations(row: Record) -> list[Record]:
    values = payload(row)
    if mapping(values.get("contract"), "canonical regime contract") != (
        CANONICAL_REGIME_TELEMETRY_CONTRACT
    ):
        raise ValueError("canonical regime telemetry contract is invalid")
    return mapping_list(values.get("evaluations"), "canonical regime evaluations")


def _require_ordered(evaluations: Sequence[Record]) -> None:
    times = [
        nonnegative_int(value.get("decision_time_ms"), "canonical decision time")
        for value in evaluations
    ]
    if times != sorted(times):
        raise ValueError("canonical regime evaluations are unordered")


def _identity(evaluation: Record) -> tuple[str, int]:
    strategy = text(evaluation.get("strategy_id"), "canonical regime strategy")
    symbol = text(evaluation.get("symbol"), "canonical regime symbol")
    telemetry_only = (
        strategy == CANONICAL_REGIME_TELEMETRY_STRATEGY
        and evaluation.get("eligible") is False
        and evaluation.get("side") is None
        and evaluation.get("decision_action") == "regime_observation"
        and evaluation.get("reason") == "canonical_regime_observation"
        and evaluation.get("backend_non_action_reason")
        == "telemetry_only_no_execution_authority"
    )
    if not telemetry_only:
        raise ValueError("canonical regime evaluation is not telemetry-only")
    decision_time = nonnegative_int(
        evaluation.get("decision_time_ms"), "canonical decision time"
    )
    return symbol, decision_time


def _symbol_summary(values: Sequence[ObservedEvaluation]) -> dict[str, object]:
    observed, latest = max(
        values,
        key=lambda item: (
            nonnegative_int(item[1].get("decision_time_ms"), "canonical decision time"),
            item[0],
        ),
    )
    return {
        "evaluations": len(values),
        "latest_observed_at_utc": observed.isoformat(),
        "latest": dict(latest),
    }
