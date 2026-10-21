"""Funding-query continuity across an offline cohort restart."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import create_autospec

import pytest

from test_multi_asset_bidirectional_live_script import _load_module

from hypervector.live.cohort_funding_window import committed_funding_window
from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_protocols import (
    MultiAssetEngineProtocol,
    MultiAssetIntentPollerProtocol,
)
from hypervector.live.asset_ledger import AssetLiveLedger

PROFILE = Path("tests/fixtures/profiles/mixed_crypto_hip3.toml")
DAY_MS = 86_400_000
COMMITTED_END_MS = 1_789_141_030_000


def test_long_downtime_restores_last_committed_funding_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A two-day outage cannot exclude funding that followed the last durable query."""
    module = _load_module()
    config = replace(
        load_multi_asset_live_config(
            PROFILE, mode="live", enabled=True, accepts_live_risk=True
        ),
        cohort_ledger=tmp_path / "live/bidirectional_cohort/decisions.jsonl",
        stop_file=tmp_path / "STOP",
    )
    ledger = AssetLiveLedger(
        path=config.cohort_ledger,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="stopped-owner",
    )
    window = committed_funding_window(
        COMMITTED_END_MS - 15_000, COMMITTED_END_MS, COMMITTED_END_MS + 5_000, 0
    )
    ledger.append(
        event_type="funding_reconciliation_window",
        observed_at_utc=datetime.fromtimestamp(
            COMMITTED_END_MS / 1000, UTC
        ).isoformat(),
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload=window.as_payload(),
    )
    telemetry = MultiAssetCohortTelemetry(
        config=config, ledger=ledger, now_fn=lambda: datetime(2026, 9, 13, tzinfo=UTC)
    )
    monkeypatch.setattr(telemetry, "emit_configuration", lambda: None)
    monkeypatch.setattr(module, "_create_operator_inbox", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "install_process_signal_stop",
        lambda *_args: SimpleNamespace(requested=False),
    )
    engines = {
        symbol: create_autospec(MultiAssetEngineProtocol, instance=True)
        for symbol in config.symbols
    }
    poller = create_autospec(MultiAssetIntentPollerProtocol, instance=True)
    runner = module._create_runner(config, engines, poller, telemetry, None, "recovery")

    runner.start(activation_time_ms=COMMITTED_END_MS + 2 * DAY_MS, start_engines=False)

    assert runner._funding_start_ms == COMMITTED_END_MS
    assert all(not engine.method_calls for engine in engines.values())
