"""Causal attribution tests for Hypervelocity regime and L2 evidence."""

from __future__ import annotations

import math
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.hypervelocity_attribution import (
    align_book_pressure,
    build_bar_annotations,
    build_lifecycle_attribution,
    compression_age_bars,
    regime_age_bars,
    slice_outcomes,
)
from hypervector.research.hypervelocity_attribution_io import (
    load_native_book_pressure,
)
from hypervector.research.hypervelocity_attribution_report import (
    summarize_attribution,
)
from hypervector.research.hypervelocity_book_sequence import align_book_sequence


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=15, freq="1min", tz="UTC")
    close = [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 900, 901, 902, 903, 904]
    return pd.DataFrame(
        {
            "open": close,
            "high": [value + 1 for value in close],
            "low": [value - 2 for value in close],
            "close": close,
            "volume": [1.0] * len(close),
        },
        index=index,
    )


def test_regime_and_compression_age_are_causal_and_explicit() -> None:
    states = pd.Series(["UP", "UP", "DOWN", "DOWN", "DOWN", "UP"])
    assert regime_age_bars(states).tolist() == [0, 1, 0, 1, 2, 0]

    bbwp = pd.Series([math.nan, 40.0, 20.0, 30.0, 10.0, 50.0])
    observed = compression_age_bars(bbwp, threshold=25.0)
    assert math.isnan(float(observed.iloc[0]))
    assert math.isnan(float(observed.iloc[1]))
    assert observed.iloc[2:].tolist() == [0.0, 1.0, 0.0, 1.0]


def test_bar_annotations_use_only_prior_completed_five_minute_structure() -> None:
    bars = _bars()
    decisions = pd.DataFrame(
        {
            "state_5m": ["TREND_UP"] * 10 + ["TREND_DOWN"] * 5,
            "context_15m": ["TREND_UP"] * len(bars),
            "bbwp_percentile": [30.0, 20.0] + [40.0] * 13,
        },
        index=bars.index,
    )

    full = build_bar_annotations(bars, decisions, structure_lookback=1)
    partial = build_bar_annotations(
        bars.iloc[:10], decisions.iloc[:10], structure_lookback=1
    )

    pd.testing.assert_frame_equal(full.iloc[:10], partial)
    at_second_close = full.iloc[9]
    assert at_second_close["prior_5m_resistance"] == pytest.approx(106.0)
    assert at_second_close["prior_5m_support"] == pytest.approx(99.0)
    assert at_second_close["regime_age_bars"] == 9
    assert at_second_close["bbwp_compression_age_bars"] == 8


def test_book_pressure_alignment_is_backward_only_and_stale_stays_missing() -> None:
    books = pd.DataFrame(
        {
            "ts_ms": [900, 1_000, 1_100],
            "obi_5": [-0.2, 0.4, 0.9],
            "obi_20": [-0.1, 0.2, 0.8],
            "spread_bps": [1.0, 2.0, 3.0],
            "micro_price_delta_bps": [-0.1, 0.3, 0.7],
        }
    )
    signals = pd.DatetimeIndex(pd.to_datetime([1_050, 5_000], unit="ms", utc=True))

    result = align_book_pressure(
        signals,
        books,
        max_age_ms=1_000,
        trailing_window_ms=200,
    )

    assert result.iloc[0]["book_snapshot_ts_ms"] == 1_000
    assert result.iloc[0]["book_snapshot_age_ms"] == 50
    assert result.iloc[0]["obi_5"] == pytest.approx(0.4)
    assert result.iloc[0]["obi_5_trailing_median"] == pytest.approx(0.1)
    assert result.iloc[0]["book_window_snapshots"] == 2
    assert math.isnan(float(result.iloc[1]["obi_5"]))
    assert result.iloc[1]["book_window_snapshots"] == 0


def test_book_sequence_features_are_multi_horizon_and_strictly_causal() -> None:
    """A future snapshot cannot alter any signal-time sequence feature."""
    books = pd.DataFrame(
        {
            "ts_ms": [0, 10_000, 20_000, 30_000],
            "obi_5": [-0.5, 0.0, 0.5, 0.99],
            "obi_20": [-0.25, 0.0, 0.25, 0.99],
            "spread_bps": [0.4, 0.3, 0.2, 9.9],
            "micro_price_delta_bps": [-0.3, 0.0, 0.3, 9.9],
            "best_bid": [100.0, 100.0, 101.0, 999.0],
            "best_ask": [101.0, 101.0, 102.0, 1_000.0],
            "best_bid_size": [10.0, 12.0, 5.0, 999.0],
            "best_ask_size": [10.0, 8.0, 9.0, 1.0],
        }
    )
    signal = pd.DatetimeIndex(pd.to_datetime([25_000], unit="ms", utc=True))

    observed = align_book_sequence(signal, books, max_age_ms=6_000).iloc[0]

    assert observed["book_sequence_snapshots_15s"] == 2
    assert observed["obi_5_mean_15s"] == pytest.approx(0.25)
    assert observed["obi_5_delta_15s"] == pytest.approx(0.5)
    assert observed["book_sequence_snapshots_60s"] == 3
    assert observed["obi_5_mean_60s"] == pytest.approx(0.0)
    assert observed["obi_5_delta_60s"] == pytest.approx(1.0)
    assert observed["obi_5_sign_mean_60s"] == pytest.approx(0.0)
    assert observed["micro_price_delta_bps_mean_60s"] == pytest.approx(0.0)
    assert observed["spread_bps_median_60s"] == pytest.approx(0.3)


def test_book_sequence_stale_latest_snapshot_stays_missing() -> None:
    books = pd.DataFrame(
        {
            "ts_ms": [0],
            "obi_5": [0.5],
            "obi_20": [0.25],
            "spread_bps": [0.2],
            "micro_price_delta_bps": [0.1],
        }
    )
    signal = pd.DatetimeIndex(pd.to_datetime([10_000], unit="ms", utc=True))

    observed = align_book_sequence(signal, books, max_age_ms=6_000).iloc[0]

    assert observed["book_sequence_snapshots_15s"] == 0
    assert math.isnan(float(observed["obi_5_mean_15s"]))


def test_lifecycle_join_retains_all_statuses_and_reports_denominators() -> None:
    decision_times = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")
    signal_times = decision_times + pd.Timedelta(minutes=1)
    lifecycles = pd.DataFrame(
        {
            "lifecycle_id": [0, 1, 2],
            "direction": ["long", "short", "long"],
            "signal_time_utc": [time.isoformat() for time in signal_times],
            "entry_time_utc": [
                signal_times[0].isoformat(),
                signal_times[1].isoformat(),
                None,
            ],
            "status": ["target_completed", "liquidated", "expired"],
        }
    )
    bars = pd.DataFrame(
        {
            "regime_age_bars": [2.0, 20.0, 3.0],
            "bbwp_compression_age_bars": [1.0, 50.0, math.nan],
            "directional_structure_distance_bps": [10.0, 120.0, math.nan],
            "context_15m": ["TREND_UP", "TREND_UP", "RANGE"],
        },
        index=decision_times,
    )
    books = pd.DataFrame(
        {
            "obi_5_trailing_median": [0.2, 0.3, math.nan],
            "obi_5": [0.2, 0.3, math.nan],
        },
        index=signal_times,
    )

    joined = build_lifecycle_attribution(lifecycles, bars, books)
    rows = slice_outcomes(joined, "pressure_alignment")

    assert len(joined) == 3
    assert joined["regime_age_bars"].tolist() == [2.0, 20.0, 3.0]
    assert joined["pressure_alignment"].tolist() == ["aligned", "opposed", "missing"]
    assert sum(int(row["lifecycles"]) for row in rows) == 3
    opposed = next(row for row in rows if row["bucket"] == "opposed")
    assert opposed["liquidated"] == 1
    assert opposed["resolved_trades"] == 1
    assert opposed["target_rate_pct"] == pytest.approx(0.0)


def test_native_book_loader_computes_depth_pressure_without_neutral_defaults(
    tmp_path: Path,
) -> None:
    bids = [{"px": str(100 - index), "sz": "2", "n": 1} for index in range(20)]
    asks = [{"px": str(101 + index), "sz": "1", "n": 1} for index in range(20)]
    row = {
        "ts_exchange_ms": 1_000,
        "best_bid": "100",
        "best_ask": "101",
        "bids": bids,
        "asks": asks,
    }
    path = tmp_path / "books.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    observed = load_native_book_pressure(path)

    assert observed.iloc[0]["obi_5"] == pytest.approx(1.0 / 3.0)
    assert observed.iloc[0]["obi_20"] == pytest.approx(1.0 / 3.0)
    assert observed.iloc[0]["spread_bps"] == pytest.approx(10000.0 / 100.5)
    assert observed.iloc[0]["micro_price_delta_bps"] > 0.0


def test_book_alignment_computes_backward_only_normalized_top_of_book_ofi(
    tmp_path: Path,
) -> None:
    """Queue changes through the signal time form causal normalized OFI."""
    snapshots = [
        (800, 100.0, 10.0, 101.0, 10.0),
        (900, 100.0, 12.0, 101.0, 8.0),
        (1_000, 101.0, 5.0, 102.0, 9.0),
        (1_100, 99.0, 100.0, 100.0, 1.0),
    ]
    rows = []
    for ts_ms, bid, bid_size, ask, ask_size in snapshots:
        bids = [
            {"px": str(bid - level), "sz": str(bid_size if level == 0 else 1.0)}
            for level in range(20)
        ]
        asks = [
            {"px": str(ask + level), "sz": str(ask_size if level == 0 else 1.0)}
            for level in range(20)
        ]
        rows.append(
            {
                "ts_exchange_ms": ts_ms,
                "best_bid": str(bid),
                "best_ask": str(ask),
                "bids": bids,
                "asks": asks,
            }
        )
    path = tmp_path / "books.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    books = load_native_book_pressure(path)
    signal = pd.DatetimeIndex(pd.to_datetime([1_050], unit="ms", utc=True))
    aligned = align_book_pressure(
        signal,
        books,
        max_age_ms=100,
        trailing_window_ms=5_000,
    )

    assert books.iloc[0]["best_bid_size"] == pytest.approx(10.0)
    assert aligned.iloc[0]["book_snapshot_ts_ms"] == 1_000
    assert aligned.iloc[0]["ofi_top_5s"] == pytest.approx(17.0)
    assert aligned.iloc[0]["ofi_top_5s_normalized"] == pytest.approx(0.85)


def test_attribution_summary_is_report_only_and_preserves_missing_book_rows() -> None:
    frame = pd.DataFrame(
        {
            "lifecycle_id": [0, 1, 2],
            "direction": ["long", "short", "long"],
            "status": ["target_completed", "liquidated", "expired"],
            "book_snapshot_ts_ms": [1_000.0, 2_000.0, math.nan],
            "regime_age_bucket": ["0-4", "15+", "0-4"],
            "structure_distance_bucket": ["<25", "100+", "missing"],
            "bbwp_recency_bucket": ["0-5", "31+", "missing"],
            "context_15m_alignment": ["aligned", "opposed", "non_directional"],
            "pressure_alignment": ["aligned", "opposed", "missing"],
        }
    )

    summary = summarize_attribution(frame)

    assert summary["report_only"] is True
    assert summary["runtime_strategy_changed"] is False
    assert summary["lifecycles"] == 3
    assert summary["status_counts"] == {
        "expired": 1,
        "liquidated": 1,
        "target_completed": 1,
    }
    assert summary["book_pressure_coverage"] == 2
    pressure_rows = summary["slices"]["pressure_alignment"]
    assert sum(row["lifecycles"] for row in pressure_rows) == 3
