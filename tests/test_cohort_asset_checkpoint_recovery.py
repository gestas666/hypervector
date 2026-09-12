"""Causal scope and identity checks for asset checkpoint history recovery."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from cohort_live_audit_trade_fixture import traded_asset_rows
from hypervector.research import cohort_asset_checkpoint_recovery as recovery
from test_cohort_checkpoint_restart_recovery import (
    _open_restart_fixture,
    _write_ledgers,
)
from test_multi_asset_live_audit import _RUN_ID, _asset_rows
from test_multi_asset_live_audit_restart import _restart_spanning_trade_rows

_CUTOFF = datetime(2026, 8, 2, tzinfo=timezone.utc)


@pytest.mark.parametrize("fresh_trade", [False, True])
def test_current_run_with_no_inherited_execution_avoids_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fresh_trade: bool
) -> None:
    """Flat restarts and independently opened trades retain the bounded fast path."""
    current = traded_asset_rows(_RUN_ID) if fresh_trade else _asset_rows("BTC")
    path = _write(tmp_path, [*traded_asset_rows("prior"), *current])

    def refuse_history(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unnecessary historical scan")

    monkeypatch.setattr(
        recovery, "snapshot_projected_compatible_execution_ledger", refuse_history
    )
    with recovery.snapshot_current_asset_ledger(
        path, run_id=_RUN_ID, as_of=_CUTOFF
    ) as (rows, evidence):
        assert rows == current
        assert evidence["snapshot_scope"] == "current_run"


def test_future_execution_does_not_expand_past_checkpoint(tmp_path: Path) -> None:
    """A position observed after the cohort cutoff cannot change that projection."""
    current = _asset_rows("BTC")
    future = deepcopy(current[-1])
    future["observed_at_utc"] = "2026-08-03T00:00:00+00:00"
    future["payload"].update(entry_oid=11, position_size_signed=0.25)
    path = _write(tmp_path, [*traded_asset_rows("prior"), *current, future])
    with recovery.snapshot_current_asset_ledger(
        path, run_id=_RUN_ID, as_of=_CUTOFF
    ) as (_, evidence):
        assert evidence["snapshot_scope"] == "current_run"


def test_owned_entry_must_match_recovered_lifecycle(tmp_path: Path) -> None:
    """A valid historical trade cannot stand in for a different owned order."""
    cohort, assets = _open_restart_fixture()
    for row in assets["BTC"]:
        if row["run_id"] == _RUN_ID and row["event_type"] == "state_transition":
            row["payload"]["entry_oid"] = 999
    root = _write_ledgers(tmp_path, cohort, assets)
    with pytest.raises(ValueError, match="inherited entry missing.*999"):
        with recovery.snapshot_current_asset_ledger(
            root / "btc.jsonl", run_id=_RUN_ID, as_of=_CUTOFF
        ):
            pytest.fail("mismatched ownership was accepted")


def test_recovered_close_must_match_attributed_exit(tmp_path: Path) -> None:
    """An older completed trade cannot conceal an unattributed current exit."""
    rows = _restart_spanning_trade_rows()
    for row in rows:
        if row["event_type"] == "close" and row["payload"].get("verified_flat") is True:
            row["payload"]["oid"] = 999
    path = _write(tmp_path, rows)
    with pytest.raises(ValueError, match="inherited close missing.*999"):
        with recovery.snapshot_current_asset_ledger(
            path, run_id=_RUN_ID, as_of=_CUTOFF
        ):
            pytest.fail("unattributed current close was accepted")


def test_repeated_restart_keeps_single_entry_and_exact_funding(tmp_path: Path) -> None:
    """Additional process identities do not duplicate durable entry or cash rows."""
    cohort, assets = _open_restart_fixture()
    prior_restart = [deepcopy(row) for row in assets["BTC"] if row["run_id"] == _RUN_ID]
    for row in prior_restart:
        row["run_id"] = "intermediate-restart"
    current = [
        deepcopy(row)
        for row in assets["BTC"]
        if row["run_id"] == _RUN_ID and row["event_type"] != "funding"
    ]
    initial = [row for row in assets["BTC"] if row["run_id"] != _RUN_ID]
    path = _write(tmp_path, [*initial, *prior_restart, *current])
    with recovery.snapshot_current_asset_ledger(
        path, run_id=_RUN_ID, as_of=_CUTOFF
    ) as (rows, evidence):
        entries = [row for row in rows if row["event_type"] == "order_acknowledgement"]
        funding = [
            row["payload"]["usdc_delta"]
            for row in rows
            if row["event_type"] == "funding"
        ]
        assert len(entries) == 1
        assert sum(funding) == pytest.approx(-0.007)
        assert evidence["inherited_entry_oids"] == [11]


def test_recovery_rejects_naive_cutoff(tmp_path: Path) -> None:
    """Recovery cannot assign causal scope to an ambiguous local timestamp."""
    path = _write(tmp_path, _asset_rows("BTC"))
    with pytest.raises(ValueError, match="timezone-aware"):
        with recovery.snapshot_current_asset_ledger(
            path, run_id=_RUN_ID, as_of=datetime(2026, 8, 2)
        ):
            pytest.fail("naive cutoff accepted")


def _write(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    """Write ordered synthetic source rows without touching a live ledger."""
    path = tmp_path / "btc.jsonl"
    path.write_text(
        "".join(
            json.dumps({**row, "sequence": sequence}) + "\n"
            for sequence, row in enumerate(rows, 1)
        )
    )
    return path


@pytest.mark.parametrize("accepted", [False, True])
def test_current_entry_acknowledgement_requires_no_prior_ownership(
    tmp_path: Path, accepted: bool
) -> None:
    """Rejected entries and known current entry IDs must not trigger history recovery."""
    current = traded_asset_rows(_RUN_ID)[: 8 if accepted else 5]
    current[4]["payload"]["accepted"] = accepted
    if accepted:
        state = deepcopy(_asset_rows("BTC")[-1])
        state["payload"].update(state="OPEN", entry_oid=11, position_size_signed=0.25)
        current.append(state)
    path = _write(tmp_path, [*traded_asset_rows("prior"), *current])
    with recovery.snapshot_current_asset_ledger(
        path, run_id=_RUN_ID, as_of=_CUTOFF
    ) as (_, evidence):
        assert evidence["snapshot_scope"] == "current_run"
