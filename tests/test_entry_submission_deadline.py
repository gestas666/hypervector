"""Exact boundary and invalid-clock tests for explicit entry deadlines."""

import pytest

from hypervector.live.entry_submission_deadline import (
    EntryDeadlineExpired,
    EntrySubmissionDeadline,
)


@pytest.mark.parametrize(
    "observed,expired", [(30_999, False), (31_000, False), (31_001, True)]
)
def test_exact_deadline_is_inclusive(observed: int, expired: bool) -> None:
    """Expiry uses the configured strict-greater-than millisecond rule."""
    deadline = EntrySubmissionDeadline(1_000, 30_000, lambda: observed)
    if expired:
        with pytest.raises(EntryDeadlineExpired) as caught:
            deadline.check("sdk_dispatch")
        assert caught.value.observation == deadline.last_observation
    else:
        assert deadline.check("sdk_dispatch") == deadline.last_observation
    assert deadline.last_observation.as_payload() == {
        "decision_time_ms": 1_000,
        "submission_observed_at_ms": observed,
        "submission_age_ms": observed - 1_000,
        "submission_limit_ms": 30_000,
        "submission_boundary": "sdk_dispatch",
    }


@pytest.mark.parametrize(
    "decision,limit", [(-1, 30_000), (True, 30_000), (0, 0), (0, -1), (0, True)]
)
def test_invalid_deadline_contract_is_rejected(decision: int, limit: int) -> None:
    """Invalid or boolean integers cannot weaken the configured limit."""
    with pytest.raises(ValueError):
        EntrySubmissionDeadline(decision, limit, lambda: 1_000)


@pytest.mark.parametrize("observed", [999, True, 1_001.5])
def test_invalid_observation_is_rejected(observed: int | float) -> None:
    """Future decisions and non-integer clocks are technical failures."""
    deadline = EntrySubmissionDeadline(1_000, 30_000, lambda: observed)
    with pytest.raises(ValueError):
        deadline.check("adapter_dispatch")


def test_backward_clock_is_rejected() -> None:
    """A later check cannot silently regain headroom by moving backward."""
    observations = iter((2_000, 1_999))
    deadline = EntrySubmissionDeadline(1_000, 30_000, lambda: next(observations))
    deadline.check("engine_admission")
    with pytest.raises(ValueError, match="backward"):
        deadline.check("adapter_dispatch")


def test_unchecked_deadline_has_no_success_shaped_observation() -> None:
    """Missing clock evidence is an error rather than an inferred timestamp."""
    deadline = EntrySubmissionDeadline(1_000, 30_000, lambda: 2_000)
    with pytest.raises(ValueError, match="not been checked"):
        _ = deadline.last_observation


def test_unknown_boundary_is_rejected() -> None:
    """Only the documented code boundaries can label a submission check."""
    deadline = EntrySubmissionDeadline(1_000, 30_000, lambda: 2_000)
    with pytest.raises(ValueError, match="boundary"):
        deadline.check("venue_fill")
