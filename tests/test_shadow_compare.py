"""Report-only reconciliation of Hypervelocity shadow and real logs."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.shadow_compare import compare_shadow_to_positions


def _observation(
    timestamp: str,
    *,
    regime: str,
    allowed: bool,
    direction: str = "long",
) -> dict[str, object]:
    return {
        "feed_ts": timestamp,
        "run_id": "run-long",
        "action": "regime_observation",
        "primary_regime": regime,
        "breakout_direction": None,
        "entry_direction": direction,
        "entry_allowed": allowed,
        "submitted": False,
    }


def test_compare_matches_entry_exit_and_maker_timing() -> None:
    shadow = [
        _observation("2026-07-25T10:00:00Z", regime="TREND_UP", allowed=True),
        {
            "feed_ts": "2026-07-25T10:00:05Z",
            "run_id": "run-long",
            "action": "submit_entry",
            "side": "buy",
            "requested_qty": 1.0,
        },
        {
            "feed_ts": "2026-07-25T10:00:20Z",
            "run_id": "run-long",
            "action": "enter_long",
            "side": "buy",
            "fill_px": 100.0,
            "fill_qty": 1.0,
        },
        _observation("2026-07-25T10:01:00Z", regime="RANGE", allowed=False),
        {
            "feed_ts": "2026-07-25T10:01:50Z",
            "run_id": "run-long",
            "action": "close",
            "side": "sell",
            "fill_px": 100.2,
            "fill_qty": 1.0,
        },
        _observation("2026-07-25T10:02:00Z", regime="RANGE", allowed=False),
    ]
    positions = pd.DataFrame(
        [
            {
                "symbol": "BTC",
                "side": "long",
                "open_time_utc": "2026-07-25T10:00:10Z",
                "close_time_utc": "2026-07-25T10:01:40Z",
                "entry_price": 100.01,
                "exit_price": 100.2,
                "fill_type": "maker",
            }
        ]
    )

    report = compare_shadow_to_positions(
        shadow,
        positions,
        run_ids=("run-long",),
        entry_tolerance_seconds=30.0,
    )

    assert report["report_only"] is True
    assert report["summary"] == {
        "shadow_entries": 1,
        "real_entries": 1,
        "matched_entries": 1,
        "direction_matches": 1,
        "direction_mismatches": 0,
        "shadow_unmatched": 0,
        "real_unmatched": 0,
        "false_range_at_real_entries": 0,
        "real_maker_entries": 1,
        "entry_precision_pct": 100.0,
        "entry_recall_pct": 100.0,
    }
    match = report["matches"][0]
    assert match["entry_timing_seconds"] == 10.0
    assert match["entry_abs_timing_seconds"] == 10.0
    assert match["shadow_submit_to_fill_seconds"] == 15.0
    assert match["exit_timing_seconds"] == 10.0
    assert match["entry_price_diff_bps"] == pytest.approx(-0.99990001)


def test_compare_reports_real_entry_during_shadow_range_without_gating() -> None:
    shadow = [
        _observation("2026-07-25T10:00:00Z", regime="RANGE", allowed=False),
        _observation("2026-07-25T10:01:00Z", regime="RANGE", allowed=False),
    ]
    positions = pd.DataFrame(
        [
            {
                "symbol": "BTC",
                "side": "long",
                "open_time_utc": "2026-07-25T10:00:20Z",
                "close_time_utc": None,
                "entry_price": 100.0,
                "exit_price": None,
                "fill_type": "maker",
            }
        ]
    )

    report = compare_shadow_to_positions(
        shadow,
        positions,
        run_ids=("run-long",),
        entry_tolerance_seconds=30.0,
    )

    assert report["summary"]["matched_entries"] == 0
    assert report["summary"]["real_unmatched"] == 1
    assert report["summary"]["false_range_at_real_entries"] == 1
    assert report["real_unmatched"][0]["nearest_primary_regime"] == "RANGE"
    assert report["real_unmatched"][0]["nearest_entry_allowed"] is False


def test_compare_reconciles_duplicate_peak_and_trade_records() -> None:
    shadow = [
        _observation("2026-07-25T10:00:00Z", regime="TREND_UP", allowed=True),
        _observation("2026-07-25T10:05:00Z", regime="TREND_UP", allowed=True),
    ]
    positions = pd.DataFrame(
        {
            "record_source": ["position_peak_only", "trade_only"],
            "symbol": ["BTC", "BTC"],
            "side": ["long", "long"],
            "open_time_utc": [
                "2026-07-25T10:01:00Z",
                "2026-07-25T10:02:00Z",
            ],
            "close_time_utc": [
                "2026-07-25T10:04:00Z",
                "2026-07-25T10:04:05Z",
            ],
            "entry_price": [100.0, 100.0],
            "exit_price": [None, 100.2],
            "quantity": [0.01, 0.01],
            "fill_type": ["", "maker"],
        }
    )

    report = compare_shadow_to_positions(
        shadow,
        positions,
        run_ids=("run-long",),
    )

    assert report["summary"]["real_entries"] == 1
    assert report["summary"]["real_maker_entries"] == 1


def test_compare_reports_nearby_opposite_direction_as_mismatch() -> None:
    long_start = _observation(
        "2026-07-25T10:00:00Z",
        regime="TREND_UP",
        allowed=True,
    )
    long_end = _observation(
        "2026-07-25T10:01:00Z",
        regime="TREND_UP",
        allowed=True,
    )
    short_start = {
        **long_start,
        "run_id": "run-short",
        "entry_direction": "short",
        "primary_regime": "TREND_DOWN",
    }
    short_end = {**short_start, "feed_ts": "2026-07-25T10:01:00Z"}
    shadow = [
        long_start,
        short_start,
        {
            "feed_ts": "2026-07-25T10:00:10Z",
            "run_id": "run-long",
            "action": "enter_long",
            "side": "buy",
            "fill_px": 100.0,
            "fill_qty": 1.0,
        },
        long_end,
        short_end,
    ]
    positions = pd.DataFrame(
        [
            {
                "symbol": "BTC",
                "side": "short",
                "open_time_utc": "2026-07-25T10:00:12Z",
                "close_time_utc": None,
                "entry_price": 100.0,
                "exit_price": None,
                "fill_type": "maker",
            }
        ]
    )

    report = compare_shadow_to_positions(
        shadow,
        positions,
        run_ids=("run-long", "run-short"),
        entry_tolerance_seconds=30.0,
    )

    assert report["summary"]["direction_matches"] == 0
    assert report["summary"]["direction_mismatches"] == 1
    assert report["direction_mismatches"][0]["shadow_direction"] == "long"
    assert report["direction_mismatches"][0]["real_direction"] == "short"


def test_compare_refuses_non_overlapping_real_log() -> None:
    shadow = [
        _observation("2026-07-25T10:00:00Z", regime="TREND_UP", allowed=True),
        _observation("2026-07-25T10:01:00Z", regime="TREND_UP", allowed=True),
    ]
    positions = pd.DataFrame(
        [
            {
                "symbol": "BTC",
                "side": "long",
                "open_time_utc": "2026-07-24T10:00:00Z",
                "close_time_utc": "2026-07-24T10:01:00Z",
                "entry_price": 100.0,
                "exit_price": 100.2,
                "fill_type": "maker",
            }
        ]
    )

    with pytest.raises(ValueError, match="does not overlap"):
        compare_shadow_to_positions(
            shadow,
            positions,
            run_ids=("run-long",),
            entry_tolerance_seconds=30.0,
        )
