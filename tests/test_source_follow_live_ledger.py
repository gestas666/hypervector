"""Durability and secret-safety tests for the BTC source-follow live ledger."""

from pathlib import Path

import pytest

from hypervector.live.sol_range_onset_ledger import SolLiveLedgerError
from hypervector.live.source_follow_live_ledger import SourceFollowLiveLedger


def _ledger(path: Path) -> SourceFollowLiveLedger:
    return SourceFollowLiveLedger(
        path=path,
        profile_id="hypervelocity_source_follow_minrange12_alloc35_live_canary_v1",
        profile_fingerprint="profile",
        run_fingerprint="run",
        run_id="btc-live-1",
    )


def test_source_ledger_appends_sequence_and_preserves_restart_position(
    tmp_path: Path,
) -> None:
    """Reopening the ledger continues its append-only sequence."""
    path = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    first = _ledger(path)
    first.append(
        event_type="configuration_identity",
        observed_at_utc="2026-07-31T16:00:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"symbol": "BTC"},
    )
    second = _ledger(path)
    second.append(
        event_type="target_order",
        observed_at_utc="2026-07-31T16:00:01+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"oid": 202, "status": "resting"},
    )

    rows = second.read_all()
    assert [row["sequence"] for row in rows] == [1, 2]
    assert rows[-1]["event_type"] == "target_order"


def test_source_ledger_rejects_other_live_domains_and_secrets(tmp_path: Path) -> None:
    """BTC evidence cannot be mixed with SOL or contain secret-shaped fields."""
    with pytest.raises(SolLiveLedgerError, match="hypervelocity_source_follow"):
        _ledger(tmp_path / "data/live/sol_range_onset_canary/decisions.jsonl")

    ledger = _ledger(tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl")
    with pytest.raises(SolLiveLedgerError, match="secret"):
        ledger.append(
            event_type="fault",
            observed_at_utc="2026-07-31T16:00:00+00:00",
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload={"private_key": "forbidden"},
        )
