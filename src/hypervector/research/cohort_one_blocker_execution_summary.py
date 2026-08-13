"""Side-level summaries for one-blocker execution replays."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import number
from hypervector.research.cohort_one_blocker_execution_contract import (
    OneBlockerExecutionContract,
)
from hypervector.research.cohort_one_blocker_execution_types import Coverage

Record = Mapping[str, object]


def build_execution_feasibility_payload(
    contract: OneBlockerExecutionContract,
    coverage: Coverage,
    funding_row_count: int,
    attempts: Sequence[Record],
    executions: Sequence[Record],
) -> dict[str, object]:
    """Build the stable report envelope around replay attempts and results."""
    return {
        "schema_version": 1,
        "mode": "one_blocker_execution_feasibility",
        "contract": contract.as_payload(),
        "coverage": coverage.as_payload(),
        "funding_evidence": {
            "rows": funding_row_count,
            "source": "official_hyperliquid_funding_history",
            "constant_entry_notional_approximation": True,
        },
        "attempts": attempts,
        "executions": executions,
        "by_side": {
            side: summarize_execution_side(executions, side)
            for side in ("long", "short")
        },
        "limitations": [
            "recorded snapshots do not prove an IOC fill between observations",
            _liquidity_limitation(contract),
            "funding bps assume entry notional remains constant between settlements",
            "stop exits use adverse BBO as a proxy, not an exact venue trigger fill",
            "selection is fixed and non-overlapping; small or one-sided N is descriptive",
        ],
    }


def _liquidity_limitation(contract: OneBlockerExecutionContract) -> str:
    if contract.liquidity_policy == "top_level":
        return "top-level capacity is stricter than a visible multi-level book walk"
    return "visible depth can cancel before a live IOC reaches the venue"


def summarize_execution_side(
    executions: Sequence[Record], side: str
) -> dict[str, object]:
    """Summarize resolved replay returns for one trade direction."""
    values = [
        number(row.get("net_return_bps"), "net return")
        for row in executions
        if row.get("side") == side
    ]
    gains = sum(value for value in values if value > 0.0)
    losses = -sum(value for value in values if value < 0.0)
    return {
        "resolved": len(values),
        "wins": sum(value > 0.0 for value in values),
        "losses": sum(value < 0.0 for value in values),
        "mean_net_return_bps": sum(values) / len(values) if values else None,
        "total_net_return_bps": sum(values),
        "profit_factor": gains / losses if losses else None,
        "stop_proxy_crosses": sum(
            bool(row.get("crossed_stop_proxy"))
            for row in executions
            if row.get("side") == side
        ),
        "target_proxy_crosses": sum(
            row.get("exit_reason") == "target_proxy"
            for row in executions
            if row.get("side") == side
        ),
    }
