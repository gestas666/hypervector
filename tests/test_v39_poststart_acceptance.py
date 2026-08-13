"""Exact technical acceptance for the staged v39 live profile."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.v39_poststart_acceptance import (
    build_v39_poststart_acceptance,
)
from v39_canonical_regime_fixture import canonical_regime_summary

_CONFIG = Path(
    "configs/"
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
_NOW = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)


def test_accepts_exact_v39_with_causally_explained_pressure_gaps() -> None:
    """Unavailable numeric pressure is valid only with exact status accounting."""
    config = _config()

    report = build_v39_poststart_acceptance(_checkpoint(config), config, now_utc=_NOW)

    assert report["accepted"] is True
    assert report["decision"] == "accepted"
    assert report["reasons"] == []
    assert report["checks"]["route_identity"]["provider_symbol_routes"] == 14
    assert report["checks"]["route_identity"]["directional_scopes"] == 28
    assert report["checks"]["hip3_pressure"]["explained_numeric_gaps"] == 8


def test_rejects_missing_pressure_status_without_success_shape() -> None:
    """An absent causal status cannot explain missing numeric L2 values."""
    config = _config()
    checkpoint = _checkpoint(config)
    route = _pressure_routes(config)[0]
    metrics = checkpoint["audit"]["signal_outcomes"]["by_provider_symbol"][route][
        "metric_diagnostics"
    ]["metrics"]
    del metrics["pressure_status"]

    report = build_v39_poststart_acceptance(checkpoint, config, now_utc=_NOW)

    assert report["accepted"] is False
    assert f"pressure_status_incomplete:{route}" in report["reasons"]


def test_rejects_stale_checkpoint_or_runtime_configuration() -> None:
    """Old telemetry and a staged/runtime mismatch both prevent acceptance."""
    config = _config()
    checkpoint = _checkpoint(config)
    checkpoint["generated_at_utc"] = (_NOW - timedelta(minutes=5)).isoformat()
    checkpoint["configuration_generation"]["matches_runtime"] = False
    checkpoint["configuration_generation"]["state"] = "stale_runtime_configuration"

    report = build_v39_poststart_acceptance(checkpoint, config, now_utc=_NOW)

    assert report["accepted"] is False
    assert "checkpoint_not_fresh" in report["reasons"]
    assert "runtime_configuration_not_current" in report["reasons"]


def test_rejects_an_unprotected_open_position() -> None:
    """Every open v39 position must retain an owned reduce-only stop."""
    config = _config()
    checkpoint = _checkpoint(config)
    asset = checkpoint["audit"]["health"]["assets"]["SOL"]
    asset.update(final_state="OPEN", protected_if_open=False, stop_oid=None)

    report = build_v39_poststart_acceptance(checkpoint, config, now_utc=_NOW)

    assert report["accepted"] is False
    assert "open_position_unprotected:SOL" in report["reasons"]


def _config() -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(_CONFIG, mode="observe")


def _checkpoint(config: MultiAssetLiveConfig) -> dict[str, object]:
    routes = _routes(config)
    pressure = frozenset(_pressure_routes(config))
    by_route = {route: _route_diagnostics(route in pressure) for route in routes}
    return {
        "schema_version": 1,
        "generated_at_utc": (_NOW - timedelta(seconds=5)).isoformat(),
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_pause": False,
            "automatic_retuning": False,
            "runtime_strategy_changed": False,
        },
        "lifecycle": _lifecycle(config),
        "configuration_generation": _generation(config),
        "audit": _audit(config, routes, by_route),
    }


def _audit(
    config: MultiAssetLiveConfig,
    routes: list[str],
    by_route: dict[str, object],
) -> dict[str, object]:
    assets = {
        symbol: {
            "faults": 0,
            "final_state": "FLAT",
            "open_order_ids": [],
            "position_size_signed": 0.0,
            "protected_if_open": True,
            "stop_oid": None,
            "stop_reason": None,
        }
        for symbol in config.symbols
    }
    return {
        "run": {
            "profile_id": config.profile_id,
            "profile_fingerprint": config.profile_fingerprint,
            "run_id": "bidirectional-live-v39-test",
            "symbols": list(config.symbols),
            "executable_provider_symbols": routes,
            "observe_only_provider_symbols": [],
            "maximum_concurrent_positions": config.maximum_positions,
        },
        "routing": {"executable_provider_symbols": routes},
        "canonical_regime_telemetry": canonical_regime_summary(
            _NOW - timedelta(seconds=10)
        ),
        "coverage": {
            "complete": False,
            "technical_gaps": ["provider_metric_telemetry_missing"],
        },
        "health": {"faults": 0, "assets": assets},
        "signal_outcomes": {
            "coverage": {
                "complete": False,
                "market_data_complete": True,
                "metric_telemetry_complete": False,
                "evaluations_without_metrics": 0,
                "metric_value_gaps": 8,
                "missing_data_observations": 0,
                "direction_conflicts": 0,
            },
            "by_provider_symbol": by_route,
        },
        "execution": _execution(routes),
    }


def _lifecycle(config: MultiAssetLiveConfig) -> dict[str, object]:
    return {
        "backend_process_health": "healthy",
        "cohort_heartbeat_status": "running",
        "cohort_heartbeat_age_seconds": 2.0,
        "state": "running_consistent",
        "faulted_assets": [],
        "asset_states": dict.fromkeys(config.symbols, "FLAT"),
    }


def _generation(config: MultiAssetLiveConfig) -> dict[str, object]:
    return {
        "state": "current_runtime_configuration",
        "matches_runtime": True,
        "runtime_profile_fingerprint": config.profile_fingerprint,
        "current_profile_fingerprint": config.profile_fingerprint,
        "blocking_assets": [],
        "execution_authority": "none",
        "automatic_restart": False,
    }


def _routes(config: MultiAssetLiveConfig) -> list[str]:
    return sorted(
        f"{provider}|{symbol}"
        for provider, symbol in config.executable_provider_symbols
    )


def _pressure_routes(config: MultiAssetLiveConfig) -> list[str]:
    return [
        route
        for route in _routes(config)
        if route.startswith("hip3_breakout_pressure_")
    ]


def _route_diagnostics(pressure: bool) -> dict[str, object]:
    if not pressure:
        return {
            "evaluations": 2,
            "metric_diagnostics": {
                "coverage": {
                    "complete": True,
                    "evaluations_with_metrics": 2,
                    "evaluations_without_metrics": 0,
                    "metric_value_gaps": 0,
                },
                "metrics": {},
            },
        }
    metrics = {
        "pressure_status": {
            "kind": "categorical",
            "value_type": "str",
            "observations": 2,
            "missing_evaluations": 0,
            "categories": [
                {"value": "available", "count": 1},
                {"value": "no_candidate", "count": 1},
            ],
        },
        "imbalance_10": _numeric_metric(-0.4, -0.4),
        "pressure_age_seconds": _numeric_metric(0.05, 0.05),
    }
    return {
        "evaluations": 2,
        "metric_diagnostics": {
            "coverage": {
                "complete": False,
                "evaluations_with_metrics": 2,
                "evaluations_without_metrics": 0,
                "metric_value_gaps": 2,
            },
            "metrics": metrics,
        },
    }


def _numeric_metric(minimum: float, maximum: float) -> dict[str, object]:
    return {
        "kind": "numeric",
        "value_type": "float",
        "observations": 1,
        "missing_evaluations": 1,
        "minimum": minimum,
        "mean": (minimum + maximum) / 2,
        "maximum": maximum,
    }


def _execution(routes: list[str]) -> dict[str, object]:
    return {
        "fees_usd": 0.0,
        "funding_usd": 0.0,
        "current_run_fills": 0,
        "friction_parity": {
            "by_provider_symbol": {
                route: {
                    "execution_effect": "report_only",
                    "parity_state": "runtime_shape_aligned",
                    "mismatches": [],
                }
                for route in routes
            }
        },
    }
