#!/usr/bin/env python3
"""Publish bounded report-only telemetry for the v33 route retirement."""

from __future__ import annotations

from functools import partial

from hypervector.research.route_forward_command import (
    V33_ROUTE_COMMAND_SPEC,
    build_route_forward_parser,
    route_forward_main,
    route_forward_summary,
    run_route_forward,
)

build_parser = partial(build_route_forward_parser, V33_ROUTE_COMMAND_SPEC)
run = partial(run_route_forward, V33_ROUTE_COMMAND_SPEC)
command_summary = route_forward_summary


if __name__ == "__main__":
    raise SystemExit(route_forward_main(V33_ROUTE_COMMAND_SPEC))
