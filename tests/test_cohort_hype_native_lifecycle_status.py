"""Tests for exact HYPE-native lifecycle status projection."""

from datetime import UTC, datetime
from importlib import import_module
from importlib.util import find_spec
import json
from pathlib import Path


def test_hype_native_status_loader_module_exists() -> None:
    """The improvement tracker needs a dedicated HYPE-native adapter."""
    assert (
        find_spec("hypervector.research.cohort_hype_native_lifecycle_status")
        is not None
    )


def test_loader_projects_fresh_open_lifecycle_and_peak_giveback(
    tmp_path: Path,
) -> None:
    """The tracker must expose exact current economics without claiming a close."""
    module = import_module("hypervector.research.cohort_hype_native_lifecycle_status")
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(_open_status()), encoding="utf-8")

    status, evidence = module.load_hype_native_lifecycle_status(
        path,
        observed_at=datetime.fromtimestamp(120.0, tz=UTC),
        maximum_age_seconds=90.0,
    )

    assert status["freshness_status"] == "fresh"
    assert status["eligible_long_entries"] == 2
    assert status["occupied_entries"] == 1
    assert status["open_lifecycles"] == 1
    assert status["resolved_lifecycles"] == 0
    current = status["current_open_lifecycle"]
    assert current["current_modeled_net_usd_excluding_funding"] == 5.0
    assert current["peak_giveback_bps"] == 35.0
    assert current["technical_path_resolved"] is True
    assert status["native_only_opportunities"] == 2
    comparison = status["baseline_comparisons"][0]
    assert comparison["baseline_reason"] == "authoritative_5m_compression_absent"
    assert comparison["common_feature_parity"] is True
    assert status["live_change_supported"] is False
    assert evidence["sha256"]


def test_loader_uses_the_requested_freshness_limit(tmp_path: Path) -> None:
    """A caller's evidence-age contract cannot be replaced by a hidden constant."""
    module = import_module("hypervector.research.cohort_hype_native_lifecycle_status")
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(_open_status()), encoding="utf-8")

    status, _ = module.load_hype_native_lifecycle_status(
        path,
        observed_at=datetime.fromtimestamp(120.0, tz=UTC),
        maximum_age_seconds=10.0,
    )

    assert status["freshness_status"] == "stale"


def test_closed_unresolved_lifecycle_is_not_counted_as_resolved(
    tmp_path: Path,
) -> None:
    """An exit without complete technical evidence cannot become a resolved trade."""
    module = import_module("hypervector.research.cohort_hype_native_lifecycle_status")
    payload = _open_status()
    lifecycle = _open_lifecycle()
    lifecycle.update(
        {
            "status": "technical_evidence_unresolved",
            "technical_path_resolved": False,
            "exit_reason": "protective_stop",
        }
    )
    payload.update(
        {
            "status": "technical_evidence_unresolved",
            "watch_state": "technical_evidence_unresolved",
            "lifecycles": [lifecycle],
        }
    )
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    status, _ = module.load_hype_native_lifecycle_status(
        path,
        observed_at=datetime.fromtimestamp(120.0, tz=UTC),
        maximum_age_seconds=90.0,
    )

    assert status["resolved_lifecycles"] == 0
    assert status["technically_unresolved_lifecycles"] == 1


def test_profile_loader_attaches_only_when_exact_baseline_route_executes(
    tmp_path: Path,
) -> None:
    """Profiles without the comparison route cannot inherit challenger evidence."""
    module = import_module("hypervector.research.cohort_hype_native_lifecycle_status")
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(_open_status()), encoding="utf-8")
    observed = datetime.fromtimestamp(120.0, tz=UTC)

    selected = module.load_hype_native_for_profile(
        path,
        {
            "run": {
                "profile_id": "multi_asset_growth_first_5000_hype_freshness_repair_v53",
                "executable_provider_symbols": [
                    "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
                ],
            }
        },
        observed_at=observed,
        maximum_age_seconds=90.0,
    )
    excluded = module.load_hype_native_for_profile(
        tmp_path / "missing.json",
        {
            "run": {
                "profile_id": "another-profile",
                "executable_provider_symbols": ["another-strategy|HYPE"],
            }
        },
        observed_at=observed,
        maximum_age_seconds=90.0,
    )

    assert selected is not None
    assert selected.status["strategy_id"] == "hype_native_breakout_onset_long_v3"
    assert selected.evidence["sha256"]
    assert excluded is None


def test_profile_loader_attaches_to_v57_with_exact_baseline_route(
    tmp_path: Path,
) -> None:
    """A successor profile must retain evidence for its unchanged HYPE route."""
    module = import_module("hypervector.research.cohort_hype_native_lifecycle_status")
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(_open_status()), encoding="utf-8")

    selected = module.load_hype_native_for_profile(
        path,
        {
            "run": {
                "profile_id": "multi_asset_growth_first_5000_spcx_short_containment_v57",
                "executable_provider_symbols": [
                    "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
                ],
            }
        },
        observed_at=datetime.fromtimestamp(120.0, tz=UTC),
        maximum_age_seconds=90.0,
    )

    assert selected is not None
    assert selected.status["strategy_id"] == "hype_native_breakout_onset_long_v3"


def _open_status() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_prospective_lifecycle_report_only",
        "status": "tracking_open_lifecycle",
        "watch_state": "tracking_open_lifecycle",
        "observed_at_ms": 100_000,
        "contract": {
            "execution_authority": "none",
            "report_only": True,
            "orders_or_fills_assumed": False,
            "realized_pnl_claimed": False,
            "funding_included": False,
            "mark_stop_truth_included": False,
        },
        "identity": {
            "profile_id": "multi_asset_growth_first_5000_hype_native_long_challenger_v54",
            "profile_fingerprint": "1c0beafb19ef1b8c5594d3bf1aa6a23eeff12f28f540d958953cc25e8bff1643",
            "run_id": "run-v54",
            "run_fingerprint": "b" * 64,
            "strategy_id": "hype_native_breakout_onset_long_v3",
            "symbol": "HYPE",
        },
        "signal_counts": {
            "eligible_long_entries": 2,
            "exit_only_short_onsets": 0,
        },
        "attempts": [
            {"status": "open_pending_exit"},
            {"status": "occupied_by_prior_lifecycle"},
        ],
        "lifecycles": [_open_lifecycle()],
        "baseline_comparisons": [
            _baseline_comparison(60_000),
            _baseline_comparison(120_000),
        ],
        "resolved_proxy_summary": {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "net_pnl_usd_before_funding": None,
            "net_pnl_usd_before_funding_excluding_largest_winner": None,
            "profit_factor_before_funding": None,
        },
    }


def _baseline_comparison(decision_time_ms: int) -> dict[str, object]:
    return {
        "symbol": "HYPE",
        "decision_time_ms": decision_time_ms,
        "reference_price": 59.0,
        "native_strategy_id": "hype_native_breakout_onset_long_v3",
        "native_eligible": True,
        "baseline_strategy_id": (
            "hype_breakout_compression_alignment_bidirectional_v2"
        ),
        "baseline_eligible": False,
        "baseline_reason": "authoritative_5m_compression_absent",
        "baseline_blockers": [
            "authoritative_5m_compression_absent",
            "prior_compression_absent",
            "directional_pullback_absent",
        ],
        "baseline_conditions_met": 2,
        "baseline_conditions_required": 5,
        "common_feature_parity": True,
        "opportunity_class": ("native_breakout_admitted_compression_pullback_rejected"),
    }


def _open_lifecycle() -> dict[str, object]:
    return {
        "decision_time_ms": 60_000,
        "side": "long",
        "status": "open_pending_exit",
        "entry_price": 59.0,
        "stop_price": 58.5,
        "current_book_time_ms": 95_000,
        "occupancy_end_time_ms": 28_860_000,
        "technical_path_resolved": True,
        "maximum_book_gap_ms": 15_000,
        "maximum_favorable_excursion_bps": 95.0,
        "maximum_adverse_excursion_bps": 2.0,
        "current_outcome": {
            "exit_price": 59.4,
            "gross_return_bps": 60.0,
            "net_pnl_usd": 5.0,
        },
        "exit_book_time_ms": None,
        "exit_reason": None,
    }
