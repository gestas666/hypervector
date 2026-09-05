"""Shared route/checkpoint fixtures for V58 continuous-improvement tests."""

from __future__ import annotations

from hypervector.research.v58_brentoil_continuous_context import (
    BrentoilContinuousContext,
)
from hypervector.research.v58_active_route_lifecycle_context import (
    V58ActiveRouteContext,
    V58RouteLifecycleItem,
)
from hypervector.research.v58_continuous_risk_context import RiskContext
from hypervector.research.v58_live_backend_context import LiveBackendContext
from hypervector.research.v58_execution_mandate_context import (
    ExecutionMandateContext,
)
from hypervector.research.v58_venue_state_context import VenueStateContext


def v58_venue_context() -> VenueStateContext:
    """Return one fresh, flat, identity-bound venue context fixture."""
    return VenueStateContext(
        observed_at_utc="2026-08-19T14:35:30+00:00",
        preflight_age_seconds=1.0,
        preflight_fresh=True,
        venue_flat_no_orders=True,
        venue_ledger_reconciled=True,
        venue_open_positions=0,
        venue_open_orders=0,
        actual_account_value_usd=4_875.84,
        maximum_sampled_account_value_usd=4_875.84,
        account_value_sampling_range_usd=0.0,
        sizing_reference_equity_usd=5_000.0,
        evidence={"sha256": "venue"},
    )


def v58_risk_context() -> RiskContext:
    """Return one internally reconciled frozen-reference risk fixture."""
    return RiskContext(
        payload={
            "account_value_usd": 5_000.0,
            "maximum_margin_fraction": 0.46,
            "maximum_margin_usd": 2_300.0,
            "maximum_gross_notional_usd": 16_500.0,
            "stacked_p99_stop_wave_loss_usd": 180.3,
            "stacked_p99_stop_wave_loss_pct_equity": 3.606,
        },
        evidence={"sha256": "risk"},
    )


def v58_backend_context() -> LiveBackendContext:
    """Return an explicit authority-none V58 context with no open positions."""
    return LiveBackendContext(
        profile_id="multi_asset_growth_first_5000_spcx_short_containment_v57",
        profile_fingerprint="7" * 64,
        run_id="bidirectional-live-1787065473571",
        lifecycle_state="backend_runtime_fault",
        backend_process_health="faulted",
        heartbeat_status="degraded",
        checkpoint_age_seconds=1.0,
        backend_event_age_seconds=20_000.0,
        last_event_type="runtime_fault",
        last_observed_at_utc="2026-08-19T07:54:57+00:00",
        runtime_fault_exception_type="ValueError",
        ledger_asset_states={"BTC": "FLAT", "HYPE": "FLAT", "xyz:SPCX": "FLAT"},
        ledger_last_snapshot_flat_order_free=True,
        evidence={"checkpoint": {"sha256": "backend"}},
        open_lifecycles={
            "execution_authority": "none",
            "actual_exit_fills_claimed": False,
            "open_lifecycles": 0,
            "trades": [],
        },
        closed_lifecycles={
            "execution_authority": "none",
            "closed_lifecycles": 0,
            "trades": [],
        },
    )


def v58_mandate_context() -> ExecutionMandateContext:
    """Return compact authority-none execution evidence for consolidation."""
    return ExecutionMandateContext(
        payload={
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "automatic_live_change": False,
            },
            "execution": {"status": "measured_zero_fills"},
        },
        evidence={"checkpoint": {"sha256": "backend"}},
    )


def v58_route(symbol: str) -> str:
    """Return one exact V58 provider-symbol route fixture."""
    return {
        "BTC_ROBUST": "hulk_expansion_short_robust_v3|BTC",
        "BTC_TUNED": "hulk_expansion_short_tuned_v2|BTC",
        "BTC_SWEEP": "liquidity_sweep_long_1h_stop60_target60_v2|BTC",
        "ETH": "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
        "SOL": "hulk_expansion_bidirectional_tuned_v2|SOL",
        "HYPE": "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
        "xyz:SP500": (
            "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500"
        ),
        "xyz:SPCX": "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX",
        "xyz:SNDK": (
            "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:SNDK"
        ),
        "xyz:BRENTOIL": (
            "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL"
        ),
    }[symbol]


def v58_route_keys() -> tuple[str, ...]:
    """Return the canonical order of V58 route-fixture keys."""
    return (
        "BTC_ROBUST",
        "BTC_TUNED",
        "BTC_SWEEP",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:BRENTOIL",
    )


def v58_observer_route_payload(run_id: str, profile: str) -> dict[str, object]:
    """Return one internally reconciled V58 readiness/scorecard payload."""
    readiness: dict[str, object] = {}
    scorecard: dict[str, object] = {}
    for key in v58_route_keys():
        route = v58_route(key)
        readiness[route] = {
            "count": 10,
            "eligible": 1 if key == "ETH" else 0,
            "first_fraction": 1.0 / 3.0,
            "minimum_fraction": 0.0,
            "mean_fraction": 0.46,
            "latest_fraction": 0.5,
            "maximum_fraction": 1.0 if key == "ETH" else 0.75,
            "latest_reason": "ready" if key == "ETH" else "entry_condition_absent",
            "latest_side": "long" if key == "ETH" else None,
            "progressions": 4,
            "regressions": 3,
            "state_transitions": 8,
            "unchanged": 2,
            "blockers": {
                "canonical_breakout_onset_absent": 9,
                "prior_compression_absent": 4,
            },
            "reasons": {
                "canonical_breakout_onset_absent": 9,
                "eth_breakout_transfer_ready": 1,
            },
        }
        scorecard[route] = {
            "research_state": "historical_candidate" if key == "ETH" else "unresolved",
            "confidence": "low",
        }
    return {
        "audit": {
            "run": {
                "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
                "profile_fingerprint": profile,
                "run_id": run_id,
            },
            "readiness": {"by_provider_symbol": readiness},
            "strategy_scorecard": {"by_provider_symbol": scorecard},
        }
    }


def v58_brentoil_context() -> BrentoilContinuousContext:
    """Return one exact open BRENTOIL watcher context."""
    return BrentoilContinuousContext(
        state="open_protected",
        pending=1,
        resolved=0,
        source_age_seconds=1.0,
        payload={
            "identity": {
                "lifecycle_id": "xyz:BRENTOIL:520642502465",
                "route": (
                    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
                    "|xyz:BRENTOIL"
                ),
            },
            "actual_live_lifecycle": {
                "actual_entry_fill_claimed": True,
                "actual_exit_fill_claimed": False,
            },
        },
        evidence={"sha256": "brentoil"},
    )


def v58_active_routes_context() -> V58ActiveRouteContext:
    """Return five fresh authority-none configured-route collectors."""
    keys = ("BTC_ROBUST", "BTC_TUNED", "SOL", "xyz:SPCX", "xyz:SNDK")
    items = tuple(
        V58RouteLifecycleItem(
            route=v58_route(key),
            symbol=v58_route(key).rsplit("|", maxsplit=1)[1],
            state="awaiting_short",
            pending=0,
            resolved=0,
            unresolved=0,
            source_age_seconds=1.0,
            evidence={"sha256": key},
        )
        for key in keys
    )
    return V58ActiveRouteContext(
        items=items,
        statuses=tuple({"route": item.route, "state": item.state} for item in items),
        evidence={"overrides": {"sha256": "active-routes"}},
        execution_authority="none",
    )
