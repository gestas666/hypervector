from __future__ import annotations

from pathlib import Path

import pandas as pd

from hypervector.research.cross_asset_residual_data import (
    build_residual_source_identity,
)
from hypervector.research.low_tf_multi_asset_contract import ordered_frame_sha256


def test_source_identity_binds_selected_frame_and_gap_runs(tmp_path: Path) -> None:
    times = pd.date_range("2026-01-01T00:00:00Z", periods=6, freq="1min")
    frame = pd.DataFrame(
        {
            "timestamp": times,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
            "source": ["hl", "hl_gap_fill", "hl_gap_fill", "hl", "hl_gap_fill", "hl"],
        }
    )
    bars_path = tmp_path / "bars.parquet"
    funding_path = tmp_path / "funding.parquet"
    frame.to_parquet(bars_path, index=False)
    pd.DataFrame({"value": [1]}).to_parquet(funding_path, index=False)

    identity = build_residual_source_identity(
        bars_path,
        funding_path,
        frame,
    )

    assert identity["selected_frame_sha256"] == ordered_frame_sha256(
        frame, time_column="timestamp"
    )
    assert identity["selected_frame_rows"] == 6
    assert identity["gap_fill_rows"] == 3
    assert identity["maximum_gap_fill_run"] == 2
    assert identity["native_rows"] == 3
