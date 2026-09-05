"""Causal feasibility tests for OI-conditioned deleveraging events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from hypervector.research.oi_deleveraging_feasibility import (
    OiDeleveragingConfig,
    assess_development,
    build_signals,
    replay_signals,
)


def _minutes(count: int = 35, *, gap_at: int | None = None) -> pd.DataFrame:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    records: list[dict[str, object]] = []
    price = 100.0
    open_interest = 1_000.0
    for index in range(count):
        offset = index + (1 if gap_at is not None and index >= gap_at else 0)
        minute = start + timedelta(minutes=offset)
        price *= 1.0001
        records.append(
            {
                "minute": minute,
                "close": price,
                "trade_imbalance": 0.2,
                "book_imbalance": 0.2,
                "open_interest": open_interest,
                "first_bid": price - 0.01,
                "first_ask": price + 0.01,
                "first_quote_at": minute + timedelta(seconds=2),
            }
        )
    return pd.DataFrame.from_records(records)


def _event_minutes() -> pd.DataFrame:
    rows = _minutes()
    event = rows.index[24]
    rows.loc[event, "close"] = float(rows.loc[event - 1, "close"]) * 0.995
    rows.loc[event, "open_interest"] = 990.0
    rows.loc[event, "trade_imbalance"] = 0.6
    rows.loc[event, "book_imbalance"] = 0.6
    terminal = rows.index[24]
    rows.loc[terminal, "trade_imbalance"] = -0.4
    rows.loc[terminal, "book_imbalance"] = -0.4
    return rows


def _config() -> OiDeleveragingConfig:
    return OiDeleveragingConfig(
        warmup_bars=3,
        minimum_shock_bps=13.0,
        minimum_oi_contraction_pct=-0.0005,
        price_quantile=0.9,
        oi_quantile=0.1,
        primary_horizon_minutes=5,
        maximum_quote_delay_seconds=15,
    )


def test_signal_uses_prior_only_thresholds_and_freezes_exhaustion() -> None:
    rows = _event_minutes()

    signals = build_signals(rows, "BTC", _config())

    assert len(signals) == 1
    signal = signals.iloc[0]
    assert signal["shock_side"] == "down"
    assert bool(signal["terminal_trade_exhaustion"]) is False
    assert bool(signal["terminal_book_replenishment"]) is False
    assert bool(signal["exhausted"]) is False
    assert signal["shock_threshold_bps"] < abs(signal["shock_bps"])


def test_gap_resets_warmup_and_cannot_be_bridged() -> None:
    rows = _event_minutes()
    rows = pd.concat([rows.iloc[:22], rows.iloc[23:]], ignore_index=True)

    signals = build_signals(rows, "BTC", _config())

    assert signals.empty


def test_replay_uses_executable_bid_ask_and_rejects_stale_quote() -> None:
    rows = _event_minutes()
    signals = build_signals(rows, "BTC", _config())
    decision = pd.Timestamp(signals.iloc[0]["decision_at"])
    exit_minute = decision + timedelta(minutes=5)
    rows.loc[rows["minute"].eq(exit_minute), "first_bid"] = 101.0
    rows.loc[rows["minute"].eq(exit_minute), "first_ask"] = 101.01

    nominal = replay_signals(rows, signals, round_trip_cost_bps=13.0)

    assert nominal.rejections == ()
    assert len(nominal.trades) == 1
    trade = nominal.trades[0]
    assert trade.side == "long"
    assert trade.entry_price > 0.0
    assert trade.exit_price == 101.0
    assert trade.net_bps == trade.gross_bps - 13.0

    rows.loc[rows["minute"].eq(decision), "first_quote_at"] = decision + timedelta(
        seconds=16
    )
    stale = replay_signals(rows, signals, round_trip_cost_bps=13.0)
    assert stale.trades == ()
    assert stale.rejections[0].reason == "stale_entry_quote"


def test_development_assessment_fails_closed_on_small_sample() -> None:
    rows = _event_minutes()
    signals = build_signals(rows, "BTC", _config())
    replay = replay_signals(rows, signals, round_trip_cost_bps=13.0)

    assessment = assess_development(replay, symbols=("BTC", "SOL"))

    assert assessment["passed"] is False
    assert "minimum_total_events" in assessment["failures"]
    assert assessment["confirmation_authorized"] is False


def test_overlapping_signal_is_suppressed_until_primary_horizon() -> None:
    rows = _event_minutes()
    second = rows.index[29]
    rows.loc[second, "close"] = float(rows.loc[second - 1, "close"]) * 0.994
    rows.loc[second, "open_interest"] = 980.0

    signals = build_signals(rows, "BTC", _config())

    assert len(signals) == 1
