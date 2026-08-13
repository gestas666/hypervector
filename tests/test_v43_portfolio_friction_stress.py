"""Full-roster friction stress for the proposed v43 successor."""

from pathlib import Path

import pytest

from hypervector.research.v43_portfolio_friction_stress import (
    build_v43_portfolio_friction_stress,
)

_PROFILE = Path("configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml")
_V44_PROFILE = Path(
    "configs/multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml"
)
_VENUE = Path(
    "data/logs/research/bidirectional_cohort/"
    "v40_growth_sizing_stress_20260811T0200Z.json"
)


def _execution_friction() -> dict[str, dict[str, object]]:
    """Return bounded empirical slippage fixtures for the three v43 assets."""
    return {
        "BTC": {
            "entry": {"sample_count": 14, "p99_bps": 3.5568},
            "adverse_exit": {"sample_count": 14, "p99_bps": 8.6860},
            "target_exit": {"sample_count": 3, "p99_bps": 0.0522},
            "exit_evidence_scope": "exact_symbol",
        },
        "HYPE": {
            "entry": {"sample_count": 15, "p99_bps": 7.0445},
            "adverse_exit": {"sample_count": 15, "p99_bps": 9.3370},
            "target_exit": {"sample_count": 1, "p99_bps": 0.0},
            "exit_evidence_scope": "exact_symbol",
        },
        "xyz:SP500": {
            "entry": {"sample_count": 1, "p99_bps": 0.7750},
            "adverse_exit": {"sample_count": 5, "p99_bps": 6.1060},
            "target_exit": {"sample_count": 0, "p99_bps": None},
            "exit_evidence_scope": "same_provider_xyz_spcx_proxy",
        },
    }


def test_v43_stress_covers_every_asset_and_mutually_exclusive_btc_side() -> None:
    """One BTC side plus HYPE and SP500 form the exact worst stop wave."""
    report = build_v43_portfolio_friction_stress(
        _PROFILE,
        venue_stress_path=_VENUE,
        execution_friction=_execution_friction(),
        account_values_usd=(500.0, 5_000.0),
    )

    growth = report["scenarios"][1]
    slots = growth["asset_slots"]
    assert set(slots) == {"BTC", "HYPE", "xyz:SP500"}
    assert len(slots["BTC"]["routes"]) == 2
    assert slots["BTC"]["simultaneous_route_count"] == 1
    assert growth["stacked_p99_stop_wave_loss_usd"] == pytest.approx(51.80, abs=0.03)
    assert growth["stacked_p99_stop_wave_loss_pct_equity"] == pytest.approx(
        1.036, abs=0.001
    )
    assert growth["maximum_simultaneous_positions"] == 3


def test_v43_long_payoff_reports_friction_adjusted_breakeven_fragility() -> None:
    """The low-target BTC long cannot be mistaken for the 3R short route."""
    report = build_v43_portfolio_friction_stress(
        _PROFILE,
        venue_stress_path=_VENUE,
        execution_friction=_execution_friction(),
        account_values_usd=(5_000.0,),
    )
    routes = report["scenarios"][0]["asset_slots"]["BTC"]["routes"]
    by_strategy = {row["strategy_id"]: row for row in routes}
    long = by_strategy["liquidity_sweep_long_1h_stop60_v1"]
    short = by_strategy["hulk_expansion_short_robust_v3"]

    assert long["stacked_p99_stop_loss_usd"] == pytest.approx(35.41, abs=0.02)
    assert long["stacked_target_net_before_funding_usd"] == pytest.approx(
        5.55, abs=0.02
    )
    assert long["friction_adjusted_breakeven_win_rate"] > 0.86
    assert short["friction_adjusted_breakeven_win_rate"] < 0.34
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["performance_gate"] is False


def test_v43_stress_rejects_missing_or_success_shaped_friction() -> None:
    """Sparse evidence remains explicit, while absent evidence fails closed."""
    friction = _execution_friction()
    del friction["HYPE"]
    with pytest.raises(ValueError, match="missing execution friction"):
        build_v43_portfolio_friction_stress(
            _PROFILE,
            venue_stress_path=_VENUE,
            execution_friction=friction,
            account_values_usd=(500.0,),
        )
    friction = _execution_friction()
    friction["BTC"]["entry"] = {"sample_count": 0, "p99_bps": 0.0}
    with pytest.raises(ValueError, match="sample_count"):
        build_v43_portfolio_friction_stress(
            _PROFILE,
            venue_stress_path=_VENUE,
            execution_friction=friction,
            account_values_usd=(500.0,),
        )


def test_corrected_successor_can_freeze_a_distinct_schema_identity() -> None:
    """A v44 artifact cannot masquerade as the superseded v43 contract."""
    report = build_v43_portfolio_friction_stress(
        _V44_PROFILE,
        venue_stress_path=_VENUE,
        execution_friction=_execution_friction(),
        account_values_usd=(5_000.0,),
        schema_version="v44_portfolio_friction_stress_v1",
    )
    routes = report["scenarios"][0]["asset_slots"]["BTC"]["routes"]
    long = next(row for row in routes if "target60" in row["strategy_id"])

    assert report["schema_version"] == "v44_portfolio_friction_stress_v1"
    assert long["target_bps"] == pytest.approx(60.0)
    assert long["friction_adjusted_breakeven_win_rate"] == pytest.approx(
        0.6456320652143959
    )


def test_candidate_notional_depth_overrides_old_uniform_slot_depth() -> None:
    """Exact candidate-size depth replaces the superseded $750 curve."""
    depths = {"BTC": 0.637741, "HYPE": 1.476004, "xyz:SP500": 1.411915}
    report = build_v43_portfolio_friction_stress(
        _V44_PROFILE,
        venue_stress_path=_VENUE,
        execution_friction=_execution_friction(),
        account_values_usd=(5_000.0,),
        schema_version="v45_portfolio_friction_stress_v1",
        visible_depth_p99_bps=depths,
    )

    slots = report["scenarios"][0]["asset_slots"]
    for symbol, expected in depths.items():
        for route in slots[symbol]["routes"]:
            assert route["friction_components_bps"]["visible_depth_p99"] == (
                pytest.approx(expected)
            )
    assert report["visible_depth_contract"] == {
        "source": "explicit_candidate_notional_override",
        "p99_bps_by_asset": depths,
    }


def test_candidate_depth_override_requires_every_exact_asset() -> None:
    """A partial or aliased depth map cannot produce a success-shaped report."""
    with pytest.raises(ValueError, match="exactly match profile symbols"):
        build_v43_portfolio_friction_stress(
            _V44_PROFILE,
            venue_stress_path=_VENUE,
            execution_friction=_execution_friction(),
            account_values_usd=(5_000.0,),
            visible_depth_p99_bps={"BTC": 1.0, "HYPE": 1.0},
        )
