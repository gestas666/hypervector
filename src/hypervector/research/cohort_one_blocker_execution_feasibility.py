"""Causal BBO replay for a fixed exact-one-blocker cohort hypothesis."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    nonnegative_int,
    number,
    payload,
    text,
)
from hypervector.research.cohort_one_blocker_execution_contract import (
    OneBlockerExecutionContract,
    OpiCohort,
)
from hypervector.research.cohort_one_blocker_execution_liquidity import (
    entry_execution,
    exit_execution,
)
from hypervector.research.cohort_one_blocker_execution_payloads import (
    attempt_base,
    direction,
    execution_payload,
    exit_level,
    pending_attempt,
)
from hypervector.research.cohort_one_blocker_execution_summary import (
    build_execution_feasibility_payload,
)
from hypervector.research.cohort_one_blocker_execution_types import (
    Book,
    Coverage,
)
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)
from hypervector.research.market_depth_fill import DepthLevel

Record = Mapping[str, object]


def build_one_blocker_execution_feasibility(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    funding_rows: Sequence[Record],
    *,
    contract: OneBlockerExecutionContract,
) -> dict[str, object]:
    """Replay one fixed near-miss contract without granting execution authority."""
    candidates, _, _ = evaluation_candidates(cohort_records)
    books = _book_index(asset_records.get(contract.symbol, ()))
    funding = _funding_events(funding_rows)
    coverage, attempts, executions = _replay_candidates(
        candidates, books, funding, contract
    )
    return build_execution_feasibility_payload(
        contract, coverage, len(funding), attempts, executions
    )


def _replay_candidates(
    candidates: Sequence[SignalCandidate],
    books: Sequence[Book],
    funding: Sequence[tuple[int, float]],
    contract: OneBlockerExecutionContract,
) -> tuple[Coverage, list[dict[str, object]], list[dict[str, object]]]:
    coverage = Coverage(evaluations=len(candidates))
    attempts: list[dict[str, object]] = []
    executions: list[dict[str, object]] = []
    next_available_ms = -1
    for candidate in sorted(candidates, key=lambda item: item.available_time_ms):
        if not _matches(candidate, contract):
            continue
        if candidate.available_time_ms < contract.minimum_available_time_ms:
            coverage.pre_cutoff_excluded += 1
            continue
        coverage.exact_candidates += 1
        status, context = _prior_context(books, candidate, contract)
        if status != "matched" or context is None:
            setattr(
                coverage,
                f"context_{status}",
                getattr(coverage, f"context_{status}") + 1,
            )
            continue
        trade_direction = direction(candidate)
        if not _opi_in_cohort(trade_direction * context.opi, contract.opi_cohort):
            coverage.context_cohort_excluded += 1
            continue
        if candidate.available_time_ms < next_available_ms:
            continue
        coverage.selected_non_overlapping += 1
        minimum_next_signal_ms = (
            candidate.available_time_ms + contract.entry_spacing_minutes * 60_000
        )
        attempt, execution = _replay(candidate, context, books, funding, contract)
        attempts.append(attempt)
        if execution is None:
            next_available_ms = minimum_next_signal_ms
            failure = text(attempt.get("status"), "attempt failure status")
            setattr(coverage, failure, getattr(coverage, failure) + 1)
            continue
        exit_time_ms = nonnegative_int(
            execution.get("exit_time_ms"), "simulated exit time"
        )
        next_available_ms = max(minimum_next_signal_ms, exit_time_ms)
        coverage.resolved_executions += 1
        executions.append(execution)
    return coverage, attempts, executions


def _replay(
    candidate: SignalCandidate,
    context: Book,
    books: Sequence[Book],
    funding: Sequence[tuple[int, float]],
    contract: OneBlockerExecutionContract,
) -> tuple[dict[str, object], dict[str, object] | None]:
    base = attempt_base(candidate, context)
    entry = _first_at_or_after(
        books, candidate.available_time_ms, contract.maximum_entry_delay_ms
    )
    if entry is None:
        return base | {"status": "entry_missing"}, None
    entry_price, entry_size = entry_execution(entry, direction(candidate), contract)
    if entry_price * entry_size + 1e-12 < contract.notional_usd:
        return base | {"status": "entry_capacity_failures"}, None
    position_size = contract.notional_usd / entry_price
    return _replay_after_entry(
        base,
        candidate,
        context,
        books,
        funding,
        entry,
        entry_price,
        position_size,
        contract,
    )


def _replay_after_entry(
    base: dict[str, object],
    candidate: SignalCandidate,
    context: Book,
    books: Sequence[Book],
    funding: Sequence[tuple[int, float]],
    entry: Book,
    entry_price: float,
    position_size: float,
    contract: OneBlockerExecutionContract,
) -> tuple[dict[str, object], dict[str, object] | None]:
    deadline = entry.recv_ts_ms + contract.horizon_minutes * 60_000
    horizon_exit = _first_at_or_after(books, deadline, contract.maximum_exit_delay_ms)
    observed_end = horizon_exit or _latest_at_or_before(books, deadline)
    if observed_end is None:
        return base | {"status": "exit_missing"}, None
    stop_exit = _candidate_stop_exit(
        books, entry, observed_end, entry_price, candidate, contract
    )
    target_exit = _candidate_target_exit(
        books, entry, observed_end, entry_price, candidate, contract
    )
    if horizon_exit is None and stop_exit is None and target_exit is None:
        return _pending_or_missing_exit(
            base,
            candidate,
            books,
            funding,
            entry,
            entry_price,
            position_size,
            deadline,
            contract,
        )
    exit_book, exit_reason = _select_exit(stop_exit, target_exit, horizon_exit)
    return _resolve_execution(
        base,
        candidate,
        context,
        books,
        funding,
        entry,
        exit_book,
        entry_price,
        position_size,
        exit_reason,
        contract,
    )


def _pending_or_missing_exit(
    base: dict[str, object],
    candidate: SignalCandidate,
    books: Sequence[Book],
    funding: Sequence[tuple[int, float]],
    entry: Book,
    entry_price: float,
    position_size: float,
    deadline: int,
    contract: OneBlockerExecutionContract,
) -> tuple[dict[str, object], None]:
    latest = books[-1]
    if latest.recv_ts_ms < deadline:
        return pending_attempt(
            base,
            candidate,
            entry,
            latest,
            books,
            funding,
            entry_price,
            position_size,
            deadline,
            contract,
        ), None
    return base | {
        "status": "exit_missing",
        "entry_time_ms": entry.recv_ts_ms,
    }, None


def _candidate_stop_exit(
    books: Sequence[Book],
    entry: Book,
    observed_end: Book,
    entry_price: float,
    candidate: SignalCandidate,
    contract: OneBlockerExecutionContract,
) -> Book | None:
    return _first_stop_cross(
        books,
        entry,
        observed_end,
        entry_price,
        direction(candidate),
        contract.stop_proxy_bps,
    )


def _candidate_target_exit(
    books: Sequence[Book],
    entry: Book,
    observed_end: Book,
    entry_price: float,
    candidate: SignalCandidate,
    contract: OneBlockerExecutionContract,
) -> Book | None:
    if contract.target_proxy_bps is None:
        return None
    return _first_target_cross(
        books,
        entry,
        observed_end,
        entry_price,
        direction(candidate),
        contract.target_proxy_bps,
    )


def _select_exit(
    stop_exit: Book | None,
    target_exit: Book | None,
    horizon_exit: Book | None,
) -> tuple[Book, str]:
    available: list[tuple[Book, str, int]] = []
    if stop_exit is not None:
        available.append((stop_exit, "stop_proxy", 0))
    if target_exit is not None:
        available.append((target_exit, "target_proxy", 1))
    if horizon_exit is not None:
        available.append((horizon_exit, "fixed_horizon", 2))
    if not available:
        raise RuntimeError("resolved replay requires an exit book")
    book, reason, _ = min(available, key=lambda row: (row[0].recv_ts_ms, row[2]))
    return book, reason


def _resolve_execution(
    base: dict[str, object],
    candidate: SignalCandidate,
    context: Book,
    books: Sequence[Book],
    funding: Sequence[tuple[int, float]],
    entry: Book,
    exit_book: Book,
    entry_price: float,
    position_size: float,
    exit_reason: str,
    contract: OneBlockerExecutionContract,
) -> tuple[dict[str, object], dict[str, object] | None]:
    exit_price, exit_size = exit_execution(
        exit_book, direction(candidate), position_size, contract
    )
    if exit_size + 1e-12 < position_size:
        return base | {"status": "exit_capacity_failures"}, None
    execution = execution_payload(
        candidate,
        context,
        books,
        funding,
        entry,
        exit_book,
        entry_price,
        exit_price,
        position_size,
        exit_reason,
        contract,
    )
    return base | {"status": "resolved", "entry_time_ms": entry.recv_ts_ms}, execution


def _first_stop_cross(
    books: Sequence[Book],
    entry: Book,
    horizon_exit: Book,
    entry_price: float,
    direction: float,
    stop_bps: float,
) -> Book | None:
    for book in books:
        if not entry.recv_ts_ms <= book.recv_ts_ms <= horizon_exit.recv_ts_ms:
            continue
        exit_price, _ = exit_level(book, direction)
        directional_bps = direction * (exit_price / entry_price - 1.0) * 10_000.0
        if directional_bps <= -stop_bps:
            return book
    return None


def _first_target_cross(
    books: Sequence[Book],
    entry: Book,
    observed_end: Book,
    entry_price: float,
    direction: float,
    target_bps: float,
) -> Book | None:
    for book in books:
        if not entry.recv_ts_ms <= book.recv_ts_ms <= observed_end.recv_ts_ms:
            continue
        exit_price, _ = exit_level(book, direction)
        directional_bps = direction * (exit_price / entry_price - 1.0) * 10_000.0
        if directional_bps >= target_bps:
            return book
    return None


def _matches(candidate: SignalCandidate, contract: OneBlockerExecutionContract) -> bool:
    return (
        candidate.strategy_id == contract.strategy_id
        and candidate.symbol == contract.symbol
        and candidate.side in {"long", "short"}
        and not candidate.eligible
        and candidate.blockers == (contract.blocker,)
    )


def _opi_in_cohort(directional_opi: float, cohort: OpiCohort) -> bool:
    if cohort == "all":
        return True
    if cohort == "aligned":
        return directional_opi > 0.0
    return directional_opi <= 0.0


def _prior_context(
    books: Sequence[Book],
    candidate: SignalCandidate,
    contract: OneBlockerExecutionContract,
) -> tuple[str, Book | None]:
    times = [book.recv_ts_ms for book in books]
    index = bisect_right(times, candidate.available_time_ms) - 1
    if index < 0:
        return "missing", None
    book = books[index]
    if candidate.available_time_ms - book.recv_ts_ms > contract.maximum_context_age_ms:
        return "stale", None
    return "matched", book


def _first_at_or_after(
    books: Sequence[Book], target_ms: int, maximum_delay_ms: int
) -> Book | None:
    index = bisect_left([book.recv_ts_ms for book in books], target_ms)
    if index >= len(books) or books[index].recv_ts_ms - target_ms > maximum_delay_ms:
        return None
    return books[index]


def _latest_at_or_before(books: Sequence[Book], target_ms: int) -> Book | None:
    index = bisect_right([book.recv_ts_ms for book in books], target_ms) - 1
    return books[index] if index >= 0 else None


def _book_index(records: Sequence[Record]) -> tuple[Book, ...]:
    books = tuple(
        sorted(
            (_book(row) for row in event_rows(records, "book_observation")),
            key=lambda item: item.recv_ts_ms,
        )
    )
    if len({book.recv_ts_ms for book in books}) != len(books):
        raise ValueError("order-book receive timestamps must be unique")
    return books


def _book(row: Record) -> Book:
    values = payload(row)
    bids = _levels(values.get("bids"), "bid", descending=True)
    asks = _levels(values.get("asks"), "ask", descending=False)
    bid_price, bid_size = bids[0].price, bids[0].size
    ask_price, ask_size = asks[0].price, asks[0].size
    if bid_price >= ask_price:
        raise ValueError("recorded BBO must have bid below ask")
    opi = number(values.get("opi"), "book OPI")
    if not -1.0 <= opi <= 1.0:
        raise ValueError("book OPI must be within [-1, 1]")
    return Book(
        nonnegative_int(values.get("recv_ts_ms"), "book receive time"),
        opi,
        bid_price,
        bid_size,
        ask_price,
        ask_size,
        bids,
        asks,
    )


def _levels(value: object, label: str, *, descending: bool) -> tuple[DepthLevel, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValueError(f"book {label}s must contain a top level")
    levels: list[DepthLevel] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError(f"book {label} level must be a mapping")
        levels.append(
            DepthLevel(
                number(raw.get("price"), f"{label} price"),
                number(raw.get("size"), f"{label} size"),
            )
        )
    prices = tuple(level.price for level in levels)
    ordered = all(
        left > right if descending else left < right
        for left, right in zip(prices, prices[1:])
    )
    if not ordered:
        raise ValueError(f"book {label} levels must be strictly ordered")
    return tuple(levels)


def _funding_events(rows: Sequence[Record]) -> tuple[tuple[int, float], ...]:
    if any(row.get("source") != "hl_funding_history" for row in rows):
        raise ValueError("funding rows must come from official Hyperliquid history")
    events = tuple(
        sorted(
            (
                nonnegative_int(row.get("event_ts_ms"), "funding event time"),
                number(row.get("funding_rate"), "funding rate"),
            )
            for row in rows
        )
    )
    if len({event[0] for event in events}) != len(events):
        raise ValueError("funding event timestamps must be unique")
    return events
