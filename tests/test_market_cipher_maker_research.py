"""Frozen contracts for the paired BTC maker-entry research screen."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from hypervector.research.market_cipher_maker_research import (
    build_paired_maker_requests,
    resolve_maker_replay_config,
    run_market_cipher_maker_research,
    validate_maker_baseline,
)


def _report() -> dict[str, object]:
    return {
        "schema_version": "market_cipher_strategy_screen_v3",
        "report_only": True,
        "execution_authority": "none",
        "place_attempted": False,
        "segment": "development",
        "start_utc": "2025-08-23T09:00:00+00:00",
        "end_utc": "2026-02-01T00:00:00+00:00",
        "bar_minutes": 15,
        "profile": {"name": "hulk_expansion_bidirectional_tuned_v2", "side": None},
        "symbol_attribution": {"BTC": {"trades": 1}},
        "replay_parameters": {
            "initial_equity": 15_000.0,
            "risk_fraction": 0.0025,
            "leverage": 5.0,
            "minimum_stop_bps": 20.0,
            "maximum_stop_bps": 75.0,
            "target_r_multiple": 3.0,
        },
    }


def _signals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "candidate": "hulk_expansion_bidirectional_tuned_v2",
                "signal_time_utc": pd.Timestamp("2025-08-28T18:00:00Z"),
                "side": "short",
                "score": 13.0,
                "eligible": True,
                "stop_anchor": 113_251.0,
                "symbol": "BTC",
            }
        ]
    )


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "candidate": "hulk_expansion_bidirectional_tuned_v2",
                "signal_score": 13.0,
                "symbol": "BTC",
                "direction": "short",
                "signal_time_utc": "2025-08-28T18:00:00+00:00",
                "entry_time_utc": "2025-08-28T18:15:00+00:00",
                "entry_price": 112_272.541,
                "initial_quantity": 0.044534,
            }
        ]
    )


def test_maker_replay_config_matches_frozen_one_minute_lifecycle() -> None:
    """Maker fees and exact entry must preserve the preregistered risk policy."""
    config = resolve_maker_replay_config()

    assert config.initial_equity == 15_000.0
    assert config.risk_fraction == 0.0025
    assert config.leverage == 5.0
    assert config.maximum_hold_bars == 1_440
    assert config.entry_fee_rate == 0.00015
    assert config.entry_slippage_bps == 0.0
    assert config.market_exit_fee_rate == 0.00045
    assert config.market_exit_slippage_bps == 2.0


def test_baseline_validation_rejects_non_frozen_timeframe() -> None:
    """A 30-minute baseline cannot masquerade as the frozen 15-minute signal."""
    report = _report()
    report["bar_minutes"] = 30

    with pytest.raises(ValueError, match="15-minute"):
        validate_maker_baseline(
            report,
            _signals(),
            _trades(),
            start_utc=pd.Timestamp("2025-08-23T09:00:00Z"),
            end_utc=pd.Timestamp("2026-02-01T00:00:00Z"),
            segment="development",
        )


def test_paired_trade_uses_original_quantity_and_next_bar_decision_time() -> None:
    """Queue depletion uses the exact accepted baseline order identity."""
    paired = build_paired_maker_requests(_signals(), _trades())

    assert len(paired) == 1
    assert paired[0].signal_time_utc == pd.Timestamp("2025-08-28T18:00:00Z")
    assert paired[0].request.decision_time_ms == 1_756_404_900_000
    assert paired[0].request.direction == "short"
    assert paired[0].request.quantity == pytest.approx(0.044534)
    assert paired[0].request.stop_anchor == 113_251.0


def test_unmatched_baseline_trade_fails_instead_of_guessing_signal_fields() -> None:
    """Missing signal identity cannot be repaired with inferred strategy data."""
    trades = _trades()
    trades.loc[0, "signal_time_utc"] = "2025-08-28T18:15:00+00:00"

    with pytest.raises(ValueError, match="exactly one signal"):
        build_paired_maker_requests(_signals(), trades)


def test_research_run_reconstructs_fill_and_replays_exact_maker_price(
    tmp_path: Path,
) -> None:
    """The end-to-end report must retain queue evidence and exact entry price."""
    start = pd.Timestamp("2025-08-28T00:00:00Z")
    end = pd.Timestamp("2025-08-29T00:00:00Z")
    baseline = _write_baseline(tmp_path, start, end)
    database = _write_database(tmp_path, start, end)
    funding = _write_funding(tmp_path, start, end + pd.Timedelta(days=1))

    run = run_market_cipher_maker_research(
        database_path=database,
        baseline_path=baseline,
        funding_paths=(funding,),
        start_utc=start,
        end_utc=end,
        segment="development",
    )

    assert run.report["execution_authority"] == "none"
    assert run.report["paired_baseline_trade_count"] == 1
    assert run.report["maker_entry_evidence"]["filled"] == 1
    assert run.report["maker_entry_evidence"]["missing_book"] == 0
    assert len(run.trades) == 1
    assert run.trades.iloc[0]["entry_price"] == 100.0
    assert run.entries.iloc[0]["displayed_queue"] == 1.0
    assert run.entries.iloc[0]["required_volume"] == 1.5


def _write_baseline(tmp_path: Path, start: pd.Timestamp, end: pd.Timestamp) -> Path:
    report = _report()
    report["start_utc"] = start.isoformat()
    report["end_utc"] = end.isoformat()
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    signals = _signals()
    signals["signal_time_utc"] = pd.Timestamp("2025-08-28T00:00:00Z")
    signals["side"] = "long"
    signals["stop_anchor"] = 99.0
    signals.to_parquet(path.with_suffix(".signals.parquet"), index=False)
    trades = _trades()
    trades["signal_time_utc"] = "2025-08-28T00:00:00+00:00"
    trades["entry_time_utc"] = "2025-08-28T00:15:00+00:00"
    trades["direction"] = "long"
    trades["entry_price"] = 101.0
    trades["initial_quantity"] = 0.5
    trades.to_parquet(path.with_suffix(".trades.parquet"), index=False)
    return path


def _write_database(tmp_path: Path, start: pd.Timestamp, end: pd.Timestamp) -> Path:
    path = tmp_path / "market.duckdb"
    books = pd.DataFrame(
        [
            {
                "symbol": "BTC",
                "ts_exchange_ms": int(
                    (start + pd.Timedelta(minutes=15, milliseconds=100)).value
                    // 1_000_000
                ),
                "best_bid": 100.0,
                "best_ask": 101.0,
                "bids": [{"n": 1, "px": 100.0, "sz": 1.0}],
                "asks": [{"n": 1, "px": 101.0, "sz": 1.0}],
            }
        ]
    )
    trades = pd.DataFrame(
        [
            {
                "symbol": "BTC",
                "trade_id": 1,
                "ts_exchange_ms": int(
                    (start + pd.Timedelta(minutes=15, seconds=2)).value // 1_000_000
                ),
                "aggressor_side": "sell",
                "price": 100.0,
                "size": 2.0,
                "bundle_id": "one",
            }
        ]
    )
    times = pd.date_range(
        start, end + pd.Timedelta(days=1), freq="1min", inclusive="left"
    )
    bars = pd.DataFrame(
        {
            "symbol": "BTC",
            "bar_open_at": times,
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "volume": 10.0,
            "trade_count": 1,
        }
    )
    bars.loc[bars["bar_open_at"].eq(start + pd.Timedelta(minutes=16)), "high"] = 103.0
    with duckdb.connect(str(path)) as connection:
        connection.register("books_frame", books)
        connection.register("trades_frame", trades)
        connection.register("bars_frame", bars)
        connection.execute(
            "CREATE TABLE replay_book_snapshots AS SELECT * FROM books_frame"
        )
        connection.execute("CREATE TABLE public_trades AS SELECT * FROM trades_frame")
        connection.execute(
            "CREATE TABLE canonical_trade_1m_bars AS SELECT * FROM bars_frame"
        )
    return path


def _write_funding(tmp_path: Path, start: pd.Timestamp, end: pd.Timestamp) -> Path:
    path = tmp_path / "funding.parquet"
    times = pd.date_range(start, end, freq="1h", inclusive="left")
    pd.DataFrame(
        {
            "timestamp": times,
            "funding_rate": 0.0,
            "source": "hl_funding_history",
        }
    ).to_parquet(path, index=False)
    return path
