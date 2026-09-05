"""Tests for report-only HIP-3 lifecycle exit attribution."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.hip3_shadow_exit_attribution import (
    build_hip3_shadow_exit_attribution,
)


def _lifecycle(
    *,
    decision_ms: int = 1_000,
    side: str = "long",
    holding_minutes: int = 50,
    gross_bps: float = -10.0,
    net_bps: float = -12.0,
    reason: str = "stop",
) -> dict[str, object]:
    entry_ms = decision_ms + 100
    return {
        "side": side,
        "decision_time_ms": decision_ms,
        "signal_available_time_ms": entry_ms,
        "entry_time_ms": entry_ms,
        "exit_time_ms": entry_ms + holding_minutes * 60_000,
        "entry_price": 100.0,
        "exit_price": 99.9,
        "stop_price": 99.2,
        "stop_trigger_time_ms": None,
        "exit_reason": reason,
        "quantity": 1.0,
        "notional_usd": 100.0,
        "gross_pnl_usd": gross_bps / 100.0,
        "fees_usd": 0.02,
        "funding_cashflow_usd": 0.0,
        "modeled_friction_usd": 0.01,
        "net_pnl_usd": net_bps / 100.0,
        "gross_return_bps": gross_bps,
        "net_return_bps": net_bps,
    }


def _lifecycle_report() -> dict[str, object]:
    nominal = _lifecycle()
    stress = {**nominal, "net_pnl_usd": -0.14, "net_return_bps": -14.0}
    return {
        "schema_version": "hip3_shadow_lifecycle_v1",
        "symbol": "xyz:MU",
        "provider_id": "hip3_mu_breakout_shadow_preclose_v1",
        "profile_id": "mu_hip3_breakout_shadow_preclose_v1",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "nominal": {"lifecycles": [nominal]},
        "stress": {"lifecycles": [stress]},
    }


def _path(
    horizon: int,
    *,
    decision_ms: int = 1_000,
    side: str = "long",
    gross_bps: float,
) -> dict[str, object]:
    return {
        "decision_time_ms": decision_ms,
        "signal_available_time_ms": decision_ms + 100,
        "entry_book_time_ms": decision_ms + 100,
        "exit_book_time_ms": decision_ms + 100 + horizon * 60_000,
        "horizon_minutes": horizon,
        "side": side,
        "entry_price": 100.0,
        "exit_price": 100.0 + gross_bps / 100.0,
        "gross_bbo_bps": gross_bps,
        "after_fee_bps": gross_bps - 1.0,
        "after_modeled_friction_bps": gross_bps - 2.0,
    }


def _markout_report() -> dict[str, object]:
    values = {15: -20.0, 60: 10.0, 240: -50.0}
    return {
        "schema_version": "hip3_shadow_signal_markouts_v1",
        "symbol": "xyz:MU",
        "provider_id": "hip3_mu_breakout_shadow_preclose_v1",
        "profile_id": "mu_hip3_breakout_shadow_preclose_v1",
        "execution_authority": "none",
        "report_only": True,
        "contract": {"fills_assumed": False, "pnl_claimed": False},
        "markouts": {
            "horizons": {
                str(horizon): {"resolved_paths": [_path(horizon, gross_bps=gross_bps)]}
                for horizon, gross_bps in values.items()
            }
        },
    }


def test_attribution_uses_first_frozen_horizon_after_actual_exit() -> None:
    """A 50-minute exit is compared only with the frozen 60-minute path."""
    report = build_hip3_shadow_exit_attribution(_lifecycle_report(), _markout_report())

    row = report["exit_attributions"][0]
    assert row["selected_post_exit_horizon_minutes"] == 60
    assert row["later_frozen_horizons_not_selected"] == [240]
    assert row["classification"] == "directional_recovery_after_exit"
    assert row["actual_nominal_net_return_bps"] == -12.0
    assert row["actual_stress_net_return_bps"] == -14.0
    assert row["selected_horizon_gross_bbo_bps"] == 10.0


def test_attribution_withholds_judgment_beyond_last_frozen_horizon() -> None:
    """A lifecycle held beyond 240 minutes has no post-exit comparator."""
    lifecycle = _lifecycle(holding_minutes=300, gross_bps=25.0, net_bps=20.0)
    report = _lifecycle_report()
    report["nominal"]["lifecycles"] = [lifecycle]
    report["stress"]["lifecycles"] = [
        {**lifecycle, "net_pnl_usd": 0.18, "net_return_bps": 18.0}
    ]

    result = build_hip3_shadow_exit_attribution(report, _markout_report())

    row = result["exit_attributions"][0]
    assert row["classification"] == "no_post_exit_frozen_horizon"
    assert row["selected_post_exit_horizon_minutes"] is None


def test_attribution_does_not_skip_an_unresolved_first_horizon() -> None:
    """Missing 60-minute evidence cannot be replaced by a later 240-minute path."""
    markouts = _markout_report()
    markouts["markouts"]["horizons"]["60"]["resolved_paths"] = []

    result = build_hip3_shadow_exit_attribution(_lifecycle_report(), markouts)

    row = result["exit_attributions"][0]
    assert row["classification"] == "first_post_exit_horizon_unresolved"
    assert row["required_post_exit_horizon_minutes"] == 60
    assert row["selected_post_exit_horizon_minutes"] is None


@pytest.mark.parametrize(
    ("actual_gross_bps", "horizon_gross_bps", "expected"),
    [
        (-10.0, -5.0, "loss_persisted_after_exit"),
        (10.0, -5.0, "profit_protected_before_later_reversal"),
        (10.0, 20.0, "positive_path_extended_after_exit"),
        (20.0, 10.0, "positive_path_reduced_after_exit"),
    ],
)
def test_attribution_classifies_directional_path_without_net_delta(
    actual_gross_bps: float,
    horizon_gross_bps: float,
    expected: str,
) -> None:
    """Classification uses gross direction and never claims execution-equivalent PnL."""
    report = _lifecycle_report()
    for scenario in ("nominal", "stress"):
        report[scenario]["lifecycles"][0]["gross_return_bps"] = actual_gross_bps
    markouts = _markout_report()
    markouts["markouts"]["horizons"]["60"]["resolved_paths"][0]["gross_bbo_bps"] = (
        horizon_gross_bps
    )

    result = build_hip3_shadow_exit_attribution(report, markouts)

    row = result["exit_attributions"][0]
    assert row["classification"] == expected
    assert "execution_equivalent_return_delta_bps" not in row


def test_attribution_rejects_identity_or_authority_mismatch() -> None:
    """Report-only evidence cannot be aliased across symbol or authority."""
    markouts = _markout_report()
    markouts["symbol"] = "xyz:SP500"
    with pytest.raises(ValueError, match="identity"):
        build_hip3_shadow_exit_attribution(_lifecycle_report(), markouts)

    markouts = _markout_report()
    markouts["execution_authority"] = "live"
    with pytest.raises(ValueError, match="authority"):
        build_hip3_shadow_exit_attribution(_lifecycle_report(), markouts)


def test_attribution_rejects_nominal_stress_lifecycle_mismatch() -> None:
    """Nominal and stress scenarios must describe the same lifecycle keys."""
    report = deepcopy(_lifecycle_report())
    report["stress"]["lifecycles"][0]["side"] = "short"

    with pytest.raises(ValueError, match="nominal and stress"):
        build_hip3_shadow_exit_attribution(report, _markout_report())


def test_attribution_is_explicitly_non_promotional() -> None:
    """The output cannot acquire live or automatic strategy authority."""
    result = build_hip3_shadow_exit_attribution(_lifecycle_report(), _markout_report())

    assert result["execution_authority"] == "none"
    assert result["report_only"] is True
    assert result["automatic_promotion"] is False
    assert result["runtime_strategy_changed"] is False
    assert result["limitations"]
