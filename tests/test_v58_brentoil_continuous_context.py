"""Canonical V58 consolidation of the exact live BRENTOIL watcher."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module, util
import json
from pathlib import Path

import pytest


_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_FINGERPRINT = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
_RUN = "bidirectional-live-1787166474078"
_ROUTE = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL"


def test_open_watcher_replaces_missing_capture_in_canonical_report(
    tmp_path: Path,
) -> None:
    """An attached exact watcher must become the canonical BRENTOIL evidence."""
    module_name = "hypervector.research.v58_brentoil_continuous_context"
    assert util.find_spec(module_name) is not None, "BRENTOIL context is missing"
    module = import_module(module_name)
    path = tmp_path / "brentoil.json"
    path.write_text(json.dumps(_watcher()), encoding="utf-8")

    context = module.load_v58_brentoil_continuous_context(
        path,
        observed_at=datetime(2026, 8, 20, 10, 7, tzinfo=UTC),
        maximum_age_seconds=180.0,
        profile_id=_PROFILE,
        profile_fingerprint=_FINGERPRINT,
        run_id=_RUN,
    )
    report = _report()
    module.attach_v58_brentoil_continuous_context(report, context)

    assert report["lifecycle_capture_coverage"]["watcher_count"] == 5
    assert report["lifecycle_capture_coverage"]["eligible_without_exact_capture"] == 0
    coverage = report["lifecycle_capture_coverage"]["routes"][0]
    assert coverage["watcher_attached"] is True
    assert coverage["status"] == "exact_lifecycle_watcher_attached"
    ledger = report["hypothesis_ledger"][0]
    assert ledger["watch_state"] == "open_protected"
    assert ledger["pending_lifecycles"] == 1
    assert ledger["resolved_lifecycles"] == 0
    assert ledger["technical_complete"] is True
    assert ledger["evidence_state"] == "open_exact_live_lifecycle"
    assert report["brentoil_live_lifecycle_context"]["state"] == "open_protected"
    assert report["evidence"]["lifecycles"][_ROUTE]["sha256"]


def test_resolved_watcher_remains_valid_after_freshness_window(
    tmp_path: Path,
) -> None:
    """An immutable terminal lifecycle must remain consolidatable."""
    module = import_module("hypervector.research.v58_brentoil_continuous_context")
    path = tmp_path / "brentoil.json"
    watcher = _watcher()
    watcher["state"] = "resolved"
    watcher["summary"] = {"open": 0, "resolved": 1}
    watcher["actual_live_lifecycle"] = {
        "actual_entry_fill_claimed": True,
        "actual_exit_fill_claimed": True,
    }
    path.write_text(json.dumps(watcher), encoding="utf-8")

    context = module.load_v58_brentoil_continuous_context(
        path,
        observed_at=datetime(2026, 8, 21, 10, 7, tzinfo=UTC),
        maximum_age_seconds=180.0,
        profile_id=_PROFILE,
        profile_fingerprint=_FINGERPRINT,
        run_id=_RUN,
    )

    assert context.state == "resolved"
    assert context.pending == 0
    assert context.resolved == 1
    assert context.source_age_seconds > 86_400.0


def test_open_watcher_still_fails_closed_after_freshness_window(
    tmp_path: Path,
) -> None:
    """A stale open lifecycle cannot masquerade as current evidence."""
    module = import_module("hypervector.research.v58_brentoil_continuous_context")
    path = tmp_path / "brentoil.json"
    path.write_text(json.dumps(_watcher()), encoding="utf-8")

    with pytest.raises(ValueError, match="watcher status is stale"):
        module.load_v58_brentoil_continuous_context(
            path,
            observed_at=datetime(2026, 8, 21, 10, 7, tzinfo=UTC),
            maximum_age_seconds=180.0,
            profile_id=_PROFILE,
            profile_fingerprint=_FINGERPRINT,
            run_id=_RUN,
        )


def _watcher() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "v58_brentoil_live_lifecycle_reconciliation_v1",
        "generated_at_utc": "2026-08-20T10:06:30+00:00",
        "state": "open_protected",
        "identity": {
            "profile_id": _PROFILE,
            "profile_fingerprint": _FINGERPRINT,
            "run_id": _RUN,
            "route": _ROUTE,
            "symbol": "xyz:BRENTOIL",
            "side": "long",
            "lifecycle_id": "xyz:BRENTOIL:520642502465",
        },
        "summary": {"open": 1, "resolved": 0},
        "actual_live_lifecycle": {
            "actual_entry_fill_claimed": True,
            "actual_exit_fill_claimed": False,
        },
        "strategy_change_supported": False,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
            "portfolio_pnl_claimed": False,
            "actual_orders_or_fills_claimed": True,
        },
    }


def _report() -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
        },
        "lifecycle_capture_coverage": {
            "watcher_count": 4,
            "eligible_without_exact_capture": 1,
            "routes": [
                {
                    "route": _ROUTE,
                    "eligible_evaluations": 1,
                    "watcher_attached": False,
                    "status": "eligible_without_exact_lifecycle_capture",
                }
            ],
        },
        "hypothesis_ledger": [
            {
                "route": _ROUTE,
                "symbol": "xyz:BRENTOIL",
                "status": "being_tested",
                "evidence_state": "awaiting_first_eligible_signal",
                "watch_state": "watcher_not_attached",
                "pending_lifecycles": 0,
                "resolved_lifecycles": 0,
                "technical_complete": None,
                "source_age_seconds": None,
                "automatic_live_change": False,
            }
        ],
        "evidence": {"lifecycles": {}},
    }
