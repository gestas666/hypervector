"""Offline paper session: warm-up + bar loop into ExplicitFillEngine (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.paper.session import (
    PaperSession,
    PaperSessionResult,
    _entry_qty,
    run_paper_session_offline,
)
from hypervector.nautilus.load_export import load_strategy_loadout


def _write_strict_export(root: Path, *, strategy: str = "crown_stack_short") -> Path:
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
            "bbwp_lookback": 100,
            "bbwp_threshold": 20.0,
            "exit_mode": "fixed_rr",
            "role": track,
        },
        metrics={
            "net_pnl": 50.0,
            "total_return_pct": 0.5,
            "sharpe": 0.4,
            "trade_count": 3,
        },
        candidate_id="paper_session_crown",
        strict=True,
    )


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
    export = _write_strict_export(tmp_path, strategy="crown_stack_long")

    class FakeML:
        root = type("R", (), {"name": "hypervelocity-long-v001"})()
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
    assert row["strategy_name"] == "crown_stack_long"
    assert row["execution_mode"] == "shadow"
    assert row["metalabel_mode"] == "observe"
    assert row["metalabel_bundle_id"] == "hypervelocity-long-v001"
    assert row["conviction"] == 0.42
    assert row["strategy_params"]["strategy"] == "crown_stack_long"
    assert row["exits"]["mode"] == "fixed_rr"
    assert row["risk"]["risk_pct_max"] == 0.05
    assert row["costs"]["slippage_bps"] == 2.0
    assert "private_key" not in json.dumps(row).lower()
    assert "wallet" not in json.dumps(row).lower()


def test_hypervelocity_identity_stamps_fixed_contract_and_observe_only(
    tmp_path: Path,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )

    class FakeML:
        root = type("R", (), {"name": "hypervelocity-replay-v002"})()
        feature_names = ["close"]

        def predict_probability(self, features):
            return 0.1

    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        metalabel_enabled=True,
        metalabeler=FakeML(),
        metalabel_mode="filter",
        book_gate_enabled=True,
    )

    session.ensure_session_identity()
    row = json.loads(session.decisions_path.read_text().splitlines()[-1])

    assert session.metalabel_mode == "observe"
    assert session.book_gate_enabled is False
    assert row["metalabel_mode"] == "observe"
    assert row["strategy_params"]["leverage"] == 40.0
    assert row["strategy_params"]["target_margin_pct"] == 8.0
    assert row["risk"] == {
        "mode": "fixed_margin_fraction",
        "margin_fraction": 0.7,
        "notional_fraction": 28.0,
    }
    assert row["exits"]["mode"] == "strategy_target_only"
    assert row["exits"]["stop"] is None
    assert row["exits"]["range_policy"] == "hold_until_target"
    assert row["execution"]["order_type"] == "limit"
    assert row["execution"]["time_in_force"] == "post_only"
    assert row["execution"]["fill_rule"] == "through_one_tick"
    assert row["execution"]["fill_model"] == "post_only_limit_through_v1"
    assert row["execution"]["price_tick_mode"] == "hyperliquid_dynamic"
    assert row["execution"]["entry_ttl_seconds"] == 300.0


def test_live_hypervelocity_bar_records_report_only_regime_observation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    bars = fixture_ohlcv(n_bars=4)

    def range_decisions(frame: pd.DataFrame, config) -> pd.DataFrame:
        del config
        return pd.DataFrame(
            {
                "primary_regime": ["RANGE"] * len(frame),
                "breakout_direction": [None] * len(frame),
            },
            index=frame.index,
        )

    monkeypatch.setattr(
        "hypervector.strategies.hypervelocity._classify_regimes",
        range_decisions,
    )
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        execution_mode="shadow",
    )
    session.warm_up(bars.iloc[:3])

    session.enable_live_telemetry()
    session.on_bar(bars.iloc[3])

    rows = [
        json.loads(line) for line in session.decisions_path.read_text().splitlines()
    ]
    observation = next(row for row in rows if row["action"] == "regime_observation")
    assert observation["run_id"] == session.run_id
    assert observation["primary_regime"] == "RANGE"
    assert observation["breakout_direction"] is None
    assert observation["entry_direction"] == "long"
    assert observation["entry_allowed"] is False
    assert observation["submitted"] is False
    assert observation["place_attempted"] is False


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


def test_hypervelocity_paper_qty_is_70pct_margin_at_40x(tmp_path: Path) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    loadout = load_strategy_loadout(export)
    bars = fixture_ohlcv(n_bars=20)

    qty = _entry_qty(
        df=bars,
        loadout=loadout,
        exits=dict(loadout.exits or {}),
        equity=10_000.0,
        conviction=0.0,
        mark_px=50_000.0,
    )

    assert qty == pytest.approx(5.6)


def test_hypervelocity_paper_waits_for_maker_through_then_exits_at_fixed_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    session = PaperSession(export_dir=export, data_root=tmp_path / "data")
    monkeypatch.setattr(
        "hypervector.paper.session.current_hypervelocity_entry_allowed",
        lambda frame, direction: True,
    )

    def bar(minute: int, *, high: float, low: float) -> dict[str, object]:
        return {
            "timestamp": pd.Timestamp(f"2026-07-25T12:{minute:02d}:00Z"),
            "open": 100.0,
            "high": high,
            "low": low,
            "close": 100.0,
            "volume": 1.0,
        }

    session.on_bar(bar(0, high=100.5, low=99.5))
    session.on_bar(bar(1, high=100.5, low=99.5))

    assert session.engine.position.qty == 0.0
    assert session.pending_maker_entry is not None
    assert session.pending_maker_entry.limit_price == 100.0

    assert session.on_bar(bar(2, high=100.5, low=99.0)) == "enter_long"
    assert session.engine.position.qty == pytest.approx(2800.0)
    assert session.engine.position.avg_px == 100.0

    assert session.on_bar(bar(3, high=101.21, low=100.0)) == "close"
    assert session.engine.position.qty == 0.0

    rows = [
        json.loads(line)
        for line in session.decisions_path.read_text().splitlines()
        if line.strip()
    ]
    submitted = [row for row in rows if row["action"] == "submit_entry"]
    entries = [row for row in rows if row["action"] == "enter_long"]
    closes = [row for row in rows if row["action"] == "close"]
    assert submitted[0]["order_intent"]["time_in_force"] == "post_only"
    assert submitted[0]["feed_ts"] == "2026-07-25T12:02:00+00:00"
    assert entries[0]["fill_px"] == 100.0
    assert entries[0]["feed_ts"] == "2026-07-25T12:03:00+00:00"
    assert entries[0]["fill_model_id"] == "post_only_limit_through_v1"
    assert closes[0]["fill_px"] == pytest.approx(100.2)
    assert closes[0]["feed_ts"] == "2026-07-25T12:04:00+00:00"


def test_bidirectional_profile_holds_then_switches_only_after_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One signed BTC position cannot reverse until its target closes."""
    from types import SimpleNamespace

    from hypervector.strategies.hypervelocity_profile import (
        load_hypervelocity_profile,
    )

    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    profile_text = Path("configs/hypervelocity_faithful.toml").read_text()
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        profile_text.replace(
            "data/exports/uptrend_hypervelocity_1m_scalper_long_784548f1",
            str(export),
        ),
        encoding="utf-8",
    )
    profile = load_hypervelocity_profile(profile_path)
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        hypervelocity_profile=profile,
    )
    directions = iter(("long", "long", "short", "short"))

    def market(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(entry_direction=next(directions))

    monkeypatch.setattr("hypervector.paper.session.current_hypervelocity_market", market)

    def bar(minute: int, *, high: float, low: float) -> dict[str, object]:
        return {
            "timestamp": pd.Timestamp(f"2026-07-25T13:{minute:02d}:00Z"),
            "open": 100.0,
            "high": high,
            "low": low,
            "close": 100.0,
            "volume": 1.0,
        }

    session.on_bar(bar(0, high=100.0, low=100.0))
    session.on_bar(bar(1, high=100.0, low=100.0))
    assert session.on_bar(bar(2, high=100.0, low=99.9)) == "enter_long"
    long_qty = session.engine.position.qty
    assert long_qty > 0.0

    assert session.on_bar(bar(3, high=100.1, low=99.9)) is None
    assert session.engine.position.qty == long_qty
    assert session.on_bar(bar(4, high=100.3, low=99.9)) == "close"
    assert session.engine.position.qty == 0.0

    session.on_bar(bar(5, high=100.0, low=100.0))
    assert session.on_bar(bar(6, high=100.1, low=100.0)) == "enter_short"
    assert session.engine.position.qty < 0.0


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
