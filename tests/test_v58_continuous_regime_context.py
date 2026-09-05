"""Canonical regime context for the V58 continuous-improvement lane."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.research.v58_continuous_regime_context import (
    load_v58_regime_context,
)

_PROFILE = "24820e4bfad8a978a7b617a29dc0326f8fc0e583389b67e0219ce4ab5789c874"
_RUN_ID = "bidirectional-observe-1787127644202"


def test_loader_projects_exact_canonical_context_without_route_authority(
    tmp_path: Path,
) -> None:
    """All four crypto states remain diagnostic and source-bound."""
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(_payload()), encoding="utf-8")

    collection = load_v58_regime_context(source, observer_status=_observer())

    assert [row.symbol for row in collection.contexts] == [
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
    ]
    assert collection.contexts[0].primary_regime == "RANGE"
    assert collection.contexts[0].readiness_fraction == 2 / 3
    assert collection.contexts[0].blockers == ("awaiting_hourly_sma_cross",)
    assert collection.execution_authority == "none"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("authority", "contract"),
        ("missing_symbol", "symbol set"),
        ("eligible", "evaluation contract"),
    ],
)
def test_loader_rejects_unsafe_or_incomplete_context(
    tmp_path: Path, mutation: str, message: str
) -> None:
    """Regime diagnostics cannot silently become routing or partial evidence."""
    payload = _payload()
    canonical = payload["audit"]["canonical_regime_telemetry"]
    assert isinstance(canonical, dict)
    if mutation == "authority":
        canonical["contract"]["execution_authority"] = "live"
    elif mutation == "missing_symbol":
        canonical["by_symbol"].pop("SOL")
    else:
        canonical["by_symbol"]["ETH"]["latest"]["eligible"] = True
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_v58_regime_context(source, observer_status=_observer())


def _observer() -> dict[str, object]:
    return {
        "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
        "profile_fingerprint": _PROFILE,
        "run_id": _RUN_ID,
        "freshness_status": "fresh",
        "technical_complete": True,
        "provider_symbol_routes": 10,
        "routed_actions": 0,
        "report_only": True,
        "execution_authority": "none",
    }


def _payload() -> dict[str, object]:
    by_symbol = {symbol: _symbol_context(symbol) for symbol in _symbols()}
    return {
        "audit": {
            "run": {
                "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
                "profile_fingerprint": _PROFILE,
                "run_id": _RUN_ID,
            },
            "canonical_regime_telemetry": {
                "schema_version": 1,
                "strategy_id": "canonical_regime_telemetry_v1",
                "contract": {
                    "execution_authority": "none",
                    "intents_emitted": False,
                    "configured_route": False,
                },
                "evaluations": 40,
                "symbols": 4,
                "by_symbol": by_symbol,
            },
        }
    }


def _symbol_context(symbol: str) -> dict[str, object]:
    return {
        "evaluations": 10,
        "latest_observed_at_utc": "2026-08-19T11:00:00+00:00",
        "latest": {
            "symbol": symbol,
            "strategy_id": "canonical_regime_telemetry_v1",
            "decision_action": "regime_observation",
            "eligible": False,
            "backend_non_action_reason": "telemetry_only_no_execution_authority",
            "primary_regime": "RANGE",
            "context_15m": "RANGE",
            "state_1m": "RANGE",
            "state_5m": "RANGE",
            "confidence": 0.25,
            "readiness": {
                "side": "short",
                "readiness_fraction": 2 / 3,
                "blockers": ["awaiting_hourly_sma_cross"],
            },
        },
    }


def _symbols() -> tuple[str, ...]:
    return ("BTC", "ETH", "SOL", "HYPE")
