"""Exact visible-depth lifecycle evidence for eligible cohort signals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hypervector.research.cohort_exact_depth_books import (
    book_time,
    compatible_run_ids,
    directional_return_bps,
    first_book,
    first_stop_book,
    latest_book_time,
    post_entry_books,
    protective_stop_price,
    validated_books,
    visible_depth_fill,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
    covered_funding_bps,
)
from hypervector.research.cohort_live_audit_values import (
    event_rows,
    mapping,
    nonnegative_int,
    number,
    payload,
    positive_int,
    text,
)
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)

Record = Mapping[str, object]
_POLICY_MODE = "cohort_config_bound_eligible_policy_forward_report"
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
    contract = _policy_contract(policy_report)
    _rate(taker_fee_rate, "taker fee rate")
    nonnegative_int(maximum_entry_delay_ms, "maximum entry delay")
    nonnegative_int(maximum_exit_delay_ms, "maximum exit delay")
    books = validated_books(
        asset_records,
        symbol=str(contract["symbol"]),
        run_ids=compatible_run_ids(contract),
    )
    candidates = _candidates(cohort_records, contract)
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
    return _report(contract, attempts, executions, overlapping, taker_fee_rate)


def _evaluate_candidate(
    candidate: SignalCandidate,
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
        contract,
        funding,
        fee_rate,
        exit_delay_ms,
    )


def _evaluate_entered(
    base: dict[str, object],
    entry: Record,
    entry_fill: Record,
    books: Sequence[Record],
    candidate: SignalCandidate,
    contract: Record,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    exit_delay_ms: int,
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    quantity = float(entry_fill["quantity"])
    deadline = book_time(entry) + int(contract["maximum_hold_minutes"]) * _MINUTE_MS
    stop_price = protective_stop_price(
        candidate.side or "", float(entry_fill["price"]), float(contract["stop_bps"])
    )
    path = post_entry_books(books, book_time(entry), deadline)
    stop_book = first_stop_book(path, side=candidate.side or "", stop_price=stop_price)
    if stop_book is not None:
        return _resolve(
            base,
            entry,
            stop_book,
            entry_fill,
            quantity,
            candidate,
            contract,
            funding,
            fee_rate,
            "protective_stop",
        )
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
    )


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
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    if latest_book_time(books) < deadline:
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
            "net_return_scope": _net_scope(funding_bps),
            "simulated_net_pnl_usd": entry_notional * net / 10_000.0,
        }
    )


def _candidates(
    records: Sequence[Record], contract: Record
) -> tuple[SignalCandidate, ...]:
    identity = event_rows(records, "configuration_identity")
    run_ids = compatible_run_ids(contract)
    if len(identity) != len(run_ids) or {row.get("run_id") for row in identity} != set(
        run_ids
    ):
        raise ValueError("exact-depth report continuation identities are incomplete")
    for row in identity:
        if payload(row).get("profile_fingerprint") != contract.get(
            "profile_fingerprint"
        ):
            raise ValueError("cohort profile fingerprint differs from policy contract")
    candidates, _, _ = evaluation_candidates(records)
    selected = tuple(
        candidate
        for candidate in candidates
        if candidate.source_run_id == contract["source_run_id"]
        and candidate.strategy_id == contract["source_strategy_id"]
        and candidate.symbol == contract["symbol"]
        and candidate.eligible
    )
    return tuple(sorted(selected, key=lambda row: row.available_time_ms))


def _policy_contract(report: Record) -> Record:
    if report.get("mode") != _POLICY_MODE:
        raise ValueError("exact-depth input is not a config-bound policy report")
    contract = mapping(report.get("contract"), "policy contract")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
        or contract.get("portfolio_pnl_claimed") is not False
    ):
        raise ValueError("policy report does not preserve report-only authority")
    for field in (
        "source_strategy_id",
        "candidate_strategy_id",
        "symbol",
        "source_run_id",
        "profile_fingerprint",
    ):
        text(contract.get(field), field)
    if number(contract.get("stop_bps"), "stop bps") <= 0.0:
        raise ValueError("stop bps must be positive")
    if number(contract.get("notional_usd"), "notional") <= 0.0:
        raise ValueError("notional must be positive")
    positive_int(contract.get("maximum_hold_minutes"), "maximum hold minutes")
    return contract


def _report(
    contract: Record,
    attempts: Sequence[Record],
    executions: Sequence[Record],
    overlapping: int,
    fee_rate: float,
) -> dict[str, object]:
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
        "summary": {
            "selected_non_overlapping": len(attempts),
            "overlapping_excluded": overlapping,
            "resolved": len(executions),
            "pending": sum(row.get("status") == "exit_pending" for row in attempts),
            "technical_incomplete": sum(
                row.get("status") not in {"resolved", "exit_pending"}
                for row in attempts
            ),
        },
        "latest_attempts": list(attempts),
        "latest_executions": list(executions),
        "limitations": [
            "recorded visible depth is not proof that a live IOC would receive the same fill",
            "book snapshots cannot observe cancellations or price changes between samples",
            "simulated PnL is descriptive and has no execution or promotion authority",
        ],
    }


def _attempt_base(candidate: SignalCandidate, contract: Record) -> dict[str, object]:
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


def _entry_fields(entry: Record, fill: Record) -> dict[str, object]:
    return {
        "entry_time_ms": book_time(entry),
        "entry_price": fill["price"],
        "position_quantity": fill["quantity"],
        "entry_notional_usd": fill["quote_usd"],
        "entry_levels_consumed": fill["levels_consumed"],
    }


def _capacity_status(prefix: str, book: Record, fill: Record) -> dict[str, object]:
    return {
        "status": f"{prefix}_capacity_insufficient",
        f"{prefix}_time_ms": book_time(book),
        f"{prefix}_filled_quantity": fill["quantity"],
        f"{prefix}_unfilled_quantity": fill["unfilled_quantity"],
    }


def _net_scope(funding_bps: float | None) -> str:
    return (
        "exact_depth_fee_and_funding"
        if funding_bps is not None
        else "exact_depth_fee_before_funding"
    )


def _rate(value: float, label: str) -> float:
    result = number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    if result >= 1.0:
        raise ValueError(f"{label} must be less than one")
    return result
