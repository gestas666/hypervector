"""Prospective HIP-3 public-trade versus live-candle parity tests."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
from pytest import raises

from hypervector.data.hl_events import PublicTradeEvent
from hypervector.research.hip3_prospective_candle_parity import (
    Hip3ProspectiveCandleParityConfig,
    build_hip3_prospective_candle_frames,
    build_hip3_prospective_candle_parity,
)

_BAR_MS = 15 * 60_000
_START_MS = 1_800_000_000_000
_END_MS = _START_MS + _BAR_MS
_SYMBOL = "xyz:SKHX"


def test_exact_trade_ohlc_matches_live_completed_candle() -> None:
    report = build_hip3_prospective_candle_parity(
        public_trades=_trades(),
        candles=_candles(),
        config=_config(),
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }
    assert report["coverage"] == {
        "expected_bars": 1,
        "trade_bars": 1,
        "candle_bars": 1,
        "overlap_bars": 1,
        "exact_ohlc_bars": 1,
        "missing_trade_bars": 0,
        "missing_candle_bars": 0,
        "mismatched_ohlc_bars": 0,
    }
    assert report["source"]["raw_trade_rows"] == 4
    assert report["source"]["unique_trade_rows"] == 4
    assert report["source"]["duplicate_trade_rows"] == 0
    assert report["source"]["comparison_trade_rows"] == 4
    assert report["source"]["comparison_candle_rows"] == 1
    assert len(report["source"]["comparison_candle_sha256"]) == 64
    assert (
        report["source"]["comparison_trade_sha256"] == report["source"]["trade_sha256"]
    )
    assert report["technical_assessment"] == {
        "candle_ohlc_parity_resolved": True,
        "unresolved_bars": 0,
    }


def test_causal_candle_frames_preserve_both_ohlc_sources() -> None:
    candles = _candles()
    candles.loc[0, "close"] = 100.5

    trade, venue = build_hip3_prospective_candle_frames(
        public_trades=_trades(),
        candles=candles,
        config=_config(),
    )

    assert trade.index.equals(venue.index)
    assert trade.iloc[0].to_dict() == {
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
    }
    assert venue.iloc[0]["close"] == 100.5


def test_out_of_window_candle_does_not_change_comparison_identity() -> None:
    control = build_hip3_prospective_candle_parity(
        public_trades=_trades(), candles=_candles(), config=_config()
    )
    candles = pd.concat(
        [
            pd.DataFrame(
                {
                    "timestamp": pd.to_datetime(
                        [_START_MS - _BAR_MS], unit="ms", utc=True
                    ),
                    "open": [90.0],
                    "high": [91.0],
                    "low": [89.0],
                    "close": [90.5],
                }
            ),
            _candles(),
        ],
        ignore_index=True,
    )

    report = build_hip3_prospective_candle_parity(
        public_trades=_trades(), candles=candles, config=_config()
    )

    assert report["source"]["candle_sha256"] != control["source"]["candle_sha256"]
    assert (
        report["source"]["comparison_candle_sha256"]
        == control["source"]["comparison_candle_sha256"]
    )


def test_price_mismatch_is_reported_without_success_shape() -> None:
    candles = _candles()
    candles.loc[0, "high"] = 102.5

    report = build_hip3_prospective_candle_parity(
        public_trades=_trades(),
        candles=candles,
        config=_config(),
    )

    assert report["coverage"]["mismatched_ohlc_bars"] == 1
    assert report["technical_assessment"]["candle_ohlc_parity_resolved"] is False
    assert report["bar_diagnostics"] == [
        {
            "bar_open_ms": _START_MS,
            "status": "ohlc_mismatch",
            "mismatched_fields": ["high"],
        }
    ]


def test_missing_trade_bar_keeps_parity_unresolved() -> None:
    report = build_hip3_prospective_candle_parity(
        public_trades=(),
        candles=_candles(),
        config=_config(),
    )

    assert report["coverage"]["missing_trade_bars"] == 1
    assert report["technical_assessment"] == {
        "candle_ohlc_parity_resolved": False,
        "unresolved_bars": 1,
    }
    assert report["bar_diagnostics"][0]["status"] == "missing_trade_bar"


def test_future_received_trade_cannot_prove_completed_bar_parity() -> None:
    future = (_END_MS + 1) * 1_000_000
    trades = (_trades()[0], replace(_trades()[1], received_ts_ns=future))

    with raises(ValueError, match="receipt exceeds observed_at_ms"):
        build_hip3_prospective_candle_parity(
            public_trades=trades,
            candles=_candles(),
            config=_config(),
        )


def test_conflicting_duplicate_trade_id_is_rejected() -> None:
    trades = _trades()
    conflict = replace(trades[0], price=100.5)

    with raises(ValueError, match="conflicting duplicate trade_id"):
        build_hip3_prospective_candle_parity(
            public_trades=trades + (conflict,),
            candles=_candles(),
            config=_config(),
        )


def _config() -> Hip3ProspectiveCandleParityConfig:
    return Hip3ProspectiveCandleParityConfig(
        symbol=_SYMBOL,
        start_ms=_START_MS,
        end_ms=_END_MS,
        observed_at_ms=_END_MS,
    )


def _candles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime([_START_MS], unit="ms", utc=True),
            "open": [100.0],
            "high": [102.0],
            "low": [99.0],
            "close": [101.0],
            "volume": [4.0],
            "trade_count": [4],
        }
    )


def _trades() -> tuple[PublicTradeEvent, ...]:
    return tuple(
        _trade(offset_ms, trade_id, price)
        for offset_ms, trade_id, price in (
            (10_000, 1, 100.0),
            (20_000, 2, 102.0),
            (30_000, 3, 99.0),
            (40_000, 4, 101.0),
        )
    )


def _trade(offset_ms: int, trade_id: int, price: float) -> PublicTradeEvent:
    timestamp = _START_MS + offset_ms
    return PublicTradeEvent(
        _SYMBOL,
        "buy",
        price,
        1.0,
        f"0x{trade_id}",
        timestamp,
        timestamp * 1_000_000 + 1_000,
        trade_id,
        "buyer",
        "seller",
    )
