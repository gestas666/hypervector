"""Integration coverage for durable ignored exits after lifecycle close."""

from copy import deepcopy

import pytest

from cohort_trade_reflection_fixtures import (
    reflection_asset_rows,
    reflection_cohort_rows,
)
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from test_multi_asset_live_audit import _HULK, _RUN_ID, _SYMBOLS, _asset_rows


def test_closed_reflection_retains_ignored_signal_and_actual_costs() -> None:
    """Closing a lifecycle cannot erase its first ignored provider exit."""
    cohort = reflection_cohort_rows()
    routes = [row for row in cohort if row["event_type"] == "intent_routing"]
    evaluation = next(
        item
        for item in routes[1]["payload"]["evaluations"]
        if item["strategy_id"] == _HULK and item["symbol"] == "BTC"
    )
    evaluation.update(
        {
            "decision_action": "close_long",
            "exit_sides": ["long"],
            "exit_reason": "hulk_exit_flip",
        }
    )
    assets = reflection_asset_rows()
    transition = deepcopy(assets[4])
    transition.update(
        {
            "event_type": "state_transition",
            "payload": {
                "state": "OPEN",
                "entry_oid": 11,
                "opened_at_ms": 1_785_600_000_000,
                "execution_plan": {
                    "strategy_id": _HULK,
                    "maximum_hold_seconds": 28_800,
                    "maximum_hold_policy": "fixed",
                    "provider_recipe_exit_policy": "ignore",
                },
            },
        }
    )
    assets.insert(5, transition)
    for sequence, row in enumerate(assets, start=1):
        row["sequence"] = sequence

    report = audit_multi_asset_live_run(
        cohort,
        {
            "BTC": assets,
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    outcome = report["trade_reflections"]["trades"][0]["ignored_provider_exit_outcome"]
    assert outcome["status"] == "observed"
    assert outcome["first_signal"]["decision_time_ms"] == 1_785_600_300_000
    assert outcome["actual_exit"]["price"] == pytest.approx(103.98)
    assert outcome["actual_exit"]["net_pnl_usd"] == pytest.approx(0.97)
    assert outcome["actual_exit"]["fees_usd"] == pytest.approx(0.02)
    assert outcome["actual_exit"]["funding_usd"] == pytest.approx(-0.01)
    assert outcome["gross_continuation_from_signal_bps"] == pytest.approx(
        (103.98 / 104.0 - 1.0) * 10_000.0
    )
    assert outcome["counterfactual_signal_exit_net_pnl_usd"] is None
