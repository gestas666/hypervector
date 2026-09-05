"""External candidate integration for the report-only improvement monitor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import ModuleType

import pytest

from cohort_improvement_monitor_external_support import (
    contract as _contract,
    evidence as _evidence,
    load_monitor as _load,
)


def test_monitor_loads_brentoil_and_mu_without_execution_authority(
    tmp_path: Path,
) -> None:
    """Fresh candidate observers must expose liquidity and Brent canary history."""
    module = _load()
    observed_at = datetime(2026, 8, 16, 1, 0, tzinfo=UTC)
    catalog = _write_catalog(tmp_path, observed_at)
    args = _args(module, catalog)

    pipeline = module._load_external_assets(args, observed_at)

    assert pipeline.status["execution_authority"] == "none"
    candidates = {row["symbol"]: row for row in pipeline.status["candidates"]}
    brent = candidates["xyz:BRENTOIL"]
    assert brent["liquidity_rank"] == 1
    assert brent["historical_live"]["closed_lifecycles"] == 3
    assert brent["historical_live"]["net_pnl_usd"] == pytest.approx(1.821755)
    assert brent["observer"]["latest_threshold_fraction"] == pytest.approx(0.42)
    assert brent["observer"]["maximum_threshold_fraction_total"] == pytest.approx(0.87)
    mu = candidates["xyz:MU"]
    assert mu["liquidity_rank"] == 2
    assert mu["historical_live"] is None
    assert mu["observer"]["decision_rows_total"] == 348
    assert mu["observer"]["eligible_decisions_total"] == 9
    assert mu["observer"]["long_decisions_total"] == 9
    assert mu["observer"]["short_decisions_total"] == 0
    assert mu["observer"]["non_action_decisions_total"] == 339
    assert mu["technical_validation"] == _expected_mu_validation()
    assert mu["prospective_lifecycle"]["watch_state"] == "WAITING_ELIGIBLE_ONSET"
    assert mu["prospective_lifecycle"]["eligible_decisions"] == 0
    assert mu["prospective_lifecycle"]["eligible_decisions_by_side"] == {
        "long": 0,
        "short": 0,
    }
    assert mu["prospective_lifecycle"]["collection_state"] == (
        "collecting_minimum_onsets"
    )
    assert mu["prospective_lifecycle"]["lifecycle_replay_candidate_due"] is False
    assert mu["prospective_lifecycle"]["live_change_supported"] is False
    assert pipeline.evidence["catalog"]["sha256"]
    assert pipeline.evidence["candidates"]["xyz:BRENTOIL"]["observer"]["sha256"]
    assert pipeline.evidence["candidates"]["xyz:MU"]["technical_validation"]["sha256"]


def test_monitor_labels_stale_external_observer_without_blocking_digest(
    tmp_path: Path,
) -> None:
    """A stale external lane must be explicit without hiding current core data."""
    module = _load()
    observed_at = datetime(2026, 8, 16, 1, 0, tzinfo=UTC)
    catalog = _write_catalog(tmp_path, observed_at - timedelta(minutes=3))

    pipeline = module._load_external_assets(_args(module, catalog), observed_at)

    candidates = {row["symbol"]: row for row in pipeline.status["candidates"]}
    for candidate in candidates.values():
        observer = candidate["observer"]
        assert observer["freshness_status"] == "stale"
        assert observer["age_seconds"] == pytest.approx(180.0)
        assert "observer_stale" in observer["promotion_blockers"]
        assert candidate["live_authorized"] is False
        assert candidate["strategy_edge_established"] is False


def test_monitor_rejects_external_observer_with_order_authority(
    tmp_path: Path,
) -> None:
    """External research rows must remain incapable of signing or ordering."""
    module = _load()
    observed_at = datetime(2026, 8, 16, 1, 0, tzinfo=UTC)
    catalog = _write_catalog(tmp_path, observed_at)
    status = tmp_path / "brentoil_status.json"
    payload = json.loads(status.read_text())
    payload["orders_supported"] = True
    status.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="invalid orders_supported"):
        module._load_external_assets(_args(module, catalog), observed_at)


def test_monitor_rejects_changed_external_evidence(tmp_path: Path) -> None:
    """Candidate summaries must remain bound to their immutable evidence bytes."""
    module = _load()
    observed_at = datetime(2026, 8, 16, 1, 0, tzinfo=UTC)
    catalog = _write_catalog(tmp_path, observed_at)
    canary = tmp_path / "brentoil_canary.json"
    canary.write_text(canary.read_text() + "\n")

    with pytest.raises(ValueError, match="external candidate evidence mismatch"):
        module._load_external_assets(_args(module, catalog), observed_at)


def test_monitor_surfaces_fresh_brentoil_lifecycle_status(tmp_path: Path) -> None:
    """The candidate lane must expose exact lifecycle resolution progress."""
    module = _load()
    observed_at = datetime(2026, 8, 18, 6, 30, tzinfo=UTC)
    catalog = _write_catalog(tmp_path, observed_at)
    lifecycle = tmp_path / "brentoil_lifecycle.json"
    lifecycle.write_text(json.dumps(_lifecycle_status(observed_at)))
    payload = json.loads(catalog.read_text())
    payload["candidates"][0]["lifecycle_status_path"] = lifecycle.name
    catalog.write_text(json.dumps(payload))

    pipeline = module._load_external_assets(_args(module, catalog), observed_at)

    brent = pipeline.status["candidates"][0]
    assert brent["prospective_lifecycle"] == {
        "watch_state": "WAITING_ELIGIBLE_ONSET",
        "freshness_status": "fresh",
        "age_seconds": 0.0,
        "observed_at_utc": "2026-08-18T06:30:00+00:00",
        "observed_decisions": 3,
        "eligible_decisions": 0,
        "nominal_resolved": 0,
        "nominal_censored": 0,
        "nominal_net_usd_excluding_funding": 0.0,
        "stress_resolved": 0,
        "stress_censored": 0,
        "stress_net_usd_excluding_funding": 0.0,
        "all_observed_paths_resolved": False,
        "live_change_supported": False,
    }
    evidence = pipeline.evidence["candidates"]["xyz:BRENTOIL"]
    assert evidence["prospective_lifecycle"]["sha256"]


def test_monitor_defaults_name_the_external_candidate_catalog() -> None:
    """The active monitor must carry the 4+4 candidate lane by default."""
    args = _load().build_parser().parse_args([])

    assert args.external_asset_catalog == Path(
        "configs/research/v51_external_asset_pipeline.json"
    )
    assert args.maximum_external_observer_age_seconds == 120.0


def test_default_catalog_uses_clean_brentoil_recovery_epoch() -> None:
    """The default pipeline must not read the source-revised observer epoch."""
    catalog = json.loads(
        Path("configs/research/v51_external_asset_pipeline.json").read_text()
    )
    brent = next(
        row for row in catalog["candidates"] if row["symbol"] == "xyz:BRENTOIL"
    )

    assert brent["stage"] == "prospective_shadow_source_revision_recovery_v2"
    assert brent["observer_path"].endswith("brentoil_oil_shock_shadow_v2_latest.json")
    assert brent["lifecycle_status_path"].endswith(
        "brentoil_oil_shock_lifecycle_v2_latest.json"
    )
    assert "technical_validation_status" not in brent


def test_default_catalog_uses_terminal_mu_source_native_result() -> None:
    """The active digest must retain the latest rejected MU result."""
    catalog = json.loads(
        Path("configs/research/v51_external_asset_pipeline.json").read_text()
    )
    mu = next(row for row in catalog["candidates"] if row["symbol"] == "xyz:MU")

    assert mu["stage"] == "source_native_lifecycle_rejected_v1"
    validation = mu["technical_validation_status"]
    assert validation["path"].endswith("mu_transport_parity_finalizer_v2_latest.json")
    assert validation["hypothesis_id"] == (
        "MU_BREAKOUT_PRESSURE_TRANSPORT_PARITY_FORWARD_V2"
    )
    immutable_paths = {row["path"] for row in mu["immutable_evidence"]}
    assert mu["lifecycle_status_path"].endswith(
        "mu_source_native_independent_window_latest.json"
    )
    assert any(
        path.endswith("v57-mu-transport-parity-forward-v2-result-20260818-v1.json")
        for path in immutable_paths
    )
    assert any(
        path.endswith("v57-mu-source-native-lifecycle-result-20260818-v1.json")
        for path in immutable_paths
    )


def test_default_catalog_projects_the_sp500_first_lifecycle_watcher() -> None:
    """The active digest must expose mutable exit readiness beside static evidence."""
    catalog = json.loads(
        Path("configs/research/v51_external_asset_pipeline.json").read_text()
    )
    sp500 = next(row for row in catalog["candidates"] if row["symbol"] == "xyz:SP500")

    assert sp500["lifecycle_status_path"].endswith(
        "v58_sp500_fresh15_first_lifecycle_latest.json"
    )
    assert sp500["partial_lifecycle_source"]["sha256"] == (
        "2bccf95ea9ea499b461f88d20d754987280c90d79cd9af3c9cc67eb34d463339"
    )


def test_monitor_keeps_external_candidates_visible_after_v52_cutover(
    tmp_path: Path,
) -> None:
    """The report-only external lane must survive the live-profile transition."""
    module = _load()
    observed_at = datetime(2026, 8, 16, 1, 0, tzinfo=UTC)
    catalog = _write_catalog(tmp_path, observed_at)
    audit = {
        "run": {
            "profile_id": "multi_asset_growth_first_5000_evidence_bound_successor_v52"
        }
    }

    pipeline = module._external_assets_for_profile(
        _args(module, catalog), audit, observed_at
    )

    assert pipeline is not None
    assert pipeline.status["execution_authority"] == "none"
    assert {row["symbol"] for row in pipeline.status["candidates"]} == {
        "xyz:BRENTOIL",
        "xyz:MU",
    }


def test_monitor_keeps_external_candidates_visible_during_v53(
    tmp_path: Path,
) -> None:
    """The external research lane must continue under the active v53 profile."""
    module = _load()
    observed_at = datetime(2026, 8, 18, 6, 0, tzinfo=UTC)
    catalog = _write_catalog(tmp_path, observed_at)
    audit = {
        "run": {"profile_id": "multi_asset_growth_first_5000_hype_freshness_repair_v53"}
    }

    pipeline = module._external_assets_for_profile(
        _args(module, catalog), audit, observed_at
    )

    assert pipeline is not None
    assert {row["symbol"] for row in pipeline.status["candidates"]} == {
        "xyz:BRENTOIL",
        "xyz:MU",
    }


def test_monitor_keeps_external_candidates_visible_during_v57(
    tmp_path: Path,
) -> None:
    """The external research lane must continue under the active v57 profile."""
    module = _load()
    observed_at = datetime(2026, 8, 18, 18, 0, tzinfo=UTC)
    catalog = _write_catalog(tmp_path, observed_at)
    audit = {
        "run": {
            "profile_id": ("multi_asset_growth_first_5000_spcx_short_containment_v57")
        }
    }

    pipeline = module._external_assets_for_profile(
        _args(module, catalog), audit, observed_at
    )

    assert pipeline is not None
    assert {row["symbol"] for row in pipeline.status["candidates"]} == {
        "xyz:BRENTOIL",
        "xyz:MU",
    }


def _args(module: ModuleType, catalog: Path) -> object:
    return module.build_parser().parse_args(
        [
            "--external-asset-catalog",
            str(catalog),
            "--maximum-external-observer-age-seconds",
            "120",
        ]
    )


def _write_catalog(tmp_path: Path, status_time: datetime) -> Path:
    liquidity = tmp_path / "liquidity.json"
    liquidity.write_text(json.dumps(_liquidity()))
    brent_status = tmp_path / "brentoil_status.json"
    brent_status.write_text(json.dumps(_status("xyz:BRENTOIL", status_time)))
    mu_status = tmp_path / "mu_status.json"
    mu_status.write_text(json.dumps(_status("xyz:MU", status_time)))
    mu_validation = tmp_path / "mu_transport_status.json"
    mu_validation.write_text(json.dumps(_mu_transport_status()))
    mu_lifecycle = tmp_path / "mu_lifecycle.json"
    mu_lifecycle.write_text(json.dumps(_lifecycle_status(status_time, "xyz:MU")))
    canary = tmp_path / "brentoil_canary.json"
    canary.write_text(json.dumps(_brentoil_canary()))
    mu_research = tmp_path / "mu_research.json"
    mu_research.write_text('{"execution_authority":"none"}')
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contract": _contract(),
                "liquidity_source": _evidence(liquidity),
                "candidates": [
                    {
                        "symbol": "xyz:BRENTOIL",
                        "stage": "prospective_shadow",
                        "observer_path": brent_status.name,
                        "historical_live_source": _evidence(canary),
                        "immutable_evidence": [],
                    },
                    {
                        "symbol": "xyz:MU",
                        "stage": "prospective_shadow",
                        "observer_path": mu_status.name,
                        "technical_validation_status": {
                            "path": mu_validation.name,
                            "mode": "mu_transport_parity_fixed_window_finalizer",
                            "hypothesis_id": (
                                "MU_BREAKOUT_PRESSURE_TRANSPORT_PARITY_FORWARD_V1"
                            ),
                        },
                        "historical_live_source": None,
                        "lifecycle_status_path": mu_lifecycle.name,
                        "immutable_evidence": [_evidence(mu_research)],
                    },
                ],
            }
        )
    )
    return catalog


def _status(symbol: str, observed_at: datetime) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "orders_supported": False,
        "signing_client_constructed": False,
        "symbol": symbol,
        "observed_at_ms": int(observed_at.timestamp() * 1000),
        "mode": "candidate_shadow_observer",
        "profile_id": f"profile-{symbol}",
        "provider_id": f"provider-{symbol}",
        "promotion_blockers": ["forward_edge_unproven"],
        "decisions_published": 0,
        "decision_rows_total": 348,
        "eligible_decisions_total": 9,
        "long_decisions_total": 9,
        "short_decisions_total": 0,
        "non_action_decisions_total": 339,
        "latest_trailing_return_bps": 42.0,
        "latest_shock_threshold_bps": 100.0,
        "latest_threshold_fraction": 0.42,
        "maximum_threshold_fraction_total": 0.87,
    }


def _liquidity() -> dict[str, object]:
    markets = []
    for symbol, volume, spread in (
        ("xyz:BRENTOIL", 49_000_000.0, 0.12),
        ("xyz:MU", 31_000_000.0, 0.10),
    ):
        markets.append(
            {
                "symbol": symbol,
                "market": {"day_notional_volume_usd": volume},
                "book": {"spread_bps": spread},
                "max_leverage": 10,
            }
        )
    return {
        "mode": "hip3_market_qualification_v1",
        "status": "qualified_for_observation_only",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "markets": markets,
    }


def _brentoil_canary() -> dict[str, object]:
    return {
        "mode": "report_only",
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "symbol": "xyz:BRENTOIL",
        "ledger_coverage": {
            "rows": 54848,
            "book_observations": 13662,
            "raw_fill_events": 7,
            "reconciled_closed_lifecycles": 3,
        },
        "descriptive_all_live_lifecycles": {
            "wins": 2,
            "losses": 1,
            "net_pnl_usd": 1.821755,
            "profit_factor": 3.648046,
            "net_pnl_excluding_largest_winner_usd": -0.232469,
        },
    }


def _mu_transport_status() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "mu_transport_parity_fixed_window_finalizer",
        "state": "collecting",
        "hypothesis_id": "MU_BREAKOUT_PRESSURE_TRANSPORT_PARITY_FORWARD_V1",
        "symbol": "xyz:MU",
        "window_start_ms": 1_786_906_800_000,
        "window_end_exclusive_ms": 1_786_993_200_000,
        "expected_decisions": 96,
        "observed_decisions": 27,
        "resolved_decisions": 27,
        "eligible_decisions": 1,
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
    }


def _expected_mu_validation() -> dict[str, object]:
    return {
        "mode": "mu_transport_parity_fixed_window_finalizer",
        "hypothesis_id": "MU_BREAKOUT_PRESSURE_TRANSPORT_PARITY_FORWARD_V1",
        "state": "collecting",
        "window_start_ms": 1_786_906_800_000,
        "window_end_exclusive_ms": 1_786_993_200_000,
        "expected_decisions": 96,
        "observed_decisions": 27,
        "resolved_decisions": 27,
        "eligible_decisions": 1,
        "coverage_fraction": pytest.approx(27 / 96),
        "complete": False,
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }


def _lifecycle_status(
    observed_at: datetime, symbol: str = "xyz:BRENTOIL"
) -> dict[str, object]:
    summary = {
        "resolved": 0,
        "censored": 0,
        "modeled_net_usd_excluding_funding": 0.0,
    }
    status = {
        "symbol": symbol,
        "observed_at_ms": int(observed_at.timestamp() * 1000),
        "watch_state": "WAITING_ELIGIBLE_ONSET",
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "source": {"observed_decisions": 3, "eligible_decisions": 0},
        "nominal": {"summary": dict(summary)},
        "stress": {"summary": dict(summary)},
        "technical_assessment": {
            "all_observed_paths_resolved": False,
            "live_change_supported": False,
        },
    }
    if symbol == "xyz:MU":
        status.update(
            {
                "schema_version": "mu_source_native_independent_window_status_v1",
                "collection_state": "collecting_minimum_onsets",
                "eligible_onsets_by_side": {"long": 0, "short": 0},
                "lifecycle_replay_candidate_due": False,
                "collection_deadline_reached": False,
            }
        )
    return status
