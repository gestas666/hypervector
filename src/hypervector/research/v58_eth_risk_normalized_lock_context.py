"""Report-only R-normalized exit-policy context for exact V58 ETH."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isclose
from pathlib import Path

from hypervector.research.v58_eth_risk_lock_evidence import minimum_evidence
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.v58_eth_historical_disposition import (
    load_historical_disposition,
)

Record = Mapping[str, object]
Payload = dict[str, object]

_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_FINGERPRINT = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_ROUTE = f"{_STRATEGY}|ETH"
_MODE = "cohort_risk_normalized_profit_lock_mechanism_v1"
_ORIGIN = "post_hoc_large_winner_giveback_hypothesis_20260813"
_POLICIES = {
    "r2_floor1_trail1": (2.0, 1.0, 1.0),
    "r5_floor2_trail2": (5.0, 2.0, 2.0),
}


@dataclass(frozen=True)
class EthRiskNormalizedLockContext:
    """Exact current-run ETH exit-policy evidence without execution authority."""

    payload: dict[str, object]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_eth_risk_normalized_lock_context(
    checkpoint_path: Path,
    historical_disposition_path: Path | None = None,
) -> EthRiskNormalizedLockContext:
    """Load one exact V58 ETH policy state from an atomic checkpoint."""
    raw = checkpoint_path.read_bytes()
    reference = {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
    checkpoint = _mapping(json.loads(raw), "V58 checkpoint")
    run_id = _runtime_identity(checkpoint)
    mechanism = _mechanism(checkpoint)
    history = _history(mechanism)
    state, lifecycle = _current_lifecycle(checkpoint, mechanism, run_id)
    limitations = _texts(mechanism.get("limitations"), "policy limitations")
    payload = _payload(state, lifecycle, history, limitations)
    evidence = {"checkpoint": {"path": str(checkpoint_path.resolve()), **reference}}
    if historical_disposition_path is not None:
        disposition, disposition_evidence = load_historical_disposition(
            historical_disposition_path,
            strategy_id=_STRATEGY,
        )
        payload["historical_disposition"] = disposition
        evidence.update(disposition_evidence)
    if file_evidence(checkpoint_path) != reference:
        raise ValueError("V58 checkpoint changed during ETH exit-policy evaluation")
    return EthRiskNormalizedLockContext(payload, evidence)


def eth_risk_normalized_lock_context_payload(
    context: EthRiskNormalizedLockContext,
) -> dict[str, object]:
    """Serialize the exact policy comparison with no live-change authority."""
    minimum = minimum_evidence(context.payload.get("lifecycle_state"))
    return {
        **context.payload,
        "execution_authority": context.execution_authority,
        "report_only": True,
        "performance_gate": False,
        "automatic_strategy_change": False,
        "strategy_change_supported": False,
        "minimum_additional_evidence": minimum,
        "interpretation": _interpretation(context.payload),
    }


def _interpretation(payload: Record) -> str:
    if payload.get("lifecycle_state") == "not_observed_current_run":
        return (
            "no ETH lifecycle has been observed in the current run; historical "
            "policy evidence remains descriptive and cannot establish an exit replacement"
        )
    side = _text(payload.get("side"), "ETH lifecycle side")
    if payload.get("lifecycle_state") == "open":
        return (
            f"the policy family predates this entry, but this is one unresolved {side} "
            "lifecycle and cannot establish an exit replacement"
        )
    return (
        f"the policy family predates this entry; this resolved {side} lifecycle "
        "updates diagnostics but cannot establish an exit replacement"
    )


def _runtime_identity(checkpoint: Record) -> str:
    lifecycle = _mapping(checkpoint.get("lifecycle"), "V58 lifecycle")
    if lifecycle.get("state") != "running_consistent":
        raise ValueError("V58 runtime is not running consistently")
    audit = _mapping(checkpoint.get("audit"), "V58 audit")
    run = _mapping(audit.get("run"), "V58 run")
    expected = {"profile_id": _PROFILE, "profile_fingerprint": _FINGERPRINT}
    if any(run.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 runtime identity is invalid")
    routes = _texts(run.get("executable_provider_symbols"), "V58 routes")
    if _ROUTE not in routes:
        raise ValueError("V58 ETH route is not executable in the active profile")
    return _text(run.get("run_id"), "V58 run id")


def _mechanism(checkpoint: Record) -> Record:
    audit = _mapping(checkpoint.get("audit"), "V58 audit")
    root = _mapping(audit.get("profit_lock_challenger"), "profit-lock audit")
    mechanism = _mapping(
        root.get("risk_normalized_all_time_live_mechanism"),
        "risk-normalized mechanism",
    )
    expected = {
        "schema_version": 1,
        "mode": _MODE,
        "scope": "all_live_history_normalized_mechanism",
        "policy_origin": _ORIGIN,
    }
    if any(mechanism.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH risk-normalized mechanism identity is invalid")
    _require_policy_contracts(mechanism.get("policies"))
    return mechanism


def _require_policy_contracts(value: object) -> None:
    rows = _records(value, "risk-normalized policy contracts")
    contracts = {
        _text(row.get("policy_id"), "policy id"): (
            _number(row.get("activation_r"), "activation R"),
            _number(row.get("floor_r"), "floor R"),
            _number(row.get("peak_giveback_r"), "giveback R"),
        )
        for row in rows
    }
    if contracts != _POLICIES:
        raise ValueError("V58 ETH risk-normalized policy contract changed")


def _history(mechanism: Record) -> dict[str, object]:
    routes = _mapping(mechanism.get("by_provider_symbol"), "policy route history")
    route = _mapping(routes.get(_ROUTE), "ETH policy history")
    summaries = _mapping(route.get("summary_by_policy"), "ETH policy summaries")
    if set(summaries) != set(_POLICIES):
        raise ValueError("V58 ETH policy history is incomplete")
    rows = {key: _mapping(summaries[key], f"{key} summary") for key in _POLICIES}
    counts = {
        _nonnegative(row.get("lifecycles"), "ETH lifecycles") for row in rows.values()
    }
    if len(counts) != 1:
        raise ValueError("V58 ETH policy lifecycle counts disagree")
    return {
        "lifecycles": counts.pop(),
        "triggered": {
            key: _nonnegative(row.get("triggered"), f"{key} triggered")
            for key, row in rows.items()
        },
        "summary_by_policy": {key: dict(row) for key, row in rows.items()},
    }


def _current_lifecycle(
    checkpoint: Record, mechanism: Record, run_id: str
) -> tuple[str, Record]:
    audit = _mapping(checkpoint.get("audit"), "V58 audit")
    open_root = _mapping(audit.get("open_trade_reflections"), "open trades")
    open_rows = _matching(_records(open_root.get("trades"), "open trades"), run_id)
    if len(open_rows) > 1:
        raise ValueError("V58 current run has duplicate ETH lifecycles")
    if open_rows:
        return "open", _open_lifecycle(open_rows[0])
    results = _records(mechanism.get("latest_results"), "closed policy results")
    closed = _matching(results, run_id)
    if not closed:
        return "not_observed_current_run", {}
    latest = max(
        closed, key=lambda row: _nonnegative(row.get("exit_timestamp_ms"), "exit")
    )
    return "closed", _closed_lifecycle(latest, checkpoint, run_id)


def _matching(rows: Sequence[Record], run_id: str) -> tuple[Record, ...]:
    return tuple(
        row
        for row in rows
        if row.get("source_run_id") == run_id
        and row.get("strategy_id") == _STRATEGY
        and row.get("symbol") == "ETH"
    )


def _open_lifecycle(row: Record) -> dict[str, object]:
    challenger = _mapping(
        row.get("open_risk_normalized_profit_lock_challenger"), "open challenger"
    )
    expected = {
        "schema_version": 2,
        "mode": "cohort_open_risk_normalized_profit_lock_challenger_v1",
        "policy_origin": _ORIGIN,
    }
    if any(challenger.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 open ETH policy identity is invalid")
    contract = _mapping(challenger.get("contract"), "open policy contract")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("V58 open ETH policy has execution authority")
    policies = _policy_results(challenger.get("policies"))
    return _lifecycle_identity(row, policies)


def _closed_lifecycle(row: Record, checkpoint: Record, run_id: str) -> Payload:
    output = _lifecycle_identity(row, _policy_results(row.get("policies")))
    actual_net = _number(row.get("actual_net_pnl_usd"), "actual net PnL")
    output["actual_net_pnl_usd"] = actual_net
    output["actual_close_reconciliation"] = _actual_close_reconciliation(
        checkpoint,
        run_id,
        _text(row.get("lifecycle_id"), "ETH lifecycle id"),
        actual_net,
    )
    return output


def _actual_close_reconciliation(
    checkpoint: Record, run_id: str, lifecycle_id: str, policy_net: float
) -> dict[str, object]:
    audit = _mapping(checkpoint.get("audit"), "V58 audit")
    root = _mapping(audit.get("trade_reflections"), "closed trade reflections")
    matches = tuple(
        row
        for row in _matching(_records(root.get("trades"), "closed trades"), run_id)
        if row.get("lifecycle_id") == lifecycle_id
    )
    if len(matches) != 1:
        raise ValueError("V58 ETH close must have one exact reflected lifecycle")
    trade = matches[0]
    _require_closed_trade_identity(trade, lifecycle_id, policy_net)
    stop = dict(_mapping(trade.get("protective_stop"), "ETH protective stop"))
    holding = _nonnegative(trade.get("holding_time_ms"), "ETH holding time")
    return {
        "lifecycle_id": lifecycle_id,
        "source_run_id": run_id,
        "source_profile_fingerprint": _FINGERPRINT,
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
        "side": trade["side"],
        "entry": dict(_mapping(trade.get("entry"), "ETH close entry")),
        "exit": dict(_mapping(trade.get("exit"), "ETH close exit")),
        "protective_stop": stop,
        "exit_reason": _text(trade.get("exit_reason"), "ETH exit reason"),
        "holding_time_ms": holding,
        **_closed_trade_economics(trade),
        "ledger": _flat_eth_ledger(audit),
        "ledger_flat_order_free": True,
    }


def _require_closed_trade_identity(
    trade: Record, lifecycle_id: str, policy_net: float
) -> None:
    expected = {
        "lifecycle_id": lifecycle_id,
        "source_profile_fingerprint": _FINGERPRINT,
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
    }
    if any(trade.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 ETH reflected close identity is invalid")
    if trade.get("side") not in {"long", "short"}:
        raise ValueError("V58 ETH reflected close side is invalid")
    reflected_net = _number(trade.get("net_pnl_usd"), "ETH reflected net PnL")
    if not isclose(reflected_net, policy_net, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("V58 ETH policy and reflected net PnL disagree")


def _closed_trade_economics(trade: Record) -> dict[str, object]:
    entry = _trade_leg(trade.get("entry"), "ETH close entry")
    exit_leg = _trade_leg(trade.get("exit"), "ETH close exit")
    net = _number(trade.get("net_pnl_usd"), "ETH net PnL")
    fees = _number(trade.get("fees_usd"), "ETH fees")
    funding = _number(trade.get("funding_usd"), "ETH funding")
    direction = 1.0 if trade.get("side") == "long" else -1.0
    price_gross = direction * (exit_leg["price"] - entry["price"]) * entry["size"]
    accounting_gross = net + fees - funding
    if not isclose(price_gross, accounting_gross, rel_tol=1e-9, abs_tol=1e-8):
        raise ValueError("V58 ETH close price and cash accounting disagree")
    return {
        "gross_market_pnl_usd": accounting_gross,
        "fees_usd": fees,
        "funding_usd": funding,
        "net_pnl_usd": net,
        "accounting_reconciled": True,
    }


def _trade_leg(value: object, label: str) -> dict[str, float]:
    leg = _mapping(value, label)
    price = _number(leg.get("price"), f"{label} price")
    size = _number(leg.get("size"), f"{label} size")
    if price <= 0.0 or size <= 0.0:
        raise ValueError(f"{label} price and size must be positive")
    _nonnegative(leg.get("venue_timestamp_ms"), f"{label} timestamp")
    _number(leg.get("slippage_bps"), f"{label} slippage")
    return {"price": price, "size": size}


def _flat_eth_ledger(audit: Record) -> dict[str, object]:
    health = _mapping(audit.get("health"), "V58 health")
    assets = _mapping(health.get("assets"), "V58 asset health")
    eth = _mapping(assets.get("ETH"), "V58 ETH health")
    size = _number(eth.get("position_size_signed"), "ETH position size")
    orders = eth.get("open_order_ids")
    if (
        eth.get("final_state") != "FLAT"
        or not isclose(size, 0.0, abs_tol=1e-12)
        or orders != []
        or eth.get("protected_if_open") is not True
    ):
        raise ValueError("V58 ETH close is not flat and order-free in the ledger")
    return {
        "final_state": "FLAT",
        "position_size_signed": size,
        "open_order_ids": [],
        "protected_if_open": True,
    }


def _lifecycle_identity(row: Record, policies: Record) -> dict[str, object]:
    side = _text(row.get("side"), "ETH lifecycle side")
    if side not in {"long", "short"}:
        raise ValueError("V58 ETH lifecycle side is invalid")
    return {
        "lifecycle_id": _text(row.get("lifecycle_id"), "ETH lifecycle id"),
        "side": side,
        "policies": dict(policies),
    }


def _policy_results(value: object) -> Record:
    policies = _mapping(value, "ETH policy results")
    if set(policies) != set(_POLICIES):
        raise ValueError("V58 ETH policy result set is incomplete")
    for policy_id, value in policies.items():
        row = _mapping(value, f"{policy_id} result")
        if row.get("policy_id") != policy_id:
            raise ValueError("V58 ETH policy result identity is invalid")
    return policies


def _payload(
    state: str, lifecycle: Record, history: Record, limitations: Sequence[str]
) -> dict[str, object]:
    if state == "not_observed_current_run":
        return _empty_lifecycle_payload(history, limitations)
    triggered = _mapping(history.get("triggered"), "ETH trigger history")
    current_triggered = all(
        "triggered"
        in _text(
            _mapping(lifecycle["policies"], "policies")[key].get("status"),
            "policy status",
        )
        for key in _POLICIES
    )
    allowed = 0 if state == "open" else 1
    first_activation = current_triggered and all(
        value == allowed for value in triggered.values()
    )
    output = {
        "route": _ROUTE,
        "lifecycle_state": state,
        "lifecycle_id": lifecycle["lifecycle_id"],
        "side": lifecycle["side"],
        "policies": lifecycle["policies"],
        "policy_origin": _ORIGIN,
        "historical_eth_lifecycles": history["lifecycles"],
        "historical_summary_by_policy": history["summary_by_policy"],
        "current_path_is_first_eth_activation": first_activation,
        "limitations": list(limitations),
    }
    if "actual_net_pnl_usd" in lifecycle:
        output["actual_net_pnl_usd"] = lifecycle["actual_net_pnl_usd"]
        output["actual_close_reconciliation"] = lifecycle["actual_close_reconciliation"]
    return output


def _empty_lifecycle_payload(
    history: Record, limitations: Sequence[str]
) -> dict[str, object]:
    return {
        "route": _ROUTE,
        "lifecycle_state": "not_observed_current_run",
        "lifecycle_id": None,
        "side": None,
        "policies": {},
        "policy_origin": _ORIGIN,
        "historical_eth_lifecycles": history["lifecycles"],
        "historical_summary_by_policy": history["summary_by_policy"],
        "current_path_is_first_eth_activation": False,
        "limitations": list(limitations),
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an object list")
    return tuple(value)


def _texts(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a text list")
    return tuple(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _nonnegative(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
