"""Mechanism-compatible prior evidence for the V58 SP500 route."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import math
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence

Record = Mapping[str, object]

_HYPOTHESIS = "v51-sp500-fresh15-v3-live-lifecycle-v1"
_STRATEGY = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
_SYMBOL = "xyz:SP500"
_AUDIT_ROLE = (
    "immutable exact-profile audit resolving the first source-native v51 "
    "SP500 lifecycle"
)


def load_v58_sp500_source_history(
    journal_path: Path,
    expected_journal_sha256: str,
    *,
    current_decision_time_ms: int,
    current_side: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Load one prior normalized outcome without pooling profile-sized PnL."""
    journal, journal_evidence = _read_journal(journal_path, expected_journal_sha256)
    source_reference = _source_reference(journal)
    source_path = (journal_path.parent / _text(source_reference.get("path"))).resolve()
    source_evidence = _verify_source_audit(source_path, source_reference)
    lifecycle = _validated_lifecycle(journal)
    _require_nonoverlap(_prior_exit_time(journal), current_decision_time_ms)
    summary = _summary(lifecycle, current_side)
    if file_evidence(journal_path) != journal_evidence:
        raise ValueError("V58 SP500 source history journal changed during evaluation")
    return summary, {
        "journal": {"path": str(journal_path.resolve()), **journal_evidence},
        "source_audit": {"path": str(source_path), **source_evidence},
    }


def _read_journal(path: Path, expected_sha256: str) -> tuple[Record, dict[str, object]]:
    expected = _digest(expected_sha256, "history journal sha256")
    raw = path.read_bytes()
    evidence = {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
    if evidence["sha256"] != expected:
        raise ValueError("V58 SP500 source history journal identity is invalid")
    journal = _mapping(json.loads(raw), "SP500 source history journal")
    expected_fields = {
        "schema_version": 1,
        "hypothesis_id": _HYPOTHESIS,
        "revision_number": 2,
        "status": "retain",
        "symbol": _SYMBOL,
        "strategy_id": _STRATEGY,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    if any(journal.get(key) != value for key, value in expected_fields.items()):
        raise ValueError("V58 SP500 source history journal contract is invalid")
    _require_route_contract(journal)
    return journal, evidence


def _require_route_contract(journal: Record) -> None:
    contract = _mapping(journal.get("route_contract"), "SP500 route contract")
    expected = {
        "source_timeframe": "15m",
        "maximum_pressure_age_seconds": 15,
        "stop_bps": 80,
        "maximum_hold_seconds": 86_400,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 SP500 prior route contract is invalid")
    lock = _mapping(contract.get("profit_lock"), "SP500 profit lock")
    expected_lock = {
        "activation_bps": 100,
        "floor_bps": 40,
        "trailing_giveback_bps": 80,
    }
    if any(lock.get(key) != value for key, value in expected_lock.items()):
        raise ValueError("V58 SP500 prior profit-lock contract is invalid")


def _source_reference(journal: Record) -> Record:
    sources = _records(journal.get("evidence"), "SP500 source evidence")
    matches = [row for row in sources if row.get("role") == _AUDIT_ROLE]
    if len(matches) != 1:
        raise ValueError("V58 SP500 exact source audit is missing or duplicated")
    return matches[0]


def _verify_source_audit(path: Path, reference: Record) -> dict[str, object]:
    evidence = file_evidence(path)
    expected = {
        "bytes": _positive_integer(reference.get("bytes"), "source audit bytes"),
        "sha256": _digest(reference.get("sha256"), "source audit sha256"),
    }
    if evidence != expected:
        raise ValueError("V58 SP500 source audit identity is invalid")
    return evidence


def _validated_lifecycle(journal: Record) -> Record:
    metrics = _mapping(journal.get("metrics"), "SP500 source metrics")
    expected_metrics = {
        "eligible_signals": 1,
        "exact_long_lifecycles": 0,
        "exact_short_lifecycles": 1,
        "resolved_lifecycles": 1,
        "wins": 1,
        "losses": 0,
        "net_pnl_usd": 3.229665,
    }
    if any(
        not _equal(metrics.get(key), value) for key, value in expected_metrics.items()
    ):
        raise ValueError("V58 SP500 prior lifecycle metrics are invalid")
    lifecycle = _mapping(
        journal.get("resolved_short_lifecycle"), "SP500 resolved lifecycle"
    )
    expected = {"status": "resolved", "side": "short"}
    if any(lifecycle.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 SP500 prior lifecycle identity is invalid")
    _positive_number(lifecycle.get("entry_notional_usd"), "prior entry notional")
    _number(lifecycle.get("realized_net_return_bps"), "prior net return")
    if not _equal(lifecycle.get("net_pnl_usd"), metrics.get("net_pnl_usd")):
        raise ValueError("V58 SP500 prior lifecycle PnL does not reconcile")
    return lifecycle


def _prior_exit_time(journal: Record) -> int:
    scope = _mapping(journal.get("scope"), "SP500 source lifecycle scope")
    return _positive_integer(scope.get("exit_venue_time_ms"), "prior exit time")


def _require_nonoverlap(prior_exit: int, current_decision_time_ms: int) -> None:
    current_decision = _positive_integer(
        current_decision_time_ms, "current decision time"
    )
    if prior_exit >= current_decision:
        raise ValueError("V58 SP500 mechanism-compatible lifecycle windows overlap")


def _summary(lifecycle: Record, current_side: str) -> dict[str, object]:
    side = _side(current_side, "current side")
    sides = ("short", side)
    return {
        "scope": "same_provider_exit_mechanism_distinct_profile_sizing",
        "observed_lifecycles": 2,
        "resolved_lifecycles": 1,
        "technically_censored_lifecycles": 1,
        "long_lifecycles": sides.count("long"),
        "short_lifecycles": sides.count("short"),
        "both_sides_observed": set(sides) == {"long", "short"},
        "prior_resolved_net_return_bps": _number(
            lifecycle.get("realized_net_return_bps"), "prior net return"
        ),
        "prior_resolved_net_pnl_usd": _number(
            lifecycle.get("net_pnl_usd"), "prior net PnL"
        ),
        "pnl_aggregation_supported": False,
        "profile_sizing_contracts_are_identical": False,
        "strategy_change_supported": False,
    }


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list):
        raise ValueError(f"V58 {label} must be an array")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 {label} must be an object")
    return value


def _side(value: object, label: str) -> str:
    side = _text(value, label)
    if side not in {"long", "short"}:
        raise ValueError(f"V58 {label} must be long or short")
    return side


def _text(value: object, label: str = "text") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"V58 {label} must be non-empty text")
    return value.strip()


def _digest(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"V58 {label} must be lowercase sha256")
    return text


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 {label} must be a positive integer")
    return value


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0:
        raise ValueError(f"V58 {label} must be positive")
    return number


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 {label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"V58 {label} must be finite")
    return number


def _equal(actual: object, expected: object) -> bool:
    if isinstance(expected, float):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and math.isclose(float(actual), expected, rel_tol=1e-9, abs_tol=1e-9)
        )
    return actual == expected
