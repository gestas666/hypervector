"""Technical acceptance contract for evidence-pruned growth profile v48."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v48_poststart_acceptance as acceptance


_PROFILE = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v48.toml")
_NOW = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)


def test_exact_v48_binds_pruned_routes_and_growth_sizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance must require the exact four-slot successor contract."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(
        acceptance,
        "_shared_acceptance_checks",
        lambda *args, **kwargs: {"shared": {"passed": True, "reasons": []}},
    )

    report = acceptance.build_v48_poststart_acceptance(
        _checkpoint(config),
        config,
        _friction(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["schema_version"] == "v48_poststart_acceptance_v1"
    assert report["checks"]["direction_scope_identity"] == {
        "passed": True,
        "reasons": [],
        "provider_symbol_routes": 5,
        "directional_scopes": 8,
    }
    assert report["friction_identity"]["maximum_simultaneous_positions"] == 4
    assert report["friction_identity"]["maximum_margin_fraction"] == 0.6


def test_v48_rejects_sp500_or_wrong_candidate_friction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retired route or v47 stress cannot masquerade as v48 evidence."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    checkpoint["configuration_generation"]["current_provider_execution_directions"][
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2|xyz:SP500"
    ] = [
        "long",
        "short",
    ]
    monkeypatch.setattr(
        acceptance,
        "_shared_acceptance_checks",
        lambda *args, **kwargs: {"shared": {"passed": True, "reasons": []}},
    )
    report = acceptance.build_v48_poststart_acceptance(
        checkpoint,
        config,
        _friction(config),
        _preflight(config),
        now_utc=_NOW,
    )
    assert report["accepted"] is False
    assert "runtime_direction_scope_mismatch" in report["reasons"]

    wrong = _friction(config)
    wrong["scenarios"][0]["maximum_simultaneous_positions"] = 5
    with pytest.raises(ValueError, match="v48 friction identity"):
        acceptance.build_v48_poststart_acceptance(
            _checkpoint(config), config, wrong, _preflight(config), now_utc=_NOW
        )


def _checkpoint(config: object) -> dict[str, object]:
    directions = {
        f"{provider.strategy_id}|{symbol}": sorted(provider.sides)
        for provider in getattr(config, "providers")
        for symbol in provider.execution_symbols
    }
    return {
        "audit": {"run": {"run_id": "v48-live"}},
        "configuration_generation": {
            "current_provider_execution_directions": directions,
        },
    }


def _friction(config: object) -> dict[str, object]:
    assets = {"BTC", "ETH", "SOL", "HYPE"}
    scenarios = [
        {
            "account_value_usd": value,
            "maximum_simultaneous_positions": 4,
            "account_position_capacity": 10,
            "route_aware_maximum_margin_fraction": 0.6,
            "asset_slots": {asset: {} for asset in assets},
        }
        for value in (500.0, 5_000.0)
    ]
    return {
        "schema_version": "v48_portfolio_friction_stress_v1",
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
