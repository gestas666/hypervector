"""Report-only v45 route-native sizing snapshot contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.v45_variable_sizing_snapshot import (
    build_v45_variable_sizing_snapshot,
)


_CONFIG = Path(
    "configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml"
)


def test_ineligible_evaluations_are_counted_but_never_sized() -> None:
    """A near-entry setup cannot manufacture a counterfactual position."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    row = _row(config, [_evaluation("HYPE", "hype", eligible=False)])

    report = build_v45_variable_sizing_snapshot([row], config)

    assert report["evaluations"] == 1
    assert report["eligible_candidates"] == 0
    assert report["candidates"] == []
    assert report["execution_authority"] == "none"
    assert report["tier_authority"] == "counterfactual_only"
    assert report["leverage_policy"] == {
        "mode": "fixed_isolated",
        "configured_leverage": 5.0,
        "variable_leverage_authorized": False,
    }
    assert report["tier_input_policy"]["route_native_features_only"] is True
    assert report["tier_input_policy"]["canonical_regime_scaling"] == (
        "withheld_pending_symbol_side_horizon_calibration"
    )


def test_configured_routes_disclose_tier_headroom_before_an_entry() -> None:
    """The counterfactual report distinguishes real size-up from capped tiers."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")

    report = build_v45_variable_sizing_snapshot([], config)

    routes = {
        (row["strategy_id"], row["symbol"], row["side"]): row
        for row in report["configured_route_scenarios"]
    }
    assert len(routes) == 6
    hype = routes[
        ("hype_breakout_compression_pullback_bidirectional_v1", "HYPE", "long")
    ]
    hype_up = hype["account_scenarios"]["5000"]["tiers"]["1.25"]
    assert hype_up["cap_binding"] is True
    assert hype_up["effective_multiplier"] == pytest.approx(1.0)
    hulk = routes[("hulk_expansion_short_robust_v3", "BTC", "short")]
    hulk_up = hulk["account_scenarios"]["5000"]["tiers"]["1.25"]
    assert hulk_up["notional_usd"] == pytest.approx(4_000.0)
    assert hulk_up["effective_multiplier"] == pytest.approx(1.2)


def test_eligible_hype_freezes_features_and_three_counterfactual_tiers() -> None:
    """An eligible route retains decision-time inputs and capped dollar sizing."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    evaluation = _evaluation("HYPE", "hype", eligible=True)

    report = build_v45_variable_sizing_snapshot([_row(config, [evaluation])], config)

    candidate = report["candidates"][0]
    assert candidate["strategy_id"] == (
        "hype_breakout_compression_pullback_bidirectional_v1"
    )
    assert candidate["features"]["breakout_volume_ratio"] == 2.5
    assert candidate["source_run_id"] == "bidirectional-observe-test"
    five_thousand = candidate["account_scenarios"]["5000"]
    assert five_thousand["base_notional_usd"] == pytest.approx(1750.0)
    assert five_thousand["tiers"]["0.75"]["notional_usd"] == pytest.approx(1312.5)
    assert five_thousand["tiers"]["1.0"]["notional_usd"] == pytest.approx(1750.0)
    assert five_thousand["tiers"]["1.25"]["notional_usd"] == pytest.approx(1750.0)
    assert five_thousand["tiers"]["1.25"]["cap_binding"] is True
    assert candidate["selected_tier"] is None


def test_btc_long_tier_reports_effective_multiplier_when_cap_binds() -> None:
    """A requested increase cannot exceed the frozen provider notional cap."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    evaluation = _evaluation("BTC", "btc_long", eligible=True)

    report = build_v45_variable_sizing_snapshot([_row(config, [evaluation])], config)

    tier = report["candidates"][0]["account_scenarios"]["5000"]["tiers"]["1.25"]
    assert tier["notional_usd"] == pytest.approx(4500.0)
    assert tier["effective_multiplier"] == pytest.approx(1.08)
    assert tier["cap_binding"] is True


def test_eligible_route_rejects_missing_frozen_sizing_feature() -> None:
    """Eligible evidence fails closed when a route-native input is absent."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    evaluation = _evaluation("HYPE", "hype", eligible=True)
    del evaluation["readiness"]["metrics"]["breakout_volume_ratio"]

    with pytest.raises(ValueError, match="breakout_volume_ratio"):
        build_v45_variable_sizing_snapshot([_row(config, [evaluation])], config)


def test_eligible_but_unrouted_evaluation_is_not_sized() -> None:
    """Provider eligibility cannot create exposure when portfolio routing withholds it."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    evaluation = _evaluation("HYPE", "hype", eligible=True)

    report = build_v45_variable_sizing_snapshot(
        [_row(config, [evaluation], route_entries=False)],
        config,
    )

    assert report["eligible_evaluations"] == 1
    assert report["eligible_not_routed"] == 1
    assert report["eligible_candidates"] == 0


def _row(
    config: object,
    evaluations: list[dict[str, object]],
    *,
    route_entries: bool = True,
) -> dict[str, object]:
    actions = [_action(value) for value in evaluations if value["eligible"] is True]
    return {
        "event_type": "intent_routing",
        "profile_id": getattr(config, "profile_id"),
        "profile_fingerprint": getattr(config, "profile_fingerprint"),
        "run_id": "bidirectional-observe-test",
        "run_fingerprint": "test-run-fingerprint",
        "execution_authority": "none",
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "payload": {
            "evaluations": evaluations,
            "actions": actions if route_entries else [],
            "withheld": [],
        },
    }


def _action(evaluation: dict[str, object]) -> dict[str, object]:
    return {
        "action": "enter",
        "strategy_id": evaluation["strategy_id"],
        "symbol": evaluation["symbol"],
        "side": evaluation["side"],
        "decision_time_ms": evaluation["decision_time_ms"],
    }


def _evaluation(symbol: str, route: str, *, eligible: bool) -> dict[str, object]:
    strategy, metrics = _route(route)
    return {
        "strategy_id": strategy,
        "symbol": symbol,
        "decision_time_ms": 1_786_530_600_000,
        "decision_action": "enter_long" if eligible else "hold",
        "eligible": eligible,
        "side": "long",
        "readiness": {"metrics": metrics},
    }


def _route(name: str) -> tuple[str, dict[str, object]]:
    if name == "btc_long":
        return "liquidity_sweep_long_1h_stop60_target60_v2", {
            "clearance_bps": 10.0,
            "close_above_ema55": True,
            "ema55": 100.0,
            "reclaim_close": 101.0,
            "sweep_low": 99.0,
            "volume_multiple": 1.5,
        }
    return "hype_breakout_compression_pullback_bidirectional_v1", {
        "authoritative_5m_bbwp_percentile": 20.0,
        "breakout_clearance_20m_bps": 10.0,
        "breakout_volume_ratio": 2.5,
        "current_bbwp_percentile": 20.0,
        "directional_bar_body_bps": -1.0,
        "prior_bbwp_below25_count_15m": 2.0,
        "prior_bbwp_min_15m": 15.0,
    }
