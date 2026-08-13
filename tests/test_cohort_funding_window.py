"""Contracts for append-only cohort funding cursor evidence."""

from __future__ import annotations

import pytest

from hypervector.live.cohort_funding_window import CohortFundingWindow


def test_no_action_window_commits_initial_reconciliation_end() -> None:
    window = CohortFundingWindow(
        funding_start_time_ms=1_000,
        initial_funding_end_time_ms=2_000,
        provider_cutoff_time_ms=2_100,
        committed_funding_end_time_ms=2_000,
        next_funding_start_time_ms=2_000,
        action_count=0,
        post_action_reconciliation=False,
    )

    assert window.as_payload()["boundary_semantics"] == (
        "contiguous_cursor_with_inclusive_venue_deduplication"
    )


def test_action_window_commits_post_action_provider_cutoff() -> None:
    window = CohortFundingWindow(
        funding_start_time_ms=1_000,
        initial_funding_end_time_ms=2_000,
        provider_cutoff_time_ms=2_100,
        committed_funding_end_time_ms=2_100,
        next_funding_start_time_ms=2_100,
        action_count=2,
        post_action_reconciliation=True,
    )

    assert window.as_payload()["post_action_reconciliation"] is True


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"next_funding_start_time_ms": 1_999}, "next funding cursor"),
        ({"committed_funding_end_time_ms": 2_100}, "no-action committed end"),
        ({"action_count": 1}, "no-action window cannot contain actions"),
        ({"action_count": 1.0}, "action count must be nonnegative"),
        ({"provider_cutoff_time_ms": 1_999}, "funding window timestamps"),
    ],
)
def test_invalid_cursor_windows_fail_closed(
    changes: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "funding_start_time_ms": 1_000,
        "initial_funding_end_time_ms": 2_000,
        "provider_cutoff_time_ms": 2_100,
        "committed_funding_end_time_ms": 2_000,
        "next_funding_start_time_ms": 2_000,
        "action_count": 0,
        "post_action_reconciliation": False,
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        CohortFundingWindow(**values)
