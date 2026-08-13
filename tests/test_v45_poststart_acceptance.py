"""Exact technical acceptance contract for the v45 growth candidate."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v43_poststart_acceptance as shared_acceptance
import hypervector.research.v45_poststart_acceptance as acceptance

_PROFILE = Path(
    "configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml"
)
_NOW = datetime(2026, 8, 12, 8, 30, tzinfo=UTC)


def test_exact_v45_binds_growth_margin_depth_and_fixed_leverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Technical acceptance requires the exact growth-sizing evidence."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(shared_acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v45_poststart_acceptance(
        _checkpoint(config),
        config,
        _risk(config),
        _friction(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["schema_version"] == "v45_poststart_acceptance_v2"
    assert report["checks"]["route_native_sizing_features"]["passed"] is True
    assert report["friction_identity"]["maximum_margin_fraction"] == pytest.approx(
        0.30666666666666664
    )
    assert report["friction_identity"]["configured_leverage"] == pytest.approx(5.0)
    assert report["friction_identity"]["variable_tiers"] == (
        "telemetry_only_not_execution_authorized"
    )


def test_v45_rejects_v44_sizing_or_executable_variable_tiers() -> None:
    """Old sizing and success-shaped dynamic authority fail closed."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    old = _friction(config)
    old["scenarios"][0]["route_aware_maximum_margin_fraction"] = 0.23203607689310038
    with pytest.raises(ValueError, match="v45 friction identity"):
        acceptance.build_v45_poststart_acceptance(
            _checkpoint(config),
            config,
            _risk(config),
            old,
            _preflight(config),
            now_utc=_NOW,
        )
    dynamic = _friction(config)
    dynamic["sizing_policy"]["variable_tiers"] = "execution_authorized"
    with pytest.raises(ValueError, match="v45 friction identity"):
        acceptance.build_v45_poststart_acceptance(
            _checkpoint(config),
            config,
            _risk(config),
            dynamic,
            _preflight(config),
            now_utc=_NOW,
        )


def test_v45_rejects_missing_route_native_sizing_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A route cannot lose a sizing input without a technical rejection."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(shared_acceptance, "_shared_acceptance_checks", _passing_checks)
    checkpoint = _checkpoint(config)
    outcomes = checkpoint["audit"]["signal_outcomes"]["by_provider_symbol"]
    route = "hulk_expansion_short_robust_v3|BTC"
    del outcomes[route]["metric_diagnostics"]["metrics"]["entry_score"]

    report = acceptance.build_v45_poststart_acceptance(
        checkpoint,
        config,
        _risk(config),
        _friction(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert report["reasons"] == [f"sizing_feature_missing:{route}:entry_score"]


def _checkpoint(config: object) -> dict[str, object]:
    directions = {
        f"{provider.strategy_id}|{symbol}": sorted(provider.sides)
        for provider in getattr(config, "providers")
        for symbol in provider.execution_symbols
    }
    return {
        "audit": {
            "run": {"run_id": "v45-live"},
            "signal_outcomes": _sizing_outcomes(),
        },
        "configuration_generation": {
            "current_provider_execution_directions": directions,
        },
    }


def _sizing_outcomes() -> dict[str, object]:
    by_route = {}
    for route, names in acceptance._SIZING_FEATURES.items():
        metrics = {
            name: {"observations": 1, "missing_evaluations": 0} for name in names
        }
        by_route[route] = {
            "evaluations": 1,
            "metric_diagnostics": {
                "coverage": {"evaluations_without_metrics": 0},
                "metrics": metrics,
            },
        }
    return {"by_provider_symbol": by_route}


def _risk(config: object) -> dict[str, object]:
    return {
        "schema_version": "btc_specialist_successor_risk_v1",
        "execution_authority": "none",
        "profile_id": getattr(config, "profile_id"),
        "profile_fingerprint": getattr(config, "profile_fingerprint"),
        "repeatability_established": False,
        "evidence_state": "short_n1_long_taker_path_unresolved",
    }


def _friction(config: object) -> dict[str, object]:
    return {
        "schema_version": "v45_portfolio_friction_stress_v1",
        "profile_id": getattr(config, "profile_id"),
        "profile_fingerprint": getattr(config, "profile_fingerprint"),
        "contract": {"report_only": True, "execution_authority": "none"},
        "visible_depth_contract": {
            "source": "explicit_candidate_notional_override",
            "p99_bps_by_asset": {"BTC": 0.64, "HYPE": 1.48, "xyz:SP500": 1.42},
        },
        "sizing_policy": {
            "configured_leverage": 5.0,
            "variable_tiers": "telemetry_only_not_execution_authorized",
            "readiness_is_win_probability": False,
        },
        "scenarios": [_scenario(500.0), _scenario(5_000.0)],
    }


def _scenario(account: float) -> dict[str, object]:
    return {
        "account_value_usd": account,
        "maximum_simultaneous_positions": 3,
        "account_position_capacity": 10,
        "route_aware_maximum_margin_fraction": 0.30666666666666664,
        "asset_slots": {"BTC": {}, "HYPE": {}, "xyz:SP500": {}},
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
    return {"runtime_identity": {"passed": True, "reasons": []}}
