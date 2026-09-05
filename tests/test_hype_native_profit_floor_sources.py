"""Tests for exact native-HYPE profit-floor source adapters."""

from __future__ import annotations

from hypervector.research.hype_native_profit_floor_sources import (
    prepare_closed_native_floor_input,
    prepare_prospective_native_floor_input,
)


def _candle_event(run_id: str) -> dict[str, object]:
    return {
        "event_type": "market_candles",
        "run_id": run_id,
        "payload": {
            "timeframe": "1m",
            "bars": {
                "HYPE": [
                    {
                        "timestamp_ms": 60_000,
                        "open": 100.0,
                        "high": 101.1,
                        "low": 99.9,
                        "close": 100.5,
                    },
                    {
                        "timestamp_ms": 120_000,
                        "open": 100.5,
                        "high": 100.8,
                        "low": 100.2,
                        "close": 100.4,
                    },
                    {
                        "timestamp_ms": 180_000,
                        "open": 100.4,
                        "high": 100.7,
                        "low": 100.3,
                        "close": 100.5,
                    },
                ]
            },
        },
    }


def _book_event(run_id: str) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "run_id": run_id,
        "payload": {
            "symbol": "HYPE",
            "exchange_ts_ms": 180_000,
            "recv_ts_ms": 180_005,
            "bids": [{"price": 100.25, "size": 10.0}],
            "asks": [{"price": 100.26, "size": 10.0}],
        },
    }


def _path_report(run_id: str) -> dict[str, object]:
    return {
        "identity": {"run_id": run_id, "symbol": "HYPE", "side": "long"},
        "execution_path": {
            "entry_book_time_ms": 10_000,
            "entry_price": 100.0,
            "entry_quantity": 1.0,
            "exit_reason": "maximum_hold",
        },
    }


def _funded_report() -> dict[str, object]:
    return {
        "entry_book_time_ms": 10_000,
        "exit_book_time_ms": 240_000,
        "net_pnl_usd_after_funding": 2.5,
        "funding_events": [{"event_ts_ms": 150_000, "cashflow_usd": -0.01}],
    }


def _status() -> dict[str, object]:
    return {
        "mode": "hype_native_v54_prospective_lifecycle_report_only",
        "contract": {"report_only": True, "execution_authority": "none"},
        "identity": {"run_id": "prospective", "symbol": "HYPE"},
        "lifecycles": [
            {
                "entry_book_time_ms": 10_000,
                "entry_price": 100.0,
                "entry_quantity": 1.0,
                "current_book_time_ms": 240_000,
                "exit_book_time_ms": 240_000,
                "exit_reason": "maximum_hold",
            }
        ],
    }


def _resolution() -> dict[str, object]:
    return {
        "mode": "hype_native_v54_exact_post_close_resolution_report_only",
        "contract": {"report_only": True, "execution_authority": "none"},
        "identity": {"run_id": "prospective", "symbol": "HYPE"},
        "lifecycles": [
            {
                "entry_book_time_ms": 10_000,
                "exit_book_time_ms": 240_000,
                "net_pnl_usd_after_funding": 3.0,
                "funding_events": [{"event_ts_ms": 150_000, "cashflow_usd": -0.02}],
            }
        ],
    }


def test_closed_adapter_reconciles_path_funding_candles_and_books() -> None:
    prepared = prepare_closed_native_floor_input(
        _path_report("closed"),
        _funded_report(),
        (_book_event("closed"),),
        (_candle_event("closed"),),
        lifecycle_id="HYPE:closed",
    )

    assert prepared.lifecycle.actual_net_after_funding_usd == 2.5
    assert prepared.lifecycle.funding_cashflows[0].cashflow_usd == -0.01
    assert [bar.timestamp_ms for bar in prepared.bars] == [60_000, 120_000, 180_000]
    assert prepared.books[0]["run_id"] == "closed"


def test_prospective_adapter_requires_resolution_for_exact_closed_economics() -> None:
    records = (_candle_event("prospective"), _book_event("prospective"))

    provisional = prepare_prospective_native_floor_input(_status(), records)
    exact = prepare_prospective_native_floor_input(
        _status(), records, resolution=_resolution()
    )

    assert provisional.lifecycle.natural_exit_time_ms == 240_000
    assert provisional.lifecycle.actual_net_after_funding_usd is None
    assert exact.lifecycle.actual_net_after_funding_usd == 3.0
    assert exact.lifecycle.funding_complete_through_ms == 240_000
