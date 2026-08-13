import json
from pathlib import Path

import pytest

from hypervector.live.hulk_smash_live_ledger import (
    HulkSmashLiveLedger,
    HulkSmashLiveLedgerError,
)


def test_hulk_ledger_appends_disarmed_events_without_secrets(tmp_path: Path) -> None:
    path = tmp_path / "data/live/hulk_smash/decisions.jsonl"
    ledger = HulkSmashLiveLedger(
        path=path,
        profile_id="profile",
        profile_fingerprint="profile-hash",
        run_fingerprint="run-hash",
        run_id="run-1",
    )

    ledger.append(
        event_type="configuration_identity",
        observed_at_utc="2026-08-01T12:00:00+00:00",
        live_armed=False,
        execution_authority="none",
        payload={"strategy_name": "hulk_expansion_short_robust_v3"},
    )

    record = json.loads(path.read_text().strip())
    assert record["sequence"] == 1
    assert record["live_armed"] is False
    assert record["effective_mode"] == "DISARMED"
    assert record["execution_authority"] == "none"


def test_hulk_ledger_rejects_wrong_domain_and_secret_shaped_payload(
    tmp_path: Path,
) -> None:
    with pytest.raises(HulkSmashLiveLedgerError, match="hulk_smash"):
        HulkSmashLiveLedger(
            path=tmp_path / "data/live/not_hulk/decisions.jsonl",
            profile_id="profile",
            profile_fingerprint="profile-hash",
            run_fingerprint="run-hash",
            run_id="run-1",
        )
    ledger = HulkSmashLiveLedger(
        path=tmp_path / "data/live/hulk_smash/decisions.jsonl",
        profile_id="profile",
        profile_fingerprint="profile-hash",
        run_fingerprint="run-hash",
        run_id="run-1",
    )
    with pytest.raises(HulkSmashLiveLedgerError, match="secret-shaped"):
        ledger.append(
            event_type="configuration_identity",
            observed_at_utc="2026-08-01T12:00:00+00:00",
            live_armed=False,
            execution_authority="none",
            payload={"private_key": "must-not-write"},
        )
