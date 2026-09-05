"""Frozen append-only sources for HIP-3 shadow lifecycle replay."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.jsonl_prefix import (
    read_jsonl_prefix,
    require_jsonl_prefix_unchanged,
)
from hypervector.research.hip3_shadow_lifecycle_sources import (
    FrozenHyperliquidL2Archive,
    FrozenHip3MarkArchive,
)


def test_complete_jsonl_prefix_ignores_partial_tail_and_allows_append(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    first = json.dumps({"id": 1}) + "\n"
    path.write_text(first + '{"id":2', encoding="utf-8")

    rows, evidence = read_jsonl_prefix(path, "events")
    path.write_text(first + json.dumps({"id": 2}) + "\n", encoding="utf-8")

    assert rows == ({"id": 1},)
    require_jsonl_prefix_unchanged(path, evidence, "events")


def test_jsonl_prefix_rewrite_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps({"id": 1}) + "\n", encoding="utf-8")
    _rows, evidence = read_jsonl_prefix(path, "events")
    path.write_text(json.dumps({"id": 2}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="prefix changed"):
        require_jsonl_prefix_unchanged(path, evidence, "events")


def test_mark_archive_binds_exact_files_and_receipt_window(tmp_path: Path) -> None:
    start_ms = 1_800_000_000_000
    part = _mark_part(tmp_path, start_ms)
    source = FrozenHip3MarkArchive()

    rows, evidence = source.load(
        data_root=tmp_path,
        symbol="xyz:MU",
        start_ms=start_ms,
        end_ms=start_ms + 2_000,
    )

    assert [row["observed_ts_ms"] for row in rows] == [start_ms, start_ms + 1_000]
    assert evidence["rows"] == 2
    source.require_unchanged(evidence)
    part.write_bytes(part.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="archive changed"):
        source.require_unchanged(evidence)


def test_mark_archive_excludes_and_counts_supplemental_rest_rows(
    tmp_path: Path,
) -> None:
    """Only exact WebSocket marks may certify a lifecycle path."""
    start_ms = 1_800_000_000_000
    part = _mark_part(tmp_path, start_ms)
    frame = pd.read_parquet(part)
    supplemental = frame.iloc[[1]].copy()
    supplemental["source"] = "hyperliquid_info_metaAndAssetCtxs"
    pd.concat([frame, supplemental], ignore_index=True).to_parquet(part, index=False)

    rows, evidence = FrozenHip3MarkArchive().load(
        data_root=tmp_path,
        symbol="xyz:MU",
        start_ms=start_ms,
        end_ms=start_ms + 2_000,
    )

    assert len(rows) == 2
    assert {row["source"] for row in rows} == {"hyperliquid_ws_activeAssetCtx"}
    assert evidence["excluded_supplemental_rows"] == 1


def test_l2_archive_binds_first_causal_depth_window(tmp_path: Path) -> None:
    """Exact local books retain nanosecond receipt ordering and file identity."""
    start_ms = 1_800_000_000_000
    part = _l2_part(tmp_path, start_ms)
    source = FrozenHyperliquidL2Archive()

    rows, evidence = source.load(
        data_root=tmp_path,
        symbol="HYPE",
        start_ms=start_ms,
        end_ms=start_ms + 2_000,
    )

    assert [row["received_ts_ns"] for row in rows] == [
        start_ms * 1_000_000,
        (start_ms + 1_000) * 1_000_000,
    ]
    assert rows[0]["bids"][0]["price"] == 99.9
    assert evidence["rows"] == 2
    source.require_unchanged(evidence)
    part.write_bytes(part.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="archive changed"):
        source.require_unchanged(evidence)


def _mark_part(root: Path, start_ms: int) -> Path:
    day = pd.Timestamp(start_ms, unit="ms", tz="UTC").date().isoformat()
    directory = root / "cache/events/hyperliquid/xyz:MU" / day / "asset_context.parquet"
    directory.mkdir(parents=True)
    part = directory / "part-fixture.parquet"
    rows = [
        {
            "symbol": "xyz:MU",
            "observed_ts_ms": timestamp,
            "received_ts_ns": timestamp * 1_000_000,
            "mark_price": 100.0,
            "source": "hyperliquid_ws_activeAssetCtx",
        }
        for timestamp in (
            start_ms - 1_000,
            start_ms,
            start_ms + 1_000,
            start_ms + 3_000,
        )
    ]
    pd.DataFrame(rows).to_parquet(part, index=False)
    return part


def _l2_part(root: Path, start_ms: int) -> Path:
    day = pd.Timestamp(start_ms, unit="ms", tz="UTC").date().isoformat()
    directory = root / "cache/events/hyperliquid/HYPE" / day / "l2.parquet"
    directory.mkdir(parents=True)
    part = directory / "part-fixture.parquet"
    rows = [
        {
            "symbol": "HYPE",
            "exchange_ts_ms": timestamp - 5,
            "received_ts_ns": timestamp * 1_000_000,
            "bids": [{"price": 99.9, "size": 100.0, "order_count": 1}],
            "asks": [{"price": 100.1, "size": 100.0, "order_count": 1}],
            "source": "hyperliquid_ws_l2Book",
        }
        for timestamp in (
            start_ms - 1_000,
            start_ms,
            start_ms + 1_000,
            start_ms + 3_000,
        )
    ]
    pd.DataFrame(rows).to_parquet(part, index=False)
    return part
