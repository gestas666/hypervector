"""External candidate evidence in the continuous-improvement pipeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from hypervector.research.cohort_external_opportunity_pipeline import (
    ExternalOpportunityPaths,
    load_brentoil_external_opportunity,
)


def test_brentoil_failed_development_is_visible_but_not_top_ranked(
    tmp_path: Path,
) -> None:
    paths = _write_sources(tmp_path)
    pipeline, evidence = load_brentoil_external_opportunity(
        paths,
        observed_at=_observed_at(),
        maximum_observer_age_seconds=360.0,
    )

    candidate = pipeline["candidates"][0]
    assert pipeline["highest_value_external_investigation"] is None
    assert candidate["symbol"] == "xyz:BRENTOIL"
    assert candidate["live_canary"] == {
        "closed_lifecycles": 3,
        "wins": 2,
        "losses": 1,
        "net_pnl_usd": 1.821755,
        "profit_factor": 3.648046,
        "net_excluding_largest_winner_usd": -0.232469,
        "maximum_observed_slippage_bps": 8.464584,
    }
    assert candidate["liquidity"]["global_rank"] == 6
    assert candidate["development"]["nominal_profit_factor"] == 2.258518
    assert candidate["development"]["stress_profit_factor"] == 0.837156
    assert candidate["prospective_observation"]["eligible_decisions"] == 0
    assert candidate["status"] == "deferred_negative_development_stress"
    assert candidate["validation_priority"] is None
    assert candidate["next_experiment"] == "passive_collection_or_new_mechanism"
    assert candidate["live_change_supported"] is False
    assert candidate["existing_strategy_edge_established"] is False
    assert pipeline["contract"]["execution_authority"] == "none"
    assert evidence["observer"]["bytes"] > 0


def test_brentoil_pipeline_rejects_stale_observer(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path)

    with pytest.raises(ValueError, match="observer is stale"):
        load_brentoil_external_opportunity(
            paths,
            observed_at=_observed_at() + timedelta(minutes=10),
            maximum_observer_age_seconds=360.0,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("execution_authority", "live", "observer contract is invalid"),
        ("orders_supported", True, "observer contract is invalid"),
        ("signing_client_constructed", True, "observer contract is invalid"),
        ("symbol", "xyz:SP500", "observer identity is invalid"),
    ],
)
def test_brentoil_pipeline_rejects_unsafe_or_wrong_observer(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    paths = _write_sources(tmp_path)
    observer = _read(paths.observer)
    observer[field] = value
    paths.observer.write_text(json.dumps(observer), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_brentoil_external_opportunity(
            paths,
            observed_at=_observed_at(),
            maximum_observer_age_seconds=360.0,
        )


def test_brentoil_pipeline_rejects_development_oos_access(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path)
    development = _read(paths.development)
    development["validation_accessed"] = True
    paths.development.write_text(json.dumps(development), encoding="utf-8")

    with pytest.raises(ValueError, match="development scope is invalid"):
        load_brentoil_external_opportunity(
            paths,
            observed_at=_observed_at(),
            maximum_observer_age_seconds=360.0,
        )


def test_brentoil_unresolved_paths_are_not_ranked_despite_positive_stress(
    tmp_path: Path,
) -> None:
    paths = _write_sources(tmp_path)
    development = _read(paths.development)
    development["development_economics"]["stress"] = _economics(42, 1.0, 1.2)
    paths.development.write_text(json.dumps(development), encoding="utf-8")

    pipeline, _ = load_brentoil_external_opportunity(
        paths,
        observed_at=_observed_at(),
        maximum_observer_age_seconds=360.0,
    )

    candidate = pipeline["candidates"][0]
    assert candidate["status"] == "deferred_technical_paths_unresolved"
    assert candidate["validation_priority"] is None
    assert pipeline["highest_value_external_investigation"] is None


def test_brentoil_pipeline_surfaces_prospective_observer_gaps(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path)
    observer = _read(paths.observer)
    observer["late_non_warmup_candle_rows_total"] = 3
    observer["source_revision_rows_total"] = 1
    observer["source_revision_fields_total"] = ["volume"]
    paths.observer.write_text(json.dumps(observer), encoding="utf-8")

    pipeline, _ = load_brentoil_external_opportunity(
        paths,
        observed_at=_observed_at(),
        maximum_observer_age_seconds=360.0,
    )

    observed = pipeline["candidates"][0]["prospective_observation"]
    assert observed["late_non_warmup_candle_rows"] == 3
    assert observed["source_revision_rows"] == 1
    assert observed["source_revision_fields"] == ["volume"]
    assert observed["technical_path_status"] == "unresolved_late_candles"


def _write_sources(root: Path) -> ExternalOpportunityPaths:
    paths = ExternalOpportunityPaths(
        canary=root / "canary.json",
        development=root / "development.json",
        parity=root / "parity.json",
        observer=root / "observer.json",
    )
    _write(paths.canary, _canary())
    _write(paths.development, _development())
    _write(paths.parity, _parity())
    _write(paths.observer, _observer())
    return paths


def _canary() -> dict[str, object]:
    return {
        "schema_version": "brentoil_live_canary_lifecycle_reconciliation_v1",
        "mode": "report_only",
        "symbol": "xyz:BRENTOIL",
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "ledger_coverage": {"reconciled_closed_lifecycles": 3},
        "descriptive_all_live_lifecycles": {
            "wins": 2,
            "losses": 1,
            "net_pnl_usd": 1.821755,
            "profit_factor": 3.648046,
            "net_pnl_excluding_largest_winner_usd": -0.232469,
        },
        "strategy_attribution": {
            "swing_ha": {"disposition": "retired_identity"},
            "breakout_pressure": {"disposition": "old_route_not_promotable"},
        },
        "current_liquidity_snapshot": {
            "global_hip3_volume_rank": 6,
            "day_notional_volume_usd": 49_403_551.84,
            "spread_bps": 0.116337,
        },
        "conclusion": {
            "asset_data_available": True,
            "asset_liquidity_rejected": False,
            "existing_strategy_edge_established": False,
            "live_addition_authorized": False,
        },
    }


def _development() -> dict[str, object]:
    return {
        "schema_version": "hip3_oil_shock_reversion_development_v1",
        "symbol": "xyz:BRENTOIL",
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "live_roster_change": False,
        "validation_accessed": False,
        "holdout_accessed": False,
        "strategy_identity": {
            "provider_id": "hip3_brentoil_oil_shock_reversion_bidirectional_5m_research_v1",
            "profile_id": "brentoil_oil_shock_reversion_5m_development_v1",
            "timeframe": "5m",
        },
        "development_economics": {
            "nominal": _economics(44, 4.238715, 2.258518),
            "stress": _economics(42, -1.068481, 0.837156),
        },
        "technical_path_evidence": {"status": "unresolved"},
        "research_disposition": {
            "status": "NOT_SUITABLE_TECHNICALLY_UNRESOLVED",
            "live_change_proposed": False,
        },
    }


def _economics(trades: int, net: float, profit_factor: float) -> dict[str, object]:
    return {
        "completed_trades": trades,
        "net_pnl_usd": net,
        "profit_factor": profit_factor,
        "diagnostics": {"all": {"net_without_largest_winner_usd": net - 0.28}},
    }


def _parity() -> dict[str, object]:
    return {
        "schema_version": "hip3_prospective_candle_parity_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "promotion_authority": "none",
            "runtime_strategy_changed": False,
        },
        "scope": {"symbol": "xyz:BRENTOIL"},
        "coverage": {"overlap_bars": 4, "mismatched_ohlc_bars": 1},
        "technical_assessment": {"candle_ohlc_parity_resolved": False},
    }


def _observer() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "brentoil_oil_shock_shadow_observer",
        "symbol": "xyz:BRENTOIL",
        "profile_id": "brentoil_oil_shock_reversion_5m_shadow_v1",
        "provider_id": "hip3_brentoil_oil_shock_reversion_bidirectional_5m_shadow_v1",
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "orders_supported": False,
        "signing_client_constructed": False,
        "observed_at_ms": int(_observed_at().timestamp() * 1000),
        "candle_rows_total": 2318,
        "decision_rows_total": 20,
        "eligible_decisions_total": 0,
        "last_non_action_reason": "no_shock_onset",
        "live_canary_execution_observations": 6,
        "live_canary_max_abs_slippage_bps": 8.464584,
        "promotion_blockers": ["validation_and_holdout_unopened"],
    }


def _observed_at() -> datetime:
    return datetime(2026, 8, 15, 20, 0, tzinfo=UTC)


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
