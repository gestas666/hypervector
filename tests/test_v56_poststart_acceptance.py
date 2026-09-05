"""Technical acceptance contract for the incremental v56 BTC route."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.btc_hulk_robust_short_provider import (
    HULK_TUNED_SHORT_STRATEGY,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v56_poststart_acceptance as acceptance

_PROFILE = Path("configs/multi_asset_growth_first_5000_btc_tuned_v2_increment_v56.toml")
_NOW = datetime(2026, 8, 18, 13, 0, tzinfo=UTC)


def test_exact_v56_accepts_increment_and_preserved_portfolio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance binds the added route while preserving all v55 assets."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v56_poststart_acceptance(
        _checkpoint(config),
        config,
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["checks"]["tuned_v2_execution_contract"]["target_r_multiple"] == 3.0
    assert report["checks"]["tuned_v2_readiness"]["minimum_score"] == 8
    assert report["checks"]["direction_scope_identity"]["passed"] is True


def test_v56_rejects_missing_tuned_v2_exit_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A profile label cannot hide a missing tuned-v2 terminal exit."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    policies = checkpoint["configuration_generation"]["current_provider_exit_policies"]
    policies[HULK_TUNED_SHORT_STRATEGY]["maximum_hold_seconds"] = 172_800
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v56_poststart_acceptance(
        checkpoint,
        config,
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "tuned_v2_execution_contract_mismatch" in report["reasons"]


def test_v56_rejects_wrong_tuned_profile_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telemetry must prove tuned-v2 parameters rather than relabeled v3."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    route = f"{HULK_TUNED_SHORT_STRATEGY}|BTC"
    checkpoint["audit"]["readiness"]["by_provider_symbol"][route]["latest_metrics"][
        "entry_score_minimum"
    ] = 7
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v56_poststart_acceptance(
        checkpoint,
        config,
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "tuned_v2_readiness_contract_missing" in report["reasons"]


def _checkpoint(config: object) -> dict[str, object]:
    directions = {
        f"{provider.strategy_id}|{symbol}": sorted(provider.sides)
        for provider in getattr(config, "providers")
        for symbol in provider.execution_symbols
    }
    route = f"{HULK_TUNED_SHORT_STRATEGY}|BTC"
    return {
        "audit": {
            "run": {"run_id": "v56-live"},
            "health": {"assets": {}},
            "open_trade_reflections": {"trades": []},
            "readiness": {
                "by_provider_symbol": {
                    route: {
                        "count": 1,
                        "latest_metrics": {
                            "entry_score_minimum": 8,
                            "adx_usable": 18.0,
                            "entry_contract": "hulk_expansion_moderate_adx_v1",
                        },
                    }
                }
            },
        },
        "configuration_generation": {
            "current_provider_execution_directions": directions,
            "current_provider_exit_policies": {
                HULK_TUNED_SHORT_STRATEGY: {
                    "maximum_hold_seconds": 86_400,
                    "provider_recipe_exit_policy": "ignore",
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
