"""Durable, execution-incapable MU shadow runner contracts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.mu_hip3_breakout_shadow import (
    MU_SHADOW_PROFILE_ID,
    MU_SHADOW_PROVIDER_ID,
)
from hypervector.live.mu_hip3_breakout_shadow_runner import (
    MU_LEDGER_PROFILE_ID,
    MuHip3BreakoutShadowRunner,
    MuHip3PublicRestSource,
    MuHip3ShadowPaths,
)
from hypervector.paper.book import BookLevel, BookSnapshot


def _bars(periods: int = 41) -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-09T12:00:00Z", periods=periods, freq="15min")
    closes = [100.0] * (periods - 1) + [102.0]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": [value + 0.1 for value in closes],
            "low": [value - 0.1 for value in closes],
            "close": closes,
            "volume": 10.0,
        }
    )


def _book(exchange_ms: int, recv_ms: int) -> BookSnapshot:
    return BookSnapshot(
        symbol="xyz:MU",
        bids=tuple(BookLevel(99.9 - index * 0.1, 3.0) for index in range(20)),
        asks=tuple(BookLevel(100.1 + index * 0.1, 1.0) for index in range(20)),
        ts_recv_ms=float(recv_ms),
        ts_exchange_ms=float(exchange_ms),
        source="hl_rest_l2",
    )


@dataclass
class _Source:
    books: list[BookSnapshot]
    frames: list[pd.DataFrame]
    candle_calls: int = 0

    def book_snapshot(self) -> BookSnapshot:
        return self.books.pop(0)

    def completed_candle_history(self, *, observed_at_ms: int) -> pd.DataFrame:
        assert observed_at_ms >= 0
        self.candle_calls += 1
        return self.frames.pop(0).copy()


def _paths(tmp_path: Path) -> MuHip3ShadowPaths:
    return MuHip3ShadowPaths(
        asset_ledger=tmp_path / "xyz:mu.jsonl",
        cohort_ledger=tmp_path / "unused_cohort.jsonl",
        cursor=tmp_path / "cursor.json",
        journal=tmp_path / "journal.jsonl",
        status=tmp_path / "status.json",
    )


def _jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_first_poll_bootstraps_durable_cursor_without_retroactive_decision(
    tmp_path: Path,
) -> None:
    observed_ms = int(pd.Timestamp("2026-08-09T22:00:01Z").timestamp() * 1_000)
    source = _Source([_book(observed_ms - 100, observed_ms - 50)], [_bars(40)])
    runner = MuHip3BreakoutShadowRunner(source=source, paths=_paths(tmp_path))

    result = runner.poll(observed_at_ms=observed_ms)

    assert result.decisions == ()
    assert result.bootstrap is True
    assert result.execution_authority == "none"
    assert result.intents == ()
    cursor = json.loads(_paths(tmp_path).cursor.read_text())
    assert cursor["provider_id"] == MU_SHADOW_PROVIDER_ID
    assert cursor["profile_id"] == MU_SHADOW_PROFILE_ID
    assert cursor["symbol"] == "xyz:MU"
    assert cursor["long_raw"] is None
    assert cursor["short_raw"] is None
    assert cursor["execution_authority"] == "none"
    assert _jsonl(_paths(tmp_path).journal) == []


def test_book_capture_persists_exact_mu_top_ten_receipt_evidence(
    tmp_path: Path,
) -> None:
    observed_ms = int(pd.Timestamp("2026-08-09T22:00:01Z").timestamp() * 1_000)
    source = _Source([_book(observed_ms - 100, observed_ms - 50)], [_bars(40)])
    runner = MuHip3BreakoutShadowRunner(source=source, paths=_paths(tmp_path))

    runner.poll(observed_at_ms=observed_ms)

    rows = _jsonl(_paths(tmp_path).asset_ledger)
    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "book_observation"
    assert row["profile_id"] == MU_LEDGER_PROFILE_ID
    assert row["execution_authority"] == "none"
    payload = row["payload"]
    assert payload["symbol"] == "xyz:MU"
    assert payload["source"] == "hyperliquid_mainnet_l2_rest"
    assert payload["exchange_ts_ms"] == observed_ms - 100
    assert payload["recv_ts_ms"] == observed_ms - 50
    assert len(payload["bids"]) == 10
    assert len(payload["asks"]) == 10


def test_restart_reuses_cursor_and_never_duplicates_one_decision(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    first_ms = int(pd.Timestamp("2026-08-09T21:45:01Z").timestamp() * 1_000)
    next_ms = int(pd.Timestamp("2026-08-09T22:00:01Z").timestamp() * 1_000)
    first = _Source([_book(first_ms - 100, first_ms - 50)], [_bars(39)])
    MuHip3BreakoutShadowRunner(source=first, paths=paths).poll(observed_at_ms=first_ms)
    proof = {
        "event_type": "book_observation",
        "profile_id": MU_LEDGER_PROFILE_ID,
        "execution_authority": "none",
        "payload": {
            **_jsonl(paths.asset_ledger)[0]["payload"],
            "exchange_ts_ms": next_ms - 900_001,
            "recv_ts_ms": next_ms - 900_001,
        },
    }
    paths.asset_ledger.write_text(
        json.dumps(proof) + "\n" + paths.asset_ledger.read_text()
    )
    next_source = _Source(
        [_book(next_ms - 1_000, next_ms - 900)],
        [_bars(40)],
    )
    restarted = MuHip3BreakoutShadowRunner(source=next_source, paths=paths)

    result = restarted.poll(observed_at_ms=next_ms)
    repeat_source = _Source([_book(next_ms + 100, next_ms + 200)], [])
    repeated = MuHip3BreakoutShadowRunner(source=repeat_source, paths=paths).poll(
        observed_at_ms=next_ms + 500
    )

    assert len(result.decisions) == 1
    assert repeated.decisions == ()
    assert len(_jsonl(paths.journal)) == 1
    assert _jsonl(paths.journal)[0]["execution_authority"] == "none"
    assert _jsonl(paths.journal)[0]["intents"] == []
    assert repeat_source.candle_calls == 0


def test_status_discloses_source_parity_blockers_and_no_execution_surface(
    tmp_path: Path,
) -> None:
    observed_ms = int(pd.Timestamp("2026-08-09T22:00:01Z").timestamp() * 1_000)
    runner = MuHip3BreakoutShadowRunner(
        source=_Source([_book(observed_ms - 100, observed_ms - 50)], [_bars(40)]),
        paths=_paths(tmp_path),
    )

    runner.poll(observed_at_ms=observed_ms)

    status = json.loads(_paths(tmp_path).status.read_text())
    assert status["mode"] == "mu_hip3_breakout_shadow_observer"
    assert status["execution_authority"] == "none"
    assert status["report_only"] is True
    assert status["signing_client_constructed"] is False
    assert status["orders_supported"] is False
    assert status["runtime_strategy_changed"] is False
    assert status["promotion_blockers"] == [
        "archive_public_trade_ohlc_vs_live_candleSnapshot_parity_unverified",
        "archive_ws_l2Book_vs_live_rest_pressure_decision_parity_unresolved",
    ]


def test_public_source_binds_exact_mu_book_and_completed_candles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []
    expected_book = _book(10, 20)
    expected_bars = _bars(40)

    def fetch_book(symbol: str) -> BookSnapshot:
        calls.append(("book", symbol))
        return expected_book

    def fetch_bars(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int,
    ) -> pd.DataFrame:
        calls.append(("bars", symbol, timeframe, lookback_days, end_ms))
        return expected_bars

    monkeypatch.setattr(
        "hypervector.live.mu_hip3_breakout_shadow_runner.fetch_hl_l2_book",
        fetch_book,
    )
    monkeypatch.setattr(
        "hypervector.live.mu_hip3_breakout_shadow_runner.fetch_hl_ohlcv_snapshot",
        fetch_bars,
    )
    source = MuHip3PublicRestSource()

    assert source.book_snapshot() == expected_book
    assert source.completed_candle_history(observed_at_ms=123) is expected_bars
    assert calls == [
        ("book", "xyz:MU"),
        ("bars", "xyz:MU", "15m", 2.0, 123),
    ]


@pytest.mark.parametrize("aliased", ["BTC", "xyz:SP500"])
def test_runner_rejects_aliased_public_book_identity(
    tmp_path: Path,
    aliased: str,
) -> None:
    observed_ms = int(pd.Timestamp("2026-08-09T22:00:01Z").timestamp() * 1_000)
    book = _book(observed_ms - 100, observed_ms - 50)
    source = _Source(
        [
            BookSnapshot(
                aliased,
                book.bids,
                book.asks,
                book.ts_recv_ms,
                book.ts_exchange_ms,
                book.source,
            )
        ],
        [_bars(40)],
    )

    with pytest.raises(ValueError, match="exact xyz:MU"):
        MuHip3BreakoutShadowRunner(source=source, paths=_paths(tmp_path)).poll(
            observed_at_ms=observed_ms
        )
    assert not _paths(tmp_path).asset_ledger.exists()
