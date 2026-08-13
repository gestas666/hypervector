import pytest

from hypervector.live.hulk_smash_live_config import load_hulk_smash_live_config
from hypervector.live.hulk_smash_live_risk import build_hulk_protection_plan


def test_hulk_plan_sizes_from_equity_risk_and_structural_stop() -> None:
    config = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="observe",
    )

    plan = build_hulk_protection_plan(
        entry_price=100.0,
        stop_anchor=100.5,
        account_equity_usd=150.0,
        config=config,
    )

    assert plan.stop_bps == pytest.approx(50.0)
    assert plan.stop_price == pytest.approx(100.5)
    assert plan.target_price == pytest.approx(98.5)
    assert plan.requested_notional_usd == pytest.approx(75.0)
    assert plan.configured_risk_usd == pytest.approx(0.375)
    assert plan.actual_stop_risk_usd == pytest.approx(0.375)


@pytest.mark.parametrize(
    ("anchor", "stop_bps", "notional", "target"),
    [
        (99.0, 20.0, 150.0, 99.4),
        (105.0, 75.0, 50.0, 97.75),
    ],
)
def test_hulk_plan_clamps_stop_and_never_exceeds_notional_cap(
    anchor: float,
    stop_bps: float,
    notional: float,
    target: float,
) -> None:
    config = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="observe",
    )

    plan = build_hulk_protection_plan(
        entry_price=100.0,
        stop_anchor=anchor,
        account_equity_usd=150.0,
        config=config,
    )

    assert plan.stop_bps == pytest.approx(stop_bps)
    assert plan.requested_notional_usd == pytest.approx(notional)
    assert plan.target_price == pytest.approx(target)
    assert plan.requested_notional_usd <= config.max_notional_usd
    assert plan.requested_notional_usd <= 150.0 * config.leverage


def test_hulk_postfill_plan_reports_risk_from_actual_position_notional() -> None:
    config = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="observe",
    )

    plan = build_hulk_protection_plan(
        entry_price=99.0,
        stop_anchor=100.5,
        account_equity_usd=150.0,
        position_notional_usd=74.25,
        config=config,
    )

    assert plan.stop_bps == pytest.approx(75.0)
    assert plan.requested_notional_usd == pytest.approx(74.25)
    assert plan.actual_stop_risk_usd == pytest.approx(0.556875)
    assert plan.notional_basis == "venue_position"


def test_hulk_postfill_plan_refuses_configured_portfolio_risk_breach() -> None:
    config = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="observe",
    )

    with pytest.raises(ValueError, match="portfolio risk cap"):
        build_hulk_protection_plan(
            entry_price=100.0,
            stop_anchor=101.0,
            account_equity_usd=150.0,
            position_notional_usd=500.0,
            config=config,
        )
