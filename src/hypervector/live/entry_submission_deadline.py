"""Explicit per-entry clock checks at named local dispatch boundaries."""

from collections.abc import Callable
from dataclasses import dataclass

SUBMISSION_BOUNDARIES = frozenset(
    {"engine_admission", "adapter_dispatch", "sdk_dispatch"}
)


@dataclass(frozen=True)
class EntrySubmissionObservation:
    """One observed deadline check; it does not claim venue receipt or fill."""

    decision_time_ms: int
    observed_at_ms: int
    limit_ms: int
    boundary: str

    @property
    def age_ms(self) -> int:
        """Return elapsed decision age on the explicitly supplied clock."""
        return self.observed_at_ms - self.decision_time_ms

    def as_payload(self) -> dict[str, object]:
        """Serialize the boundary actually checked without inventing an ACK."""
        return {
            "decision_time_ms": self.decision_time_ms,
            "submission_observed_at_ms": self.observed_at_ms,
            "submission_age_ms": self.age_ms,
            "submission_limit_ms": self.limit_ms,
            "submission_boundary": self.boundary,
        }


class EntryDeadlineExpired(RuntimeError):
    """An entry exceeded its existing limit before any dispatch at this boundary."""

    def __init__(self, observation: EntrySubmissionObservation) -> None:
        """Retain the exact expiry observation for routing and durable evidence."""
        self.observation = observation
        super().__init__(
            f"entry age {observation.age_ms}ms exceeds {observation.limit_ms}ms "
            f"at {observation.boundary}"
        )


class EntrySubmissionDeadline:
    """Carry one configured deadline explicitly through blocking preparation."""

    def __init__(
        self,
        decision_time_ms: int,
        limit_ms: int,
        now_ms: Callable[[], int],
    ) -> None:
        """Validate one configured deadline and retain its explicit clock source."""
        for value, minimum in ((decision_time_ms, 0), (limit_ms, 1)):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(
                    "entry decision and limit require valid integer milliseconds"
                )
        self.decision_time_ms = decision_time_ms
        self.limit_ms = limit_ms
        self._now_ms = now_ms
        self._last: EntrySubmissionObservation | None = None

    @property
    def last_observation(self) -> EntrySubmissionObservation:
        """Require a real observation rather than synthesizing clock evidence."""
        if self._last is None:
            raise ValueError("entry deadline has not been checked")
        return self._last

    def check(self, boundary: str) -> EntrySubmissionObservation:
        """Check after blocking work; equality is admitted and expiry is explicit."""
        if boundary not in SUBMISSION_BOUNDARIES:
            raise ValueError("unsupported entry submission boundary")
        observed = self._now_ms()
        if isinstance(observed, bool) or not isinstance(observed, int):
            raise ValueError("entry submission clock must return integer milliseconds")
        if observed < self.decision_time_ms:
            raise ValueError("entry submission clock precedes the decision")
        if self._last is not None and observed < self._last.observed_at_ms:
            raise ValueError("entry submission clock moved backward")
        self._last = EntrySubmissionObservation(
            self.decision_time_ms,
            observed,
            self.limit_ms,
            boundary,
        )
        if self._last.age_ms > self.limit_ms:
            raise EntryDeadlineExpired(self._last)
        return self._last
