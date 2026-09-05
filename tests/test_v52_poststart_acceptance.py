"""Technical acceptance contract for evidence-bound successor v52."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v52_poststart_acceptance as acceptance

_PROFILE = Path(
    "configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml"
)
_STRESS = Path("tests/fixtures/v52_growth_sizing_stress_5000.json")
_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def test_exact_v52_binds_two_assets_three_routes_and_alignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance must bind the exact reduced roster and repaired HYPE route."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v52_poststart_acceptance(
        checkpoint,
        config,
        _stress_evidence(),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["schema_version"] == "v52_poststart_acceptance_v1"
    scope = report["checks"]["direction_scope_identity"]
    assert scope == {
        "passed": True,
        "reasons": [],
        "provider_symbol_routes": 3,
        "directional_scopes": 4,
    }
    assert report["checks"]["hype_alignment_readiness"]["passed"] is True
    assert report["stress_identity"]["actual_position_count"] == 2
    assert report["stress_identity"]["p99_stop_wave_loss_usd"] == pytest.approx(
        92.84753440041398
    )


def test_v52_rejects_synthetic_ten_slots_as_actual_exposure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The account capacity row cannot masquerade as v52's actual stress."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    evidence = _stress_evidence()
    evidence["portfolio_stress"]["configured_asset_roster"] = deepcopy(
        evidence["portfolio_stress"]["hypothetical_ten_slot_capacity"]
    )
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    with pytest.raises(ValueError, match="v52 stress identity"):
        acceptance.build_v52_poststart_acceptance(
            _checkpoint(config),
            config,
            evidence,
            _preflight(config),
            now_utc=_NOW,
        )


def test_v52_rejects_old_hype_runtime_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generic compression provider cannot impersonate alignment v2."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    directions = checkpoint["configuration_generation"][
        "current_provider_execution_directions"
    ]
    directions["hype_breakout_compression_pullback_bidirectional_v1|HYPE"] = (
        directions.pop("hype_breakout_compression_alignment_bidirectional_v2|HYPE")
    )
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v52_poststart_acceptance(
        checkpoint,
        config,
        _stress_evidence(),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "runtime_direction_scope_mismatch" in report["reasons"]


def test_v52_rejects_missing_alignment_readiness_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A route evaluation without the repaired gate is not launch evidence."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    route = "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
    checkpoint["audit"]["readiness"]["by_provider_symbol"][route]["latest_metrics"].pop(
        "alignment_only"
    )
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v52_poststart_acceptance(
        checkpoint,
        config,
        _stress_evidence(),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert report["checks"]["hype_alignment_readiness"]["reasons"] == [
        "hype_alignment_readiness_contract_missing"
    ]


def test_v52_rejects_open_position_without_bound_exit_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every restored v52 position must retain its persisted exit contract."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    checkpoint["audit"]["health"] = {"assets": {"HYPE": {"final_state": "OPEN"}}}
    checkpoint["audit"]["open_trade_reflections"] = {"trades": []}
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v52_poststart_acceptance(
        checkpoint,
        config,
        _stress_evidence(),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert report["checks"]["bound_execution_plans"]["reasons"] == [
        "open_lifecycle_missing_bound_execution_plan:HYPE"
    ]


def _checkpoint(config: object) -> dict[str, object]:
    directions = {
        f"{provider.strategy_id}|{symbol}": sorted(provider.sides)
        for provider in getattr(config, "providers")
        for symbol in provider.execution_symbols
    }
    route = "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
    return {
        "audit": {
            "run": {"run_id": "v52-live"},
            "health": {"assets": {}},
            "open_trade_reflections": {"trades": []},
            "readiness": {
                "by_provider_symbol": {
                    route: {
                        "count": 1,
                        "latest_metrics": {
                            "alignment_only": True,
                            "breakout_side_alignment_required": True,
                            "breakout_side_relation": "unavailable",
                        },
                    }
                }
            },
        },
        "configuration_generation": {
            "current_provider_execution_directions": directions,
        },
    }


def _stress_evidence() -> dict[str, object]:
    fixture = json.loads(_STRESS.read_text(encoding="utf-8"))
    scenario = fixture["scenario"]
    btc = 46.04011320906441
    hype = 46.80742119134957
    return {
        "schema_version": 3,
        "mode": "cohort_growth_sizing_stress_v3",
        "profile_id": fixture["profile_id"],
        "profile_fingerprint": fixture["profile_fingerprint"],
        "contract": {
            "automatic_sizing_change": False,
            "balance_gate": False,
            "execution_authority": "none",
            "performance_gate": False,
            "profit_forecast": False,
            "report_only": True,
            "runtime_strategy_changed": False,
        },
        "sizing_plan": {
            **scenario,
            "leverage": 10.0,
            "ten_slot_maximum_margin_fraction": 1.0,
            "unused_capacity_slots": 8,
        },
        "by_asset": {
            "BTC": _asset_stress(btc),
            "HYPE": _asset_stress(hype),
        },
        "portfolio_stress": {
            "configured_asset_roster": {
                "position_count": 2,
                "isolated_margin_at_risk_usd": 1000.0,
                "isolated_margin_at_risk_pct_equity": 20.0,
                "p99_stop_wave_loss_usd": btc + hype,
                "p99_stop_wave_loss_pct_equity": (btc + hype) / 50.0,
            },
            "hypothetical_ten_slot_capacity": {
                "position_count": 10,
                "isolated_margin_at_risk_usd": 5000.0,
                "isolated_margin_at_risk_pct_equity": 100.0,
                "p99_stop_wave_loss_usd": 467.3069039312105,
                "p99_stop_wave_loss_pct_equity": 9.34613807862421,
            },
        },
    }


def _asset_stress(loss: float) -> dict[str, object]:
    return {
        "stop_bps": 80.0,
        "visible_depth_complete_rate": 1.0,
        "visible_cost_sample_count": 240,
        "current_profile_cap_usd": 5000.0,
        "candidate_nonbinding_cap_usd": 5000.0,
        "p99_total_loss_pct_equity": loss / 50.0,
        "p99": {"total_loss_usd": loss},
    }


def _preflight(config: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "authority": {"execution_authority": "none"},
        "identity": {
            "candidate_profile_id": getattr(config, "profile_id"),
            "candidate_profile_fingerprint": getattr(config, "profile_fingerprint"),
        },
        "portfolio": {
            "flat_no_orders": True,
            "ledger_reconciled": True,
            "sizing_technically_ready": True,
            "technically_ready_for_profile_transition": True,
            "open_positions": 0,
            "open_orders": 0,
        },
    }


def _passing_checks(*args: object, **kwargs: object) -> dict[str, object]:
    return {"shared": {"passed": True, "reasons": []}}
