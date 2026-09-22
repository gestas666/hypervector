"""Reproduce the live runner's own runtime validation for a profile, offline.

Report-only. execution_authority: none. No credentials, no venue client.

The configuration loader, the read-only preflight and the observe-mode runner all
accept shapes that ``MultiAssetLiveRunner`` refuses at construction through
``validate_runtime`` — for example a ``sizing_overrides`` table on a provider
whose ``execution_symbols`` is empty. On 2026-09-22 that gap cost a 13-minute
armed startup (prestart backup plus full ledger replay) that ended in
``provider entry sizing exceeds executable provider-symbol scope``.

This script builds exactly the arguments ``scripts/multi_asset_bidirectional_live.py``
hands to the runner — using the same ``build_router`` and the same config-derived
mappings — and calls ``validate_runtime`` with placeholder engines, which the
validator inspects only by key. Run it before every armed start.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from hypervector.live.cohort_execution_plan_validation import CohortExecutionPlanError
from hypervector.live.cohort_runtime_preflight import validate_runtime_configuration
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_runner_support import (
    MultiAssetLiveRunnerError,
)


def check(config_path: Path, *, mode: str) -> list[str]:
    """Return the runtime validator's objections for one profile, if any."""
    armed = mode == "live"
    config = load_multi_asset_live_config(
        config_path, mode=mode, enabled=armed, accepts_live_risk=armed
    )
    problems: list[str] = []
    try:
        validate_runtime_configuration(config)
    except MultiAssetLiveRunnerError as exc:
        problems.append(str(exc))
    return problems


def main() -> int:
    """Exit 0 only when the runner would accept the profile."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=("observe", "live"), default="live")
    args = parser.parse_args()
    try:
        problems = check(args.config, mode=args.mode)
    except (
        MultiAssetLiveConfigError,
        CohortExecutionPlanError,
        FileNotFoundError,
        ValueError,
    ) as exc:
        # Exit 1 is reserved for collected runner objections. Every loader refusal
        # reports 2, exactly as the armed entrypoint does, so an operator can tell
        # "this profile is unloadable" from "the runner would refuse it".
        print(f"loader refused: {exc}", file=sys.stderr)
        return 2
    if problems:
        for problem in problems:
            print(f"runtime validator would refuse: {problem}", file=sys.stderr)
        return 1
    print(f"runtime validator accepts {args.config} in {args.mode} mode")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
