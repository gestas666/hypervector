"""Contract validation and reporting for exact-depth cohort lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    mapping,
    number,
    positive_int,
    text,
)

Record = Mapping[str, object]
_POLICY_MODE = "cohort_config_bound_eligible_policy_forward_report"


def policy_contract(report: Record) -> dict[str, object]:
    """Validate and normalize one report-only exact-depth policy contract."""
    if report.get("mode") != _POLICY_MODE:
        raise ValueError("exact-depth input is not a config-bound policy report")
    contract = mapping(report.get("contract"), "policy contract")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
        or contract.get("portfolio_pnl_claimed") is not False
    ):
        raise ValueError("policy report does not preserve report-only authority")
    _validate_identity(contract)
    if number(contract.get("stop_bps"), "stop bps") <= 0.0:
        raise ValueError("stop bps must be positive")
    if number(contract.get("notional_usd"), "notional") <= 0.0:
        raise ValueError("notional must be positive")
    positive_int(contract.get("maximum_hold_minutes"), "maximum hold minutes")
    close_opposite = contract.get("close_on_eligible_opposite_signal", False)
    if not isinstance(close_opposite, bool):
        raise ValueError("close_on_eligible_opposite_signal must be boolean")
    return {**dict(contract), "close_on_eligible_opposite_signal": close_opposite}


def forward_report(
    contract: Record,
    attempts: Sequence[Record],
    executions: Sequence[Record],
    overlapping: int,
    fee_rate: float,
) -> dict[str, object]:
    """Render a report-only exact-depth lifecycle result."""
    return {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
        "state": "descriptive_exact_depth_evidence"
        if executions
        else "awaiting_resolution",
        "contract": {
            **dict(contract),
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
            "actual_orders_or_fills_claimed": False,
            "entry_exit_source": "recorded_visible_l2_depth_vwap",
            "taker_fee_rate": fee_rate,
        },
        "summary": _summary(attempts, executions, overlapping),
        "latest_attempts": list(attempts),
        "latest_executions": list(executions),
        "limitations": [
            "recorded visible depth is not proof that a live IOC would receive the same fill",
            "book snapshots cannot observe cancellations or price changes between samples",
            "protective-stop timing uses the first adverse recorded BBO as a venue-mark proxy",
            "simulated PnL is descriptive and has no execution or promotion authority",
        ],
    }


def net_scope(funding_bps: float | None) -> str:
    """Describe whether exact funding is included in one net result."""
    return (
        "exact_depth_fee_and_funding"
        if funding_bps is not None
        else "exact_depth_fee_before_funding"
    )


def positive_rate(value: float, label: str) -> float:
    """Validate a positive fractional rate."""
    result = number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    if result >= 1.0:
        raise ValueError(f"{label} must be less than one")
    return result


def _validate_identity(contract: Record) -> None:
    for field in (
        "source_strategy_id",
        "candidate_strategy_id",
        "symbol",
        "source_run_id",
        "profile_fingerprint",
    ):
        text(contract.get(field), field)


def _summary(
    attempts: Sequence[Record], executions: Sequence[Record], overlapping: int
) -> dict[str, object]:
    return {
        "selected_non_overlapping": len(attempts),
        "overlapping_excluded": overlapping,
        "resolved": len(executions),
        "pending": sum(row.get("status") == "exit_pending" for row in attempts),
        "technical_incomplete": sum(
            row.get("status") not in {"resolved", "exit_pending"} for row in attempts
        ),
    }
