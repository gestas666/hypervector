"""Technical acceptance contract for the exact eight-asset V58 profile."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from importlib import import_module, util
import json
from pathlib import Path
from types import ModuleType

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_configuration_exit_policy import (
    provider_exit_expectation,
    provider_exit_policy_evidence,
)

_PROFILE = Path(
    "configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml"
)
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_eight_asset_growth_sizing_stress_20260819_v1.json"
)
_NOW = datetime(2026, 8, 19, 6, 0, tzinfo=UTC)


def _acceptance() -> ModuleType:
    name = "hypervector.research.v58_poststart_acceptance"
    assert util.find_spec(name) is not None, "V58 acceptance module is missing"
    return import_module(name)


def test_exact_v58_accepts_all_routes_sizing_and_exit_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance must reconcile the exact eight-asset runtime contract."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v58_poststart_acceptance(
        _checkpoint(config),
        config,
        _stress(),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["contract"]["performance_gate"] is False
    assert report["checks"]["direction_scope_identity"] == {
        "passed": True,
        "reasons": [],
        "provider_symbol_routes": 10,
        "directional_scopes": 14,
    }
    assert report["checks"]["asset_sizing_identity"]["passed"] is True
    assert report["checks"]["provider_exit_identity"]["passed"] is True


def test_v58_rejects_runtime_direction_or_sizing_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loaded route side or allocation may not differ from frozen V58."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    directions = checkpoint["configuration_generation"][
        "current_provider_execution_directions"
    ]
    directions["hulk_expansion_bidirectional_tuned_v2|SOL"] = ["long", "short"]
    checkpoint["configuration_generation"]["current_asset_sizing"]["HYPE"][
        "margin_fraction"
    ] = 0.11
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v58_poststart_acceptance(
        checkpoint, config, _stress(), _preflight(config), now_utc=_NOW
    )

    assert report["accepted"] is False
    assert "runtime_direction_scope_mismatch" in report["reasons"]
    assert "runtime_asset_sizing_mismatch" in report["reasons"]


def test_v58_rejects_runtime_exit_policy_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loaded hold or profit-protection policy may not differ from V58."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    policies = checkpoint["configuration_generation"]["current_provider_exit_policies"]
    policies["hype_breakout_compression_alignment_bidirectional_v2"][
        "hard_maximum_hold_seconds"
    ] = 172_800
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v58_poststart_acceptance(
        checkpoint, config, _stress(), _preflight(config), now_utc=_NOW
    )

    assert report["accepted"] is False
    assert "runtime_provider_exit_mismatch" in report["reasons"]


def test_v58_missing_provider_coverage_returns_a_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial startup checkpoint must reject cleanly instead of crashing."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    routes = checkpoint["audit"]["readiness"]["by_provider_symbol"]
    routes.pop("hulk_expansion_bidirectional_tuned_v2|SOL")
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v58_poststart_acceptance(
        checkpoint, config, _stress(), _preflight(config), now_utc=_NOW
    )

    assert report["accepted"] is False
    assert "v58_provider_coverage_incomplete" in report["reasons"]


def test_v58_rejects_stress_evidence_from_another_envelope() -> None:
    """Post-start acceptance must bind the exact V58 stress identity."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    stress = deepcopy(_stress())
    stress["v58_preflight_evidence"]["maximum_configured_margin_fraction"] = 0.45

    with pytest.raises(ValueError, match="V58 stress evidence"):
        acceptance.build_v58_poststart_acceptance(
            _checkpoint(config),
            config,
            stress,
            _preflight(config),
            now_utc=_NOW,
        )


def _checkpoint(config: object) -> dict[str, object]:
    providers = getattr(config, "providers")
    directions = {
        f"{provider.strategy_id}|{symbol}": sorted(provider.executable_sides(symbol))
        for provider in providers
        for symbol in provider.execution_symbols
    }
    sizing = {
        asset.symbol: {
            "leverage": asset.leverage,
            "margin_fraction": asset.margin_fraction,
            "max_notional_usd": asset.max_notional_usd,
        }
        for asset in getattr(config, "assets")
    }
    return {
        "audit": {
            "run": {"run_id": "v58-live"},
            "health": {"assets": {}},
            "open_trade_reflections": {"trades": []},
            "readiness": {
                "by_provider_symbol": {route: {"count": 1} for route in directions}
            },
        },
        "configuration_generation": {
            "current_provider_execution_directions": directions,
            "current_asset_sizing": sizing,
            "current_provider_exit_policies": provider_exit_policy_evidence(
                provider_exit_expectation(config)
            ),
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


def _stress() -> dict[str, object]:
    return json.loads(_STRESS.read_text())


def _passing_checks(*args: object, **kwargs: object) -> dict[str, object]:
    return {"shared": {"passed": True, "reasons": []}}
