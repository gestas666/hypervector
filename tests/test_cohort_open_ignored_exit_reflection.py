"""Integration coverage for ignored provider exits on open lifecycles."""

from cohort_trade_reflection_fixtures import (
    open_reflection_asset_rows,
    open_reflection_cohort_rows,
)
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from test_multi_asset_live_audit import _HULK, _RUN_ID, _SYMBOLS, _asset_rows


def test_open_reflection_binds_first_ignored_exit_to_lifecycle() -> None:
    """The open-trade report must retain the provider's first ignored exit."""
    cohort = open_reflection_cohort_rows()
    cohort[-1]["observed_at_utc"] = "2026-08-01T16:05:06+00:00"
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

    report = audit_multi_asset_live_run(
        cohort,
        {
            "BTC": open_reflection_asset_rows(),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    observer = report["open_trade_reflections"]["trades"][0][
        "ignored_provider_exit_observer"
    ]
    assert observer["status"] == "observed"
    assert observer["provider_recipe_exit_policy"] == "ignore"
    assert observer["ignored_signal_count"] == 1
    assert observer["first_signal"]["decision_time_ms"] == 1_785_600_300_000
    assert observer["first_signal"]["exit_reason"] == "hulk_exit_flip"
    assert observer["contract"]["execution_authority"] == "none"
