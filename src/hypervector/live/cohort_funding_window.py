"""Typed evidence for one cohort funding-reconciliation cursor commit."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CohortFundingWindow:
    """Describe one committed funding query window without payment inference."""

    funding_start_time_ms: int
    initial_funding_end_time_ms: int
    provider_cutoff_time_ms: int
    committed_funding_end_time_ms: int
    next_funding_start_time_ms: int
    action_count: int
    post_action_reconciliation: bool

    def __post_init__(self) -> None:
        """Reject gaps, invalid ordering, and contradictory action semantics."""
        times = (
            self.funding_start_time_ms,
            self.initial_funding_end_time_ms,
            self.provider_cutoff_time_ms,
            self.committed_funding_end_time_ms,
            self.next_funding_start_time_ms,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) for value in times
        ):
            raise ValueError("funding window timestamps must be integers")
        if min(times) < 0 or not times[0] <= times[1] <= times[2]:
            raise ValueError("funding window timestamps are invalid")
        if (
            isinstance(self.action_count, bool)
            or not isinstance(self.action_count, int)
            or self.action_count < 0
        ):
            raise ValueError("funding window action count must be nonnegative")
        if not isinstance(self.post_action_reconciliation, bool):
            raise ValueError("post-action reconciliation state must be boolean")
        expected_end = times[2] if self.post_action_reconciliation else times[1]
        if self.committed_funding_end_time_ms != expected_end:
            label = "action" if self.post_action_reconciliation else "no-action"
            raise ValueError(f"{label} committed end is invalid")
        if self.next_funding_start_time_ms != self.committed_funding_end_time_ms:
            raise ValueError("next funding cursor must equal committed end")
        if self.post_action_reconciliation != (self.action_count > 0):
            raise ValueError("no-action window cannot contain actions")

    def as_payload(self) -> dict[str, object]:
        """Return deterministic append-only ledger evidence."""
        return {
            "funding_start_time_ms": self.funding_start_time_ms,
            "initial_funding_end_time_ms": self.initial_funding_end_time_ms,
            "provider_cutoff_time_ms": self.provider_cutoff_time_ms,
            "committed_funding_end_time_ms": self.committed_funding_end_time_ms,
            "next_funding_start_time_ms": self.next_funding_start_time_ms,
            "action_count": self.action_count,
            "post_action_reconciliation": self.post_action_reconciliation,
            "boundary_semantics": (
                "contiguous_cursor_with_inclusive_venue_deduplication"
            ),
        }


def committed_funding_window(
    funding_start_time_ms: int,
    initial_funding_end_time_ms: int,
    provider_cutoff_time_ms: int,
    action_count: int,
) -> CohortFundingWindow:
    """Build one cursor commit using the runner's action reconciliation rule."""
    post_action = action_count > 0
    committed_end = (
        provider_cutoff_time_ms if post_action else initial_funding_end_time_ms
    )
    return CohortFundingWindow(
        funding_start_time_ms=funding_start_time_ms,
        initial_funding_end_time_ms=initial_funding_end_time_ms,
        provider_cutoff_time_ms=provider_cutoff_time_ms,
        committed_funding_end_time_ms=committed_end,
        next_funding_start_time_ms=committed_end,
        action_count=action_count,
        post_action_reconciliation=post_action,
    )
