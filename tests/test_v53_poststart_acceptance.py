"""Technical acceptance contract for the v53 HYPE freshness repair."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.hype_compression_alignment_provider import (
    HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v53_poststart_acceptance as acceptance

_PROFILE = Path("configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml")
_NOW = datetime(2026, 8, 17, 4, 30, tzinfo=UTC)


def test_exact_v53_accepts_the_fresh_exit_evidence_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance binds the repaired contract without changing route economics."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v53_poststart_acceptance(
        _checkpoint(config, evidence_age=60),
        config,
        _stress(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["schema_version"] == "v53_poststart_acceptance_v1"
    assert report["checks"]["maximum_hold_evidence_freshness"] == {
        "passed": True,
        "reasons": [],
        "maximum_age_seconds": 60,
    }


def test_v53_rejects_checkpoint_without_the_freshness_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A running identity cannot omit the field that makes the repair effective."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v53_poststart_acceptance(
        _checkpoint(config, evidence_age=None),
        config,
        _stress(config),
        _preflight(config),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "maximum_hold_evidence_freshness_mismatch" in report["reasons"]


def _checkpoint(config: object, *, evidence_age: int | None) -> dict[str, object]:
    directions = {
        f"{provider.strategy_id}|{symbol}": sorted(provider.sides)
        for provider in getattr(config, "providers")
        for symbol in provider.execution_symbols
    }
    route = f"{HYPE_COMPRESSION_ALIGNMENT_STRATEGY}|HYPE"
    return {
        "audit": {
            "run": {"run_id": "v53-live"},
            "health": {"assets": {}},
            "open_trade_reflections": {"trades": []},
            "readiness": {
                "by_provider_symbol": {
                    route: {
                        "count": 1,
                        "latest_metrics": {
                            "alignment_only": True,
                            "breakout_side_alignment_required": True,
                            "breakout_side_relation": "unavailable",
                        },
                    }
                }
            },
        },
        "configuration_generation": {
            "current_provider_execution_directions": directions,
            "current_provider_exit_policies": {
                HYPE_COMPRESSION_ALIGNMENT_STRATEGY: {
                    "maximum_hold_evidence_maximum_age_seconds": evidence_age,
                }
            },
        },
    }


def _stress(config: object) -> dict[str, object]:
    losses = {"BTC": 46.0, "HYPE": 47.0}
    return {
        "schema_version": 3,
        "mode": "cohort_growth_sizing_stress_v3",
        "profile_id": getattr(config, "profile_id"),
        "profile_fingerprint": getattr(config, "profile_fingerprint"),
        "contract": {
            "automatic_sizing_change": False,
            "balance_gate": False,
            "execution_authority": "none",
            "performance_gate": False,
            "profit_forecast": False,
            "report_only": True,
            "runtime_strategy_changed": False,
        },
        "sizing_plan": {
            "actual_roster_maximum_margin_fraction": 0.2,
            "configured_assets": 2,
            "leverage": 10.0,
            "margin_fraction_per_slot": 0.1,
            "maximum_positions": 10,
            "planned_margin_usd_per_slot": 500.0,
            "planned_notional_usd_per_slot": 5000.0,
            "target_equity_usd": 5000.0,
            "ten_slot_maximum_margin_fraction": 1.0,
            "unused_capacity_slots": 8,
        },
        "by_asset": {symbol: _asset_stress(loss) for symbol, loss in losses.items()},
        "portfolio_stress": {
            "configured_asset_roster": {
                "position_count": 2,
                "isolated_margin_at_risk_usd": 1000.0,
                "isolated_margin_at_risk_pct_equity": 20.0,
                "p99_stop_wave_loss_usd": sum(losses.values()),
                "p99_stop_wave_loss_pct_equity": sum(losses.values()) / 50.0,
            }
        },
    }


def _asset_stress(loss: float) -> dict[str, object]:
    return {
        "stop_bps": 80.0,
        "visible_depth_complete_rate": 1.0,
        "visible_cost_sample_count": 240,
        "current_profile_cap_usd": 5000.0,
        "candidate_nonbinding_cap_usd": 5000.0,
        "p99_total_loss_pct_equity": loss / 50.0,
        "p99": {"total_loss_usd": loss},
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
