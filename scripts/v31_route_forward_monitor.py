#!/usr/bin/env python3
"""Continuously refresh the execution-incapable v31 route tracker."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from hypervector.research.route_forward_monitor import (
    RouteForwardMonitorSpec,
    build_route_monitor_parser,
    record_material_change,
    route_monitor_main,
    route_tracker_command,
    run_route_monitor,
)
from hypervector.research.v31_route_change_journal import append_v31_material_change

_SPEC = RouteForwardMonitorSpec(
    label="v31 route-forward monitor",
    event="v31_route_forward_refresh",
    tracker=Path(__file__).resolve().with_name("v31_route_forward.py"),
    checkpoint=Path("data/runtime/bidirectional_cohort/latest_checkpoint.json"),
    journal=Path("docs/research-journal/hip3-route-authority-pruning-v1.json"),
    source_config=Path(
        "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml"
    ),
    candidate_config=Path(
        "configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml"
    ),
    output=Path("data/runtime/bidirectional_cohort/latest_v31_route_forward.json"),
    change_journal=Path(
        "data/logs/research/bidirectional_cohort/v31_route_material_changes.jsonl"
    ),
    change_recorder=partial(
        record_material_change, appender=append_v31_material_change
    ),
)

build_parser = partial(build_route_monitor_parser, _SPEC)
tracker_command = partial(route_tracker_command, _SPEC)
run_monitor = partial(run_route_monitor, _SPEC)


if __name__ == "__main__":
    raise SystemExit(route_monitor_main(_SPEC))
