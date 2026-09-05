"""Attempt payloads for the report-only SOL route-native shadow."""

from __future__ import annotations

from collections.abc import Sequence

from hypervector.research.cohort_one_blocker_execution_contract import (
    OneBlockerExecutionContract,
)
from hypervector.research.cohort_one_blocker_execution_liquidity import exit_execution
from hypervector.research.cohort_one_blocker_execution_payloads import (
    attempt_base,
    direction,
    pending_attempt,
)
from hypervector.research.cohort_one_blocker_execution_types import Book
from hypervector.research.cohort_signal_candidates import SignalCandidate
from hypervector.research.sol_route_native_one_blocker_models import SolFundingEvidence


def basic_attempt(
    candidate: SignalCandidate,
    status: str,
    entry_time_ms: int | None = None,
) -> dict[str, object]:
    """Build one attributable attempt without unavailable economics."""
    payload: dict[str, object] = {
        "strategy_id": candidate.strategy_id,
        "symbol": candidate.symbol,
        "side": candidate.side,
        "decision_time_ms": candidate.decision_time_ms,
        "available_time_ms": candidate.available_time_ms,
        "source_run_id": candidate.source_run_id,
        "blockers": list(candidate.blockers),
        "status": status,
    }
    if entry_time_ms is not None:
        payload["entry_time_ms"] = entry_time_ms
    return payload


def pending_marked_attempt(
    *,
    candidate: SignalCandidate,
    context: Book,
    entry: Book,
    books: Sequence[Book],
    funding: Sequence[tuple[int, float]],
    entry_price: float,
    deadline_ms: int,
    contract: OneBlockerExecutionContract,
) -> dict[str, object]:
    """Describe a funded pending lifecycle at the latest executable quote."""
    position_size = contract.notional_usd / entry_price
    path_books = tuple(book for book in books if book.recv_ts_ms >= entry.recv_ts_ms)
    priced_books, path_complete = _visible_depth_exit_books(
        path_books, candidate, position_size, contract
    )
    payload = pending_attempt(
        attempt_base(candidate, context),
        candidate,
        entry,
        priced_books[-1],
        priced_books,
        funding,
        entry_price,
        position_size,
        deadline_ms,
        contract,
    )
    capacity = payload.pop("current_exit_top_level_capacity")
    payload["current_exit_visible_depth_capacity"] = capacity
    payload["visible_depth_path_complete"] = path_complete
    payload["liquidity_pricing"] = "visible_depth_vwap"
    if capacity is not True:
        for key in (
            "current_gross_return_bps",
            "current_fee_bps",
            "current_estimated_net_return_bps",
        ):
            payload[key] = None
    if not path_complete:
        payload["mfe_bps"] = None
        payload["mae_bps"] = None
    return payload


def pending_candidate(
    *,
    candidate: SignalCandidate,
    books: Sequence[Book],
    funding_evidence: SolFundingEvidence | None,
    context: Book,
    entry: Book,
    entry_price: float,
    deadline_ms: int,
    contract: OneBlockerExecutionContract,
) -> tuple[dict[str, object], None]:
    """Return marked pending economics when funding coverage is complete."""
    latest = books[-1]
    funding = covered_funding(funding_evidence, entry.recv_ts_ms, latest.recv_ts_ms)
    if funding is None:
        return basic_attempt(candidate, "exit_pending", entry.recv_ts_ms), None
    return (
        pending_marked_attempt(
            candidate=candidate,
            context=context,
            entry=entry,
            books=books,
            funding=funding,
            entry_price=entry_price,
            deadline_ms=deadline_ms,
            contract=contract,
        ),
        None,
    )


def _visible_depth_exit_books(
    books: Sequence[Book],
    candidate: SignalCandidate,
    position_size: float,
    contract: OneBlockerExecutionContract,
) -> tuple[tuple[Book, ...], bool]:
    trade_direction = direction(candidate)
    converted: list[Book] = []
    complete = True
    for book in books:
        price, size = exit_execution(book, trade_direction, position_size, contract)
        complete = complete and size + 1e-12 >= position_size
        if trade_direction > 0.0:
            top = (price, size, book.ask_price, book.ask_size)
        else:
            top = (book.bid_price, book.bid_size, price, size)
        converted.append(Book(book.recv_ts_ms, book.opi, *top, book.bids, book.asks))
    return tuple(converted), complete


def covered_funding(
    evidence: SolFundingEvidence | None,
    start_ms: int,
    end_ms: int,
) -> tuple[tuple[int, float], ...] | None:
    """Return official settlements only for a fully covered lifecycle window."""
    if evidence is None:
        return None
    if evidence.requested_start_ms > start_ms or evidence.requested_end_ms < end_ms:
        return None
    return tuple(event for event in evidence.events if start_ms < event[0] <= end_ms)
