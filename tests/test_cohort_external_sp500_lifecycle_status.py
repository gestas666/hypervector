"""Projection of the exact SP500 first-lifecycle watcher status."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.research.cohort_external_lifecycle_status import (
    load_external_lifecycle_status,
)


def test_sp500_open_lifecycle_status_is_visible_without_pnl_claim(
    tmp_path: Path,
) -> None:
    """The digest must expose the censored path and exact replay readiness."""
    observed_at = datetime(2026, 8, 19, 7, 40, tzinfo=UTC)
    status_path = tmp_path / "sp500_lifecycle.json"
    status_path.write_text(json.dumps(_status(observed_at)), encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text("{}", encoding="utf-8")

    status, evidence = load_external_lifecycle_status(
        catalog,
        {"lifecycle_status_path": status_path.name},
        "xyz:SP500",
        observed_at,
        120.0,
    )

    assert status is not None
    assert status["watch_state"] == "OPEN_LIFECYCLE_CENSORED"
    assert status["lifecycle_replay_candidate_due"] is False
    assert status["trigger_reasons"] == []
    assert status["side"] == "short"
    assert status["decision_time_ms"] == 1_787_120_100_000
    assert status["entry_time_ms"] == 1_787_120_101_436
    assert status["completed_candles"] == 84
    assert status["profit_lock_activated"] is False
    assert status["pnl_claimed"] is False
    assert status["live_change_supported"] is False
    assert evidence is not None and evidence["sha256"]


def test_sp500_first_lifecycle_accepts_later_eligible_observations(
    tmp_path: Path,
) -> None:
    """The first frozen path remains valid as later decisions accumulate."""
    observed_at = datetime(2026, 8, 19, 7, 40, tzinfo=UTC)
    payload = _status(observed_at)
    payload["source"] = {"observed_decisions": 8, "eligible_decisions": 3}
    status_path = tmp_path / "sp500_lifecycle.json"
    status_path.write_text(json.dumps(payload), encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text("{}", encoding="utf-8")

    status, _evidence = load_external_lifecycle_status(
        catalog,
        {"lifecycle_status_path": status_path.name},
        "xyz:SP500",
        observed_at,
        120.0,
    )

    assert status is not None
    assert status["eligible_decisions"] == 3
    assert status["nominal_censored"] == 1


def _status(observed_at: datetime) -> dict[str, object]:
    summary = {
        "resolved": 0,
        "censored": 1,
        "modeled_net_usd_excluding_funding": 0.0,
    }
    return {
        "schema_version": "sp500_fresh15_lifecycle_watch_status_v1",
        "symbol": "xyz:SP500",
        "observed_at_ms": int(observed_at.timestamp() * 1_000),
        "watch_state": "OPEN_LIFECYCLE_CENSORED",
        "lifecycle_replay_candidate_due": False,
        "trigger_reasons": [],
        "source": {"observed_decisions": 6, "eligible_decisions": 1},
        "lifecycle": {
            "side": "short",
            "decision_time_ms": 1_787_120_100_000,
            "entry_time_ms": 1_787_120_101_436,
            "entry_price": 7675.6,
            "stop_price": 7737.0048,
        },
        "path": {
            "completed_candles": 84,
            "last_bar_close_ms": 1_787_125_140_000,
            "last_close": 7693.8,
            "minimum_low": 7675.4,
            "maximum_high": 7695.8,
            "profit_lock_activated": False,
            "profit_lock_activation_ms": None,
            "profit_lock_triggered": False,
            "source_gap": False,
            "source_stale": False,
        },
        "nominal": {"summary": dict(summary)},
        "stress": {"summary": dict(summary)},
        "technical_assessment": {
            "all_observed_paths_resolved": False,
            "live_change_supported": False,
        },
        "report_only": True,
        "execution_authority": "none",
        "orders_supported": False,
        "signing_client_constructed": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
