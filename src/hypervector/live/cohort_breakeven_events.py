"""Durable event names for venue break-even raises, free of runtime imports."""

from __future__ import annotations

BREAKEVEN_ATTEMPT_EVENT = "breakeven_stop_attempt"
BREAKEVEN_SKIPPED_EVENT = "breakeven_stop_skipped"
RAISE_EXHAUSTED_EVENT = "protective_stop_raise_exhausted"
BREAKEVEN_EVENTS = frozenset(
    {BREAKEVEN_ATTEMPT_EVENT, BREAKEVEN_SKIPPED_EVENT, RAISE_EXHAUSTED_EVENT}
)
