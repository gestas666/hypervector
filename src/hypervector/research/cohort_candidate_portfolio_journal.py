"""Causal shared-portfolio classification for report-only strategy attempts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_live_audit_values import (
    mapping,
    mapping_list,
    nonnegative_int,
    number,
    payload,
    positive_int,
    run_id,
    text,
)

Record = Mapping[str, object]
_LATEST_ATTEMPT_LIMIT = 100


@dataclass(frozen=True)
class CandidatePortfolioJournalSpec:
    """Identify one flat-entry candidate and its shared-portfolio constraints."""

    source_strategy_id: str
    candidate_strategy_id: str
    symbol: str
    maximum_positions: int

    def __post_init__(self) -> None:
        """Reject incomplete strategy or portfolio identity."""
        text(self.source_strategy_id, "source strategy_id")
        text(self.candidate_strategy_id, "candidate strategy_id")
        text(self.symbol, "candidate symbol")
        positive_int(self.maximum_positions, "maximum positions")
        if self.source_strategy_id == self.candidate_strategy_id:
            raise ValueError("candidate strategy must differ from its source strategy")


def build_candidate_portfolio_journal(
    cohort_records: Sequence[Record],
    replay: Mapping[str, object],
    *,
    spec: CandidatePortfolioJournalSpec,
) -> dict[str, object]:
    """Classify whether each replay attempt fit the observed live portfolio."""
    attempts, executions = _validated_replay(replay, spec)
    routings = _routing_index(cohort_records, attempts, spec)
    snapshots = _snapshot_index(cohort_records)
    rows = [
        _classify_attempt(
            attempt,
            routings[_attempt_key(attempt)],
            snapshots,
            executions,
            spec,
        )
        for attempt in attempts
    ]
    return {
        "schema_version": 1,
        "mode": "candidate_portfolio_compatibility_journal",
        "state": "resolved_observations" if rows else "awaiting_attempts",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "source_strategy_id": spec.source_strategy_id,
            "candidate_strategy_id": spec.candidate_strategy_id,
            "symbol": spec.symbol,
            "position_policy": "flat_entry_only",
            "maximum_positions": spec.maximum_positions,
            "portfolio_pnl_claimed": False,
            "simulated_outcomes_are_non_additive": True,
        },
        "summary": _summary(rows),
        "latest_attempts": rows[-_LATEST_ATTEMPT_LIMIT:],
        "limitations": [
            "deployable means observed portfolio compatibility, not proof of venue fill",
            "same-cycle route conflicts remain counterfactual without candidate activation",
            "simulated outcomes are not added to live portfolio performance",
        ],
    }


def _validated_replay(
    replay: Mapping[str, object], spec: CandidatePortfolioJournalSpec
) -> tuple[list[Record], dict[tuple[object, ...], Record]]:
    supported_modes = {
        "one_blocker_execution_feasibility",
        "eligible_policy_forward_observer",
        "v51_sol_route_native_one_blocker_shadow",
    }
    if replay.get("schema_version") != 1 or replay.get("mode") not in supported_modes:
        raise ValueError("candidate portfolio replay envelope is invalid")
    attempts = mapping_list(replay.get("attempts"), "candidate replay attempts")
    executions = mapping_list(replay.get("executions"), "candidate replay executions")
    attempt_keys = [_validated_attempt_key(row, spec) for row in attempts]
    if len(set(attempt_keys)) != len(attempt_keys):
        raise ValueError("candidate replay attempt identity is duplicated")
    execution_index = _execution_index(executions, spec)
    if not set(execution_index).issubset(attempt_keys):
        raise ValueError("candidate execution has no matching selected attempt")
    for row, key in zip(attempts, attempt_keys, strict=True):
        resolved = text(row.get("status"), "candidate attempt status") == "resolved"
        if resolved != (key in execution_index):
            raise ValueError("candidate attempt and execution status are inconsistent")
    return attempts, execution_index


def _execution_index(
    rows: Sequence[Record], spec: CandidatePortfolioJournalSpec
) -> dict[tuple[object, ...], Record]:
    result: dict[tuple[object, ...], Record] = {}
    for row in rows:
        key = _validated_attempt_key(row, spec)
        if key in result:
            raise ValueError("candidate execution identity is duplicated")
        nonnegative_int(row.get("entry_time_ms"), "candidate entry time")
        nonnegative_int(row.get("exit_time_ms"), "candidate exit time")
        result[key] = row
    return result


def _validated_attempt_key(
    row: Record, spec: CandidatePortfolioJournalSpec
) -> tuple[object, ...]:
    key = _attempt_key(row)
    if key[1] != spec.source_strategy_id or key[2] != spec.symbol:
        raise ValueError("candidate attempt source identity changed")
    if key[3] not in {"long", "short"}:
        raise ValueError("candidate attempt side must be long or short")
    return key


def _attempt_key(row: Record) -> tuple[object, ...]:
    return (
        text(row.get("source_run_id"), "candidate source run_id"),
        text(row.get("strategy_id"), "candidate source strategy_id"),
        text(row.get("symbol"), "candidate symbol"),
        text(row.get("side"), "candidate side"),
        nonnegative_int(row.get("decision_time_ms"), "candidate decision time"),
        nonnegative_int(row.get("available_time_ms"), "candidate available time"),
    )


def _routing_index(
    records: Sequence[Record],
    attempts: Sequence[Record],
    spec: CandidatePortfolioJournalSpec,
) -> dict[tuple[object, ...], Record]:
    result: dict[tuple[object, ...], Record] = {}
    for attempt in attempts:
        key = _attempt_key(attempt)
        matches = [row for row in records if _routing_matches(row, key, spec)]
        if not matches:
            raise ValueError("candidate routing publication unavailable")
        if len(matches) != 1:
            raise ValueError("candidate has ambiguous routing publication")
        result[key] = matches[0]
    return result


def _routing_matches(
    row: Record, key: tuple[object, ...], spec: CandidatePortfolioJournalSpec
) -> bool:
    if row.get("event_type") != "intent_routing" or row.get("run_id") != key[0]:
        return False
    evaluations = mapping_list(payload(row).get("evaluations"), "routing evaluations")
    matches = [
        item
        for item in evaluations
        if item.get("strategy_id") == spec.source_strategy_id
        and item.get("symbol") == spec.symbol
        and item.get("decision_time_ms") == key[4]
    ]
    if len(matches) > 1:
        raise ValueError("routing contains duplicate source evaluations")
    return bool(matches)


def _snapshot_index(records: Sequence[Record]) -> dict[str, list[Record]]:
    result: dict[str, list[Record]] = {}
    seen: set[tuple[str, int]] = set()
    for row in records:
        if row.get("event_type") != "cohort_snapshot":
            continue
        identity = (run_id(row), _sequence(row))
        if identity in seen:
            raise ValueError("cohort snapshot sequence is duplicated")
        seen.add(identity)
        result.setdefault(identity[0], []).append(row)
    for rows in result.values():
        rows.sort(key=_sequence)
    return result


def _classify_attempt(
    attempt: Record,
    routing: Record,
    snapshots: Mapping[str, Sequence[Record]],
    executions: Mapping[tuple[object, ...], Record],
    spec: CandidatePortfolioJournalSpec,
) -> dict[str, object]:
    key = _attempt_key(attempt)
    prior = _strictly_prior_snapshot(snapshots.get(key[0], ()), routing)
    route = _route_context(routing, spec.symbol)
    base = {
        **dict(attempt),
        "candidate_strategy_id": spec.candidate_strategy_id,
        "routing_sequence": _sequence(routing),
        **route,
    }
    if prior is None:
        return (
            base
            | {
                "portfolio_classification": "portfolio_state_unavailable",
                "open_position_count": None,
                "available_position_slots": None,
            }
            | _outcome(executions.get(key))
        )
    context = _snapshot_context(prior, spec)
    classification = _classification(context, route, spec.maximum_positions)
    return (
        base
        | context
        | {
            "portfolio_classification": classification,
            "snapshot_sequence": _sequence(prior),
        }
        | _outcome(executions.get(key))
    )


def _strictly_prior_snapshot(rows: Sequence[Record], routing: Record) -> Record | None:
    routing_sequence = _sequence(routing)
    prior = [row for row in rows if _sequence(row) < routing_sequence]
    return prior[-1] if prior else None


def _snapshot_context(
    row: Record, spec: CandidatePortfolioJournalSpec
) -> dict[str, object]:
    values = payload(row)
    open_positions = nonnegative_int(
        values.get("open_position_count"), "open position count"
    )
    if open_positions > spec.maximum_positions:
        raise ValueError("open position count exceeds configured maximum")
    assets = mapping_list(values.get("assets"), "cohort snapshot assets")
    matches = [asset for asset in assets if asset.get("symbol") == spec.symbol]
    if len(matches) != 1:
        raise ValueError("cohort snapshot must contain one candidate symbol")
    asset = matches[0]
    state = text(asset.get("state"), "candidate symbol state")
    side = asset.get("position_side")
    if side is not None and side not in {"long", "short"}:
        raise ValueError("candidate symbol position side is invalid")
    strategy = _position_strategy(asset)
    return {
        "open_position_count": open_positions,
        "available_position_slots": spec.maximum_positions - open_positions,
        "symbol_state": state,
        "symbol_position_side": side,
        "symbol_position_strategy_id": strategy,
    }


def _position_strategy(asset: Record) -> str | None:
    plan = asset.get("execution_plan")
    if plan is None:
        return None
    return text(
        mapping(plan, "candidate execution plan").get("strategy_id"), "strategy"
    )


def _route_context(routing: Record, symbol: str) -> dict[str, object]:
    values = payload(routing)
    actions = _symbol_routes(values.get("actions"), symbol, include_reason=False)
    withheld = _symbol_routes(values.get("withheld"), symbol, include_reason=True)
    return {
        "same_cycle_symbol_actions": actions,
        "same_cycle_symbol_withheld": withheld,
    }


def _symbol_routes(
    value: object, symbol: str, *, include_reason: bool
) -> list[dict[str, str]]:
    rows = mapping_list(value, "routing result rows")
    result: list[dict[str, str]] = []
    for row in rows:
        if row.get("symbol") != symbol:
            continue
        item = {"strategy_id": text(row.get("strategy_id"), "route strategy")}
        if include_reason:
            item["reason"] = text(row.get("reason"), "withheld route reason")
        result.append(item)
    return result


def _classification(
    context: Mapping[str, object],
    route: Mapping[str, object],
    maximum_positions: int,
) -> str:
    if context["symbol_state"] != "FLAT" or context["symbol_position_side"]:
        return "existing_symbol_position"
    if context["open_position_count"] >= maximum_positions:
        return "portfolio_capacity"
    if route["same_cycle_symbol_actions"]:
        return "same_cycle_symbol_action"
    return "deployable_flat_entry"


def _outcome(execution: Record | None) -> dict[str, object]:
    if execution is None:
        return {
            "outcome_status": "pending_or_unresolved",
            "net_return_bps": None,
            "simulated_net_pnl_usd": None,
        }
    return {
        "outcome_status": "resolved",
        "net_return_bps": execution.get("net_return_bps"),
        "simulated_net_pnl_usd": execution.get("simulated_net_pnl_usd"),
    }


def _summary(rows: Sequence[Record]) -> dict[str, object]:
    classes = Counter(row["portfolio_classification"] for row in rows)
    resolved = sum(row["outcome_status"] == "resolved" for row in rows)
    deployable_rows = [
        row
        for row in rows
        if row["portfolio_classification"] == "deployable_flat_entry"
    ]
    deployable = [
        number(row.get("net_return_bps"), "deployable net return")
        for row in deployable_rows
        if row["outcome_status"] == "resolved"
    ]
    active = sum(row.get("status") == "exit_pending" for row in deployable_rows)
    unresolved = len(deployable_rows) - len(deployable) - active
    gains = sum(value for value in deployable if value > 0.0)
    losses = -sum(value for value in deployable if value < 0.0)
    absolute = sum(abs(value) for value in deployable)
    return {
        "attempts": len(rows),
        "deployable": classes["deployable_flat_entry"],
        "deployable_resolved": len(deployable),
        "deployable_wins": sum(value > 0.0 for value in deployable),
        "deployable_losses": sum(value < 0.0 for value in deployable),
        "deployable_total_net_return_bps": sum(deployable),
        "deployable_profit_factor": gains / losses if losses else None,
        "deployable_largest_abs_contribution_fraction": (
            max((abs(value) for value in deployable), default=0.0) / absolute
            if absolute
            else None
        ),
        "deployable_active_pending": active,
        "deployable_technically_unresolved": unresolved,
        "deployable_observed_sides": sorted(
            {text(row.get("side"), "deployable side") for row in deployable_rows}
        ),
        "existing_symbol_position": classes["existing_symbol_position"],
        "portfolio_capacity": classes["portfolio_capacity"],
        "same_cycle_symbol_action": classes["same_cycle_symbol_action"],
        "portfolio_state_unavailable": classes["portfolio_state_unavailable"],
        "resolved": resolved,
        "pending": len(rows) - resolved,
    }


def _sequence(row: Record) -> int:
    return nonnegative_int(row.get("sequence"), "ledger sequence")
