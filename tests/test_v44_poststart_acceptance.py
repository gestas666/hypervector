"""Exact technical acceptance contract for a future live v44 run."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v43_poststart_acceptance as shared_acceptance
import hypervector.research.v44_poststart_acceptance as acceptance

_PROFILE = Path(
    "configs/multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml"
)
_NOW = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)


def test_exact_v44_binds_taker_parity_risk_friction_and_sides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The corrected live identity must match every frozen technical input."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(shared_acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v44_poststart_acceptance(
        _checkpoint(config),
        config,
        _risk(config),
        _friction(config),
        _preflight(config, ready=True),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["contract"]["execution_authority"] == "none"
    assert report["checks"]["direction_scope_identity"]["directional_scopes"] == 6
    assert report["friction_identity"]["scenario_accounts_usd"] == [500.0, 5000.0]
    assert report["evidence_identity"]["repeatability_established"] is False


def test_v44_rejects_wrong_friction_or_nonflat_preflight() -> None:
    """Aliased stress evidence and inherited exposure must fail closed."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    wrong = _friction(config)
    wrong["profile_fingerprint"] = "wrong"
    with pytest.raises(ValueError, match="friction identity"):
        acceptance.build_v44_poststart_acceptance(
            _checkpoint(config),
            config,
            _risk(config),
            wrong,
            _preflight(config, ready=True),
            now_utc=_NOW,
        )
    with pytest.raises(ValueError, match="flat and order-free"):
        acceptance.build_v44_poststart_acceptance(
            _checkpoint(config),
            config,
            _risk(config),
            _friction(config),
            _preflight(config, ready=False),
            now_utc=_NOW,
        )


def test_v44_rejects_superseded_long_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The old maker-derived BTC long cannot masquerade as corrected v44."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    directions = checkpoint["configuration_generation"][
        "current_provider_execution_directions"
    ]
    directions.pop("liquidity_sweep_long_1h_stop60_target60_v2|BTC")
    directions["liquidity_sweep_long_1h_stop60_v1|BTC"] = ["long"]
    monkeypatch.setattr(shared_acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v44_poststart_acceptance(
        checkpoint,
        config,
        _risk(config),
        _friction(config),
        _preflight(config, ready=True),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert report["reasons"] == ["runtime_direction_scope_mismatch"]


def _checkpoint(config: object) -> dict[str, object]:
    directions = {
        f"{provider.strategy_id}|{symbol}": sorted(provider.sides)
        for provider in getattr(config, "providers")
        for symbol in provider.execution_symbols
    }
    return {
        "audit": {"run": {"run_id": "v44-live"}},
        "configuration_generation": {
            "current_provider_execution_directions": directions,
        },
    }


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
        "schema_version": "v44_portfolio_friction_stress_v1",
        "profile_id": getattr(config, "profile_id"),
        "profile_fingerprint": getattr(config, "profile_fingerprint"),
        "contract": {"report_only": True, "execution_authority": "none"},
        "scenarios": [
            _friction_scenario(500.0),
            _friction_scenario(5000.0),
        ],
    }


def _friction_scenario(account: float) -> dict[str, object]:
    return {
        "account_value_usd": account,
        "maximum_simultaneous_positions": 3,
        "account_position_capacity": 10,
        "route_aware_maximum_margin_fraction": 0.23203607689310038,
        "asset_slots": {"BTC": {}, "HYPE": {}, "xyz:SP500": {}},
    }


def _preflight(config: object, *, ready: bool) -> dict[str, object]:
    return {
        "schema_version": 1,
        "authority": {"execution_authority": "none"},
        "identity": {
            "candidate_profile_id": getattr(config, "profile_id"),
            "candidate_profile_fingerprint": getattr(config, "profile_fingerprint"),
        },
        "portfolio": {
            "flat_no_orders": ready,
            "ledger_reconciled": True,
            "sizing_technically_ready": True,
            "technically_ready_for_profile_transition": ready,
            "open_positions": 0 if ready else 1,
            "open_orders": 0 if ready else 1,
        },
    }


def _passing_checks(*args: object, **kwargs: object) -> dict[str, object]:
    assert kwargs["checkpoint_age"] == 90.0
    assert kwargs["pressure_age"] == 30.0
    return {"runtime_identity": {"passed": True, "reasons": []}}
