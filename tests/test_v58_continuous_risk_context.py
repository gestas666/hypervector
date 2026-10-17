"""Source-bound V58 exposure and simultaneous-stop stress context."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.research.v58_continuous_risk_context import (
    current_equity_risk_context_payload,
    load_v58_risk_context,
    risk_context_payload,
)

_CONFIG = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_eight_asset_growth_sizing_stress_20260819_v1.json"
)


@pytest.mark.evidence
def test_loader_reconciles_current_config_and_stacked_loss() -> None:
    """Current exposure must reconcile to the exact frozen V58 stress bytes."""
    context = load_v58_risk_context(_CONFIG, _STRESS)
    payload = risk_context_payload(context)

    assert payload["account_value_usd"] == 5_000.0
    assert payload["account_position_capacity"] == 10
    assert payload["maximum_simultaneous_positions"] == 8
    assert payload["maximum_margin_fraction"] == pytest.approx(0.46)
    assert payload["maximum_margin_usd"] == pytest.approx(2_300.0)
    assert payload["maximum_gross_notional_usd"] == pytest.approx(16_500.0)
    assert payload["stacked_p99_stop_wave_loss_usd"] == pytest.approx(180.304176)
    assert payload["stacked_p99_stop_wave_loss_pct_equity"] == pytest.approx(3.60608352)
    assert len(payload["asset_slots"]) == 8
    assert sum(
        row["slot_p99_loss_usd"] for row in payload["asset_slots"]
    ) == pytest.approx(payload["stacked_p99_stop_wave_loss_usd"])
    assert payload["joint_loss_probability_claim"] is False
    assert payload["sizing_input"] is False
    assert payload["automatic_sizing_change"] is False
    assert payload["execution_authority"] == "none"


@pytest.mark.evidence
def test_loader_rejects_slot_margin_that_disagrees_with_routes(
    tmp_path: Path,
) -> None:
    """A self-consistent aggregate cannot conceal a changed asset route margin."""
    stress = json.loads(_STRESS.read_text(encoding="utf-8"))
    scenario = stress["scenarios"][0]
    scenario["asset_slots"]["BTC"]["maximum_margin_fraction"] = 0.09
    scenario["route_aware_maximum_margin_fraction"] = 0.45
    path = tmp_path / "stress.json"
    path.write_text(json.dumps(stress), encoding="utf-8")

    with pytest.raises(ValueError, match="slot margin does not reconcile"):
        load_v58_risk_context(_CONFIG, path)


@pytest.mark.evidence
def test_loader_rejects_position_capacity_that_disagrees_with_config(
    tmp_path: Path,
) -> None:
    """Stress capacity must describe the exact current portfolio topology."""
    stress = json.loads(_STRESS.read_text(encoding="utf-8"))
    stress["scenarios"][0]["account_position_capacity"] = 9
    path = tmp_path / "stress.json"
    path.write_text(json.dumps(stress), encoding="utf-8")

    with pytest.raises(ValueError, match="position capacity is inconsistent"):
        load_v58_risk_context(_CONFIG, path)


@pytest.mark.evidence
def test_loader_rejects_duplicated_route_identity(tmp_path: Path) -> None:
    """A duplicated stress row cannot masquerade as complete route coverage."""
    stress = json.loads(_STRESS.read_text(encoding="utf-8"))
    routes = stress["scenarios"][0]["asset_slots"]["BTC"]["routes"]
    routes.append(dict(routes[0]))
    path = tmp_path / "stress.json"
    path.write_text(json.dumps(stress), encoding="utf-8")

    with pytest.raises(ValueError, match="route identity is incomplete or aliased"):
        load_v58_risk_context(_CONFIG, path)


@pytest.mark.evidence
def test_current_equity_payload_retains_both_denominators() -> None:
    """Current account risk must not overwrite the frozen sizing reference."""
    context = load_v58_risk_context(_CONFIG, _STRESS)
    payload = current_equity_risk_context_payload(
        context,
        actual_account_value_usd=4_875.83799849,
        sizing_reference_equity_usd=5_000.0,
        observed_at_utc="2026-08-19T17:19:06+00:00",
        fresh=True,
    )

    assert payload["stacked_p99_stop_wave_loss_pct_sizing_reference"] == pytest.approx(
        3.6060835200814267
    )
    assert payload["stacked_p99_stop_wave_loss_pct_actual_account"] == pytest.approx(
        3.697910744836888
    )
    assert payload["sizing_input"] is False


@pytest.mark.evidence
def test_current_equity_payload_rejects_changed_sizing_reference() -> None:
    """Point-in-time venue data cannot relabel the frozen model denominator."""
    context = load_v58_risk_context(_CONFIG, _STRESS)

    with pytest.raises(ValueError, match="risk and venue sizing references differ"):
        current_equity_risk_context_payload(
            context,
            actual_account_value_usd=4_875.83799849,
            sizing_reference_equity_usd=4_900.0,
            observed_at_utc="2026-08-19T17:19:06+00:00",
            fresh=True,
        )
