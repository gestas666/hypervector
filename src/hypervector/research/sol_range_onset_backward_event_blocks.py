"""Immutable gap-safe candle blocks for older SOL venue-event replay."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_json,
)
from hypervector.research.sol_range_onset_backward_challenge import PreparedGapBlock


@dataclass(frozen=True)
class BackwardEventBlock:
    """One repaired candle block with clock-hour-aligned causal warmup."""

    number: int
    source_start: pd.Timestamp
    source_end: pd.Timestamp
    signal_start: pd.Timestamp
    execution_start: pd.Timestamp
    execution_rows: int
    status: str
    bars: pd.DataFrame


def prepare_backward_event_blocks(
    blocks: Sequence[PreparedGapBlock],
    *,
    warmup_hours: int,
) -> tuple[BackwardEventBlock, ...]:
    """Align repaired blocks to funding hours without bridging large gaps."""
    if not blocks:
        raise ValueError("backward event blocks must be non-empty")
    if warmup_hours < 30:
        raise ValueError("backward event blocks require at least 30 warmup hours")
    return tuple(_prepare_block(block, warmup_hours) for block in blocks)


def store_backward_event_blocks(
    output: Path,
    blocks: Sequence[BackwardEventBlock],
    *,
    source_evidence: Mapping[str, object],
) -> Path:
    """Atomically publish repaired block Parquet and a checksum manifest."""
    if not blocks:
        raise ValueError("stored backward event blocks must be non-empty")
    if not source_evidence:
        raise ValueError("stored backward event blocks require source evidence")

    def write_bundle(staging: Path) -> None:
        rows = [_write_block(staging, block) for block in blocks]
        write_json(staging / "manifest.json", _manifest(rows, source_evidence))

    publish_immutable_directory(output, write_bundle)
    return output / "manifest.json"


def _prepare_block(block: PreparedGapBlock, warmup_hours: int) -> BackwardEventBlock:
    signal_start = block.start.ceil("1h")
    execution_start = signal_start + pd.Timedelta(hours=warmup_hours)
    bars = block.bars.loc[
        (block.bars.index >= signal_start) & (block.bars.index < block.end)
    ].copy()
    _validate_cadence(bars, signal_start, block.end)
    execution_rows = int((bars.index >= execution_start).sum())
    status = "complete" if execution_rows >= 2 else "insufficient_warmup"
    return BackwardEventBlock(
        block.number,
        block.start,
        block.end,
        signal_start,
        execution_start,
        execution_rows,
        status,
        bars,
    )


def _validate_cadence(
    bars: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    expected = int((end - start) / pd.Timedelta(minutes=1))
    if len(bars) != expected or not bars.index.is_unique:
        raise ValueError("backward event block is not complete at one-minute cadence")
    if len(bars) > 1:
        deltas = bars.index.to_series().diff().iloc[1:]
        if deltas.ne(pd.Timedelta(minutes=1)).any():
            raise ValueError("backward event block contains a timestamp gap")


def _write_block(staging: Path, block: BackwardEventBlock) -> dict[str, object]:
    directory = staging / f"block-{block.number:02d}"
    directory.mkdir()
    path = directory / "bars.parquet"
    frame = block.bars.rename_axis("timestamp").reset_index()
    frame.to_parquet(path, index=False)
    return {
        "number": block.number,
        "source_start_utc": block.source_start.isoformat(),
        "source_end_utc": block.source_end.isoformat(),
        "signal_start_utc": block.signal_start.isoformat(),
        "execution_start_utc": block.execution_start.isoformat(),
        "bar_rows": len(block.bars),
        "execution_rows": block.execution_rows,
        "gap_fill_rows": int(block.bars["source"].eq("hl_gap_fill").sum()),
        "status": block.status,
        "relative_directory": str(directory.relative_to(staging)),
        "files": {"bars.parquet": file_evidence(path)},
    }


def _manifest(
    blocks: list[dict[str, object]],
    source_evidence: Mapping[str, object],
) -> dict[str, object]:
    complete = sum(block["status"] == "complete" for block in blocks)
    return {
        "schema_version": 1,
        "mode": "sol_range_onset_backward_gap_safe_event_blocks",
        "symbol": "SOL",
        "execution_authority": "none",
        "model_authority": "none",
        "place_attempted": False,
        "submitted": False,
        "block_count": len(blocks),
        "complete_block_count": complete,
        "source_evidence": dict(source_evidence),
        "blocks": blocks,
        "limitations": [
            "bounded source gaps are explicit zero-volume continuity rows",
            "large source outages remain separate and are never bridged",
            "clock-hour alignment can only be accepted after signal-population comparison",
        ],
    }
