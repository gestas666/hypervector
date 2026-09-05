"""Report construction for exact V58 BTC sweep lifecycle evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_exact_depth_books import (
    book_time,
    directional_return_bps,
    visible_depth_fill,
)

Record = Mapping[str, object]


def build_v58_btc_sweep_report(
    contract: Record,
    attempts: Sequence[Record],
    outcomes: Sequence[Record],
    overlapping: int,
    start_ms: int,
) -> dict[str, object]:
    """Build one authority-none lifecycle report from reconciled attempts."""
    pending = sum(row.get("status") == "exit_pending" for row in attempts)
    incomplete = sum(
        row.get("status") not in {"resolved", "exit_pending"} for row in attempts
    )
    return {
        "schema_version": 1,
        "mode": "v58_btc_sweep_exact_mark_depth_lifecycle_v1",
        "state": "descriptive_exact_depth_evidence"
        if outcomes
        else "awaiting_resolution",
        "contract": dict(contract),
        "identity": {
            "profile_id": contract["profile_id"],
            "profile_fingerprint": contract["profile_fingerprint"],
            "source_run_id": contract["source_run_id"],
            "prospective_start_ms": start_ms,
        },
        "summary": {
            "selected_non_overlapping": len(attempts),
            "overlapping_excluded": overlapping,
            "resolved": len(outcomes),
            "pending": pending,
            "technical_incomplete": incomplete,
        },
        "latest_attempts": list(attempts),
        "latest_executions": list(outcomes),
        "limitations": [
            "report-only visible-depth fills are not actual order fills",
            "REST mark receipts cannot prove the exact venue-internal stop timestamp",
            "taker fees on both sides conservatively ignore possible maker target rebates",
            "sparse prospective outcomes cannot establish future profitability",
        ],
    }


def build_v58_btc_sweep_pending(
    books: Sequence[Record], entry_fill: Record, fee_rate: float, quality: Record
) -> dict[str, object]:
    """Describe a technically fillable open-path exit without claiming a fill."""
    current = books[-1]
    exit_fill = visible_depth_fill(
        current,
        position_side="long",
        notional=0.0,
        quantity=float(entry_fill["quantity"]),
    )
    if not exit_fill["complete"]:
        return {
            "status": "current_exit_capacity_insufficient",
            "current_exit_time_ms": book_time(current),
            "current_exit_filled_quantity": exit_fill["quantity"],
            "current_exit_unfilled_quantity": exit_fill["unfilled_quantity"],
            "mark_path": dict(quality),
        }
    gross = directional_return_bps(
        "long", float(entry_fill["price"]), float(exit_fill["price"])
    )
    return {
        "status": "exit_pending",
        "current_exit_time_ms": book_time(current),
        "current_exit_price": exit_fill["price"],
        "current_gross_return_bps": gross,
        "current_fee_assumption_bps": fee_rate * 20_000.0,
        "mark_path": dict(quality),
    }
