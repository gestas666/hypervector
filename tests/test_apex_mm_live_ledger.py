"""Durability and domain-isolation contracts for the Apex MM live ledger."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.apex_mm_live_ledger import (
    ApexMMLiveLedger,
    ApexMMLiveLedgerError,
)


def _ledger(path: Path) -> ApexMMLiveLedger:
    return ApexMMLiveLedger(
        path=path,
        profile_id="apex_regime_mm_canary_v1",
        profile_fingerprint="profile-fingerprint",
        run_fingerprint="run-fingerprint",
        run_id="run-id",
    )


def test_ledger_is_append_only_and_accepts_mm_telemetry(tmp_path: Path) -> None:
    path = tmp_path / "data/live/apex_regime_mm/decisions.jsonl"
    ledger = _ledger(path)

    ledger.append(
        event_type="theoretical_quote",
        observed_at_utc="2026-08-01T12:00:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"strategy_id": "apex_regime_mm_v2", "bid_price": 100.0},
    )
    ledger.append(
        event_type="fill_markout",
        observed_at_utc="2026-08-01T12:00:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"oid": 1, "markout_bps": -1.0},
    )

    assert [row["sequence"] for row in ledger.read_all()] == [1, 2]


def test_ledger_rejects_other_live_domains(tmp_path: Path) -> None:
    with pytest.raises(ApexMMLiveLedgerError, match="apex_regime_mm"):
        _ledger(tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl")


def test_ledger_rejects_secret_shaped_payloads(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "data/live/apex_regime_mm/decisions.jsonl")

    with pytest.raises(ApexMMLiveLedgerError, match="secret-shaped"):
        ledger.append(
            event_type="fault",
            observed_at_utc="2026-08-01T12:00:00+00:00",
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload={"private_key": "forbidden"},
        )
