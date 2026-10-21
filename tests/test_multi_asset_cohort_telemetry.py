"""Authoritative ledger projection tests for the multi-asset cohort."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.bidirectional_intents import (
    IntentRoutingReport,
    RoutingAction,
    StrategyIntent,
    WithheldIntent,
)
from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
)
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_funding_window import CohortFundingWindow
from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult
from hypervector.live.cohort_transition_drain import CohortTransitionDrain
from hypervector.live.multi_asset_cohort_telemetry import (
    AssetCohortSnapshot,
    MultiAssetCohortTelemetry,
    SharedAccountFacts,
)
from hypervector.live import multi_asset_strategy_evidence
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_intent_poller import CohortMarketBar
from hypervector.live.provider_evaluation import ProviderEvaluation
from hypervector.live.multi_asset_strategy_evidence_models import (
    StrategyDirectionalEvidence,
    StrategyResearchEvidence,
)
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.hyperliquid_protocol import SolBookLevel, SolBookSnapshot
from hypervector.live.sol_range_onset_ledger import SolLiveLedger


def _telemetry(
    tmp_path: Path,
    *,
    prestart_backup: CohortPrestartBackupResult | None = None,
) -> tuple[MultiAssetCohortTelemetry, SolLiveLedger]:
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/cohort_base.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    ledger = SolLiveLedger(
        path=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="cohort-live-test",
    )
    return (
        MultiAssetCohortTelemetry(
            config=config,
            ledger=ledger,
            now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
            prestart_backup=prestart_backup,
        ),
        ledger,
    )


def _intent(symbol: str, side: str) -> StrategyIntent:
    return StrategyIntent(
        strategy_id="hulk_expansion_bidirectional_tuned_v2",
        symbol=symbol,
        side=side,
        decision_time_ms=1_785_600_000_000,
        reference_price=100.0,
        reason="completed_signal",
    )


def test_configuration_and_snapshot_expose_every_coin_and_both_sides(
    tmp_path: Path,
) -> None:
    """The TUI source ledger cannot present the cohort as short-only."""
    telemetry, ledger = _telemetry(tmp_path)
    telemetry.emit_configuration()
    telemetry.emit_snapshot(
        account=SharedAccountFacts(
            153.5,
            148.0,
            5.5,
            25.0,
            "spot_clearinghouse_state",
        ),
        assets=_snapshot_assets(),
    )

    records = ledger.read_all()
    identity = records[0]["payload"]
    snapshot = records[1]["payload"]
    assert identity["enabled_symbols"] == ["BTC", "ETH", "SOL", "HYPE"]
    assert all(item["sides"] == ["long", "short"] for item in identity["assets"])
    range_provider = next(
        provider
        for provider in identity["providers"]
        if provider["strategy_id"] == "range_onset_bidirectional_v1"
    )
    assert range_provider["entry_context_overrides"] == {"ETH": "dual_mtf_not_opposed"}
    assert snapshot["open_position_count"] == 1
    assert snapshot["account_balance_source"] == "spot_clearinghouse_state"
    assert snapshot["assets"][0]["position_side"] == "short"
    assert snapshot["assets"][0]["target_oid"] == 3
    assert snapshot["assets"][0]["target_price"] == 99.25
    assert snapshot["assets"][0]["execution_plan"]["strategy_id"].startswith("hulk_")


def test_funding_reconciliation_window_is_append_only_raw_evidence(
    tmp_path: Path,
) -> None:
    """Funding cursor telemetry must preserve exact committed boundaries."""
    telemetry, ledger = _telemetry(tmp_path)
    window = CohortFundingWindow(
        funding_start_time_ms=1_000,
        initial_funding_end_time_ms=2_000,
        provider_cutoff_time_ms=2_100,
        committed_funding_end_time_ms=2_000,
        next_funding_start_time_ms=2_000,
        action_count=0,
        post_action_reconciliation=False,
    )

    telemetry.emit_funding_reconciliation_window(window)

    row = ledger.read_all()[0]
    assert row["event_type"] == "funding_reconciliation_window"
    assert row["payload"] == window.as_payload()
    assert row["execution_authority"] == "hyperliquid_mainnet"


def test_snapshots_project_explicit_transition_drain_state(tmp_path: Path) -> None:
    """The TUI receives current drain truth rather than inferring command history."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/cohort_base.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    ledger = SolLiveLedger(
        path=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="cohort-live-test",
    )
    drain = CohortTransitionDrain(
        path=tmp_path / "transition_drain.json",
        run_id=ledger.run_id,
        profile_fingerprint=config.profile_fingerprint,
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
    )
    telemetry = MultiAssetCohortTelemetry(
        config=config,
        ledger=ledger,
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        transition_drain=drain,
    )
    account = SharedAccountFacts(100.0, 100.0, 0.0, 0.0)

    telemetry.emit_snapshot(account=account, assets=_flat_snapshot_assets())
    drain.activate(
        request_id="d" * 32,
        requested_at_utc="2026-08-01T11:59:59+00:00",
    )
    telemetry.emit_snapshot(account=account, assets=_flat_snapshot_assets())
    drain.complete()
    telemetry.emit_snapshot(account=account, assets=_flat_snapshot_assets())

    states = [row["payload"]["transition_drain"] for row in ledger.read_all()]
    assert states[0] == {
        "status": "inactive",
        "request_id": None,
        "origin_run_id": None,
        "run_id": ledger.run_id,
        "profile_fingerprint": config.profile_fingerprint,
        "requested_at_utc": None,
        "activated_at_utc": None,
        "resume_count": 0,
        "last_resumed_at_utc": None,
        "completed_at_utc": None,
    }
    assert states[1]["status"] == "active"
    assert states[1]["request_id"] == "d" * 32
    assert states[2]["status"] == "completed"
    assert states[2]["completed_at_utc"] == "2026-08-01T12:00:00+00:00"


def _snapshot_assets() -> tuple[AssetCohortSnapshot, ...]:
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="hulk_expansion_bidirectional_tuned_v2", stop_anchor=None)
    open_btc = AssetCohortSnapshot(
        "BTC",
        "OPEN",
        -0.001,
        1,
        2,
        None,
        target_oid=3,
        target_price=99.25,
        execution_plan=plan,
    )
    flat = tuple(
        AssetCohortSnapshot(symbol, "FLAT", 0.0, None, None, None)
        for symbol in ("ETH", "SOL", "HYPE")
    )
    return (open_btc, *flat)


def _flat_snapshot_assets() -> tuple[AssetCohortSnapshot, ...]:
    return tuple(
        AssetCohortSnapshot(symbol, "FLAT", 0.0, None, None, None)
        for symbol in ("BTC", "ETH", "SOL", "HYPE")
    )


def test_configuration_exposes_non_gating_strategy_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every provider-symbol mapping carries an honest research-state record."""
    hulk = "hulk_expansion_bidirectional_tuned_v2"
    monkeypatch.setitem(
        multi_asset_strategy_evidence._EVIDENCE,
        (hulk, "BTC"),
        StrategyResearchEvidence(
            hulk,
            "BTC",
            "contradictory",
            "medium",
            "historical sample",
            "long and short disagree",
            "evidence/hulk-btc.json",
            directional_evidence=(
                StrategyDirectionalEvidence(
                    "short",
                    "historical_candidate",
                    "low",
                    "12 trades",
                    "short survives modeled costs",
                    "evidence/hulk-btc.json",
                ),
            ),
        ),
    )
    telemetry, ledger = _telemetry(tmp_path)

    telemetry.emit_configuration()

    identity = ledger.read_all()[0]["payload"]
    assert identity["routing_policy"] == {
        "mode": "same_symbol_conflict_preference_v1",
        "alignment_basis": "canonical_1m_5m_15m_1_3_2_v1",
        "state_weights": {"state_1m": 1.0, "state_5m": 3.0, "context_15m": 2.0},
        "standalone_intents_ungated": True,
        "forced_regime_exit": False,
        "fallback": "provider_priority_then_decision_time",
    }
    evidence = identity["strategy_evidence"]
    provider_pairs = {
        (provider["strategy_id"], symbol)
        for provider in identity["providers"]
        for symbol in provider["symbols"]
    }
    evidence_pairs = {(record["strategy_id"], record["symbol"]) for record in evidence}
    assert evidence_pairs == provider_pairs
    assert all(record["execution_effect"] == "report_only" for record in evidence)
    assert all(record["confidence"] in {"high", "medium", "low"} for record in evidence)
    assert all(record["cadence"] for record in evidence)
    hulk_btc = next(
        record
        for record in evidence
        if record["strategy_id"] == hulk and record["symbol"] == "BTC"
    )
    assert hulk_btc["research_state"] == "contradictory"
    assert hulk_btc["evidence_source"] == "evidence/hulk-btc.json"
    assert [row["side"] for row in hulk_btc["directional_evidence"]] == ["short"]
    assert hulk_btc["directional_evidence"][0]["execution_effect"] == "report_only"
    assert all(
        record["research_state"] == "unreviewed_exact_mapping"
        and record["evidence_source"] == "none"
        for record in evidence
        if record is not hulk_btc
    )


def test_configuration_persists_verified_prestart_backup_identity(
    tmp_path: Path,
) -> None:
    """The durable run identity binds the bundle that preceded live authority."""
    bundle = tmp_path / "prestart_bundle"
    backup = CohortPrestartBackupResult(
        path=bundle,
        manifest_path=bundle / "manifest.json",
        manifest_sha256="a" * 64,
        strategy_changed=True,
        implementation_file_count=1_156,
        implementation_sha256="b" * 64,
    )
    telemetry, ledger = _telemetry(tmp_path, prestart_backup=backup)

    telemetry.emit_configuration()

    identity = ledger.read_all()[0]["payload"]
    assert identity["prestart_backup"] == {
        "status": "verified",
        "bundle_path": str(bundle),
        "manifest_path": str(bundle / "manifest.json"),
        "manifest_sha256": "a" * 64,
        "strategy_changed": True,
        "implementation_file_count": 1_156,
        "implementation_sha256": "b" * 64,
    }


def test_routing_records_selected_and_withheld_strategy_identity(
    tmp_path: Path,
) -> None:
    """No conflict or capacity decision disappears from the operator journal."""
    telemetry, ledger = _telemetry(tmp_path)
    selected = _aligned_intent("BTC", "long", 1.0, "directionally_supported")
    withheld = _aligned_intent("SOL", "short", -1.0, "directionally_opposed")
    report = IntentRoutingReport(
        actions=(
            RoutingAction(
                "enter",
                selected.strategy_id,
                selected.symbol,
                selected.side,
                selected.decision_time_ms,
                selected.reference_price,
                regime_alignment_score=selected.regime_alignment_score,
                regime_alignment_stance=selected.regime_alignment_stance,
                regime_decision_time_ms=selected.regime_decision_time_ms,
                regime_alignment_basis=selected.regime_alignment_basis,
                submission_observed_at_ms=1_785_600_029_000,
                submission_age_ms=29_000,
                submission_limit_ms=30_000,
            ),
        ),
        withheld=(
            WithheldIntent(
                withheld,
                "stale_before_submission",
                submission_observed_at_ms=1_785_600_031_000,
                submission_age_ms=31_000,
                submission_limit_ms=30_000,
            ),
        ),
    )

    telemetry.emit_routing((selected, withheld), report)

    records = ledger.read_all()
    assert [row["event_type"] for row in records] == [
        "strategy_intent",
        "strategy_intent",
        "intent_routing",
    ]
    payload = records[-1]["payload"]
    assert payload["actions"][0]["strategy_id"] == selected.strategy_id
    assert payload["actions"][0]["regime_alignment_score"] == 1.0
    assert payload["actions"][0]["regime_alignment_stance"] == (
        "directionally_supported"
    )
    assert payload["actions"][0]["submission_observed_at_ms"] == 1_785_600_029_000
    assert payload["actions"][0]["submission_age_ms"] == 29_000
    assert payload["actions"][0]["submission_limit_ms"] == 30_000
    assert payload["withheld"][0]["regime_alignment_score"] == -1.0
    assert payload["withheld"][0]["reason"] == "stale_before_submission"
    assert payload["withheld"][0]["submission_observed_at_ms"] == 1_785_600_031_000
    assert payload["withheld"][0]["submission_age_ms"] == 31_000
    assert payload["withheld"][0]["submission_limit_ms"] == 30_000


def _aligned_intent(
    symbol: str,
    side: str,
    score: float,
    stance: str,
) -> StrategyIntent:
    return replace(
        _intent(symbol, side),
        regime_alignment_score=score,
        regime_alignment_stance=stance,
        regime_decision_time_ms=1_785_600_000_000,
        regime_alignment_basis="canonical_1m_5m_15m_1_3_2_v1",
    )


def test_routing_records_non_entry_provider_readiness(tmp_path: Path) -> None:
    """A healthy no-trade cycle carries progress and blockers to the TUI."""
    telemetry, ledger = _telemetry(tmp_path)
    evaluation = ProviderEvaluation(
        strategy_id="hulk_expansion_bidirectional_tuned_v2",
        symbol="BTC",
        decision_time_ms=1_785_600_000_000,
        reference_price=100.0,
        decision_action="hold",
        eligible=False,
        reason="no_trigger",
        side="long",
        readiness=SignalReadiness(
            side="long",
            conditions_met=4,
            conditions_required=6,
            blockers=("awaiting_squeeze_release", "volume_not_above_1x"),
            indicators=("ADX 21.4/18.0", "VOLUME 0.92x", "SQUEEZE ARMED"),
        ),
        score=3,
        minimum_score=8,
        trigger="none",
    )

    telemetry.emit_routing((), IntentRoutingReport((), ()), (evaluation,))

    record = ledger.read_all()[0]
    assert record["event_type"] == "intent_routing"
    assert record["payload"]["evaluations"] == [evaluation.as_payload()]
    coverage = record["payload"]["setup_coverage"]
    assert coverage["expected_provider_symbols"] == 10
    assert coverage["observed_provider_symbols"] == 1
    assert coverage["complete"] is False
    assert coverage["missing_provider_symbols"] == sorted(
        coverage["missing_provider_symbols"]
    )
    assert (
        "hulk_expansion_bidirectional_tuned_v2|ETH"
        in coverage["missing_provider_symbols"]
    )


def test_canonical_regime_telemetry_is_separate_and_non_executable(
    tmp_path: Path,
) -> None:
    """Independent regime rows cannot inflate setup coverage or imply an intent."""
    telemetry, ledger = _telemetry(tmp_path)
    evaluation = ProviderEvaluation(
        strategy_id=CANONICAL_REGIME_TELEMETRY_STRATEGY,
        symbol="BTC",
        decision_time_ms=1_785_600_000_000,
        reference_price=100.0,
        decision_action="regime_observation",
        eligible=False,
        reason="canonical_regime_observation",
        side=None,
        readiness=SignalReadiness(
            side=None,
            conditions_met=1,
            conditions_required=1,
            blockers=(),
            indicators=("5m TREND_UP",),
        ),
        primary_regime="TREND_UP",
        state_1m="TREND_UP",
        state_5m="TREND_UP",
        context_15m="RANGE",
        confidence=0.8,
        backend_non_action_reason="telemetry_only_no_execution_authority",
    )

    telemetry.emit_canonical_regimes((evaluation,))

    row = ledger.read_all()[0]
    assert row["event_type"] == "canonical_regime_evaluations"
    assert row["payload"]["contract"] == {
        "execution_authority": "none",
        "intents_emitted": False,
        "configured_route": False,
    }
    assert row["payload"]["evaluations"] == [evaluation.as_payload()]


def test_observe_telemetry_is_explicitly_disarmed(tmp_path: Path) -> None:
    """The same TUI schema must not imply order authority in observe mode."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/cohort_base.toml",
        mode="observe",
    )
    ledger = SolLiveLedger(
        path=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="cohort-observe-test",
    )
    telemetry = MultiAssetCohortTelemetry(
        config=config,
        ledger=ledger,
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
    )

    telemetry.emit_configuration()
    telemetry.emit_heartbeat()

    records = ledger.read_all()
    assert all(record["live_armed"] is False for record in records)
    assert all(record["execution_authority"] == "none" for record in records)
    assert records[0]["payload"]["backend_ledger_path"] == str(ledger.path)


def test_transient_poll_failure_emits_degraded_no_order_heartbeat(
    tmp_path: Path,
) -> None:
    """A skipped read cycle remains visible without implying an order attempt."""
    telemetry, ledger = _telemetry(tmp_path)

    telemetry.emit_poll_degraded(
        source="hyperliquid_public_candles",
        reason="http_429_retry_exhausted",
    )

    record = ledger.read_all()[0]
    assert record["event_type"] == "heartbeat"
    assert record["payload"] == {
        "status": "degraded",
        "source": "hyperliquid_public_candles",
        "reason": "http_429_retry_exhausted",
        "orders_attempted": False,
    }


def test_unhandled_runtime_fault_is_durable_without_exception_detail(
    tmp_path: Path,
) -> None:
    """A terminal process fault records its class without leaking message data."""
    telemetry, ledger = _telemetry(tmp_path)

    telemetry.emit_runtime_fault(exception_type="ReadTimeout")

    record = ledger.read_all()[0]
    assert record["event_type"] == "runtime_fault"
    assert record["payload"] == {
        "status": "faulted",
        "exception_type": "ReadTimeout",
        "orders_attempted": False,
        "detail": "inspect backend process log",
    }


def test_maximum_hold_decision_is_durable_and_restart_idempotent(
    tmp_path: Path,
) -> None:
    """A stable lifecycle boundary is appended once across telemetry restarts."""
    telemetry, ledger = _telemetry(tmp_path)
    payload = {
        "decision_id": "HYPE:99:soft_maximum_hold",
        "lifecycle_id": "HYPE:99",
        "symbol": "HYPE",
        "outcome": "extend",
    }

    telemetry.emit_maximum_hold_decision(payload)
    telemetry.emit_maximum_hold_decision(payload)
    _restarted_telemetry(ledger).emit_maximum_hold_decision(payload)

    records = ledger.read_all()
    assert len(records) == 1
    assert records[0]["event_type"] == "maximum_hold_decision"
    assert records[0]["payload"] == payload


def test_maximum_hold_decision_rejects_conflicting_stable_identity(
    tmp_path: Path,
) -> None:
    """One stable decision ID cannot silently describe two outcomes."""
    telemetry, _ = _telemetry(tmp_path)
    payload = {
        "decision_id": "HYPE:99:soft_maximum_hold",
        "lifecycle_id": "HYPE:99",
        "symbol": "HYPE",
        "outcome": "extend",
    }
    telemetry.emit_maximum_hold_decision(payload)

    with pytest.raises(ValueError, match="conflicting maximum-hold decision"):
        telemetry.emit_maximum_hold_decision(payload | {"outcome": "exit"})


def test_provider_exit_decision_is_durable_and_restart_idempotent(
    tmp_path: Path,
) -> None:
    """A provider recipe exit survives telemetry reconstruction exactly once."""
    telemetry, ledger = _telemetry(tmp_path)
    payload = {
        "decision_id": "HYPE:99:provider_recipe_exit",
        "lifecycle_id": "HYPE:99",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "symbol": "HYPE",
        "side": "long",
        "outcome": "exit",
        "exit_reason": "provider_recipe_exit",
        "decision_time_ms": 1_785_600_000_000,
    }

    telemetry.emit_provider_exit_decision(payload)
    telemetry.emit_provider_exit_decision(payload)
    restarted = _restarted_telemetry(ledger)

    assert restarted.recorded_provider_exit_decision(payload["decision_id"]) == payload
    restarted.emit_provider_exit_decision(payload)
    records = ledger.read_all()
    assert len(records) == 1
    assert records[0]["event_type"] == "provider_exit_decision"


def test_provider_exit_decision_rejects_conflicting_stable_identity(
    tmp_path: Path,
) -> None:
    """One lifecycle cannot silently acquire a different persisted exit reason."""
    telemetry, _ = _telemetry(tmp_path)
    payload = {
        "decision_id": "HYPE:99:provider_recipe_exit",
        "lifecycle_id": "HYPE:99",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "symbol": "HYPE",
        "side": "long",
        "outcome": "exit",
        "exit_reason": "hip3_swing_ha_flip",
        "decision_time_ms": 1_785_600_000_000,
    }
    telemetry.emit_provider_exit_decision(payload)

    with pytest.raises(ValueError, match="conflicting provider-exit decision"):
        telemetry.emit_provider_exit_decision(
            payload | {"exit_reason": "hip3_swing_alignment_loss"}
        )


def _restarted_telemetry(ledger: SolLiveLedger) -> MultiAssetCohortTelemetry:
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/cohort_base.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    restarted_ledger = SolLiveLedger(
        path=ledger.path,
        profile_id=ledger.profile_id,
        profile_fingerprint=ledger.profile_fingerprint,
        run_fingerprint=ledger.run_fingerprint,
        run_id=ledger.run_id,
    )
    return MultiAssetCohortTelemetry(
        config=config,
        ledger=restarted_ledger,
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
    )


def test_market_candles_emit_initial_history_then_only_new_completed_bars(
    tmp_path: Path,
) -> None:
    """Fast reconciliation polls cannot duplicate backend candle history."""
    telemetry, ledger = _telemetry(tmp_path)
    first = {
        symbol: (
            CohortMarketBar(symbol, 1_785_585_480_000, 99.0, 101.0, 98.0, 100.0, 10.0),
            CohortMarketBar(symbol, 1_785_585_540_000, 100.0, 102.0, 99.0, 101.0, 11.0),
        )
        for symbol in ("BTC", "ETH", "SOL", "HYPE")
    }

    telemetry.emit_market_bars(first)
    telemetry.emit_market_bars(first)
    telemetry.emit_market_bars(
        {
            symbol: bars
            + (
                CohortMarketBar(
                    symbol,
                    1_785_585_600_000,
                    101.0,
                    103.0,
                    100.0,
                    102.0,
                    12.0,
                ),
            )
            for symbol, bars in first.items()
        }
    )

    rows = ledger.read_all()
    assert [row["event_type"] for row in rows] == [
        "market_candles",
        "market_candles",
    ]
    assert all(len(rows[0]["payload"]["bars"][symbol]) == 2 for symbol in first)
    assert all(len(rows[1]["payload"]["bars"][symbol]) == 1 for symbol in first)
    assert rows[1]["payload"]["bars"]["BTC"][0]["timestamp_ms"] == 1_785_585_600_000


def test_observer_books_emit_complete_backend_authored_depth(tmp_path: Path) -> None:
    """Public observer depth is serialized without wallet or order authority."""
    telemetry, ledger = _telemetry(tmp_path)
    books = {
        symbol: SolBookSnapshot(
            exchange_timestamp_ms=1_785_585_600_000,
            bids=(SolBookLevel(99.9, 2.0, 3), SolBookLevel(99.8, 1.0, 1)),
            asks=(SolBookLevel(100.1, 1.5, 2), SolBookLevel(100.2, 2.5, 4)),
            mid_price=100.0,
            spread_bps=20.0,
            bid_depth=3.0,
            ask_depth=4.0,
            order_pressure=-1.0 / 7.0,
        )
        for symbol in ("BTC", "ETH", "SOL", "HYPE")
    }

    telemetry.emit_market_books(books)

    row = ledger.read_all()[0]
    assert row["event_type"] == "market_books"
    assert row["payload"]["books"]["BTC"]["source"] == "hyperliquid_mainnet_l2_rest"
    assert len(row["payload"]["books"]["BTC"]["bids"]) == 2
    assert row["payload"]["books"]["BTC"]["asks"][0]["price"] == 100.1
