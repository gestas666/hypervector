"""Run the standalone, unsigned ``xyz:MU`` breakout shadow observer."""

from __future__ import annotations

import argparse
from pathlib import Path

from hypervector.live.hip3_breakout_shadow_observer import (
    ObserverConfig as ObserverConfig,
    ObserverDefaults,
    build_parser as _build_parser,
    config_from_args as config_from_args,
    main_for,
    run_observer as run_observer,
)
from hypervector.live.mu_hip3_breakout_shadow import MU_SHADOW_SPEC


MU_DEFAULTS = ObserverDefaults(
    asset=Path("data/live/research/xyz:mu_breakout_shadow.jsonl"),
    cohort=Path("data/live/research/mu_unused_cohort.jsonl"),
    cursor=Path("data/runtime/research/mu_hip3_breakout_shadow_cursor.json"),
    journal=Path("data/live/research/mu_hip3_breakout_shadow.jsonl"),
    status=Path("data/runtime/research/mu_hip3_breakout_shadow_latest.json"),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the backward-compatible exact MU observer parser."""
    return _build_parser(MU_DEFAULTS)


def main() -> int:
    """Run the exact MU report-only observer."""
    return main_for(MU_SHADOW_SPEC, MU_DEFAULTS)


if __name__ == "__main__":
    raise SystemExit(main())
