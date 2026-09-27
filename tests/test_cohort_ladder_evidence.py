"""The read-only size-ladder evidence tool reconstructs Donchian lifecycles exactly."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

import cohort_ladder_evidence as ladder

PROFILE = "p_v94"
RUN = "run-1"
OTHER_RUN = "run-other"
DONCHIAN = "hourly_donchian_20_10_atr20_bidirectional_v1"
HOUR_MS = 3_600_000
MINUTE_MS = 60_000
T0 = 1_789_999_200_000
SINCE = datetime.fromtimestamp(T0 / 1000 - 60, tz=UTC).isoformat()


class _Ledger:
    """Compact JSONL rows shaped exactly like the live journal writer's."""

    def __init__(self, path: Path, profile_id: str) -> None:
        self.path = path
        self.profile_id = profile_id
        self.rows: list[dict[str, object]] = []

    def add(
        self,
        event_type: str,
        observed_ms: int,
        payload: Mapping[str, object],
        *,
        run_id: str = RUN,
    ) -> None:
        self.rows.append(
            {
                "schema_version": 1,
                "sequence": len(self.rows) + 1,
                "event_type": event_type,
                "observed_at_utc": _iso(observed_ms),
                "execution_mode": "live",
                "profile_id": self.profile_id,
                "run_id": run_id,
                "payload": dict(payload),
            }
        )

    def write(self) -> None:
        self.rows.sort(key=lambda row: str(row["observed_at_utc"]))
        self.path.write_text(
            "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in self.rows)
        )


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def _plan(**extra: object) -> dict[str, object]:
    return {
        "strategy_id": DONCHIAN,
        "stop_policy": "structural_clamped_bps",
        "minimum_stop_bps": 20.0,
        "maximum_stop_bps": 250.0,
        "maximum_hold_seconds": 86_400,
        "maximum_hold_policy": "fixed",
        **extra,
    }


def _book(ledger: _Ledger, ms: int, *, bid: float, ask: float) -> None:
    ledger.add(
        "book_observation",
        ms,
        {
            "source": "hyperliquid_mainnet_l2_rest",
            "exchange_ts_ms": ms,
            "recv_ts_ms": ms + 5,
            "mid_px": (bid + ask) / 2,
            "bids": [{"price": bid, "size": 1.0}],
            "asks": [{"price": ask, "size": 1.0}],
        },
        run_id="any-run",
    )


def _lifecycle(
    ledger: _Ledger,
    *,
    symbol: str,
    side: str,
    decision_ms: int,
    entry_oid: int,
    entry_price: float,
    size: float,
    stop: float,
    exit_oid: int,
    exit_ms: int,
    exit_price: float,
    reason: str,
    run_id: str = RUN,
    funding: Sequence[tuple[int, float]] = (),
    timer: bool = False,
    submission_age_ms: int | None = None,
    sizing: Mapping[str, object] | None = None,
    stop_raised: bool = False,
) -> None:
    sign = 1.0 if side == "long" else -1.0
    stop_oid = entry_oid + 1000
    ledger.add(
        "regime_decision",
        decision_ms + 5_000,
        {
            "strategy_id": DONCHIAN,
            "symbol": symbol,
            "side": side,
            "decision_time_ms": decision_ms,
            "reference_price": entry_price,
            "routing_action": "enter",
            "execution_plan": _plan(stop_anchor=stop),
        },
        run_id=run_id,
    )
    if sizing is not None:
        ledger.add("entry_stop_risk_sizing", decision_ms + 5_500, sizing, run_id=run_id)
    acknowledgement: dict[str, object] = {
        "operation": "entry",
        "accepted": True,
        "oid": entry_oid,
        "status": "filled",
    }
    if submission_age_ms is not None:
        acknowledgement.update(
            decision_time_ms=decision_ms,
            submission_age_ms=submission_age_ms,
            submission_boundary="sdk_dispatch",
            submission_limit_ms=30_000,
            submission_observed_at_ms=decision_ms + submission_age_ms,
        )
    ledger.add(
        "order_acknowledgement", decision_ms + 6_000, acknowledgement, run_id=run_id
    )
    ledger.add(
        "order_intent",
        decision_ms + 7_000,
        {"operation": "protective_stop", "trigger_price": stop},
        run_id=run_id,
    )
    ledger.add(
        "stop_order",
        decision_ms + 8_000,
        {"operation": "protective_stop", "accepted": True, "oid": stop_oid},
        run_id=run_id,
    )
    ledger.add(
        "fill",
        decision_ms + 9_000,
        {
            "oid": entry_oid,
            "trade_id": entry_oid * 10,
            "venue_timestamp_ms": decision_ms + 6_500,
            "price": entry_price,
            "size": size,
            "direction": f"Open {side.title()}",
            "closed_pnl_usd": 0.0,
            "fee_usd": 0.1,
        },
        run_id=run_id,
    )
    ledger.add(
        "state_transition",
        decision_ms + 9_500,
        {
            "state": "OPEN",
            "entry_oid": entry_oid,
            "stop_oid": stop_oid,
            "opened_at_ms": decision_ms,
            "execution_plan": _plan(stop_anchor=stop),
        },
        run_id=run_id,
    )
    for venue_ms, delta in funding:
        ledger.add(
            "funding",
            venue_ms + 1_000,
            {"venue_timestamp_ms": venue_ms, "usdc_delta": delta},
            run_id=run_id,
        )
    if stop_raised:
        ledger.add(
            "stop_order",
            decision_ms + 10_000,
            {
                "operation": "protective_stop_raise",
                "accepted": True,
                "oid": stop_oid + 1,
                "status": "resting",
            },
            run_id=run_id,
        )
    if timer:
        ledger.add(
            "close",
            exit_ms - 3_000,
            {"reason": reason, "intent": True, "stop_oid": stop_oid},
            run_id=run_id,
        )
        ledger.add(
            "close",
            exit_ms - 1_000,
            {"operation": "reduce_only_close", "accepted": True, "oid": exit_oid},
            run_id=run_id,
        )
    ledger.add(
        "close",
        exit_ms,
        {"reason": reason, "oid": exit_oid, "verified_flat": True},
        run_id=run_id,
    )
    # The live journal records the exit fill after the verified-flat close event.
    ledger.add(
        "fill",
        exit_ms + 500,
        {
            "oid": exit_oid,
            "trade_id": exit_oid * 10,
            "venue_timestamp_ms": exit_ms - 500,
            "price": exit_price,
            "size": size,
            "direction": f"Close {side.title()}",
            "closed_pnl_usd": sign * (exit_price - entry_price) * size,
            "fee_usd": 0.1,
        },
        run_id=run_id,
    )


def _routing(
    cohort: _Ledger,
    *,
    symbol: str,
    decision_ms: int,
    side: str | None,
    close: float,
    atr: float,
    prior_low: float,
    prior_high: float,
    exit_sides: Sequence[str] = (),
) -> None:
    cohort.add(
        "intent_routing",
        decision_ms + 4_000,
        {
            "evaluations": [
                {
                    "strategy_id": DONCHIAN,
                    "symbol": symbol,
                    "decision_time_ms": decision_ms,
                    "reference_price": close,
                    "eligible": side is not None,
                    "side": side,
                    "exit_sides": list(exit_sides),
                    "readiness": {
                        "metrics": {
                            "atr": atr,
                            "prior_entry_low": prior_low,
                            "prior_entry_high": prior_high,
                        }
                    },
                }
            ],
            "actions": [],
        },
    )


@pytest.fixture
def ledgers(tmp_path: Path) -> Path:
    """Three closed Donchian lifecycles plus noise from another run."""
    cohort = _Ledger(tmp_path / "decisions.jsonl", PROFILE)
    sndk = _Ledger(tmp_path / "xyz:sndk.jsonl", f"{PROFILE}_xyz:sndk")
    sol = _Ledger(tmp_path / "sol.jsonl", f"{PROFILE}_sol")
    tsla = _Ledger(tmp_path / "xyz:tsla.jsonl", f"{PROFILE}_xyz:tsla")
    brent = _Ledger(tmp_path / "xyz:brentoil.jsonl", f"{PROFILE}_xyz:brentoil")

    # A: SNDK short, weak breakout (0.5 ATR), stopped at its own 200 bps stop.
    _routing(
        cohort,
        symbol="xyz:SNDK",
        decision_ms=T0,
        side="short",
        close=100.0,
        atr=1.0,
        prior_low=100.5,
        prior_high=110.0,
    )
    _lifecycle(
        sndk,
        symbol="xyz:SNDK",
        side="short",
        decision_ms=T0,
        entry_oid=11,
        entry_price=100.0,
        size=10.0,
        stop=102.0,
        exit_oid=12,
        exit_ms=T0 + 2 * HOUR_MS,
        exit_price=102.0,
        reason="protective_stop",
        funding=[(T0 + HOUR_MS, 0.05)],
    )
    exit_a = T0 + 2 * HOUR_MS
    _book(sndk, exit_a + 240 * MINUTE_MS + 30_000, bid=100.9, ask=101.1)
    _book(sndk, exit_a + 1440 * MINUTE_MS + 30_000, bid=103.9, ask=104.1)

    # B: SNDK long, strong breakout, 24h timer exit with the v2 floor armed.
    t1 = T0 + 4 * HOUR_MS
    _routing(
        cohort,
        symbol="xyz:SNDK",
        decision_ms=t1,
        side="long",
        close=100.0,
        atr=1.0,
        prior_low=90.0,
        prior_high=98.0,
    )
    _lifecycle(
        sndk,
        symbol="xyz:SNDK",
        side="long",
        decision_ms=t1,
        entry_oid=21,
        entry_price=100.0,
        size=10.0,
        stop=99.0,
        exit_oid=22,
        exit_ms=t1 + 24 * HOUR_MS + 16_000,
        exit_price=103.0,
        reason="maximum_hold_seconds",
        timer=True,
    )
    cohort.add(
        "adaptive_exit_observation",
        t1 + 20 * HOUR_MS,
        {
            "lifecycle_id": f"xyz:SNDK:21:{t1}",
            "symbol": "xyz:SNDK",
            "entry_oid": 21,
            "opened_at_ms": t1,
            "strategy_id": DONCHIAN,
            "risk_bps": 100.0,
            "pnl_bps": 250.0,
            "state": {
                "peak_bps": 260.0,
                "armed": True,
                "floor_armed": True,
                "floor_bps": 50.0,
                "exit_reason": None,
            },
        },
    )
    exit_b = t1 + 24 * HOUR_MS + 16_000
    _book(sndk, exit_b + HOUR_MS, bid=104.0, ask=104.2)
    _book(sndk, exit_b + 3 * HOUR_MS, bid=100.4, ask=100.6)

    # C: SOL long held 50h through an outage; the 24h cap mark is observed.
    t2 = T0 + 2 * 24 * HOUR_MS
    _routing(
        cohort,
        symbol="SOL",
        decision_ms=t2,
        side="long",
        close=100.0,
        atr=2.0,
        prior_low=80.0,
        prior_high=97.0,
    )
    _lifecycle(
        sol,
        symbol="SOL",
        side="long",
        decision_ms=t2,
        entry_oid=31,
        entry_price=100.0,
        size=5.0,
        stop=98.0,
        exit_oid=32,
        exit_ms=t2 + 50 * HOUR_MS,
        exit_price=97.0,
        reason="maximum_hold_seconds",
        timer=True,
    )
    _book(sol, t2 - HOUR_MS, bid=99.9, ask=100.1)
    _book(sol, t2 + 24 * HOUR_MS + 100_000, bid=105.0, ask=105.2)
    _book(sol, t2 + 60 * HOUR_MS, bid=95.9, ask=96.1)

    # Noise: an identical lifecycle journaled by a different run is excluded.
    _lifecycle(
        tsla,
        symbol="xyz:TSLA",
        side="short",
        decision_ms=T0 + HOUR_MS,
        entry_oid=41,
        entry_price=300.0,
        size=1.0,
        stop=303.0,
        exit_oid=42,
        exit_ms=T0 + 2 * HOUR_MS,
        exit_price=303.0,
        reason="protective_stop",
        run_id=OTHER_RUN,
    )
    for ms, value in ((T0, 5_000.0), (T0 + 24 * HOUR_MS, 5_200.0), (t2, 4_500.0)):
        cohort.add("cohort_snapshot", ms, {"account_value_usd": value, "assets": []})
    cohort.add("cohort_snapshot", t2, {"account_value_usd": 1.0}, run_id=OTHER_RUN)
    for ledger in (cohort, sndk, sol, tsla, brent):
        ledger.write()
    return tmp_path


def _report(ledger_dir: Path, **overrides: object) -> dict[str, object]:
    options = {
        "ledger_dir": ledger_dir,
        "profile_id": None,
        "run_ids": (RUN,),
        "since": SINCE,
        "until": None,
        **overrides,
    }
    return ladder.build_report(**options)  # type: ignore[arg-type]


def _by_oid(report: Mapping[str, object]) -> dict[int, Mapping[str, object]]:
    rows = report["lifecycles"]
    assert isinstance(rows, list)
    return {int(row["entry_oid"]): row for row in rows}


def test_lifecycles_use_their_own_stop_distance_and_all_costs(ledgers: Path) -> None:
    report = _report(ledgers)
    rows = _by_oid(report)
    assert set(rows) == {11, 21, 31}
    short = rows[11]
    assert short["symbol"] == "xyz:SNDK"
    assert short["side"] == "short"
    assert short["exit_reason"] == "protective_stop"
    assert short["status"] == "closed"
    assert short["stop_bps"] == pytest.approx(200.0)
    assert short["risk_usd"] == pytest.approx(20.0)
    # -$20 venue PnL, $0.20 fees and +$0.05 funding.
    assert short["net_usd"] == pytest.approx(-20.15)
    assert short["r_multiple"] == pytest.approx(-20.15 / 20.0)
    assert short["hold_seconds"] == pytest.approx(2 * 3600 - 0.5)


def test_selection_by_profile_matches_the_run_selection(ledgers: Path) -> None:
    by_run = _report(ledgers)
    by_profile = _report(ledgers, profile_id=PROFILE, run_ids=())
    assert set(_by_oid(by_profile)) == {11, 21, 31, 41}
    assert set(_by_oid(by_run)) == {11, 21, 31}
    assert _report(ledgers, profile_id="other_profile", run_ids=())["lifecycles"] == []


def test_outage_hold_is_flagged_and_capped_at_the_configured_hold(
    ledgers: Path,
) -> None:
    rows = _by_oid(_report(ledgers))
    outage = rows[31]
    assert outage["outage_hold"] is True
    assert outage["net_usd"] == pytest.approx(-15.2)
    capped = outage["capped"]
    assert capped["status"] == "capped"
    # Exits a long at the observed bid 100 s after opened + 24 h.
    assert capped["exit_price"] == pytest.approx(105.0)
    assert capped["net_usd"] == pytest.approx(25.0 - 0.1 - 0.1 * 105.0 / 97.0)
    assert capped["r_multiple"] == pytest.approx(capped["net_usd"] / 10.0)
    normal = rows[21]
    assert normal["outage_hold"] is False
    assert normal["capped"]["net_usd"] == pytest.approx(normal["net_usd"])


def test_outage_hold_without_a_cap_mark_is_indeterminate(ledgers: Path) -> None:
    rows = _by_oid(_report(ledgers, mark_tolerance_seconds=60))
    assert rows[31]["capped"]["status"] == "cap_mark_unavailable"
    assert rows[31]["capped"]["net_usd"] is None


def test_supplemental_marks_fill_only_the_gap_the_book_left(
    ledgers: Path, tmp_path: Path
) -> None:
    cap_ms = T0 + 2 * 24 * HOUR_MS + 24 * HOUR_MS
    marks = tmp_path / "marks.csv"
    marks.write_text(f"symbol,time,price\nSOL,{_iso(cap_ms + 30_000)},101.0\n")
    report = _report(ledgers, mark_tolerance_seconds=60, supplemental_marks=marks)
    capped = _by_oid(report)[31]["capped"]
    assert capped["status"] == "capped"
    assert capped["mark_source"] == "supplemental"
    assert capped["exit_price"] == pytest.approx(101.0)
    # Book observations still take precedence wherever they exist.
    within = _by_oid(_report(ledgers, supplemental_marks=marks))[31]["capped"]
    assert within["mark_source"] == "book"
    assert within["exit_price"] == pytest.approx(105.0)


def test_post_exit_marks_are_signed_in_the_trade_direction(ledgers: Path) -> None:
    rows = _by_oid(_report(ledgers))
    marks = rows[11]["post_exit_marks"]
    assert marks["240"]["mid"] == pytest.approx(101.0)
    # A short that exited at 102 would have gained 98 bps by the 240 min mark.
    assert marks["240"]["move_bps"] == pytest.approx((1 - 101.0 / 102.0) * 10_000)
    assert marks["240"]["move_r"] == pytest.approx(marks["240"]["move_bps"] / 200.0)
    assert marks["1440"]["move_bps"] == pytest.approx((1 - 104.0 / 102.0) * 10_000)


def test_breakout_extension_is_reported_for_every_donchian_short(
    ledgers: Path,
) -> None:
    report = _report(ledgers)
    shorts = report["donchian_short_extension"]
    assert [row["entry_oid"] for row in shorts] == [11]
    assert shorts[0]["extension_atr"] == pytest.approx(0.5)
    assert shorts[0]["weak"] is True
    longs = {row["entry_oid"]: row for row in report["donchian_entry_extension"]}
    assert longs[21]["extension_atr"] == pytest.approx(2.0)
    assert longs[21]["weak"] is None


def test_floor_armed_timer_counterfactual_follows_the_book_path(
    ledgers: Path,
) -> None:
    report = _report(ledgers)
    rows = report["timer_counterfactual"]
    assert [row["entry_oid"] for row in rows] == [21]
    row = rows[0]
    assert row["floor_armed"] is True
    assert row["floor_bps"] == pytest.approx(50.0)
    assert row["timer_exit_price"] == pytest.approx(103.0)
    assert row["counterfactual_exit_reason"] == "profit_floor"
    assert row["counterfactual_exit_price"] == pytest.approx(100.4)
    assert row["max_favorable_bps"] == pytest.approx(400.0)
    expected = 4.0 - 0.1 - 0.1 * 100.4 / 103.0
    assert row["counterfactual_net_usd"] == pytest.approx(expected)
    assert row["delta_vs_timer_usd"] == pytest.approx(expected - (30.0 - 0.2))


def test_recipe_exit_ends_the_counterfactual_before_the_floor(
    ledgers: Path,
) -> None:
    cohort = ledgers / "decisions.jsonl"
    t1 = T0 + 4 * HOUR_MS
    extra = _Ledger(cohort, PROFILE)
    _routing(
        extra,
        symbol="xyz:SNDK",
        decision_ms=t1 + 25 * HOUR_MS,
        side=None,
        close=104.1,
        atr=1.0,
        prior_low=90.0,
        prior_high=110.0,
        exit_sides=("long",),
    )
    with cohort.open("a") as handle:
        handle.write(json.dumps(extra.rows[0], separators=(",", ":")) + "\n")
    row = _report(ledgers)["timer_counterfactual"][0]
    assert row["counterfactual_exit_reason"] == "hourly_price_recipe_exit"
    # The first executable bid at or after the 25 h channel-exit decision.
    assert row["counterfactual_exit_price"] == pytest.approx(104.0)


def test_summary_and_equity_drawdown_from_the_rung_high(ledgers: Path) -> None:
    report = _report(ledgers)
    summary = report["summary"]
    assert summary["closed"] == 3
    nets = sorted(row["net_usd"] for row in report["lifecycles"])
    assert summary["net_usd"] == pytest.approx(sum(nets))
    equity = report["equity"]
    assert equity["high_water_usd"] == pytest.approx(5_200.0)
    assert equity["last_usd"] == pytest.approx(4_500.0)
    assert equity["drawdown_from_high"] == pytest.approx(4_500.0 / 5_200.0 - 1)
    step_down = report["ladder"]["step_down"]
    assert step_down["drawdown_triggered"] is True
    assert step_down["triggered"] is True
    assert report["ladder"]["advance"]["status"] == "pending"
    assert report["ladder"]["advance"]["closed"] == 3


def test_time_scaled_buy_and_hold_uses_observed_marks(ledgers: Path) -> None:
    report = _report(ledgers)
    sol = report["buy_and_hold"]["SOL"]
    assert sol["first_mid"] == pytest.approx(100.0)
    assert sol["last_mid"] == pytest.approx(96.0)
    assert sol["window_bps"] == pytest.approx(-400.0)
    window_ms = (T0 + 2 * 24 * HOUR_MS + 60 * HOUR_MS) - (
        T0 + 2 * 24 * HOUR_MS - HOUR_MS
    )
    fraction = (50 * HOUR_MS - 6_500 - 500) / window_ms
    assert sol["time_in_market_fraction"] == pytest.approx(fraction, rel=1e-6)
    assert sol["time_scaled_bps"] == pytest.approx(-400.0 * fraction, rel=1e-6)
    assert sol["time_scaled_usd"] == pytest.approx(-0.04 * fraction * 500.0, rel=1e-6)


def _trade(net: float, risk: float = 10.0) -> dict[str, object]:
    return {
        "status": "closed",
        "net_usd": net,
        "r_multiple": net / risk,
        "capped": {"status": "not_capped", "net_usd": net, "r_multiple": net / risk},
    }


def test_advance_requires_positive_mean_r_and_ex_top_three_net() -> None:
    passing = [_trade(4.0)] * 20 + [_trade(-5.0)] * 10
    result = ladder.evaluate_ladder(passing, [(1, 5_000.0), (2, 5_050.0)])
    assert result["advance"]["status"] == "advance"
    assert result["advance"]["ex_top3_net_usd"] == pytest.approx(80.0 - 50.0 - 12.0)
    concentrated = [_trade(40.0)] * 3 + [_trade(-1.0)] * 27
    result = ladder.evaluate_ladder(concentrated, [])
    assert result["advance"]["status"] == "not_met"
    assert result["advance"]["mean_r"] > 0
    assert result["advance"]["ex_top3_net_usd"] < 0
    # Only the first 30 closes since the rung start are evaluated.
    later = passing + [_trade(-100.0)] * 5
    assert ladder.evaluate_ladder(later, [])["advance"]["status"] == "advance"


def test_advance_is_indeterminate_when_a_capped_mark_is_missing() -> None:
    rows = [_trade(4.0)] * 30
    rows[5] = {
        **rows[5],
        "capped": {"status": "cap_mark_unavailable", "net_usd": None},
    }
    assert ladder.evaluate_ladder(rows, [])["advance"]["status"] == "indeterminate"


def test_step_down_on_any_fifty_trade_window_with_negative_mean_r() -> None:
    healthy = [_trade(1.0)] * 60
    assert ladder.evaluate_ladder(healthy, [])["step_down"]["triggered"] is False
    losing = [_trade(5.0)] * 10 + [_trade(-2.0)] * 50 + [_trade(20.0)] * 30
    step = ladder.evaluate_ladder(losing, [])["step_down"]
    assert step["window_triggered"] is True
    assert step["worst_window_mean_r"] < 0
    assert step["triggered"] is True
    drawdown = ladder.evaluate_ladder([], [(1, 5_000.0), (2, 4_401.0)])["step_down"]
    assert drawdown["drawdown_triggered"] is False
    drawdown = ladder.evaluate_ladder([], [(1, 5_000.0), (2, 4_400.0)])["step_down"]
    assert drawdown["drawdown_triggered"] is True


def test_seek_offset_never_skips_rows_at_or_after_the_start(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    stamps = [T0 + index * 1_000 for index in range(500)]
    path.write_text(
        "".join(
            json.dumps(
                {"event_type": "heartbeat", "observed_at_utc": _iso(ms), "pad": "x" * i}
            )
            + "\n"
            for i, ms in enumerate(stamps)
        )
    )
    target = stamps[321]
    offset = ladder.seek_offset(path, target, chunk_bytes=64)
    with path.open("rb") as handle:
        handle.seek(offset)
        tail = handle.read().decode()
    assert f'"{_iso(target)}"' in tail
    assert offset > 0
    assert ladder.seek_offset(path, stamps[0] - 1, chunk_bytes=64) == 0


def test_main_writes_json_and_a_short_text_summary(
    ledgers: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out" / "ladder.json"
    code = ladder.main(
        [
            "--ledger-dir",
            str(ledgers),
            "--run-id",
            RUN,
            "--since",
            SINCE,
            "--out",
            str(out),
        ]
    )
    assert code == 0
    report = json.loads(out.read_text())
    assert report["summary"]["closed"] == 3
    text = capsys.readouterr().out
    assert "closed Donchian lifecycles: 3" in text
    assert "advance: pending" in text


def test_main_requires_a_run_or_profile_selection(ledgers: Path) -> None:
    with pytest.raises(SystemExit):
        ladder.main(["--ledger-dir", str(ledgers), "--since", SINCE])


def test_the_tool_imports_no_execution_or_project_modules() -> None:
    source = Path(ladder.__file__).read_text()
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    assert modules <= {
        "__future__",
        "argparse",
        "bisect",
        "collections",
        "csv",
        "dataclasses",
        "datetime",
        "json",
        "math",
        "pathlib",
        "re",
        "statistics",
        "sys",
        "typing",
    }


def test_unannounced_exit_order_is_attributed_by_time_window(tmp_path: Path) -> None:
    """A close whose order id the journal never announced still reconciles."""
    brent = _Ledger(tmp_path / "xyz:brentoil.jsonl", f"{PROFILE}_xyz:brentoil")
    _lifecycle(
        brent,
        symbol="xyz:BRENTOIL",
        side="long",
        decision_ms=T0,
        entry_oid=51,
        entry_price=100.0,
        size=4.0,
        stop=98.5,
        exit_oid=52,
        exit_ms=T0 + 5 * HOUR_MS,
        exit_price=101.0,
        reason="hourly_price_recipe_exit",
    )
    for row in brent.rows:
        payload = row["payload"]
        assert isinstance(payload, dict)
        if row["event_type"] == "close":
            payload.pop("oid")
    # A later, unrelated close fill outside the lifecycle is never attributed.
    brent.add(
        "fill",
        T0 + 9 * HOUR_MS,
        {
            "oid": 99,
            "trade_id": 990,
            "venue_timestamp_ms": T0 + 9 * HOUR_MS,
            "price": 90.0,
            "size": 4.0,
            "direction": "Close Long",
            "closed_pnl_usd": -40.0,
            "fee_usd": 0.1,
        },
    )
    brent.write()
    _Ledger(tmp_path / "decisions.jsonl", PROFILE).write()
    row = _by_oid(_report(tmp_path))[51]
    assert row["status"] == "closed"
    assert row["exit_attribution"] == "order_ids_plus_time_window"
    assert row["exit_price"] == pytest.approx(101.0)
    assert row["net_usd"] == pytest.approx(4.0 - 0.2)


def _unreconciled_first_close(tmp_path: Path, *, exit_fill_size: float | None) -> Path:
    """A gap stop-out to 80 against a 99 stop, then 30 closes of +0.58R.

    ``exit_fill_size`` None drops the loser's exit fill from the journal (closed
    without fills); a size below the entry leaves it closed with a size mismatch.
    """
    sol = _Ledger(tmp_path / "sol.jsonl", f"{PROFILE}_sol")
    cohort = _Ledger(tmp_path / "decisions.jsonl", PROFILE)
    for index in range(31):
        decision = T0 + index * 3 * HOUR_MS
        loser = index == 0
        _lifecycle(
            sol,
            symbol="SOL",
            side="long",
            decision_ms=decision,
            entry_oid=100 + 10 * index,
            entry_price=100.0,
            size=10.0,
            stop=99.0,
            exit_oid=105 + 10 * index,
            exit_ms=decision + HOUR_MS,
            exit_price=80.0 if loser else 100.6,
            reason="protective_stop" if loser else "profit_floor",
        )
    for row in sol.rows:
        payload = row["payload"]
        assert isinstance(payload, dict)
        if row["event_type"] != "fill" or payload.get("oid") != 105:
            continue
        if exit_fill_size is None:
            sol.rows.remove(row)
        else:
            payload["size"] = exit_fill_size
        break
    cohort.add("cohort_snapshot", T0, {"account_value_usd": 5_000.0, "assets": []})
    for ledger in (sol, cohort):
        ledger.write()
    return tmp_path


@pytest.mark.parametrize(
    "exit_fill_size,status",
    [(None, "closed_without_fills"), (5.0, "closed_size_mismatch")],
)
def test_an_unreconciled_close_holds_its_place_in_the_advance_window(
    tmp_path: Path, exit_fill_size: float | None, status: str
) -> None:
    """Dropping it would pull a 31st close in and report advance at +0.58R."""
    report = _report(_unreconciled_first_close(tmp_path, exit_fill_size=exit_fill_size))
    loser = _by_oid(report)[100]
    assert loser["status"] == status
    assert loser["exit_ms"] == T0 + HOUR_MS - (0 if exit_fill_size is None else 500)
    assert report["summary"]["unreconciled"] == 1
    advance = report["ladder"]["advance"]
    assert advance["closed"] == ladder.ADVANCE_CLOSES
    assert advance["status"] == "indeterminate"
    assert advance["unreconciled"] == 1
    assert advance["capped_mark_unavailable"] == 0
    # The 29 reconciled closes in the window, not the 30 after it.
    assert advance["net_usd"] == pytest.approx(29 * 5.8)
    step_down = report["ladder"]["step_down"]
    assert step_down["closed"] == 31
    assert step_down["unreconciled"] == 1
    text = ladder.summary_text(report)
    assert "unreconciled lifecycles: 1" in text
    assert "advance: indeterminate (30/30 closes" in text


def test_a_reconciled_gap_loss_in_the_same_window_is_not_met(tmp_path: Path) -> None:
    report = _report(_unreconciled_first_close(tmp_path, exit_fill_size=10.0))
    assert _by_oid(report)[100]["r_multiple"] == pytest.approx(-20.02)
    advance = report["ladder"]["advance"]
    assert advance["status"] == "not_met"
    assert advance["unreconciled"] == 0
    assert advance["mean_r"] == pytest.approx((29 * 0.58 - 20.02) / 30)


def test_a_close_without_a_known_r_makes_the_advance_indeterminate() -> None:
    rows = [_trade(4.0)] * 30
    rows[7] = {**rows[7], "r_multiple": None}
    advance = ladder.evaluate_ladder(rows, [])["advance"]
    assert advance["status"] == "indeterminate"
    assert advance["unreconciled"] == 1
    assert advance["net_usd"] == pytest.approx(29 * 4.0)


def test_a_verified_flat_close_is_ordered_by_its_flat_time(tmp_path: Path) -> None:
    """A late unreconciled close cannot jump into, or out of, an earlier window."""
    ledger_dir = _unreconciled_first_close(tmp_path, exit_fill_size=None)
    report = _report(ledger_dir)
    loser = _by_oid(report)[100]
    assert loser["exit_time_utc"] == _iso(T0 + HOUR_MS)
    assert loser["in_market_until_ms"] == T0 + HOUR_MS


# ---------------------------------------------------------------- review additions


def _routing_actions(
    cohort: _Ledger,
    observed_ms: int,
    *,
    actions: Sequence[Mapping[str, object]] = (),
    withheld: Sequence[Mapping[str, object]] = (),
) -> None:
    cohort.add(
        "intent_routing",
        observed_ms,
        {"evaluations": [], "actions": list(actions), "withheld": list(withheld)},
    )


def _entry_action(
    symbol: str, decision_ms: int, age_ms: int, *, strategy: str = DONCHIAN
) -> dict[str, object]:
    return {
        "action": "enter",
        "strategy_id": strategy,
        "symbol": symbol,
        "side": "long",
        "decision_time_ms": decision_ms,
        "submission_age_ms": age_ms,
        "submission_boundary": "sdk_dispatch",
        "submission_limit_ms": 30_000,
        "submission_observed_at_ms": decision_ms + age_ms,
    }


def test_entry_headroom_measures_every_routed_entry_and_stale_withhold(
    tmp_path: Path,
) -> None:
    cohort = _Ledger(tmp_path / "decisions.jsonl", PROFILE)
    later = T0 + HOUR_MS
    # Three serial entries of one decision, one the next hour, and noise: an exit
    # action, another route's entry, a duplicate row and a pre-window entry.
    _routing_actions(
        cohort,
        T0 + 29_000,
        actions=[
            _entry_action("SOL", T0, 16_000),
            _entry_action("xyz:SNDK", T0, 23_500),
            _entry_action("xyz:TSLA", T0, 28_000),
            {**_entry_action("SOL", T0, 1_000), "action": "close"},
            _entry_action("BTC", T0, 29_500, strategy="liquidity_sweep_v2"),
        ],
    )
    _routing_actions(cohort, T0 + 30_000, actions=[_entry_action("SOL", T0, 16_000)])
    _routing_actions(
        cohort,
        T0 - 2 * HOUR_MS + 5_000,
        actions=[_entry_action("SOL", T0 - 7_200_000, 5)],
    )
    stale = {
        **_entry_action("xyz:BRENTOIL", later, 31_000),
        "reason": "stale_before_submission",
    }
    stale.pop("action")
    observe_only = {
        **stale,
        "symbol": "xyz:SPCX",
        "reason": "provider_symbol_observe_only",
    }
    _routing_actions(
        cohort,
        later + 32_000,
        actions=[_entry_action("SOL", later, 9_000)],
        withheld=[stale, observe_only],
    )
    cohort.write()
    report = _report(tmp_path)
    headroom = report["entry_deadline_headroom"]
    assert headroom["entries"] == 4
    assert headroom["limit_seconds"] == [30.0]
    ages = headroom["age_seconds"]
    assert ages["median"] == pytest.approx((16.0 + 23.5) / 2)
    assert ages["p95"] == pytest.approx(23.5 + 4.5 * (0.95 * 3 - 2))
    assert ages["max"] == pytest.approx(28.0)
    assert headroom["minimum_headroom_seconds"] == pytest.approx(2.0)
    assert headroom["within_warning_of_limit"] == 1
    assert headroom["over_limit"] == 0
    ranks = headroom["by_same_decision_rank"]
    assert ranks["1"] == {
        "entries": 2,
        "median_age_seconds": pytest.approx(12.5),
        "max_age_seconds": pytest.approx(16.0),
    }
    assert ranks["3"]["max_age_seconds"] == pytest.approx(28.0)
    tsla = next(row for row in headroom["entry_rows"] if row["symbol"] == "xyz:TSLA")
    assert (tsla["same_decision_rank"], tsla["same_decision_entries"]) == (3, 3)
    assert headroom["stale_before_submission"] == 1
    assert headroom["stale_entries"][0]["symbol"] == "xyz:BRENTOIL"
    assert headroom["stale_entries"][0]["age_seconds"] == pytest.approx(31.0)
    text = ladder.summary_text(report)
    assert "max 28.0 s vs 30 s limit" in text
    assert "stale_before_submission: 1" in text


def test_ioc_no_fills_count_as_submitted_and_over_limit_entries_are_counted(
    tmp_path: Path,
) -> None:
    cohort = _Ledger(tmp_path / "decisions.jsonl", PROFILE)
    # A submitted IOC that did not fill is journaled as a withhold with its age.
    no_fill = {**_entry_action("xyz:SNDK", T0, 26_000), "reason": "entry_ioc_no_fill"}
    no_fill.pop("action")
    _routing_actions(
        cohort,
        T0 + 32_000,
        # Synthetic: live withholds a stale entry, but the branch is reported.
        actions=[_entry_action("SOL", T0, 31_000)],
        withheld=[no_fill],
    )
    cohort.write()
    report = _report(tmp_path)
    headroom = report["entry_deadline_headroom"]
    assert (headroom["entries"], headroom["ioc_no_fill"]) == (2, 1)
    assert headroom["over_limit"] == 1
    assert headroom["within_warning_of_limit"] == 2
    assert headroom["minimum_headroom_seconds"] == pytest.approx(-1.0)
    rows = {row["symbol"]: row for row in headroom["entry_rows"]}
    assert rows["xyz:SNDK"]["outcome"] == "ioc_no_fill"
    assert rows["xyz:SNDK"]["same_decision_rank"] == 1
    assert (rows["SOL"]["outcome"], rows["SOL"]["same_decision_rank"]) == (
        "submitted",
        2,
    )
    assert headroom["stale_before_submission"] == 0
    text = ladder.summary_text(report)
    assert "2 Donchian entries (1 IOC no-fill)" in text
    assert "2 within 5 s; 1 over)" in text


def test_lifecycle_entry_submission_comes_from_its_acknowledgement(
    tmp_path: Path,
) -> None:
    sol = _Ledger(tmp_path / "sol.jsonl", f"{PROFILE}_sol")
    for index, age in enumerate((27_700, None)):
        decision = T0 + index * 3 * HOUR_MS
        _lifecycle(
            sol,
            symbol="SOL",
            side="long",
            decision_ms=decision,
            entry_oid=300 + 10 * index,
            entry_price=100.0,
            size=5.0,
            stop=98.0,
            exit_oid=305 + 10 * index,
            exit_ms=decision + HOUR_MS,
            exit_price=101.0,
            reason="hourly_price_recipe_exit",
            submission_age_ms=age,
        )
    sol.write()
    _Ledger(tmp_path / "decisions.jsonl", PROFILE).write()
    rows = _by_oid(_report(tmp_path))
    observed = rows[300]["entry_submission"]
    assert observed["status"] == "observed"
    assert observed["age_seconds"] == pytest.approx(27.7)
    assert observed["headroom_seconds"] == pytest.approx(2.3)
    assert observed["boundary"] == "sdk_dispatch"
    assert rows[310]["entry_submission"] == {"status": "unavailable"}


def _sizing(estimated: float, quantity: float) -> dict[str, object]:
    return {
        "estimated_loss_usd": estimated,
        "quantity": quantity,
        "effective_maximum_loss_usd": 28.99,
        "notional_usd": quantity * 100.0,
    }


def test_modeled_and_realized_loss_are_compared_at_the_initial_stop(
    tmp_path: Path,
) -> None:
    sndk = _Ledger(tmp_path / "xyz:sndk.jsonl", f"{PROFILE}_xyz:sndk")
    # A: a short stopped 50 bps through its 200 bps stop; the model priced 10.5.
    _lifecycle(
        sndk,
        symbol="xyz:SNDK",
        side="short",
        decision_ms=T0,
        entry_oid=11,
        entry_price=100.0,
        size=10.0,
        stop=102.0,
        exit_oid=12,
        exit_ms=T0 + HOUR_MS,
        exit_price=102.5,
        reason="protective_stop",
        sizing=_sizing(24.0, 10.5),
    )
    # B: a raised stop closes a long in profit; it is not a loss at the model.
    _lifecycle(
        sndk,
        symbol="xyz:SNDK",
        side="long",
        decision_ms=T0 + 3 * HOUR_MS,
        entry_oid=21,
        entry_price=100.0,
        size=10.0,
        stop=99.0,
        exit_oid=22,
        exit_ms=T0 + 5 * HOUR_MS,
        exit_price=100.5,
        reason="protective_stop",
        sizing=_sizing(14.0, 10.0),
        stop_raised=True,
    )
    # A sizing row whose entry never acknowledged must not attach to C.
    sndk.add("entry_stop_risk_sizing", T0 + 7 * HOUR_MS, _sizing(99.0, 1.0))
    # C: stopped without any sizing row.
    _lifecycle(
        sndk,
        symbol="xyz:SNDK",
        side="long",
        decision_ms=T0 + 8 * HOUR_MS,
        entry_oid=31,
        entry_price=100.0,
        size=10.0,
        stop=99.0,
        exit_oid=32,
        exit_ms=T0 + 9 * HOUR_MS,
        exit_price=99.0,
        reason="protective_stop",
    )
    sndk.write()
    _Ledger(tmp_path / "decisions.jsonl", PROFILE).write()
    report = _report(tmp_path)
    rows = _by_oid(report)
    model = rows[11]["stop_loss_model"]
    assert model["modeled_source"] == "entry_stop_risk_sizing"
    assert model["modeled_loss_at_filled_size_usd"] == pytest.approx(24.0 * 10 / 10.5)
    assert model["exited_at_initial_stop"] is True
    assert model["realized_loss_usd"] == pytest.approx(25.2)
    assert model["realized_to_modeled"] == pytest.approx(25.2 / (24.0 * 10 / 10.5))
    assert model["realized_to_unslipped"] == pytest.approx(25.2 / 20.0)
    raised = rows[21]["stop_loss_model"]
    assert raised["stop_raised"] is True
    assert raised["exited_at_initial_stop"] is False
    assert raised["realized_loss_usd"] is None
    unmodeled = rows[31]["stop_loss_model"]
    assert unmodeled["modeled_source"] == "missing"
    assert unmodeled["realized_loss_usd"] == pytest.approx(10.2)
    assert unmodeled["realized_to_modeled"] is None
    summary = report["stop_loss_model"]
    assert summary["with_modeled_loss"] == 2
    assert summary["stop_exits_at_initial_stop"] == 2
    assert summary["stop_exits_after_raise"] == 1
    assert summary["modeled_loss_usd"] == pytest.approx(24.0 * 10 / 10.5)
    assert summary["realized_loss_usd"] == pytest.approx(25.2 + 10.2)
    assert summary["realized_to_modeled"]["mean"] == pytest.approx(1.1025)
    assert "2 close(s) at the initial stop" in ladder.summary_text(report)


def test_every_stop_fill_reason_is_compared_and_a_dollar_budget_is_read(
    tmp_path: Path,
) -> None:
    brent = _Ledger(tmp_path / "xyz:brentoil.jsonl", f"{PROFILE}_xyz:brentoil")
    reasons = (
        "protective_stop_during_protection",
        "protective_stop_during_exit",
        "protective_stop_during_rejected_exit",
        "replacement_protective_stop_during_exit",
        "protective_stop_remainder",
        "protective_stop_future_reason",
    )
    for index, reason in enumerate(reasons):
        decision = T0 + index * 3 * HOUR_MS
        _lifecycle(
            brent,
            symbol="xyz:BRENTOIL",
            side="long",
            decision_ms=decision,
            entry_oid=400 + 10 * index,
            entry_price=100.0,
            size=5.0,
            stop=98.0,
            exit_oid=405 + 10 * index,
            exit_ms=decision + HOUR_MS,
            exit_price=97.9,
            reason=reason,
            # A fixed-dollar budget journals no equity-fraction fields.
            sizing={
                "estimated_loss_usd": 10.5,
                "quantity": 5.0,
                "maximum_loss_usd": 25.0,
            },
        )
    brent.write()
    _Ledger(tmp_path / "decisions.jsonl", PROFILE).write()
    report = _report(tmp_path)
    rows = _by_oid(report)
    model = rows[400]["stop_loss_model"]
    assert model["exited_at_initial_stop"] is True
    assert model["budget_usd"] == pytest.approx(25.0)
    assert model["realized_loss_usd"] == pytest.approx(10.7)
    summary = report["stop_loss_model"]
    assert summary["stop_exits_at_initial_stop"] == 5
    assert summary["stop_exit_reasons"] == {reason: 1 for reason in reasons[:5]}
    # A stop-fill reason the tool does not know yet is counted, not dropped.
    assert summary["unclassified_stop_exit_reasons"] == {
        "protective_stop_future_reason": 1
    }
    assert rows[450]["stop_loss_model"]["exited_at_initial_stop"] is False


def test_proposed_step_down_look_is_indeterminate_with_an_unreconciled_close() -> None:
    # Mean -0.1R: the 50-close look triggers once every close is reconciled.
    rows = [_trade(-5.0), _trade(3.0)] * 25
    assert ladder.evaluate_proposed_ladder(rows, [])["step_down"]["triggered"] is True
    rows[7] = {**rows[7], "status": "closed_size_mismatch"}
    step = ladder.evaluate_proposed_ladder(rows, [])["step_down"]
    look = step["looks"][0]
    assert look["status"] == "indeterminate"
    assert (look["capped_status"], look["realized_status"]) == (
        "indeterminate",
        "indeterminate",
    )
    assert (look["capped_t"], look["realized_t"]) == (None, None)
    assert (step["t_triggered"], step["triggered"]) == (False, False)
    assert ladder._looks_text(step["looks"]) == (
        "50: indeterminate, 100: pending, 150: pending"
    )


def test_a_uniformly_winning_block_meets_the_conservative_look() -> None:
    """Zero spread has no t; a positive mean is t = +inf, as in the power table."""
    winning = ladder.evaluate_proposed_ladder([_trade(5.0)] * 30, [])["advance"]
    assert winning["looks"][0]["t_stat"] is None
    assert winning["looks"][0]["conservative_status"] == "met"
    assert winning["conservative_status"] == "advance"
    flat = ladder.evaluate_proposed_ladder([_trade(0.0)] * 30, [])["advance"]
    assert flat["looks"][0]["conservative_status"] == "not_met"


def test_proposed_rule_gates_ex_top_three_in_r_not_dollars() -> None:
    """Three large-dollar, small-R winners fail the USD gate, not the R gate."""
    rows = (
        [_trade(100.0, risk=500.0)] * 3
        + [_trade(0.3, risk=1.0)] * 10
        + [_trade(-1.0, risk=10.0)] * 17
    )
    current = ladder.evaluate_ladder(rows, [])["advance"]
    assert current["status"] == "not_met"
    assert current["ex_top3_net_usd"] == pytest.approx(286.0 - 300.0)
    proposed = ladder.evaluate_proposed_ladder(rows, [])["advance"]
    assert proposed["status"] == "advance"
    assert proposed["advanced_at_closes"] == 30
    look = proposed["looks"][0]
    assert look["ex_top3_r"] == pytest.approx(1.9 - 0.9)
    assert look["ex_top3_net_usd"] == pytest.approx(-14.0)
    assert [row["status"] for row in proposed["looks"][1:]] == ["pending", "pending"]


def test_proposed_rule_retests_at_sixty_and_ninety_closes() -> None:
    losing, winning = [_trade(-1.0)] * 30, [_trade(3.0)] * 30
    assert ladder.evaluate_ladder(losing + winning, [])["advance"]["status"] == (
        "not_met"
    )
    proposed = ladder.evaluate_proposed_ladder(losing + winning, [])["advance"]
    assert [look["status"] for look in proposed["looks"]] == [
        "not_met",
        "met",
        "pending",
    ]
    assert (proposed["status"], proposed["advanced_at_closes"]) == ("advance", 60)
    waiting = ladder.evaluate_proposed_ladder(losing + winning[:15], [])["advance"]
    assert waiting["status"] == "pending"
    never = ladder.evaluate_proposed_ladder([_trade(-1.0)] * 95, [])["advance"]
    assert never["status"] == "not_met"
    assert never["conservative_status"] == "not_met"


def test_conservative_variant_needs_a_t_of_one_point_six() -> None:
    # Mean +0.1R with a standard deviation of about 0.4R: t is about 1.4 at 30.
    rows = [_trade(5.0), _trade(-3.0)] * 15
    proposed = ladder.evaluate_proposed_ladder(rows, [])["advance"]
    look = proposed["looks"][0]
    assert look["t_stat"] == pytest.approx(0.1 / (0.4 * (30 / 29) ** 0.5 / 30**0.5))
    assert proposed["status"] == "advance"
    assert proposed["conservative_status"] == "pending"
    assert look["conservative_status"] == "not_met"


def test_proposed_advance_is_indeterminate_with_an_unknown_r() -> None:
    rows = [_trade(4.0)] * 30
    rows[3] = {**rows[3], "r_multiple": None}
    proposed = ladder.evaluate_proposed_ladder(rows, [])["advance"]
    assert proposed["status"] == "indeterminate"
    assert proposed["looks"][0]["unreconciled"] == 1


def test_proposed_step_down_uses_cumulative_t_at_fixed_looks() -> None:
    # A losing 50-close stretch inside a winning run trips the rule in force only.
    middle = [_trade(5.0)] * 25 + [_trade(-1.0)] * 50 + [_trade(5.0)] * 25
    assert ladder.evaluate_ladder(middle, [])["step_down"]["window_triggered"] is True
    step = ladder.evaluate_proposed_ladder(middle, [])["step_down"]
    assert step["triggered"] is False
    assert [look["status"] for look in step["looks"]] == [
        "not_triggered",
        "not_triggered",
        "pending",
    ]
    # Mean -0.1R with a 0.4R spread: t is about -1.75 at 50 closes.
    losing = [_trade(-5.0), _trade(3.0)] * 25
    step = ladder.evaluate_proposed_ladder(losing, [])["step_down"]
    assert step["t_triggered"] is True
    assert step["looks"][0]["capped_t"] == pytest.approx(
        -0.1 / (0.4 * (50 / 49) ** 0.5 / 50**0.5)
    )
    # Zero spread has no t; a uniformly losing block still steps down.
    flat = ladder.evaluate_proposed_ladder([_trade(-2.0)] * 50, [])["step_down"]
    assert flat["looks"][0]["capped_t"] is None
    assert flat["triggered"] is True
    drawdown = ladder.evaluate_proposed_ladder([], [(1, 5_000.0), (2, 4_400.0)])
    assert drawdown["step_down"]["drawdown_triggered"] is True
    assert drawdown["step_down"]["t_triggered"] is False
    assert drawdown["report_only"] is True


def test_review_additions_leave_every_existing_report_key_in_place(
    ledgers: Path,
) -> None:
    report = _report(ledgers)
    assert {
        "execution_authority",
        "selection",
        "ledger_stats",
        "summary",
        "ladder",
        "equity",
        "lifecycles",
        "donchian_entry_extension",
        "donchian_short_extension",
        "timer_counterfactual",
        "timer_exits",
        "buy_and_hold",
    } < set(report)
    assert set(report["ladder"]) == {"advance", "step_down"}
    assert report["ladder_proposed"]["advance"]["status"] == "pending"
    assert report["entry_deadline_headroom"]["entries"] == 0
    json.dumps(report, allow_nan=False)
    text = ladder.summary_text(report)
    assert "proposed ladder (report-only): advance pending" in text
    assert "advance: pending (3/30 closes" in text
