"""Canonical multi-timeframe regime context for the V58 research lane."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from hypervector.research.v58_observer_technical_state import (
    require_reportable_v58_observer_status,
)

Record = Mapping[str, object]

_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_STRATEGY_ID = "canonical_regime_telemetry_v1"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")


@dataclass(frozen=True)
class RegimeContext:
    """One symbol's causal diagnostic state and setup readiness."""

    symbol: str
    evaluations: int
    observed_at_utc: str
    primary_regime: str
    context_15m: str
    state_1m: str
    state_5m: str
    confidence: float
    readiness_side: str
    readiness_fraction: float
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class RegimeContextCollection:
    """Validated four-symbol context and exact observer checkpoint bytes."""

    contexts: tuple[RegimeContext, ...]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_regime_context(
    path: Path, *, observer_status: Record
) -> RegimeContextCollection:
    """Load exact canonical telemetry without granting routing authority."""
    _require_observer(observer_status)
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), "V58 observer checkpoint")
    audit = _mapping(payload.get("audit"), "V58 observer audit")
    _require_run(_mapping(audit.get("run"), "V58 observer run"), observer_status)
    canonical = _mapping(
        audit.get("canonical_regime_telemetry"), "canonical regime telemetry"
    )
    _require_canonical_contract(canonical)
    rows = _mapping(canonical.get("by_symbol"), "canonical symbol contexts")
    if set(rows) != set(_SYMBOLS):
        raise ValueError("canonical regime symbol set is incomplete or aliased")
    contexts = tuple(_context(symbol, rows[symbol]) for symbol in _SYMBOLS)
    if canonical.get("evaluations") != sum(row.evaluations for row in contexts):
        raise ValueError("canonical regime evaluation count is inconsistent")
    evidence = {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    return RegimeContextCollection(contexts, evidence)


def regime_context_payload(
    collection: RegimeContextCollection,
) -> list[dict[str, object]]:
    """Serialize context while labeling its diagnostic-only authority."""
    return [
        {
            "symbol": row.symbol,
            "evaluations": row.evaluations,
            "observed_at_utc": row.observed_at_utc,
            "primary_regime": row.primary_regime,
            "context_15m": row.context_15m,
            "state_1m": row.state_1m,
            "state_5m": row.state_5m,
            "confidence": row.confidence,
            "readiness_side": row.readiness_side,
            "readiness_fraction": row.readiness_fraction,
            "blockers": list(row.blockers),
            "entry_gate": False,
            "edge_claim": False,
            "execution_authority": "none",
        }
        for row in collection.contexts
    ]


def _require_observer(status: Record) -> None:
    expected = {
        "profile_id": _PROFILE_ID,
        "freshness_status": "fresh",
        "provider_symbol_routes": 10,
        "routed_actions": 0,
        "report_only": True,
        "execution_authority": "none",
    }
    if any(status.get(field) != value for field, value in expected.items()):
        raise ValueError("canonical regime observer identity is invalid")
    require_reportable_v58_observer_status(status, "canonical regime observer")


def _require_run(run: Record, observer: Record) -> None:
    expected = {
        "profile_id": observer.get("profile_id"),
        "profile_fingerprint": observer.get("profile_fingerprint"),
        "run_id": observer.get("run_id"),
    }
    if any(run.get(field) != value for field, value in expected.items()):
        raise ValueError("canonical regime observer run identity is invalid")


def _require_canonical_contract(canonical: Record) -> None:
    expected = {
        "schema_version": 1,
        "strategy_id": _STRATEGY_ID,
        "symbols": 4,
    }
    if any(canonical.get(field) != value for field, value in expected.items()):
        raise ValueError("canonical regime source contract is invalid")
    contract = _mapping(canonical.get("contract"), "canonical regime contract")
    safe = {
        "execution_authority": "none",
        "intents_emitted": False,
        "configured_route": False,
    }
    if any(contract.get(field) != value for field, value in safe.items()):
        raise ValueError("canonical regime contract is invalid")


def _context(symbol: str, value: object) -> RegimeContext:
    record = _mapping(value, f"{symbol} canonical context")
    evaluations = _positive_integer(record.get("evaluations"), f"{symbol} evaluations")
    latest = _mapping(record.get("latest"), f"{symbol} latest context")
    _require_evaluation_contract(symbol, latest)
    readiness = _mapping(latest.get("readiness"), f"{symbol} readiness")
    blockers = _text_tuple(readiness.get("blockers"), f"{symbol} blockers")
    return RegimeContext(
        symbol=symbol,
        evaluations=evaluations,
        observed_at_utc=_text(record.get("latest_observed_at_utc"), "observation"),
        primary_regime=_text(latest.get("primary_regime"), "primary regime"),
        context_15m=_text(latest.get("context_15m"), "15m context"),
        state_1m=_text(latest.get("state_1m"), "1m state"),
        state_5m=_text(latest.get("state_5m"), "5m state"),
        confidence=_fraction(latest.get("confidence"), f"{symbol} confidence"),
        readiness_side=_side(readiness.get("side"), symbol),
        readiness_fraction=_fraction(
            readiness.get("readiness_fraction"), f"{symbol} readiness"
        ),
        blockers=blockers,
    )


def _require_evaluation_contract(symbol: str, latest: Record) -> None:
    expected = {
        "symbol": symbol,
        "strategy_id": _STRATEGY_ID,
        "decision_action": "regime_observation",
        "eligible": False,
        "backend_non_action_reason": "telemetry_only_no_execution_authority",
    }
    if any(latest.get(field) != value for field, value in expected.items()):
        raise ValueError(f"{symbol} canonical evaluation contract is invalid")


def _fraction(value: object, label: str) -> float:
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid or not isfinite(value) or not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{label} must be within zero and one")
    return float(value)


def _side(value: object, symbol: str) -> str:
    if value not in {"long", "short"}:
        raise ValueError(f"{symbol} canonical readiness side is invalid")
    return str(value)


def _text_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return tuple(_text(item, label) for item in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value
