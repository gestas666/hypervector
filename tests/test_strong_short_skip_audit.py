"""The strong-short skip audit replays both live identities and scores each skip."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import cohort_ladder_evidence as ladder
import strong_short_skip_audit as audit

MINUTE_MS = 60_000
HOUR_MS = 3_600_000
T0_MS = 1_788_220_800_000  # 2026-09-01T00:00:00Z, hour aligned
WARMUP_HOURS = 30
BREAKDOWN_MS = T0_MS + WARMUP_HOURS * HOUR_MS
DECISION_MS = BREAKDOWN_MS + HOUR_MS


def _minute_bars(
    symbol: str, start_ms: int, rows: list[tuple[float, float, float, float]]
) -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "timestamp_ms": start_ms + index * MINUTE_MS,
            "open": row[0],
            "high": row[1],
            "low": row[2],
            "close": row[3],
            "volume": 1.0,
        }
        for index, row in enumerate(rows)
    ]


def _market(symbol: str, breakdown_close: float, after: list[float]) -> list[dict]:
    """Thirty flat hours (H 101, L 99, C 100: ATR 2, prior low 99), one breakdown
    hour closing at ``breakdown_close``, then one minute per price in ``after``."""
    flat = [(100.0, 101.0, 99.0, 100.0)] * (WARMUP_HOURS * 60)
    low = breakdown_close - 0.1
    breakdown = [(100.0, 100.0, low, breakdown_close)] + [
        (breakdown_close, breakdown_close + 0.05, low, breakdown_close)
    ] * 59
    path = [(price, price + 0.05, price - 0.05, price) for price in after]
    rows = flat + breakdown + path
    return _minute_bars(symbol, T0_MS, rows)


def _rising(start: float, end: float, minutes: int) -> list[float]:
    return list(np.linspace(start, end, minutes))


@pytest.fixture
def candles(tmp_path: Path) -> Path:
    """SOL breaks down weakly (0.25 ATR) then rallies through the stop; SNDK
    breaks down strongly (1.4 ATR), so both identities enter it."""
    sol = _market("SOL", 98.5, [98.5] * 5 + _rising(98.5, 101.5, 120) + [101.5] * 60)
    sndk = _market("xyz:SNDK", 96.0, [96.0] * 185)
    path = tmp_path / "candles.csv"
    pd.DataFrame(sol + sndk).to_csv(path, index=False)
    return path


def _report(path: Path, **extra: object) -> dict[str, object]:
    return audit.build_report(
        candles_path=path,
        since=pd.Timestamp(T0_MS, unit="ms", tz="UTC").isoformat(),
        symbols=("SOL", "xyz:SNDK"),
        **extra,  # type: ignore[arg-type]
    )


def test_only_the_weak_short_is_a_skip(candles: Path) -> None:
    report = _report(candles)
    skips = report["skips"]
    assert [(row["symbol"], row["decision_time_ms"]) for row in skips] == [
        ("SOL", DECISION_MS)
    ]
    skip = skips[0]
    assert skip["prior_entry_low"] == pytest.approx(99.0)
    assert skip["signal_close"] == pytest.approx(98.5)
    assert 0 < skip["extension_atr"] < audit.STRONG_SHORT_MINIMUM_EXTENSION_ATR
    assert skip["extension_atr"] == pytest.approx(0.5 / skip["atr"])
    assert skip["stop_anchor"] == pytest.approx(98.5 + 2 * skip["atr"])
    check = report["identity_check"]
    assert check == {
        "long_mismatches": 0,
        "exit_mismatches": 0,
        "stop_mismatches": 0,
        "filtered_only_shorts": 0,
        "kept_shorts_below_threshold": 0,
        "skips_at_or_above_threshold": 0,
    }
    assert report["coverage"]["SOL"]["first_ready_decision_utc"] is not None
    # The strong breakdown is entered by both identities, so it is no skip.
    frames = audit.load_candles(candles)
    observed = pd.Timestamp(DECISION_MS + 4 * HOUR_MS, unit="ms", tz="UTC")
    strong = audit.replay_symbol("xyz:SNDK", frames["xyz:SNDK"], observed)
    for evaluations in (strong.baseline, strong.filtered):
        entry = evaluations[DECISION_MS]
        assert (entry.eligible, entry.side) == (True, "short")
    assert audit.short_extension_atr(strong.filtered[DECISION_MS]) > 1.0
    weak = audit.replay_symbol("SOL", frames["SOL"], observed)
    assert weak.baseline[DECISION_MS].side == "short"
    assert weak.filtered[DECISION_MS].eligible is False


def test_a_skip_is_scored_under_the_clamped_stop(candles: Path) -> None:
    skip = _report(candles)["skips"][0]
    # The 2 x ATR anchor is about 400 bps away, so the 250 bps clamp binds.
    assert skip["entry_price"] == pytest.approx(98.5)
    assert skip["stop_bps"] == pytest.approx(250.0)
    assert skip["exit_reason"] == "protective_stop"
    assert skip["exit_price"] == pytest.approx(98.5 * 1.025)
    # SOL is a crypto route: 8.6 bps fees plus 10 bps stop slippage.
    assert skip["net_bps"] == pytest.approx(-250.0 - 8.6 - 10.0)
    assert skip["net_r"] == pytest.approx((-250.0 - 18.6) / 250.0)


def test_until_bounds_decisions_and_costs_are_configurable(candles: Path) -> None:
    before = pd.Timestamp(DECISION_MS - 1, unit="ms", tz="UTC").isoformat()
    assert _report(candles, until=before)["skips"] == []
    cheap = audit.CostModel(crypto_round_trip_bps=0.0, stop_slippage_bps=0.0)
    skip = _report(candles, costs=cheap)["skips"][0]
    assert skip["net_bps"] == pytest.approx(-250.0)


@pytest.fixture
def overlapping(tmp_path: Path) -> Path:
    """Two weak SOL breakdowns two hours apart; the first hypothetical short is
    still open (far from its stop or a channel exit) when the second fires."""
    rows = [(100.0, 101.0, 99.0, 100.0)] * (WARMUP_HOURS * 60)
    # Weak breakdown to 98.5 (prior low 99), then back above the new low.
    rows += [(100.0, 100.0, 98.4, 98.5)] + [(98.5, 98.55, 98.4, 98.5)] * 59
    rows += [(98.5, 98.65, 98.45, 98.6)] * 60
    # A second, fresh weak breakdown below 98.4, then a rally through both stops.
    rows += [(98.6, 98.6, 98.15, 98.2)] + [(98.2, 98.25, 98.15, 98.2)] * 59
    rows += [
        (price, price + 0.05, price - 0.05, price)
        for price in _rising(98.2, 101.5, 120)
    ]
    rows += [(101.5, 101.55, 101.45, 101.5)] * 120
    path = tmp_path / "overlapping.csv"
    pd.DataFrame(_minute_bars("SOL", T0_MS, rows)).to_csv(path, index=False)
    return path


def test_a_skip_while_an_earlier_skip_is_open_is_not_an_independent_trade(
    overlapping: Path,
) -> None:
    since = pd.Timestamp(T0_MS, unit="ms", tz="UTC").isoformat()
    report = audit.build_report(candles_path=overlapping, since=since, symbols=("SOL",))
    first, second = report["skips"]
    assert (first["decision_time_ms"], second["decision_time_ms"]) == (
        DECISION_MS,
        DECISION_MS + 2 * HOUR_MS,
    )
    assert first["status"] == "closed"
    assert first["exit_time_ms"] > second["decision_time_ms"]
    # The router holds one position per symbol: the second is never entered.
    assert second["status"] == "overlaps_prior_skip"
    assert second["overlaps_skip_at_utc"] == first["decision_time_utc"]
    assert "net_r" not in second
    summary, rule = report["summary"], report["falsifier"]
    assert (summary["skips"], summary["independent"], summary["resolved"]) == (2, 1, 1)
    assert summary["overlaps_prior_skip"] == 1
    assert summary["by_symbol"]["SOL"]["overlapping"] == 1
    assert rule["resolved_skips"] == 1
    assert rule["net_r"] == pytest.approx(first["net_r"])
    assert summary["net_r"] == pytest.approx(first["net_r"])
    # A skip before --since still blocks the skips it overlaps after it.
    later = pd.Timestamp(DECISION_MS + HOUR_MS, unit="ms", tz="UTC").isoformat()
    after = audit.build_report(candles_path=overlapping, since=later, symbols=("SOL",))
    assert [row["status"] for row in after["skips"]] == ["overlaps_prior_skip"]
    assert after["falsifier"]["resolved_skips"] == 0
    text = audit.summary_text(report)
    assert "1 overlap a prior skip" in text
    assert f"(skip at {first['decision_time_utc']} still open)" in text


def _evaluation(
    decided: int,
    *,
    side: str | None = None,
    exit_sides: tuple[str, ...] = (),
    anchor: float = 102.0,
    close: float = 100.0,
    prior_low: float = 100.2,
) -> SimpleNamespace:
    """A stand-in for a provider evaluation with the fields the audit reads."""
    return SimpleNamespace(
        decision_time_ms=decided,
        eligible=side is not None,
        side=side,
        exit_sides=frozenset(exit_sides),
        reference_price=close,
        readiness=SimpleNamespace(
            metrics={"stop_price": anchor, "atr": 2.0, "prior_entry_low": prior_low}
        ),
    )


def test_an_overlapping_skip_never_extends_the_block_and_live_holds_exclude() -> None:
    first, second, third = DECISION_MS, DECISION_MS + HOUR_MS, DECISION_MS + 3 * HOUR_MS
    recipe = DECISION_MS + 5 * HOUR_MS
    # Flat at 100; at +2 h one candle trades to 102.2, through the first skip's
    # 200 bps stop (102.0) but short of the second's clamped 250 bps (102.5).
    rows = [(100.0, 100.05, 99.95, 100.0)] * (6 * 60)
    rows[120] = (100.0, 102.2, 99.95, 100.0)
    replay = audit.Replay(
        baseline={
            first: _evaluation(first, side="short"),
            second: _evaluation(second, side="short", anchor=110.0),
            third: _evaluation(third, side="short"),
            recipe: _evaluation(recipe, exit_sides=("short",)),
        },
        filtered={},
        fifteen_minute_bars=0,
    )
    options = {
        "since_ms": DECISION_MS,
        "until_ms": None,
        "fees_bps": 0.0,
        "stop_slippage_bps": 0.0,
    }
    skips = audit.symbol_skips(
        "SOL",
        replay,
        _candles(DECISION_MS, rows),
        **options,  # type: ignore[arg-type]
    )
    assert [row["status"] for row in skips] == [
        "closed",
        "overlaps_prior_skip",
        "closed",
    ]
    assert skips[0]["exit_reason"] == "protective_stop"
    assert skips[0]["exit_time_ms"] == DECISION_MS + 2 * HOUR_MS
    # Had the second been entered it would still be open at +3 h; it was not,
    # so the third skip is independent and runs to its recipe exit.
    assert skips[2]["exit_reason"] == "hourly_price_recipe_exit"
    assert skips[2]["exit_time_ms"] == recipe
    # A live lifecycle holding the symbol excludes the skip; it is not scored.
    held = audit.symbol_skips(
        "SOL",
        replay,
        _candles(DECISION_MS, rows),
        live_holds=[(third - 600_000, float(third + HOUR_MS))],
        **options,  # type: ignore[arg-type]
    )
    assert held[2]["status"] == "live_position_open"
    assert (
        held[2]["live_position"]["entry_time_utc"]
        == pd.Timestamp(third - 600_000, unit="ms", tz="UTC").isoformat()
    )


def test_an_unscored_or_open_skip_blocks_its_symbol_conservatively() -> None:
    assert audit._held_until(DECISION_MS, {"status": "open"}) == float("inf")
    assert audit._held_until(DECISION_MS, {"status": "entry_unavailable"}) == (
        DECISION_MS + audit.MAXIMUM_HOLD_MS
    )
    closed = {"status": "closed", "exit_time_ms": DECISION_MS + HOUR_MS}
    assert audit._held_until(DECISION_MS, closed) == DECISION_MS + HOUR_MS


def test_live_lifecycles_are_read_from_ladder_evidence_reports(
    candles: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "ladder.json"
    lifecycles = [
        # Open across the SOL skip: the skip is excluded.
        {"symbol": "SOL", "status": "open", "entry_ms": DECISION_MS - HOUR_MS},
        {
            "symbol": "xyz:SNDK",
            "status": "closed",
            "entry_ms": T0_MS,
            "exit_ms": T0_MS + HOUR_MS,
        },
        {"symbol": "xyz:TSLA", "status": "closed"},
    ]
    report.write_text(json.dumps({"lifecycles": lifecycles}))
    holds = audit.load_live_holds([report, report])
    assert holds == {
        "SOL": [(DECISION_MS - HOUR_MS, float("inf"))],
        "xyz:SNDK": [(T0_MS, float(T0_MS + HOUR_MS))],
    }
    out = tmp_path / "audit.json"
    since = pd.Timestamp(T0_MS, unit="ms", tz="UTC").isoformat()
    code = audit.main(
        ["--candles", str(candles), "--since", since, "--symbols", "SOL,xyz:SNDK"]
        + ["--ladder-report", str(report), "--out", str(out)]
    )
    assert code == 0
    written = json.loads(out.read_text())
    assert [row["status"] for row in written["skips"]] == ["live_position_open"]
    assert written["skips"][0]["live_position"]["exit_time_utc"] is None
    assert written["falsifier"]["resolved_skips"] == 0
    assert written["overlap"]["live_lifecycles"] == 2
    text = capsys.readouterr().out
    assert "live book: 2 live lifecycle(s) from 1 ladder report(s)" in text
    assert "0 overlap a prior skip, 1 a live position" in text
    not_a_report = tmp_path / "other.json"
    not_a_report.write_text("{}")
    with pytest.raises(ValueError):
        audit.load_live_holds([not_a_report])


def test_the_identity_check_counts_every_kind_of_divergence() -> None:
    at = [DECISION_MS + index * HOUR_MS for index in range(5)]
    replay = audit.Replay(
        baseline={
            at[0]: _evaluation(at[0], side="long"),
            at[1]: _evaluation(at[1]),
            at[2]: _evaluation(at[2], exit_sides=("long",)),
            at[3]: _evaluation(at[3], side="long", anchor=98.0),
            at[4]: _evaluation(at[4], side="short", close=97.0, prior_low=99.0),
        },
        filtered={
            at[0]: _evaluation(at[0]),
            # A kept short the baseline did not take, only 0.1 ATR deep.
            at[1]: _evaluation(at[1], side="short", close=99.0, prior_low=99.2),
            at[2]: _evaluation(at[2], exit_sides=("long", "short")),
            at[3]: _evaluation(at[3], side="long", anchor=97.5),
            # The same strong short with the same anchor: no divergence.
            at[4]: _evaluation(at[4], side="short", close=97.0, prior_low=99.0),
        },
        fifteen_minute_bars=0,
    )
    assert audit.identity_check(replay) == {
        "long_mismatches": 1,
        "filtered_only_shorts": 1,
        "kept_shorts_below_threshold": 1,
        "exit_mismatches": 1,
        "stop_mismatches": 1,
    }


def _candles(
    start_ms: int, rows: list[tuple[float, float, float, float]]
) -> audit.Candles:
    frame = pd.DataFrame(_minute_bars("SOL", start_ms, rows))
    frame["timestamp"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)
    return audit.Candles.from_frame(frame)


def _score(candles: audit.Candles, anchor: float, **extra: object) -> dict[str, object]:
    options: dict[str, object] = {
        "decision_ms": DECISION_MS,
        "anchor": anchor,
        "candles": candles,
        "recipe_exits_ms": (),
        "fees_bps": 0.0,
        "stop_slippage_bps": 0.0,
        **extra,
    }
    return audit.score_short(**options)  # type: ignore[arg-type]


def test_a_gap_through_the_stop_fills_at_the_open() -> None:
    rows = [(100.0, 100.2, 99.8, 100.0), (103.0, 103.5, 102.5, 103.0)]
    result = _score(_candles(DECISION_MS, rows), 102.0, stop_slippage_bps=10.0)
    assert result["stop_bps"] == pytest.approx(200.0)
    assert result["exit_reason"] == "protective_stop"
    assert result["exit_price"] == pytest.approx(103.0)
    assert result["net_bps"] == pytest.approx(-300.0 - 10.0)


def test_the_stop_distance_is_clamped_both_ways() -> None:
    assert audit.clamped_short_stop(100.0, 99.0) == pytest.approx((100.2, 20.0))
    assert audit.clamped_short_stop(100.0, 110.0) == pytest.approx((102.5, 250.0))


def test_recipe_exit_and_maximum_hold_close_at_the_candle_open() -> None:
    rows = [(100.0 - 0.001 * index, 100.1, 99.9, 100.0) for index in range(90)]
    recipe = _score(
        _candles(DECISION_MS, rows),
        102.0,
        recipe_exits_ms=(
            DECISION_MS - HOUR_MS,
            DECISION_MS + HOUR_MS,
        ),
    )
    assert recipe["exit_reason"] == "hourly_price_recipe_exit"
    assert (
        recipe["exit_time_utc"]
        == pd.Timestamp(DECISION_MS + HOUR_MS, unit="ms", tz="UTC").isoformat()
    )
    assert recipe["exit_price"] == pytest.approx(100.0 - 0.06)
    # One candle per hour for 30 hours: the first open at or after 24 h exits.
    hourly = [(100.0, 100.1, 99.9, 100.0)] * 30
    frame = pd.DataFrame(_minute_bars("SOL", DECISION_MS, hourly))
    frame["timestamp_ms"] = DECISION_MS + np.arange(30) * HOUR_MS
    frame["timestamp"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)
    held = _score(audit.Candles.from_frame(frame), 102.0)
    assert held["exit_reason"] == "maximum_hold_seconds"
    assert held["hold_hours"] == pytest.approx(24.0)


def test_the_profit_floor_arms_at_two_r_and_exits_at_half_r() -> None:
    rows = [
        (100.0, 100.1, 99.0, 99.0),
        # The 2R peak (410 bps) is made here; this candle's high cannot use it.
        (99.0, 99.5, 95.9, 96.0),
        # Next candle trades back through the 0.5R floor (100 bps) at 99.0.
        (96.0, 99.5, 95.95, 99.4),
    ]
    result = _score(_candles(DECISION_MS, rows), 102.0)
    assert result["floor_armed"] is True
    assert result["exit_reason"] == "profit_floor"
    assert result["exit_price"] == pytest.approx(99.0)
    assert result["gross_r"] == pytest.approx(0.5)
    assert result["max_favorable_bps"] == pytest.approx(410.0)


def test_an_open_through_the_armed_floor_exits_at_that_open() -> None:
    rows = [
        (100.0, 100.1, 99.0, 99.0),
        # The 2R peak (410 bps) arms the floor at 0.5R (100 bps, price 99.0).
        (99.0, 99.5, 95.9, 96.0),
        # The next candle opens at 99.2, already through the floor: it exits at
        # that open (80 bps), worse than the floor itself.
        (99.2, 99.5, 99.0, 99.3),
    ]
    result = _score(_candles(DECISION_MS, rows), 102.0)
    assert result["floor_armed"] is True
    assert result["exit_reason"] == "profit_floor"
    assert result["exit_price"] == pytest.approx(99.2)
    assert result["gross_bps"] == pytest.approx(80.0)
    assert result["exit_time_ms"] == DECISION_MS + 2 * MINUTE_MS


def test_an_unresolved_or_unfillable_skip_is_reported_as_such() -> None:
    rows = [(100.0, 100.5, 99.5, 100.2)] * 3
    still_open = _score(_candles(DECISION_MS, rows), 102.0)
    assert still_open["status"] == "open"
    assert still_open["mark_price"] == pytest.approx(100.2)
    late = _score(_candles(DECISION_MS + 10 * MINUTE_MS, rows), 102.0)
    assert late == {"status": "entry_unavailable"}


def test_the_falsifier_needs_forty_resolved_skips_net_and_ex_top_three() -> None:
    assert audit.falsifier([1.0] * 39)["status"] == "pending"
    concentrated = audit.falsifier([10.0] * 3 + [-0.5] * 37)
    assert concentrated["net_r"] == pytest.approx(11.5)
    assert concentrated["ex_top3_net_r"] == pytest.approx(-18.5)
    assert concentrated["status"] == "keep_rule"
    assert audit.falsifier([0.1] * 40)["status"] == "reopen_candidate"
    assert audit.falsifier([-0.1] * 40)["status"] == "keep_rule"
    # Nothing is left after the top three: ex-top-3 is unknown, not zero.
    assert audit.falsifier([-1.0, -1.0])["ex_top3_net_r"] is None
    assert audit.falsifier([-1.0] * 4)["ex_top3_net_r"] == pytest.approx(-1.0)


def test_journaled_market_candle_events_load_in_every_format(tmp_path: Path) -> None:
    def event(bars: dict[str, list[dict[str, float]]], timeframe: str = "1m") -> dict:
        return {
            "event_type": "market_candles",
            "payload": json.dumps({"timeframe": timeframe, "bars": bars}),
        }

    bar = {"timestamp_ms": T0_MS, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}
    rows = [
        event({"SOL": [bar], "BTC": [{**bar, "close": 1.2}]}),
        # A later re-emission of the same minute wins; other timeframes are ignored.
        event({"SOL": [{**bar, "close": 1.9}]}),
        event({"SOL": [{**bar, "timestamp_ms": T0_MS + MINUTE_MS}]}, timeframe="5m"),
        {"event_type": "heartbeat", "payload": "{}"},
    ]
    parquet = tmp_path / "events.parquet"
    pd.DataFrame(rows).to_parquet(parquet)
    jsonl = tmp_path / "decisions.jsonl"
    jsonl.write_text(
        "".join(
            json.dumps({**row, "payload": json.loads(str(row["payload"]))}) + "\n"
            for row in rows
        )
        + "{torn row\n"
    )
    for path in (parquet, jsonl):
        loaded = audit.load_candles(path)
        assert sorted(loaded) == ["BTC", "SOL"]
        sol = loaded["SOL"]
        assert len(sol) == 1
        assert sol["close"].tolist() == [1.9]
        assert str(sol["timestamp"].iloc[0]) == "2026-09-01 00:00:00+00:00"
        assert sol["volume"].tolist() == [0.0]


def _ledger_row(observed_ms: int, bars: dict[str, list[dict[str, float]]]) -> str:
    """A journal row shaped like the live writer's, observed time near the head."""
    row = {
        "schema_version": 1,
        "event_type": "market_candles",
        "observed_at_utc": pd.Timestamp(observed_ms, unit="ms", tz="UTC").isoformat(),
        "payload": {"timeframe": "1m", "bars": bars},
    }
    return json.dumps(row) + "\n"


def test_a_jsonl_ledger_is_bisected_to_the_lookback_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = T0_MS + 100 * HOUR_MS

    def bar(ms: int, close: float) -> dict[str, float]:
        return {
            "timestamp_ms": ms,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": close,
        }

    # An early row carries a bar stamped after the start (a planted marker: no
    # real row journals a candle before it closes). Reading from the bisected
    # offset never decodes it; streaming the whole file would.
    lines = [_ledger_row(T0_MS, {"SOL": [bar(start + HOUR_MS, 9.0)]})]
    lines += [
        _ledger_row(
            T0_MS + hour * HOUR_MS,
            {
                "SOL": [bar(T0_MS + hour * HOUR_MS - MINUTE_MS, 1.5)],
                "BTC": [bar(0, 1.0)],
            },
        )
        for hour in range(1, 200)
    ]
    path = tmp_path / "decisions.jsonl"
    path.write_text("".join(lines))
    # A small bisect chunk so the test file is bisected like a multi-GB ledger.
    monkeypatch.setattr(
        audit,
        "seek_offset",
        lambda ledger, target: ladder.seek_offset(ledger, target, chunk_bytes=512),
    )
    loaded = audit.load_candles(path, start_ms=start, symbols=("SOL",))
    assert sorted(loaded) == ["SOL"]
    sol = loaded["SOL"]
    assert sol["timestamp"].iloc[0] == pd.Timestamp(
        start + HOUR_MS - MINUTE_MS, unit="ms", tz="UTC"
    )
    assert 9.0 not in sol["close"].tolist()
    assert len(sol) == 99
    # Without a start the whole file is read, the planted marker included.
    full = audit.load_candles(path, symbols=("SOL",))
    assert 9.0 in full["SOL"]["close"].tolist()


def test_the_lookback_trims_old_candles_in_every_format(candles: Path) -> None:
    since = pd.Timestamp(DECISION_MS, unit="ms", tz="UTC").isoformat()
    # Ten hours of lookback leave no warm-up before the weak breakdown.
    short = audit.build_report(
        candles_path=candles, since=since, symbols=("SOL",), lookback_hours=10
    )
    assert short["skips"] == []
    assert (
        short["selection"]["candles_from_utc"]
        == pd.Timestamp(DECISION_MS - 10 * HOUR_MS, unit="ms", tz="UTC").isoformat()
    )
    first = short["coverage"]["SOL"]["first_one_minute_utc"]
    assert first == short["selection"]["candles_from_utc"]
    full = audit.build_report(candles_path=candles, since=since, symbols=("SOL",))
    assert [row["decision_time_ms"] for row in full["skips"]] == [DECISION_MS]
    with pytest.raises(ValueError):
        audit.build_report(
            candles_path=candles, since=since, symbols=("SOL",), lookback_hours=-1
        )


def test_candle_gaps_are_reported_in_the_coverage() -> None:
    stamps = [0, 1, 2, 5, 6, 16]
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [T0_MS + m * MINUTE_MS for m in stamps], unit="ms", utc=True
            )
        }
    )
    assert audit._gaps(frame) == {
        "gaps": 2,
        "missing_one_minute_bars": 2 + 9,
        "largest_gap_minutes": 9,
    }
    assert audit._gaps(frame.iloc[:3]) == {
        "gaps": 0,
        "missing_one_minute_bars": 0,
        "largest_gap_minutes": 0,
    }


def test_main_writes_json_and_prints_the_falsifier_line(
    candles: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out" / "audit.json"
    code = audit.main(
        [
            "--candles",
            str(candles),
            "--since",
            pd.Timestamp(T0_MS, unit="ms", tz="UTC").isoformat(),
            "--symbols",
            "SOL,xyz:SNDK",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    report = json.loads(out.read_text())
    assert report["execution_authority"] == "none"
    assert report["falsifier"]["resolved_skips"] == 1
    assert report["falsifier"]["status"] == "pending"
    text = capsys.readouterr().out
    assert (
        "skipped shorts: 1 (1 independent: 1 resolved, 0 open; 0 overlap a prior "
        "skip, 0 a live position)" in text
    )
    assert "live book: not checked (pass --ladder-report)" in text
    assert "falsifier (pre-registered): after >= 40 independent skips" in text
    # Nothing is left after the top three, so ex-top-3 is not a number yet.
    assert "now 1/40, net -1.07R, ex-top-3 n/a: pending" in text


def test_the_audit_imports_only_signal_and_exit_policy_modules() -> None:
    source = Path(audit.__file__).read_text()
    project: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("hypervector"):
                project.add(node.module)
        elif isinstance(node, ast.Import):
            assert not any(alias.name.startswith("hypervector") for alias in node.names)
    assert project == {
        "hypervector.live.cohort_adaptive_exit_policy",
        "hypervector.live.hourly_price_provider",
        "hypervector.live.multi_asset_market_bars",
        "hypervector.live.multi_asset_signal_source",
    }
    # Importing it never loads the venue SDK.
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, strong_short_skip_audit; "
            "print(any(name.split('.')[0] == 'hyperliquid' for name in sys.modules))",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(audit.__file__).parent,
    )
    assert probe.stdout.strip() == "False"
