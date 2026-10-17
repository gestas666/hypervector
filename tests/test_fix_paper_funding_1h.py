"""Hourly funding boundaries cover every timeframe the live feed accepts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from paper_fix_fixtures import write_strict_export

from hypervector.paper.session import PaperSession
from hypervector.paper.session_bars import _is_funding_boundary, _timeframe_minutes


def test_one_hour_bars_are_supported_funding_boundaries() -> None:
    assert _timeframe_minutes("1h") == 60
    record = {"timestamp": pd.Timestamp("2026-07-22T00:00:00Z")}
    assert _is_funding_boundary(record, timeframe="1h") is True


def test_open_one_hour_position_charges_exactly_one_funding_row(tmp_path: Path) -> None:
    export = write_strict_export(tmp_path, timeframe="1h")
    rate = 0.0001
    mark = 50_000.0
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        funding_rate_hourly=rate,
        enable_funding_refresh=False,
    )
    session.engine.apply_market_fill(
        feed_ts="t0",
        action="enter_short",
        side="sell",
        qty=1.0,
        mark_px=mark,
    )

    session.on_bar(
        {
            "timestamp": pd.Timestamp("2026-07-22T00:00:00Z"),
            "open": mark,
            "high": mark,
            "low": mark,
            "close": mark,
            "volume": 1.0,
        }
    )

    rows = [
        json.loads(line)
        for line in session.decisions_path.read_text(encoding="utf-8").splitlines()
    ]
    funding = [row for row in rows if row.get("action") == "funding"]
    assert len(funding) == 1
    assert funding[0]["feed_ts"] == "2026-07-22T01:00:00+00:00"
    # Short receives positive funding: one hour at the hourly rate.
    assert funding[0]["funding_payment_usd"] == pytest.approx(-mark * rate)


def test_unsupported_timeframe_fails_at_construction_before_any_io(
    tmp_path: Path,
) -> None:
    export = write_strict_export(tmp_path, timeframe="4h")
    root = tmp_path / "data"

    with pytest.raises(ValueError, match="4h"):
        PaperSession(export_dir=export, data_root=root)

    assert not root.exists()
