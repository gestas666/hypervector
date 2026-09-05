"""BTC sweep capture coverage in the canonical V58 hypothesis ledger."""

from __future__ import annotations

from datetime import UTC, datetime

from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.v58_continuous_improvement import (
    LifecycleEvidence,
    RouteOpportunity,
    RouteOpportunityCollection,
    build_v58_continuous_improvement,
)

_BTC_SWEEP = "liquidity_sweep_long_1h_stop60_target60_v2|BTC"
_ROUTES = (
    "hulk_expansion_short_robust_v3|BTC",
    "hulk_expansion_short_tuned_v2|BTC",
    _BTC_SWEEP,
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
    "hulk_expansion_bidirectional_tuned_v2|SOL",
    "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500",
    "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX",
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:SNDK",
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL",
)


def test_btc_sweep_watcher_is_accounted_for_in_canonical_capture() -> None:
    """An attached exact watcher must not remain labeled as missing."""
    report = build_v58_continuous_improvement(
        _observer(),
        _lifecycle("BTC", _BTC_SWEEP),
        _lifecycle("ETH", _ROUTES[3], pending=1),
        _lifecycle("HYPE", _ROUTES[5]),
        _lifecycle("xyz:SP500", _ROUTES[6], complete=False),
        _opportunities(),
        generated_at=datetime(2026, 8, 19, 16, 0, tzinfo=UTC),
    )

    coverage = report["lifecycle_capture_coverage"]
    btc = next(row for row in coverage["routes"] if row["route"] == _BTC_SWEEP)
    assert coverage["watcher_count"] == 4
    assert btc == {
        "route": _BTC_SWEEP,
        "eligible_evaluations": 0,
        "watcher_attached": True,
        "status": "exact_lifecycle_watcher_attached",
    }
    ledger = next(
        row for row in report["hypothesis_ledger"] if row["route"] == _BTC_SWEEP
    )
    assert ledger["symbol"] == "BTC"
    assert ledger["status"] == "being_tested"


def _observer() -> SuccessorObserverEvidence:
    return SuccessorObserverEvidence(
        status={
            "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
            "profile_fingerprint": "profile",
            "run_id": "run",
            "freshness_status": "fresh",
            "technical_complete": True,
            "provider_symbol_routes": 10,
            "routed_actions": 0,
            "report_only": True,
            "execution_authority": "none",
        },
        evidence={"sha256": "observer"},
    )


def _lifecycle(
    symbol: str,
    route: str,
    *,
    pending: int = 0,
    complete: bool = True,
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
        for route in _ROUTES
    )
    return RouteOpportunityCollection(rows, {"sha256": "routes"})
