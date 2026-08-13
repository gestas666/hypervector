#!/usr/bin/env python3
"""Publish gap-checked source-follow candles from warm-up plus live telemetry."""

from __future__ import annotations

import argparse
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.paper.report import load_decision_rows
from hypervector.research.hypertrader_source_adapter import (
    load_hyperliquid_candles,
)
from hypervector.research.source_follow_live_parity import (
    LiveCandleAssembly,
    assemble_source_follow_live_candles,
)
from hypervector.strategies.source_follow_profile import load_source_follow_profile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--warmup-bars", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--metadata-out", type=Path, required=True)
    return parser


def _experiment_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "runtime_strategy_changed": False,
        "execution_authority": "none",
    }


def _publish(args: argparse.Namespace) -> dict[str, object]:
    _validate_outputs(args.out, args.metadata_out)
    profile = load_source_follow_profile(args.profile)
    warmup = load_hyperliquid_candles([args.warmup_bars])
    rows = load_decision_rows(args.decisions)
    _validate_no_submit(rows, profile.profile_id)
    assembly = assemble_source_follow_live_candles(
        warmup,
        rows,
        profile.profile_id,
    )
    frame = assembly.candles.rename_axis("timestamp").reset_index()
    published = False
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(args.out, index=False)
        metadata = _metadata(
            args, profile.profile_id, profile.source_revision, assembly
        )
        write_immutable_json(args.metadata_out, metadata)
        published = True
        return metadata
    finally:
        if not published:
            args.out.unlink(missing_ok=True)


def _metadata(
    args: argparse.Namespace,
    profile_id: str,
    source_revision: str,
    assembly: LiveCandleAssembly,
) -> dict[str, object]:
    candles = assembly.candles
    return {
        **_experiment_contract(),
        "profile_id": profile_id,
        "source_revision": source_revision,
        "warmup": file_evidence(args.warmup_bars),
        "decisions": file_evidence(args.decisions),
        "output": file_evidence(args.out),
        "candles": len(candles),
        "start_utc": candles.index[0].isoformat(),
        "end_utc": candles.index[-1].isoformat(),
        "appended_rows": assembly.appended_rows,
        "trailing_rows_discarded": assembly.trailing_rows_discarded,
    }


def _validate_no_submit(rows: list[dict[str, object]], profile_id: str) -> None:
    matching = [row for row in rows if row.get("profile_id") == profile_id]
    if any(row.get("submitted") is True for row in matching):
        raise RuntimeError("source-follow shadow ledger contains submitted=true")
    if any(row.get("place_attempted") is True for row in matching):
        raise RuntimeError("source-follow shadow ledger contains place_attempted=true")


def _validate_outputs(out: Path, metadata_out: Path) -> None:
    existing = [path for path in (out, metadata_out) if path.exists()]
    if existing:
        raise FileExistsError(f"immutable live candle output exists: {existing[0]}")


def main(argv: list[str] | None = None) -> int:
    """Publish immutable completed candles without changing strategy authority."""
    args = _parser().parse_args(argv)
    metadata = _publish(args)
    print(
        f"wrote candles={args.out} metadata={args.metadata_out} "
        f"rows={metadata['candles']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
