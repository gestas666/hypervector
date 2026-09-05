"""Attach immutable V58 ETH duration evidence to the continuous report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from math import isclose, isfinite
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence


Record = Mapping[str, object]

_ROUTE = "eth_breakout_precompression_pullback_bidirectional_v1|ETH"
_STRATEGY = _ROUTE.split("|", 1)[0]
_EXIT_REASONS = {"maximum_hold", "protective_stop", "opposite_strategy_intent"}


def attach_v58_eth_duration_evidence(report: dict[str, object], path: Path) -> None:
    """Attach one safe duration checkpoint or an explicit unavailable state."""
    if not path.is_file():
        report["eth_duration_checkpoint_context"] = _unavailable_payload()
        return
    before = file_evidence(path)
    payload = _mapping(json.loads(path.read_bytes()), "duration checkpoint")
    context = _duration_payload(payload)
    if file_evidence(path) != before:
        raise ValueError("V58 ETH duration checkpoint changed during analysis")
    report["eth_duration_checkpoint_context"] = context
    _attach_to_eth_ledger(report, context)
    evidence = _mutable_mapping(report.get("evidence"), "report evidence")
    evidence["eth_duration_checkpoint_context"] = {
        "path": str(path.resolve()),
        **before,
    }


def _unavailable_payload() -> dict[str, object]:
    return {
        "status": "not_available",
        "reason": "duration_checkpoint_not_published",
        "execution_authority": "none",
        "strategy_change_supported": False,
    }


def _duration_payload(payload: Record) -> dict[str, object]:
    expected = {
        "schema_version": 1,
        "mode": "v58_eth_fixed_entry_duration_checkpoint_v1",
        "execution_authority": "none",
        "historical_optimum_claim": False,
        "strategy_change_supported": False,
    }
    if any(payload.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH duration authority or contract is invalid")
    source = _mapping(payload.get("source_lifecycle"), "duration source lifecycle")
    _require_source(source)
    checkpoints = _mapping(payload.get("duration_checkpoints"), "duration checkpoints")
    fixed_240 = _checkpoint(checkpoints, "fixed_240m", 240)
    fixed_480 = _checkpoint(checkpoints, "fixed_480m", 480)
    retained = _retained_control(payload)
    return {
        "status": "captured",
        "source_lifecycle": dict(source),
        "fixed_240m": fixed_240,
        "fixed_480m": fixed_480,
        "fixed_240m_minus_480m_usd": (
            fixed_240["simulated_net_pnl_usd"] - fixed_480["simulated_net_pnl_usd"]
        ),
        "fixed_240m_minus_480m_bps": (
            fixed_240["net_return_bps"] - fixed_480["net_return_bps"]
        ),
        "retained_control": retained,
        "interpretation": "single_open_path_duration_diagnostic",
        "execution_authority": "none",
        "strategy_change_supported": False,
    }


def _require_source(source: Record) -> None:
    required = {
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
    }
    if any(source.get(field) != value for field, value in required.items()):
        raise ValueError("V58 ETH duration source identity is invalid")
    if source.get("side") not in {"long", "short"}:
        raise ValueError("V58 ETH duration source side is invalid")
    _text(source.get("source_run_id"), "duration source run")
    _positive_int(source.get("decision_time_ms"), "duration decision time")
    _positive_int(source.get("entry_time_ms"), "duration entry time")


def _checkpoint(checkpoints: Record, key: str, minutes: int) -> dict[str, object]:
    row = _mapping(checkpoints.get(key), f"{key} checkpoint")
    if row.get("status") != "resolved" or row.get("exit_reason") not in _EXIT_REASONS:
        raise ValueError(f"V58 ETH {key} checkpoint is unresolved")
    if row.get("maximum_hold_minutes") != minutes:
        raise ValueError(f"V58 ETH {key} duration is inconsistent")
    if row.get("net_return_scope") != "exact_depth_fee_and_funding":
        raise ValueError(f"V58 ETH {key} cost scope is incomplete")
    notional = _positive_number(row.get("entry_notional_usd"), f"{key} notional")
    net_bps = _number(row.get("net_return_bps"), f"{key} net return")
    net_pnl = _number(row.get("simulated_net_pnl_usd"), f"{key} net pnl")
    if not isclose(net_pnl, notional * net_bps / 10_000.0, abs_tol=1e-9):
        raise ValueError(f"V58 ETH {key} economics are inconsistent")
    return {
        field: row.get(field)
        for field in (
            "status",
            "exit_reason",
            "maximum_hold_minutes",
            "exit_time_ms",
            "exit_price",
            "entry_notional_usd",
            "gross_return_bps",
            "fee_bps",
            "funding_bps",
            "net_return_bps",
            "simulated_net_pnl_usd",
            "net_return_scope",
        )
        if field in row
    }


def _retained_control(payload: Record) -> dict[str, object]:
    retained = _mapping(payload.get("retained_control"), "retained control")
    snapshot = _mapping(payload.get("retained_control_snapshot"), "control snapshot")
    if retained.get("maximum_hold_minutes") != 720:
        raise ValueError("V58 ETH retained control duration is invalid")
    expected = {
        "status": "exit_pending",
        "actual_exit_fill_claim": False,
        "net_return_scope": "exact_depth_fee_and_funding",
    }
    if any(snapshot.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH retained control snapshot is invalid")
    return {**dict(retained), "actual_exit_fill_claim": False}


def _attach_to_eth_ledger(
    report: dict[str, object], context: dict[str, object]
) -> None:
    ledger = _sequence(report.get("hypothesis_ledger"), "hypothesis ledger")
    matches = [row for row in ledger if row.get("route") == _ROUTE]
    if len(matches) != 1 or not isinstance(matches[0], dict):
        raise ValueError("V58 ETH duration hypothesis identity is invalid")
    matches[0]["duration_checkpoint_status"] = "captured_single_open_path"
    matches[0]["duration_checkpoint_evidence"] = context


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _mutable_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be mutable mapping")
    return value


def _sequence(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"{label} rows must be mappings")
    return tuple(row for row in value if isinstance(row, Mapping))


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{label} must be finite numeric")
    return result


def _positive_number(value: object, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result
