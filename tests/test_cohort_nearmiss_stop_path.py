"""Causal stop-path evidence for a report-only near miss."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.research.cohort_nearmiss_stop_path import (
    NearMissPathSpec,
    build_nearmiss_stop_path,
)


def test_long_path_reports_candle_and_executable_book_stop_proxies() -> None:
    """A stopped counterfactual must retain both source boundaries."""
    spec = _spec()
    cohort = [
        _candles(0, 100.0, 101.0, 99.5, 100.5),
        _candles(60_000, 100.5, 100.6, 98.9, 99.0),
    ]
    assets = [
        _book(2_000, 100.4, 100.5),
        _book(70_000, 98.95, 98.96),
    ]

    report = build_nearmiss_stop_path(cohort, assets, spec)

    assert report["technical"]["complete"] is True
    assert report["status"] == "protective_stop_proxy_crossed"
    assert report["risk_path"]["stop_price"] == pytest.approx(99.0)
    assert report["risk_path"]["first_candle_cross_timestamp_ms"] == 60_000
    assert report["risk_path"]["first_executable_cross_timestamp_ms"] == 70_000
    assert report["risk_path"]["actual_mark_trigger_observed"] is False
    assert report["economics"]["gross_exit_proxy_bps"] == pytest.approx(-105.0)
    assert report["economics"]["after_hurdle_exit_proxy_bps"] == pytest.approx(-118.0)
    assert report["economics"]["after_hurdle_exit_proxy_usd"] == pytest.approx(-59.0)


def test_candle_cross_without_observed_book_cross_remains_unpriced() -> None:
    """A candle low cannot be success-shaped into an executable exit price."""
    report = build_nearmiss_stop_path(
        [
            _candles(0, 100.0, 100.5, 99.5, 100.0),
            _candles(60_000, 100.0, 100.1, 98.9, 99.2),
        ],
        [_book(70_000, 99.1, 99.2)],
        _spec(),
    )

    assert report["status"] == "protective_stop_candle_proxy_only"
    assert report["risk_path"]["first_executable_cross_timestamp_ms"] is None
    assert report["economics"]["gross_exit_proxy_bps"] is None


def test_conflicting_duplicate_candle_invalidates_path() -> None:
    """Two values for one completed bar must remain an explicit defect."""
    report = build_nearmiss_stop_path(
        [
            _candles(0, 100.0, 100.5, 99.5, 100.0),
            _candles(0, 100.0, 101.0, 99.0, 100.0),
        ],
        [],
        _spec(),
    )

    assert report["technical"]["complete"] is False
    assert report["technical"]["technical_gaps"] == ["conflicting_completed_candle"]
    assert report["status"] == "technical_evidence_incomplete"


def test_target_before_stop_uses_first_executable_target_quote() -> None:
    """A target touched and quoted first must resolve before a later stop."""
    report = build_nearmiss_stop_path(
        [
            _candles(0, 100.0, 100.5, 99.5, 100.0),
            _candles(60_000, 100.0, 101.1, 99.8, 101.0),
            _candles(120_000, 101.0, 101.2, 98.9, 99.0),
        ],
        [
            _book(70_000, 101.05, 101.06),
            _book(130_000, 98.95, 98.96),
        ],
        replace(_spec(), target_bps=100.0),
    )

    assert report["status"] == "profit_target_proxy_crossed"
    assert report["risk_path"]["target_price"] == pytest.approx(101.0)
    assert report["risk_path"]["first_observed_barrier"] == "target"
    assert report["risk_path"]["first_target_candle_cross_timestamp_ms"] == 60_000
    assert report["risk_path"]["first_target_executable_cross_timestamp_ms"] == 70_000
    assert report["economics"]["exit_proxy_barrier"] == "target"
    assert report["economics"]["gross_exit_proxy_bps"] == pytest.approx(105.0)
    assert report["economics"]["after_hurdle_exit_proxy_usd"] == pytest.approx(46.0)


def test_stop_before_target_keeps_protective_stop_outcome() -> None:
    """A stop quoted first must not be overwritten by a later target touch."""
    report = build_nearmiss_stop_path(
        [
            _candles(0, 100.0, 100.5, 99.5, 100.0),
            _candles(60_000, 100.0, 100.2, 98.9, 99.0),
            _candles(120_000, 99.0, 101.1, 98.8, 101.0),
        ],
        [
            _book(70_000, 98.95, 98.96),
            _book(130_000, 101.05, 101.06),
        ],
        replace(_spec(), target_bps=100.0),
    )

    assert report["status"] == "protective_stop_proxy_crossed"
    assert report["risk_path"]["first_observed_barrier"] == "stop"
    assert report["economics"]["exit_proxy_barrier"] == "stop"
    assert report["economics"]["gross_exit_proxy_bps"] == pytest.approx(-105.0)


def test_same_candle_stop_and_target_remain_order_ambiguous() -> None:
    """OHLC cannot order two barriers touched inside one completed minute."""
    report = build_nearmiss_stop_path(
        [
            _candles(0, 100.0, 100.5, 99.5, 100.0),
            _candles(60_000, 100.0, 101.1, 98.9, 100.0),
        ],
        [
            _book(70_000, 101.05, 101.06),
            _book(80_000, 98.95, 98.96),
        ],
        replace(_spec(), target_bps=100.0),
    )

    assert report["status"] == "barrier_order_ambiguous_within_candle"
    assert report["risk_path"]["first_observed_barrier"] is None
    assert report["risk_path"]["same_candle_barrier_ambiguity"] is True
    assert report["economics"]["gross_exit_proxy_bps"] is None


def test_partial_availability_minute_cannot_create_a_stop_cross() -> None:
    """OHLC observed before provider availability cannot become path evidence."""
    spec = replace(
        _spec(),
        decision_time_ms=0,
        available_time_ms=30_000,
    )
    report = build_nearmiss_stop_path(
        [
            _candles(0, 100.0, 100.1, 98.0, 99.0),
            _candles(60_000, 100.0, 100.2, 99.5, 100.0),
            _candles(120_000, 100.0, 100.1, 98.9, 99.0),
        ],
        [
            _book(20_000, 98.9, 99.0),
            _book(130_000, 98.9, 99.0),
        ],
        spec,
    )

    assert report["identity"]["available_time_ms"] == 30_000
    assert report["identity"]["causal_path_start_time_ms"] == 60_000
    assert report["risk_path"]["first_candle_cross_timestamp_ms"] == 120_000
    assert report["risk_path"]["first_executable_cross_timestamp_ms"] == 130_000


def test_other_symbol_candle_batches_are_ignored() -> None:
    """Incremental multi-asset batches may legitimately omit the target symbol."""
    other = _candles(0, 100.0, 101.0, 99.0, 100.0)
    bars = other["payload"]["bars"]
    assert isinstance(bars, dict)
    bars["BTC"] = bars.pop("HYPE")

    report = build_nearmiss_stop_path(
        [other, _candles(0, 100.0, 100.5, 99.5, 100.0)],
        [],
        _spec(),
    )

    assert report["technical"]["complete"] is True
    assert report["technical"]["completed_candles"] == 1


def test_excursion_magnitudes_cannot_be_negative() -> None:
    """A path wholly below a long reference has zero favorable excursion."""
    report = build_nearmiss_stop_path(
        [_candles(0, 99.8, 99.9, 98.9, 99.0)],
        [_book(2_000, 98.9, 99.0)],
        _spec(),
    )

    assert report["risk_path"]["maximum_favorable_excursion_bps"] == 0.0
    assert report["risk_path"]["maximum_adverse_excursion_bps"] >= 0.0


def _spec() -> NearMissPathSpec:
    return NearMissPathSpec(
        run_id="run-a",
        profile_id="profile-a",
        profile_fingerprint="f" * 64,
        strategy_id="strategy-a",
        symbol="HYPE",
        side="long",
        decision_time_ms=0,
        available_time_ms=0,
        reference_price=100.0,
        stop_bps=100.0,
        soft_maximum_hold_seconds=120,
        modeled_round_trip_hurdle_bps=13.0,
        notional_usd=5_000.0,
    )


def _candles(
    timestamp_ms: int,
    open_px: float,
    high: float,
    low: float,
    close: float,
) -> dict[str, object]:
    return {
        "event_type": "market_candles",
        "run_id": "run-a",
        "profile_id": "profile-a",
        "profile_fingerprint": "f" * 64,
        "payload": {
            "timeframe": "1m",
            "bars": {
                "HYPE": [
                    {
                        "timestamp_ms": timestamp_ms,
                        "open": open_px,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": 1.0,
                    }
                ]
            },
        },
    }


def _book(timestamp_ms: int, bid: float, ask: float) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "run_id": "run-a",
        "profile_id": "profile-a_hype",
        "payload": {
            "exchange_ts_ms": timestamp_ms,
            "bids": [{"price": bid, "size": 10.0}],
            "asks": [{"price": ask, "size": 10.0}],
        },
    }
