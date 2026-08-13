"""Run the standalone, unsigned ``xyz:SKHX`` breakout shadow observer."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.hip3_breakout_shadow_observer import (
    ObserverDefaults,
    main_for,
)
from hypervector.live.mu_hip3_breakout_shadow import SKHX_SHADOW_SPEC


SKHX_DEFAULTS = ObserverDefaults(
    asset=Path("data/live/research/xyz:skhx_breakout_shadow.jsonl"),
    cohort=Path("data/live/research/skhx_unused_cohort.jsonl"),
    cursor=Path("data/runtime/research/skhx_hip3_breakout_shadow_cursor.json"),
    journal=Path("data/live/research/skhx_hip3_breakout_shadow.jsonl"),
    status=Path("data/runtime/research/skhx_hip3_breakout_shadow_latest.json"),
)


def main() -> int:
    """Run the exact SKHX report-only observer."""
    return main_for(SKHX_SHADOW_SPEC, SKHX_DEFAULTS)


if __name__ == "__main__":
    raise SystemExit(main())
