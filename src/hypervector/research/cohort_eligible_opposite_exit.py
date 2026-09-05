"""Causal stop and opposite-intent evidence for exact-depth lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_exact_depth_books import (
    book_time,
    first_book,
    first_stop_book,
    post_entry_books,
    protective_stop_price,
)
from hypervector.research.cohort_signal_candidates import SignalCandidate

Record = Mapping[str, object]
_POLICY_EXIT_REASONS = frozenset(
    {
        "maximum_hold_seconds",
        "hard_maximum_hold_seconds",
        "maximum_hold_evidence_contract_missing",
        "maximum_hold_evidence_future",
        "maximum_hold_evidence_missing",
        "maximum_hold_evidence_stale",
    }
)


@dataclass(frozen=True)
class _PolicyExit:
    available_time_ms: int
    reason: str
    evidence: Record


@dataclass(frozen=True)
class EarlyExitEvidence:
    """Earliest observed stop proxy and eligible opposite-intent quote."""

    stop_book: Record | None
    opposite: SignalCandidate | None
    opposite_book: Record | None
    policy: _PolicyExit | None
    policy_book: Record | None

    @property
    def stop_precedes(self) -> bool:
        """Return whether stop evidence occurs before or with the intent."""
        return self.stop_book is not None and (
            self.opposite is None
            or book_time(self.stop_book) <= self.opposite.available_time_ms
        )

    @property
    def reason(self) -> str | None:
        """Return the causal exit reason when executable evidence exists."""
        selected = self._selected()
        return selected[0] if selected is not None else None

    @property
    def exit_book(self) -> Record | None:
        """Return the book consumed by the selected early exit."""
        selected = self._selected()
        return selected[1] if selected is not None else None

    @property
    def policy_selected(self) -> bool:
        """Return whether the provider policy supplies the selected exit."""
        selected = self._selected()
        return selected is not None and selected[2] == 2

    @property
    def opposite_exit_unavailable(self) -> bool:
        """Return whether an opposite signal lacks a timely exit book."""
        return (
            self.opposite is not None
            and self.opposite_book is None
            and self._unavailable_precedes_selected(self.opposite.available_time_ms)
        )

    @property
    def policy_exit_unavailable(self) -> bool:
        """Return whether a timer decision lacks a timely exit book."""
        return (
            self.policy is not None
            and self.policy_book is None
            and self._unavailable_precedes_selected(self.policy.available_time_ms)
        )

    @property
    def unavailable_status(self) -> tuple[dict[str, object], int] | None:
        """Return explicit status fields and resume time for missing depth."""
        if self.opposite_exit_unavailable and self.opposite is not None:
            return {
                "status": "opposite_signal_exit_unavailable",
                "opposite_decision_time_ms": self.opposite.decision_time_ms,
                "opposite_available_time_ms": self.opposite.available_time_ms,
            }, self.opposite.available_time_ms + 1
        if self.policy_exit_unavailable and self.policy is not None:
            return {
                "status": "policy_exit_unavailable",
                "policy_exit_time_ms": self.policy.available_time_ms,
                "policy_exit_reason": self.policy.reason,
            }, self.policy.available_time_ms + 1
        return None

    def _unavailable_precedes_selected(self, available_ms: int) -> bool:
        selected = self._selected()
        return selected is None or available_ms < book_time(selected[1])

    def _selected(self) -> tuple[str, Record, int] | None:
        choices = [
            ("protective_stop", self.stop_book, 0),
            ("opposite_strategy_intent", self.opposite_book, 1),
            (self.policy.reason if self.policy else "", self.policy_book, 2),
        ]
        available = [row for row in choices if row[1] is not None]
        return min(available, key=lambda row: (book_time(row[1]), row[2]), default=None)


def early_exit_evidence(
    *,
    entry: Record,
    entry_price: float,
    books: Sequence[Record],
    opening: SignalCandidate,
    candidates: Sequence[SignalCandidate],
    contract: Record,
    exit_delay_ms: int,
    deadline_ms: int,
) -> EarlyExitEvidence:
    """Select causal exit evidence without assigning execution economics."""
    stop_price = protective_stop_price(
        opening.side or "", entry_price, float(contract["stop_bps"])
    )
    path = post_entry_books(books, book_time(entry), deadline_ms)
    stop_book = first_stop_book(path, side=opening.side or "", stop_price=stop_price)
    opposite = _first_opposite(
        opening, candidates, book_time(entry), deadline_ms, contract
    )
    opposite_book = (
        first_book(books, opposite.available_time_ms, exit_delay_ms)
        if opposite is not None
        else None
    )
    policy = _policy_exit(opening, contract, book_time(entry), deadline_ms)
    policy_book = (
        first_book(books, policy.available_time_ms, exit_delay_ms)
        if policy is not None
        else None
    )
    return EarlyExitEvidence(stop_book, opposite, opposite_book, policy, policy_book)


def entered_early_exit_evidence(
    *,
    entry: Record,
    entry_fill: Record,
    books: Sequence[Record],
    opening: SignalCandidate,
    candidates: Sequence[SignalCandidate],
    contract: Record,
    exit_delay_ms: int,
    deadline_ms: int,
) -> EarlyExitEvidence:
    """Return early-exit evidence for an exact visible-depth entry fill."""
    return early_exit_evidence(
        entry=entry,
        entry_price=float(entry_fill["price"]),
        books=books,
        opening=opening,
        candidates=candidates,
        contract=contract,
        exit_delay_ms=exit_delay_ms,
        deadline_ms=deadline_ms,
    )


def _first_opposite(
    opening: SignalCandidate,
    candidates: Sequence[SignalCandidate],
    entry_time_ms: int,
    deadline_ms: int,
    contract: Record,
) -> SignalCandidate | None:
    if contract.get("close_on_eligible_opposite_signal") is not True:
        return None
    opposite_side = "short" if opening.side == "long" else "long"
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.side == opposite_side
            and entry_time_ms < candidate.available_time_ms <= deadline_ms
        ),
        None,
    )


def _policy_exit(
    opening: SignalCandidate,
    contract: Record,
    entry_time_ms: int,
    deadline_ms: int,
) -> _PolicyExit | None:
    raw = contract.get("policy_exits", ())
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("policy exits must be a sequence")
    selected: list[_PolicyExit] = []
    for value in raw:
        if not isinstance(value, Mapping):
            raise ValueError("policy exit rows must be mappings")
        if value.get("opening_decision_time_ms") != opening.decision_time_ms:
            continue
        selected.append(_validated_policy_exit(value, entry_time_ms, deadline_ms))
    if len(selected) > 1:
        raise ValueError("opening decision has multiple policy exits")
    return selected[0] if selected else None


def _validated_policy_exit(
    value: Record, entry_time_ms: int, deadline_ms: int
) -> _PolicyExit:
    available = value.get("available_time_ms")
    if isinstance(available, bool) or not isinstance(available, int):
        raise ValueError("policy exit availability must be an integer")
    if not entry_time_ms < available <= deadline_ms:
        raise ValueError("policy exit lies outside the open lifecycle")
    reason = value.get("reason")
    if not isinstance(reason, str) or reason not in _POLICY_EXIT_REASONS:
        raise ValueError("policy exit reason is unsupported")
    evidence = value.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("policy exit evidence must be a mapping")
    return _PolicyExit(available, reason, evidence)
