"""Paper-session parity tests for the source-follow shadow profile."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent, PublicTradeEvent
from hypervector.paper.maker_execution import quantize_size_down
from hypervector.paper.session import PaperSession
from hypervector.regime.source_follow_runtime import (
    FiveMinuteBar,
    SourceFollowRuntime,
    SourceRegimeLabel,
)
from hypervector.regime.source_follow_session import SourceFollowSessionSignal
from hypervector.strategies.source_follow_profile import load_source_follow_profile


class _TrendDownClassifier:
    def classify(self, bar: FiveMinuteBar) -> SourceRegimeLabel:
        return SourceRegimeLabel(
            label_time_utc=bar.timestamp_utc,
            primary="TREND_DOWN",
            secondary=None,
            confidence=0.90,
        )


def _warm_frame() -> pd.DataFrame:
    stamps = pd.date_range("2026-07-28T12:00:00Z", periods=5, freq="1min")
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "open": [100.0] * 5,
            "high": [100.4] * 5,
            "low": [99.6] * 5,
            "close": [100.0] * 5,
            "volume": [1.0] * 5,
            "source": ["hl"] * 5,
        }
    )


def _book(at: datetime) -> L2SnapshotEvent:
    exchange_ms = int(at.timestamp() * 1_000)
    return L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=exchange_ms,
        received_ts_ns=(exchange_ms + 1) * 1_000_000,
        bids=(BookLevel(99.9, 10_000.0, 1),),
        asks=(BookLevel(100.1, 10_000.0, 1),),
    )


def _trade(at: datetime) -> PublicTradeEvent:
    exchange_ms = int(at.timestamp() * 1_000)
    return PublicTradeEvent(
        symbol="BTC",
        aggressor_side="buy",
        price=100.1,
        size=20_000.0,
        transaction_hash="0xsourcefill",
        exchange_ts_ms=exchange_ms,
        received_ts_ns=(exchange_ms + 1) * 1_000_000,
        trade_id=1,
        buyer="0xbuyer",
        seller="0xseller",
    )


@pytest.mark.integration
def test_source_profile_warmup_arms_one_fresh_l2_sized_short(tmp_path) -> None:
    """Warm labels submit once from fresh L2 using the measured 50%/30x size."""
    profile = load_source_follow_profile(
        "configs/hypervelocity_source_follow_shadow.toml"
    )
    signal = SourceFollowSessionSignal(SourceFollowRuntime(_TrendDownClassifier()))
    session = PaperSession(
        export_dir=profile.export_path,
        data_root=tmp_path,
        execution_mode="shadow",
        hypervelocity_profile=profile,
        initial_cash_usd=profile.initial_cash_usd,
        source_follow_signal=signal,
    )
    controller = session.activate_hypervelocity_event_runtime(
        observed_at="2026-07-28T12:05:00+00:00"
    )
    session.warm_up(_warm_frame())

    session.ingest_hyperliquid_event(_book(datetime(2026, 7, 28, 12, 5, tzinfo=UTC)))

    pending = controller.state.pending_entry
    assert pending is not None
    assert pending.command.side == "sell"
    expected = quantize_size_down(
        profile.initial_cash_usd * profile.margin_fraction * profile.leverage / 100.1,
        size_decimals=profile.size_decimals,
    )
    assert pending.command.quantity == pytest.approx(expected)
    assert pending.command.limit_price == pytest.approx(100.1)
    frame = _warm_frame().set_index("timestamp")
    telemetry = session._hypervelocity_regime_payload(frame)
    assert telemetry["primary_regime"] == "TREND_DOWN"
    assert telemetry["state_5m"] == "TREND_DOWN"
    assert telemetry["entry_direction"] == "short"
    assert telemetry["structural_direction"] == "short"
    assert telemetry["confidence"] == pytest.approx(0.90)
    assert telemetry["regime_score_source"] == ("pinned_hypertrader_rule_agreement")

    session.ingest_hyperliquid_event(_book(datetime(2026, 7, 28, 12, 6, tzinfo=UTC)))
    canceled = controller.state.pending_entry
    assert canceled is not None
    assert canceled.cancel_requested is True


@pytest.mark.integration
def test_session_profile_holds_open_position_after_entry_window(tmp_path: Path) -> None:
    """Ending entry hours must not force-close a position awaiting its target."""
    profile = load_source_follow_profile(
        "configs/hypervelocity_source_follow_session_06_15_minrange12_alloc35_shadow.toml"
    )
    signal = SourceFollowSessionSignal(
        SourceFollowRuntime(_TrendDownClassifier(), minimum_range_bps=12.0),
        entry_session_utc=profile.entry_session_utc,
    )
    session = PaperSession(
        export_dir=profile.export_path,
        data_root=tmp_path,
        execution_mode="shadow",
        hypervelocity_profile=profile,
        initial_cash_usd=profile.initial_cash_usd,
        source_follow_signal=signal,
    )
    controller = session.activate_hypervelocity_event_runtime(
        observed_at="2026-07-28T12:05:00+00:00"
    )
    session.warm_up(_warm_frame())
    opened_at = datetime(2026, 7, 28, 12, 5, tzinfo=UTC)
    session.ingest_hyperliquid_event(_book(opened_at))
    session.ingest_hyperliquid_event(_book(opened_at.replace(microsecond=100_000)))
    session.ingest_hyperliquid_event(_trade(opened_at.replace(microsecond=101_000)))

    session.ingest_hyperliquid_event(_book(datetime(2026, 7, 28, 16, tzinfo=UTC)))

    assert controller.state.position_direction == "short"
    assert controller.state.position_quantity > 0.0
    assert controller.state.active_targets
    frame = _warm_frame().set_index("timestamp")
    telemetry = session._hypervelocity_regime_payload(frame)
    assert telemetry["entry_allowed"] is False
    assert telemetry["regime_reason"] == "source_follow_outside_entry_session"


@pytest.mark.integration
def test_source_profile_ledgers_exact_effective_backend_configuration(
    tmp_path: Path,
) -> None:
    """TUI consumers must receive source-profile risk and exit values, not base values."""
    profile = load_source_follow_profile(
        "configs/hypervelocity_source_follow_shadow.toml"
    )
    session = PaperSession(
        export_dir=profile.export_path,
        data_root=tmp_path,
        execution_mode="shadow",
        hypervelocity_profile=profile,
        initial_cash_usd=profile.initial_cash_usd,
    )

    session.ensure_session_identity()

    identity = json.loads(session.decisions_path.read_text().splitlines()[-1])
    assert identity["profile_id"] == "hypervelocity_source_follow_shadow_v1"
    assert identity["strategy_params"]["leverage"] == 30.0
    assert identity["risk"]["margin_fraction"] == 0.50
    assert identity["risk"]["notional_fraction"] == 15.0
    assert identity["exits"]["maximum_hold_seconds"] == 86_400.0
    assert identity["exits"]["range_policy"] == ("hold_until_target_or_maximum_hold")
    assert identity["execution"]["maximum_hold_exit"] == ("first_fresh_bbo_taker")


@pytest.mark.integration
def test_minrange12_profile_ledgers_its_distinct_entry_contract(
    tmp_path: Path,
) -> None:
    """Backend and TUI telemetry must identify the lead's added range floor."""
    profile = load_source_follow_profile(
        "configs/hypervelocity_source_follow_minrange12_shadow.toml"
    )
    signal = SourceFollowSessionSignal(
        SourceFollowRuntime(_TrendDownClassifier(), minimum_range_bps=12.0)
    )
    session = PaperSession(
        export_dir=profile.export_path,
        data_root=tmp_path,
        execution_mode="shadow",
        hypervelocity_profile=profile,
        initial_cash_usd=profile.initial_cash_usd,
        source_follow_signal=signal,
    )

    session.ensure_session_identity()

    identity = json.loads(session.decisions_path.read_text().splitlines()[-1])
    assert identity["profile_id"] == (
        "hypervelocity_source_follow_minrange12_shadow_v1"
    )
    assert identity["regime_policy"]["minimum_completed_5m_range_bps"] == 12.0
    assert identity["execution_mode"] == "shadow"
    assert identity["metalabel_mode"] == "observe"


@pytest.mark.integration
def test_alloc35_profile_ledgers_exact_backend_risk_contract(
    tmp_path: Path,
) -> None:
    """Backend telemetry must expose the measured 35% isolated allocation."""
    profile = load_source_follow_profile(
        "configs/hypervelocity_source_follow_minrange12_alloc35_shadow.toml"
    )
    signal = SourceFollowSessionSignal(
        SourceFollowRuntime(_TrendDownClassifier(), minimum_range_bps=12.0)
    )
    session = PaperSession(
        export_dir=profile.export_path,
        data_root=tmp_path,
        execution_mode="shadow",
        hypervelocity_profile=profile,
        initial_cash_usd=profile.initial_cash_usd,
        source_follow_signal=signal,
    )

    session.ensure_session_identity()

    identity = json.loads(session.decisions_path.read_text().splitlines()[-1])
    assert identity["profile_id"] == (
        "hypervelocity_source_follow_minrange12_alloc35_shadow_v1"
    )
    assert identity["risk"]["margin_fraction"] == pytest.approx(0.35)
    assert identity["risk"]["notional_fraction"] == pytest.approx(10.5)
    assert identity["strategy_params"]["leverage"] == pytest.approx(30.0)
    assert identity["regime_policy"]["minimum_completed_5m_range_bps"] == 12.0
    assert identity["metalabel_mode"] == "observe"


@pytest.mark.evidence
def test_measured_profile_ledgers_risk_target_and_evidence_status(
    tmp_path: Path,
) -> None:
    """TUI identity must distinguish measured risk from development evidence."""
    profile = load_source_follow_profile(
        "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow.toml"
    )
    signal = SourceFollowSessionSignal(
        SourceFollowRuntime(_TrendDownClassifier(), minimum_range_bps=12.0)
    )
    session = PaperSession(
        export_dir=profile.export_path,
        data_root=tmp_path,
        execution_mode="shadow",
        hypervelocity_profile=profile,
        initial_cash_usd=profile.initial_cash_usd,
        source_follow_signal=signal,
    )

    session.ensure_session_identity()

    identity = json.loads(session.decisions_path.read_text().splitlines()[-1])
    assert identity["risk"]["margin_fraction"] == pytest.approx(0.10)
    assert identity["risk"]["notional_fraction"] == pytest.approx(0.50)
    assert identity["strategy_params"]["leverage"] == pytest.approx(5.0)
    assert identity["exits"]["target_margin_pct"] == pytest.approx(4.0 / 3.0)
    assert identity["exits"]["target_price_fraction"] == pytest.approx(
        8.0 / 30.0 / 100.0
    )
    assert identity["runtime"]["evidence_status"] == (
        "development_candidate_not_live_proven"
    )
    assert identity["runtime"]["execution_economics_conclusive"] is False
    assert identity["runtime"]["active_book_gap_windows"] == 2
    assert identity["metalabel_policy"] == {
        "observation_type": "annotation_collection",
        "inference_active": False,
        "bundle_id": None,
        "probabilities_emitted": False,
        "may_filter": False,
        "may_scale": False,
        "execution_authority": "none",
    }


@pytest.mark.integration
def test_source_fill_and_restart_preserve_original_hold_deadline(
    tmp_path: Path,
) -> None:
    """Source L2 fill, ledger resume, and runtime restore share one hold clock."""
    profile = load_source_follow_profile(
        "configs/hypervelocity_source_follow_shadow.toml"
    )
    signal = SourceFollowSessionSignal(SourceFollowRuntime(_TrendDownClassifier()))
    first = PaperSession(
        export_dir=profile.export_path,
        data_root=tmp_path,
        execution_mode="shadow",
        hypervelocity_profile=profile,
        initial_cash_usd=profile.initial_cash_usd,
        source_follow_signal=signal,
    )
    original = first.activate_hypervelocity_event_runtime(
        observed_at="2026-07-28T12:05:00+00:00"
    )
    first.ensure_session_identity()
    first.warm_up(_warm_frame())
    opened_at = datetime(2026, 7, 28, 12, 5, tzinfo=UTC)

    first.ingest_hyperliquid_event(_book(opened_at))
    first.ingest_hyperliquid_event(_book(opened_at.replace(microsecond=100_000)))
    first.ingest_hyperliquid_event(_trade(opened_at.replace(microsecond=101_000)))

    assert original.state.position_direction == "short"
    assert first.engine.position.qty < 0.0
    original_opened_at = original.state.position_opened_at
    assert original_opened_at == "2026-07-28T12:05:00.101000+00:00"

    resumed = PaperSession(
        export_dir=profile.export_path,
        data_root=tmp_path,
        execution_mode="shadow",
        hypervelocity_profile=profile,
        initial_cash_usd=profile.initial_cash_usd,
        source_follow_signal=SourceFollowSessionSignal(
            SourceFollowRuntime(_TrendDownClassifier())
        ),
    )
    controller = resumed.activate_hypervelocity_event_runtime(
        observed_at="2026-07-28T12:06:00+00:00"
    )

    assert controller.state.position_direction == "short"
    assert controller.state.position_opened_at == original_opened_at
    assert controller.state.maximum_hold_seconds == 86_400.0
