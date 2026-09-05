"""Exact exchange-mark minute path tests for profit-lock replay."""

from __future__ import annotations

import pandas as pd


def test_exact_mark_rows_form_causal_minute_ohlc_and_gap_evidence() -> None:
    from hypervector.research.cohort_profit_lock_exact_mark import (
        exact_mark_minute_bars,
    )

    frame = pd.DataFrame(
        {
            "ts_ms": (61_000, 70_000, 119_000, 121_000),
            "mark_price": (100.0, 101.0, 99.0, 102.0),
        }
    )

    bars = exact_mark_minute_bars(frame)

    assert bars[60_000].open == 100.0
    assert bars[60_000].high == 101.0
    assert bars[60_000].low == 99.0
    assert bars[60_000].close == 99.0
    assert bars[60_000].snapshot_count == 3
    assert bars[60_000].first_delay_ms == 1_000
    assert bars[60_000].maximum_internal_gap_ms == 49_000
    assert bars[60_000].end_boundary_age_ms == 1_000
