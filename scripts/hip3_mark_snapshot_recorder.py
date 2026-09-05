#!/usr/bin/env python3
"""Record periodic public HIP-3 mark snapshots without execution authority."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import json
from pathlib import Path
import signal
import sys
import threading
from types import FrameType
from typing import cast

from hypervector.data.hip3_mark_snapshot_recorder import (
    Hip3ContextInfoProtocol,
    Hip3MarkRecorderConfig,
    run_hip3_mark_recorder,
)
from hypervector.research.checkpoint_storage import write_atomic_json

_DEFAULT_SYMBOLS = ("xyz:SP500", "xyz:SPCX")
_DEFAULT_STATUS = Path("data/runtime/research/hip3_index_mark_recorder_latest.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the unsigned archive-only recorder parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--status-seconds", type=float, default=30.0)
    parser.add_argument("--flush-seconds", type=float, default=30.0)
    parser.add_argument("--archive-batch-size", type=int, default=1_000)
    parser.add_argument("--max-polls", type=int)
    parser.add_argument("--status-output", type=Path, default=_DEFAULT_STATUS)
    return parser


def config_from_args(args: argparse.Namespace) -> Hip3MarkRecorderConfig:
    """Resolve exact CLI values into a validated recorder contract."""
    return Hip3MarkRecorderConfig(
        symbols=tuple(args.symbols or _DEFAULT_SYMBOLS),
        data_root=Path(args.data_root),
        poll_seconds=float(args.poll_seconds),
        status_seconds=float(args.status_seconds),
        flush_seconds=float(args.flush_seconds),
        archive_batch_size=int(args.archive_batch_size),
        max_polls=args.max_polls,
    )


def official_info(dex: str) -> Hip3ContextInfoProtocol:
    """Construct only the official unsigned public Info reader."""
    try:
        from hyperliquid.info import Info  # type: ignore[import-untyped]
        from hyperliquid.utils.constants import (  # type: ignore[import-untyped]
            MAINNET_API_URL,
        )
    except ImportError as exc:
        raise RuntimeError("official Hyperliquid SDK is unavailable") from exc
    return cast(
        Hip3ContextInfoProtocol,
        Info(
            MAINNET_API_URL,
            skip_ws=True,
            perp_dexs=[dex],
            timeout=20.0,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run until bounded completion or an operator process signal."""
    args = build_parser().parse_args(argv)
    config = config_from_args(args)
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stopping.set()

    previous = {
        signal.SIGINT: signal.signal(signal.SIGINT, request_stop),
        signal.SIGTERM: signal.signal(signal.SIGTERM, request_stop),
    }
    try:
        run_hip3_mark_recorder(
            config,
            info=official_info(config.dex),
            stop_requested=stopping.is_set,
            status_sink=status_sink(Path(args.status_output)),
        )
    finally:
        for current, handler in previous.items():
            signal.signal(current, handler)
    return 0


def _print_status(row: dict[str, object]) -> None:
    print(json.dumps(row, separators=(",", ":"), sort_keys=True), flush=True)


def status_sink(path: Path) -> Callable[[dict[str, object]], None]:
    """Return a sink that prints and atomically stores safe capture health."""

    def persist(row: dict[str, object]) -> None:
        if (
            row.get("execution_authority") != "none"
            or row.get("report_only") is not True
        ):
            raise ValueError("HIP-3 mark status must remain authority-none")
        _print_status(row)
        write_atomic_json(path, row)

    return persist


if __name__ == "__main__":
    sys.exit(main())
