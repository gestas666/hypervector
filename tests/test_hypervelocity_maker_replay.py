"""Causal post-only maker replay for backend Hypervelocity decisions."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.cli import main
from hypervector.research.maker_replay import MakerReplayConfig, replay_maker_orders
from hypervector.research.maker_replay_validation import validate_book, validate_trades


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


def _trades(
    seconds: list[int],
    sides: list[str],
    prices: list[float],
    sizes: list[float] | None = None,
) -> pd.DataFrame:
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    times = [origin + pd.Timedelta(seconds=value) for value in seconds]
    return pd.DataFrame(
        {
            "ts_ms": [int(value.timestamp() * 1000) for value in times],
            "trade_id": list(range(1, len(times) + 1)),
            "aggressor_side": sides,
            "price": prices,
            "size": sizes or [1.0] * len(times),
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


def test_trade_through_fills_long_entry_and_exit_only_from_later_prints() -> None:
    """Opposite aggressors beyond resting limits provide conservative evidence."""
    decisions = _decisions(["TREND_UP", "TREND_UP"])
    book = _book([60], [100.0], [101.0])
    trades = _trades(
        [61, 62],
        ["sell", "buy"],
        [99.0, 100.3],
        [30.0, 30.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="trade-through",
        ),
        trades=trades,
    )

    assert report.market_trade_prints == 2
    assert report.entry_fills == 1
    assert report.completed_trades == 1
    assert report.trades[0].entry_time_utc == "2026-01-01T00:01:01+00:00"
    assert report.trades[0].exit_time_utc == "2026-01-01T00:01:02+00:00"


def test_trade_through_fills_short_from_buy_print_beyond_resting_ask() -> None:
    """A buy aggressor above a resting sell proves a short maker entry crossed."""
    decisions = _decisions(["TREND_DOWN", "TREND_DOWN"])
    book = _book([60], [100.0], [101.0])
    trades = _trades([61], ["buy"], [102.0], [30.0])

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(initial_equity=100.0, fill_rule="trade-through"),
        trades=trades,
    )

    assert report.entry_fills == 1
    assert report.open_positions == 1
    assert report.trades == ()


def test_trade_through_does_not_claim_same_price_or_pre_submission_print() -> None:
    """Queue completion stays unresolved at the limit and before submission."""
    decisions = _decisions(["TREND_UP", "TREND_UP"])
    book = _book([60], [100.0], [101.0])
    trades = _trades(
        [59, 61],
        ["sell", "sell"],
        [99.0, 100.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(fill_rule="trade-through"),
        trades=trades,
    )

    assert report.entry_fills == 0
    assert report.pending_orders == 1


def test_trade_through_requires_cumulative_volume_to_cover_order() -> None:
    """A price-through print smaller than our order cannot imply a full fill."""
    trades = _trades([61, 62], ["sell", "sell"], [99.0, 99.0], [10.0, 18.0])
    config = MakerReplayConfig(initial_equity=100.0, fill_rule="trade-through")
    book = _book([60], [100.0], [101.0])
    decisions = _decisions(["TREND_UP", "TREND_UP"])

    partial = replay_maker_orders(
        book,
        decisions,
        config,
        trades=trades.iloc[:1],
    )

    report = replay_maker_orders(
        book,
        decisions,
        config,
        trades=trades,
    )

    assert partial.entry_fills == 0
    assert report.entry_fills == 1
    assert report.open_positions == 1
    assert report.trades == ()


def test_trade_through_deduplicates_exact_chunk_boundary_prints() -> None:
    """Inclusive adjacent windows may repeat one identical public trade."""
    trade = _trades([61], ["sell"], [99.0], [30.0])
    duplicated = pd.concat((trade, trade), ignore_index=True)

    report = replay_maker_orders(
        _book([60], [100.0], [101.0]),
        _decisions(["TREND_UP", "TREND_UP"]),
        MakerReplayConfig(initial_equity=100.0, fill_rule="trade-through"),
        trades=duplicated,
    )

    assert report.market_trade_prints == 1
    assert report.entry_fills == 1


def test_trade_through_rejects_conflicting_duplicate_trade_ids() -> None:
    """A repeated identifier with different market fields is corrupt evidence."""
    trades = _trades([61, 62], ["sell", "sell"], [99.0, 98.0])
    trades.loc[1, "trade_id"] = trades.loc[0, "trade_id"]

    with pytest.raises(ValueError, match="conflicting duplicate trade_id"):
        replay_maker_orders(
            _book([60], [100.0], [101.0]),
            _decisions(["TREND_UP", "TREND_UP"]),
            MakerReplayConfig(fill_rule="trade-through"),
            trades=trades,
        )


@pytest.mark.parametrize(
    ("book", "message"),
    [
        (pd.DataFrame({"ts_ms": [1]}), "missing columns"),
        (pd.DataFrame(columns=["ts_ms", "best_bid", "best_ask"]), "at least one"),
        (
            pd.DataFrame({"ts_ms": [1], "best_bid": [0.0], "best_ask": [1.0]}),
            "positive",
        ),
        (
            pd.DataFrame({"ts_ms": [1], "best_bid": [2.0], "best_ask": [1.0]}),
            "best_bid",
        ),
    ],
)
def test_book_validation_rejects_invalid_replay_evidence(
    book: pd.DataFrame, message: str
) -> None:
    """Malformed or crossed top-of-book evidence must fail closed."""
    with pytest.raises(ValueError, match=message):
        validate_book(book)


def test_book_validation_deduplicates_only_exact_boundary_snapshots() -> None:
    """Repeated chunk boundaries must agree before one snapshot is retained."""
    exact = pd.DataFrame(
        {
            "ts_ms": [1, 1],
            "best_bid": [100.0, 100.0],
            "best_ask": [101.0, 101.0],
        }
    )
    conflicting = exact.copy()
    conflicting.loc[1, "best_bid"] = 99.0

    assert len(validate_book(exact)) == 1
    with pytest.raises(ValueError, match="conflicting duplicate book timestamp"):
        validate_book(conflicting)


@pytest.mark.parametrize(
    ("trades", "message"),
    [
        (None, "requires public"),
        (pd.DataFrame({"ts_ms": [1]}), "missing columns"),
        (
            pd.DataFrame(
                columns=["ts_ms", "trade_id", "aggressor_side", "price", "size"]
            ),
            "requires public",
        ),
        (_trades([1], ["unknown"], [100.0]), "buy\\|sell"),
        (_trades([1], ["buy"], [0.0]), "positive"),
    ],
)
def test_trade_validation_rejects_invalid_replay_evidence(
    trades: pd.DataFrame | None, message: str
) -> None:
    """Trade-through accepts only complete positive public-print evidence."""
    with pytest.raises(ValueError, match=message):
        validate_trades(trades)


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
    decisions = _decisions(["TREND_DOWN"] * 8 + ["RANGE", "TREND_DOWN", "TREND_DOWN"])
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


def test_cli_reports_trade_through_when_public_prints_are_supplied(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The comparison surface must expose all three fill assumptions."""
    decisions = _decisions(["TREND_UP", "TREND_UP"])
    bars = pd.DataFrame(
        {
            "timestamp": decisions.index,
            "open": [100.0] * 2,
            "high": [101.0] * 2,
            "low": [99.0] * 2,
            "close": [100.0] * 2,
            "volume": [1.0] * 2,
        }
    )
    monkeypatch.setattr(
        "hypervector.cli._load_bars", lambda _args: (bars, {"source": "fixture"})
    )
    monkeypatch.setattr(
        "hypervector.regime.composite.classify_multitimeframe",
        lambda _bars, config: decisions,
    )
    monkeypatch.setattr(
        "hypervector.data.book_align.load_l2_jsonl",
        lambda _path: _book([60], [100.0], [101.0]),
    )
    monkeypatch.setattr(
        "hypervector.data.oxa_trades.load_trade_jsonl",
        lambda _path: _trades([61], ["sell"], [99.0]),
    )

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "hypervelocity-maker-replay",
            "--book-path",
            str(tmp_path / "books.jsonl"),
            "--trade-path",
            str(tmp_path / "trades.jsonl"),
            "--fill-rule",
            "all",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert set(payload["reports"]) == {"touch", "through", "trade-through"}
    assert payload["reports"]["trade-through"]["market_trade_prints"] == 1
    assert payload["trade_paths"] == [str(tmp_path / "trades.jsonl")]
