"""Argument parsing and validation options for the cohort TUI supervisor."""

from __future__ import annotations

import argparse
from pathlib import Path

from typing import Literal

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
)

_DEFAULT_BACKTEST_LAB = Path("../backtest-lab/backtest_lab")
_DEFAULT_STARTUP_TIMEOUT_SECONDS = 900.0


def build_parser() -> argparse.ArgumentParser:
    """Build an observe-default and explicitly armed live supervisor."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("observe", "monitor", "live"),
        default="observe",
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--staged-config",
        type=Path,
        help="optional report-only next profile to compare with the active monitor ledger",
    )
    parser.add_argument(
        "--growth-preflight",
        type=Path,
        help="optional read-only sizing evidence for the staged monitor profile",
    )
    parser.add_argument(
        "--backtest-lab-root",
        type=Path,
        default=_DEFAULT_BACKTEST_LAB,
    )
    parser.add_argument("--tui-bin", type=Path)
    parser.add_argument("--tui-bin-sha256")
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--i-accept-live-risk", action="store_true")
    parser.add_argument("--accounting-epoch-bundle", type=Path)
    parser.add_argument("--resume-transition-drain", action="store_true")
    parser.add_argument("--refresh-ms", type=int, default=500)
    parser.add_argument(
        "--startup-timeout-seconds",
        type=float,
        default=_DEFAULT_STARTUP_TIMEOUT_SECONDS,
    )
    return parser


def validate_launch_args(
    args: argparse.Namespace,
    mode: Literal["observe", "live"],
    config: MultiAssetLiveConfig,
    staged_config: MultiAssetLiveConfig | None,
    credentials_present: bool,
) -> None:
    """Validate configured mode, telemetry options and existing live authority."""
    if (
        staged_config is not None
        and staged_config.cohort_ledger != config.cohort_ledger
    ):
        raise MultiAssetLiveConfigError(
            "active and staged profiles must use the same cohort ledger"
        )
    if mode == "live":
        config.require_live_start(credentials_present=credentials_present)
    elif args.resume_transition_drain:
        raise MultiAssetLiveConfigError("transition drain recovery requires live mode")
    if args.startup_timeout_seconds <= 0.0 or args.refresh_ms < 100:
        raise MultiAssetLiveConfigError("invalid TUI refresh or startup timeout")
    if args.mode == "observe" and args.accounting_epoch_bundle is not None:
        raise MultiAssetLiveConfigError(
            "--accounting-epoch-bundle requires live or monitor mode"
        )
