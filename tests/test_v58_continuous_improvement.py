"""Current, authority-none consolidation of the V58 research lane."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.report_only_lifecycle_watch import publish_watch_status
from hypervector.research.v58_continuous_improvement import (
    LifecycleEvidence,
    RouteOpportunity,
    RouteOpportunityCollection,
    V58LifecycleSources,
    build_v58_continuous_improvement,
    load_v58_route_opportunities,
    load_v58_lifecycle_evidence,
)
from v58_btc_sweep_status_fixtures import btc_sweep_status
from v58_continuous_improvement_fixtures import (
    v58_observer_route_payload,
    v58_route as _route,
    v58_route_keys as _route_keys,
)

_NOW = datetime(2026, 8, 19, 11, 0, tzinfo=UTC)
_RUN_ID = "bidirectional-observe-1787127644202"
_PROFILE = "24820e4bfad8a978a7b617a29dc0326f8fc0e583389b67e0219ce4ab5789c874"
_SOL_SIDES = {"long": 0, "short": 1}


def test_pending_eth_is_the_single_highest_value_investigation() -> None:
    """An actual open exact lifecycle outranks hypothetical route tuning."""
    report = build_v58_continuous_improvement(
        _observer(),
        _lifecycle("BTC", _route("BTC_SWEEP")),
        _lifecycle("ETH", _route("ETH"), pending=1),
        _lifecycle("HYPE", _route("HYPE")),
        _lifecycle("xyz:SP500", _route("xyz:SP500"), complete=False),
        _opportunities(),
        generated_at=_NOW,
    )

    assert report["highest_value_next_investigation"] == {
        "route": _route("ETH"),
        "experiment": "resolve_open_exact_lifecycle",
        "why_now": "one source-compatible lifecycle is open under frozen exits",
    }
    assert report["change_proposals"] == []
    assert report["contract"]["execution_authority"] == "none"
    assert report["assessment"]["automatic_live_change"] is False
    assert len(report["hypothesis_ledger"]) == 10
    assert {row["status"] for row in report["hypothesis_ledger"]} == {"being_tested"}
    assert {row["route"] for row in report["hypothesis_ledger"]} == {
        item.route for item in _opportunities().opportunities
    }


def test_resolved_lifecycle_requires_review_without_automatic_promotion() -> None:
    """Resolution creates analysis work, never execution authority."""
    report = build_v58_continuous_improvement(
        _observer(),
        _lifecycle("BTC", _route("BTC_SWEEP")),
        _lifecycle("ETH", _route("ETH"), resolved=1),
        _lifecycle("HYPE", _route("HYPE")),
        _lifecycle("xyz:SP500", _route("xyz:SP500"), complete=False),
        _opportunities(),
        generated_at=_NOW,
    )

    highest = report["highest_value_next_investigation"]
    assert highest["experiment"] == "review_resolved_exact_lifecycle"
    assert report["change_proposals"] == []
    assert report["assessment"]["evidence_sufficient_for_change"] is False


def test_unwatched_eligible_route_becomes_immediate_capture_priority() -> None:
    """A sparse eligible event cannot pass without an exact lifecycle lane."""
    base = _opportunities()
    sol_route = _route("SOL")
    rows = tuple(
        replace(
            item,
            eligible=1 if item.route == sol_route else 0,
            eligible_by_side=_SOL_SIDES if item.route == sol_route else None,
        )
        for item in base.opportunities
    )
    report = build_v58_continuous_improvement(
        _observer(),
        _lifecycle("BTC", _route("BTC_SWEEP")),
        _lifecycle("ETH", _route("ETH"), pending=1),
        _lifecycle("HYPE", _route("HYPE")),
        _lifecycle("xyz:SP500", _route("xyz:SP500"), complete=False),
        RouteOpportunityCollection(rows, base.evidence),
        generated_at=_NOW,
    )

    assert report["highest_value_next_investigation"] == {
        "route": sol_route,
        "experiment": "attach_exact_lifecycle_capture",
        "why_now": "an executable eligible signal has no exact lifecycle watcher",
    }
    coverage = report["lifecycle_capture_coverage"]
    assert coverage["eligible_without_exact_capture"] == 1
    sol = next(row for row in coverage["routes"] if row["route"] == sol_route)
    assert sol["status"] == "eligible_without_exact_lifecycle_capture"
    assert sol["watcher_attached"] is False
    assert coverage["execution_authority"] == "none"


def test_builder_rejects_route_alias_and_nonfinite_freshness() -> None:
    """Exact lifecycle identity and bounded staleness cannot be bypassed."""
    with pytest.raises(ValueError, match="route identity"):
        build_v58_continuous_improvement(
            _observer(),
            _lifecycle("BTC", _route("BTC_SWEEP")),
            _lifecycle("ETH", "wrong-route", pending=1),
            _lifecycle("HYPE", _route("HYPE")),
            _lifecycle("xyz:SP500", _route("xyz:SP500"), complete=False),
            _opportunities(),
            generated_at=_NOW,
        )


def test_route_pipeline_preserves_readiness_without_calling_it_edge(
    tmp_path: Path,
) -> None:
    """All ten route opportunities remain visible with research caveats."""
    source = tmp_path / "observer.json"
    source.write_text(
        json.dumps(v58_observer_route_payload(_RUN_ID, _PROFILE)), encoding="utf-8"
    )

    collection = load_v58_route_opportunities(
        source, observer_status=_observer().status
    )
    report = build_v58_continuous_improvement(
        _observer(),
        _lifecycle("BTC", _route("BTC_SWEEP")),
        _lifecycle("ETH", _route("ETH"), pending=1),
        _lifecycle("HYPE", _route("HYPE")),
        _lifecycle("xyz:SP500", _route("xyz:SP500"), complete=False),
        collection,
        generated_at=_NOW,
    )

    assert len(report["opportunity_pipeline"]) == 10
    eth = next(row for row in collection.opportunities if row.route == _route("ETH"))
    assert eth.eligible == 1
    assert eth.research_state == "historical_candidate"
    pipeline_eth = next(
        row for row in report["opportunity_pipeline"] if row["route"] == _route("ETH")
    )
    assert pipeline_eth["readiness_distribution"] == {
        "first_fraction": 1.0 / 3.0,
        "minimum_fraction": 0.0,
        "mean_fraction": 0.46,
        "maximum_fraction": 1.0,
        "progressions": 4,
        "regressions": 3,
        "state_transitions": 8,
        "unchanged": 2,
    }
    assert pipeline_eth["blocker_counts"] == {
        "canonical_breakout_onset_absent": 9,
        "prior_compression_absent": 4,
    }
    assert pipeline_eth["reason_counts"] == {
        "canonical_breakout_onset_absent": 9,
        "eth_breakout_transfer_ready": 1,
    }
    assert pipeline_eth["observed_eligible_rate"] == 0.1
    assert pipeline_eth["frequency_claimed"] is False
    assert report["evidence"]["route_opportunities"] == collection.evidence


def test_route_pipeline_rejects_missing_or_invalid_readiness(tmp_path: Path) -> None:
    """A partial or success-shaped route matrix cannot look current."""
    payload = v58_observer_route_payload(_RUN_ID, _PROFILE)
    readiness = payload["audit"]["readiness"]["by_provider_symbol"]
    assert isinstance(readiness, dict)
    readiness.pop(_route("SOL"))
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="route set"):
        load_v58_route_opportunities(source, observer_status=_observer().status)

    payload = v58_observer_route_payload(_RUN_ID, _PROFILE)
    readiness = payload["audit"]["readiness"]["by_provider_symbol"]
    assert isinstance(readiness, dict)
    row = readiness[_route("HYPE")]
    assert isinstance(row, dict)
    row["latest_fraction"] = 1.5
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="readiness fraction"):
        load_v58_route_opportunities(source, observer_status=_observer().status)

    payload = v58_observer_route_payload(_RUN_ID, _PROFILE)
    readiness = payload["audit"]["readiness"]["by_provider_symbol"]
    assert isinstance(readiness, dict)
    row = readiness[_route("ETH")]
    assert isinstance(row, dict)
    row["reasons"] = {"canonical_breakout_onset_absent": 8, "ready": 1}
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="reason counts must reconcile"):
        load_v58_route_opportunities(source, observer_status=_observer().status)

    sources = V58LifecycleSources(Path("btc"), Path("eth"), Path("hype"), Path("sp500"))
    with pytest.raises(ValueError, match="maximum lifecycle age"):
        load_v58_lifecycle_evidence(
            sources,
            observer_status=_observer().status,
            observed_at=_NOW,
            maximum_age_seconds=float("inf"),
        )


def test_route_pipeline_rejects_inconsistent_readiness_distribution(
    tmp_path: Path,
) -> None:
    """Summary fractions must describe one internally ordered distribution."""
    payload = v58_observer_route_payload(_RUN_ID, _PROFILE)
    readiness = payload["audit"]["readiness"]["by_provider_symbol"]
    assert isinstance(readiness, dict)
    row = readiness[_route("ETH")]
    assert isinstance(row, dict)
    row["minimum_fraction"] = 0.9
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="readiness distribution is inconsistent"):
        load_v58_route_opportunities(source, observer_status=_observer().status)


def test_loader_normalizes_exact_current_watcher_contracts(tmp_path: Path) -> None:
    """Heterogeneous watcher schemas must reconcile to one honest ledger."""
    sources = _write_sources(tmp_path)

    loaded = load_v58_lifecycle_evidence(
        sources,
        observer_status=_observer().status,
        observed_at=_NOW,
        maximum_age_seconds=180.0,
    )

    assert [item.route for item in loaded] == [
        "liquidity_sweep_long_1h_stop60_target60_v2|BTC",
        "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
        "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500",
    ]
    assert loaded[1].pending == 1
    assert loaded[2].pending == 0
    assert loaded[3].technical_complete is False


def test_prior_eth_censor_does_not_hide_current_complete_pending_path(
    tmp_path: Path,
) -> None:
    """Current research priority follows the latest lifecycle, not old gaps."""
    sources = _write_sources(tmp_path)
    payload = json.loads(sources.eth.read_text(encoding="utf-8"))
    payload["latest_attempts"] = [_censored_eth_attempt(), _pending_eth_attempt()]
    payload["latest_executions"] = []
    payload["summary"] = {
        "selected_non_overlapping": 2,
        "pending": 1,
        "resolved": 0,
        "technical_incomplete": 1,
    }
    sources.eth.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_v58_lifecycle_evidence(
        sources,
        observer_status=_observer().status,
        observed_at=_NOW,
        maximum_age_seconds=180.0,
    )
    report = build_v58_continuous_improvement(
        _observer(), *loaded, _opportunities(), generated_at=_NOW
    )

    assert loaded[1].technical_complete is True
    assert report["highest_value_next_investigation"]["route"] == _route("ETH")
    assert report["highest_value_next_investigation"]["experiment"] == (
        "resolve_open_exact_lifecycle"
    )


def test_loader_rejects_live_authority_or_stale_status(tmp_path: Path) -> None:
    """Unsafe or stale lifecycle bytes cannot enter a current V58 digest."""
    sources = _write_sources(tmp_path)
    eth = json.loads(sources.eth.read_text(encoding="utf-8"))
    eth["contract"]["execution_authority"] = "live"
    sources.eth.write_text(json.dumps(eth), encoding="utf-8")

    with pytest.raises(ValueError, match="authority"):
        load_v58_lifecycle_evidence(
            sources,
            observer_status=_observer().status,
            observed_at=_NOW,
            maximum_age_seconds=180.0,
        )


def test_loader_rejects_unverifiable_resolved_snapshot(tmp_path: Path) -> None:
    """Resolved status text cannot substitute for matching evidence bytes."""
    sources = _write_sources(tmp_path)
    report = _depth_payload("ETH", pending=0)
    report["state"] = "descriptive_exact_depth_evidence"
    report["summary"] = {"pending": 0, "resolved": 1, "technical_incomplete": 0}
    status = publish_watch_status(
        report, status_path=sources.eth, snapshot_dir=tmp_path, run_id=_RUN_ID
    )
    status["observed_at_utc"] = (_NOW - timedelta(seconds=10)).isoformat()
    status["summary"]["technical_incomplete"] = 1
    sources.eth.write_text(json.dumps(status), encoding="utf-8")

    with pytest.raises(ValueError, match="snapshot state"):
        load_v58_lifecycle_evidence(
            sources,
            observer_status=_observer().status,
            observed_at=_NOW,
            maximum_age_seconds=180.0,
        )

    sources = _write_sources(tmp_path)
    hype = json.loads(sources.hype.read_text(encoding="utf-8"))
    hype["observed_at_utc"] = (_NOW - timedelta(minutes=4)).isoformat()
    sources.hype.write_text(json.dumps(hype), encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        load_v58_lifecycle_evidence(
            sources,
            observer_status=_observer().status,
            observed_at=_NOW,
            maximum_age_seconds=180.0,
        )


def _observer() -> SuccessorObserverEvidence:
    return SuccessorObserverEvidence(
        status={
            "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
            "profile_fingerprint": _PROFILE,
            "run_id": _RUN_ID,
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


def _lifecycle(
    symbol: str,
    route: str,
    *,
    pending: int = 0,
    resolved: int = 0,
    complete: bool = True,
) -> LifecycleEvidence:
    return LifecycleEvidence(
        symbol=symbol,
        route=route,
        state="awaiting_resolution" if not resolved else "resolved",
        pending=pending,
        resolved=resolved,
        technical_complete=complete,
        source_age_seconds=1.0,
        evidence={"sha256": symbol},
    )


def _opportunities() -> RouteOpportunityCollection:
    rows = tuple(
        RouteOpportunity(
            route=_route(key),
            evaluations=10,
            eligible=1 if key == "ETH" else 0,
            first_fraction=1.0 / 3.0,
            minimum_fraction=0.0,
            mean_fraction=0.46,
            latest_fraction=0.5,
            maximum_fraction=1.0 if key == "ETH" else 0.75,
            progressions=4,
            regressions=3,
            state_transitions=8,
            unchanged=2,
            blocker_counts={"canonical_breakout_onset_absent": 9},
            reason_counts={"entry_condition_absent": 10},
            latest_reason="ready" if key == "ETH" else "entry_condition_absent",
            latest_side="long" if key == "ETH" else None,
            research_state="historical_candidate" if key == "ETH" else "unresolved",
            confidence="low",
        )
        for key in _route_keys()
    )
    return RouteOpportunityCollection(rows, {"sha256": "routes"})


def _write_sources(tmp_path: Path) -> V58LifecycleSources:
    btc = tmp_path / "btc.json"
    eth = tmp_path / "eth.json"
    hype = tmp_path / "hype.json"
    sp500 = tmp_path / "sp500.json"
    btc.write_text(
        json.dumps(btc_sweep_status(_NOW, _RUN_ID, _PROFILE)), encoding="utf-8"
    )
    eth.write_text(json.dumps(_depth_payload("ETH", pending=1)), encoding="utf-8")
    hype.write_text(json.dumps(_depth_payload("HYPE", pending=0)), encoding="utf-8")
    sp500.write_text(json.dumps(_sp500_payload()), encoding="utf-8")
    return V58LifecycleSources(btc=btc, eth=eth, hype=hype, sp500=sp500)


def _depth_payload(symbol: str, *, pending: int) -> dict[str, object]:
    strategy = {
        "ETH": "eth_breakout_precompression_pullback_bidirectional_v1",
        "HYPE": "hype_breakout_compression_alignment_bidirectional_v2",
    }[symbol]
    return {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
        "state": "awaiting_resolution",
        "watch_state": "awaiting_resolution",
        "observed_at_utc": (_NOW - timedelta(seconds=10)).isoformat(),
        "snapshot": None,
        "identity": {
            "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
            "profile_fingerprint": _PROFILE,
            "source_run_id": _RUN_ID,
        },
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
            "actual_orders_or_fills_claimed": False,
            "source_run_id": _RUN_ID,
            "source_strategy_id": strategy,
            "symbol": symbol,
        },
        "summary": {"pending": pending, "resolved": 0, "technical_incomplete": 0},
    }


def _censored_eth_attempt() -> dict[str, object]:
    return {
        "status": "active_book_path_gap",
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "candidate_strategy_id": (
            "eth_breakout_precompression_pullback_bidirectional_v1_v55_forward"
        ),
        "symbol": "ETH",
        "source_run_id": _RUN_ID,
        "side": "long",
        "decision_time_ms": 100,
        "entry_time_ms": 200,
        "entry_price": 100.0,
        "position_quantity": 1.0,
        "current_exit_time_ms": 600,
        "deadline_time_ms": 900,
        "active_book_gap_start_ms": 300,
        "active_book_gap_end_ms": 500,
        "maximum_active_book_gap_ms": 200,
        "maximum_allowed_active_book_gap_ms": 100,
    }


def _pending_eth_attempt() -> dict[str, object]:
    return {"status": "exit_pending", "decision_time_ms": 1_000}


def _sp500_payload() -> dict[str, object]:
    return {
        "schema_version": "sp500_fresh15_lifecycle_watch_status_v1",
        "symbol": "xyz:SP500",
        "observed_at_ms": int((_NOW - timedelta(seconds=10)).timestamp() * 1000),
        "watch_state": "LIFECYCLE_REPLAY_CANDIDATE_DUE",
        "lifecycle_replay_candidate_due": True,
        "trigger_reasons": ["profit_lock_source_gap"],
        "nominal": {"summary": {"resolved": 0, "censored": 1}},
        "technical_assessment": {"all_observed_paths_resolved": False},
        "report_only": True,
        "execution_authority": "none",
        "orders_supported": False,
        "signing_client_constructed": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
