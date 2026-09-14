"""Stable offline event ordering across native acquisition and SDK response waits."""

from collections.abc import Callable
from datetime import datetime
from heapq import heappop, heappush

from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_events import Stamp, require_clock, require_name


class ReplayTimeline:
    """Advance existing economic fills before each declared external event at that clock."""

    def __init__(self, clock: ReplayClock, advance_economics: Callable[[int], None]) -> None:
        """Require a raw clock and economic advancement function without timeline recursion."""
        self.clock, self._advance = clock, advance_economics
        self._events: list[tuple[int, int, str, Callable[[], None]]] = []
        self._identities: set[str] = set()
        self._dispatching = False

    def schedule(self, time_ms: int, identity: str, apply: Callable[[], None]) -> None:
        """Schedule one unique explicit observation or settlement in stable insertion order."""
        require_clock(time_ms, "scheduled event time")
        require_name(identity, "scheduled event identity")
        if time_ms < self.clock.now_ms or identity in self._identities or not callable(apply):
            raise ValueError("replay event requires a future/current clock, unique ID and callback")
        heappush(self._events, (time_ms, len(self._identities), identity, apply))
        self._identities.add(identity)

    def advance_to(self, time_ms: int) -> None:
        """Apply every intermediate event; a failed callback remains pending and propagates."""
        require_clock(time_ms, "timeline advance time")
        if self._dispatching or time_ms < self.clock.now_ms:
            raise ValueError("replay timeline cannot recurse or move backwards")
        self._dispatching = True
        try:
            while self._events and self._events[0][0] <= time_ms:
                at_ms, _, _, apply = self._events[0]
                self._advance(at_ms)
                apply()
                if self.clock.now_ms != at_ms:
                    raise ValueError(
                        "scheduled callback cannot independently advance the raw clock"
                    )
                heappop(self._events)
            self._advance(time_ms)
        finally:
            self._dispatching = False


class ReplayRuntimeClock(ReplayClock):
    """Native clock interface whose waits process the shared economic event timeline."""

    def __init__(self, timeline: ReplayTimeline) -> None:
        """Delegate all clock state to the timeline; no second independently moving clock."""
        self.timeline = timeline

    @property
    def now_ms(self) -> int:
        """Read the one underlying exact economic clock."""
        return self.timeline.clock.now_ms

    def now(self) -> datetime:
        """Read the native timezone-aware observation time."""
        return self.timeline.clock.now()

    def monotonic(self) -> float:
        """Read elapsed time since the underlying clock's original activation."""
        return self.timeline.clock.monotonic()

    def advance_to(self, observed_time_ms: int) -> None:
        """Advance acquisition or runner time through every scheduled event."""
        self.timeline.advance_to(observed_time_ms)

    def sleep(self, seconds: float) -> None:
        """Reuse exact native duration validation before dispatching events during a wait."""
        duration = ReplayClock(self.now_ms)
        duration.sleep(seconds)
        self.advance_to(duration.now_ms)

    def next_stamp(self) -> Stamp:
        """Allocate a shared economic sequence number, without a private counter."""
        return self.timeline.clock.next_stamp()
