"""Durable telemetry contracts for live profit-lock decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.sol_range_onset_ledger import SolLiveLedger


def _telemetry(
    tmp_path: Path,
    ledger: SolLiveLedger | None = None,
) -> tuple[MultiAssetCohortTelemetry, SolLiveLedger]:
    config = load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    sink = ledger or SolLiveLedger(
        path=tmp_path / "data/live/bidirectional_cohort/profit-lock.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="profit-lock-test",
    )
    return (
        MultiAssetCohortTelemetry(
            config=config,
            ledger=sink,
            now_fn=lambda: datetime(2026, 8, 13, tzinfo=UTC),
        ),
        sink,
    )


def _payload() -> dict[str, object]:
    return {
        "decision_id": "SOL:7:profit_lock_exit",
        "lifecycle_id": "SOL:7",
        "strategy_id": "range_onset_bidirectional_v1",
        "symbol": "SOL",
        "side": "long",
        "outcome": "exit",
        "exit_reason": "completed_bar_profit_lock",
        "decision_time_ms": 180_000,
    }


def test_profit_lock_decision_survives_restart_exactly_once(tmp_path: Path) -> None:
    """A durable exit remains readable and idempotent after reconstruction."""
    telemetry, ledger = _telemetry(tmp_path)
    payload = _payload()

    telemetry.emit_profit_lock_decision(payload)
    restarted, _ = _telemetry(tmp_path, ledger)
    restarted.emit_profit_lock_decision(payload)

    assert restarted.recorded_profit_lock_decision(payload["decision_id"]) == payload
    rows = ledger.read_all()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "profit_lock_decision"


def test_profit_lock_decision_rejects_conflicting_identity(tmp_path: Path) -> None:
    """One lifecycle decision ID cannot describe two exit boundaries."""
    telemetry, _ = _telemetry(tmp_path)
    payload = _payload()
    telemetry.emit_profit_lock_decision(payload)

    with pytest.raises(ValueError, match="conflicting profit-lock decision"):
        telemetry.emit_profit_lock_decision(payload | {"decision_time_ms": 240_000})
