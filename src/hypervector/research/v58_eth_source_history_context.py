"""Source-bound cumulative evidence for the exact V58 ETH route."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
import math
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence

Record = Mapping[str, object]

_HYPOTHESIS = "eth-breakout-precompression-pullback"
_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_CANDIDATE = f"{_STRATEGY}_v55_forward"
_SYMBOL = "ETH"


def load_v58_eth_source_history(
    journal_path: Path,
    expected_journal_sha256: str,
    *,
    current_contract: Record,
    current_lifecycles: Sequence[tuple[Record, str]],
) -> tuple[dict[str, object], dict[str, object]]:
    """Load one prior exact lifecycle and combine it with the current lane."""
    journal, journal_evidence = _read_pinned_journal(
        journal_path, expected_journal_sha256
    )
    source_reference = _source_reference(journal)
    artifact_path = Path(_text(source_reference.get("path"), "source artifact path"))
    artifact, artifact_evidence = _read_source_artifact(artifact_path, source_reference)
    prior = _validated_prior_lifecycle(journal, artifact)
    _require_distinct_current(prior, current_contract, current_lifecycles)
    summary = _combined_summary(prior, current_lifecycles)
    if file_evidence(journal_path) != journal_evidence:
        raise ValueError("V58 ETH source history journal changed during evaluation")
    return summary, {
        "journal": {"path": str(journal_path.resolve()), **journal_evidence},
        "artifact": {"path": str(artifact_path.resolve()), **artifact_evidence},
    }


def _read_pinned_journal(
    path: Path, expected_sha256: str
) -> tuple[Record, dict[str, object]]:
    expected = _digest(expected_sha256, "history journal sha256")
    raw = path.read_bytes()
    evidence = {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
    if evidence["sha256"] != expected:
        raise ValueError("V58 ETH source history journal identity is invalid")
    journal = _mapping(json.loads(raw), "ETH source history journal")
    expected_fields = {
        "schema_version": 1,
        "hypothesis_id": _HYPOTHESIS,
        "revision_number": 14,
        "status": "first_exact_eligible_lifecycle_adverse",
        "symbol": _SYMBOL,
        "strategy_id": _STRATEGY,
    }
    if any(journal.get(field) != value for field, value in expected_fields.items()):
        raise ValueError("V58 ETH source history journal contract is invalid")
    _require_journal_authority(journal)
    return journal, evidence


def _require_journal_authority(journal: Record) -> None:
    contract = _mapping(journal.get("contract"), "ETH history journal authority")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "actual_order_or_fill_claimed": False,
    }
    if any(contract.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH source history journal authority is invalid")


def _source_reference(journal: Record) -> Record:
    references = _records(journal.get("source_evidence"), "ETH source references")
    matches = [
        row
        for row in references
        if Path(_text(row.get("path"), "source artifact path")).name
        == "eth_pullback_eligible_exact_depth_20260818T1108Z_v2.json"
    ]
    if len(matches) != 1:
        raise ValueError("V58 ETH source artifact reference is missing or duplicated")
    return matches[0]


def _read_source_artifact(
    path: Path, reference: Record
) -> tuple[Record, dict[str, object]]:
    raw = path.read_bytes()
    evidence = {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
    expected = {
        "bytes": _positive_integer(reference.get("bytes"), "source artifact bytes"),
        "sha256": _digest(reference.get("sha256"), "source artifact sha256"),
    }
    if evidence != expected:
        raise ValueError("V58 ETH source artifact identity is invalid")
    artifact = _mapping(json.loads(raw), "ETH source lifecycle artifact")
    if file_evidence(path) != evidence:
        raise ValueError("V58 ETH source artifact changed during evaluation")
    return artifact, evidence


def _validated_prior_lifecycle(journal: Record, artifact: Record) -> Record:
    _require_artifact_contract(journal, artifact)
    summary = _mapping(artifact.get("summary"), "ETH source lifecycle summary")
    counts = {"pending": 0, "resolved": 1, "technical_incomplete": 0}
    if any(summary.get(field) != value for field, value in counts.items()):
        raise ValueError("V58 ETH source lifecycle counts are invalid")
    executions = _records(
        artifact.get("latest_executions"), "ETH source lifecycle executions"
    )
    if len(executions) != 1:
        raise ValueError("V58 ETH source lifecycle execution is missing")
    lifecycle = executions[0]
    _require_prior_economics(lifecycle)
    _require_journal_reconciliation(journal, lifecycle)
    return lifecycle


def _require_artifact_contract(journal: Record, artifact: Record) -> None:
    expected = {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
        "state": "descriptive_exact_depth_evidence",
    }
    if any(artifact.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH source lifecycle artifact contract is invalid")
    frozen = _mapping(journal.get("frozen_identity"), "ETH frozen identity")
    contract = _mapping(artifact.get("contract"), "ETH source artifact contract")
    expected_contract = {
        "report_only": True,
        "execution_authority": "none",
        "actual_orders_or_fills_claimed": False,
        "portfolio_pnl_claimed": False,
        "source_strategy_id": _STRATEGY,
        "candidate_strategy_id": _CANDIDATE,
        "symbol": _SYMBOL,
        "source_run_id": frozen.get("run_id"),
        "profile_fingerprint": frozen.get("profile_fingerprint"),
        "compatible_run_ids": [frozen.get("run_id")],
        "stop_bps": 60.0,
        "notional_usd": 750.0,
        "maximum_hold_minutes": 720,
        "taker_fee_rate": 0.00045,
    }
    if any(
        not _equal(contract.get(key), value) for key, value in expected_contract.items()
    ):
        raise ValueError("V58 ETH source lifecycle artifact identity is invalid")


def _require_prior_economics(lifecycle: Record) -> None:
    expected = {
        "status": "resolved",
        "strategy_id": _STRATEGY,
        "candidate_strategy_id": _CANDIDATE,
        "symbol": _SYMBOL,
        "side": "long",
        "exit_reason": "protective_stop",
        "net_return_scope": "exact_depth_fee_and_funding",
    }
    if any(lifecycle.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH source lifecycle identity is invalid")
    gross = _number(lifecycle.get("gross_return_bps"), "prior gross return")
    fee = _number(lifecycle.get("fee_bps"), "prior fee")
    funding = _number(lifecycle.get("funding_bps"), "prior funding")
    net = _number(lifecycle.get("net_return_bps"), "prior net return")
    pnl = _number(lifecycle.get("simulated_net_pnl_usd"), "prior net PnL")
    if not _equal(net, gross - fee + funding):
        raise ValueError("V58 ETH source lifecycle economics do not reconcile")
    if not _equal(pnl, 750.0 * net / 10_000.0):
        raise ValueError("V58 ETH source lifecycle PnL does not reconcile")


def _require_journal_reconciliation(journal: Record, lifecycle: Record) -> None:
    frozen = _mapping(journal.get("frozen_identity"), "ETH frozen identity")
    expected_identity = {
        "run_id": lifecycle.get("source_run_id"),
        "side": lifecycle.get("side"),
        "notional_usd": 750.0,
        "stop_bps": 60.0,
        "maximum_hold_seconds": 43_200,
        "taker_fee_rate": 0.00045,
    }
    if any(
        not _equal(frozen.get(field), value)
        for field, value in expected_identity.items()
    ):
        raise ValueError("V58 ETH source journal identity does not reconcile")
    journal_lifecycle = _mapping(
        journal.get("exact_forward_lifecycle"), "ETH journal lifecycle"
    )
    fields = (
        "entry_time_ms",
        "entry_price",
        "exit_time_ms",
        "exit_price",
        "exit_reason",
        "gross_return_bps",
        "fee_bps",
        "funding_bps",
        "net_return_bps",
        "simulated_net_pnl_usd",
    )
    if any(
        not _equal(journal_lifecycle.get(field), lifecycle.get(field))
        for field in fields
    ):
        raise ValueError("V58 ETH source journal lifecycle does not reconcile")


def _require_distinct_current(
    prior: Record,
    current_contract: Record,
    current_lifecycles: Sequence[tuple[Record, str]],
) -> None:
    current_run = _text(current_contract.get("source_run_id"), "current source run")
    prior_run = _text(prior.get("source_run_id"), "prior source run")
    if current_run == prior_run:
        raise ValueError("V58 ETH cumulative evidence requires distinct observer runs")
    if not current_lifecycles:
        return
    decisions = tuple(
        _positive_integer(row.get("decision_time_ms"), "current decision time")
        for row, _state in current_lifecycles
    )
    prior_exit = _positive_integer(prior.get("exit_time_ms"), "prior exit time")
    if len(decisions) != len(set(decisions)) or prior_exit >= min(decisions):
        raise ValueError("V58 ETH cumulative lifecycle windows overlap")


def _combined_summary(
    prior: Record, current_lifecycles: Sequence[tuple[Record, str]]
) -> dict[str, object]:
    states = tuple(state for _row, state in current_lifecycles)
    if any(state not in {"open", "resolved", "censored"} for state in states):
        raise ValueError("V58 ETH current lifecycle state is invalid")
    sides = (
        _text(prior.get("side"), "prior side"),
        *(_text(row.get("side"), "current side") for row, _state in current_lifecycles),
    )
    realized_net = _number(prior.get("net_return_bps"), "prior net return")
    realized_pnl = _number(prior.get("simulated_net_pnl_usd"), "prior net PnL")
    for current, state in current_lifecycles:
        if state == "resolved":
            net, pnl = _resolved_current_economics(current)
            realized_net += net
            realized_pnl += pnl
    return {
        "scope": "exact_route_source_compatible_distinct_runs",
        "observed_lifecycles": 1 + len(current_lifecycles),
        "resolved_lifecycles": 1 + states.count("resolved"),
        "pending_lifecycles": states.count("open"),
        "technical_incomplete": states.count("censored"),
        "long_lifecycles": sides.count("long"),
        "short_lifecycles": sides.count("short"),
        "both_sides_observed": set(sides) == {"long", "short"},
        "realized_net_return_bps": realized_net,
        "realized_net_pnl_usd": realized_pnl,
        "pending_excluded_from_realized_totals": "open" in states,
        "censored_excluded_from_realized_totals": "censored" in states,
        "strategy_change_supported": False,
    }


def _resolved_current_economics(lifecycle: Record) -> tuple[float, float]:
    gross = _number(lifecycle.get("gross_return_bps"), "current gross return")
    fee = _number(lifecycle.get("fee_bps"), "current fee")
    funding = _number(lifecycle.get("funding_bps"), "current funding")
    net = _number(lifecycle.get("net_return_bps"), "current net return")
    pnl = _number(lifecycle.get("simulated_net_pnl_usd"), "current PnL")
    notional = _number(lifecycle.get("entry_notional_usd"), "current notional")
    if not _equal(net, gross - fee + funding):
        raise ValueError("V58 ETH current lifecycle economics do not reconcile")
    if not _equal(pnl, notional * net / 10_000.0):
        raise ValueError("V58 ETH current lifecycle PnL does not reconcile")
    return net, pnl


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _digest(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be lowercase sha256")
    return text


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _equal(actual: object, expected: object) -> bool:
    if isinstance(expected, float):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and math.isclose(float(actual), expected, rel_tol=1e-9, abs_tol=1e-9)
        )
    return actual == expected
