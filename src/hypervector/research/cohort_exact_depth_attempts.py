"""Identity and capacity fields for exact-depth lifecycle attempts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_exact_depth_books import book_time, compatible_run_ids
from hypervector.research.cohort_live_audit_values import event_rows, payload
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)

Record = Mapping[str, object]


def attempt_base(candidate: SignalCandidate, contract: Record) -> dict[str, object]:
    """Return immutable signal identity fields for one attempt."""
    return {
        "source_run_id": candidate.source_run_id,
        "strategy_id": candidate.strategy_id,
        "candidate_strategy_id": contract["candidate_strategy_id"],
        "symbol": candidate.symbol,
        "side": candidate.side,
        "decision_time_ms": candidate.decision_time_ms,
        "available_time_ms": candidate.available_time_ms,
        "reference_price": candidate.reference_price,
    }


def entry_fields(entry: Record, fill: Record) -> dict[str, object]:
    """Return exact visible-depth entry fields for one entered attempt."""
    return {
        "entry_time_ms": book_time(entry),
        "entry_price": fill["price"],
        "position_quantity": fill["quantity"],
        "entry_notional_usd": fill["quote_usd"],
        "entry_levels_consumed": fill["levels_consumed"],
    }


def capacity_status(prefix: str, book: Record, fill: Record) -> dict[str, object]:
    """Return explicit visible-depth capacity failure evidence."""
    return {
        "status": f"{prefix}_capacity_insufficient",
        f"{prefix}_time_ms": book_time(book),
        f"{prefix}_filled_quantity": fill["quantity"],
        f"{prefix}_unfilled_quantity": fill["unfilled_quantity"],
    }


def eligible_candidates(
    records: Sequence[Record], contract: Record
) -> tuple[SignalCandidate, ...]:
    """Return exact eligible candidates bound to the policy identity."""
    identities = event_rows(records, "configuration_identity")
    run_ids = compatible_run_ids(contract)
    observed_run_ids = {row.get("run_id") for row in identities}
    if len(identities) != len(run_ids) or observed_run_ids != set(run_ids):
        raise ValueError("exact-depth report continuation identities are incomplete")
    expected_fingerprint = contract.get("profile_fingerprint")
    if any(
        payload(row).get("profile_fingerprint") != expected_fingerprint
        for row in identities
    ):
        raise ValueError("cohort profile fingerprint differs from policy contract")
    candidates, _, _ = evaluation_candidates(records)
    selected = (
        candidate
        for candidate in candidates
        if candidate.source_run_id == contract["source_run_id"]
        and candidate.strategy_id == contract["source_strategy_id"]
        and candidate.symbol == contract["symbol"]
        and candidate.eligible
    )
    return tuple(sorted(selected, key=lambda row: row.available_time_ms))
