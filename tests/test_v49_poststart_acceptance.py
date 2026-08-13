"""Technical acceptance contract for repaired growth profile v49."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v49_poststart_acceptance as acceptance

_PROFILE = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")
_NOW = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)


def test_exact_v49_binds_symbol_stop_repair_and_growth_sizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance must bind the four-slot profile with SOL's stop override."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(
        acceptance,
        "_shared_acceptance_checks",
        lambda *args, **kwargs: {"shared": {"passed": True, "reasons": []}},
    )

    report = acceptance.build_v49_poststart_acceptance(
        _checkpoint(config),
        config,
        _friction(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["schema_version"] == "v49_poststart_acceptance_v1"
    assert report["checks"]["direction_scope_identity"]["provider_symbol_routes"] == 5
    contracts = config.provider_execution_contracts
    assert contracts["range_onset_bidirectional_v1"].stop_bps == 60.0
    assert contracts[("range_onset_bidirectional_v1", "SOL")].stop_bps == 80.0


def test_v49_rejects_v48_friction_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unrepaired v48 stress identity cannot masquerade as v49."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    friction = _friction(config)
    friction["schema_version"] = "v48_portfolio_friction_stress_v1"
    monkeypatch.setattr(
        acceptance,
        "_shared_acceptance_checks",
        lambda *args, **kwargs: {"shared": {"passed": True, "reasons": []}},
    )

    with pytest.raises(ValueError, match="v49 friction identity"):
        acceptance.build_v49_poststart_acceptance(
            _checkpoint(config),
            config,
            friction,
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
        "audit": {"run": {"run_id": "v49-live"}},
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
        "schema_version": "v49_portfolio_friction_stress_v1",
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
