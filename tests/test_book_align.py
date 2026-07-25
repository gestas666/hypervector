"""Tests for orderbook alignment and feature extraction."""

import json
import tempfile
from pathlib import Path

import pandas as pd

from hypervector.data.book_align import (
    align_orderbook_to_ohlcv,
    gate_signals_by_orderbook,
    load_l2_jsonl,
)


def test_load_l2_jsonl_and_alignment():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w+", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        # Write 2 L2 snapshot rows
        r1 = {
            "ts_exchange_ms": 1784827370000,
            "best_bid": 64790.0,
            "best_ask": 64791.0,
            "bids": [{"px": 64790.0, "sz": 5.0}, {"px": 64789.0, "sz": 2.0}],
            "asks": [{"px": 64791.0, "sz": 1.0}, {"px": 64792.0, "sz": 4.0}],
        }
        r2 = {
            "ts_exchange_ms": 1784827430000,
            "best_bid": 64800.0,
            "best_ask": 64801.0,
            "bids": [{"px": 64800.0, "sz": 1.0}, {"px": 64799.0, "sz": 1.0}],
            "asks": [{"px": 64801.0, "sz": 5.0}, {"px": 64802.0, "sz": 5.0}],
        }
        tmp.write(json.dumps(r1) + "\n")
        tmp.write(json.dumps(r2) + "\n")

    try:
        df_book = load_l2_jsonl(tmp_path)
        assert len(df_book) == 2
        assert "spread_bps" in df_book.columns
        assert "obi_5" in df_book.columns
        assert df_book.iloc[0]["obi_5"] > 0  # 7 bids vs 5 asks

        # Create dummy OHLCV bars
        ts_ms = [1784827380000, 1784827440000]
        df_ohlcv = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(ts_ms, unit="ms", utc=True),
                "open": [64790.0, 64800.0],
                "high": [64795.0, 64805.0],
                "low": [64785.0, 64795.0],
                "close": [64792.0, 64802.0],
                "volume": [10.0, 12.0],
            }
        )

        aligned = align_orderbook_to_ohlcv(df_ohlcv, df_book)
        assert "spread_bps" in aligned.columns
        assert "obi_5" in aligned.columns
        assert len(aligned) == 2

        # Test gating
        entries = pd.Series([True, True])
        gated_long = gate_signals_by_orderbook(
            entries, aligned, direction="long", min_obi=0.0
        )
        assert gated_long.iloc[0]
        assert not gated_long.iloc[1]  # r2 has obi_5 < 0

    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_alignment_handles_millisecond_index_and_preserves_it():
    """Parquet-style datetime64[ms] bars must retain causal book matches."""
    index = pd.DatetimeIndex(
        pd.to_datetime([1784827380000, 1784827440000], unit="ms", utc=True)
    ).as_unit("ms")
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1.0, 2.0],
        },
        index=index,
    )
    book = pd.DataFrame(
        {
            "ts_ms": [1784827370000, 1784827430000],
            "best_bid": [99.0, 100.0],
            "best_ask": [100.0, 101.0],
            "spread_bps": [1.0, 2.0],
            "obi_5": [0.2, -0.2],
        }
    )

    aligned = align_orderbook_to_ohlcv(bars, book)

    assert aligned.index.equals(index)
    assert aligned["best_bid"].tolist() == [99.0, 100.0]
