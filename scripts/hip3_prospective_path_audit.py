#!/usr/bin/env python3
"""Audit prospectively recorded HIP-3 venue paths without execution authority."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from typing import Protocol

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_events import (
    AssetContextEvent,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.data.oxa_api import validate_market_symbol
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_prospective_path_audit import (
    Hip3ProspectivePathAuditConfig,
    build_hip3_prospective_path_audit,
)

_STAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
_DEFAULT_OUTPUT = Path(f"data/logs/research/hip3_prospective_path_audit_{_STAMP}.json")


class ProspectiveArchiveReader(Protocol):
    """Read-only event archive surface used by the audit command."""

    def replay_l2(self) -> tuple[L2SnapshotEvent, ...]: ...

    def replay_trades(self) -> tuple[PublicTradeEvent, ...]: ...

    def replay_asset_contexts(self) -> tuple[AssetContextEvent, ...]: ...

    def replay_gaps(self) -> tuple[StreamGap, ...]: ...


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--timeframe-minutes", type=int, default=15)
    parser.add_argument("--maximum-mark-gap-ms", type=int, default=5_000)
    parser.add_argument("--maximum-l2-gap-ms", type=int, default=15_000)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    archive: ProspectiveArchiveReader | None = None,
    observed_at_ms: int | None = None,
) -> dict[str, object]:
    """Read one receipt-causal archive prefix and publish its coverage audit."""
    symbol = _symbol(str(args.symbol))
    data_root = Path(args.data_root)
    cutoff = (
        observed_at_ms if observed_at_ms is not None else time.time_ns() // 1_000_000
    )
    config = Hip3ProspectivePathAuditConfig(
        symbol=symbol,
        timeframe_minutes=int(args.timeframe_minutes),
        maximum_mark_gap_ms=int(args.maximum_mark_gap_ms),
        maximum_l2_gap_ms=int(args.maximum_l2_gap_ms),
    )
    reader = archive or EventArchive(
        data_root=data_root,
        symbol=symbol,
        batch_size=2_000,
    )
    report = _audit_reader(reader, config, cutoff)
    source = report["source"]
    if not isinstance(source, dict):
        raise RuntimeError("prospective path audit source must be mutable")
    source["archive_path"] = str(
        data_root / "cache" / "events" / "hyperliquid" / symbol
    )
    report["generator_identity"] = _generator_identity()
    write_immutable_json(Path(args.output), report)
    return report


def _audit_reader(
    reader: ProspectiveArchiveReader,
    config: Hip3ProspectivePathAuditConfig,
    cutoff_ms: int,
) -> dict[str, object]:
    books = tuple(
        event
        for event in reader.replay_l2()
        if event.received_ts_ns // 1_000_000 <= cutoff_ms
        and event.exchange_ts_ms <= cutoff_ms
    )
    trades = tuple(
        event
        for event in reader.replay_trades()
        if event.received_ts_ns // 1_000_000 <= cutoff_ms
        and event.exchange_ts_ms <= cutoff_ms
    )
    contexts = tuple(
        event
        for event in reader.replay_asset_contexts()
        if event.received_ts_ns // 1_000_000 <= cutoff_ms
        and event.observed_ts_ms <= cutoff_ms
    )
    gaps = tuple(
        gap
        for gap in reader.replay_gaps()
        if gap.detected_ts_ns // 1_000_000 <= cutoff_ms
    )
    return build_hip3_prospective_path_audit(
        l2_snapshots=books,
        public_trades=trades,
        asset_contexts=contexts,
        stream_gaps=gaps,
        observed_at_ms=cutoff_ms,
        config=config,
    )


def _symbol(value: str) -> str:
    dex, separator, asset = value.strip().partition(":")
    if not separator:
        raise ValueError("prospective path audit requires exact HIP-3 dex symbol")
    symbol = f"{dex.lower()}:{asset.upper()}"
    validate_market_symbol(symbol, "hip3")
    return symbol


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/hip3_prospective_path_audit.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def main() -> int:
    """Run the bounded audit and print a compact non-authoritative summary."""
    args = build_parser().parse_args()
    report = run_command(args)
    summary = {
        "ok": True,
        "output": str(Path(args.output).resolve()),
        "symbol": report["source"]["symbol"],
        "completed_bars": report["coverage"]["completed_bars"],
        "technical_assessment": report["technical_assessment"],
        "execution_authority": "none",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
