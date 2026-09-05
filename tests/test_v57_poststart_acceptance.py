"""Technical acceptance contract for SPCX short-side containment."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module, util
from pathlib import Path
from types import ModuleType

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_PROFILE = Path("configs/multi_asset_growth_first_5000_spcx_short_containment_v57.toml")
_SPCX = "xyz:SPCX"
_SPCX_PROVIDER = "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1"
_NOW = datetime(2026, 8, 18, 15, 30, tzinfo=UTC)


def _acceptance() -> ModuleType:
    name = "hypervector.research.v57_poststart_acceptance"
    assert util.find_spec(name) is not None, "v57 acceptance module is missing"
    return import_module(name)


def test_exact_v57_accepts_short_only_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance must prove the exact effective SPCX direction and exit contract."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v57_poststart_acceptance(
        _checkpoint(config), config, _preflight(config), now_utc=_NOW
    )

    assert report["accepted"] is True
    assert report["checks"]["direction_scope_identity"]["passed"] is True
    assert report["checks"]["spcx_short_exit_contract"]["passed"] is True
    assert report["checks"]["spcx_long_authority_absent"]["passed"] is True


def test_v57_rejects_a_reintroduced_spcx_long(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checkpoint telemetry cannot include SPCX long authority under v57."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    key = f"{_SPCX_PROVIDER}|{_SPCX}"
    directions = checkpoint["configuration_generation"][
        "current_provider_execution_directions"
    ]
    directions[key] = ["long", "short"]
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v57_poststart_acceptance(
        checkpoint, config, _preflight(config), now_utc=_NOW
    )

    assert report["accepted"] is False
    assert "runtime_direction_scope_mismatch" in report["reasons"]
    assert "spcx_long_authority_present" in report["reasons"]


def _checkpoint(config: object) -> dict[str, object]:
    directions = {
        f"{provider.strategy_id}|{symbol}": sorted(provider.executable_sides(symbol))
        for provider in getattr(config, "providers")
        for symbol in provider.execution_symbols
    }
    return {
        "audit": {
            "run": {"run_id": "v57-live"},
            "health": {"assets": {}},
            "open_trade_reflections": {"trades": []},
        },
        "configuration_generation": {
            "current_provider_execution_directions": directions,
            "current_provider_exit_policies": {
                _SPCX_PROVIDER: {
                    "maximum_hold_seconds": 22_500,
                    "provider_recipe_exit_policy": "honor",
                }
            },
        },
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
