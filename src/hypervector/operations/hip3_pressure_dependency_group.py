"""Supervise required unsigned pressure observers without live execution authority."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import signal
import threading
from types import FrameType

from hypervector.live.cohort_pressure_dependencies import run_pressure_dependencies
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config


def main(argv: Sequence[str] | None = None) -> int:
    """Run public-data dependencies and stop only processes this group owns."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--log-root", type=Path, default=Path("data/logs/pressure_dependencies")
    )
    args = parser.parse_args(argv)
    config = load_multi_asset_live_config(args.config, mode="observe")
    stopped = threading.Event()

    def stop(_signal: int, _frame: FrameType | None) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    run_pressure_dependencies(
        config, log_root=args.log_root, stop_requested=stopped.is_set
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
