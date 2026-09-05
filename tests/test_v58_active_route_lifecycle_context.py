"""Canonical V58 context tests for exact active-route collectors."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime

from hypervector.research.v58_active_route_lifecycle_context import (
    V58ActiveRouteContext,
    V58RouteLifecycleItem,
    attach_v58_active_route_lifecycle_context,
)
from hypervector.research.v58_future_only_experiment_context import (
    V58FutureOnlyExperimentContext,
)


_ROUTES = (
    ("hulk_expansion_short_robust_v3|BTC", "BTC"),
    ("hulk_expansion_short_tuned_v2|BTC", "BTC"),
    ("hulk_expansion_bidirectional_tuned_v2|SOL", "SOL"),
    (
        "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX",
        "xyz:SPCX",
    ),
    (
        "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:SNDK",
        "xyz:SNDK",
    ),
)


def test_attaches_all_five_collectors_without_changing_authority() -> None:
    """The canonical ledger must stop claiming these collectors are absent."""
    report = _report()
    context = _context()

    attach_v58_active_route_lifecycle_context(report, context)

    coverage = report["lifecycle_capture_coverage"]
    assert coverage["watcher_count"] == 9
    assert coverage["eligible_without_exact_capture"] == 0
    for route, _symbol in _ROUTES:
        capture = next(row for row in coverage["routes"] if row["route"] == route)
        ledger = next(
            row for row in report["hypothesis_ledger"] if row["route"] == route
        )
        assert capture["watcher_attached"] is True
        assert capture["status"] == "exact_lifecycle_watcher_attached"
        assert ledger["watch_state"] == "awaiting_short"
        assert ledger["evidence_state"] == "awaiting_first_eligible_signal"
    assert report["active_route_lifecycle_context"]["execution_authority"] == "none"
    assert report["change_proposals"] == []


def test_active_context_attaches_future_only_experiment_ledger() -> None:
    """The central attachment must not orphan current exit experiments."""
    assert "experiments" in {field.name for field in fields(V58ActiveRouteContext)}
    context = replace(_context(), experiments=_future_context())
    report = _report()

    attach_v58_active_route_lifecycle_context(report, context)

    assert len(report["experiment_ledger"]) == 2
    assert report["future_only_experiment_context"]["experiment_count"] == 2
    assert set(report["evidence"]["experiments"]) == {
        "v58-sp500-lower-activation-profit-lock-future-only-v1",
        "v58-brentoil-profit-lock-future-only-v1",
    }


def _context() -> V58ActiveRouteContext:
    items = tuple(
        V58RouteLifecycleItem(
            route=route,
            symbol=symbol,
            state="awaiting_short",
            pending=0,
            resolved=0,
            unresolved=0,
            source_age_seconds=5.0,
            evidence={"path": f"{symbol}.json", "sha256": "a" * 64, "bytes": 1},
        )
        for route, symbol in _ROUTES
    )
    return V58ActiveRouteContext(
        items=items,
        statuses=tuple(
            {
                "route": item.route,
                "state": item.state,
                "pending_lifecycles": item.pending,
                "resolved_lifecycles": item.resolved,
            }
            for item in items
        ),
        evidence={"overrides": {"sha256": "b" * 64}},
        execution_authority="none",
    )


def _future_context() -> V58FutureOnlyExperimentContext:
    routes = (
        (
            "v58-sp500-lower-activation-profit-lock-future-only-v1",
            "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500",
        ),
        (
            "v58-brentoil-profit-lock-future-only-v1",
            "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL",
        ),
    )
    statuses = tuple(
        {
            "hypothesis_id": hypothesis_id,
            "route": route,
            "required_sides": ["long", "short"],
            "minimum_diagnostic_evidence_met": False,
        }
        for hypothesis_id, route in routes
    )
    evidence = {
        hypothesis_id: {"sha256": "c" * 64, "bytes": 1}
        for hypothesis_id, _route in routes
    }
    lineage = {
        routes[0][0]: {
            "hypothesis_id": "sp500-breakout-profit-lock-l2-proxy",
            "status": "reject",
            "decision": "Keep the current SP500 exit contract unchanged.",
            "falsifier": "Exact venue paths may update the proxy result.",
            "revisit_basis": (
                "exact_v3_live_source_and_fill_contract_replaces_v1_l2_midpoint_proxy"
            ),
            "new_evidence_scope": "future_only_both_sides_exact_costed_lifecycles",
            "source_evidence": {"sha256": "d" * 64, "bytes": 2},
        }
    }
    return V58FutureOnlyExperimentContext(statuses, evidence, "none", lineage)


def _report() -> dict[str, object]:
    routes = _all_routes()
    initially_attached = _initially_attached(routes)
    return {
        "generated_at_utc": datetime(2026, 8, 20, tzinfo=UTC).isoformat(),
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
        },
        "hypothesis_ledger": [
            {
                "route": route,
                "watch_state": (
                    "attached"
                    if route in initially_attached
                    else "watcher_not_attached"
                ),
            }
            for route in routes
        ],
        "lifecycle_capture_coverage": {
            "watcher_count": 4,
            "eligible_without_exact_capture": 0,
            "routes": [
                {
                    "route": route,
                    "watcher_attached": route in initially_attached,
                    "status": (
                        "exact_lifecycle_watcher_attached"
                        if route in initially_attached
                        else "awaiting_first_eligible_signal"
                    ),
                }
                for route in routes
            ],
        },
        "evidence": {"lifecycles": {}},
        "change_proposals": [],
    }


def _all_routes() -> list[str]:
    return [route for route, _symbol in _ROUTES] + [
        "liquidity_sweep_long_1h_stop60_target60_v2|BTC",
        "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
        "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500",
        "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL",
    ]


def _initially_attached(routes: list[str]) -> set[str]:
    brentoil = (
        "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL"
    )
    return set(routes) - set(_route_names()) - {brentoil}


def _route_names() -> tuple[str, ...]:
    return tuple(route for route, _symbol in _ROUTES)
