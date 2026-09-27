"""Observe-only D1 Donchian 20/10 shadow runner contracts (research lane, Sleeve S1).

Every test injects a synthetic kline fetcher; nothing here touches the network.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
import json
import math
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys
from urllib.parse import parse_qs, urlparse

import d1_shadow_runner as runner
import pandas as pd
import pytest
import requests
from requests.adapters import BaseAdapter

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "d1_shadow_runner.py"
_PLIST = _ROOT / "scripts" / "local.hypervector.research.d1_shadow.plist.example"

HISTORY_START = date(2026, 1, 1)
BACKFILL = date(2026, 5, 1)
BREAKOUT = date(2026, 5, 5)
DAY = timedelta(days=1)


# ----------------------------------------------------------------- fixtures


def _refuse(*args: object, **kwargs: object) -> None:
    raise AssertionError("real network or credential lookup attempted")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs with DNS and outbound connections refused.

    A regression in the transport guard then fails a test instead of reaching
    a real host.
    """
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)


def _flat(days: int = 150, *, volume: float = 1e6) -> pd.DataFrame:
    index = pd.date_range(HISTORY_START, periods=days, freq="D")
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "quote_volume": volume,
        },
        index=index,
    )


def _set(frame: pd.DataFrame, day: date, **values: float) -> None:
    for key, value in values.items():
        frame.loc[pd.Timestamp(day), key] = value


def _breakout(frame: pd.DataFrame, day: date = BREAKOUT) -> pd.DataFrame:
    """Signal bar closes above the prior 20-bar high (101) but below its own high."""
    _set(frame, day, open=100.0, high=106.0, low=100.0, close=105.0)
    _set(frame, day + DAY, open=105.5, high=106.5, low=104.5, close=106.0)
    return frame


def _uptrend_then_channel_break(frame: pd.DataFrame) -> pd.DataFrame:
    """Entry at B+1, rising lows to B+12, then B+13 closes under the 10-bar low."""
    _breakout(frame)
    for k in range(1, 12):
        _set(
            frame,
            BREAKOUT + DAY * (k + 1),
            open=105.0 + k,
            high=106.5 + k,
            low=104.5 + k,
            close=106.0 + k,
        )
    exit_signal = BREAKOUT + DAY * 13
    _set(frame, exit_signal, open=117.0, high=117.5, low=104.5, close=105.0)
    _set(frame, exit_signal + DAY, open=104.8, high=105.5, low=104.0, close=105.0)
    return frame


class FakeFetcher:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames
        self.calls: list[str] = []

    def __call__(self, symbol: str, *, start: date | None, limit: int) -> pd.DataFrame:
        self.calls.append(symbol)
        if symbol not in self.frames:
            raise runner.SymbolUnavailableError(symbol)
        return self.frames[symbol].copy()


def _census(tmp_path: Path, rows: list[tuple]) -> Path:
    """rows: (dex, coin, maxLeverage, volume[, isDelisted])."""
    path = tmp_path / "census_perps.csv"
    pd.DataFrame(
        [
            {
                "dex": row[0],
                "coin": row[1],
                "maxLeverage": row[2],
                "dayNtlVlm": row[3],
                "isDelisted": row[4] if len(row) > 4 else False,
                "listing_status": "delisted" if len(row) > 4 and row[4] else "listed",
            }
            for row in rows
        ]
    ).to_csv(path, index=False)
    return path


def _now(day: date, hour: int = 0, minute: int = 30) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


def _run(
    tmp_path: Path,
    frames: dict[str, pd.DataFrame],
    census_rows: list[tuple],
    *,
    now: datetime,
    backfill: date | None = None,
    config: runner.ShadowConfig | None = None,
) -> tuple[runner.RunReport, list[dict]]:
    ledger = tmp_path / "ledger.jsonl"
    report = runner.run_shadow(
        ledger_path=ledger,
        census_path=_census(tmp_path, census_rows),
        config=config or runner.ShadowConfig(),
        fetcher=FakeFetcher(frames),
        now=now,
        backfill_from=backfill,
    )
    return report, runner.load_ledger(ledger)


def _of(events: list[dict], event_type: str, **match: object) -> list[dict]:
    return [
        event
        for event in events
        if event["event"] == event_type
        and all(event.get(k) == v for k, v in match.items())
    ]


_ONE_COIN = [("main", "AAA", 10, 5e7)]


# ----------------------------------------------------------------- signals / fills


def test_breakout_uses_prior_bars_and_excludes_the_signal_bar(tmp_path: Path) -> None:
    frames = {"AAAUSDT": _breakout(_flat()), "BBBUSDT": _flat()}
    # BBB closes exactly at the prior 20-bar high: not a breakout (strictly above).
    _set(frames["BBBUSDT"], BREAKOUT, open=100.0, high=101.0, low=99.5, close=101.0)
    report, events = _run(
        tmp_path,
        frames,
        [*_ONE_COIN, ("main", "BBB", 10, 4e7)],
        now=_now(BREAKOUT + DAY),
        backfill=BACKFILL,
    )

    assert report.ok, report.error
    signals = _of(events, "signal")
    assert [(s["coin"], s["bar_date"], s["kind"]) for s in signals] == [
        ("AAA", BREAKOUT.isoformat(), "entry_long")
    ]
    signal = signals[0]
    assert signal["channel_level"] == 101.0
    assert signal["close"] == 105.0
    # Including the signal bar's own high (106) in the channel would have vetoed it.
    assert signal["close"] < 106.0
    assert signal["label"] == "trend"
    assert signal["fill_at_open_of"] == (BREAKOUT + DAY).isoformat()


def test_entry_fills_at_the_next_open_with_a_two_atr_stop(tmp_path: Path) -> None:
    _, events = _run(
        tmp_path,
        {"AAAUSDT": _breakout(_flat())},
        _ONE_COIN,
        now=_now(BREAKOUT + DAY),
        backfill=BACKFILL,
    )

    (entry,) = _of(events, "hypothetical_entry")
    # Recorded at 00:30 UTC from today's (in-progress) open; bar B+1 is not complete.
    assert entry["bar_date"] == (BREAKOUT + DAY).isoformat()
    assert entry["entry_px"] == 105.5
    # Wilder ATR(20): flat TR 2, signal-bar TR 6 -> 2 + (6 - 2) / 20 = 2.2.
    assert entry["atr_signal"] == pytest.approx(2.2)
    assert entry["stop_px"] == pytest.approx(105.5 - 4.4)
    stop_fraction = 4.4 / 105.5
    assert entry["stop_fraction"] == pytest.approx(stop_fraction)
    assert entry["taken"] is True
    assert entry["risk_usd_planned"] == pytest.approx(24.0)
    assert entry["notional_usd"] == pytest.approx(24.0 / stop_fraction)
    # maxLeverage 10 -> MMR 0.05; floor(1 / (0.05 + 2.5 * 0.0417)) = 6 -> cap 3.
    assert entry["leverage"] == 3
    assert entry["mmr"] == pytest.approx(0.05)
    assert entry["liq_px"] == pytest.approx(105.5 * (1 - (1 / 3 - 0.05)))
    assert entry["liq_buffer_ok"] is True
    assert entry["mode"] == "backfill"


@pytest.mark.parametrize(
    ("bars", "exit_day", "reason", "exit_px"),
    [
        # Opens below the stop: fills at the open, not at the stop.
        (
            {2: dict(open=100.0, high=101.0, low=99.0, close=100.0)},
            2,
            "gap_stop",
            100.0,
        ),
        (
            {2: dict(open=104.0, high=104.5, low=101.0, close=103.0)},
            2,
            "stop_intrabar",
            101.1,
        ),
        # The entry bar itself trades through the stop.
        (
            {1: dict(open=105.5, high=106.0, low=101.0, close=102.0)},
            1,
            "stop_intrabar",
            101.1,
        ),
    ],
)
def test_stop_checks_intrabar_with_gap_through_at_the_open(
    tmp_path: Path, bars: dict, exit_day: int, reason: str, exit_px: float
) -> None:
    frame = _breakout(_flat())
    for offset, values in bars.items():
        _set(frame, BREAKOUT + DAY * offset, **values)
    _, events = _run(
        tmp_path,
        {"AAAUSDT": frame},
        _ONE_COIN,
        now=_now(BREAKOUT + DAY * 4),
        backfill=BACKFILL,
    )

    (stop,) = _of(events, "hypothetical_stop_hit")
    assert stop["bar_date"] == (BREAKOUT + DAY * exit_day).isoformat()
    assert stop["exit_reason"] == reason
    assert stop["exit_px"] == pytest.approx(exit_px)
    assert stop["days_held"] == exit_day - 1
    assert stop["wick_through_liq"] is False
    assert stop["exit_beyond_liq_px"] is False
    stop_fraction = 4.4 / 105.5
    expected = (exit_px / 105.5 - 1) - 4.32e-4 * (1 + exit_px / 105.5)
    expected -= 0.1095 / 365 * (exit_day - 1)
    assert stop["net_r"] == pytest.approx(expected / stop_fraction)
    assert stop["net_pnl_usd"] == pytest.approx(expected * 24.0 / stop_fraction)
    assert not _of(events, "hypothetical_exit")


def test_channel_exit_fills_at_the_next_open(tmp_path: Path) -> None:
    exit_signal = BREAKOUT + DAY * 13
    _, events = _run(
        tmp_path,
        {"AAAUSDT": _uptrend_then_channel_break(_flat())},
        _ONE_COIN,
        now=_now(exit_signal + DAY * 2),
        backfill=BACKFILL,
    )

    (signal,) = _of(events, "signal", kind="exit_long")
    assert signal["bar_date"] == exit_signal.isoformat()
    # Prior 10 bars (B+3..B+12) lows are 106.5..115.5; the close 105 breaks 106.5.
    assert signal["channel_level"] == pytest.approx(106.5)
    (exit_event,) = _of(events, "hypothetical_exit")
    assert exit_event["bar_date"] == (exit_signal + DAY).isoformat()
    assert exit_event["exit_reason"] == "channel_exit"
    assert exit_event["exit_px"] == 104.8
    assert exit_event["days_held"] == 13
    assert not _of(events, "hypothetical_stop_hit")
    # The close stayed above the 20-bar low: an exit, not a reversal.
    assert not _of(events, "signal", kind="entry_short")


def test_short_breakdown_is_labelled_hedge_with_a_two_x_cap(tmp_path: Path) -> None:
    frame = _flat()
    _set(frame, BREAKOUT, open=100.0, high=100.0, low=94.0, close=95.0)
    _set(frame, BREAKOUT + DAY, open=94.5, high=95.0, low=93.5, close=94.0)
    _, events = _run(
        tmp_path,
        {"AAAUSDT": frame},
        [("main", "AAA", 40, 5e7)],
        now=_now(BREAKOUT + DAY),
        backfill=BACKFILL,
    )

    (signal,) = _of(events, "signal")
    assert signal["kind"] == "entry_short"
    assert signal["label"] == "hedge"
    (entry,) = _of(events, "hypothetical_entry")
    assert entry["side"] == "short"
    assert entry["label"] == "hedge"
    assert entry["stop_px"] == pytest.approx(94.5 + 2 * 2.2)
    # maxLeverage 40 would allow 3x on a long; shorts are capped at 2x.
    assert entry["leverage"] == 2
    assert entry["liq_px"] > entry["stop_px"]


# ----------------------------------------------------------------- portfolio


def test_slot_priority_is_trailing_quote_volume_at_signal_time(tmp_path: Path) -> None:
    coins = [f"COIN{letter}" for letter in "ABCDEFGHIJKL"]
    frames = {
        f"{coin}USDT": _breakout(_flat(volume=(i + 1) * 1e6))
        for i, coin in enumerate(coins)
    }
    # Census volume ranks the other way round: priority must not use it.
    census = [("main", coin, 10, (20 - i) * 1e7) for i, coin in enumerate(coins)]
    _, events = _run(
        tmp_path, frames, census, now=_now(BREAKOUT + DAY), backfill=BACKFILL
    )

    entries = sorted(
        _of(events, "hypothetical_entry"), key=lambda e: e["priority_rank"]
    )
    assert [e["coin"] for e in entries] == list(reversed(coins))
    taken = [e["coin"] for e in entries if e["taken"]]
    skipped = {e["coin"]: e["skip_reason"] for e in entries if not e["taken"]}
    assert taken == list(reversed(coins))[:10]
    assert skipped == {"COINB": "slots_full", "COINA": "slots_full"}
    assert entries[9]["slots_used_after"] == 10
    # Priority is the 30 completed bars through the signal bar (no look-ahead).
    top = entries[0]
    assert top["priority_quote_volume_30d"] == pytest.approx(30 * 12e6)
    assert {s["bar_date"] for s in _of(events, "signal")} == {BREAKOUT.isoformat()}


def test_gross_cap_scales_then_refuses() -> None:
    config = runner.ShadowConfig()
    state = runner.EngineState(last_bar_date="2026-05-05")
    engine = runner.ShadowEngine(config, state)
    atr = 0.3 / 0.7  # stop fraction 0.857% at a 100 fill -> wanted notional 2800
    for i, coin in enumerate(["P1", "P2", "P3", "P4"]):
        state.pending[coin] = runner.PendingOrder(
            coin=coin,
            binance_symbol=f"{coin}USDT",
            signal_date="2026-05-05",
            entry_direction=1,
            atr=atr,
            max_leverage=10.0,
            census_rank=i + 1,
            priority_quote_volume_30d=1e9 - i,
        )
    events = engine.open_step(date(2026, 5, 6), dict.fromkeys(state.pending, 100.0))

    by_coin = {event["coin"]: event for event in events}
    assert by_coin["P1"]["notional_usd"] == pytest.approx(2800.0)
    assert by_coin["P2"]["notional_usd"] == pytest.approx(2800.0)
    # 1.5 x 4800 = 7200 gross: the third fits 1600 of 2800 (>= 25%), scaled.
    assert by_coin["P3"]["taken"] is True
    assert by_coin["P3"]["notional_usd"] == pytest.approx(1600.0)
    assert by_coin["P3"]["scaled_by_gross_cap"] is True
    assert by_coin["P4"]["taken"] is False
    assert by_coin["P4"]["skip_reason"] == "gross_cap"
    # The untaken signal stays a virtual trade and blocks a re-entry on P4.
    assert state.trades["P4"].taken is False
    assert state.pending == {}


@pytest.mark.parametrize(
    ("stop_fraction", "max_leverage", "direction", "expected"),
    [
        (0.10, 10, 1, 3),  # 1 / (0.05 + 0.25) = 3.33
        (0.15, 10, 1, 2),  # 1 / (0.05 + 0.375) = 2.35
        (0.05, 40, -1, 2),  # 7.27, shorts capped at 2
        (0.02, 3, 1, 3),  # 1 / (0.1667 + 0.05) = 4.6 -> 3
        (0.02, 2, 1, 2),  # never above the venue maxLeverage
        (0.60, 10, 1, 1),  # floor below 1 -> 1, buffer flagged
    ],
)
def test_leverage_rule(
    stop_fraction: float, max_leverage: float, direction: int, expected: int
) -> None:
    leverage, mmr, distance, buffer_ok = runner.leverage_for(
        stop_fraction, max_leverage, direction
    )
    assert leverage == expected
    assert mmr == pytest.approx(1 / (2 * max_leverage))
    assert distance == pytest.approx(1 / leverage - mmr)
    assert buffer_ok is (distance >= 2.5 * stop_fraction)
    if stop_fraction == 0.60:
        assert buffer_ok is False


def test_daily_mark_marks_open_positions_with_a_funding_estimate(
    tmp_path: Path,
) -> None:
    _, events = _run(
        tmp_path,
        {"AAAUSDT": _breakout(_flat())},
        _ONE_COIN,
        now=_now(BREAKOUT + DAY * 2),
        backfill=BACKFILL,
    )
    (mark,) = _of(events, "daily_mark", bar_date=(BREAKOUT + DAY).isoformat())
    (position,) = mark["open_positions"]
    notional = 24.0 / (4.4 / 105.5)
    assert position["close"] == 106.0
    assert position["days_held"] == 1
    assert position["gross_unrealized_usd"] == pytest.approx(
        (106 / 105.5 - 1) * notional
    )
    assert position["funding_est_usd"] == pytest.approx(notional * 0.1095 / 365)
    assert mark["totals"]["open_taken"] == 1
    assert mark["totals"]["gross_to_equity"] == pytest.approx(notional / 4800)
    assert mark["state"]["trades"][0]["coin"] == "AAA"
    assert mark["execution_authority"] == "none"


# ----------------------------------------------------------------- ledger contract


def test_rerunning_the_same_day_appends_nothing(tmp_path: Path) -> None:
    frames = {"AAAUSDT": _uptrend_then_channel_break(_flat())}
    ledger = tmp_path / "ledger.jsonl"
    census = _census(tmp_path, _ONE_COIN)

    def run(now: datetime, backfill: date | None = None) -> runner.RunReport:
        return runner.run_shadow(
            ledger_path=ledger,
            census_path=census,
            config=runner.ShadowConfig(),
            fetcher=FakeFetcher(frames),
            now=now,
            backfill_from=backfill,
        )

    first = run(_now(BREAKOUT + DAY), backfill=BACKFILL)
    assert first.appended
    snapshot = ledger.read_bytes()
    for hour in (0, 6, 23):
        again = run(_now(BREAKOUT + DAY, hour=hour, minute=45))
        assert again.ok and again.appended == []
        assert ledger.read_bytes() == snapshot

    # The next UTC day completes B+1 and re-derives B+1's open entry identically.
    later = run(_now(BREAKOUT + DAY * 2))
    kinds = [event["event"] for event in later.appended]
    assert "hypothetical_entry" not in kinds
    assert kinds.count("daily_mark") == 1
    assert run(_now(BREAKOUT + DAY * 2, hour=12)).appended == []
    events = runner.load_ledger(ledger)
    ids = [event["event_id"] for event in events]
    assert len(ids) == len(set(ids))
    assert len(_of(events, "hypothetical_entry")) == 1


def test_cold_start_then_same_day_rerun_is_idempotent(tmp_path: Path) -> None:
    frames = {"AAAUSDT": _breakout(_flat())}
    first, events = _run(tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT + DAY))
    assert first.ok and any("cold start" in note for note in first.notes)
    (mark,) = _of(events, "daily_mark")
    assert mark["bar_date"] == BREAKOUT.isoformat() and mark["cold_start"] is True
    assert len(_of(events, "hypothetical_entry")) == 1
    # The report counts the entry recorded at today's open, and says so.
    assert first.open_taken == 1
    assert first.book_through == f"{(BREAKOUT + DAY).isoformat()} open"
    # A mid-month cold start uses a census captured after the month began.
    (frozen,) = _of(events, "universe_frozen")
    assert frozen["frozen_by"] == "daily" and frozen["point_in_time"] is False
    again, events_again = _run(tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT + DAY))
    assert again.appended == [] and events_again == events


def test_settle_delay_holds_the_day_until_five_past_midnight(tmp_path: Path) -> None:
    frames = {"AAAUSDT": _breakout(_flat())}
    report, events = _run(
        tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT + DAY, minute=3)
    )
    # 00:03 UTC counts as the previous day: the B bar is still treated as open.
    assert report.ok
    assert [m["bar_date"] for m in _of(events, "daily_mark")] == [
        (BREAKOUT - DAY).isoformat()
    ]
    assert not _of(events, "signal")


def test_universe_is_frozen_once_per_month_and_recorded(tmp_path: Path) -> None:
    frames = {"AAAUSDT": _flat()}
    ledger = tmp_path / "ledger.jsonl"
    census = _census(tmp_path, _ONE_COIN)
    kwargs = dict(
        ledger_path=ledger,
        census_path=census,
        config=runner.ShadowConfig(),
        fetcher=FakeFetcher(frames),
    )
    runner.run_shadow(
        now=_now(date(2026, 5, 10)), backfill_from=date(2026, 4, 20), **kwargs
    )
    runner.run_shadow(now=_now(date(2026, 5, 12)), **kwargs)
    frozen = _of(runner.load_ledger(ledger), "universe_frozen")
    assert [(u["month"], u["bar_date"]) for u in frozen] == [
        ("2026-04", "2026-04-01"),
        ("2026-05", "2026-05-01"),
    ]
    assert frozen[1]["members"][0]["history_bars_seen"] == 120
    assert frozen[1]["census"]["volume_basis"] == "24h_snapshot"
    assert frozen[1]["point_in_time"] is False  # frozen during a backfill


def test_backfill_refuses_a_non_empty_ledger(tmp_path: Path) -> None:
    frames = {"AAAUSDT": _flat()}
    _run(tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT), backfill=BACKFILL)
    with pytest.raises(runner.LedgerError, match="empty ledger"):
        _run(tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT), backfill=BACKFILL)


def test_config_change_fails_closed(tmp_path: Path) -> None:
    frames = {"AAAUSDT": _flat()}
    _run(tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT), backfill=BACKFILL)
    with pytest.raises(runner.LedgerError, match="configuration differs"):
        _run(
            tmp_path,
            frames,
            _ONE_COIN,
            now=_now(BREAKOUT + DAY),
            config=runner.ShadowConfig(book_equity=10_000.0),
        )


def test_edited_ledger_line_fails_closed(tmp_path: Path) -> None:
    frames = {"AAAUSDT": _breakout(_flat())}
    _run(tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT + DAY), backfill=BACKFILL)
    ledger = tmp_path / "ledger.jsonl"
    text = ledger.read_text()
    assert '"entry_px":105.5' in text
    ledger.write_text(text.replace('"entry_px":105.5', '"entry_px":99.5'))
    with pytest.raises(runner.LedgerError, match="does not match its digest"):
        runner.load_ledger(ledger)


def test_missing_bar_for_a_held_symbol_stops_after_the_last_full_day(
    tmp_path: Path,
) -> None:
    frames = {"AAAUSDT": _uptrend_then_channel_break(_flat())}
    _run(tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT + DAY * 2), backfill=BACKFILL)
    frames["AAAUSDT"] = frames["AAAUSDT"].drop(pd.Timestamp(BREAKOUT + DAY * 3))
    report, events = _run(tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT + DAY * 5))

    assert not report.ok
    assert "no completed" in report.error
    assert [e["bar_date"] for e in report.appended if e["event"] == "daily_mark"] == [
        (BREAKOUT + DAY * 2).isoformat()
    ]
    assert _of(events, "daily_mark")[-1]["bar_date"] == (BREAKOUT + DAY * 2).isoformat()


def test_a_torn_last_line_fails_closed_with_the_repair_offset(tmp_path: Path) -> None:
    frames = {"AAAUSDT": _breakout(_flat())}
    _run(tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT + DAY), backfill=BACKFILL)
    ledger = tmp_path / "ledger.jsonl"
    good = ledger.read_bytes()
    ledger.write_bytes(good + b'{"schema":"d1_shadow_ledger_v1","event":"sig')

    with pytest.raises(runner.LedgerError, match=f"truncate the file to {len(good)} "):
        runner.load_ledger(ledger)
    os.truncate(ledger, len(good))
    report, events = _run(tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT + DAY * 2))
    assert report.ok, report.error
    assert _of(events, "daily_mark")[-1]["bar_date"] == (BREAKOUT + DAY).isoformat()


def test_a_deleted_or_reordered_line_breaks_the_chain(tmp_path: Path) -> None:
    frames = {"AAAUSDT": _breakout(_flat())}
    _run(tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT + DAY * 3), backfill=BACKFILL)
    ledger = tmp_path / "ledger.jsonl"
    lines = ledger.read_text().splitlines(keepends=True)
    events = runner.load_ledger(ledger)
    for index, event in enumerate(events):
        if event["event"] == "daily_mark":
            assert event["ledger_chain_before"] == runner.ledger_chain(events[:index])
    signal = next(i for i, event in enumerate(events) if event["event"] == "signal")

    for broken in (
        lines[:signal] + lines[signal + 1 :],
        [lines[1], lines[0], *lines[2:]],
    ):
        ledger.write_text("".join(broken))
        with pytest.raises(runner.LedgerError, match="breaks the ledger chain"):
            runner.load_ledger(ledger)


def test_a_stale_census_stops_a_daily_monthly_freeze(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    census = _census(tmp_path, _ONE_COIN)
    kwargs = dict(
        ledger_path=ledger,
        census_path=census,
        config=runner.ShadowConfig(),
        fetcher=FakeFetcher({"AAAUSDT": _flat()}),
    )

    def captured_on(day: date) -> None:
        stamp = datetime(day.year, day.month, day.day, 12, tzinfo=UTC).timestamp()
        os.utime(census, (stamp, stamp))

    runner.run_shadow(
        now=_now(date(2026, 4, 30)), backfill_from=date(2026, 4, 20), **kwargs
    )
    captured_on(date(2026, 3, 1))
    report = runner.run_shadow(now=_now(date(2026, 5, 3)), **kwargs)

    assert (
        not report.ok and "61 days old at the 2026-05 universe freeze" in report.error
    )
    assert report.last_bar == "2026-04-30"  # April completes; May waits
    events = runner.load_ledger(ledger)
    assert _of(events, "daily_mark")[-1]["bar_date"] == "2026-04-30"
    assert [u["month"] for u in _of(events, "universe_frozen")] == ["2026-04"]

    captured_on(date(2026, 4, 28))
    report = runner.run_shadow(now=_now(date(2026, 5, 3)), **kwargs)
    assert report.ok, report.error
    (may,) = _of(runner.load_ledger(ledger), "universe_frozen", month="2026-05")
    assert may["census_age_days_at_month_start"] == 3
    assert may["point_in_time"] is True and may["frozen_by"] == "daily"
    assert may["max_census_age_days"] == 7


def test_the_last_day_waits_for_a_later_bar_or_the_grace(tmp_path: Path) -> None:
    # The response ends at the signal bar: it may be a cached pre-close response.
    frames = {"AAAUSDT": _breakout(_flat()).loc[: pd.Timestamp(BREAKOUT)]}
    report, events = _run(
        tmp_path,
        frames,
        _ONE_COIN,
        now=_now(BREAKOUT + DAY, minute=10),
        backfill=BACKFILL,
    )
    assert report.ok and report.deferred == BREAKOUT.isoformat()
    assert any(note.startswith(f"deferred {BREAKOUT}") for note in report.notes)
    assert _of(events, "daily_mark")[-1]["bar_date"] == (BREAKOUT - DAY).isoformat()
    assert not _of(events, "signal")

    # An hour after the close the bar is final without a later bar.
    report, events = _run(
        tmp_path, frames, _ONE_COIN, now=_now(BREAKOUT + DAY, hour=1, minute=5)
    )
    assert report.ok and report.deferred is None
    assert [s["coin"] for s in _of(events, "signal")] == ["AAA"]
    assert _of(events, "daily_mark")[-1]["bar_date"] == BREAKOUT.isoformat()
    # Today's open is not in the response yet, so no entry is recorded.
    assert not _of(events, "hypothetical_entry")
    assert report.book_through == f"{BREAKOUT.isoformat()} close"


def test_a_channel_exit_beyond_liquidation_is_flagged_not_capped() -> None:
    state = runner.EngineState(last_bar_date="2026-05-05")
    engine = runner.ShadowEngine(runner.ShadowConfig(), state)
    state.pending["AAA"] = runner.PendingOrder(
        coin="AAA",
        binance_symbol="AAAUSDT",
        signal_date="2026-05-05",
        entry_direction=1,
        atr=5.0,
        max_leverage=10.0,
        census_rank=1,
        priority_quote_volume_30d=1e9,
    )
    engine.open_step(date(2026, 5, 6), {"AAA": 100.0})
    trade = state.trades["AAA"]
    assert trade.leverage == 3 and trade.stop_px == pytest.approx(90.0)
    state.pending["AAA"] = runner.PendingOrder(
        coin="AAA",
        binance_symbol="AAAUSDT",
        signal_date="2026-05-09",
        exit_direction=1,
    )
    # Research-engine order: the pending exit fills at the open first.
    (event,) = engine.open_step(date(2026, 5, 10), {"AAA": trade.liq_px * 0.5})
    assert event["event"] == "hypothetical_exit"
    assert event["exit_reason"] == "channel_exit"
    assert event["exit_beyond_liq_px"] is True
    assert event["net_return"] < -1 / trade.leverage


# ----------------------------------------------------------------- universe


def test_universe_freeze_rules(tmp_path: Path) -> None:
    path = _census(
        tmp_path,
        [
            ("main", "BTC", 40, 9e8),
            ("xyz", "xyz:TSLA", 10, 8e8),
            ("main", "DEAD", 10, 7e8, True),
            ("main", "NOPE", 10, 6e8),
            ("main", "YOUNG", 10, 5e8),
            ("main", "OLD", 10, 4e8),
            ("main", "kPEPE", 10, 3e8),
            ("main", "ETH", 25, 2e8),
        ],
    )
    census = runner.load_census(path)
    assert [e.coin for e in census.entries] == [
        "BTC",
        "NOPE",
        "YOUNG",
        "OLD",
        "kPEPE",
        "ETH",
    ]
    month = date(2026, 6, 1)
    history = {
        "BTCUSDT": _flat(170),  # through 2026-06-19; only bars before June count
        "YOUNGUSDT": _flat(170).iloc[-50:],
        "OLDUSDT": _flat(140),  # ends 2026-05-20: stale at the June freeze
        "PEPEUSDT": _flat(170),
        "ETHUSDT": _flat(170),
    }
    payload = runner.freeze_universe(
        month, census, history.get, runner.ShadowConfig(universe_size=2)
    )

    assert [(m["coin"], m["binance_symbol"]) for m in payload["members"]] == [
        ("BTC", "BTCUSDT"),
        ("kPEPE", "PEPEUSDT"),
    ]
    assert payload["members"][0]["history_bars_seen"] == 151
    assert payload["members"][0]["mmr"] == pytest.approx(1 / 80)
    assert {r["coin"]: r["reason"] for r in payload["rejected"]} == {
        "NOPE": "no_binance_usdt_spot_pair",
        "YOUNG": "insufficient_history",
        "OLD": "stale_binance_pair",
    }
    assert payload["short_universe"] is False
    assert payload["history_cutoff"] == "2026-05-31"
    assert payload["census"]["volume_basis"] == "24h_snapshot"


def test_universe_rejects_a_ticker_collision_by_census_price(tmp_path: Path) -> None:
    path = tmp_path / "census.csv"
    pd.DataFrame(
        [
            {
                "dex": "main",
                "coin": "SAME",
                "maxLeverage": 10,
                "dayNtlVlm": 9e8,
                "markPx": 101.0,
            },
            {
                "dex": "main",
                "coin": "OTHER",
                "maxLeverage": 10,
                "dayNtlVlm": 8e8,
                "markPx": 1000.0,
            },
            # 1000x contract: HL quotes 1000 units, Binance one.
            {
                "dex": "main",
                "coin": "kMEME",
                "maxLeverage": 10,
                "dayNtlVlm": 7e8,
                "markPx": 99_000.0,
            },
            {"dex": "main", "coin": "NOMARK", "maxLeverage": 10, "dayNtlVlm": 6e8},
        ]
    ).to_csv(path, index=False)
    captured = datetime(2026, 5, 20, 12, tzinfo=UTC).timestamp()
    os.utime(path, (captured, captured))
    census = runner.load_census(path)
    history = {
        symbol: _flat(170)
        for symbol in ("SAMEUSDT", "OTHERUSDT", "MEMEUSDT", "NOMARKUSDT")
    }
    payload = runner.freeze_universe(
        date(2026, 6, 1), census, history.get, runner.ShadowConfig()
    )

    members = {m["coin"]: m for m in payload["members"]}
    assert set(members) == {"SAME", "kMEME", "NOMARK"}
    assert members["SAME"]["price_ratio_vs_census"] == pytest.approx(100 / 101)
    assert members["kMEME"]["price_ratio_vs_census"] == pytest.approx(100 / 99)
    assert members["NOMARK"]["price_ratio_vs_census"] is None
    (rejected,) = payload["rejected"]
    assert rejected["coin"] == "OTHER" and rejected["reason"] == "price_mismatch"
    assert rejected["price_ratio"] == pytest.approx(0.1)
    assert payload["census_age_days_at_month_start"] == 12


def test_a_pair_with_no_rows_is_rejected_as_stale(tmp_path: Path) -> None:
    # Binance answers an old, delisted pair with an empty page (no DatetimeIndex).
    frames = {
        "AAAUSDT": _breakout(_flat()),
        "GONEUSDT": pd.DataFrame(columns=["open", "high", "low", "close"]),
    }
    report, events = _run(
        tmp_path,
        frames,
        [("main", "GONE", 10, 9e7), *_ONE_COIN],
        now=_now(BREAKOUT + DAY),
        backfill=BACKFILL,
    )
    assert report.ok, report.error
    (frozen,) = _of(events, "universe_frozen")
    assert [m["coin"] for m in frozen["members"]] == ["AAA"]
    assert frozen["rejected"] == [
        {
            "coin": "GONE",
            "binance_symbol": "GONEUSDT",
            "reason": "stale_binance_pair",
            "last_bar": None,
        }
    ]


def test_census_prefers_a_trailing_30d_volume_column(tmp_path: Path) -> None:
    path = tmp_path / "census.csv"
    pd.DataFrame(
        [
            {
                "dex": "main",
                "coin": "AAA",
                "maxLeverage": 10,
                "dayNtlVlm": 9e9,
                "ntlVlm30d": 1e8,
            },
            {
                "dex": "main",
                "coin": "BBB",
                "maxLeverage": 10,
                "dayNtlVlm": 1e6,
                "ntlVlm30d": 5e8,
            },
        ]
    ).to_csv(path, index=False)
    census = runner.load_census(path)
    assert [e.coin for e in census.entries] == ["BBB", "AAA"]
    assert census.meta["volume_basis"] == "trailing_30d"
    with pytest.raises(runner.CensusError):
        runner.load_census(tmp_path / "missing.csv")


# ----------------------------------------------------------------- regime


def test_regime_tag_tracks_the_btc_sma200_switch() -> None:
    index = pd.date_range("2025-01-01", periods=260, freq="D")
    closes = [100.0 + i for i in range(259)] + [50.0]
    frame = pd.DataFrame(
        {
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "quote_volume": 1e6,
        },
        index=index,
    )
    rows = runner.compute_indicators(frame)
    days = sorted(rows)
    up, state = runner.regime_tag(days[-2], {"BTC": rows[days[-2]]}, None)
    switch = up["btc_beta_switch"]
    assert switch["state"] == "long" and switch["switched"] is None
    assert up["context"]["BTC"]["sma50_above_sma200"] is True
    assert up["context"]["ETH"] is None
    down, state = runner.regime_tag(days[-1], {"BTC": rows[days[-1]]}, state)
    assert down["btc_beta_switch"]["state"] == "cash"
    assert down["btc_beta_switch"]["switched"] is True
    assert state == "cash"
    assert down["context"]["BTC"]["sma200"] == pytest.approx(sum(closes[-200:]) / 200)


def test_atr_and_channels_match_the_research_convention() -> None:
    frame = _breakout(_flat())
    rows = runner.compute_indicators(frame)
    row = rows[BREAKOUT]
    assert row.entry_high == 101.0 and row.entry_low == 99.0
    assert row.atr == pytest.approx(2.2)
    assert math.isnan(rows[HISTORY_START].entry_high)
    assert math.isnan(rows[HISTORY_START + DAY * 18].atr)
    assert rows[HISTORY_START + DAY * 19].atr == pytest.approx(2.0)


# ----------------------------------------------------------------- safety


def test_runs_without_any_network_when_a_fetcher_is_injected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(requests.Session, "request", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    ledger = tmp_path / "ledger.jsonl"
    fetcher = FakeFetcher({"AAAUSDT": _breakout(_flat())})
    code = runner.main(
        [
            "--ledger",
            str(ledger),
            "--census",
            str(_census(tmp_path, _ONE_COIN)),
            "--backfill-from",
            BACKFILL.isoformat(),
            "--now-utc",
            _now(BREAKOUT + DAY).isoformat(),
        ],
        fetcher=fetcher,
    )
    assert code == 0
    assert ledger.exists()
    assert set(fetcher.calls) >= {"AAAUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT"}
    out = capsys.readouterr().out
    assert "http_requests_by_host=n/a(injected_fetcher)" in out
    assert "hyperliquid_client=none" in out


def test_dry_run_prints_events_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    code = runner.main(
        [
            "--ledger",
            str(ledger),
            "--census",
            str(_census(tmp_path, _ONE_COIN)),
            "--backfill-from",
            BACKFILL.isoformat(),
            "--now-utc",
            _now(BREAKOUT + DAY).isoformat(),
            "--dry-run",
        ],
        fetcher=FakeFetcher({"AAAUSDT": _breakout(_flat())}),
    )
    assert code == 0
    assert not ledger.exists()
    assert not ledger.with_name("ledger.jsonl.lock").exists()
    lines = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    kinds = {json.loads(line)["event"] for line in lines}
    assert {"universe_frozen", "signal", "hypothetical_entry", "daily_mark"} <= kinds


def test_fail_closed_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("not json\n")
    code = runner.main(
        ["--ledger", str(ledger), "--now-utc", _now(BREAKOUT).isoformat()],
        fetcher=FakeFetcher({}),
    )
    assert code == 2
    assert "FAIL-CLOSED" in capsys.readouterr().err


def test_binance_fetcher_refuses_any_other_host() -> None:
    for url in (
        "https://api.hyperliquid.xyz",
        "http://data-api.binance.vision",
        "https://api.binance.com",
    ):
        with pytest.raises(ValueError, match="refusing"):
            runner.BinanceKlineFetcher(url)


Reply = tuple[int, object, dict[str, str]]


class _Transport(BaseAdapter):
    """Fake network behind the runner's real session and transport guard."""

    def __init__(
        self,
        handler: Callable[[requests.PreparedRequest], Reply],
        *,
        final_url: str | None = None,
    ) -> None:
        super().__init__()
        self.handler = handler
        self.final_url = final_url
        self.requests: list[requests.PreparedRequest] = []
        self.kwargs: list[dict] = []

    def send(self, request: requests.PreparedRequest, **kwargs: object) -> object:
        self.requests.append(request)
        self.kwargs.append(kwargs)
        status, payload, headers = self.handler(request)
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(payload).encode()
        response.headers.update(headers)
        response.url = self.final_url or request.url
        response.request = request
        response.encoding = "utf-8"
        return response

    def close(self) -> None:
        pass


def _replies(*replies: Reply) -> Callable[[requests.PreparedRequest], Reply]:
    queue = list(replies)
    return lambda request: queue.pop(0)


def _kline_handler(
    frames: dict[str, pd.DataFrame],
) -> Callable[[requests.PreparedRequest], Reply]:
    """Serves 1d klines from frames the way Binance does (startTime, limit)."""

    def handle(request: requests.PreparedRequest) -> Reply:
        query = parse_qs(urlparse(request.url).query)
        symbol = query["symbol"][0]
        if symbol not in frames:
            return 400, {"code": -1121, "msg": "Invalid symbol."}, {}
        frame = frames[symbol]
        if "startTime" in query:
            start = pd.Timestamp(int(query["startTime"][0]), unit="ms")
            frame = frame[frame.index >= start]
        rows = [
            [
                int(stamp.timestamp() * 1000),
                str(bar.open),
                str(bar.high),
                str(bar.low),
                str(bar.close),
                "0",
                int(stamp.timestamp() * 1000) + 86_399_999,
                str(bar.quote_volume),
                0,
            ]
            for stamp, bar in zip(
                frame.index, frame.itertuples(index=False), strict=True
            )
        ]
        return 200, rows[: int(query["limit"][0])], {}

    return handle


def _kline(day: date, close: float) -> list:
    ms = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)
    return [ms, "1", "2", "0.5", str(close), "10", ms + 86_399_999, "123.5", 7]


def _hosts(transport: _Transport) -> list[str | None]:
    return [urlparse(request.url).hostname for request in transport.requests]


def test_binance_fetcher_parses_pages_and_maps_invalid_symbols() -> None:
    first = [_kline(date(2023, 1, 1) + DAY * i, 1.0) for i in range(1000)]
    second = [_kline(date(2025, 9, 27) + DAY * i, 2.0) for i in range(3)]
    transport = _Transport(_replies((200, first, {}), (200, second, {})))
    fetcher = runner.BinanceKlineFetcher(transport=transport, sleep=lambda _: None)
    frame = fetcher("BTCUSDT", start=date(2023, 1, 1), limit=1000)

    assert len(frame) == 1003
    assert frame["quote_volume"].iloc[0] == 123.5
    assert frame["close"].iloc[-1] == 2.0
    urls = [urlparse(request.url) for request in transport.requests]
    assert all(
        (url.scheme, url.hostname, url.path)
        == ("https", "data-api.binance.vision", "/api/v3/klines")
        for url in urls
    )
    assert parse_qs(urls[1].query)["startTime"] == [str(first[-1][0] + 86_400_000)]
    assert fetcher.requests_made == 2
    assert fetcher.requests_by_host == {"data-api.binance.vision": 2}

    bad = _Transport(_replies((400, {"code": -1121, "msg": "Invalid symbol."}, {})))
    with pytest.raises(runner.SymbolUnavailableError):
        runner.BinanceKlineFetcher(transport=bad)("NOPEUSDT", start=None, limit=400)
    throttled = _Transport(_replies((429, {}, {"Retry-After": "7"}), (200, second, {})))
    waits: list[float] = []
    fetcher = runner.BinanceKlineFetcher(transport=throttled, sleep=waits.append)
    assert len(fetcher("ETHUSDT", start=None, limit=400)) == 3
    assert waits == [7.0]
    malformed = _Transport(_replies((200, [[1, "not-a-price"]], {})))
    with pytest.raises(runner.DataFetchError, match="malformed klines row"):
        runner.BinanceKlineFetcher(transport=malformed)("X", start=None, limit=400)


def test_fetcher_never_follows_a_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(requests.sessions, "get_netrc_auth", _refuse)
    moved = {"Location": "https://api.hyperliquid.xyz/info"}
    for status in (301, 302, 307, 308):
        transport = _Transport(_replies((status, [], moved)))
        fetcher = runner.BinanceKlineFetcher(transport=transport, sleep=_refuse)
        with pytest.raises(runner.DataFetchError, match="redirect .* refused"):
            fetcher("BTCUSDT", start=None, limit=400)
        # One request, to Binance; the Location host was never requested.
        assert _hosts(transport) == ["data-api.binance.vision"]
        assert fetcher.requests_by_host == {"data-api.binance.vision": 1}
        assert fetcher.refused_by_host == {}


def test_fetcher_ignores_netrc_proxy_and_ca_bundle_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    netrc = tmp_path / "netrc"
    netrc.write_text("machine data-api.binance.vision login user password secret\n")
    netrc.chmod(0o600)
    monkeypatch.setenv("NETRC", str(netrc))
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(tmp_path / "ca.pem"))
    monkeypatch.setattr(requests.sessions, "get_netrc_auth", _refuse)
    transport = _Transport(_replies((200, [_kline(date(2026, 5, 1), 1.0)], {})))
    fetcher = runner.BinanceKlineFetcher(transport=transport)

    assert len(fetcher("BTCUSDT", start=None, limit=400)) == 1
    assert fetcher.session.trust_env is False
    (request,) = transport.requests
    assert "Authorization" not in request.headers
    (sent,) = transport.kwargs
    assert not sent["proxies"]
    assert sent["verify"] is True


def test_transport_guard_refuses_every_other_host_and_method() -> None:
    moved = {"Location": "https://api.hyperliquid.xyz/info"}
    transport = _Transport(_replies((302, [], moved)))
    fetcher = runner.BinanceKlineFetcher(transport=transport)
    session = fetcher.session
    klines = "https://data-api.binance.vision/api/v3/klines"
    # Even a caller that asks the session to follow the redirect cannot leave.
    with pytest.raises(runner.EgressRefusedError):
        session.get(klines, allow_redirects=True)
    for method, url in (
        ("GET", "https://api.hyperliquid.xyz/info"),
        ("POST", "https://api.hyperliquid.xyz/exchange"),
        ("GET", "http://data-api.binance.vision/api/v3/klines"),
        ("POST", klines),
    ):
        with pytest.raises(runner.EgressRefusedError):
            session.request(method, url)
    assert _hosts(transport) == ["data-api.binance.vision"]
    assert fetcher.refused_by_host == {
        "api.hyperliquid.xyz": 3,
        "data-api.binance.vision": 2,
    }
    assert isinstance(session.get_adapter("https://x/"), runner.AllowListTransport)
    assert isinstance(session.get_adapter("http://x/"), runner.AllowListTransport)


def test_fetcher_refuses_a_response_from_another_host() -> None:
    transport = _Transport(
        _replies((200, [], {})), final_url="https://api.hyperliquid.xyz/info"
    )
    fetcher = runner.BinanceKlineFetcher(transport=transport)
    with pytest.raises(runner.EgressRefusedError, match="refusing it"):
        fetcher("BTCUSDT", start=None, limit=400)


def test_main_logs_observed_requests_per_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    transport = _Transport(_kline_handler({"AAAUSDT": _breakout(_flat())}))
    ledger = tmp_path / "ledger.jsonl"
    code = runner.main(
        [
            "--ledger",
            str(ledger),
            "--census",
            str(_census(tmp_path, _ONE_COIN)),
            "--backfill-from",
            BACKFILL.isoformat(),
            "--now-utc",
            _now(BREAKOUT + DAY).isoformat(),
        ],
        fetcher=runner.BinanceKlineFetcher(transport=transport, sleep=_refuse),
    )

    assert code == 0
    out = capsys.readouterr().out
    # AAA, then BTC, ETH and SOL for the regime tag (unknown pairs, one GET each).
    assert "http_requests_by_host=data-api.binance.vision:4 " in out
    assert "refused_by_host" not in out and "hyperliquid_client=none" in out
    assert f"open_taken=1 book_through={(BREAKOUT + DAY).isoformat()}_open" in out
    assert set(_hosts(transport)) == {"data-api.binance.vision"}
    (entry,) = _of(runner.load_ledger(ledger), "hypothetical_entry")
    assert entry["entry_px"] == 105.5 and entry["taken"] is True


def test_unexpected_errors_also_exit_fail_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    def broken(symbol: str, *, start: date | None, limit: int) -> pd.DataFrame:
        raise IndexError("kline row too short")

    ledger = tmp_path / "ledger.jsonl"
    code = runner.main(
        [
            "--ledger",
            str(ledger),
            "--census",
            str(_census(tmp_path, _ONE_COIN)),
            "--now-utc",
            _now(BREAKOUT).isoformat(),
        ],
        fetcher=broken,
    )
    assert code == 2
    assert "FAIL-CLOSED: unexpected IndexError" in capsys.readouterr().err
    assert not ledger.exists()


def test_script_is_observe_only() -> None:
    source = _SCRIPT.read_text()
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    roots = {name.split(".")[0] for name in imported}
    assert roots <= {
        "__future__",
        "argparse",
        "collections",
        "copy",
        "dataclasses",
        "datetime",
        "fcntl",
        "hashlib",
        "io",
        "json",
        "math",
        "os",
        "pathlib",
        "re",
        "sys",
        "time",
        "traceback",
        "typing",
        "urllib",
        "numpy",
        "pandas",
        "requests",
    }, roots
    assert imported.isdisjoint(
        {"subprocess", "importlib", "socket", "http.client", "urllib.request"}
    )
    assert not any(
        token in name
        for name in imported
        for token in ("hyperliquid", "eth_account", "web3", "dotenv", "keyring")
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in {"__import__", "eval", "exec", "compile"}, node.id
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        ):
            # No environment, process or exec access: os is used to fsync only.
            assert node.attr == "fsync", node.attr
    assert "hyperliquid.xyz" not in source
    assert ".env" not in source
    assert "execution_authority: none" in source
    assert runner.ALLOWED_DATA_HOSTS == frozenset({"data-api.binance.vision"})
    # The real client: environment ignored, guard on every scheme, no redirects.
    fetcher = runner.BinanceKlineFetcher()
    assert fetcher.session.trust_env is False
    for url in ("https://api.hyperliquid.xyz/", "http://data-api.binance.vision/"):
        assert isinstance(fetcher.session.get_adapter(url), runner.AllowListTransport)
    assert "allow_redirects=False" in source


def test_plist_example_runs_isolated_after_midnight_utc() -> None:
    plist = plistlib.loads(_PLIST.read_bytes())
    repo = "/Users/gestas/Prototypes/hypervector"
    assert plist["Label"] == "local.hypervector.research.d1_shadow"
    # Nothing from hypervector is imported, so nothing adds src to the path.
    assert "EnvironmentVariables" not in plist
    arguments = plist["ProgramArguments"]
    assert arguments[:4] == [
        f"{repo}/.venv/bin/python",
        "-I",
        "-u",
        f"{repo}/scripts/d1_shadow_runner.py",
    ]
    census = arguments[arguments.index("--census") + 1]
    assert census == f"{repo}/data/research/d1_shadow/census_perps.csv"
    assert runner.DEFAULT_CENSUS == runner.REPO_ROOT / Path(census).relative_to(repo)
    assert "--backfill-from" not in arguments and "--dry-run" not in arguments
    log = f"{repo}/data/runtime/research/d1_shadow.log"
    assert plist["StandardOutPath"] == log and plist["StandardErrorPath"] == log
    # America/New_York local 20:10 = 00:10 UTC (EDT) / 01:10 UTC (EST); the
    # 22:10 run retries a deferred or failed day and is otherwise a no-op.
    assert plist["StartCalendarInterval"] == [
        {"Hour": 20, "Minute": 10},
        {"Hour": 22, "Minute": 10},
    ]
    assert plist["RunAtLoad"] is False
    assert "KeepAlive" not in plist


def test_script_runs_under_isolated_python() -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--max-census-age-days" in result.stdout
