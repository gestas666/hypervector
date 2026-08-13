"""Technical acceptance contract for six-asset growth profile v50."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v50_poststart_acceptance as acceptance
import hypervector.research.v51_poststart_acceptance as v51_acceptance

_PROFILE = Path("configs/multi_asset_growth_first_5000_six_asset_candidate_v50.toml")
_V51_PROFILE = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)
_NOW = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)
_ASSETS = {"BTC", "ETH", "SOL", "HYPE", "xyz:SP500", "xyz:SPCX"}


def test_exact_v50_binds_six_assets_routes_and_growth_sizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance must bind all six assets and twelve directional scopes."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(
        acceptance,
        "_shared_acceptance_checks",
        lambda *args, **kwargs: {"shared": {"passed": True, "reasons": []}},
    )

    report = acceptance.build_v50_poststart_acceptance(
        _checkpoint(config),
        config,
        _friction(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["schema_version"] == "v50_poststart_acceptance_v1"
    scope = report["checks"]["direction_scope_identity"]
    assert scope["provider_symbol_routes"] == 7
    assert scope["directional_scopes"] == 12


def test_v50_rejects_wrong_friction_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A prior four-asset stress report cannot masquerade as v50 evidence."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    friction = _friction(config)
    friction["schema_version"] = "v49_portfolio_friction_stress_v1"
    monkeypatch.setattr(
        acceptance,
        "_shared_acceptance_checks",
        lambda *args, **kwargs: {"shared": {"passed": True, "reasons": []}},
    )

    with pytest.raises(ValueError, match="v50 friction identity"):
        acceptance.build_v50_poststart_acceptance(
            _checkpoint(config),
            config,
            friction,
            _preflight(config),
            now_utc=_NOW,
        )


def test_exact_v51_binds_profit_protected_six_asset_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The launch audit must bind v51 rather than accepting the v50 draft."""
    config = load_multi_asset_live_config(_V51_PROFILE, mode="observe")
    monkeypatch.setattr(
        v51_acceptance,
        "_shared_acceptance_checks",
        lambda *args, **kwargs: {"shared": {"passed": True, "reasons": []}},
    )

    report = v51_acceptance.build_v51_poststart_acceptance(
        _checkpoint(config),
        config,
        _friction(config, schema="v51_growth_sizing_stress_v1"),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["schema_version"] == "v51_poststart_acceptance_v1"
    assert report["checks"]["direction_scope_identity"]["directional_scopes"] == 12


def test_v51_rejects_an_open_index_without_its_bound_profit_lock_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Venue protection alone cannot success-shape a planless index restart."""
    config = load_multi_asset_live_config(_V51_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    checkpoint["audit"] = {
        "run": {"run_id": "v51-live"},
        "health": {
            "assets": {
                "xyz:SP500": {"final_state": "OPEN"},
            }
        },
        "open_trade_reflections": {"trades": []},
    }
    monkeypatch.setattr(
        v51_acceptance,
        "_shared_acceptance_checks",
        lambda *args, **kwargs: {"shared": {"passed": True, "reasons": []}},
    )

    report = v51_acceptance.build_v51_poststart_acceptance(
        checkpoint,
        config,
        _friction(config, schema="v51_growth_sizing_stress_v1"),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert report["checks"]["bound_execution_plans"]["reasons"] == [
        "open_lifecycle_missing_bound_execution_plan:xyz:SP500"
    ]


def _checkpoint(config: object) -> dict[str, object]:
    directions = {
        f"{provider.strategy_id}|{symbol}": sorted(provider.sides)
        for provider in getattr(config, "providers")
        for symbol in provider.execution_symbols
    }
    return {
        "audit": {"run": {"run_id": "v50-live"}},
        "configuration_generation": {
            "current_provider_execution_directions": directions,
        },
    }


def _friction(
    config: object,
    *,
    schema: str = "v50_growth_sizing_stress_v1",
) -> dict[str, object]:
    scenarios = [
        {
            "account_value_usd": value,
            "maximum_simultaneous_positions": 6,
            "account_position_capacity": 10,
            "route_aware_maximum_margin_fraction": 0.6,
            "asset_slots": {asset: {} for asset in _ASSETS},
        }
        for value in (500.0, 5_000.0)
    ]
    return {
        "schema_version": schema,
        "profile_id": getattr(config, "profile_id"),
        "profile_fingerprint": getattr(config, "profile_fingerprint"),
        "contract": {"report_only": True, "execution_authority": "none"},
        "visible_depth_contract": {
            "source": "explicit_candidate_notional_override",
            "p99_bps_by_asset": {asset: 1.0 for asset in _ASSETS},
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
