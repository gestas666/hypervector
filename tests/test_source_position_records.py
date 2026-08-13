"""Tests for reconciling overlapping source-position record types."""

from __future__ import annotations

import pandas as pd

from hypervector.data.source_position_records import reconcile_source_position_records


def _duplicate_records() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "record_source": ["position_peak_only", "trade_only"],
            "symbol": ["BTC", "BTC"],
            "side": ["long", "long"],
            "open_time_utc": [
                "2026-07-18T19:10:01Z",
                "2026-07-18T19:32:13Z",
            ],
            "close_time_utc": [
                "2026-07-18T21:02:32Z",
                "2026-07-18T21:02:37Z",
            ],
            "entry_price": [64_522.0, 64_522.0],
            "exit_price": [None, 64_689.0],
            "quantity": [0.01358, 0.01358],
            "status": ["closed", "closed"],
        }
    )


def test_reconciliation_prefers_trade_record_for_duplicate_peak_record() -> None:
    reconciled = reconcile_source_position_records(_duplicate_records())

    assert len(reconciled) == 1
    assert reconciled.iloc[0]["record_source"] == "trade_only"
    assert reconciled.iloc[0]["open_time_utc"] == "2026-07-18T19:32:13Z"


def test_reconciliation_preserves_true_split_exit_rows() -> None:
    records = _duplicate_records()
    records["record_source"] = ["position_peak+trade", "trade_only"]
    records["open_time_utc"] = [
        "2026-07-20T18:19:35.675977Z",
        "2026-07-20T18:19:35.696860Z",
    ]
    records["quantity"] = [0.01173, 0.00695]

    reconciled = reconcile_source_position_records(records)

    assert len(reconciled) == 2


def test_reconciliation_leaves_generic_position_frames_unchanged() -> None:
    generic = _duplicate_records().drop(
        columns=["record_source", "close_time_utc", "entry_price", "quantity"]
    )

    reconciled = reconcile_source_position_records(generic)

    pd.testing.assert_frame_equal(reconciled, generic)
