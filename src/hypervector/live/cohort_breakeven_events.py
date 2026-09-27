"""Durable event names for venue break-even raises, free of runtime imports.

An accepted raise is journaled as ``protective_stop_raised``. Its
``venue_visible`` field records only that the position was still open when the
engine's bounded post-modify wait ended. The wait returns its last observation
even when the replacement stop never appeared, so the field does not prove the
new stop was seen resting on the venue. The reconcile that follows every
executed action is the fail-closed backstop: it verifies the owned stop against
venue truth.
"""

from __future__ import annotations

BREAKEVEN_ATTEMPT_EVENT = "breakeven_stop_attempt"
BREAKEVEN_SKIPPED_EVENT = "breakeven_stop_skipped"
RAISE_EXHAUSTED_EVENT = "protective_stop_raise_exhausted"
BREAKEVEN_EVENTS = frozenset(
    {BREAKEVEN_ATTEMPT_EVENT, BREAKEVEN_SKIPPED_EVENT, RAISE_EXHAUSTED_EVENT}
)
