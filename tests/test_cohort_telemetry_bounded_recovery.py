"""Bounded startup recovery for the shared cohort telemetry ledger."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.sol_range_onset_ledger import SolLiveLedger


def test_durable_decision_recovery_does_not_materialize_complete_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telemetry retains decision rows while streaming unrelated history."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    ledger = SolLiveLedger(
        path=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="bounded-recovery-test",
    )
    ledger.append(
        event_type="maximum_hold_decision",
        observed_at_utc="2026-08-20T12:00:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"decision_id": "hold-1"},
    )

    def forbidden_read_all() -> list[dict[str, object]]:
        raise AssertionError("telemetry recovery must stream the cohort ledger")

    monkeypatch.setattr(ledger, "read_all", forbidden_read_all)
    telemetry = MultiAssetCohortTelemetry(
        config=config,
        ledger=ledger,
        now_fn=lambda: datetime(2026, 8, 20, 12, tzinfo=UTC),
    )

    assert telemetry.recorded_maximum_hold_decision("hold-1") == {
        "decision_id": "hold-1"
    }
