"""Accounting helpers for report-only HYPE-native prospective lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from hypervector.research.cohort_exact_depth_books import (
    book_time,
    directional_return_bps,
    visible_depth_fill,
)
from hypervector.research.cohort_signal_candidates import SignalCandidate

Record = Mapping[str, object]


def attempt_payload(candidate: SignalCandidate, status: str) -> dict[str, object]:
    """Serialize one eligible signal's prospective handling result."""
    return {
        "decision_time_ms": candidate.decision_time_ms,
        "available_time_ms": candidate.available_time_ms,
        "side": candidate.side,
        "status": status,
    }


def lifecycle_payload(
    candidate: SignalCandidate,
    entry: Record,
    entry_fill: Record,
    current: Record,
    exit_book: Record | None,
    exit_reason: str | None,
    stop_price: float,
    books: Sequence[Record],
    spec: object,
) -> dict[str, object]:
    """Serialize one finite-depth proxy lifecycle without claiming venue fills."""
    entry_time = book_time(entry)
    current_time = book_time(current)
    gap = _maximum_gap(books, entry_time, current_time)
    path_resolved = gap <= int(getattr(spec, "maximum_book_gap_ms"))
    current_outcome = _outcome(entry_fill, current, spec)
    favorable, adverse = _excursions(entry_fill, books, entry_time, current_time)
    resolved_outcome = current_outcome if exit_book is not None else None
    status = _lifecycle_status(exit_reason, exit_book, path_resolved)
    deadline = entry_time + int(getattr(spec, "maximum_hold_seconds")) * 1_000
    return {
        "status": status,
        "side": candidate.side,
        "decision_time_ms": candidate.decision_time_ms,
        "entry_book_time_ms": entry_time,
        "entry_price": entry_fill["price"],
        "entry_quantity": entry_fill["quantity"],
        "entry_levels_consumed": entry_fill["levels_consumed"],
        "stop_price": stop_price,
        "exit_reason": exit_reason,
        "exit_book_time_ms": book_time(exit_book) if exit_book is not None else None,
        "occupancy_end_time_ms": book_time(exit_book) if exit_book else deadline,
        "net_pnl_usd_before_funding": _net(resolved_outcome),
        "funding_bps": None,
        "mark_stop_truth": "unavailable",
        "current_book_time_ms": current_time,
        "current_outcome": current_outcome,
        "maximum_favorable_excursion_bps": favorable,
        "maximum_adverse_excursion_bps": adverse,
        "entry_context": dict(candidate.metrics),
        "maximum_book_gap_ms": gap,
        "technical_path_resolved": path_resolved,
    }


def report_status(
    entries: Sequence[SignalCandidate], lifecycles: Sequence[Record]
) -> str:
    """Classify the evidence window without success-shaped defaults."""
    if not entries:
        return "waiting_for_first_eligible_long"
    if not lifecycles:
        return "eligible_entry_without_executable_depth"
    if any(row.get("technical_path_resolved") is not True for row in lifecycles):
        return "technical_evidence_unresolved"
    if any(row.get("exit_book_time_ms") is None for row in lifecycles):
        return "tracking_open_lifecycle"
    return "resolved_proxy_lifecycle_evidence_available"


def proxy_summary(lifecycles: Sequence[Record]) -> dict[str, object]:
    """Summarize only technically resolved, closed proxy lifecycles."""
    values = [
        _number(row.get("net_pnl_usd_before_funding"), "lifecycle net PnL")
        for row in lifecycles
        if row.get("technical_path_resolved") is True
        and row.get("exit_book_time_ms") is not None
    ]
    if not values:
        return _empty_summary()
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value <= 0.0]
    net = sum(values)
    return {
        "trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "net_pnl_usd_before_funding": net,
        "net_pnl_usd_before_funding_excluding_largest_winner": (
            net - max(wins) if wins else net
        ),
        "profit_factor_before_funding": _profit_factor(wins, losses),
    }


def _outcome(entry_fill: Record, exit_book: Record, spec: object) -> dict[str, object]:
    quantity = _number(entry_fill.get("quantity"), "entry quantity")
    exit_fill = visible_depth_fill(
        exit_book, position_side="long", notional=0.0, quantity=quantity
    )
    if exit_fill.get("complete") is not True:
        raise ValueError("prospective HYPE exit exceeds recorded depth")
    entry_price = _number(entry_fill.get("price"), "entry price")
    exit_price = _number(exit_fill.get("price"), "exit price")
    gross = quantity * (exit_price - entry_price)
    turnover = _number(entry_fill.get("quote_usd"), "entry quote") + _number(
        exit_fill.get("quote_usd"), "exit quote"
    )
    fee = turnover * _number(getattr(spec, "fee_bps_per_side"), "fee bps") / 10_000
    slip = (
        turnover
        * _number(getattr(spec, "residual_slippage_bps_per_side"), "slippage bps")
        / 10_000
    )
    net = gross - fee - slip
    return {
        "exit_price": exit_price,
        "exit_levels_consumed": exit_fill["levels_consumed"],
        "gross_return_bps": directional_return_bps("long", entry_price, exit_price),
        "fee_usd": fee,
        "residual_slippage_usd": slip,
        "net_pnl_usd": net,
    }


def _lifecycle_status(
    exit_reason: str | None, exit_book: Record | None, path_resolved: bool
) -> str:
    if not path_resolved:
        return "technical_evidence_unresolved"
    if exit_book is None:
        return "open_pending_exit"
    if exit_reason == "protective_stop_bbo_proxy":
        return "resolved_bbo_stop_proxy_mark_trigger_unverified"
    return f"resolved_{exit_reason}_proxy"


def _excursions(
    entry_fill: Record,
    books: Sequence[Record],
    start_ms: int,
    end_ms: int,
) -> tuple[float, float]:
    entry_price = _number(entry_fill.get("price"), "entry price")
    quantity = _number(entry_fill.get("quantity"), "entry quantity")
    returns: list[float] = []
    for book in books:
        if not start_ms <= book_time(book) <= end_ms:
            continue
        fill = visible_depth_fill(
            book, position_side="long", notional=0.0, quantity=quantity
        )
        if fill.get("complete") is not True:
            raise ValueError("prospective HYPE excursion exceeds recorded depth")
        exit_price = _number(fill.get("price"), "excursion exit price")
        returns.append(directional_return_bps("long", entry_price, exit_price))
    return max([0.0, *returns]), max([0.0, *(-value for value in returns)])


def _maximum_gap(books: Sequence[Record], start_ms: int, end_ms: int) -> int:
    times = [book_time(row) for row in books if start_ms <= book_time(row) <= end_ms]
    return max((right - left for left, right in zip(times, times[1:])), default=0)


def _net(outcome: Record | None) -> float | None:
    return None if outcome is None else _number(outcome.get("net_pnl_usd"), "net PnL")


def _profit_factor(wins: Sequence[float], losses: Sequence[float]) -> float | None:
    gross_loss = -sum(losses)
    return None if gross_loss <= 0.0 else sum(wins) / gross_loss


def _empty_summary() -> dict[str, object]:
    return {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "net_pnl_usd_before_funding": None,
        "net_pnl_usd_before_funding_excluding_largest_winner": None,
        "profit_factor_before_funding": None,
    }


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result
