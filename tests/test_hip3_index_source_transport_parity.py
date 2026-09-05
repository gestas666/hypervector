"""Exact index source-transport parity diagnostics."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_index_source_transport_parity import (
    Hip3IndexSourceParityConfig,
    build_hip3_index_source_transport_parity,
)

_BAR_MS = 900_000
_START_MS = 1_800_000_000_000


def test_exact_sources_and_frozen_decisions_resolve_non_vacuously() -> None:
    """Matching tape, candle, WS, REST, and decision paths must reconcile."""
    report = _build()

    assert report["coverage"]["observer_decisions"] == 8
    assert report["coverage"]["observer_eligible_decisions"] == 1
    assert report["technical_assessment"] == {
        "observer_rest_ledger_reconciled": True,
        "trade_candle_ohlc_parity_resolved": True,
        "pressure_threshold_parity_resolved": True,
        "signal_decision_parity_resolved": True,
        "decision_parity_non_vacuous": True,
        "source_transport_parity_resolved": True,
    }


def test_changed_rest_ledger_cannot_rewrite_a_frozen_observer_decision() -> None:
    """Raw REST evidence must agree exactly with its prospective journal row."""
    rest = _rest_books()
    rest[-1]["payload"]["bids"][0]["size"] = 99.0

    with pytest.raises(ValueError, match="observer decision differs from REST ledger"):
        _build(rest_books=rest)


def test_trade_candle_difference_is_timestamped_not_hidden() -> None:
    """One altered venue close must remain an explicit source mismatch."""
    candles = _candles()
    candles.loc[58, "close"] += 0.25
    candles.loc[58, "high"] += 0.25

    report = _build(candles=candles)

    assert report["technical_assessment"]["trade_candle_ohlc_parity_resolved"] is False
    assert report["mismatches"]["candle_ohlc"][0]["bar_open_ms"] == (
        _START_MS + 58 * _BAR_MS
    )


def test_initial_midbar_capture_reconciles_as_scan_incomplete() -> None:
    """A ledger that starts midbar must preserve the frozen unresolved status."""
    rest = _rest_books()[2:]
    observers = _observer_rows()
    first = observers[0]["decision"]
    assert isinstance(first, dict)
    first["pressure_scan_complete"] = False
    first["pressure_fresh"] = False
    first["pressure_status"] = "truncated_ledger_tail"

    report = build_hip3_index_source_transport_parity(
        trades=_trades(),
        archive_books=_archive_books(),
        venue_candles=_candles(),
        rest_book_rows=rest,
        observer_rows=observers,
        config=_config(),
    )

    assert report["technical_assessment"]["observer_rest_ledger_reconciled"] is True


def _build(
    *,
    candles: pd.DataFrame | None = None,
    rest_books: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return build_hip3_index_source_transport_parity(
        trades=_trades(),
        archive_books=_archive_books(),
        venue_candles=candles if candles is not None else _candles(),
        rest_book_rows=rest_books if rest_books is not None else _rest_books(),
        observer_rows=_observer_rows(),
        config=_config(),
    )


def _config() -> Hip3IndexSourceParityConfig:
    return Hip3IndexSourceParityConfig(
        "xyz:SP500",
        "index-v3",
        "sp500-v3",
        _START_MS,
        _START_MS + 64 * _BAR_MS,
        Hip3BreakoutPressureConfig(4, 3, 5, 0.1, 120.0),
    )


def _candles() -> pd.DataFrame:
    close = [100.0 + index * 0.1 for index in range(64)]
    close[60] += 1.0
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [_START_MS + index * _BAR_MS for index in range(64)],
                unit="ms",
                utc=True,
            ),
            "open": close,
            "high": [value + 0.2 for value in close],
            "low": [value - 0.2 for value in close],
            "close": close,
        }
    )


def _trades() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, candle in _candles().iterrows():
        for offset, field in enumerate(("open", "high", "low", "close"), 1):
            rows.append(
                {
                    "ts_ms": _START_MS + index * _BAR_MS + offset * 1_000,
                    "trade_id": index * 10 + offset,
                    "price": float(candle[field]),
                    "size": 1.0,
                }
            )
    return pd.DataFrame(rows)


def _archive_books() -> pd.DataFrame:
    rows = []
    for index in range(64):
        imbalance = 0.6 if index == 60 else 0.0
        bid, ask = (8.0, 2.0) if imbalance else (5.0, 5.0)
        for offset in (_BAR_MS - 10_000, _BAR_MS - 2_000):
            rows.append(
                {
                    "ts_ms": _START_MS + index * _BAR_MS + offset,
                    "obi_10": (bid - ask) / (bid + ask),
                }
            )
    return pd.DataFrame(rows)


def _rest_books() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(55, 64):
        bid, ask = (8.0, 2.0) if index == 60 else (5.0, 5.0)
        for offset in (_BAR_MS - 10_000, _BAR_MS - 2_000):
            exchange = _START_MS + index * _BAR_MS + offset
            rows.append(
                {
                    "event_type": "book_observation",
                    "payload": {
                        "symbol": "xyz:SP500",
                        "source": "hyperliquid_mainnet_l2_rest",
                        "exchange_ts_ms": exchange,
                        "recv_ts_ms": exchange + 100,
                        "bids": _levels(100.0, bid, descending=True),
                        "asks": _levels(101.0, ask, descending=False),
                    },
                }
            )
    return rows


def _observer_rows() -> list[dict[str, object]]:
    output = []
    for index in range(56, 64):
        imbalance = 0.6 if index == 60 else 0.0
        exchange = _START_MS + (index + 1) * _BAR_MS - 2_000
        output.append(
            {
                "decision": {
                    "symbol": "xyz:SP500",
                    "provider_id": "index-v3",
                    "profile_id": "sp500-v3",
                    "decision_time_ms": _START_MS + (index + 1) * _BAR_MS,
                    "observed_at_ms": _START_MS + (index + 1) * _BAR_MS + 500,
                    "pressure_snapshot_count": 2,
                    "pressure_exchange_ts_ms": exchange,
                    "pressure_recv_ts_ms": exchange + 100,
                    "pressure_end_boundary_age_ms": 2_000,
                    "decision_imbalance_10": imbalance,
                    "pressure_fresh": True,
                    "pressure_scan_complete": True,
                    "pressure_source": "hyperliquid_mainnet_l2_rest",
                    "pressure_status": "fresh",
                    "eligible": index == 60,
                    "side": "long" if index == 60 else None,
                    "prospective": True,
                    "execution_authority": "none",
                },
                "execution_authority": "none",
                "report_only": True,
                "runtime_strategy_changed": False,
                "intents": [],
            }
        )
    return output


def _levels(price: float, size: float, *, descending: bool) -> list[dict[str, float]]:
    sign = -1.0 if descending else 1.0
    return [
        {"price": price + sign * index * 0.1, "size": size / 10.0}
        for index in range(10)
    ]
