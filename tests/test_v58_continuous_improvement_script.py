from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest
from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.v58_continuous_improvement import (
    LifecycleEvidence,
    RouteOpportunity,
    RouteOpportunityCollection,
)
from hypervector.research.v58_current_funding_context import CurrentFundingContext
from hypervector.research.v58_continuous_generator_paths import (
    v58_continuous_generator_paths,
)
from hypervector.research.v58_eth_open_path_context import EthOpenPathContext
from hypervector.research.v58_eth_exit_research_context import EthExitResearchContext
from hypervector.research.v58_eth_profit_lock_context import EthProfitLockContext
from hypervector.research.v58_eth_risk_normalized_lock_context import (
    EthRiskNormalizedLockContext,
)
from hypervector.research.v58_continuous_liquidity_context import LiquidityContext
from hypervector.research.v58_continuous_portfolio_context import (
    PortfolioOpportunityContext,
)
from hypervector.research.v58_continuous_regime_context import (
    RegimeContext,
    RegimeContextCollection,
)
from hypervector.research.v58_continuous_runtime_context import (
    ProviderArrivalLag,
    RuntimeContext,
)
from hypervector.research.v58_continuous_return_context import (
    ReturnInteractionContext,
)
import v58_continuous_improvement_fixtures as fixtures

_SCRIPT = Path("scripts/v58_continuous_improvement.py")


def test_refresh_atomically_publishes_current_report_only_state(tmp_path: Path) -> None:
    """One bounded cycle must publish evidence without live authority."""
    module = _module()
    output = tmp_path / "latest.json"
    args = _args(tmp_path, output)

    loaders = module._ContinuousLoaders(
        observer=lambda *_args, **_kwargs: _observer(),
        lifecycle=lambda *_args, **_kwargs: _lifecycles(),
        opportunity=lambda *_args, **_kwargs: _opportunities(),
        active_routes=lambda *_args, **_kwargs: fixtures.v58_active_routes_context(),
        regime=lambda *_args, **_kwargs: _regimes(),
        portfolio=lambda *_args, **_kwargs: _portfolio(),
        runtime=lambda *_args, **_kwargs: _runtime(),
        backend=lambda *_args, **_kwargs: fixtures.v58_backend_context(),
        mandate=lambda *_args, **_kwargs: fixtures.v58_mandate_context(),
        brentoil=lambda *_args, **_kwargs: fixtures.v58_brentoil_context(),
        venue=lambda *_args, **_kwargs: fixtures.v58_venue_context(),
        returns=lambda *_args, **_kwargs: _returns(),
        risk=lambda *_args, **_kwargs: fixtures.v58_risk_context(),
        liquidity=lambda *_args, **_kwargs: _liquidity(),
        eth_path=lambda *_args, **_kwargs: _eth_path(),
        funding=lambda *_args, **_kwargs: _funding(),
        eth_exit=lambda *_args, **_kwargs: _eth_exit_research(),
        eth_profit_lock=lambda *_args, **_kwargs: _eth_profit_lock(),
        eth_risk_lock=lambda _checkpoint, _disposition: _eth_risk_lock(),
        sp500_recovery=lambda *_args, **_kwargs: _sp500_recovery(),
    )
    report = module.refresh(args, loaders=loaders)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["contract"]["execution_authority"] == "none"
    assert report["change_proposals"] == []
    assert report["generator_identity"]
    assert report["brentoil_live_lifecycle_context"]["state"] == "open_protected"
    _assert_contexts(report)


def _assert_contexts(report: dict[str, object]) -> None:
    assert len(report["regime_context"]) == 4
    assert all(row["edge_claim"] is False for row in report["regime_context"])
    portfolio = report["portfolio_opportunity_context"]
    assert portfolio["maximum_concurrent_eligible_symbols"] == 1
    assert portfolio["maximum_concurrent_margin_fraction"] == 0.03
    assert portfolio["joint_loss_probability_claim"] is False
    runtime = report["runtime_context"]
    assert runtime["minimum_entry_delay_headroom_seconds"] == 3.0
    assert runtime["entry_submission_latency_measured"] is False
    backend = report["live_backend_context"]
    assert backend["lifecycle_state"] == "backend_runtime_fault"
    assert backend["live_execution_running"] is False
    assert backend["current_venue_position_order_state_verified"] is True
    assert backend["venue_flat_no_orders"] is True
    assert backend["venue_open_positions"] == 0
    assert backend["venue_open_orders"] == 0
    assert backend["execution_authority"] == "none"
    returns = report["return_interaction_context"]
    assert returns["common_completed_bars"] == 20
    assert returns["stable_covariance_claim"] is False
    assert returns["sizing_input"] is False
    risk = report["risk_context"]
    assert risk["maximum_margin_fraction"] == 0.46
    assert risk["stacked_p99_stop_wave_loss_usd"] == 180.3
    assert risk["sizing_reference_equity_usd"] == 5_000.0
    assert risk["actual_account_value_usd"] == 4_875.84
    assert risk["actual_account_value_fresh"] is True
    assert risk["stacked_p99_stop_wave_loss_pct_sizing_reference"] == pytest.approx(
        3.606
    )
    assert risk["stacked_p99_stop_wave_loss_pct_actual_account"] == pytest.approx(
        180.3 / 4_875.84 * 100.0
    )
    assert risk["automatic_sizing_change"] is False
    liquidity = report["liquidity_context"]
    assert liquidity["synchronized_snapshot_count"] == 100
    assert liquidity["minimum_both_complete_rate"] == 1.0
    assert liquidity["visible_book_fill_claim"] is False
    assert liquidity["sizing_input"] is False
    _assert_eth_context(report)
    funding = report["current_funding_context"]
    assert funding["routes_exceeding_frozen_adverse"] == 1
    assert funding["constant_rate_projection_is_forecast"] is False
    assert funding["sizing_input"] is False
    assert funding["execution_authority"] == "none"
    _assert_sp500_context(report)


def _assert_eth_context(report: dict[str, object]) -> None:
    assert report["eth_duration_checkpoint_context"]["status"] == "not_available"
    eth_path = report["eth_open_path_context"]
    assert eth_path["maximum_favorable_excursion_bps"] == 25.0
    assert eth_path["maximum_adverse_excursion_bps"] == 15.0
    assert eth_path["continuous_path_claim"] is False
    history = eth_path["source_compatible_lifecycle_summary"]
    assert history["resolved_lifecycles"] == 1
    assert history["pending_lifecycles"] == 1
    eth_ledger = next(
        row for row in report["hypothesis_ledger"] if row["symbol"] == "ETH"
    )
    assert eth_ledger["source_compatible_lifecycle_summary"] == history
    assert eth_ledger["resolved_lifecycles"] == 0
    exit_research = report["eth_exit_research_context"]
    assert exit_research["retained_maximum_hold_minutes"] == 720
    assert exit_research["opened_final_720m_ex_largest_positive"] is False
    assert exit_research["automatic_strategy_change"] is False
    assert exit_research["execution_authority"] == "none"
    lock = report["eth_profit_lock_context"]
    assert lock["historical_disposition"] == "rejected_in_both_source_partitions"
    assert lock["strategy_change_supported"] is False
    assert lock["execution_authority"] == "none"
    risk_lock = report["eth_risk_normalized_lock_context"]
    assert risk_lock["current_path_is_first_eth_activation"] is True
    minimum = risk_lock["minimum_additional_evidence"]
    assert eth_ledger["minimum_additional_evidence"] == minimum


def _assert_sp500_context(report: dict[str, object]) -> None:
    recovery = report["sp500_gap_recovery_context"]
    assert recovery["disposition"] == "OPEN_LIFECYCLE_CENSORED_DECISION_GAP"
    assert recovery["mark_risk_path_resolved"] is True
    assert recovery["prospective_decision_path_resolved"] is False
    assert recovery["full_lifecycle_path_resolved"] is False
    assert recovery["strategy_change_supported"] is False
    assert recovery["execution_authority"] == "none"
    sp500_ledger = next(
        row for row in report["hypothesis_ledger"] if row["symbol"] == "xyz:SP500"
    )
    assert sp500_ledger["status"] == "being_tested"
    assert sp500_ledger["evidence_state"] == "technically_censored"
    assert sp500_ledger["recovery_disposition"] == recovery["disposition"]
    assert sp500_ledger["mark_risk_path_resolved"] is True
    assert sp500_ledger["prospective_decision_path_resolved"] is False
    assert sp500_ledger["full_lifecycle_path_resolved"] is False
    history = recovery["mechanism_compatible_lifecycle_summary"]
    assert sp500_ledger["mechanism_compatible_lifecycle_summary"] == history
    assert sp500_ledger["resolved_lifecycles"] == 0


def test_parser_has_no_execution_or_secret_flags() -> None:
    """The V58 consolidation cannot arm, sign, or place an order."""
    module = _module()
    options = {action.dest for action in module.build_parser()._actions}

    forbidden = {"enabled", "i_accept_live_risk", "wallet", "private_key"}
    assert options.isdisjoint(forbidden)


def test_generator_identity_covers_eth_censoring_module() -> None:
    """Consolidated evidence must freeze its extracted censoring behavior."""
    paths = {str(path) for path in v58_continuous_generator_paths("script.py")}

    assert "src/hypervector/research/v58_eth_censored_context.py" in paths


def _module() -> ModuleType:
    assert _SCRIPT.is_file(), "V58 continuous-improvement script is missing"
    spec = spec_from_file_location("v58_continuous_improvement_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _args(tmp_path: Path, output: Path) -> SimpleNamespace:
    return SimpleNamespace(
        config=tmp_path / "config.toml",
        observer=tmp_path / "observer.json",
        live_checkpoint=tmp_path / "live-checkpoint.json",
        venue_preflight=tmp_path / "venue-preflight.json",
        btc=tmp_path / "btc.json",
        eth=tmp_path / "eth.json",
        hype=tmp_path / "hype.json",
        sp500=tmp_path / "sp500.json",
        brentoil=tmp_path / "brentoil.json",
        active_route_overrides=tmp_path / "active-routes.json",
        stress=tmp_path / "stress.json",
        eth_exit_journal=tmp_path / "eth-exit-journal.json",
        eth_exit_duration=tmp_path / "eth-exit-duration.json",
        eth_risk_lock_disposition=tmp_path / "eth-risk-lock-disposition.json",
        eth_duration_checkpoint=tmp_path / "eth-duration-checkpoint.json",
        eth_historical_funding_stress=tmp_path / "eth-funding-stress.json",
        btc_long_coverage_result=tmp_path / "btc-long-coverage-result.json",
        sp500_recovery=tmp_path / "sp500-recovery.json",
        sp500_recovery_journal=tmp_path / "sp500-recovery-journal.json",
        out=output,
        maximum_age_seconds=180.0,
        interval_seconds=120.0,
        max_cycles=1,
    )


def _observer() -> SuccessorObserverEvidence:
    return SuccessorObserverEvidence(
        status={
            "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
            "profile_fingerprint": "profile",
            "base_profile_fingerprint": "base-profile",
            "run_id": "run",
            "symbols": [
                "BTC",
                "ETH",
                "SOL",
                "HYPE",
                "xyz:SP500",
                "xyz:SPCX",
                "xyz:SNDK",
                "xyz:BRENTOIL",
            ],
            "freshness_status": "fresh",
            "technical_complete": True,
            "provider_symbol_routes": 10,
            "eligible_evaluations": 1,
            "strategy_intents": 1,
            "routed_actions": 0,
            "report_only": True,
            "execution_authority": "none",
        },
        evidence={"checkpoint": {"sha256": "a" * 64}},
    )


def _lifecycles() -> tuple[LifecycleEvidence, ...]:
    return (
        _lifecycle("BTC", "liquidity_sweep_long_1h_stop60_target60_v2|BTC"),
        _lifecycle(
            "ETH",
            "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
            pending=1,
        ),
        _lifecycle("HYPE", "hype_breakout_compression_alignment_bidirectional_v2|HYPE"),
        _lifecycle(
            "xyz:SP500",
            "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500",
            complete=False,
        ),
    )


def _lifecycle(
    symbol: str, route: str, *, pending: int = 0, complete: bool = True
) -> LifecycleEvidence:
    return LifecycleEvidence(
        symbol=symbol,
        route=route,
        state="awaiting_resolution",
        pending=pending,
        resolved=0,
        technical_complete=complete,
        source_age_seconds=1.0,
        evidence={"sha256": symbol},
    )


def _opportunities() -> RouteOpportunityCollection:
    routes = (
        "hulk_expansion_short_robust_v3|BTC",
        "hulk_expansion_short_tuned_v2|BTC",
        "liquidity_sweep_long_1h_stop60_target60_v2|BTC",
        "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
        "hulk_expansion_bidirectional_tuned_v2|SOL",
        "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500",
        "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX",
        "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:SNDK",
        "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL",
    )
    rows = tuple(
        RouteOpportunity(
            route=route,
            evaluations=1,
            eligible=0,
            first_fraction=0.5,
            minimum_fraction=0.5,
            mean_fraction=0.5,
            latest_fraction=0.5,
            maximum_fraction=0.5,
            progressions=0,
            regressions=0,
            state_transitions=0,
            unchanged=0,
            blocker_counts={"waiting": 1},
            reason_counts={"waiting": 1},
            latest_reason="waiting",
            latest_side=None,
            research_state="unresolved",
            confidence="low",
        )
        for route in routes
    )
    return RouteOpportunityCollection(rows, {"sha256": "routes"})


def _regimes() -> RegimeContextCollection:
    rows = tuple(
        RegimeContext(
            symbol=symbol,
            evaluations=1,
            observed_at_utc="2026-08-19T11:00:00+00:00",
            primary_regime="RANGE",
            context_15m="RANGE",
            state_1m="RANGE",
            state_5m="RANGE",
            confidence=0.25,
            readiness_side="short",
            readiness_fraction=2 / 3,
            blockers=("awaiting_hourly_sma_cross",),
        )
        for symbol in ("BTC", "ETH", "SOL", "HYPE")
    )
    return RegimeContextCollection(rows, {"sha256": "regimes"})


def _portfolio() -> PortfolioOpportunityContext:
    return PortfolioOpportunityContext(
        summary={
            "routing_cycles": 10,
            "prospective_evaluations": 20,
            "eligible_provider_events": 1,
            "executable_eligible_events": 1,
            "observe_only_eligible_events": 0,
            "eligible_symbols": 1,
            "maximum_concurrent_eligible_symbols": 1,
            "maximum_concurrent_margin_fraction": 0.03,
        },
        co_trigger_cycles=1,
        latest_co_trigger={"symbols": ["ETH"], "margin_fraction": 0.03},
        evidence={"sha256": "portfolio"},
    )


def _runtime() -> RuntimeContext:
    lag = ProviderArrivalLag("provider", 10, 1.0, 10.0, 27.0, 30.0, 3.0)
    return RuntimeContext(
        poll_cycles=100,
        successful_poll_cycles=99,
        degraded_poll_cycles=1,
        degraded_reasons={"timeout": 1},
        degraded_sources={"public_l2": 1},
        first_degraded_observed_at_utc="2026-08-19T08:29:05+00:00",
        last_degraded_observed_at_utc="2026-08-19T08:29:05+00:00",
        successful_polls_since_last_degraded=5,
        latest_poll_status="running",
        heartbeat={"count": 99, "minimum": 14.0, "mean": 15.0, "maximum": 16.0},
        provider_arrival_lags=(lag,),
        evidence={"sha256": "runtime"},
    )


def _returns() -> ReturnInteractionContext:
    return ReturnInteractionContext(
        payload={
            "common_completed_bars": 20,
            "one_minute_return_observations": 19,
            "five_minute_return_observations": 3,
        },
        evidence={"sha256": "returns"},
    )


def _liquidity() -> LiquidityContext:
    return LiquidityContext(
        payload={
            "synchronized_snapshot_count": 100,
            "minimum_both_complete_rate": 1.0,
        },
        evidence={"sha256": "liquidity"},
    )


def _eth_path() -> EthOpenPathContext:
    return EthOpenPathContext(
        payload={
            "state": "open",
            "maximum_favorable_excursion_bps": 25.0,
            "maximum_adverse_excursion_bps": 15.0,
            "source_compatible_lifecycle_summary": {
                "observed_lifecycles": 2,
                "resolved_lifecycles": 1,
                "pending_lifecycles": 1,
                "long_lifecycles": 2,
                "short_lifecycles": 0,
            },
        },
        evidence={"sha256": "eth-path"},
    )


def _funding() -> CurrentFundingContext:
    return CurrentFundingContext(
        payload={
            "status": "available",
            "routes_exceeding_frozen_adverse": 1,
            "maximum_current_to_frozen_adverse_ratio": 1.2,
        },
        evidence={"sha256": "funding"},
    )


def _eth_exit_research() -> EthExitResearchContext:
    return EthExitResearchContext(
        payload={
            "retained_maximum_hold_minutes": 720,
            "opened_final_720m_ex_largest_positive": False,
        },
        evidence={"sha256": "eth-exit-research"},
    )


def _eth_profit_lock() -> EthProfitLockContext:
    return EthProfitLockContext(
        payload={
            "historical_disposition": "rejected_in_both_source_partitions",
            "policies": {},
        },
        evidence={"sha256": "eth-profit-lock"},
    )


def _eth_risk_lock() -> EthRiskNormalizedLockContext:
    return EthRiskNormalizedLockContext(
        payload={
            "current_path_is_first_eth_activation": True,
            "lifecycle_state": "open",
            "side": "long",
            "historical_disposition": {"live_change_proposed": False},
        },
        evidence={"sha256": "eth-risk-lock"},
    )


def _sp500_recovery() -> SimpleNamespace:
    return SimpleNamespace(
        payload={
            "disposition": "OPEN_LIFECYCLE_CENSORED_DECISION_GAP",
            "mark_risk_path_resolved": True,
            "prospective_decision_path_resolved": False,
            "full_lifecycle_path_resolved": False,
            "missing_prospective_decision_boundaries_ms": [1787125500000],
            "minimum_additional_evidence": "new boundary evidence or lifecycle",
            "mechanism_compatible_lifecycle_summary": {
                "observed_lifecycles": 2,
                "resolved_lifecycles": 1,
                "technically_censored_lifecycles": 1,
                "short_lifecycles": 2,
                "long_lifecycles": 0,
                "pnl_aggregation_supported": False,
            },
        },
        evidence={"sha256": "sp500-recovery"},
        execution_authority="none",
    )
