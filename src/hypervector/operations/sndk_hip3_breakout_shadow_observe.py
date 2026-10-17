"""Run the unsigned SNDK v4 observer with durable prior pressure state."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from hypervector.live.hip3_breakout_shadow_observer import ObserverDefaults, main_for
from hypervector.live.hip3_breakout_shadow_specs import SNDK_SHADOW_SPEC
from hypervector.live.hip3_fresh15_journal_contracts import (
    DEFAULT_JOURNALS,
    DEFAULT_OBSERVER_STATES,
)

DEFAULTS = ObserverDefaults(
    asset=Path("data/live/research/xyz:sndk_fresh15_v4.jsonl"),
    cohort=Path("data/live/research/xyz_sndk_unused_cohort.jsonl"),
    cursor=DEFAULT_OBSERVER_STATES[SNDK_SHADOW_SPEC.symbol][1],
    journal=DEFAULT_JOURNALS[SNDK_SHADOW_SPEC.symbol],
    status=DEFAULT_OBSERVER_STATES[SNDK_SHADOW_SPEC.symbol][0],
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one exact public-data observer without any live execution flags."""
    return main_for(SNDK_SHADOW_SPEC, DEFAULTS, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
