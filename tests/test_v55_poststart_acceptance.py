"""Technical acceptance contract for the additive v55 SPCX route."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.hip3_cash_open_gap_provider import (
    HIP3_SPCX_CASH_OPEN_STRATEGY,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v55_poststart_acceptance as acceptance

_PROFILE = Path("configs/multi_asset_growth_first_5000_spcx_cash_open_v55.toml")
_NOW = datetime(2026, 8, 18, 10, 30, tzinfo=UTC)


def test_exact_v55_accepts_additive_route_and_dynamic_exit_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance binds SPCX without changing the inherited BTC/HYPE routes."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v55_poststart_acceptance(
        _checkpoint(config),
        config,
        _candidate(),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["checks"]["spcx_execution_contract"]["target_policy"] == (
        "absolute_anchor"
    )
    assert report["checks"]["spcx_readiness"]["signal_source"] == (
        "hyperliquid_ws_trades"
    )
    assert report["candidate_identity"]["technical_disposition"] == (
        "NOT_SUITABLE_TECHNICALLY_UNRESOLVED"
    )


def test_v55_rejects_runtime_that_omits_recipe_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A matching profile label cannot hide a missing cash-session exit policy."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    policies = checkpoint["configuration_generation"]["current_provider_exit_policies"]
    policies[HIP3_SPCX_CASH_OPEN_STRATEGY]["provider_recipe_exit_policy"] = "ignore"
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v55_poststart_acceptance(
        checkpoint,
        config,
        _candidate(),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "spcx_execution_contract_mismatch" in report["reasons"]


def _checkpoint(config: object) -> dict[str, object]:
    directions = {
        f"{provider.strategy_id}|{symbol}": sorted(provider.sides)
        for provider in getattr(config, "providers")
        for symbol in provider.execution_symbols
    }
    route = f"{HIP3_SPCX_CASH_OPEN_STRATEGY}|xyz:SPCX"
    return {
        "audit": {
            "run": {"run_id": "v55-live"},
            "health": {"assets": {}},
            "open_trade_reflections": {"trades": []},
            "readiness": {
                "by_provider_symbol": {
                    route: {
                        "count": 1,
                        "latest_metrics": {
                            "signal_source": "hyperliquid_ws_trades",
                            "gap_threshold_bps": 20.0,
                            "public_trade_count": 42,
                        },
                    }
                }
            },
        },
        "configuration_generation": {
            "current_provider_execution_directions": directions,
            "current_provider_exit_policies": {
                HIP3_SPCX_CASH_OPEN_STRATEGY: {
                    "maximum_hold_seconds": 22500,
                    "provider_recipe_exit_policy": "honor",
                }
            },
        },
    }


def _candidate() -> dict[str, object]:
    return {
        "schema_version": "hip3_cash_open_gap_reversal_development_v1",
        "symbol": "xyz:SPCX",
        "report_only": True,
        "execution_authority": "none",
        "holdout_accessed": False,
        "validation_accessed": False,
        "automatic_promotion": False,
        "live_roster_change": False,
        "research_disposition": {
            "live_change_proposed": False,
            "status": "NOT_SUITABLE_TECHNICALLY_UNRESOLVED",
        },
        "strategy_identity": {
            "provider_id": "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_research_v1",
            "timeframe": "15m",
        },
        "applied_execution": {
            "leverage": 10.0,
            "notional_usd": 5000.0,
            "margin_fraction": 0.1,
            "stop_bps": 80.0,
            "maximum_hold_seconds": 22500,
            "target_policy": "prior_eligible_cash_session_close",
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
