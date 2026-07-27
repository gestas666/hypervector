"""Offline paper session: warm-up + bar loop into ExplicitFillEngine (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from hypervector.data.hl_events import BookLevel as EventBookLevel
from hypervector.data.hl_events import (
    AssetContextEvent,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.nautilus.hypervelocity_sim import HypervelocitySimulationConfig
from hypervector.paper.hypervelocity_shadow_controller import (
    HypervelocityShadowController,
)
from hypervector.paper.nautilus_shadow import NautilusShadowExecutionPort
from hypervector.paper.session import (
    PaperSession,
    PaperSessionResult,
    _entry_qty,
    run_paper_session_offline,
)
from hypervector.paper.maker_execution import PostOnlyLimitFillModel
from hypervector.paper.resume import ShadowResumeError
from hypervector.nautilus.load_export import load_strategy_loadout
from hypervector.strategies.hypervelocity_runtime import RuntimeMarketState
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile
from hypervector.paper.conviction import ConvictionResult


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


def _hl_bar(
    timestamp: str,
    *,
    high: float,
    low: float,
) -> dict[str, object]:
    """Build one venue-identified completed bar for restart tests."""
    return {
        "timestamp": pd.Timestamp(timestamp),
        "open": 100.0,
        "high": high,
        "low": low,
        "close": 100.0,
        "volume": 1.0,
        "source": "hl",
    }


def _decision_rows(path: Path) -> list[dict[str, object]]:
    """Read the append-only test ledger."""
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class _EventAnnotationProvider:
    @property
    def bundle_id(self) -> str:
        return "event-observe-bundle"

    def resolve(self, **_kwargs: object) -> ConvictionResult:
        return ConvictionResult(
            conviction=0.5,
            source="metalabel_observe",
            metalabel_p=0.73,
            metalabel_bundle_id=self.bundle_id,
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


def test_hypervelocity_shadow_session_resumes_latest_filled_run(
    tmp_path: Path,
) -> None:
    """Normal restart preserves the shadow portfolio until explicit reset."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    first = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="persistent-run",
        execution_mode="shadow",
    )
    first.ensure_session_identity()
    entry = first.engine.apply_market_fill(
        feed_ts="2026-07-25T18:05:00Z",
        action="enter_long",
        side="buy",
        qty=2.0,
        mark_px=100.0,
    )

    resumed = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="discarded-new-run",
        execution_mode="shadow",
    )

    assert resumed.run_id == "persistent-run"
    assert resumed.engine.position.qty == pytest.approx(2.0)
    assert resumed.engine.position.avg_px == pytest.approx(entry["position_avg_px"])
    assert resumed.engine.position.realized_pnl == pytest.approx(entry["realized_pnl"])

    resumed.ensure_session_identity()
    latest = json.loads(resumed.decisions_path.read_text().splitlines()[-1])
    assert latest["run_id"] == "persistent-run"
    assert latest["position_qty"] == pytest.approx(2.0)
    assert latest["position_avg_px"] == pytest.approx(entry["position_avg_px"])
    assert latest["realized_pnl"] == pytest.approx(entry["realized_pnl"])
    assert latest["resumed_shadow_portfolio"] is True


def test_hypervelocity_shadow_session_without_fills_starts_new_run(
    tmp_path: Path,
) -> None:
    """Empty prior launches do not become persistent portfolio epochs."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    abandoned = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="empty-run",
        execution_mode="shadow",
    )
    abandoned.ensure_session_identity()

    fresh = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="fresh-run",
        execution_mode="shadow",
    )

    assert fresh.run_id == "fresh-run"
    assert fresh.engine.position.qty == 0.0


def test_hypervelocity_open_position_rejects_incompatible_profile(
    tmp_path: Path,
) -> None:
    """An open portfolio cannot silently switch execution specifications."""
    long_export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=long_export,
        data_root=data_root,
        run_id="persistent-run",
        execution_mode="shadow",
    )
    original.ensure_session_identity()
    original.engine.apply_market_fill(
        feed_ts="2026-07-25T18:05:00Z",
        action="enter_long",
        side="buy",
        qty=2.0,
        mark_px=100.0,
    )
    short_export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_short",
    )

    with pytest.raises(ShadowResumeError, match="incompatible.*open position"):
        PaperSession(
            export_dir=short_export,
            data_root=data_root,
            execution_mode="shadow",
        )


def test_hypervelocity_flat_portfolio_records_compatible_profile_change(
    tmp_path: Path,
) -> None:
    """A flat portfolio keeps its PnL while explicitly changing profile identity."""
    long_export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=long_export,
        data_root=data_root,
        run_id="persistent-run",
        execution_mode="shadow",
    )
    original.ensure_session_identity()
    original.engine.apply_market_fill(
        feed_ts="2026-07-25T18:05:00Z",
        action="enter_long",
        side="buy",
        qty=2.0,
        mark_px=100.0,
    )
    close = original.engine.apply_market_fill(
        feed_ts="2026-07-25T18:10:00Z",
        action="close",
        side="sell",
        qty=2.0,
        mark_px=101.0,
    )
    short_export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_short",
    )

    changed = PaperSession(
        export_dir=short_export,
        data_root=data_root,
        execution_mode="shadow",
    )
    changed.ensure_session_identity()
    identity = json.loads(changed.decisions_path.read_text().splitlines()[-1])

    assert changed.run_id == "persistent-run"
    assert changed.engine.position.qty == 0.0
    assert changed.engine.position.realized_pnl == pytest.approx(close["realized_pnl"])
    assert identity["portfolio_profile_changed_from"]
    assert identity["portfolio_fingerprint"]


def test_repeated_resume_preserves_market_state_timestamp(tmp_path: Path) -> None:
    """A synthetic session_start never replaces the last market as-of timestamp."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="persistent-run",
        execution_mode="shadow",
    )
    original.ensure_session_identity()
    original.engine.apply_market_fill(
        feed_ts="2026-07-25T18:05:00Z",
        action="enter_long",
        side="buy",
        qty=2.0,
        mark_px=100.0,
    )
    second = PaperSession(
        export_dir=export,
        data_root=data_root,
        execution_mode="shadow",
    )
    second.ensure_session_identity()

    third = PaperSession(
        export_dir=export,
        data_root=data_root,
        execution_mode="shadow",
    )

    assert third._shadow_resume is not None
    assert third._shadow_resume.state_asof == "2026-07-25T18:05:00Z"


def test_hypervelocity_session_restores_pending_maker_entry(tmp_path: Path) -> None:
    """The backend restores the exact unmatched post-only order state."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="pending-run",
        execution_mode="shadow",
    )
    original.ensure_session_identity()
    original.engine.record_order_event(
        feed_ts="2026-07-25T18:05:00Z",
        action="submit_entry",
        side="buy",
        qty=2.0,
        limit_px=100.0,
        status="pending",
        conviction=0.75,
        conviction_source="fixed",
        metalabel_p=0.62,
        metalabel_bundle_id="bundle-long",
    )

    resumed = PaperSession(
        export_dir=export,
        data_root=data_root,
        execution_mode="shadow",
    )
    pending = resumed.pending_maker_entry

    assert resumed.run_id == "pending-run"
    assert pending is not None
    assert pending.direction == "long"
    assert pending.qty == 2.0
    assert pending.limit_price == 100.0
    assert pending.submitted_at == pd.Timestamp("2026-07-25T18:05:00Z")
    assert pending.metalabel_p == 0.62
    assert pending.metalabel_bundle_id == "bundle-long"


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
    assert row["execution"]["expired_entry_rearm_policy"] == "regime_reset"


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
                "state_1m": ["RANGE"] * len(frame),
                "state_5m": ["RANGE"] * len(frame),
                "context_15m": ["TREND_UP"] * len(frame),
                "confidence": [0.61] * len(frame),
                "reason": ["5m_primary_state"] * len(frame),
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
    execution = next(
        row for row in rows if row["action"] == "entry_execution_observation"
    )
    assert observation["run_id"] == session.run_id
    assert observation["primary_regime"] == "RANGE"
    assert observation["breakout_direction"] is None
    assert observation["entry_direction"] == "long"
    assert observation["entry_allowed"] is False
    assert execution["maker_entry_state"] == "standby"
    assert execution["maker_entry_direction"] is None
    assert execution["entry_retry_state"] == "ready"
    assert execution["entry_cooldown_active"] is False
    assert observation["state_1m"] == "RANGE"
    assert observation["state_5m"] == "RANGE"
    assert observation["context_15m"] == "TREND_UP"
    assert observation["confidence"] == pytest.approx(0.61)
    assert observation["regime_strength_score"] == pytest.approx(0.61)
    assert observation["regime_score_source"] == "legacy_confidence_alias"
    assert observation["regime_reason"] == "5m_primary_state"
    assert observation["high"] == pytest.approx(float(bars.iloc[3]["high"]))
    assert observation["low"] == pytest.approx(float(bars.iloc[3]["low"]))
    assert observation["volume"] == pytest.approx(float(bars.iloc[3]["volume"]))
    assert "rsi" in observation
    assert "bbwp_percentile" in observation
    assert observation["submitted"] is False
    assert observation["place_attempted"] is False
    assert observation["position_qty"] == 0.0
    assert observation["position_avg_px"] == 0.0
    assert observation["realized_pnl"] == 0.0
    assert observation["unrealized_pnl"] == 0.0
    assert observation["equity"] == pytest.approx(10_000.0)


def test_live_book_refresh_records_authoritative_microstructure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backend L2 refresh produces the record consumed by the TUI."""
    from hypervector.paper.book import BookLevel, BookSnapshot
    from hypervector.strategies.hypervelocity_profile import (
        load_hypervelocity_profile,
    )

    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    profile = load_hypervelocity_profile("configs/hypervelocity_faithful.toml")
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        execution_mode="shadow",
        enable_book_poll=True,
        hypervelocity_profile=profile,
    )
    snapshot = BookSnapshot(
        symbol="BTC",
        bids=(BookLevel(100.0, 3.0), BookLevel(99.5, 1.0)),
        asks=(BookLevel(100.5, 1.0), BookLevel(101.0, 1.0)),
        ts_recv_ms=2_000.0,
        ts_exchange_ms=1_900.0,
        source="fixture_l2",
    )
    monkeypatch.setattr(session.book_feed, "poll", lambda: snapshot)
    session.enable_live_telemetry()

    observed = session.refresh_book_telemetry()

    assert observed is snapshot
    rows = [
        json.loads(line) for line in session.decisions_path.read_text().splitlines()
    ]
    telemetry = next(row for row in rows if row["action"] == "book_observation")
    assert telemetry["source"] == "fixture_l2"
    assert telemetry["mid_px"] == pytest.approx(100.25)
    assert telemetry["spread_bps"] == pytest.approx(49.87531172)
    assert telemetry["bid_depth_ratio"] == pytest.approx(2.0)
    assert telemetry["opi"] == pytest.approx(1.0 / 3.0)
    assert telemetry["bids"][0] == {"price": 100.0, "size": 3.0}
    assert telemetry["asks"][0] == {"price": 100.5, "size": 1.0}
    assert telemetry["submitted"] is False
    assert telemetry["place_attempted"] is False
    archives = list((tmp_path / "data" / "cache" / "book").glob("BTC_l2_*.jsonl"))
    assert len(archives) == 1
    archived = json.loads(archives[0].read_text(encoding="utf-8").strip())
    assert archived["run_id"] == session.run_id
    assert archived["bids"][0] == {"px": 100.0, "sz": 3.0}


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


def test_event_shadow_session_ledgers_partial_fill_and_proportional_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        execution_mode="shadow",
        funding_rate_hourly=0.001,
        conviction_provider=_EventAnnotationProvider(),
    )
    port = NautilusShadowExecutionPort(
        symbol="BTC",
        initial_cash_usd=10_000.0,
        simulation_config=HypervelocitySimulationConfig(
            submit_latency_ms=0,
            cancel_latency_ms=50,
            update_latency_ms=0,
        ),
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
        leverage=40.0,
        maintenance_rate=0.0125,
        max_event_age_ms=3_000,
    )
    neutral = RuntimeMarketState(
        symbol="BTC",
        observed_at="2026-07-26T20:00:00+00:00",
        entry_direction=None,
        entry_quantity=1.0,
        entry_limit_price=None,
        evidence_fresh=False,
        entry_ttl_seconds=300.0,
        reentry_cooldown_seconds=60.0,
        target_price_fraction=0.002,
        price_tick=1.0,
    )
    session.attach_hypervelocity_event_controller(
        HypervelocityShadowController(port=port, initial_market=neutral)
    )
    session.enable_live_telemetry()
    monkeypatch.setattr(
        "hypervector.paper.session.current_hypervelocity_entry_allowed",
        lambda _frame, direction: direction == "long",
    )
    base_ms = int(pd.Timestamp("2026-07-26T20:02:01Z").timestamp() * 1_000)
    session.ingest_hyperliquid_event(
        L2SnapshotEvent(
            symbol="BTC",
            exchange_ts_ms=base_ms,
            received_ts_ns=(base_ms + 1) * 1_000_000,
            bids=(EventBookLevel(64_500.0, 0.001, 1),),
            asks=(EventBookLevel(64_501.0, 0.5, 1),),
        )
    )

    def bar(minute: int) -> dict[str, object]:
        return {
            "timestamp": pd.Timestamp(f"2026-07-26T20:{minute:02d}:00Z"),
            "open": 64_500.0,
            "high": 64_501.0,
            "low": 64_499.0,
            "close": 64_500.0,
            "volume": 1.0,
        }

    session.on_bar(bar(0))
    session.on_bar(bar(1))
    assert session.pending_maker_entry is not None
    session.ingest_hyperliquid_event(
        L2SnapshotEvent(
            symbol="BTC",
            exchange_ts_ms=base_ms + 60_001,
            received_ts_ns=(base_ms + 60_002) * 1_000_000,
            bids=(EventBookLevel(64_500.0, 0.001, 1),),
            asks=(EventBookLevel(64_501.0, 0.5, 1),),
        )
    )
    session.ingest_hyperliquid_event(
        PublicTradeEvent(
            symbol="BTC",
            aggressor_side="sell",
            price=64_500.0,
            size=1.001,
            transaction_hash="0xpartial",
            exchange_ts_ms=base_ms + 60_002,
            received_ts_ns=(base_ms + 60_003) * 1_000_000,
            trade_id=99,
            buyer="0xbuyer",
            seller="0xseller",
        )
    )

    assert session.engine.position.qty == pytest.approx(1.0)
    rows = _decision_rows(session.decisions_path)
    entry = next(row for row in rows if row.get("action") == "enter_long")
    target = next(row for row in rows if row.get("action") == "submit_target")
    assert entry["execution_model"] == "nautilus_event_v1"
    assert entry["liquidity_side"] == "maker"
    assert entry["cumulative_filled_qty"] == pytest.approx(1.0)
    assert entry["execution_requested_qty"] > entry["cumulative_filled_qty"]
    assert entry["conviction_source"] == "metalabel_observe"
    assert entry["metalabel_p"] == pytest.approx(0.73)
    assert entry["metalabel_bundle_id"] == "event-observe-bundle"
    assert entry["liquidation_price"] == pytest.approx(port.liquidation_price)
    assert target["requested_qty"] == pytest.approx(1.0)
    assert target["execution_model"] == "nautilus_event_v1"

    marked_ms = base_ms + 60_003
    session.ingest_hyperliquid_event(
        L2SnapshotEvent(
            symbol="BTC",
            exchange_ts_ms=marked_ms,
            received_ts_ns=(marked_ms + 1) * 1_000_000,
            bids=(EventBookLevel(64_400.0, 1.0, 1),),
            asks=(EventBookLevel(64_401.0, 1.0, 1),),
        )
    )
    session.ingest_hyperliquid_event(
        StreamGap(
            symbol="BTC",
            channel="l2Book,trades",
            detected_ts_ns=(marked_ms + 1) * 1_000_000,
            reason="test_disconnect",
            previous_exchange_ts_ms=marked_ms,
            next_exchange_ts_ms=marked_ms + 2,
        )
    )
    uncertain = next(
        row
        for row in reversed(_decision_rows(session.decisions_path))
        if row.get("action") == "execution_evidence_uncertain"
    )
    marked_equity = port.account_snapshot().equity_usd
    realized_equity = session.engine.initial_cash + session.engine.position.realized_pnl
    assert uncertain["unrealized_pnl"] == pytest.approx(marked_equity - realized_equity)
    assert uncertain["unrealized_pnl"] < 0.0
    assert uncertain["equity"] == pytest.approx(marked_equity)

    session.on_bar(bar(59))
    assert port.funding_net_usd == pytest.approx(-64.5)
    rows = _decision_rows(session.decisions_path)
    funding_rows = [row for row in rows if row.get("action") == "funding"]
    assert len(funding_rows) == 1
    assert funding_rows[0]["execution_model"] == "nautilus_event_v1"
    assert funding_rows[0]["liquidation_price"] == pytest.approx(port.liquidation_price)
    regime_rows = [row for row in rows if row.get("action") == "regime_observation"]
    assert regime_rows[-1]["liquidation_price"] == pytest.approx(port.liquidation_price)

    liquidation_price = port.liquidation_price
    assert liquidation_price is not None
    execution_mark = liquidation_price - 0.01
    mark_ms = int(pd.Timestamp("2026-07-26T21:00:00.999Z").timestamp() * 1_000)
    session.ingest_hyperliquid_event(
        L2SnapshotEvent(
            symbol="BTC",
            exchange_ts_ms=mark_ms,
            received_ts_ns=mark_ms * 1_000_000,
            bids=(EventBookLevel(execution_mark, 1.0, 1),),
            asks=(EventBookLevel(execution_mark + 1.0, 1.0, 1),),
        )
    )
    action = session.apply_hyperliquid_mark(
        mark_price=execution_mark,
        observed_at="2026-07-26T21:00:01+00:00",
    )
    assert action == "liquidation"
    assert session.engine.position.qty == 0.0
    assert port.account_snapshot().position_quantity == 0.0
    assert port.account_snapshot().equity_usd == pytest.approx(
        session.engine.equity(mark_px=execution_mark)
    )
    rows = _decision_rows(session.decisions_path)
    liquidation = next(row for row in rows if row.get("action") == "liquidation")
    assert liquidation["execution_model"] == "nautilus_event_v1"
    assert liquidation["fee_usd"] == pytest.approx(execution_mark * 0.00045)
    assert liquidation["clearance_fee_usd"] == 0.0
    assert (
        liquidation["liquidation_execution_model"]
        == "hyperliquid_market_liquidation_v2"
    )
    assert liquidation["fill_model_id"] == "liquidation_l2_vwap_v2"
    assert liquidation["order_intent"]["reduce_only"] is True
    assert liquidation["order_intent"]["order_type"] == "market"
    assert liquidation["order_intent"]["time_in_force"] == "ioc"
    assert liquidation["order_intent"]["limit_px"] is None


def test_profile_activates_event_runtime_and_stamps_authority(tmp_path: Path) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    profile = load_hypervelocity_profile("configs/hypervelocity_faithful.toml")
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        execution_mode="shadow",
        hypervelocity_profile=profile,
    )

    controller = session.activate_hypervelocity_event_runtime(
        observed_at="2026-07-26T20:00:00+00:00"
    )
    session.ensure_session_identity()

    assert controller.port.execution_records() == ()
    assert session.downtime_reconciliation_enabled is False
    identity = _decision_rows(session.decisions_path)[-1]
    assert identity["execution_model"] == "nautilus_event_v1"
    assert (
        identity["execution_data_source"]
        == "hyperliquid_public_ws_l2_trades_active_asset_ctx"
    )
    assert identity["execution_evidence_fresh"] is False
    assert identity["execution_submit_latency_ms"] == 50
    assert identity["execution_cancel_latency_ms"] == 50
    assert identity["execution_update_latency_ms"] == 50
    assert identity["execution_queue_ahead_qty"] is None
    assert identity["execution_requested_qty"] is None
    assert identity["cumulative_filled_qty"] is None
    assert identity["remaining_qty"] is None
    assert identity["liquidity_side"] is None
    assert identity["margin_model"] == "hyperliquid_isolated_v1"
    assert identity["liquidation_price"] is None
    assert (
        identity["liquidation_execution_model"] == "hyperliquid_market_liquidation_v2"
    )
    assert identity["partial_liquidation_supported"] is True
    assert identity["backstop_liquidation_supported"] is True
    assert identity["regime_policy"] == {
        "execution_timeframe": "1m",
        "primary_timeframe": "5m",
        "context_timeframe": "15m",
        "context_is_hard_gate": False,
        "allowed_entry_states": ["TREND_UP", "TREND_DOWN", "BREAKOUT"],
        "blocked_entry_states": ["RANGE", "TRANSITION", "UNKNOWN"],
        "breakout_requires_direction": True,
        "confidence_is_gate": False,
    }
    assert identity["portfolio_spec"]["regime_policy"] == identity["regime_policy"]
    assert identity["execution"]["fill_model"] == "nautilus_event_v1"
    assert (
        identity["execution"]["restart_queue_policy"]
        == "requeue_behind_displayed_liquidity"
    )
    assert identity["execution"]["partial_liquidation_threshold_usd"] == 100_000.0
    assert identity["execution"]["partial_liquidation_fraction"] == 0.20
    assert identity["execution"]["liquidation_cooldown_ms"] == 30_000
    assert identity["execution"]["backstop_liquidation_supported"] is True
    assert identity["execution"]["backstop_maintenance_fraction"] == pytest.approx(
        2.0 / 3.0
    )
    assert identity["execution"]["legacy_comparator"] == "legacy_bar_through_v1"


def test_event_shadow_backstop_transfer_preserves_ledger_parity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        execution_mode="shadow",
    )
    port = NautilusShadowExecutionPort(
        symbol="BTC",
        initial_cash_usd=10_000.0,
        simulation_config=HypervelocitySimulationConfig(
            submit_latency_ms=0,
            cancel_latency_ms=50,
            update_latency_ms=0,
        ),
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
        leverage=40.0,
        maintenance_rate=0.0125,
        max_event_age_ms=3_000,
    )
    neutral = RuntimeMarketState(
        symbol="BTC",
        observed_at="2026-07-26T20:00:00+00:00",
        entry_direction=None,
        entry_quantity=1.0,
        entry_limit_price=None,
        evidence_fresh=False,
        entry_ttl_seconds=300.0,
        reentry_cooldown_seconds=60.0,
        target_price_fraction=0.002,
        price_tick=1.0,
    )
    session.attach_hypervelocity_event_controller(
        HypervelocityShadowController(port=port, initial_market=neutral)
    )
    monkeypatch.setattr(
        "hypervector.paper.session.current_hypervelocity_entry_allowed",
        lambda _frame, direction: direction == "long",
    )
    base_ms = int(pd.Timestamp("2026-07-26T20:02:01Z").timestamp() * 1_000)
    session.ingest_hyperliquid_event(
        L2SnapshotEvent(
            symbol="BTC",
            exchange_ts_ms=base_ms,
            received_ts_ns=(base_ms + 1) * 1_000_000,
            bids=(EventBookLevel(64_500.0, 0.001, 1),),
            asks=(EventBookLevel(64_501.0, 1.0, 1),),
        )
    )

    def trend_bar(minute: int) -> dict[str, object]:
        return {
            "timestamp": pd.Timestamp(f"2026-07-26T20:{minute:02d}:00Z"),
            "open": 64_500.0,
            "high": 64_501.0,
            "low": 64_499.0,
            "close": 64_500.0,
            "volume": 1.0,
        }

    session.on_bar(trend_bar(0))
    session.on_bar(trend_bar(1))
    pending = session.pending_maker_entry
    assert pending is not None
    assert pending.qty * pending.limit_price > 100_000.0
    session.ingest_hyperliquid_event(
        L2SnapshotEvent(
            symbol="BTC",
            exchange_ts_ms=base_ms + 60_001,
            received_ts_ns=(base_ms + 60_002) * 1_000_000,
            bids=(EventBookLevel(64_500.0, 0.001, 1),),
            asks=(EventBookLevel(64_501.0, 1.0, 1),),
        )
    )
    session.ingest_hyperliquid_event(
        PublicTradeEvent(
            symbol="BTC",
            aggressor_side="sell",
            price=64_500.0,
            size=pending.qty + 0.001,
            transaction_hash="0xbackstop",
            exchange_ts_ms=base_ms + 60_002,
            received_ts_ns=(base_ms + 60_003) * 1_000_000,
            trade_id=100,
            buyer="0xbuyer",
            seller="0xseller",
        )
    )
    boundary = port.liquidation_price
    assert boundary is not None
    deep_mark = boundary - 500.0
    mark_ms = int(pd.Timestamp("2026-07-26T20:03:01.999Z").timestamp() * 1_000)
    session.ingest_hyperliquid_event(
        L2SnapshotEvent(
            symbol="BTC",
            exchange_ts_ms=mark_ms,
            received_ts_ns=mark_ms * 1_000_000,
            bids=(EventBookLevel(deep_mark, 0.01, 1),),
            asks=(EventBookLevel(deep_mark + 1.0, 1.0, 1),),
        )
    )

    action = session.apply_hyperliquid_mark(
        mark_price=deep_mark,
        observed_at="2026-07-26T20:03:02+00:00",
    )

    assert action == "backstop_liquidation"
    assert port.account_snapshot().position_quantity == 0.0
    assert session.engine.position.qty == 0.0
    assert port.account_snapshot().equity_usd == pytest.approx(
        session.engine.equity(mark_px=deep_mark)
    )
    row = next(
        item
        for item in _decision_rows(session.decisions_path)
        if item.get("action") == "backstop_liquidation"
    )
    assert row["liquidation_method"] == "backstop"
    assert row["liquidation_market_filled_qty"] == pytest.approx(0.01)
    assert row["liquidation_backstop_qty"] > 0.0
    assert row["order_intent"]["order_type"] == "backstop_transfer"


def test_asset_context_updates_funding_and_continuous_mark_without_fill(
    tmp_path: Path,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    profile = load_hypervelocity_profile("configs/hypervelocity_faithful.toml")
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        execution_mode="shadow",
        hypervelocity_profile=profile,
    )
    controller = session.activate_hypervelocity_event_runtime(
        observed_at="2026-07-26T20:00:00+00:00"
    )
    context = AssetContextEvent(
        symbol="BTC",
        observed_ts_ms=1_785_103_200_500,
        received_ts_ns=1_785_103_200_500_000_000,
        mark_price=64_501.0,
        oracle_price=64_502.0,
        funding_rate_hourly=0.0000125,
        open_interest=36_000.0,
        mid_price=64_500.5,
    )

    action = session.ingest_hyperliquid_event(context)

    snapshot = session.cost_provider.snapshot()
    expected_at = pd.Timestamp(context.received_ts_ns, unit="ns", tz="UTC").isoformat()
    assert action is None
    assert snapshot.funding_rate_hourly == pytest.approx(0.0000125)
    assert snapshot.oracle_px == pytest.approx(64_502.0)
    assert snapshot.asof_ts == expected_at
    assert controller.port.account_snapshot().observed_at == expected_at
    assert session.fills_count == 0


def test_event_runtime_applies_boundary_funding_before_liquidation_mark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    session = PaperSession(export_dir=export, data_root=tmp_path / "data")
    session._event_shadow_bridge = Mock()
    calls: list[str] = []
    monkeypatch.setattr(
        session,
        "_apply_hourly_funding",
        lambda _record: calls.append("funding"),
    )
    monkeypatch.setattr(
        session,
        "_apply_event_mark",
        lambda _record: calls.append("mark"),
    )

    session.on_bar(_hl_bar("2026-07-26T20:59:00Z", high=100.1, low=99.9))

    assert calls == ["funding", "mark"]


def test_event_restart_reconciles_funding_without_candle_fills(tmp_path: Path) -> None:
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
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=export,
        data_root=data_root,
        execution_mode="shadow",
        hypervelocity_profile=profile,
    )
    original.ensure_session_identity()
    original.engine.apply_market_fill(
        feed_ts="2026-07-26T20:58:00Z",
        action="enter_long",
        side="buy",
        qty=1.0,
        mark_px=100.0,
        fill_model=PostOnlyLimitFillModel(),
    )
    resumed = PaperSession(
        export_dir=export,
        data_root=data_root,
        execution_mode="shadow",
        hypervelocity_profile=profile,
    )
    resumed.activate_hypervelocity_event_runtime(
        observed_at="2026-07-26T21:00:30+00:00"
    )
    frame = pd.DataFrame([_hl_bar("2026-07-26T20:59:00Z", high=500.0, low=1.0)])

    count = resumed.reconcile_event_downtime_funding(
        frame,
        funding_rates={pd.Timestamp("2026-07-26T21:00:00Z"): 0.001},
    )

    assert count == 1
    assert resumed.engine.position.qty == pytest.approx(1.0)
    rows = _decision_rows(resumed.decisions_path)
    funding = [row for row in rows if row.get("action") == "funding"][-1]
    assert funding["funding_payment_usd"] == pytest.approx(0.1)
    assert funding["execution_model"] == "nautilus_event_v1"


def test_hypervelocity_paper_waits_for_maker_through_then_exits_at_fixed_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    session = PaperSession(export_dir=export, data_root=tmp_path / "data")
    session.enable_live_telemetry()
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
    assert closes[0]["exit_reason"] == "take_profit_8pct_margin"
    execution = [row for row in rows if row["action"] == "entry_execution_observation"]
    assert execution[-1]["maker_entry_state"] == "standby"
    assert execution[-1]["entry_cooldown_active"] is False


def test_completed_hypervelocity_trade_requires_regime_reset_before_same_side_reentry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed long consumes that directional episode until it resets."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    session = PaperSession(export_dir=export, data_root=tmp_path / "data")
    session.enable_live_telemetry()
    state = {"eligible": True}

    monkeypatch.setattr(
        "hypervector.paper.session.current_hypervelocity_entry_allowed",
        lambda _frame, direction: state["eligible"],
    )

    def bar(
        minute: int, *, high: float = 100.0, low: float = 99.9
    ) -> dict[str, object]:
        return {
            "timestamp": pd.Timestamp(f"2026-07-25T12:{minute:02d}:00Z"),
            "open": 100.0,
            "high": high,
            "low": low,
            "close": 100.0,
            "volume": 1.0,
        }

    session.on_bar(bar(0))
    session.on_bar(bar(1))
    assert session.on_bar(bar(2, low=99.0)) == "enter_long"
    assert session.on_bar(bar(3, high=100.3)) == "close"

    session.on_bar(bar(4))
    assert session.pending_maker_entry is None
    blocked = session._hypervelocity_entry_execution_payload(bar(4))
    assert blocked["entry_retry_state"] == "awaiting_regime_reset_long"

    state["eligible"] = False
    session.on_bar(bar(5))
    state["eligible"] = True
    session.on_bar(bar(6))
    assert session.pending_maker_entry is not None
    assert session.pending_maker_entry.direction == "long"


def test_expired_hypervelocity_entry_waits_for_regime_reset_before_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unfilled maker attempt cannot chase one uninterrupted trend."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_short",
    )
    session = PaperSession(export_dir=export, data_root=tmp_path / "data")
    session.enable_live_telemetry()
    state = {"eligible": True}

    def entry_allowed(_frame: pd.DataFrame, direction: str) -> bool:
        assert direction == "short"
        return state["eligible"]

    monkeypatch.setattr(
        "hypervector.paper.session.current_hypervelocity_entry_allowed",
        entry_allowed,
    )

    def falling_bar(minute: int) -> dict[str, object]:
        close = 100.0 - float(minute)
        return {
            "timestamp": pd.Timestamp(f"2026-07-25T12:{minute:02d}:00Z"),
            "open": close,
            "high": close,
            "low": close - 0.05,
            "close": close,
            "volume": 1.0,
        }

    for minute in range(8):
        session.on_bar(falling_bar(minute))

    rows = _decision_rows(session.decisions_path)
    submissions = [row for row in rows if row.get("action") == "submit_entry"]
    assert len(submissions) == 1
    assert session.pending_maker_entry is None
    execution = [
        row for row in rows if row.get("action") == "entry_execution_observation"
    ]
    assert execution[-1]["entry_retry_state"] == "blocked_short"

    state["eligible"] = False
    session.on_bar(falling_bar(8))
    state["eligible"] = True
    session.on_bar(falling_bar(9))

    rows = _decision_rows(session.decisions_path)
    submissions = [row for row in rows if row.get("action") == "submit_entry"]
    assert len(submissions) == 2
    assert submissions[-1]["fill_px"] == pytest.approx(91.0)
    execution = [
        row for row in rows if row.get("action") == "entry_execution_observation"
    ]
    assert execution[-1]["entry_retry_state"] == "ready"
    assert execution[-1]["maker_entry_state"] == "pending"


def test_downtime_reconciliation_manages_open_target_and_historical_funding(
    tmp_path: Path,
) -> None:
    """Missed HL bars fund and close existing state without current-rate leakage."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="resume-open",
        execution_mode="shadow",
    )
    original.ensure_session_identity()
    original.engine.apply_market_fill(
        feed_ts="2026-07-25T12:58:00Z",
        action="enter_long",
        side="buy",
        qty=1.0,
        mark_px=100.0,
        fill_model=PostOnlyLimitFillModel(),
    )
    resumed = PaperSession(
        export_dir=export,
        data_root=data_root,
        execution_mode="shadow",
    )
    missed = pd.DataFrame(
        [
            _hl_bar("2026-07-25T12:58:00Z", high=100.1, low=99.9),
            _hl_bar("2026-07-25T12:59:00Z", high=100.1, low=99.9),
            _hl_bar("2026-07-25T13:00:00Z", high=100.3, low=99.9),
        ]
    )

    count = resumed.reconcile_downtime(
        missed,
        funding_rates={pd.Timestamp("2026-07-25T13:00:00Z"): 0.001},
    )

    assert count == 3
    assert resumed.engine.position.qty == 0.0
    rows = _decision_rows(resumed.decisions_path)
    funding = [row for row in rows if row.get("action") == "funding"]
    closes = [row for row in rows if row.get("action") == "close"]
    assert funding[-1]["funding_rate_hourly"] == 0.001
    assert closes[-1]["feed_ts"] == "2026-07-25T13:01:00+00:00"


def test_downtime_reconciliation_rejects_non_hl_bars(tmp_path: Path) -> None:
    """An active target is not reconciled against another venue's candles."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="resume-open",
        execution_mode="shadow",
    )
    original.ensure_session_identity()
    original.engine.apply_market_fill(
        feed_ts="2026-07-25T12:58:00Z",
        action="enter_long",
        side="buy",
        qty=1.0,
        mark_px=100.0,
        fill_model=PostOnlyLimitFillModel(),
    )
    resumed = PaperSession(
        export_dir=export,
        data_root=data_root,
        execution_mode="shadow",
    )
    missed = pd.DataFrame(
        [{**_hl_bar("2026-07-25T12:59:00Z", high=100.1, low=99.9), "source": "binance"}]
    )

    with pytest.raises(RuntimeError, match="Hyperliquid bars"):
        resumed.reconcile_downtime(missed, funding_rates={})


def test_downtime_reconciliation_requires_hourly_funding_evidence(
    tmp_path: Path,
) -> None:
    """An hourly boundary cannot be replayed using an unrelated current rate."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="resume-open",
        execution_mode="shadow",
    )
    original.ensure_session_identity()
    original.engine.apply_market_fill(
        feed_ts="2026-07-25T12:58:00Z",
        action="enter_long",
        side="buy",
        qty=1.0,
        mark_px=100.0,
        fill_model=PostOnlyLimitFillModel(),
    )
    resumed = PaperSession(
        export_dir=export,
        data_root=data_root,
        execution_mode="shadow",
    )

    with pytest.raises(RuntimeError, match="missing Hyperliquid funding history"):
        resumed.reconcile_downtime(
            pd.DataFrame([_hl_bar("2026-07-25T12:59:00Z", high=100.1, low=99.9)]),
            funding_rates={},
        )

    assert resumed.engine.position.qty == 1.0


def test_downtime_reconciliation_accepts_no_completed_missed_bars(
    tmp_path: Path,
) -> None:
    """An immediate restart with no completed candle is a valid no-op."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="resume-open",
        execution_mode="shadow",
    )
    original.ensure_session_identity()
    original.engine.apply_market_fill(
        feed_ts="2026-07-25T12:58:00Z",
        action="enter_long",
        side="buy",
        qty=1.0,
        mark_px=100.0,
        fill_model=PostOnlyLimitFillModel(),
    )
    resumed = PaperSession(
        export_dir=export,
        data_root=data_root,
        execution_mode="shadow",
    )
    empty = pd.DataFrame(
        columns=["timestamp", "open", "high", "low", "close", "volume", "source"]
    )

    assert resumed.reconcile_downtime(empty, funding_rates={}) == 0


def test_downtime_reconciliation_never_synthesizes_new_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offline bars cannot create a trade after an existing position closes."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="resume-flat",
        execution_mode="shadow",
    )
    original.ensure_session_identity()
    original.engine.apply_market_fill(
        feed_ts="2026-07-25T12:57:00Z",
        action="enter_long",
        side="buy",
        qty=1.0,
        mark_px=100.0,
        fill_model=PostOnlyLimitFillModel(),
    )
    original.engine.apply_market_fill(
        feed_ts="2026-07-25T12:58:00Z",
        action="close",
        side="sell",
        qty=1.0,
        mark_px=100.2,
        fill_model=PostOnlyLimitFillModel(),
    )
    resumed = PaperSession(
        export_dir=export,
        data_root=data_root,
        execution_mode="shadow",
    )
    monkeypatch.setattr(
        "hypervector.paper.session.current_hypervelocity_entry_allowed",
        lambda frame, direction: True,
    )

    resumed.reconcile_downtime(
        pd.DataFrame(
            [
                _hl_bar("2026-07-25T12:58:00Z", high=100.5, low=99.5),
                _hl_bar("2026-07-25T12:59:00Z", high=100.5, low=99.5),
            ]
        ),
        funding_rates={},
    )

    assert resumed.engine.position.qty == 0.0
    assert resumed.pending_maker_entry is None
    new_rows = _decision_rows(resumed.decisions_path)
    assert len([row for row in new_rows if row.get("action") == "submit_entry"]) == 0


def test_downtime_reconciliation_fills_restored_pending_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pre-restart maker order keeps its original limit and annotations."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="resume-pending",
        execution_mode="shadow",
    )
    original.ensure_session_identity()
    original.engine.record_order_event(
        feed_ts="2026-07-25T12:58:00Z",
        action="submit_entry",
        side="buy",
        qty=2.0,
        limit_px=100.0,
        status="pending",
        metalabel_p=0.62,
        metalabel_bundle_id="long-bundle",
    )
    resumed = PaperSession(
        export_dir=export,
        data_root=data_root,
        execution_mode="shadow",
    )
    monkeypatch.setattr(
        "hypervector.paper.session.current_hypervelocity_entry_allowed",
        lambda frame, direction: True,
    )

    resumed.reconcile_downtime(
        pd.DataFrame([_hl_bar("2026-07-25T12:58:00Z", high=100.1, low=99.9)]),
        funding_rates={},
    )

    assert resumed.pending_maker_entry is None
    assert resumed.engine.position.qty == 2.0
    entries = [
        row
        for row in _decision_rows(resumed.decisions_path)
        if row.get("action") == "enter_long"
    ]
    assert entries[-1]["fill_px"] == 100.0
    assert entries[-1]["metalabel_p"] == 0.62


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
    assert session.metalabel_mode == "observe"
    assert "hypervelocity-l2-runtime-uptrend-long" in (
        session.conviction_provider.bundle_id or ""
    )
    assert "hypervelocity-l2-runtime-downtrend-short" in (
        session.conviction_provider.bundle_id or ""
    )
    directions = iter(("long", "long", "short", "short"))

    def market(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(entry_direction=next(directions))

    monkeypatch.setattr(
        "hypervector.paper.session.current_hypervelocity_market", market
    )

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
    execution = session._hypervelocity_entry_execution_payload(
        bar(4, high=100.3, low=99.9)
    )
    assert execution["entry_cooldown_active"] is True

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
