"""Exact technical acceptance contract for a future live v43 run."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v43_poststart_acceptance as acceptance

_PROFILE = Path("configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml")
_NOW = datetime(2026, 8, 12, 1, 0, tzinfo=UTC)


def test_exact_v43_binds_flat_preflight_risk_and_direction_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clean technical run retains exact one-sided provider identities."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v43_poststart_acceptance(
        _checkpoint(config),
        config,
        _risk(config),
        _preflight(config, ready=True),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["contract"]["execution_authority"] == "none"
    assert report["checks"]["direction_scope_identity"]["directional_scopes"] == 6
    assert report["evidence_identity"]["repeatability_established"] is False


def test_v43_rejects_nonflat_preflight_or_wrong_risk_identity() -> None:
    """Prior-run exposure and aliased research cannot authorize acceptance."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    with pytest.raises(ValueError, match="flat and order-free"):
        acceptance.build_v43_poststart_acceptance(
            _checkpoint(config),
            config,
            _risk(config),
            _preflight(config, ready=False),
            now_utc=_NOW,
        )

    wrong = _risk(config)
    wrong["profile_fingerprint"] = "wrong"
    with pytest.raises(ValueError, match="risk identity"):
        acceptance.build_v43_poststart_acceptance(
            _checkpoint(config),
            config,
            wrong,
            _preflight(config, ready=True),
            now_utc=_NOW,
        )


def test_v43_direction_drift_is_a_technical_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A BTC long provider cannot silently acquire short authority."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    directions = checkpoint["configuration_generation"][
        "current_provider_execution_directions"
    ]
    directions["liquidity_sweep_long_1h_stop60_v1|BTC"] = ["long", "short"]
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v43_poststart_acceptance(
        checkpoint,
        config,
        _risk(config),
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
        "audit": {"run": {"run_id": "v43-live"}},
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
        "evidence_state": "two_distinct_forward_exact_n1_routes",
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
