"""Shared partial-protection runner cases for the split native runner test modules.

The configured seven-engine runner cases are expensive (one full recorded poll each), so
their test modules are split to let ``--dist loadfile`` spread them across workers. This
non-test module holds the schedule and inspection helpers those modules share.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path

import pytest
from native_replay_partial_protective_fixture import PartialProtectiveFixture
from native_replay_runner_fixture import configured_recorded_runner
from test_native_partial_protective_execution import assert_partial_economics
from test_native_partial_protective_recovery import assert_closed_economics
from test_native_runner_recorded_control import INPUTS

from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.live.sol_range_onset_state import SolLiveSnapshot
from hypervector.research.native_runner_recorded_fetch import RecordedRunnerFetch

PARTIAL_OBSERVATION_MS = 750
FOLLOWUP_CLOSE_OBSERVATION_MS = 450
SIBLING_CANCEL_OBSERVATION_MS = 550
PARTIAL_EXECUTION_ADVANCE_MS = 1000
ENTRY_LEAD_MS = 30_000


@dataclass
class RunnerPartialCase:
    """Keep the actual configured runner and its explicit offline execution inputs."""

    replay: PartialProtectiveFixture
    runner: MultiAssetLiveRunner
    ledger: SolLiveLedger
    fetch: RecordedRunnerFetch
    original: SolLiveSnapshot


def partial_case(
    root: Path, symbol: str, kind: str, last_side: bool, *, partial_close: bool = False
) -> RunnerPartialCase:
    """Schedule native receipts so recorded acquisition starts at its exact original cutoff."""
    packet = json.loads((INPUTS / "profile_cold.json").read_text())
    cutoff = int(datetime.fromisoformat(packet["observed_cutoff_utc"]).timestamp() * 1000)
    replay = PartialProtectiveFixture(root)
    replay.clock.advance_to(cutoff - ENTRY_LEAD_MS)
    original = replay.enter_current(replay.assets[symbol], last_side=last_side)
    fetch = RecordedRunnerFetch(replay.clock)
    runner, ledger = configured_recorded_runner(replay, fetch)
    delay = PARTIAL_OBSERVATION_MS
    if kind == "stop":
        delay += FOLLOWUP_CLOSE_OBSERVATION_MS
        if original.target_oid is not None and not partial_close:
            delay += SIBLING_CANCEL_OBSERVATION_MS
    replay.clock.advance_to(cutoff - delay - PARTIAL_EXECUTION_ADVANCE_MS)
    runner.start(activation_time_ms=replay.clock.now_ms)
    collateral = replay.collateral[symbol]
    replay.fill_partial_protection(
        original.target_oid if kind == "target" else original.stop_oid,
        remaining_collateral=replace(collateral, cash_usd=collateral.cash_usd / 2),
        history_delay_ms=0,
        remainder_open=kind == "target",
        fee_rate=Decimal("0.00015") if kind == "target" else Decimal("0.0009"),
    )
    if partial_close:
        replay.partial_operation = "close"
        replay.partial_close_collateral[symbol] = replay.collateral[symbol]
    manifest = json.loads((INPUTS / "manifest.json").read_text())
    checksum = next(
        row["sha256"] for row in manifest["files"] if row["relative"] == "profile_cold.json"
    )
    fetch.load_packet(INPUTS / "profile_cold.json", checksum)
    return RunnerPartialCase(replay, runner, ledger, fetch, original)


def final_cohort(case: RunnerPartialCase) -> dict[str, object]:
    """Read the last actual emitted cohort snapshot, including shared account values."""
    rows = [json.loads(line) for line in case.ledger.path.read_text().splitlines()]
    snapshots = [row["payload"] for row in rows if row["event_type"] == "cohort_snapshot"]
    assert len(snapshots) == 1
    result = snapshots[0]
    assert [asset["symbol"] for asset in result["assets"]] == list(case.replay.symbols)
    assert result["account_value_usd"] == pytest.approx(
        float(case.replay.account.snapshot().equity_usd)
    )
    return result


def assert_partial_protection_final_state(
    tmp_path: Path, symbol: str, kind: str, last_side: bool
) -> None:
    """The configured runner publishes the reduced protected target or completed stop exit."""
    case = partial_case(tmp_path, symbol, kind, last_side)
    assert case.runner.poll_once() == 0
    assert case.fetch.completed_packets == 1
    cohort = final_cohort(case)
    asset = next(row for row in cohort["assets"] if row["symbol"] == symbol)
    if kind == "target":
        assert cohort["open_position_count"] == 1 and asset["state"] == "OPEN"
        assert (
            asset["position_size_signed"]
            == case.replay.engines[symbol].snapshot.position_size_signed
        )
        assert asset["opened_at_ms"] == case.original.opened_at_ms
        assert asset["partial_exit_fill_count"] == 1 and asset["partial_exit_size"] > 0
        assert asset["protective_exit_pending"] is False
        assert asset["stop_protection"] == "covering"
    else:
        assert cohort["open_position_count"] == 0 and asset["state"] == "FLAT"
        assert asset["stop_protection"] == "flat"
        assert asset["protective_exit_pending"] is False
        assert case.replay.mutations.count("close") == 1
        assert_closed_economics(case.replay, symbol)
    assert_partial_economics(case.replay)
