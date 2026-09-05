"""Integration tests for V58 exact active-route lifecycle collectors."""

from __future__ import annotations

from pathlib import Path

from hypervector.research.v58_active_route_lifecycle_context import (
    V58ActiveRouteContext,
    V58RouteLifecycleItem,
)
import test_v58_continuous_improvement_script as base
import v58_continuous_improvement_fixtures as fixtures


def test_refresh_attaches_all_ten_route_collectors(tmp_path: Path) -> None:
    """The canonical report must expose complete configured-route coverage."""
    module = base._module()
    output = tmp_path / "latest.json"
    args = base._args(tmp_path, output)
    args.active_route_overrides = tmp_path / "active-routes.json"
    loaders = module._ContinuousLoaders(
        observer=lambda *_args, **_kwargs: base._observer(),
        lifecycle=lambda *_args, **_kwargs: base._lifecycles(),
        opportunity=lambda *_args, **_kwargs: base._opportunities(),
        active_routes=lambda *_args, **_kwargs: _active_routes(),
        regime=lambda *_args, **_kwargs: base._regimes(),
        portfolio=lambda *_args, **_kwargs: base._portfolio(),
        runtime=lambda *_args, **_kwargs: base._runtime(),
        backend=lambda *_args, **_kwargs: fixtures.v58_backend_context(),
        mandate=lambda *_args, **_kwargs: fixtures.v58_mandate_context(),
        brentoil=lambda *_args, **_kwargs: fixtures.v58_brentoil_context(),
        venue=lambda *_args, **_kwargs: fixtures.v58_venue_context(),
        returns=lambda *_args, **_kwargs: base._returns(),
        risk=lambda *_args, **_kwargs: fixtures.v58_risk_context(),
        liquidity=lambda *_args, **_kwargs: base._liquidity(),
        eth_path=lambda *_args, **_kwargs: base._eth_path(),
        funding=lambda *_args, **_kwargs: base._funding(),
        eth_exit=lambda *_args, **_kwargs: base._eth_exit_research(),
        eth_profit_lock=lambda *_args, **_kwargs: base._eth_profit_lock(),
        eth_risk_lock=lambda *_args, **_kwargs: base._eth_risk_lock(),
        sp500_recovery=lambda *_args, **_kwargs: base._sp500_recovery(),
    )

    report = module.refresh(args, loaders=loaders)

    coverage = report["lifecycle_capture_coverage"]
    assert coverage["watcher_count"] == 10
    assert coverage["eligible_without_exact_capture"] == 0
    assert len(report["active_route_lifecycle_context"]["statuses"]) == 5
    assert report["mandate_evidence"] == fixtures.v58_mandate_context().payload
    assert report["change_proposals"] == []


def _active_routes() -> V58ActiveRouteContext:
    items = tuple(_item(route, symbol) for route, symbol in _routes())
    return V58ActiveRouteContext(
        items=items,
        statuses=tuple({"route": item.route, "state": item.state} for item in items),
        evidence={"overrides": {"sha256": "a" * 64}},
        execution_authority="none",
    )


def _item(route: str, symbol: str) -> V58RouteLifecycleItem:
    return V58RouteLifecycleItem(
        route=route,
        symbol=symbol,
        state="awaiting_short",
        pending=0,
        resolved=0,
        unresolved=0,
        source_age_seconds=1.0,
        evidence={"sha256": route, "bytes": 1},
    )


def _routes() -> tuple[tuple[str, str], ...]:
    return (
        (fixtures.v58_route("BTC_ROBUST"), "BTC"),
        (fixtures.v58_route("BTC_TUNED"), "BTC"),
        (fixtures.v58_route("SOL"), "SOL"),
        (fixtures.v58_route("xyz:SPCX"), "xyz:SPCX"),
        (fixtures.v58_route("xyz:SNDK"), "xyz:SNDK"),
    )
