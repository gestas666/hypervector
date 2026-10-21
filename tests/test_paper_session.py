"""Offline paper session: warm-up + bar loop into ExplicitFillEngine (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.nautilus.load_export import load_strategy_loadout
from hypervector.paper.session import (
    PaperSession,
    PaperSessionResult,
    _entry_qty,
    run_paper_session_offline,
)
from synthetic_strategies import (
    MANAGED_LONG,
    MANAGED_SHORT,
    SYNTHETIC_LONG,
    SYNTHETIC_SHORT,
)


def _write_strict_export(root: Path, *, strategy: str = SYNTHETIC_SHORT) -> Path:
    """Minimal strict Phase 1.5 export for offline session tests."""
    track = "downtrend" if "short" in strategy else "uptrend"
    return export_candidate(
        root / "exports",
        run_id="sess01",
        meta={
            "symbol": "BTC",
            "timeframe": "1m",
            "track": track,
            "lookback_days": 30,
            "init_cash": 10_000.0,
            "tp_sl_mode": "fixed_rr",
            "exits": {
                "mode": "fixed_rr",
                "sl_pct": 0.01,
                "rr": 2.0,
                "atr_length": 14,
                "sl_atr_mult": 1.5,
                "trail_atr_mult": 2.0,
            },
            "costs": {
                "taker_fee": 0.00035,
                "slippage_bps": 2.0,
                "funding_rate_8h": 0.0001,
                "minutes_per_funding": 480,
            },
            "risk": {
                "risk_pct_min": 0.01,
                "risk_pct_max": 0.05,
                "default_conviction": 0.5,
                "max_size_frac": 1.0,
            },
            "data_provenance": {"sources": {"fixture": 300}},
        },
        params={
            "strategy": strategy,
            "fast": 5,
            "slow": 20,
            "exit_mode": "fixed_rr",
            "role": track,
        },
        metrics={
            "net_pnl": 50.0,
            "total_return_pct": 0.5,
            "sharpe": 0.4,
            "trade_count": 3,
        },
        candidate_id="paper_session_synthetic",
        strict=True,
    )

def _decision_rows(path: Path) -> list[dict[str, object]]:
    """Read the append-only test ledger."""
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

def test_offline_session_writes_paper_decisions(tmp_path: Path):
    export = _write_strict_export(tmp_path)
    ohlcv = fixture_ohlcv(n_bars=300, drift=-5.0, wave_period=40)
    result = run_paper_session_offline(
        export_dir=export,
        data_root=tmp_path / "data",
        ohlcv=ohlcv,
        conviction=0.5,
        max_bars=300,
    )
    assert isinstance(result, PaperSessionResult)
    assert result.bars_processed > 0
    assert result.bars_processed == 300
    assert result.export_dir == export.resolve()
    assert result.run_id
    assert result.decisions_path.is_file()
    text = result.decisions_path.read_text(encoding="utf-8")
    assert "execution_mode" in text
    assert "paper" in text
    assert result.fills_count >= 0

def test_session_passes_execution_mode_to_engine(tmp_path: Path):
    """PaperSession execution_mode is forwarded to ExplicitFillEngine fills."""
    export = _write_strict_export(tmp_path)
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        conviction=0.5,
        execution_mode="shadow",
    )
    assert session.execution_mode == "shadow"
    # Engine path: force a market fill stamp via apply_market_fill
    rec = session.engine.apply_market_fill(
        feed_ts="t0",
        action="enter_long",
        side="buy",
        qty=0.01,
        mark_px=100.0,
    )
    assert rec["execution_mode"] == "shadow"
    assert rec["submitted"] is False

def test_session_identity_stamps_effective_metalabel_policy(tmp_path: Path):
    """Every backend run identifies its immutable strategy and model policy."""
    export = _write_strict_export(tmp_path, strategy=SYNTHETIC_LONG)

    class FakeML:
        root = type("R", (), {"name": "synthetic-long-v001"})()
        feature_names = ["a"]

        def predict_probability(self, features):
            return 0.6

    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        conviction=0.42,
        execution_mode="shadow",
        metalabeler=FakeML(),
        metalabel_mode="observe",
    )

    session.ensure_session_identity()
    row = json.loads(
        session.decisions_path.read_text(encoding="utf-8").splitlines()[-1]
    )

    assert row["run_id"] == session.run_id
    assert row["export_id"] == session.export_id
    assert row["strategy_name"] == SYNTHETIC_LONG
    assert row["execution_mode"] == "shadow"
    assert row["metalabel_mode"] == "observe"
    assert row["metalabel_bundle_id"] == "synthetic-long-v001"
    assert row["conviction"] == 0.42
    assert row["strategy_params"]["strategy"] == SYNTHETIC_LONG
    assert row["exits"]["mode"] == "fixed_rr"
    assert row["risk"]["risk_pct_max"] == 0.05
    assert row["costs"]["slippage_bps"] == 2.0
    assert "private_key" not in json.dumps(row).lower()
    assert "wallet" not in json.dumps(row).lower()

def test_session_accepts_canonical_hourly_funding_with_null_legacy_rate(
    tmp_path: Path,
):
    """Research CostModel exports must load directly into the paper backend."""
    export = _write_strict_export(tmp_path)
    meta_path = export / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["costs"]["funding_rate_1h"] = 0.0000125
    meta["costs"]["funding_rate_8h"] = None
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    session = PaperSession(export_dir=export, data_root=tmp_path / "data")

    assert session.cost_provider.snapshot().funding_rate_hourly == pytest.approx(
        0.0000125
    )

def test_offline_session_no_trade_before_two_bars(tmp_path: Path):
    """Warm-up matches actor: no intent/fill path until buffer length >= 2."""
    export = _write_strict_export(tmp_path)
    ohlcv = fixture_ohlcv(n_bars=1, drift=-5.0)
    result = run_paper_session_offline(
        export_dir=export,
        data_root=tmp_path / "data",
        ohlcv=ohlcv,
        max_bars=1,
    )
    assert result.bars_processed == 1
    assert result.fills_count == 0

def test_offline_session_rejects_bad_ohlcv(tmp_path: Path):
    export = _write_strict_export(tmp_path)
    import pandas as pd

    bad = pd.DataFrame({"close": [1.0, 2.0]})
    with pytest.raises(ValueError, match="OHLCV"):
        run_paper_session_offline(
            export_dir=export,
            data_root=tmp_path / "data",
            ohlcv=bad,
        )

def test_offline_session_missing_export(tmp_path: Path):
    ohlcv = fixture_ohlcv(n_bars=5)
    with pytest.raises((FileNotFoundError, ValueError, OSError)):
        run_paper_session_offline(
            export_dir=tmp_path / "missing_export",
            data_root=tmp_path / "data",
            ohlcv=ohlcv,
        )

def test_session_applies_funding_on_open_long(tmp_path: Path):
    """Open long + non-zero hourly rate → on_bar writes signed funding decision."""
    export = _write_strict_export(tmp_path)
    rate = 0.0001
    mark = 50_000.0
    qty = 1.0
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        funding_rate_hourly=rate,
        enable_funding_refresh=False,
    )
    session.engine.apply_market_fill(
        feed_ts="t0",
        action="enter_long",
        side="buy",
        qty=qty,
        mark_px=mark,
    )
    bar = {
        "timestamp": pd.Timestamp("2026-07-22T00:59:00Z"),
        "open": mark,
        "high": mark,
        "low": mark,
        "close": mark,
        "volume": 1.0,
    }
    session.on_bar(bar)

    lines = [
        json.loads(line)
        for line in session.decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    funding_rows = [r for r in lines if r.get("action") == "funding"]
    assert len(funding_rows) == 1
    fre = funding_rows[0]
    assert fre["funding_payment_usd"] == pytest.approx(qty * mark * rate)
    assert fre["funding_payment_usd"] > 0  # long pays when rate > 0
    assert fre["funding_rate_hourly"] == pytest.approx(rate)
    assert fre["side"] == "buy"
    assert session.engine.position.qty == qty

def test_session_does_not_prorate_funding_between_hourly_boundaries(
    tmp_path: Path,
) -> None:
    export = _write_strict_export(tmp_path)
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        funding_rate_hourly=0.0001,
        enable_funding_refresh=False,
    )
    session.engine.apply_market_fill(
        feed_ts="t0",
        action="enter_long",
        side="buy",
        qty=1.0,
        mark_px=50_000.0,
    )
    session.on_bar(
        {
            "timestamp": pd.Timestamp("2026-07-22T00:01:00Z"),
            "open": 50_000.0,
            "high": 50_000.0,
            "low": 50_000.0,
            "close": 50_000.0,
            "volume": 1.0,
        }
    )
    rows = [
        json.loads(line)
        for line in session.decisions_path.read_text().splitlines()
        if line.strip()
    ]
    assert not [row for row in rows if row.get("action") == "funding"]

def test_session_uses_live_oracle_for_hourly_funding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    export = _write_strict_export(tmp_path)
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        funding_rate_hourly=0.0001,
        enable_funding_refresh=False,
    )
    snapshot = session.cost_provider.snapshot()
    monkeypatch.setattr(
        session.cost_provider,
        "snapshot",
        lambda: replace(snapshot, oracle_px=51_000.0),
    )
    session.engine.apply_market_fill(
        feed_ts="t0",
        action="enter_long",
        side="buy",
        qty=1.0,
        mark_px=50_000.0,
    )
    session.on_bar(
        {
            "timestamp": pd.Timestamp("2026-07-22T00:59:00Z"),
            "open": 50_000.0,
            "high": 50_000.0,
            "low": 50_000.0,
            "close": 50_000.0,
            "volume": 1.0,
        }
    )
    rows = [
        json.loads(line)
        for line in session.decisions_path.read_text().splitlines()
        if line.strip()
    ]
    funding = next(row for row in rows if row.get("action") == "funding")
    assert funding["funding_payment_usd"] == pytest.approx(5.1)

def test_session_funding_refresh_disabled_offline(tmp_path: Path, monkeypatch):
    """enable_funding_refresh=False must never hit CostProvider.refresh_funding."""
    export = _write_strict_export(tmp_path)
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        funding_rate_hourly=0.0001,
        enable_funding_refresh=False,
    )

    def _boom(*_a, **_k):
        raise AssertionError("refresh_funding must not be called offline")

    monkeypatch.setattr(session.cost_provider, "refresh_funding", _boom)
    session.engine.apply_market_fill(
        feed_ts="t0",
        action="enter_long",
        side="buy",
        qty=0.01,
        mark_px=50_000.0,
    )
    session.on_bar(
        {
            "timestamp": pd.Timestamp("2026-07-22T00:01:00Z"),
            "open": 50_000.0,
            "high": 50_000.0,
            "low": 50_000.0,
            "close": 50_000.0,
            "volume": 1.0,
        }
    )
    assert session.maybe_refresh_funding() is None

def test_session_inject_book_offline_no_poll(tmp_path: Path):
    """Offline: inject BookSnapshot into BookFeed; enable_book_poll stays False."""
    from hypervector.paper.book import BookLevel, BookSnapshot
    from hypervector.paper.fill_models import FILL_MODEL_L2_WALK_V1

    export = _write_strict_export(tmp_path)
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        preferred_fill_model=FILL_MODEL_L2_WALK_V1,
        enable_book_poll=False,
        enable_funding_refresh=False,
    )
    assert session.book_feed.latest() is None
    snap = BookSnapshot(
        symbol="BTC",
        bids=(BookLevel(99.0, 10.0),),
        asks=(BookLevel(101.0, 10.0),),
        ts_recv_ms=1.0,
        ts_exchange_ms=1.0,
        source="inject",
    )
    session.inject_book(snap)
    assert session.book_feed.latest() is snap
    # Direct engine path with injected book uses L2 walk when preferred.
    rec = session.engine.apply_market_fill(
        feed_ts="t0",
        action="enter_long",
        side="buy",
        qty=1.0,
        mark_px=100.0,
        book=session.book_feed.latest(),
        now_ms=1.0,
    )
    assert rec["fill_model_id"] == FILL_MODEL_L2_WALK_V1
    # l2_walk_v1 uses pure VWAP (slippage_bps unused; impact is in the walk)
    assert abs(rec["fill_px"] - 101.0) < 1e-9
    assert rec.get("skipped") is not True


# --- declared execution options ---------------------------------------------


def _minute_bar(minute: int, *, high: float = 100.5, low: float = 99.5) -> dict:
    return {
        "timestamp": pd.Timestamp(f"2026-07-25T12:{minute:02d}:00Z"),
        "open": 100.0,
        "high": high,
        "low": low,
        "close": 100.0,
        "volume": 1.0,
    }


def _scripted_intents(
    monkeypatch: pytest.MonkeyPatch, intents: list[tuple[str, bool, bool]]
) -> None:
    """Replace the strategy with a scripted intent per processed bar."""
    from hypervector.nautilus.signals import SignalIntent

    queue = list(intents)

    def scripted(df: pd.DataFrame, _name: str, _params: dict) -> SignalIntent:
        direction, enter, exit_ = queue.pop(0)
        return SignalIntent(
            direction=direction, enter=enter, exit=exit_, bar_index=len(df) - 1
        )

    monkeypatch.setattr("hypervector.paper.session.last_bar_intent", scripted)


def test_declared_fixed_sizing_ignores_conviction_and_stop(tmp_path: Path) -> None:
    export = _write_strict_export(tmp_path, strategy=MANAGED_LONG)
    loadout = load_strategy_loadout(export)

    qty = _entry_qty(
        df=fixture_ohlcv(n_bars=20),
        loadout=loadout,
        exits=dict(loadout.exits or {}),
        equity=10_000.0,
        conviction=0.0,
        mark_px=50_000.0,
    )

    # 50% margin at the declared 10x: notional 50,000 = 1.0 BTC.
    assert qty == pytest.approx(1.0)


def test_standard_strategy_sizing_follows_risk_band(tmp_path: Path) -> None:
    export = _write_strict_export(tmp_path, strategy=SYNTHETIC_LONG)
    loadout = load_strategy_loadout(export)

    qty = _entry_qty(
        df=fixture_ohlcv(n_bars=20),
        loadout=loadout,
        exits=dict(loadout.exits or {}),
        equity=10_000.0,
        conviction=0.0,
        mark_px=50_000.0,
    )

    # risk_pct_min 1% over a 1% fixed_rr stop, capped at 1x equity.
    assert qty == pytest.approx(10_000.0 / 50_000.0)


def test_declared_post_only_entry_rests_then_fills_through_at_maker_fee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export = _write_strict_export(tmp_path, strategy=MANAGED_LONG)
    session = PaperSession(export_dir=export, data_root=tmp_path / "data")
    _scripted_intents(
        monkeypatch,
        [("long", True, False), ("long", False, False), ("long", False, True)],
    )
    assert session.book_gate_enabled is False

    session.on_bar(_minute_bar(0))
    assert session.on_bar(_minute_bar(1)) is None
    pending = session.pending_maker_entry
    assert pending is not None and pending.limit_price == 100.0
    assert session.engine.position.qty == 0.0

    assert session.on_bar(_minute_bar(2, low=99.0)) == "enter_long"
    assert session.pending_maker_entry is None
    assert session.engine.position.qty == pytest.approx(pending.qty)

    assert session.on_bar(_minute_bar(3)) == "close"
    assert session.engine.position.qty == 0.0

    rows = _decision_rows(session.decisions_path)
    submitted = [row for row in rows if row["action"] == "submit_entry"]
    entry = next(row for row in rows if row["action"] == "enter_long")
    close = next(row for row in rows if row["action"] == "close")
    maker_fee = session.cost_provider.snapshot().maker_fee
    assert submitted[0]["order_intent"]["time_in_force"] == "post_only"
    assert submitted[0]["order_intent"]["order_type"] == "limit"
    assert entry["fill_px"] == 100.0
    assert entry["fill_model_id"] == "post_only_limit_through_v1"
    assert entry["fee_usd"] == pytest.approx(pending.qty * 100.0 * maker_fee)
    assert entry["order_intent"]["time_in_force"] == "post_only"
    assert close["fill_model_id"] != "post_only_limit_through_v1"
    assert close["order_intent"]["time_in_force"] == "ioc"


def test_declared_post_only_entry_expires_after_its_time_to_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export = _write_strict_export(tmp_path, strategy=MANAGED_LONG)
    session = PaperSession(export_dir=export, data_root=tmp_path / "data")
    _scripted_intents(monkeypatch, [("long", True, False)] + [("long", False, False)] * 4)

    untouched = {"high": 100.5, "low": 100.0}  # never one tick through 100.0
    session.on_bar(_minute_bar(0))
    session.on_bar(_minute_bar(1))  # submitted at the 12:02 close
    session.on_bar(_minute_bar(2, **untouched))  # 60 s
    session.on_bar(_minute_bar(3, **untouched))  # 120 s = the declared TTL
    assert session.pending_maker_entry is not None
    session.on_bar(_minute_bar(4, **untouched))  # 180 s > 120 s
    assert session.pending_maker_entry is None
    assert session.engine.position.qty == 0.0

    cancels = [
        row
        for row in _decision_rows(session.decisions_path)
        if row["action"] == "cancel_entry"
    ]
    assert [row["reason"] for row in cancels] == ["entry_ttl_expired"]


def test_declared_post_only_entry_cancels_when_the_intent_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export = _write_strict_export(tmp_path, strategy=MANAGED_SHORT)
    session = PaperSession(export_dir=export, data_root=tmp_path / "data")
    _scripted_intents(monkeypatch, [("long", True, False), ("short", True, False)])

    session.on_bar(_minute_bar(0))
    session.on_bar(_minute_bar(1))
    assert session.pending_maker_entry is not None
    assert session.pending_maker_entry.direction == "long"
    session.on_bar(_minute_bar(2, high=100.0, low=99.995))

    pending = session.pending_maker_entry
    assert pending is not None and pending.direction == "short"
    rows = _decision_rows(session.decisions_path)
    assert [row["reason"] for row in rows if row["action"] == "cancel_entry"] == [
        "strategy_intent_changed"
    ]
    assert [row["side"] for row in rows if row["action"] == "submit_entry"] == [
        "buy",
        "sell",
    ]


def test_standard_strategy_enters_at_market_without_resting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export = _write_strict_export(tmp_path, strategy=SYNTHETIC_LONG)
    session = PaperSession(
        export_dir=export, data_root=tmp_path / "data", book_gate_enabled=False
    )
    _scripted_intents(monkeypatch, [("long", True, False)])

    session.on_bar(_minute_bar(0))
    assert session.on_bar(_minute_bar(1)) == "enter_long"
    assert session.pending_maker_entry is None

    entry = next(
        row
        for row in _decision_rows(session.decisions_path)
        if row["action"] == "enter_long"
    )
    assert entry["order_intent"]["time_in_force"] == "ioc"
    taker_fee = session.cost_provider.snapshot().taker_fee
    assert entry["fee_usd"] == pytest.approx(
        entry["fill_qty"] * entry["fill_px"] * taker_fee
    )


def test_identity_stamps_declared_execution_and_observe_only_models(
    tmp_path: Path,
) -> None:
    export = _write_strict_export(tmp_path, strategy=MANAGED_LONG)

    class FakeML:
        root = type("R", (), {"name": "managed-v001"})()
        feature_names = ["a"]

        def predict_probability(self, features):
            return 0.6

    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        metalabeler=FakeML(),
        metalabel_mode="filter",
    )
    session.ensure_session_identity()
    row = _decision_rows(session.decisions_path)[-1]

    # Fixed sizing is never scaled or filtered by a model.
    assert session.metalabel_mode == "observe"
    assert row["metalabel_mode"] == "observe"
    assert row["execution_profile"]["post_only_entries"] is True
    assert row["execution_profile"]["fixed_notional_fraction"] == pytest.approx(5.0)
    assert row["risk"] == {
        "mode": "fixed_margin_fraction",
        "margin_fraction": 0.5,
        "notional_fraction": 5.0,
        "leverage": 10.0,
    }
    assert row["execution"]["time_in_force"] == "post_only"
    assert row["execution"]["entry_ttl_seconds"] == 120.0
