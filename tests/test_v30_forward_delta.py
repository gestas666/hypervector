"""Contracts for immutable v30 forward-readiness evidence deltas."""

from collections.abc import Callable
from importlib import import_module

import pytest


def _performance(
    *,
    closed: int,
    wins: int,
    losses: int,
    net: float,
) -> dict[str, object]:
    return {
        "closed_trades": closed,
        "wins": wins,
        "losses": losses,
        "fees_usd": 0.10 * closed,
        "funding_usd": -0.01 * closed,
        "net_pnl_usd": net,
        "profit_factor": 2.0 if losses else None,
    }


def _route(
    name: str,
    *,
    evaluations: int = 100,
    eligible: int = 0,
    resolved: int = 0,
    performance: dict[str, object] | None = None,
    sides: dict[str, object] | None = None,
    net_ex_largest: float | None = None,
) -> dict[str, object]:
    return {
        "route": name,
        "forward_evaluations": evaluations,
        "eligible_signals": eligible,
        "resolved_signal_horizons": resolved,
        "forward_assessment": "observed",
        "eligible_signal_horizons": {},
        "execution_performance": performance,
        "execution_performance_by_side": sides or {},
        "net_pnl_excluding_largest_winner_usd": net_ex_largest,
        "repeatability_evidence_state": (
            "observed" if performance is not None else "no_closed_execution"
        ),
    }


def _report(*, timestamp: str, routes: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "v30_live_forward_readiness_v1",
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "source_checkpoint_generated_at_utc": timestamp,
        "source_run": {
            "run_id": "run-1",
            "profile_id": "v25",
            "profile_fingerprint": "runtime-fingerprint",
        },
        "candidate": {
            "profile_id": "v30",
            "profile_fingerprint": "candidate-fingerprint",
            "symbols": ["ETH", "SOL", "xyz:SPCX"],
            "maximum_positions": 3,
            "executable_routes": sorted(str(row["route"]) for row in routes),
            "both_directions": True,
        },
        "routes": routes,
        "live_state": {
            "mode": "multi_asset_bidirectional_live_checkpoint",
            "transition_drain": {"status": "inactive"},
            "execution": {"closed_trades": 11},
            "portfolio": {"final_equity_usd": 504.0},
            "faults": 0,
            "open_positions": [{"symbol": "ETH", "protected_if_open": True}],
            "all_open_positions_protected": True,
        },
        "assessment": {
            "recommendation": "retain_v30_inactive_collect_exact_forward_evidence"
        },
    }


def _routes() -> list[dict[str, object]]:
    return [
        _route("range_onset_bidirectional_v1|ETH"),
        _route("range_onset_bidirectional_v1|SOL"),
        _route(
            "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX",
            eligible=2,
            resolved=2,
            performance=_performance(closed=1, wins=1, losses=0, net=0.6),
            sides={"long": {"closed_trades": 1}},
            net_ex_largest=-0.2,
        ),
    ]


def test_delta_reports_only_material_successor_evidence_changes() -> None:
    """New closes and side evidence must be separate from routine evaluations."""
    build = import_module(
        "hypervector.research.v30_forward_delta"
    ).build_v30_forward_delta
    before_routes = _routes()
    after_routes = _routes()
    after_routes[0]["forward_evaluations"] = 160
    after_routes[2].update(
        {
            "forward_evaluations": 160,
            "eligible_signals": 3,
            "resolved_signal_horizons": 3,
            "execution_performance": _performance(closed=2, wins=1, losses=1, net=0.3),
            "execution_performance_by_side": {
                "long": {"closed_trades": 1},
                "short": {"closed_trades": 1},
            },
            "net_pnl_excluding_largest_winner_usd": -0.3,
        }
    )
    before = _report(timestamp="2026-08-09T17:00:00Z", routes=before_routes)
    after = _report(timestamp="2026-08-09T18:00:00Z", routes=after_routes)

    delta = build(before, after)

    assert delta["contract"]["execution_authority"] == "none"
    assert delta["summary"] == {
        "evaluation_delta": 120,
        "eligible_signal_delta": 1,
        "resolved_signal_horizon_delta": 1,
        "closed_trade_delta": 1,
        "new_side_evidence": [
            "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX|short"
        ],
        "fault_delta": 0,
        "protection_degraded": False,
        "recommendation_changed": False,
        "open_position_count_before": 1,
        "open_position_count_after": 1,
        "flat_boundary_reached": False,
        "transition_state_changed": False,
        "transition_status_before": "inactive",
        "transition_status_after": "inactive",
    }
    spcx = next(row for row in delta["routes"] if row["route"].endswith("|xyz:SPCX"))
    assert spcx["closed_trade_delta"] == 1
    assert spcx["net_pnl_usd_delta"] == pytest.approx(-0.3)
    assert delta["assessment"]["material_evidence_change"] is True
    assert delta["assessment"]["journal_revision_recommended"] is True


def test_delta_does_not_treat_evaluation_cadence_as_material() -> None:
    """Routine completed-bar evaluations alone must not trigger a journal revision."""
    build = import_module(
        "hypervector.research.v30_forward_delta"
    ).build_v30_forward_delta
    before_routes = _routes()
    after_routes = _routes()
    for route in after_routes:
        route["forward_evaluations"] = 110

    delta = build(
        _report(timestamp="2026-08-09T17:00:00Z", routes=before_routes),
        _report(timestamp="2026-08-09T17:10:00Z", routes=after_routes),
    )

    assert delta["summary"]["evaluation_delta"] == 30
    assert delta["assessment"]["material_evidence_change"] is False
    assert delta["assessment"]["journal_revision_recommended"] is False


def test_delta_marks_flat_boundary_and_protection_degradation() -> None:
    """Lifecycle readiness and protection loss must be material operator events."""
    build = import_module(
        "hypervector.research.v30_forward_delta"
    ).build_v30_forward_delta
    before = _report(timestamp="2026-08-09T17:00:00Z", routes=_routes())
    flat_after = _report(timestamp="2026-08-09T18:00:00Z", routes=_routes())
    flat_after["live_state"]["open_positions"] = []

    flat_delta = build(before, flat_after)

    assert flat_delta["summary"]["flat_boundary_reached"] is True
    assert flat_delta["assessment"]["material_evidence_change"] is True
    assert flat_delta["assessment"]["journal_revision_recommended"] is True

    degraded_after = _report(timestamp="2026-08-09T18:00:00Z", routes=_routes())
    degraded_after["live_state"]["all_open_positions_protected"] = False
    degraded_delta = build(before, degraded_after)
    assert degraded_delta["summary"]["protection_degraded"] is True
    assert degraded_delta["assessment"]["journal_revision_recommended"] is True


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda report: report["source_run"].update(run_id="run-2"), "run_id"),
        (
            lambda report: report["candidate"].update(profile_fingerprint="changed"),
            "candidate profile_fingerprint",
        ),
        (
            lambda report: report["routes"][0].update(forward_evaluations=99),
            "forward_evaluations cannot move backwards",
        ),
        (
            lambda report: report["live_state"].update(faults=-1),
            "after faults must be a nonnegative integer",
        ),
    ],
)
def test_delta_rejects_incomparable_or_backward_reports(
    mutation: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    """Identity drift and backward cumulative counters must fail closed."""
    build = import_module(
        "hypervector.research.v30_forward_delta"
    ).build_v30_forward_delta
    before = _report(timestamp="2026-08-09T17:00:00Z", routes=_routes())
    after = _report(timestamp="2026-08-09T18:00:00Z", routes=_routes())
    mutation(after)

    with pytest.raises(ValueError, match=message):
        build(before, after)


def test_delta_rejects_economic_mutation_without_a_new_close() -> None:
    """Aggregate economics cannot change when closed-trade count is unchanged."""
    build = import_module(
        "hypervector.research.v30_forward_delta"
    ).build_v30_forward_delta
    before = _report(timestamp="2026-08-09T17:00:00Z", routes=_routes())
    after_routes = _routes()
    after_routes[2]["execution_performance"]["net_pnl_usd"] = 999.0
    after = _report(timestamp="2026-08-09T18:00:00Z", routes=after_routes)

    with pytest.raises(ValueError, match="economics changed without a new close"):
        build(before, after)
