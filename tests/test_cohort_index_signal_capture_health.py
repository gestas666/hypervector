"""Tests for report-only index signal-capture continuity health."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

MODULE = "hypervector.research.cohort_index_signal_capture_health"
CADENCE_MS = 900_000
PROVIDER = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
PROFILES = {
    "xyz:SP500": "sp500_fresh15_pressure_shadow_research_v3",
    "xyz:SPCX": "spcx_fresh15_pressure_shadow_research_v3",
}


def test_contiguous_current_run_capture_is_healthy(tmp_path: Path) -> None:
    """Every completed boundary through the common cursor must reconcile."""
    module = _module()
    observed = datetime(2026, 8, 15, 0, 46, tzinfo=UTC)
    statuses, journals = _sources(tmp_path, observed, (1, 2, 3))

    result = module.load_index_signal_capture_health(
        status_paths=statuses,
        journal_paths=journals,
        run_started_at=datetime(2026, 8, 15, 0, 7, tzinfo=UTC),
        observed_at=observed,
        maximum_age_seconds=90.0,
    )

    assert result.status["status"] == "healthy"
    assert result.status["expected_decisions_total"] == 6
    assert result.status["observed_decisions_total"] == 6
    assert result.status["missing_boundaries_total"] == 0
    assert result.status["missing_ranges"] == []
    assert set(result.evidence["statuses"]) == set(PROFILES)
    assert set(result.evidence["journals"]) == set(PROFILES)


def test_internal_joint_gap_is_reported_after_status_recovers(tmp_path: Path) -> None:
    """Fresh current status must not erase a historical internal outage."""
    module = _module()
    observed = datetime(2026, 8, 15, 0, 46, tzinfo=UTC)
    statuses, journals = _sources(tmp_path, observed, (1, 3))

    result = module.load_index_signal_capture_health(
        status_paths=statuses,
        journal_paths=journals,
        run_started_at=datetime(2026, 8, 15, 0, 7, tzinfo=UTC),
        observed_at=observed,
        maximum_age_seconds=90.0,
    )

    assert result.status["status"] == "degraded_internal_gaps"
    assert result.status["expected_decisions_total"] == 6
    assert result.status["observed_decisions_total"] == 4
    assert result.status["missing_boundaries_total"] == 2
    assert [row["symbol"] for row in result.status["missing_ranges"]] == [
        "xyz:SP500",
        "xyz:SPCX",
    ]
    assert all(row["count"] == 1 for row in result.status["missing_ranges"])


def test_stale_observer_status_is_unavailable(tmp_path: Path) -> None:
    """A complete old journal cannot make a stopped observer look current."""
    module = _module()
    observed = datetime(2026, 8, 15, 0, 50, tzinfo=UTC)
    statuses, journals = _sources(tmp_path, observed, (1, 2, 3))
    payload = json.loads(statuses["xyz:SPCX"].read_text())
    payload["observed_at_ms"] = _millis(observed - timedelta(minutes=3))
    statuses["xyz:SPCX"].write_text(json.dumps(payload))

    result = module.load_index_signal_capture_health(
        status_paths=statuses,
        journal_paths=journals,
        run_started_at=datetime(2026, 8, 15, 0, 7, tzinfo=UTC),
        observed_at=observed,
        maximum_age_seconds=90.0,
    )

    assert result.status["status"] == "unavailable_stale"
    assert result.status["age_seconds_by_symbol"]["xyz:SPCX"] == 180.0


def test_wrong_observer_identity_fails_explicitly(tmp_path: Path) -> None:
    """Another symbol or provider cannot enter the v51 continuity record."""
    module = _module()
    observed = datetime(2026, 8, 15, 0, 46, tzinfo=UTC)
    statuses, journals = _sources(tmp_path, observed, (1, 2, 3))
    payload = json.loads(statuses["xyz:SP500"].read_text())
    payload["provider_id"] = "wrong-provider"
    statuses["xyz:SP500"].write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="observer has invalid provider_id"):
        module.load_index_signal_capture_health(
            status_paths=statuses,
            journal_paths=journals,
            run_started_at=datetime(2026, 8, 15, 0, 7, tzinfo=UTC),
            observed_at=observed,
            maximum_age_seconds=90.0,
        )


def _module() -> ModuleType:
    assert importlib.util.find_spec(MODULE) is not None, "health module is missing"
    return importlib.import_module(MODULE)


def _sources(
    root: Path, observed: datetime, offsets: tuple[int, ...]
) -> tuple[dict[str, Path], dict[str, Path]]:
    start = datetime(2026, 8, 15, 0, 0, tzinfo=UTC)
    cursor = _millis(start) + max(offsets) * CADENCE_MS
    statuses: dict[str, Path] = {}
    journals: dict[str, Path] = {}
    for symbol, profile in PROFILES.items():
        slug = symbol.lower().replace(":", "_")
        status = root / f"{slug}_latest.json"
        journal = root / f"{slug}_decisions.jsonl"
        status.write_text(json.dumps(_status(symbol, profile, cursor, observed)))
        rows = [
            _decision(symbol, profile, _millis(start) + offset * CADENCE_MS)
            for offset in offsets
        ]
        journal.write_text("".join(json.dumps(row) + "\n" for row in rows))
        statuses[symbol] = status
        journals[symbol] = journal
    return statuses, journals


def _status(
    symbol: str, profile: str, cursor: int, observed: datetime
) -> dict[str, object]:
    token = symbol.removeprefix("xyz:").lower()
    return {
        "schema_version": 1,
        "mode": f"{token}_hip3_breakout_shadow_observer",
        "symbol": symbol,
        "provider_id": PROVIDER,
        "profile_id": profile,
        "cursor_decision_time_ms": cursor,
        "observed_at_ms": _millis(observed - timedelta(seconds=1)),
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "signing_client_constructed": False,
        "orders_supported": False,
        "signal_ohlc_source": "hyperliquid_public_candleSnapshot_15m",
        "pressure_source": "hyperliquid_mainnet_l2_rest",
    }


def _decision(symbol: str, profile: str, boundary: int) -> dict[str, object]:
    token = symbol.removeprefix("xyz:").lower()
    return {
        "schema_version": 1,
        "event_type": f"{token}_hip3_breakout_shadow_decision",
        "event_id": f"{PROVIDER}|{symbol}|{boundary}",
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "intents": [],
        "decision": {
            "decision_time_ms": boundary,
            "provider_id": PROVIDER,
            "profile_id": profile,
            "symbol": symbol,
            "prospective": True,
            "execution_authority": "none",
        },
    }


def _millis(value: datetime) -> int:
    return int(value.timestamp() * 1_000)
