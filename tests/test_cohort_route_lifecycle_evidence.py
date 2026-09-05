"""Exact-route prospective lifecycle evidence tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hypervector.research.cohort_route_lifecycle_evidence import (
    RouteLifecycleBoundary,
    RouteLifecycleIdentity,
    build_route_lifecycle_status,
)


_RUN = "bidirectional-live-1787065473571"
_PROFILE = "multi_asset_growth_first_5000_spcx_short_containment_v57"
_FINGERPRINT = "7" * 64
_PROVIDER = "hype_breakout_compression_alignment_bidirectional_v2"
_SIGNAL = "hype_breakout_compression_pullback_bidirectional_v1"
_SYMBOL = "HYPE"
_NOW = datetime(2026, 8, 18, 20, 1, tzinfo=UTC)


def test_quiet_route_reports_both_sides_pending_without_authority() -> None:
    """A quiet route must remain diagnostic and show exact readiness."""
    report = build_route_lifecycle_status(
        _checkpoint(eligible=0),
        _identity(),
        boundary=_boundary(),
        observed_at=_NOW,
    )

    assert report["state"] == "awaiting_both_sides"
    assert report["contract"]["execution_authority"] == "none"
    assert report["route_readiness"]["evaluations"] == 304
    assert report["route_readiness"]["eligible"] == 0
    assert report["route_readiness"]["prospective_evaluations"] == 4
    assert report["route_readiness"]["prospective_eligible"] == 0
    assert report["side_progress"]["long"]["resolved_lifecycles"] == 0
    assert report["side_progress"]["short"]["resolved_lifecycles"] == 0
    assert report["minimum_diagnostic_evidence_met"] is False


def test_one_resolved_long_keeps_short_side_pending() -> None:
    """One direction cannot satisfy a bidirectional evidence requirement."""
    report = build_route_lifecycle_status(
        _checkpoint(eligible=1, closed=[_closed_trade("long")]),
        _identity(),
        boundary=_boundary(),
        observed_at=_NOW,
    )

    assert report["state"] == "awaiting_short"
    assert report["side_progress"]["long"]["resolved_lifecycles"] == 1
    assert report["side_progress"]["short"]["resolved_lifecycles"] == 0
    assert report["minimum_diagnostic_evidence_met"] is False


def test_both_resolved_sides_preserve_exact_economics_and_protection() -> None:
    """The completed diagnostic must retain every required live field."""
    report = build_route_lifecycle_status(
        _checkpoint(
            eligible=2,
            closed=[_closed_trade("long"), _closed_trade("short")],
        ),
        _identity(),
        boundary=_boundary(),
        observed_at=_NOW,
    )

    assert report["state"] == "diagnostic_minimum_complete"
    assert report["minimum_diagnostic_evidence_met"] is True
    assert len(report["resolved_lifecycles"]) == 2
    short = report["resolved_lifecycles"][1]
    assert short["side"] == "short"
    assert short["protection"] == {"oid": 3002, "trigger_price": 59.4}
    assert short["costs"] == {
        "entry_slippage_bps": 1.5,
        "exit_slippage_bps": -0.5,
        "fees_usd": 4.2,
        "funding_usd": 0.3,
    }
    assert short["outcome"]["net_pnl_usd"] == 12.5
    assert short["outcome"]["maximum_favorable_excursion_bps"] == 120.0
    assert short["outcome"]["maximum_adverse_excursion_bps"] == 20.0
    assert short["outcome"]["peak_giveback_bps"] == 30.0
    assert short["exit_attribution"]["exit_reason"] == "maximum_hold_seconds"


def test_unattributed_eligible_evaluation_is_explicit_not_side_credited() -> None:
    """An eligible evaluation without a lifecycle cannot invent a side result."""
    report = build_route_lifecycle_status(
        _checkpoint(eligible=1),
        _identity(),
        boundary=_boundary(),
        observed_at=_NOW,
    )

    assert report["route_readiness"]["unattributed_eligible_evaluations"] == 1
    assert report["side_progress"]["long"]["attributable_entries"] == 0
    assert report["side_progress"]["short"]["attributable_entries"] == 0
    assert report["state"] == "eligible_evidence_unattributed"


def test_open_lifecycle_missing_protection_is_technical_evidence_pending() -> None:
    """A live entry without stop evidence must surface a technical fault state."""
    opened = _open_trade("long")
    del opened["protective_stop"]

    report = build_route_lifecycle_status(
        _checkpoint(eligible=1, opened=[opened]),
        _identity(),
        boundary=_boundary(),
        observed_at=_NOW,
    )

    lifecycle = report["open_lifecycles"][0]
    assert lifecycle["missing_evidence_fields"] == ["protective_stop"]
    assert report["state"] == "technical_evidence_pending"


def test_incomplete_closed_reflection_does_not_count_as_resolved() -> None:
    """Missing excursion evidence must remain visibly unresolved."""
    trade = _closed_trade("long")
    del trade["completed_hold_capture"]
    report = build_route_lifecycle_status(
        _checkpoint(eligible=1, closed=[trade]),
        _identity(),
        boundary=_boundary(),
        observed_at=_NOW,
    )

    assert report["resolved_lifecycles"] == []
    assert report["unresolved_lifecycles"][0]["missing_evidence_fields"] == [
        "completed_hold_capture"
    ]
    assert report["state"] == "technical_evidence_pending"


def test_missing_fill_leaf_cannot_count_as_resolved() -> None:
    """Leaf validation must finish before a lifecycle is marked resolved."""
    trade = _closed_trade("long")
    del trade["entry"]["price"]

    report = build_route_lifecycle_status(
        _checkpoint(eligible=1, closed=[trade]),
        _identity(),
        boundary=_boundary(),
        observed_at=_NOW,
    )

    lifecycle = report["closed_lifecycles"][0]
    assert lifecycle["fully_resolved"] is False
    assert "entry.price" in lifecycle["missing_evidence_fields"]
    assert report["resolved_lifecycles"] == []
    assert report["state"] == "technical_evidence_pending"


def test_profile_or_route_identity_drift_fails_closed() -> None:
    """A successor or alternate HYPE route cannot inherit V57 evidence."""
    checkpoint = _checkpoint(eligible=0)
    checkpoint["audit"]["run"]["profile_fingerprint"] = "8" * 64

    with pytest.raises(ValueError, match="profile fingerprint"):
        build_route_lifecycle_status(
            checkpoint, _identity(), boundary=_boundary(), observed_at=_NOW
        )


def test_multiple_hype_routes_fail_unique_attribution() -> None:
    """One signal implementation cannot be aliased across two live providers."""
    checkpoint = _checkpoint(eligible=0)
    checkpoint["audit"]["run"]["executable_provider_symbols"].append(
        "another_hype_provider|HYPE"
    )

    with pytest.raises(ValueError, match="unique provider"):
        build_route_lifecycle_status(
            checkpoint, _identity(), boundary=_boundary(), observed_at=_NOW
        )


def test_direct_signal_provider_allows_other_routes_on_same_symbol() -> None:
    """An exact provider-signal identity remains attributable on shared BTC."""
    checkpoint = _checkpoint(eligible=0)
    checkpoint["audit"]["run"]["executable_provider_symbols"].append(
        "another_btc_provider|HYPE"
    )
    direct = RouteLifecycleIdentity(
        run_id=_RUN,
        profile_id=_PROFILE,
        profile_fingerprint=_FINGERPRINT,
        provider_id=_PROVIDER,
        signal_strategy_id=_PROVIDER,
        symbol=_SYMBOL,
        required_sides=("long", "short"),
    )

    report = build_route_lifecycle_status(
        checkpoint, direct, boundary=_boundary(), observed_at=_NOW
    )

    assert report["state"] == "awaiting_both_sides"


def test_short_only_route_reports_its_required_side_pending() -> None:
    """Single-side execution must not require a nonexistent long progress row."""
    checkpoint = _checkpoint(eligible=0)
    route = f"{_PROVIDER}|{_SYMBOL}"
    checkpoint["configuration_generation"]["current_provider_execution_directions"][
        route
    ] = ["short"]
    short_only = RouteLifecycleIdentity(
        run_id=_RUN,
        profile_id=_PROFILE,
        profile_fingerprint=_FINGERPRINT,
        provider_id=_PROVIDER,
        signal_strategy_id=_SIGNAL,
        symbol=_SYMBOL,
        required_sides=("short",),
    )

    report = build_route_lifecycle_status(
        checkpoint, short_only, boundary=_boundary(), observed_at=_NOW
    )

    assert report["state"] == "awaiting_short"
    assert set(report["side_progress"]) == {"short"}


def test_stale_checkpoint_fails_before_publishing_progress() -> None:
    """Old projections cannot masquerade as a current live observation."""
    with pytest.raises(ValueError, match="stale"):
        build_route_lifecycle_status(
            _checkpoint(eligible=0),
            _identity(),
            boundary=_boundary(),
            observed_at=datetime(2026, 8, 18, 20, 5, tzinfo=UTC),
            maximum_checkpoint_age_seconds=90.0,
        )


def test_pre_activation_decision_and_readiness_are_not_prospective_evidence() -> None:
    """Run history before the frozen boundary cannot satisfy either side."""
    before = _closed_trade("long")
    before["entry_context"]["signal_provider"]["decision_time_ms"] = 700
    after = _closed_trade("short")
    report = build_route_lifecycle_status(
        _checkpoint(eligible=2, closed=[before, after]),
        _identity(),
        boundary=RouteLifecycleBoundary(
            capture_start_ms=800,
            baseline_evaluations=302,
            baseline_eligible=1,
        ),
        observed_at=_NOW,
    )

    assert [row["side"] for row in report["closed_lifecycles"]] == ["short"]
    assert report["route_readiness"]["prospective_evaluations"] == 2
    assert report["route_readiness"]["prospective_eligible"] == 1
    assert report["side_progress"]["long"]["resolved_lifecycles"] == 0
    assert report["state"] == "awaiting_long"


def _identity() -> RouteLifecycleIdentity:
    return RouteLifecycleIdentity(
        run_id=_RUN,
        profile_id=_PROFILE,
        profile_fingerprint=_FINGERPRINT,
        provider_id=_PROVIDER,
        signal_strategy_id=_SIGNAL,
        symbol=_SYMBOL,
        required_sides=("long", "short"),
    )


def _boundary() -> RouteLifecycleBoundary:
    return RouteLifecycleBoundary(
        capture_start_ms=800,
        baseline_evaluations=300,
        baseline_eligible=0,
    )


def _checkpoint(
    *,
    eligible: int,
    closed: list[dict[str, object]] | None = None,
    opened: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    contract = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
    route = f"{_PROVIDER}|{_SYMBOL}"
    return {
        "generated_at_utc": "2026-08-18T20:00:30+00:00",
        "checkpoint_contract": contract,
        "lifecycle": {
            "state": "running_consistent",
            "backend_process_health": "healthy",
        },
        "configuration_generation": {
            "matches_runtime": True,
            "current_profile_fingerprint": _FINGERPRINT,
            "runtime_profile_fingerprint": _FINGERPRINT,
            "current_provider_execution_directions": {route: ["long", "short"]},
        },
        "audit": {
            "experiment_contract": contract,
            "run": {
                "run_id": _RUN,
                "profile_id": _PROFILE,
                "profile_fingerprint": _FINGERPRINT,
                "executable_provider_symbols": [route],
            },
            "readiness": {
                "by_provider_symbol": {route: {"count": 304, "eligible": eligible}}
            },
            "trade_reflections": {"trades": closed or []},
            "open_trade_reflections": {"trades": opened or []},
        },
    }


def _closed_trade(side: str) -> dict[str, object]:
    is_long = side == "long"
    entry_oid = 1001 if is_long else 1002
    return {
        "lifecycle_id": f"HYPE:{entry_oid}",
        "source_run_id": _RUN,
        "source_profile_fingerprint": _FINGERPRINT,
        "symbol": _SYMBOL,
        "side": side,
        "entry_strategy_id": _SIGNAL,
        "entry_oid": entry_oid,
        "entry_margin_used_usd": 500.0,
        "leverage": 10.0,
        "entry": {
            "price": 60.0,
            "size": 80.0,
            "slippage_bps": 1.5,
            "venue_timestamp_ms": 1_000,
        },
        "entry_context": {
            "signal_provider": {
                "strategy_id": _SIGNAL,
                "eligible": True,
                "side": side,
                "decision_action": f"enter_{side}",
                "decision_time_ms": 900,
            }
        },
        "protective_stop": {
            "oid": 3001 if is_long else 3002,
            "trigger_price": 59.4,
        },
        "exit": {
            "price": 59.0,
            "size": 80.0,
            "slippage_bps": -0.5,
            "venue_timestamp_ms": 10_000,
        },
        "exit_oid": 4001 if is_long else 4002,
        "exit_reason": "maximum_hold_seconds",
        "exit_controller_strategy_id": "cohort_maximum_hold",
        "cross_provider_exit": False,
        "holding_time_ms": 9_000,
        "fees_usd": 4.2,
        "funding_usd": 0.3,
        "net_pnl_usd": 12.5,
        "net_return_on_margin_pct": 2.5,
        "completed_hold_capture": _hold_capture(),
    }


def _open_trade(side: str) -> dict[str, object]:
    closed = _closed_trade(side)
    return {
        "lifecycle_id": closed["lifecycle_id"],
        "source_run_id": closed["source_run_id"],
        "symbol": closed["symbol"],
        "strategy_id": closed["entry_strategy_id"],
        "side": closed["side"],
        "entry": closed["entry"],
        "entry_context": closed["entry_context"],
        "protective_stop": closed["protective_stop"],
        "holding_time_ms": 5_000,
        "marked_economics": {"mark_price": 60.5},
        "exit_plan": {"maximum_hold_seconds": 28_800},
    }


def _hold_capture() -> dict[str, object]:
    return {
        "status": "resolved",
        "economic_outcome": "profitable_after_costs",
        "observed_cost_hurdle_bps": 9.0,
        "realized_gross_return_bps": 80.0,
        "realized_net_return_bps": 70.0,
        "maximum_favorable_excursion_bps": 120.0,
        "maximum_adverse_excursion_bps": 20.0,
        "peak_giveback_bps": 30.0,
        "gross_mfe_capture_ratio": 0.75,
    }
