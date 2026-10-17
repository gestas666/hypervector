"""Technical acceptance contract for the SP500 short-containment successor."""

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
    "configs/"
    "multi_asset_growth_first_5000_eight_asset_sp500_short_containment_candidate_v59.toml"
)
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_eight_asset_growth_sizing_stress_20260819_v1.json"
)
_SP500_ROUTE = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500"
_SPCX_ROUTE = "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX"
_V58_FINGERPRINT = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
_V59_FINGERPRINT = "c057882fdd0818831076685aa0fb0134b22889618f6c145ca8e1f9f33111ab78"
_ACCOUNTING_START_MS = 1_787_164_729_837
_NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def _acceptance() -> ModuleType:
    name = "hypervector.research.v59_poststart_acceptance"
    assert util.find_spec(name) is not None, "V59 acceptance module is missing"
    return import_module(name)


@pytest.mark.evidence
def test_exact_v59_accepts_thirteen_directions_and_unchanged_risk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance must bind containment plus unchanged sizing and exits."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v59_poststart_acceptance(
        _checkpoint(config),
        config,
        _stress(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["contract"]["performance_gate"] is False
    assert report["checks"]["direction_scope_identity"] == {
        "passed": True,
        "reasons": [],
        "provider_symbol_routes": 10,
        "directional_scopes": 13,
    }
    assert report["checks"]["sp500_long_authority_absent"]["passed"] is True
    assert report["checks"]["asset_sizing_identity"]["passed"] is True
    assert report["checks"]["provider_exit_identity"]["passed"] is True
    assert report["checks"]["accounting_epoch_lineage"]["passed"] is True


@pytest.mark.evidence
def test_v59_rejects_reintroduced_sp500_long_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime telemetry must not restore the contained SP500 long scope."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    directions = checkpoint["configuration_generation"][
        "current_provider_execution_directions"
    ]
    directions[_SP500_ROUTE] = ["long", "short"]
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v59_poststart_acceptance(
        checkpoint,
        config,
        _stress(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "runtime_direction_scope_mismatch" in report["reasons"]
    assert "sp500_long_authority_present" in report["reasons"]


@pytest.mark.evidence
def test_v59_rejects_sizing_exit_and_provider_coverage_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No unrelated V58 contract may drift under the containment candidate."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    checkpoint["configuration_generation"]["current_asset_sizing"]["BTC"][
        "margin_fraction"
    ] = 0.11
    checkpoint["configuration_generation"]["current_provider_exit_policies"][
        "hype_breakout_compression_alignment_bidirectional_v2"
    ]["hard_maximum_hold_seconds"] = 172_800
    checkpoint["audit"]["readiness"]["by_provider_symbol"].pop(
        "hulk_expansion_bidirectional_tuned_v2|SOL"
    )
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v59_poststart_acceptance(
        checkpoint,
        config,
        _stress(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "v59_provider_coverage_incomplete" in report["reasons"]
    assert "runtime_asset_sizing_mismatch" in report["reasons"]
    assert "runtime_provider_exit_mismatch" in report["reasons"]


@pytest.mark.evidence
def test_v59_rejects_spcx_cash_open_source_unavailability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evaluation count cannot disguise a persistently unavailable SPCX source."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    checkpoint["audit"]["readiness"]["by_provider_symbol"][_SPCX_ROUTE] = {
        "count": 5_889,
        "latest_reason": "cash_open_trade_bars_incomplete",
        "latest_backend_non_action_reason": "cash_open_trade_bars_incomplete",
        "latest_blockers": ["cash_open_trade_bars_incomplete"],
        "latest_metrics": {"technical_availability": "unavailable"},
    }
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v59_poststart_acceptance(
        checkpoint,
        config,
        _stress(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "spcx_cash_open_source_unavailable" in report["reasons"]
    assert report["checks"]["spcx_source_availability"] == {
        "passed": False,
        "reasons": ["spcx_cash_open_source_unavailable"],
        "evaluations": 5_889,
        "latest_reason": "cash_open_trade_bars_incomplete",
        "latest_backend_non_action_reason": "cash_open_trade_bars_incomplete",
        "signal_source": None,
        "public_trade_count": None,
    }


@pytest.mark.evidence
@pytest.mark.parametrize(
    "accounting_epoch",
    [
        None,
        {
            "epoch_id": "v59_fresh_reset",
            "profile_fingerprint": _V59_FINGERPRINT,
            "start_venue_timestamp_ms": 1_787_396_800_000,
            "included_profile_fingerprints": [
                _V58_FINGERPRINT,
                _V59_FINGERPRINT,
            ],
        },
        {
            "epoch_id": "v58_v59_growth_5000",
            "profile_fingerprint": "f" * 64,
            "start_venue_timestamp_ms": _ACCOUNTING_START_MS,
            "included_profile_fingerprints": [
                _V58_FINGERPRINT,
                _V59_FINGERPRINT,
            ],
        },
        {
            "epoch_id": "v58_v59_growth_5000",
            "profile_fingerprint": _V59_FINGERPRINT,
            "start_venue_timestamp_ms": _ACCOUNTING_START_MS,
            "included_profile_fingerprints": [_V59_FINGERPRINT],
        },
        {
            "epoch_id": "v58_v59_growth_5000",
            "profile_fingerprint": _V59_FINGERPRINT,
            "start_venue_timestamp_ms": _ACCOUNTING_START_MS,
            "included_profile_fingerprints": [
                _V59_FINGERPRINT,
                _V58_FINGERPRINT,
                _V59_FINGERPRINT,
            ],
        },
    ],
)
def test_v59_rejects_missing_reset_or_changed_accounting_lineage(
    monkeypatch: pytest.MonkeyPatch,
    accounting_epoch: dict[str, object] | None,
) -> None:
    """Post-start acceptance must retain the original funded-run scope."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    checkpoint = _checkpoint(config)
    checkpoint["audit"]["portfolio_archive"]["accounting_epoch"] = accounting_epoch
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v59_poststart_acceptance(
        checkpoint,
        config,
        _stress(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "v59_accounting_epoch_lineage_mismatch" in report["reasons"]


@pytest.mark.evidence
def test_v59_rejects_foreign_stress_or_preflight_identity() -> None:
    """Every economic and transition input must bind the candidate fingerprint."""
    acceptance = _acceptance()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    stress = _stress(config)
    stress["profile_fingerprint"] = "foreign"
    with pytest.raises(ValueError, match="V59 stress evidence"):
        acceptance.build_v59_poststart_acceptance(
            _checkpoint(config),
            config,
            stress,
            _preflight(config),
            now_utc=_NOW,
        )

    preflight = _preflight(config)
    preflight["identity"]["candidate_profile_fingerprint"] = "foreign"
    with pytest.raises(ValueError, match="flat and order-free"):
        acceptance.build_v59_poststart_acceptance(
            _checkpoint(config),
            config,
            _stress(config),
            preflight,
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
    readiness = {route: {"count": 1} for route in directions}
    readiness[_SPCX_ROUTE] = {
        "count": 1,
        "latest_reason": "cash_session_closed",
        "latest_backend_non_action_reason": "activation_readiness_seed",
        "latest_blockers": ["cash_session_closed"],
        "latest_metrics": {
            "signal_source": "hyperliquid_ws_trades",
            "gap_threshold_bps": 20.0,
            "public_trade_count": 12,
        },
    }
    return {
        "audit": {
            "run": {"run_id": "v59-live"},
            "health": {"assets": {}},
            "open_trade_reflections": {"trades": []},
            "readiness": {"by_provider_symbol": readiness},
            "portfolio_archive": {
                "accounting_epoch": {
                    "epoch_id": "v58_v59_growth_5000",
                    "profile_fingerprint": _V59_FINGERPRINT,
                    "start_venue_timestamp_ms": _ACCOUNTING_START_MS,
                    "included_profile_fingerprints": [
                        _V58_FINGERPRINT,
                        _V59_FINGERPRINT,
                    ],
                }
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


def _stress(config: object) -> dict[str, object]:
    document = deepcopy(json.loads(_STRESS.read_text(encoding="utf-8")))
    document["profile_id"] = getattr(config, "profile_id")
    document["profile_fingerprint"] = getattr(config, "profile_fingerprint")
    return document


def _passing_checks(*args: object, **kwargs: object) -> dict[str, object]:
    return {"shared": {"passed": True, "reasons": []}}
