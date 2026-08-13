#!/usr/bin/env python3
"""Project one canonical live audit onto the frozen v29 route scope."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Protocol

from hypervector.data.oxa_storage import file_evidence, write_immutable_json


CONFIG = Path(
    "configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml"
)
PRIOR_BOUNDARY = Path("data/logs/research/v25_live_monitor_20260808T064253Z.json")


class CandidateContract(Protocol):
    """Fields required from the frozen v29 profile contract."""

    profile_id: str
    profile_fingerprint: str
    execution_scope: tuple[tuple[str, str], ...]


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable v29 live-boundary projection command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--prior-boundary", type=Path, default=PRIOR_BOUNDARY)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Load immutable sources, build the projection, and publish it once."""
    frozen = _load_frozen_runner()
    contract = frozen.load_profile_contract(args.config)
    audit = _load_json(args.audit)
    prior = _load_json(args.prior_boundary)
    artifact = build_live_boundary(
        audit,
        prior,
        contract=contract,
        audit_evidence=_path_evidence(args.audit),
        prior_evidence=_path_evidence(args.prior_boundary),
        config_evidence=_path_evidence(args.config),
    )
    write_immutable_json(args.out, artifact)
    return artifact


def _load_frozen_runner() -> ModuleType:
    """Load the frozen v29 contract without treating scripts as a package."""
    name = "_hypervector_evidence_selected_portfolio_v29_contract"
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = Path(__file__).with_name("evidence_selected_portfolio_v29.py")
    spec = spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load frozen v29 contract: {path}")
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> Mapping[str, object]:
    """Load one required JSON object."""
    if not path.is_file():
        raise FileNotFoundError(f"required evidence file is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise TypeError(f"evidence root must be an object: {path}")
    return value


def _path_evidence(path: Path) -> dict[str, object]:
    """Return an absolute path plus byte and SHA-256 identity."""
    return {"path": str(path.resolve()), **file_evidence(path)}


def main(argv: Sequence[str] | None = None) -> int:
    """Publish one boundary and print only a bounded operator summary."""
    args = build_parser().parse_args(argv)
    artifact = run(args)
    assessment = _mapping(artifact, "assessment")
    delta = _mapping(artifact, "delta")
    print(
        json.dumps(
            {
                "execution_authority": "none",
                "material_delta": _boolean(delta, "material"),
                "out": str(args.out),
                "report_only": True,
                "resolved_selected_route_lifecycles": _integer(
                    assessment,
                    "resolved_selected_route_lifecycles",
                ),
            },
            sort_keys=True,
        )
    )
    return 0


def build_live_boundary(
    audit: Mapping[str, object],
    prior_boundary: Mapping[str, object],
    *,
    contract: CandidateContract,
    audit_evidence: Mapping[str, object],
    prior_evidence: Mapping[str, object],
    config_evidence: Mapping[str, object],
) -> dict[str, object]:
    """Build a compact candidate-route boundary from one canonical live audit."""
    _validate_audit(audit)
    _validate_prior_boundary(prior_boundary)
    run = _mapping(audit, "run")
    route_rows = [
        _route_observation(audit, strategy_id, symbol)
        for strategy_id, symbol in contract.execution_scope
    ]
    delta = _resolved_delta(route_rows, prior_boundary)
    active = _string(run, "profile_fingerprint") == contract.profile_fingerprint
    return {
        "schema_version": "evidence_selected_portfolio_v29_live_boundary_v1",
        "mode": "report_only_candidate_route_live_projection",
        "generated_at_utc": _string(run, "last_observed_at_utc"),
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "source_audit": dict(audit_evidence),
        "prior_boundary": dict(prior_evidence),
        "candidate": _candidate_summary(contract, config_evidence, active=active),
        "runtime": _runtime_summary(audit, run),
        "current_run": _execution_summary(_mapping(audit, "execution")),
        "v29_route_observations": route_rows,
        "delta": delta,
        "assessment": _assessment(active=active, delta=delta, rows=route_rows),
        "limitations": [
            "open marked PnL is provisional and excluded from material-delta decisions",
            "resolved live counts remain too sparse to establish route or portfolio edge",
            "the projection cannot route, size, place, close, protect, or promote trades",
        ],
    }


def _candidate_summary(
    contract: CandidateContract,
    config_evidence: Mapping[str, object],
    *,
    active: bool,
) -> dict[str, object]:
    """Project the frozen candidate identity without granting authority."""
    return {
        "profile_id": contract.profile_id,
        "profile_fingerprint": contract.profile_fingerprint,
        "config_evidence": dict(config_evidence),
        "active": active,
        "route_count": len(contract.execution_scope),
    }


def _runtime_summary(
    audit: Mapping[str, object],
    run: Mapping[str, object],
) -> dict[str, object]:
    """Project active-run identity and observed fault count."""
    return {
        "run_id": _string(run, "run_id"),
        "profile_id": _string(run, "profile_id"),
        "profile_fingerprint": _string(run, "profile_fingerprint"),
        "faults": _integer(_mapping(audit, "health"), "faults"),
    }


def _validate_audit(audit: Mapping[str, object]) -> None:
    """Require a complete report-only canonical audit boundary."""
    if _string(audit, "mode") != "multi_asset_bidirectional_live_audit":
        raise ValueError("source must be a canonical multi-asset live audit")
    experiment = _mapping(audit, "experiment_contract")
    if _string(experiment, "execution_authority") != "none":
        raise ValueError("source audit must have no execution authority")
    if not _boolean(experiment, "report_only"):
        raise ValueError("source audit must be report-only")
    if _boolean(experiment, "runtime_strategy_changed"):
        raise ValueError("source audit reports a runtime strategy change")
    if not _boolean(_mapping(audit, "coverage"), "complete"):
        raise ValueError("source audit coverage is incomplete")


def _validate_prior_boundary(prior: Mapping[str, object]) -> None:
    """Require a report-only prior comparison boundary."""
    if _string(prior, "execution_authority") != "none":
        raise ValueError("prior boundary must have no execution authority")
    if not _boolean(prior, "report_only"):
        raise ValueError("prior boundary must be report-only")


def _route_observation(
    audit: Mapping[str, object],
    strategy_id: str,
    symbol: str,
) -> dict[str, object]:
    """Project one exact selected provider-symbol route."""
    route = f"{strategy_id}|{symbol}"
    scorecards = _mapping(_mapping(audit, "strategy_scorecard"), "by_provider_symbol")
    if route not in scorecards:
        raise ValueError(f"missing selected v29 route scorecard: {route}")
    scorecard = _mapping(scorecards, route)
    performance = _route_performance(audit, route)
    open_rows = _open_rows(audit, strategy_id=strategy_id, symbol=symbol)
    return {
        "route": route,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "eligible_signals": _integer(scorecard, "eligible_signals"),
        "resolved_signal_horizons": _integer(scorecard, "resolved_signal_horizons"),
        "forward_assessment": _string(scorecard, "forward_assessment"),
        "research_state": _string(scorecard, "research_state"),
        "resolved_execution_outcomes": _optional_integer(
            performance, "closed_trades", 0
        ),
        "execution_net_pnl_usd": _optional_number(performance, "net_pnl_usd", 0.0),
        "execution_profit_factor": performance.get("profit_factor"),
        "execution_wins": _optional_integer(performance, "wins", 0),
        "execution_losses": _optional_integer(performance, "losses", 0),
        "open_lifecycles": len(open_rows),
        "open_marked_net_pnl_usd": sum(_open_marked_net(row) for row in open_rows),
        "open_sides": sorted({_string(row, "side") for row in open_rows}),
        "all_open_positions_protected": _protection_state(open_rows),
    }


def _route_performance(audit: Mapping[str, object], route: str) -> Mapping[str, object]:
    """Return current-run performance for one exact route, if observed."""
    reflections = _mapping(audit, "trade_reflections")
    performance = _mapping(reflections, "performance")
    current_run = _mapping(performance, "current_run")
    by_route = _mapping(current_run, "by_provider_symbol")
    value = by_route.get(route, {})
    if not isinstance(value, Mapping):
        raise TypeError(f"route performance must be an object: {route}")
    return value


def _open_rows(
    audit: Mapping[str, object],
    *,
    strategy_id: str,
    symbol: str,
) -> list[Mapping[str, object]]:
    """Return open lifecycle rows matching one exact route."""
    reflections = _mapping(audit, "open_trade_reflections")
    rows = _sequence(reflections, "trades")
    selected: list[Mapping[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("open trade reflection must be an object")
        if row.get("strategy_id") == strategy_id and row.get("symbol") == symbol:
            selected.append(row)
    return selected


def _open_marked_net(row: Mapping[str, object]) -> float:
    """Return backend-authored provisional marked net PnL."""
    economics = _mapping(row, "marked_economics")
    return _number(economics, "active_lifecycle_marked_net_pnl_usd")


def _open_protected(row: Mapping[str, object]) -> bool:
    """Report whether an open row carries an explicit protective stop identity."""
    stop = row.get("protective_stop")
    return isinstance(stop, Mapping) and isinstance(stop.get("oid"), int)


def _protection_state(rows: Sequence[Mapping[str, object]]) -> bool | None:
    """Return protection coverage only when an open lifecycle exists."""
    if not rows:
        return None
    return all(_open_protected(row) for row in rows)


def _resolved_delta(
    current: Sequence[Mapping[str, object]],
    prior_boundary: Mapping[str, object],
) -> dict[str, object]:
    """Compare only material resolved/eligible counters with the prior boundary."""
    prior_rows = _sequence(prior_boundary, "v29_route_observations")
    prior = {
        _string(row, "route"): row for row in prior_rows if isinstance(row, Mapping)
    }
    changes: list[dict[str, object]] = []
    fields = (
        "eligible_signals",
        "resolved_signal_horizons",
        "resolved_execution_outcomes",
    )
    for row in current:
        route = _string(row, "route")
        before = prior.get(route)
        for field in fields:
            old = _optional_integer(before or {}, field, 0)
            new = _integer(row, field)
            if old != new:
                changes.append(
                    {"route": route, "field": field, "before": old, "after": new}
                )
    return {"material": bool(changes), "changes": changes}


def _execution_summary(execution: Mapping[str, object]) -> dict[str, object]:
    """Retain exact resolved economics and measured friction summaries."""
    return {
        key: execution.get(key)
        for key in (
            "closed_trades",
            "wins",
            "losses",
            "net_pnl_usd",
            "profit_factor",
            "fees_usd",
            "funding_usd",
            "slippage_bps",
            "acknowledgement_latency_ms",
            "markout_bps",
        )
    }


def _assessment(
    *,
    active: bool,
    delta: Mapping[str, object],
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """State the evidence action without creating an execution gate."""
    material = _boolean(delta, "material")
    resolved = sum(_integer(row, "resolved_execution_outcomes") for row in rows)
    decision = (
        "review_material_evidence_before_append_only_journal_revision"
        if material
        else "retain_v29_without_new_journal_revision"
    )
    return {
        "implementation_state": "active" if active else "inactive_candidate",
        "economic_state": "sparse_forward_evidence",
        "resolved_selected_route_lifecycles": resolved,
        "decision": decision,
        "confidence": "low",
    }


def _mapping(parent: Mapping[str, object], key: str) -> Mapping[str, object]:
    """Read a required mapping with an actionable error."""
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be an object")
    return value


def _sequence(parent: Mapping[str, object], key: str) -> Sequence[object]:
    """Read a required non-string sequence with an actionable error."""
    value = parent.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{key} must be an array")
    return value


def _string(parent: Mapping[str, object], key: str) -> str:
    """Read a required string with an actionable error."""
    value = parent.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _boolean(parent: Mapping[str, object], key: str) -> bool:
    """Read a required boolean with an actionable error."""
    value = parent.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean")
    return value


def _integer(parent: Mapping[str, object], key: str) -> int:
    """Read a required integer with an actionable error."""
    value = parent.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an integer")
    return value


def _optional_integer(parent: Mapping[str, object], key: str, default: int) -> int:
    """Read an optional integer without accepting booleans or floats."""
    if key not in parent:
        return default
    return _integer(parent, key)


def _number(parent: Mapping[str, object], key: str) -> float:
    """Read a required finite-compatible numeric value."""
    value = parent.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(f"{key} must be numeric")
    return float(value)


def _optional_number(parent: Mapping[str, object], key: str, default: float) -> float:
    """Read an optional numeric value with a typed default."""
    if key not in parent:
        return default
    return _number(parent, key)


if __name__ == "__main__":
    raise SystemExit(main())
