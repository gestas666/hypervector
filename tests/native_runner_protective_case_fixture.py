"""Shared owned-protective-exit runner case for the split native runner test modules.

Each case builds the configured seven-engine runner and performs one full recorded poll, so
the cases are split across modules by entry side to let ``--dist loadfile`` spread them.
"""

from datetime import datetime
import json
from pathlib import Path

import pytest
from native_replay_protective_fixture import ProtectiveEngineFixture
from native_replay_runner_fixture import configured_recorded_runner
from test_native_protective_observation import assert_current_flat_ledger, assert_exact_cash
from test_native_runner_recorded_control import INPUTS

from hypervector.research.native_runner_recorded_fetch import RecordedRunnerFetch

CASES = [
    (symbol, "stop")
    for symbol in ("BTC", "ETH", "SOL", "HYPE", "xyz:BBB", "xyz:CCC", "xyz:EEE")
]
CASES.append(("BTC", "target"))
HISTORY_DELAY_MS = 500
BRACKET_OBSERVATION_MS = 750
SIBLING_CANCEL_OBSERVATION_MS = 550
PROTECTIVE_EXECUTION_ADVANCE_MS = 1000


def assert_protective_exit_final_cohort(
    tmp_path: Path, symbol: str, kind: str, last_side: bool
) -> None:
    """The actual runner must publish its cleaned final account after an owned exit."""
    replay = ProtectiveEngineFixture(tmp_path)
    original = replay.enter_current(replay.assets[symbol], last_side=last_side)
    fetch = RecordedRunnerFetch(replay.clock)
    runner, ledger = configured_recorded_runner(replay, fetch)
    packet = json.loads((INPUTS / "profile_cold.json").read_text())
    cutoff = int(datetime.fromisoformat(packet["observed_cutoff_utc"]).timestamp() * 1000)
    delay = (
        BRACKET_OBSERVATION_MS + SIBLING_CANCEL_OBSERVATION_MS
        if original.target_oid is not None
        else HISTORY_DELAY_MS
    )
    replay.clock.advance_to(cutoff - delay - PROTECTIVE_EXECUTION_ADVANCE_MS)
    runner.start(activation_time_ms=replay.clock.now_ms)
    oid = original.stop_oid if kind == "stop" else original.target_oid
    assert oid is not None
    replay.fill_owned_order(oid, history_delay_ms=HISTORY_DELAY_MS)
    manifest = json.loads((INPUTS / "manifest.json").read_text())
    checksum = next(
        row["sha256"] for row in manifest["files"] if row["relative"] == "profile_cold.json"
    )
    fetch.load_packet(INPUTS / "profile_cold.json", checksum)
    assert runner.poll_once() == 0
    assert fetch.completed_packets == 1
    assert not replay.orders and not replay.account.snapshot().positions
    assert replay.mutations.count("entry") == 1 and replay.mutations.count("close") == 0
    assert_exact_cash(replay)
    assert_current_flat_ledger(replay, symbol)
    rows = [json.loads(line) for line in ledger.path.read_text().splitlines()]
    snapshot = [row["payload"] for row in rows if row["event_type"] == "cohort_snapshot"][-1]
    assert snapshot["account_value_usd"] == pytest.approx(float(replay.account.snapshot().cash_usd))
    assert snapshot["open_position_count"] == 0
    assert [asset["symbol"] for asset in snapshot["assets"]] == list(replay.symbols)
