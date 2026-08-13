"""Exact technical acceptance contract for repaired growth profile v47."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v47_poststart_acceptance as acceptance

_PROFILE = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v47.toml")
_NOW = datetime(2026, 8, 12, 15, 30, tzinfo=UTC)


def test_exact_v47_binds_routes_growth_sizing_and_fresh15_pressure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Technical acceptance requires the exact repaired runtime contract."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    captured: dict[str, object] = {}

    def passing_checks(*args: object, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"shared": {"passed": True, "reasons": []}}

    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", passing_checks)
    report = acceptance.build_v47_poststart_acceptance(
        _checkpoint(config),
        config,
        _friction(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["schema_version"] == "v47_poststart_acceptance_v1"
    assert captured["pressure_age"] == 15.0
    assert report["checks"]["direction_scope_identity"]["provider_symbol_routes"] == 6
    assert report["checks"]["direction_scope_identity"]["directional_scopes"] == 10
    assert report["friction_identity"] == {
        "schema_version": "v47_portfolio_friction_stress_v1",
        "profile_fingerprint": config.profile_fingerprint,
        "scenario_accounts_usd": [500.0, 5000.0],
        "maximum_simultaneous_positions": 5,
        "maximum_margin_fraction": 0.6,
        "configured_leverage": 10.0,
        "variable_tiers": "telemetry_only_not_execution_authorized",
    }


def test_v47_rejects_legacy_hip3_identity_without_reselecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A legacy pressure provider cannot masquerade as repaired v47."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    directions = checkpoint["configuration_generation"][
        "current_provider_execution_directions"
    ]
    repaired = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2|xyz:SP500"
    directions["hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500"] = (
        directions.pop(repaired)
    )
    monkeypatch.setattr(
        acceptance,
        "_shared_acceptance_checks",
        lambda *args, **kwargs: {"shared": {"passed": True, "reasons": []}},
    )

    report = acceptance.build_v47_poststart_acceptance(
        checkpoint,
        config,
        _friction(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "runtime_direction_scope_mismatch" in report["reasons"]


def test_v47_rejects_old_leverage_or_wrong_asset_wave() -> None:
    """v47 acceptance fails closed on a v45-shaped friction artifact."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    friction = _friction(config)
    friction["sizing_policy"]["configured_leverage"] = 5.0
    with pytest.raises(ValueError, match="v47 friction identity"):
        acceptance.build_v47_poststart_acceptance(
            _checkpoint(config),
            config,
            friction,
            _preflight(config),
            now_utc=_NOW,
        )
    wrong_slots = _friction(config)
    wrong_slots["scenarios"][0]["maximum_simultaneous_positions"] = 3
    with pytest.raises(ValueError, match="v47 friction identity"):
        acceptance.build_v47_poststart_acceptance(
            _checkpoint(config),
            config,
            wrong_slots,
            _preflight(config),
            now_utc=_NOW,
        )


def _checkpoint(config: object) -> dict[str, object]:
    directions = {
        f"{provider.strategy_id}|{symbol}": sorted(provider.sides)
        for provider in getattr(config, "providers")
        for symbol in provider.execution_symbols
    }
    return {
        "audit": {"run": {"run_id": "v47-live"}},
        "configuration_generation": {
            "current_provider_execution_directions": directions,
        },
    }


def _friction(config: object) -> dict[str, object]:
    assets = {"BTC", "ETH", "SOL", "HYPE", "xyz:SP500"}
    scenarios = [
        {
            "account_value_usd": value,
            "maximum_simultaneous_positions": 5,
            "account_position_capacity": 10,
            "route_aware_maximum_margin_fraction": 0.6,
            "asset_slots": {asset: {} for asset in assets},
        }
        for value in (500.0, 5000.0)
    ]
    return {
        "schema_version": "v47_portfolio_friction_stress_v1",
        "profile_id": getattr(config, "profile_id"),
        "profile_fingerprint": getattr(config, "profile_fingerprint"),
        "contract": {"report_only": True, "execution_authority": "none"},
        "visible_depth_contract": {
            "source": "explicit_candidate_notional_override",
            "p99_bps_by_asset": {asset: 1.0 for asset in assets},
        },
        "sizing_policy": {
            "configured_leverage": 10.0,
            "variable_tiers": "telemetry_only_not_execution_authorized",
            "readiness_is_win_probability": False,
        },
        "scenarios": scenarios,
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
