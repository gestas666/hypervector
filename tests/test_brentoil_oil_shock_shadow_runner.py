"""Durable no-authority BRENTOIL oil-shock shadow runner tests."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.brentoil_oil_shock_shadow import (
    BRENTOIL_OIL_SHOCK_PROFILE_ID,
    BRENTOIL_OIL_SHOCK_PROVIDER_ID,
)
from hypervector.live.brentoil_oil_shock_shadow_runner import (
    BRENTOIL_OIL_SHOCK_LEDGER_PROFILE_ID,
    BrentoilOilShockShadowPaths,
    BrentoilOilShockShadowRunner,
)
from hypervector.paper.book import BookLevel, BookSnapshot


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


def test_first_poll_bootstraps_without_retroactive_decision(tmp_path: Path) -> None:
    """Startup anchors the latest close and preserves a blank journal."""
    observed = _ms("2026-08-15T12:40:05Z")
    runner = BrentoilOilShockShadowRunner(
        source=_Source([_book(observed)], [_bars(8)]), paths=_paths(tmp_path)
    )

    result = runner.poll(observed_at_ms=observed)

    assert result.bootstrap is True
    assert result.decisions == ()
    assert result.intents == ()
    cursor = json.loads(_paths(tmp_path).cursor.read_text())
    assert cursor["provider_id"] == BRENTOIL_OIL_SHOCK_PROVIDER_ID
    assert cursor["profile_id"] == BRENTOIL_OIL_SHOCK_PROFILE_ID
    assert cursor["execution_authority"] == "none"
    assert not _paths(tmp_path).journal.exists()
    candles = _jsonl(_paths(tmp_path).candle_ledger)
    assert len(candles) == 8
    assert all(row["historical_warmup"] is True for row in candles)
    assert all(row["prospective"] is False for row in candles)
    assert candles[-1]["source"] == "hyperliquid_public_candleSnapshot_5m"


def test_runner_persists_exact_book_and_discloses_evidence_limits(
    tmp_path: Path,
) -> None:
    """Every poll retains top-ten BBO provenance and honest blockers."""
    observed = _ms("2026-08-15T12:40:05Z")
    paths = _paths(tmp_path)
    runner = BrentoilOilShockShadowRunner(
        source=_Source([_book(observed)], [_bars(8)]), paths=paths
    )

    runner.poll(observed_at_ms=observed)

    row = _jsonl(paths.book_ledger)[0]
    assert row["profile_id"] == BRENTOIL_OIL_SHOCK_LEDGER_PROFILE_ID
    assert row["execution_authority"] == "none"
    assert row["payload"]["symbol"] == "xyz:BRENTOIL"
    assert len(row["payload"]["bids"]) == 10
    status = json.loads(paths.status.read_text())
    assert status["execution_authority"] == "none"
    assert status["orders_supported"] is False
    assert status["signing_client_constructed"] is False
    assert status["live_canary_execution_observations"] == 6
    assert status["live_canary_max_abs_slippage_bps"] == 8.464583786205068
    assert status["promotion_blockers"] == [
        "archive_public_trade_ohlc_vs_live_candleSnapshot_parity_unverified",
        "mechanism_specific_live_fill_slippage_not_observed",
        "historical_mark_path_incomplete",
        "validation_and_holdout_unopened",
    ]


def test_book_capture_normalizes_bounded_exchange_clock_lead(
    tmp_path: Path,
) -> None:
    """A small venue-clock lead stays causal and retains raw provenance."""
    local_receipt = _ms("2026-08-15T12:40:05Z")
    exchange = local_receipt + 1_600
    source = _Source([_book_times(exchange, local_receipt)], [_bars(8)])

    result = BrentoilOilShockShadowRunner(source=source, paths=_paths(tmp_path)).poll(
        observed_at_ms=local_receipt
    )

    payload = _jsonl(_paths(tmp_path).book_ledger)[0]["payload"]
    assert result.observed_at_ms == exchange
    assert payload["exchange_ts_ms"] == exchange
    assert payload["recv_ts_ms"] == exchange
    assert payload["local_recv_ts_ms"] == local_receipt
    assert payload["negative_clock_skew_ms"] == 1_600


def test_book_capture_rejects_excessive_exchange_clock_lead(tmp_path: Path) -> None:
    """A material clock disagreement remains a fail-closed data error."""
    local_receipt = _ms("2026-08-15T12:40:05Z")
    source = _Source([_book_times(local_receipt + 5_001, local_receipt)], [_bars(8)])

    with pytest.raises(ValueError, match="clock skew exceeds 5000ms"):
        BrentoilOilShockShadowRunner(source=source, paths=_paths(tmp_path)).poll(
            observed_at_ms=local_receipt
        )


def test_restart_reuses_cursor_and_journals_once(tmp_path: Path) -> None:
    """A restarted writer cannot duplicate one completed-bar decision."""
    paths = _paths(tmp_path)
    first = _ms("2026-08-15T12:40:05Z")
    BrentoilOilShockShadowRunner(
        source=_Source([_book(first)], [_bars(8)]), paths=paths
    ).poll(observed_at_ms=first)
    second = _ms("2026-08-15T12:45:05Z")
    restarted = BrentoilOilShockShadowRunner(
        source=_Source([_book(second)], [_bars(9)]), paths=paths
    )

    result = restarted.poll(observed_at_ms=second)
    repeated = BrentoilOilShockShadowRunner(
        source=_Source([_book(second + 500)], []), paths=paths
    ).poll(observed_at_ms=second + 500)

    assert len(result.decisions) == 1
    assert repeated.decisions == ()
    assert len(_jsonl(paths.journal)) == 1
    assert _jsonl(paths.journal)[0]["intents"] == []
    status = json.loads(paths.status.read_text())
    assert status["decisions_this_poll"] == 0
    assert status["decision_rows_total"] == 1
    assert status["eligible_decisions_total"] == 0
    assert status["last_decision_time_ms"] == second - 5_000
    assert status["last_non_action_reason"] == "signal_history_incomplete"
    candles = _jsonl(paths.candle_ledger)
    assert len(candles) == 9
    assert candles[-1]["prospective"] is True
    assert candles[-1]["historical_warmup"] is False
    assert status["candle_rows_total"] == 9
    assert status["prospective_candle_rows_total"] == 1


def test_restart_freezes_disclosed_volume_revision(tmp_path: Path) -> None:
    """A late volume revision cannot stop or rewrite prospective decisions."""
    observed = _ms("2026-08-15T12:40:05Z")
    revised_paths = _paths(tmp_path / "revised")
    baseline_paths = _paths(tmp_path / "baseline")
    for paths in (revised_paths, baseline_paths):
        BrentoilOilShockShadowRunner(
            source=_Source([_book(observed)], [_bars(8)]), paths=paths
        ).poll(observed_at_ms=observed)
    current = _ms("2026-08-15T12:45:05Z")
    revised = _bars(9)
    revised.loc[7, "volume"] = 10.25

    changed = BrentoilOilShockShadowRunner(
        source=_Source([_book(current)], [revised]), paths=revised_paths
    ).poll(observed_at_ms=current)
    baseline = BrentoilOilShockShadowRunner(
        source=_Source([_book(current)], [_bars(9)]), paths=baseline_paths
    ).poll(observed_at_ms=current)
    BrentoilOilShockShadowRunner(
        source=_Source([_book(current + 500)], []), paths=revised_paths
    ).poll(observed_at_ms=current + 500)

    assert (
        changed.decisions[0].signal_window_sha256
        == baseline.decisions[0].signal_window_sha256
    )
    assert _jsonl(revised_paths.candle_ledger)[7]["volume"] == 10.0
    status = json.loads(revised_paths.status.read_text())
    assert status["source_revision_rows_current_snapshot"] == 0
    assert status["source_revision_rows_total"] == 1
    assert status["source_revision_fields_total"] == ["volume"]


def test_status_exposes_direction_counts_and_threshold_proximity(
    tmp_path: Path,
) -> None:
    """Status must distinguish a quiet strategy from one nearing its threshold."""
    paths = _paths(tmp_path)
    first = _ms("2026-08-15T12:40:05Z")
    BrentoilOilShockShadowRunner(
        source=_Source([_book(first)], [_bars(8)]), paths=paths
    ).poll(observed_at_ms=first)
    rows = (
        _decision_row(1, "long", -100.0, 80.0),
        _decision_row(2, "short", 90.0, 80.0),
        _decision_row(3, None, 40.0, 80.0),
    )
    paths.journal.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    BrentoilOilShockShadowRunner(
        source=_Source([_book(first + 500)], []), paths=paths
    ).poll(observed_at_ms=first + 500)

    status = json.loads(paths.status.read_text())
    assert status["long_decisions_total"] == 1
    assert status["short_decisions_total"] == 1
    assert status["non_action_decisions_total"] == 1
    assert status["latest_trailing_return_bps"] == 40.0
    assert status["latest_shock_threshold_bps"] == 80.0
    assert status["latest_threshold_fraction"] == 0.5
    assert status["maximum_threshold_fraction_total"] == 1.25


def _decision_row(
    index: int, side: str | None, trailing: float, threshold: float
) -> dict[str, object]:
    decision_ms = _ms("2026-08-15T12:40:00Z") + index
    return {
        "event_type": "brentoil_oil_shock_shadow_decision",
        "event_id": f"event-{index}",
        "execution_authority": "none",
        "intents": [],
        "decision": {
            "decision_time_ms": decision_ms,
            "side": side,
            "eligible": side is not None,
            "non_action_reason": None if side is not None else "no_shock_onset",
            "trailing_return_bps": trailing,
            "shock_threshold_bps": threshold,
        },
    }


def _paths(root: Path) -> BrentoilOilShockShadowPaths:
    return BrentoilOilShockShadowPaths(
        book_ledger=root / "books.jsonl",
        candle_ledger=root / "candles.jsonl",
        cursor=root / "cursor.json",
        journal=root / "decisions.jsonl",
        status=root / "status.json",
        websocket_archive=root / "ws",
        rest_mark_archive=root / "marks",
    )


def _book(receipt_ms: int) -> BookSnapshot:
    return _book_times(receipt_ms - 50, receipt_ms)


def _book_times(exchange_ms: int, receipt_ms: int) -> BookSnapshot:
    return BookSnapshot(
        symbol="xyz:BRENTOIL",
        bids=tuple(BookLevel(70.0 - index * 0.01, 10.0) for index in range(20)),
        asks=tuple(BookLevel(70.02 + index * 0.01, 8.0) for index in range(20)),
        ts_recv_ms=float(receipt_ms),
        ts_exchange_ms=float(exchange_ms),
        source="hl_rest_l2",
    )


def _bars(periods: int) -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-15T12:00:00Z", periods=periods, freq="5min")
    closes = [70.0] * periods
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


def _jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1_000)
