"""Exact-profile, report-only forward evidence tests for v39."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
import importlib

import pytest

from hypervector.research.cohort_trade_performance import build_trade_performance
from v39_forward_evidence_fixtures import (
    NOW as _NOW,
    checkpoint as _checkpoint,
    config as _config,
    current_run as _current_run,
    current_summary_rows as _current_summary_rows,
    install_current_run as _install_current_run,
    open_row as _open_row,
    route_performance as _route_performance,
    routes as _routes,
)


def test_exact_v39_snapshot_contains_all_routes_and_both_sides() -> None:
    """Zero-trade scopes remain explicit beside one current-run close."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    _install_current_run(checkpoint, route)

    report = _builder()(checkpoint, config, observed_at=_NOW)

    assert report["source"]["profile_fingerprint"] == config.profile_fingerprint
    assert report["summary"]["provider_symbol_routes"] == 14
    assert report["summary"]["configured_directional_scopes"] == 28
    assert report["summary"]["directional_scopes_with_evaluations"] == 28
    assert report["summary"]["closed_trades"] == 1
    assert len(report["routes"]) == 14
    assert report["routes"][route]["sides"]["long"]["net_pnl_usd"] == 1.25
    assert report["routes"][route]["sides"]["short"]["closed_trades"] == 0
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["performance_gate"] is False


def test_snapshot_uses_current_run_not_mixed_history() -> None:
    """An all-time winner cannot enter an exact current-run result."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    checkpoint["audit"]["trade_reflections"]["performance"]["all_time_live"] = {
        "by_provider_symbol": {route: _route_performance(net=99.0)},
    }

    report = _builder()(checkpoint, config, observed_at=_NOW)

    assert report["summary"]["closed_trades"] == 0
    assert report["summary"]["net_pnl_usd"] == 0.0
    assert report["routes"][route]["closed"]["closed_trades"] == 0


def test_snapshot_accepts_production_zero_trade_performance() -> None:
    """A fresh v39 run publishes explicit zero evidence before its first close."""
    config = _config()
    checkpoint = _checkpoint(config)
    checkpoint["audit"]["trade_reflections"]["performance"] = build_trade_performance(
        [], current_run_id="bidirectional-live-v39"
    )

    report = _builder()(checkpoint, config, observed_at=_NOW)

    assert report["summary"]["closed_trades"] == 0
    assert report["summary"]["net_pnl_usd"] == 0.0


def test_snapshot_rejects_active_v35_identity() -> None:
    """A staged v39 config cannot relabel an active v35 checkpoint."""
    config = _config()
    checkpoint = _checkpoint(config)
    checkpoint["audit"]["run"]["profile_id"] = (
        "multi_asset_bidirectional_all_live_canary_v35"
    )

    with pytest.raises(ValueError, match="profile identity"):
        _builder()(checkpoint, config, observed_at=_NOW)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("checkpoint", "performance_gate", "false"),
        ("checkpoint", "automatic_retuning", True),
        ("checkpoint", "runtime_strategy_changed", True),
        ("trade", "automatic_strategy_changes", True),
        ("open", "automatic_strategy_changes", True),
    ],
)
def test_snapshot_rejects_contradictory_source_contract(
    section: str,
    field: str,
    value: object,
) -> None:
    """Authority-none evidence requires explicit non-mutating source fields."""
    config = _config()
    checkpoint = _checkpoint(config)
    contracts = {
        "checkpoint": checkpoint["checkpoint_contract"],
        "trade": checkpoint["audit"]["trade_reflections"]["contract"],
        "open": checkpoint["audit"]["open_trade_reflections"]["contract"],
    }
    contracts[section][field] = value

    with pytest.raises(ValueError, match="source contract"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_missing_route_coverage() -> None:
    """Every configured provider-symbol route must be represented."""
    config = _config()
    checkpoint = _checkpoint(config)
    checkpoint["audit"]["signal_outcomes"]["by_provider_symbol"].pop(
        _routes(config)[-1]
    )

    with pytest.raises(ValueError, match="route coverage"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_open_position_is_provisional_and_separate_from_closed_pnl() -> None:
    """Marked open PnL cannot alter closed lifecycle economics."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    strategy, symbol = route.split("|", 1)
    checkpoint["audit"]["open_trade_reflections"]["trades"] = [
        {
            "lifecycle_id": f"{symbol}:123",
            "source_run_id": "bidirectional-live-v39",
            "strategy_id": strategy,
            "symbol": symbol,
            "side": "short",
            "entry": {"venue_timestamp_ms": 150},
            "open_profit_lock_challenger": {"as_of_timestamp_ms": 300},
            "marked_economics": {
                "active_lifecycle_marked_net_pnl_usd": 4.5,
                "status": "provisional_open",
                "symbol": symbol,
                "side": "short",
            },
        }
    ]
    checkpoint["audit"]["open_trade_reflections"]["open_lifecycles"] = 1

    report = _builder()(checkpoint, config, observed_at=_NOW)

    assert report["summary"]["net_pnl_usd"] == 0.0
    assert report["routes"][route]["sides"]["short"]["open_positions"] == 1
    assert report["routes"][route]["sides"]["short"]["open_marked_pnl_usd"] == 4.5
    assert report["routes"][route]["sides"]["short"]["open_pnl_status"] == (
        "provisional"
    )


def test_snapshot_rejects_changed_config_with_same_topology() -> None:
    """Topology counts cannot substitute for the pinned v39 fingerprint."""
    config = _config()
    changed = replace(config, poll_seconds=config.poll_seconds + 1.0)
    checkpoint = _checkpoint(changed)

    with pytest.raises(ValueError, match="exact v39 config"):
        _builder()(checkpoint, changed, observed_at=_NOW)


def test_snapshot_rejects_route_totals_that_disagree_with_sides() -> None:
    """Closed route economics must equal the sum of directional records."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    current = _install_current_run(checkpoint, route)
    current["by_provider_symbol"][route]["by_side"]["long"]["net_pnl_usd"] = 999.0
    checkpoint["audit"]["trade_reflections"]["trades"][0]["net_pnl_usd"] = 999.0
    checkpoint["audit"]["trade_reflections"]["performance"]["current_run"] = current

    with pytest.raises(ValueError, match="performance summary does not reconcile"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_malformed_directional_performance() -> None:
    """A present but malformed by-side record cannot become zero evidence."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    current = _install_current_run(checkpoint, route)
    current["by_provider_symbol"][route]["by_side"] = []
    checkpoint["audit"]["trade_reflections"]["performance"]["current_run"] = current

    with pytest.raises(ValueError, match="current .* sides must be an object"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_impossible_trade_counts() -> None:
    """Wins, losses, and breakevens must partition closed trades exactly."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    current = _install_current_run(checkpoint, route)
    current["by_provider_symbol"][route]["losses"] = 1
    checkpoint["audit"]["trade_reflections"]["performance"]["current_run"] = current

    with pytest.raises(ValueError, match="performance summary does not reconcile"):
        _builder()(checkpoint, config, observed_at=_NOW)


@pytest.mark.parametrize(
    "field",
    ["fees_usd", "entry_margin_used_usd", "maximum_closed_sequence_drawdown_usd"],
)
def test_snapshot_rejects_negative_nonnegative_economics(field: str) -> None:
    """Costs, used margin, and drawdown magnitudes cannot be negative."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    current = _install_current_run(checkpoint, route)
    current["by_provider_symbol"][route][field] = -1.0
    checkpoint["audit"]["trade_reflections"]["performance"]["current_run"] = current

    with pytest.raises(ValueError, match="performance summary does not reconcile"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_more_eligible_than_evaluated() -> None:
    """Eligible evaluations must be a subset of all evaluations."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    checkpoint["audit"]["signal_outcomes"]["by_provider_symbol"][route] = {
        "evaluations": 3,
        "eligible_evaluations": 4,
        "no_direction": 0,
        "by_side": {
            "long": {"evaluations": 2, "eligible_evaluations": 2},
            "short": {"evaluations": 1, "eligible_evaluations": 1},
        },
    }

    with pytest.raises(ValueError, match="eligible evaluations exceed evaluations"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_stale_checkpoint() -> None:
    """A monitor refresh cannot make unchanged old evidence appear current."""
    config = _config()
    checkpoint = _checkpoint(config)

    with pytest.raises(ValueError, match="checkpoint is stale"):
        _builder()(
            checkpoint,
            config,
            observed_at=datetime(2026, 8, 11, 10, 2, tzinfo=UTC),
        )


def test_snapshot_rejects_stale_underlying_observation() -> None:
    """A fresh publication cannot relabel ancient market evidence as fresh."""
    config = _config()
    checkpoint = _checkpoint(config)
    checkpoint["audit"]["run"]["last_observed_at_utc"] = "2000-01-01T00:00:00Z"

    with pytest.raises(ValueError, match="source observation is stale"):
        _builder()(checkpoint, config, observed_at=_NOW)


@pytest.mark.parametrize("section", ["run", "routing"])
def test_snapshot_rejects_duplicate_route_identity(section: str) -> None:
    """Duplicate route rows cannot disappear through set coercion."""
    config = _config()
    checkpoint = _checkpoint(config)
    target = checkpoint["audit"][section]
    routes = target["executable_provider_symbols"]
    routes.append(routes[0])
    other = "routing" if section == "run" else "run"
    other_routes = checkpoint["audit"][other]["executable_provider_symbols"]
    assert len(other_routes) == len(set(other_routes))

    with pytest.raises(ValueError, match="duplicate route"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_noncausal_source_timestamps() -> None:
    """Run observation cannot occur after checkpoint publication."""
    config = _config()
    checkpoint = _checkpoint(config)
    checkpoint["audit"]["run"]["last_observed_at_utc"] = "2026-08-11T10:00:01+00:00"

    with pytest.raises(ValueError, match="source timestamps are not causal"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_reports_observed_directional_signal_coverage() -> None:
    """Configured side authority remains distinct from measured side observations."""
    config = _config()
    checkpoint = _checkpoint(config)
    for outcome in checkpoint["audit"]["signal_outcomes"][
        "by_provider_symbol"
    ].values():
        outcome.update(
            {
                "no_direction": 0,
                "by_side": {
                    "long": {"evaluations": 2, "eligible_evaluations": 0},
                    "short": {"evaluations": 1, "eligible_evaluations": 0},
                },
            }
        )

    report = _builder()(checkpoint, config, observed_at=_NOW)
    route = _routes(config)[0]

    assert report["summary"]["configured_directional_scopes"] == 28
    assert report["summary"]["directional_scopes_with_evaluations"] == 28
    assert report["routes"][route]["sides"]["long"]["signal_evaluations"] == 2
    assert report["routes"][route]["sides"]["short"]["signal_evaluations"] == 1


def test_snapshot_rejects_duplicate_open_lifecycle_identity() -> None:
    """One active venue lifecycle cannot be counted twice under one route."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    strategy, symbol = route.split("|", 1)
    row = _open_row(strategy, symbol, "long")
    checkpoint["audit"]["open_trade_reflections"]["trades"] = [row, dict(row)]
    checkpoint["audit"]["open_trade_reflections"]["open_lifecycles"] = 2

    with pytest.raises(ValueError, match="lifecycle identity is duplicated"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_mismatched_open_mark_identity() -> None:
    """Nested marked economics must describe the same asset and side."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    strategy, symbol = route.split("|", 1)
    row = _open_row(strategy, symbol, "long")
    row["marked_economics"]["symbol"] = "MISMATCH"
    checkpoint["audit"]["open_trade_reflections"]["trades"] = [row]
    checkpoint["audit"]["open_trade_reflections"]["open_lifecycles"] = 1

    with pytest.raises(ValueError, match="marked economics identity"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_open_lifecycle_count_mismatch() -> None:
    """Declared open count must equal the serialized lifecycle rows."""
    config = _config()
    checkpoint = _checkpoint(config)
    checkpoint["audit"]["open_trade_reflections"]["open_lifecycles"] = 1

    with pytest.raises(ValueError, match="open lifecycle count does not reconcile"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_lifecycle_symbol_mismatch() -> None:
    """A lifecycle key must use its exact asset identity prefix."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    strategy, symbol = route.split("|", 1)
    row = _open_row(strategy, symbol, "long")
    row["lifecycle_id"] = "BTC:999"
    section = checkpoint["audit"]["open_trade_reflections"]
    section["trades"] = [row]
    section["open_lifecycles"] = 1

    with pytest.raises(ValueError, match="lifecycle identity does not match symbol"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_current_aggregate_without_lifecycles() -> None:
    """Aggregate closes cannot exist without exact current-run trade rows."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    checkpoint["audit"]["trade_reflections"]["performance"]["current_run"] = (
        _current_run(route)
    )

    with pytest.raises(ValueError, match="closed lifecycle count does not reconcile"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_current_lifecycle_economics_mismatch() -> None:
    """Raw current-run lifecycle economics must reconcile to route aggregates."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    _install_current_run(checkpoint, route)
    checkpoint["audit"]["trade_reflections"]["trades"][0]["net_pnl_usd"] = 9.0

    with pytest.raises(ValueError, match="performance summary does not reconcile"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_current_lifecycle_profile_mismatch() -> None:
    """A raw lifecycle must carry the frozen v39 profile fingerprint."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    _install_current_run(checkpoint, route)
    trades = checkpoint["audit"]["trade_reflections"]["trades"]
    trades[0]["source_profile_fingerprint"] = "wrong-profile"

    with pytest.raises(ValueError, match="profile fingerprint"):
        _builder()(checkpoint, config, observed_at=_NOW)


def test_snapshot_rejects_raw_winner_labeled_as_loss() -> None:
    """Win/loss classification must be rebuilt from raw lifecycle PnL."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    current = _install_current_run(checkpoint, route)
    for row in _current_summary_rows(current, route):
        row["wins"] = 0
        row["losses"] = 1

    with pytest.raises(ValueError, match="performance summary does not reconcile"):
        _builder()(checkpoint, config, observed_at=_NOW)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("net_return_on_margin_pct", 999.0),
        ("profit_factor", -3.0),
        ("maximum_closed_sequence_drawdown_usd", 77.0),
    ],
)
def test_snapshot_rejects_derived_performance_mismatch(
    field: str,
    value: float,
) -> None:
    """Derived directional economics must match the raw lifecycle sequence."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _routes(config)[0]
    current = _install_current_run(checkpoint, route)
    for row in _current_summary_rows(current, route):
        row[field] = value

    with pytest.raises(ValueError, match="performance summary does not reconcile"):
        _builder()(checkpoint, config, observed_at=_NOW)


def _builder() -> Callable[..., dict[str, object]]:
    try:
        module = importlib.import_module("hypervector.research.v39_forward_evidence")
    except ModuleNotFoundError:
        pytest.fail("v39 forward evidence module is missing")
    builder = getattr(module, "build_v39_forward_evidence", None)
    if not callable(builder):
        pytest.fail("build_v39_forward_evidence is missing")
    return builder
