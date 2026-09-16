"""Stopped-process truth must survive recovery of older trade evidence."""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hypervector.research.checkpoint_ledger_projection import compact_asset_ledger_rows
from hypervector.research.cohort_checkpoint_asset_snapshots import (
    snapshot_checkpoint_assets,
)
from test_checkpoint_ledger_projection import _row, _write_rows
from test_cohort_checkpoint_restart_recovery import (
    _hashes,
    _open_restart_fixture,
    _publish,
    _write_ledgers,
)
from test_multi_asset_live_audit import _RUN_ID


def test_recovered_trade_can_publish_all_stopped_lifecycle(tmp_path: Path) -> None:
    """A protected inherited position remains visible after every worker stops."""
    cohort, assets = _stopped_fixture()
    root = _write_ledgers(tmp_path, cohort, assets)
    before = _hashes(root)

    checkpoint = _publish(root, tmp_path)

    assert checkpoint["lifecycle"]["backend_process_health"] == "stopped"
    assert checkpoint["lifecycle"]["all_assets_terminal"] is True
    assert set(checkpoint["lifecycle"]["asset_states"].values()) == {"STOPPED"}
    health = checkpoint["audit"]["health"]["assets"]["BTC"]
    assert health["final_state"] == "OPEN"
    assert health["protected_if_open"] is True
    assert health["position_size_signed"] == 0.25
    position = checkpoint["audit"]["execution"]["open_positions"][0]
    assert position["funding_usd"] == pytest.approx(-0.007)
    assert _hashes(root) == before


@pytest.mark.parametrize("current_run_only", [False, True])
def test_both_compacted_snapshot_modes_retain_stop_records(
    tmp_path: Path, current_run_only: bool
) -> None:
    """Current-run recovery and compatible history retain the same process truth."""
    cohort, assets = _stopped_fixture()
    root = _write_ledgers(tmp_path, cohort, assets)
    cutoff = _cutoff(cohort)
    with ExitStack() as stack:
        rows, _ = snapshot_checkpoint_assets(
            stack,
            {symbol: root / f"{symbol.lower()}.jsonl" for symbol in assets},
            run_id=_RUN_ID,
            as_of=cutoff,
            current_run_only=current_run_only,
            compatible_execution_history=not current_run_only,
        )
        for records in rows.values():
            transitions = [
                row for row in records if row["event_type"] == "state_transition"
            ]
            assert transitions[-1]["payload"]["state"] == "STOPPED"


@pytest.mark.parametrize("state", ["FAULT", "FLAT"])
def test_recovered_history_cannot_conceal_partial_stop_or_fault(
    tmp_path: Path, state: str
) -> None:
    """Recovery must preserve the mismatching state so publication fails closed."""
    cohort, assets = _stopped_fixture()
    assets["BTC"][-1]["payload"]["state"] = state
    root = _write_ledgers(tmp_path, cohort, assets)

    with pytest.raises(ValueError, match="checkpoint asset state cutoff mismatch"):
        _publish(root, tmp_path)

    assert not (tmp_path / "checkpoint.json").exists()


def test_stopped_recovered_position_still_requires_protection(tmp_path: Path) -> None:
    """A missing venue stop remains a publication failure after lifecycle recovery."""
    cohort, assets = _stopped_fixture()
    for row in assets["BTC"]:
        if row["run_id"] == _RUN_ID and row["event_type"] == "reconciliation":
            row["payload"]["open_order_ids"] = []
    root = _write_ledgers(tmp_path, cohort, assets)
    with pytest.raises(ValueError, match="checkpoint asset state cutoff mismatch"):
        _publish(root, tmp_path)
    assert not (tmp_path / "checkpoint.json").exists()


@pytest.mark.parametrize("retain_lifecycle", [False, True])
def test_post_cutoff_projection_only_retains_requested_current_lifecycle(
    tmp_path: Path, retain_lifecycle: bool
) -> None:
    """Opt-in lifecycle retention cannot introduce later financial or foreign rows."""
    rows = [_row(1, "state_transition", {"state": "OPEN"})]
    rows.extend(
        [
            _row(2, "state_transition", {"state": "STOPPED"}),
            _row(3, "funding", {"usdc_delta": 999.0}),
            _row(4, "position", {"size_signed": 0.0}),
            {**_row(5, "state_transition", {"state": "FAULT"}), "run_id": "foreign"},
        ]
    )
    path = _write_rows(tmp_path / "projection.jsonl", rows)
    result = compact_asset_ledger_rows(
        path,
        current_run_id="run-current",
        as_of=datetime(2026, 8, 20, 12, 0, 1, tzinfo=timezone.utc),
        include_post_cutoff_lifecycle=retain_lifecycle,
    )

    expected = rows[:2] if retain_lifecycle else rows[:1]
    assert result.rows == expected
    assert result.source_sequence_end == 5


def _stopped_fixture() -> tuple[
    list[dict[str, object]], dict[str, list[dict[str, object]]]
]:
    """Append actual shutdown ordering after a protected-position snapshot."""
    cohort, assets = _open_restart_fixture()
    for row in assets["BTC"]:
        if row["run_id"] == _RUN_ID and row["event_type"] == "reconciliation":
            row["payload"]["open_order_ids"] = [12]
    stop_at = (_cutoff(cohort) + timedelta(seconds=1)).isoformat()
    for symbol, rows in assets.items():
        transitions = [row for row in rows if row["event_type"] == "state_transition"]
        latest = transitions[-1]
        if symbol != "BTC":
            latest["payload"].update(state="FLAT", stop_reason=None)
        funding = deepcopy(rows[-1])
        funding.update(
            sequence=len(rows) + 1,
            event_type="funding",
            observed_at_utc=stop_at,
            payload={"usdc_delta": 999.0, "venue_timestamp_ms": 1_785_696_000_000},
        )
        stopped = deepcopy(latest)
        stopped.update(sequence=len(rows) + 2, observed_at_utc=stop_at)
        stopped["payload"].update(state="STOPPED", stop_reason="operator_stop")
        rows.extend([funding, stopped])
    return cohort, assets


def _cutoff(cohort: list[dict[str, object]]) -> datetime:
    """Return the fixture's last economic snapshot boundary."""
    snapshot = next(
        row for row in reversed(cohort) if row["event_type"] == "cohort_snapshot"
    )
    return datetime.fromisoformat(str(snapshot["observed_at_utc"]))
