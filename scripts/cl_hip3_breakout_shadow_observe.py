"""Run the standalone, unsigned ``xyz:CL`` breakout shadow observer."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.hip3_breakout_shadow_observer import ObserverDefaults, main_for
from hypervector.live.mu_hip3_breakout_shadow import CL_SHADOW_SPEC


DEFAULTS = ObserverDefaults(
    asset=Path("data/live/research/xyz:cl_breakout_shadow.jsonl"),
    cohort=Path("data/live/research/cl_unused_cohort.jsonl"),
    cursor=Path("data/runtime/research/cl_hip3_breakout_shadow_cursor.json"),
    journal=Path("data/live/research/cl_hip3_breakout_shadow.jsonl"),
    status=Path("data/runtime/research/cl_hip3_breakout_shadow_latest.json"),
)


def main() -> int:
    """Run the exact CL report-only observer."""
    return main_for(CL_SHADOW_SPEC, DEFAULTS)


if __name__ == "__main__":
    raise SystemExit(main())
