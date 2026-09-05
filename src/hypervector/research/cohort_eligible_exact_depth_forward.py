"""Exact visible-depth lifecycle evidence for eligible cohort signals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hypervector.research.cohort_active_book_path import (
    active_book_gap,
    active_book_gap_attempt as _gap_attempt,
)
from hypervector.research.cohort_exact_depth_books import (
    book_time,
    compatible_run_ids,
    directional_return_bps,
    first_book,
    latest_book_time,
    validated_books,
    visible_depth_fill,
)
from hypervector.research.cohort_exact_depth_attempts import (
    attempt_base as _attempt_base,
    capacity_status as _capacity_status,
    eligible_candidates,
    entry_fields as _entry_fields,
)
from hypervector.research.cohort_eligible_opposite_exit import (
    EarlyExitEvidence,
    entered_early_exit_evidence,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
    covered_funding_bps,
)
from hypervector.research.cohort_eligible_exact_depth_reporting import (
    forward_report,
    net_scope,
    policy_contract,
    positive_rate,
)
from hypervector.research.cohort_live_audit_values import nonnegative_int
from hypervector.research.cohort_signal_candidates import SignalCandidate

Record = Mapping[str, object]
_MINUTE_MS = 60_000
_CURRENT_OUTCOME_KEYS = (
    "exit_time_ms",
    "exit_price",
    "gross_return_bps",
    "fee_bps",
    "funding_bps",
    "net_return_bps",
    "simulated_net_pnl_usd",
)


def build_eligible_exact_depth_forward_report(
    cohort_records: Sequence[Record],
    asset_records: Sequence[Record],
    *,
    policy_report: Record,
    funding_evidence: EligiblePolicyFundingEvidence | None,
    taker_fee_rate: float,
    maximum_entry_delay_ms: int,
    maximum_exit_delay_ms: int,
) -> dict[str, object]:
    """Replay eligible signals through causal recorded visible depth."""
    contract = policy_contract(policy_report)
    positive_rate(taker_fee_rate, "taker fee rate")
    nonnegative_int(maximum_entry_delay_ms, "maximum entry delay")
    nonnegative_int(maximum_exit_delay_ms, "maximum exit delay")
    books = validated_books(
        asset_records,
        symbol=str(contract["symbol"]),
        run_ids=compatible_run_ids(contract),
    )
    candidates = eligible_candidates(cohort_records, contract)
    attempts: list[dict[str, object]] = []
    executions: list[dict[str, object]] = []
    next_available_ms = -1
    overlapping = 0
    for candidate in candidates:
        if candidate.available_time_ms < next_available_ms:
            overlapping += 1
            continue
        attempt, execution, next_available_ms = _evaluate_candidate(
            candidate,
            candidates,
            books,
            contract,
            funding_evidence,
            taker_fee_rate,
            maximum_entry_delay_ms,
            maximum_exit_delay_ms,
        )
        attempts.append(attempt)
        if execution is not None:
            executions.append(execution)
    return forward_report(contract, attempts, executions, overlapping, taker_fee_rate)


def _evaluate_candidate(
    candidate: SignalCandidate,
    candidates: Sequence[SignalCandidate],
    books: Sequence[Record],
    contract: Record,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    entry_delay_ms: int,
    exit_delay_ms: int,
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    base = _attempt_base(candidate, contract)
    entry = first_book(books, candidate.available_time_ms, entry_delay_ms)
    deadline = (
        candidate.available_time_ms + int(contract["maximum_hold_minutes"]) * _MINUTE_MS
    )
    if entry is None:
        return base | {"status": "entry_book_unavailable"}, None, deadline
    entry_fill = visible_depth_fill(
        entry,
        position_side=candidate.side or "",
        notional=float(contract["notional_usd"]),
        quantity=None,
    )
    if not entry_fill["complete"]:
        return base | _capacity_status("entry", entry, entry_fill), None, deadline
    return _evaluate_entered(
        base,
        entry,
        entry_fill,
        books,
        candidate,
        candidates,
        contract,
        funding,
        fee_rate,
        exit_delay_ms,
        max(entry_delay_ms, exit_delay_ms),
    )


def _evaluate_entered(
    base: dict[str, object],
    entry: Record,
    entry_fill: Record,
    books: Sequence[Record],
    candidate: SignalCandidate,
    candidates: Sequence[SignalCandidate],
    contract: Record,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    exit_delay_ms: int,
    active_gap_limit_ms: int,
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    quantity = float(entry_fill["quantity"])
    deadline = book_time(entry) + int(contract["maximum_hold_minutes"]) * _MINUTE_MS
    early = _early_exit(
        base,
        entry,
        entry_fill,
        books,
        candidate,
        candidates,
        contract,
        funding,
        fee_rate,
        exit_delay_ms,
        deadline,
        active_gap_limit_ms,
    )
    if early is not None:
        return early
    return _maximum_hold_or_pending(
        base,
        entry,
        entry_fill,
        quantity,
        books,
        candidate,
        contract,
        funding,
        fee_rate,
        deadline,
        exit_delay_ms,
        active_gap_limit_ms,
    )


def _early_exit(
    base: dict[str, object],
    entry: Record,
    entry_fill: Record,
    books: Sequence[Record],
    candidate: SignalCandidate,
    candidates: Sequence[SignalCandidate],
    contract: Record,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    exit_delay_ms: int,
    deadline: int,
    active_gap_limit_ms: int,
) -> tuple[dict[str, object], dict[str, object] | None, int] | None:
    evidence = entered_early_exit_evidence(
        entry=entry,
        entry_fill=entry_fill,
        books=books,
        opening=candidate,
        candidates=candidates,
        contract=contract,
        exit_delay_ms=exit_delay_ms,
        deadline_ms=deadline,
    )
    if evidence.unavailable_status is not None:
        fields, resume_time = evidence.unavailable_status
        return base | _entry_fields(entry, entry_fill) | fields, None, resume_time
    if evidence.reason is None or evidence.exit_book is None:
        return None
    return _resolve_early_exit(
        base,
        entry,
        entry_fill,
        books,
        candidate,
        contract,
        funding,
        fee_rate,
        deadline,
        active_gap_limit_ms,
        evidence,
    )


def _resolve_early_exit(
    base: dict[str, object],
    entry: Record,
    entry_fill: Record,
    books: Sequence[Record],
    candidate: SignalCandidate,
    contract: Record,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    deadline: int,
    active_gap_limit_ms: int,
    evidence: EarlyExitEvidence,
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    exit_book = evidence.exit_book
    reason = evidence.reason
    if exit_book is None or reason is None:
        raise ValueError("selected early exit is incomplete")
    gap = active_book_gap(entry, exit_book, books, active_gap_limit_ms)
    if gap is not None:
        attempt = _gap_attempt(base, _entry_fields(entry, entry_fill), gap, deadline)
        return attempt, None, deadline
    result = _resolve(
        base,
        entry,
        exit_book,
        entry_fill,
        float(entry_fill["quantity"]),
        candidate,
        contract,
        funding,
        fee_rate,
        reason,
    )
    attempt, execution, exit_time = result
    if execution is not None and evidence.policy_selected and evidence.policy:
        execution["policy_exit_evidence"] = dict(evidence.policy.evidence)
    if evidence.opposite is not None:
        exit_time = max(exit_time, evidence.opposite.available_time_ms + 1)
    return attempt, execution, exit_time


def _maximum_hold_or_pending(
    base: dict[str, object],
    entry: Record,
    entry_fill: Record,
    quantity: float,
    books: Sequence[Record],
    candidate: SignalCandidate,
    contract: Record,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    deadline: int,
    exit_delay_ms: int,
    active_gap_limit_ms: int,
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    if latest_book_time(books) < deadline:
        return _pending_before_deadline(
            base,
            entry,
            entry_fill,
            quantity,
            books,
            candidate,
            contract,
            funding,
            fee_rate,
            deadline,
            active_gap_limit_ms,
        )
    return _maximum_hold_exit(
        base,
        entry,
        entry_fill,
        quantity,
        books,
        candidate,
        contract,
        funding,
        fee_rate,
        deadline,
        exit_delay_ms,
        active_gap_limit_ms,
    )


def _maximum_hold_exit(
    base: dict[str, object],
    entry: Record,
    entry_fill: Record,
    quantity: float,
    books: Sequence[Record],
    candidate: SignalCandidate,
    contract: Record,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    deadline: int,
    exit_delay_ms: int,
    active_gap_limit_ms: int,
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    exit_book = first_book(books, deadline, exit_delay_ms)
    if exit_book is None:
        attempt = (
            base
            | _entry_fields(entry, entry_fill)
            | {
                "status": "maximum_hold_exit_unavailable",
                "deadline_time_ms": deadline,
            }
        )
        return attempt, None, deadline
    gap = active_book_gap(entry, exit_book, books, active_gap_limit_ms)
    if gap is not None:
        attempt = _gap_attempt(base, _entry_fields(entry, entry_fill), gap, deadline)
        return attempt, None, deadline
    return _resolve(
        base,
        entry,
        exit_book,
        entry_fill,
        quantity,
        candidate,
        contract,
        funding,
        fee_rate,
        "maximum_hold",
    )


def _pending_before_deadline(
    base: dict[str, object],
    entry: Record,
    entry_fill: Record,
    quantity: float,
    books: Sequence[Record],
    candidate: SignalCandidate,
    contract: Record,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    deadline: int,
    active_gap_limit_ms: int,
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    gap = active_book_gap(entry, books[-1], books, active_gap_limit_ms)
    if gap is not None:
        attempt = _gap_attempt(base, _entry_fields(entry, entry_fill), gap, deadline)
        return attempt, None, deadline
    attempt = _pending(
        base,
        entry,
        books[-1],
        entry_fill,
        quantity,
        candidate,
        contract,
        funding,
        fee_rate,
    )
    return attempt, None, deadline


def _resolve(
    base: dict[str, object],
    entry: Record,
    exit_book: Record,
    entry_fill: Record,
    quantity: float,
    candidate: SignalCandidate,
    contract: Record,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    reason: str,
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    exit_fill = visible_depth_fill(
        exit_book,
        position_side=candidate.side or "",
        notional=0.0,
        quantity=quantity,
    )
    if not exit_fill["complete"]:
        attempt = (
            base
            | _entry_fields(entry, entry_fill)
            | _capacity_status("exit", exit_book, exit_fill)
        )
        return attempt, None, book_time(exit_book)
    result = _outcome(
        base,
        entry,
        exit_book,
        entry_fill,
        exit_fill,
        candidate,
        contract,
        funding,
        fee_rate,
    )
    execution = result | {"status": "resolved", "exit_reason": reason}
    return base | {"status": "resolved"}, execution, book_time(exit_book)


def _pending(
    base: dict[str, object],
    entry: Record,
    current: Record,
    entry_fill: Record,
    quantity: float,
    candidate: SignalCandidate,
    contract: Record,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
) -> dict[str, object]:
    exit_fill = visible_depth_fill(
        current,
        position_side=candidate.side or "",
        notional=0.0,
        quantity=quantity,
    )
    if not exit_fill["complete"]:
        return (
            base
            | _entry_fields(entry, entry_fill)
            | _capacity_status("current_exit", current, exit_fill)
        )
    outcome = _outcome(
        base,
        entry,
        current,
        entry_fill,
        exit_fill,
        candidate,
        contract,
        funding,
        fee_rate,
    )
    deadline = book_time(entry) + int(contract["maximum_hold_minutes"]) * _MINUTE_MS
    current_values = {
        f"current_{key}": outcome.pop(key) for key in _CURRENT_OUTCOME_KEYS
    }
    return {
        **outcome,
        "status": "exit_pending",
        "deadline_time_ms": deadline,
        **current_values,
    }


def _outcome(
    base: dict[str, object],
    entry: Record,
    exit_book: Record,
    entry_fill: Record,
    exit_fill: Record,
    candidate: SignalCandidate,
    contract: Record,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
) -> dict[str, object]:
    entry_price = float(entry_fill["price"])
    exit_price = float(exit_fill["price"])
    gross = directional_return_bps(candidate.side or "", entry_price, exit_price)
    entry_notional = float(entry_fill["quote_usd"])
    exit_notional = float(exit_fill["quote_usd"])
    fee_usd = fee_rate * (entry_notional + exit_notional)
    fee_bps = fee_usd / entry_notional * 10_000.0
    funding_bps = covered_funding_bps(
        funding,
        symbol=candidate.symbol,
        side=candidate.side or "",
        start_ms=book_time(entry),
        end_ms=book_time(exit_book),
    )
    net = gross - fee_bps + (funding_bps or 0.0)
    return (
        base
        | _entry_fields(entry, entry_fill)
        | {
            "exit_time_ms": book_time(exit_book),
            "exit_price": exit_price,
            "gross_return_bps": gross,
            "fee_usd": fee_usd,
            "fee_bps": fee_bps,
            "funding_bps": funding_bps,
            "net_return_bps": net,
            "net_return_scope": net_scope(funding_bps),
            "simulated_net_pnl_usd": entry_notional * net / 10_000.0,
        }
    )
