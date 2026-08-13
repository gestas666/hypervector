"""Tests for immutable official Hyperliquid funding evidence."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from hypervector.cli import build_parser
from hypervector.data.hl_funding_archive import (
    HlFundingRequest,
    store_hl_funding,
)


def test_hl_funding_fetch_command_is_discoverable() -> None:
    """The official funding acquisition command is public and repeatable."""
    parser = build_parser()
    choices: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            choices.update(action.choices)

    assert "hl-funding-fetch" in choices


def _request() -> HlFundingRequest:
    return HlFundingRequest(
        "BTC",
        datetime(2026, 7, 25, 12, tzinfo=UTC),
        datetime(2026, 7, 25, 14, tzinfo=UTC),
    )


def _row(hour_ms: int, rate: str) -> dict[str, object]:
    return {
        "coin": "BTC",
        "fundingRate": rate,
        "premium": "0.00002",
        "time": hour_ms + 30,
    }


def test_funding_bundle_retains_raw_pages_and_complete_hourly_coverage(
    tmp_path: Path,
) -> None:
    """A complete bounded window is published with checksummed evidence."""
    pages = (
        (
            _row(1_784_980_800_000, "0.00001"),
            _row(1_784_984_400_000, "-0.00002"),
        ),
    )

    stored = store_hl_funding(tmp_path, _request(), pages)
    manifest = json.loads(stored.manifest_path.read_text(encoding="utf-8"))
    frame = pd.read_parquet(stored.funding_path)

    assert manifest["complete"] is True
    assert manifest["expected_hour_count"] == 2
    assert manifest["missing_hour_count"] == 0
    assert manifest["files"]["raw/page-0001.json.gz"]["sha256"]
    assert len(frame) == 2
    assert frame["event_ts_ms"].tolist() == [1_784_980_800_030, 1_784_984_400_030]
    assert frame["source"].eq("hl_funding_history").all()


def test_funding_bundle_rejects_missing_settlement_hours(tmp_path: Path) -> None:
    """A gap cannot become success-shaped replay funding evidence."""
    pages = ((_row(1_784_980_800_000, "0.00001"),),)

    with pytest.raises(ValueError, match="missing 1 hourly settlement"):
        store_hl_funding(tmp_path, _request(), pages)


def test_funding_request_requires_hour_aligned_utc_window() -> None:
    """Replay archives use exact half-open hourly windows."""
    with pytest.raises(ValueError, match="hour-aligned"):
        HlFundingRequest(
            "BTC",
            datetime(2026, 7, 25, 12, 1, tzinfo=UTC),
            datetime(2026, 7, 25, 14, tzinfo=UTC),
        )
