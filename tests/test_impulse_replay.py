"""Tests for reconstructing the recorded Hypervelocity impulse replay."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from hypervector.research.impulse_replay import (
    attach_completed_bar_features,
    assign_completed_regimes,
    load_decision_events,
    load_completed_regimes,
    load_completed_mid_bars,
    materialized_replay_database,
    pair_replay_trades,
    run_replay_autotune,
)


def _write_decision_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE decision_samples (
            recorded_at REAL NOT NULL,
            coin TEXT NOT NULL,
            direction TEXT,
            event_type TEXT,
            current_mid REAL,
            impulse_score REAL,
            momentum_score REAL,
            velocity_bps_1s REAL,
            velocity_bps_3s REAL,
            velocity_bps_5s REAL,
            acceleration_bps REAL,
            feature_age_ms INTEGER,
            features_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE feature_samples (
            id INTEGER PRIMARY KEY,
            coin TEXT NOT NULL,
            feature_time INTEGER NOT NULL,
            mid REAL
        )
        """
    )
    rows = [
        (1.0, "BTC", "long", "WOULD_EXIT_INVALIDATION", 99.0),
        (2.0, "BTC", "long", "WOULD_ENTER_LONG", 100.0),
        (3.0, "BTC", "long", "WOULD_EXIT_INVALIDATION", 101.0),
        (4.0, "BTC", "short", "WOULD_ENTER_SHORT", 100.0),
        (5.0, "BTC", "short", "WOULD_CLOSE_TP_10", 99.0),
        (6.0, "ETH", "long", "WOULD_ENTER_LONG", 10.0),
    ]
    connection.executemany(
        """
        INSERT INTO decision_samples VALUES (
            ?, ?, ?, ?, ?, 1.0, 0.8, 0.1, 0.2, 0.3, 0.01, 10,
            '{"obi_5":"0.2","obi_10":"0.1","spread_bps":"1.0"}'
        )
        """,
        rows,
    )
    connection.executemany(
        "INSERT INTO feature_samples (coin, feature_time, mid) VALUES (?, ?, ?)",
        [("BTC", bucket * 900_000 + 899_000, 100.0 + bucket) for bucket in range(80)],
    )
    connection.commit()
    connection.close()


def test_pair_replay_trades_uses_recorded_entries_and_exits(tmp_path: Path):
    """Replay pairing must preserve both lanes and report unmatched events."""
    database = tmp_path / "impulse.sqlite"
    _write_decision_fixture(database)

    events = load_decision_events(database, coin="BTC")
    trades, stats = pair_replay_trades(events, fee_bps_side=4.5, leverage=40.0)

    assert trades["direction"].tolist() == ["long", "short"]
    assert trades["gross_price_pct"].round(6).tolist() == [1.0, 1.0]
    assert trades["net_margin_pct"].round(6).tolist() == [36.4, 36.4]
    assert trades["obi_10"].tolist() == [0.1, 0.1]
    assert stats.completed_trades == 2
    assert stats.unmatched_exits == 1


def test_assign_completed_regimes_never_uses_future_bucket():
    """An entry may consume only a regime bucket completed before entry time."""
    trades = pd.DataFrame({"entry_ts_ms": [3_000, 5_000]})
    regimes = pd.DataFrame(
        {
            "available_ts_ms": [2_000, 4_000],
            "regime": ["up", "down"],
        }
    )

    assigned = assign_completed_regimes(trades, regimes)

    assert assigned["regime"].tolist() == ["up", "down"]


def test_load_completed_regimes_uses_last_mid_and_availability(tmp_path: Path):
    """Regime buckets become observable only after their 15-minute close."""
    database = tmp_path / "impulse.sqlite"
    _write_decision_fixture(database)

    regimes = load_completed_regimes(database, coin="BTC")

    assert len(regimes) == 80
    assert regimes.iloc[0]["available_ts_ms"] == 900_000
    assert regimes.iloc[-1]["close"] == 179.0
    assert "up" in set(regimes["regime"])


def test_materialized_raw_database_does_not_copy_source(tmp_path: Path):
    """Raw SQLite inputs should be consumed directly in read-only mode."""
    database = tmp_path / "impulse.sqlite"
    _write_decision_fixture(database)

    with materialized_replay_database(database) as materialized:
        assert materialized == database


def test_replay_autotune_reports_losing_trials_without_aborting():
    """Negative performance remains a valid result under the project charter."""
    trades = pd.DataFrame(
        {
            "entry_ts_ms": list(range(20)),
            "direction": ["long"] * 20,
            "regime": ["up"] * 20,
            "impulse_score": [1.0] * 20,
            "momentum_score": [0.8] * 20,
            "velocity_bps_5s": [1.0] * 20,
            "spread_bps": [1.0] * 20,
            "obi_10": [0.2] * 20,
            "feature_age_ms": [100.0] * 20,
            "gross_price_pct": [-0.01] * 20,
            "net_margin_pct": [-4.0] * 20,
        }
    )

    board = run_replay_autotune(
        trades,
        lane="uptrend_long",
        n_trials=5,
        seed=42,
    )

    assert len(board["trials"]) == 5
    assert {trial["status"] for trial in board["trials"]} == {"ok"}
    assert board["best_train_metrics"]["net_margin_pct"] < 0
    assert board["oos_metrics"]["net_margin_pct"] < 0


def test_completed_mid_bars_and_features_are_causal(tmp_path: Path):
    """Runtime-compatible features must come from already closed replay bars."""
    database = tmp_path / "impulse.sqlite"
    _write_decision_fixture(database)
    bars = load_completed_mid_bars(database, coin="BTC", timeframe_minutes=15)
    trade = pd.DataFrame(
        {
            "entry_ts_ms": [bars.iloc[-1]["available_ts_ms"] + 1],
            "exit_ts_ms": [bars.iloc[-1]["available_ts_ms"] + 60_000],
            "net_margin_pct": [1.0],
        }
    )

    featured = attach_completed_bar_features(trade, bars)

    assert len(bars) == 80
    assert bars.iloc[0]["available_ts_ms"] == 900_000
    assert featured.iloc[0]["close_vs_ema21_bps"] > 0.0
    assert featured.iloc[0]["label"] == 1
    assert featured.iloc[0]["outcome_ts_ms"] == trade.iloc[0]["exit_ts_ms"]
