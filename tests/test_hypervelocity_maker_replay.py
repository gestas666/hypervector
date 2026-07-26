"""Causal post-only maker replay for backend Hypervelocity decisions."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.cli import main
from hypervector.research.maker_replay import MakerReplayConfig, replay_maker_orders


def _decisions(states: list[str]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(states), freq="1min", tz="UTC")
    return pd.DataFrame(
        {"primary_regime": states, "breakout_direction": [None] * len(states)},
        index=index,
    )


def _book(
    seconds: list[int],
    bids: list[float],
    asks: list[float],
) -> pd.DataFrame:
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    times = [origin + pd.Timedelta(seconds=value) for value in seconds]
    return pd.DataFrame(
        {
            "ts_ms": [int(value.timestamp() * 1000) for value in times],
            "best_bid": bids,
            "best_ask": asks,
        }
    )


def test_touch_replay_compounds_70pct_margin_at_40x() -> None:
    decisions = _decisions(["TREND_UP", "TREND_UP", "TREND_UP"])
    book = _book(
        [60, 70, 80],
        [100.0, 99.0, 100.2],
        [101.0, 100.0, 100.3],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
        ),
    )

    assert report.completed_trades == 1
    trade = report.trades[0]
    assert trade.margin == pytest.approx(70.0)
    assert trade.notional == pytest.approx(2_800.0)
    assert trade.quantity == pytest.approx(28.0)
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(100.2)
    assert report.final_equity == pytest.approx(105.6)


def test_through_rule_does_not_claim_touch_only_fill() -> None:
    decisions = _decisions(["TREND_UP", "TREND_UP"])
    book = _book([60, 70], [100.0, 99.0], [101.0, 100.0])

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="through",
            tick_size=1.0,
        ),
    )

    assert report.entry_fills == 0
    assert report.pending_orders == 1


def test_replay_does_not_use_open_candle_or_trade_range() -> None:
    decisions = _decisions(["TREND_UP", "RANGE", "TREND_DOWN"])
    book = _book(
        [30, 120, 180],
        [100.0, 100.0, 100.0],
        [101.0, 101.0, 101.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(fill_rule="touch"),
    )

    assert report.submitted_entries == 1
    assert report.submission_times_utc == ("2026-01-01T00:03:00+00:00",)


def test_pending_entry_cancels_when_backend_moves_to_range() -> None:
    decisions = _decisions(["TREND_UP", "RANGE", "RANGE"])
    book = _book(
        [60, 120],
        [100.0, 100.0],
        [101.0, 101.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(fill_rule="through", tick_size=1.0),
    )

    assert report.submitted_entries == 1
    assert report.canceled_entries == 1
    assert report.pending_orders == 0


def test_expired_entry_retries_only_after_directional_regime_resets() -> None:
    decisions = _decisions(
        ["TREND_DOWN"] * 8 + ["RANGE", "TREND_DOWN", "TREND_DOWN"]
    )
    seconds = list(range(60, 661, 60))
    bids = [100.0 - float(index) for index in range(len(seconds))]
    asks = [bid + 1.0 for bid in bids]

    report = replay_maker_orders(
        _book(seconds, bids, asks),
        decisions,
        MakerReplayConfig(fill_rule="through", tick_size=1.0),
    )

    assert report.expired_entries == 1
    assert report.submitted_entries == 2
    assert report.submission_times_utc == (
        "2026-01-01T00:01:00+00:00",
        "2026-01-01T00:10:00+00:00",
    )


def test_cli_reports_touch_and_through_without_placing_orders(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    decisions = _decisions(["TREND_UP", "TREND_UP", "TREND_UP"])
    bars = pd.DataFrame(
        {
            "timestamp": decisions.index,
            "open": [100.0] * 3,
            "high": [101.0] * 3,
            "low": [99.0] * 3,
            "close": [100.0] * 3,
            "volume": [1.0] * 3,
        }
    )
    book = _book([60, 70, 80], [100.0, 99.0, 100.2], [101.0, 100.0, 100.3])
    monkeypatch.setattr(
        "hypervector.cli._load_bars",
        lambda _args: (bars, {"source": "fixture"}),
    )
    monkeypatch.setattr(
        "hypervector.regime.composite.classify_multitimeframe",
        lambda _bars, config: decisions,
    )
    monkeypatch.setattr(
        "hypervector.data.book_align.load_l2_jsonl",
        lambda _path: book,
    )

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "hypervelocity-maker-replay",
            "--book-path",
            str(tmp_path / "book.jsonl"),
            "--initial-equity",
            "100",
            "--maker-fee-rate",
            "0",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["report_only"] is True
    assert set(payload["reports"]) == {"touch", "through"}
    assert payload["reports"]["touch"]["completed_trades"] == 1
