"""Explicit deterministic clocks for offline native polling and delayed receipts."""

from datetime import UTC, datetime, timedelta
from fractions import Fraction
import math

from hypervector.research.native_replay_events import Stamp, require_clock

MILLISECONDS_PER_SECOND = 1000
MAX_FLOAT_DRIFT_MS = Fraction(1, 1_000_000)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class ReplayClock:
    """Provide native clock callbacks without sleeping or reading wall time."""

    def __init__(self, initial_time_ms: int) -> None:
        """Start one monotonic replay with an exact representable UTC instant."""
        _utc(initial_time_ms)
        self._initial = self._current = initial_time_ms
        self._sequence = -1

    @property
    def now_ms(self) -> int:
        """Return the currently observed replay millisecond."""
        return self._current

    def now(self) -> datetime:
        """Supply the execution engine's timezone-aware wall-clock interface."""
        return _utc(self._current)

    def monotonic(self) -> float:
        """Supply elapsed replay seconds to the native poll-period controller."""
        return (self._current - self._initial) / MILLISECONDS_PER_SECOND

    def advance_to(self, observed_time_ms: int) -> None:
        """Advance causally; repeated reads at the same millisecond retain order."""
        _utc(observed_time_ms)
        if observed_time_ms < self._current:
            raise ValueError("replay clock cannot move backwards")
        if observed_time_ms != self._current:
            self._sequence = -1
        self._current = observed_time_ms

    def sleep(self, seconds: float) -> None:
        """Advance whole milliseconds, tolerating at most 1 ns of float residue."""
        if (
            type(seconds) not in (float, int)
            or seconds < 0
            or (isinstance(seconds, float) and not math.isfinite(seconds))
        ):
            raise ValueError("replay sleep requires finite nonnegative seconds")
        milliseconds = Fraction(str(seconds)) * MILLISECONDS_PER_SECOND
        rounded = round(milliseconds)
        if abs(milliseconds - rounded) > MAX_FLOAT_DRIFT_MS:
            raise ValueError("replay sleep requires whole milliseconds")
        self.advance_to(self._current + rounded)

    def next_stamp(self) -> Stamp:
        """Allocate one unambiguous receipt order at the current millisecond."""
        self._sequence += 1
        return Stamp(self._current, self._sequence)


def _utc(value: int) -> datetime:
    require_clock(value, "replay clock")
    try:
        return EPOCH + timedelta(milliseconds=value)
    except OverflowError as exc:
        raise ValueError("replay clock is outside the supported UTC datetime range") from exc
