"""Run an execution-incapable Hyperliquid mainnet SOL canary preflight."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from hypervector.live.hyperliquid_sol_factory import (
    SolSdkFactoryError,
    create_read_only_sol_reader,
)
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.live.sol_range_onset_config import (
    SolCanaryConfigError,
    load_sol_range_onset_config,
)
from hypervector.live.sol_range_onset_read_only_preflight import (
    collect_sol_read_only_preflight,
)
from hypervector.runtime_env import load_wallet_env_if_present

_DEFAULT_CONFIG = Path("configs/sol_range_onset_canary.toml")


def build_parser() -> argparse.ArgumentParser:
    """Build the public-wallet-only preflight command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    return parser


def run_preflight(args: argparse.Namespace) -> int:
    """Read mainnet account and venue state without constructing Exchange."""
    config = load_sol_range_onset_config(args.config, mode="shadow")
    reader = create_read_only_sol_reader()
    report = collect_sol_read_only_preflight(
        config=config,
        reader=reader,
        observed_at=datetime.now(UTC),
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    canary = report["canary"]
    if not isinstance(canary, dict):
        raise RuntimeError("preflight report omitted canary readiness")
    return 0 if canary.get("technically_ready") is True else 3


def main() -> int:
    """Load only public wallet identity and run sanitized preflight."""
    load_wallet_env_if_present()
    try:
        return run_preflight(build_parser().parse_args())
    except (SolCanaryConfigError, SolSdkFactoryError, HyperliquidAdapterError) as exc:
        print(f"read-only preflight failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
