"""Drive seven simultaneous positions through the configured recorded-acquisition runner."""

import json
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from native_replay_partial_protective_fixture import PartialProtectiveFixture
from native_replay_portfolio_oracle import INITIAL_CASH, portfolio_receipt_oracle
from native_replay_runner_fixture import configured_recorded_runner
from native_runner_partial_case_fixture import (
    ENTRY_LEAD_MS,
    FOLLOWUP_CLOSE_OBSERVATION_MS,
    PARTIAL_EXECUTION_ADVANCE_MS,
    PARTIAL_OBSERVATION_MS,
    SIBLING_CANCEL_OBSERVATION_MS,
)
from test_native_replay_adapter import deny_external_ports
from test_native_runner_recorded_control import INPUTS

from hypervector.live.sol_live_snapshot import SolLiveSnapshot
from hypervector.live.sol_range_onset_live_journal import build_live_journal
from hypervector.research.native_runner_recorded_fetch import RecordedRunnerFetch

__all__ = ["deny_external_ports"]
STOP_FEE_RATE = Decimal("0.0009")


@pytest.mark.parametrize("last_sides", [False, True])
@pytest.mark.parametrize("partial_close", [False, True])
def test_seven_simultaneous_partial_stops_preserve_shared_economics_and_runner_state(
    tmp_path: Path, last_sides: bool, partial_close: bool
) -> None:
    """Every configured asset closes or retains its exact pending remainder in one native poll."""
    cutoff = int(
        datetime.fromisoformat(
            json.loads((INPUTS / "profile_cold.json").read_text())["observed_cutoff_utc"]
        ).timestamp()
        * 1000
    )
    replay = PartialProtectiveFixture(tmp_path)
    replay.clock.advance_to(cutoff - 2 * ENTRY_LEAD_MS)
    originals = {
        symbol: replay.enter_current(replay.assets[symbol], last_side=last_sides)
        for symbol in replay.symbols
    }
    assert len(replay.account.snapshot().positions) == 7
    portfolio_receipt_oracle(replay)
    fetch = RecordedRunnerFetch(replay.clock)
    runner, ledger = configured_recorded_runner(replay, fetch)
    delays = len(originals) * (PARTIAL_OBSERVATION_MS + FOLLOWUP_CLOSE_OBSERVATION_MS)
    if not partial_close:
        delays += SIBLING_CANCEL_OBSERVATION_MS
    replay.clock.advance_to(cutoff - delays - len(originals) * PARTIAL_EXECUTION_ADVANCE_MS)
    runner.start(activation_time_ms=replay.clock.now_ms)
    _partial_stops(replay, originals, partial_close)
    portfolio_receipt_oracle(replay)
    _load_cold_packet(fetch)
    assert runner.poll_once() == 0 and fetch.completed_packets == 1
    expected = portfolio_receipt_oracle(replay)
    snapshots = [
        row["payload"] for row in ledger.read_all() if row["event_type"] == "cohort_snapshot"
    ]
    assert len(snapshots) == 1
    cohort = snapshots[0]
    assert cohort["account_value_usd"] == pytest.approx(
        float(
            INITIAL_CASH + sum(row.gross - row.fees + row.unrealized for row in expected.values())
        )
    )
    assert cohort["total_notional_position_usd"] == pytest.approx(
        float(sum(row.notional for row in expected.values()))
    )
    assert cohort["open_position_count"] == (7 if partial_close else 0)
    _assert_asset_results(replay, originals, cohort["assets"], partial_close)
    assert replay.mutations.count("close") == 7


def _partial_stops(
    replay: PartialProtectiveFixture, originals: dict[str, SolLiveSnapshot], partial_close: bool
) -> None:
    for symbol, original in originals.items():
        collateral = replay.collateral[symbol]
        replay.fill_partial_protection(
            original.stop_oid,
            remaining_collateral=replace(collateral, cash_usd=collateral.cash_usd / 2),
            history_delay_ms=0,
            remainder_open=False,
            fee_rate=STOP_FEE_RATE,
        )
    if partial_close:
        replay.partial_operation = "close"
        replay.partial_close_collateral.update(replay.collateral)


def _load_cold_packet(fetch: RecordedRunnerFetch) -> None:
    manifest = json.loads((INPUTS / "manifest.json").read_text())
    checksum = next(
        row["sha256"] for row in manifest["files"] if row["relative"] == "profile_cold.json"
    )
    fetch.load_packet(INPUTS / "profile_cold.json", checksum)


def _assert_asset_results(
    replay: PartialProtectiveFixture,
    originals: dict[str, SolLiveSnapshot],
    assets: list[dict[str, object]],
    partial_close: bool,
) -> None:
    expected = portfolio_receipt_oracle(replay)
    assert [row["symbol"] for row in assets] == list(replay.symbols)
    for asset in assets:
        symbol = asset["symbol"]
        assert asset["state"] == ("EXIT_PENDING" if partial_close else "FLAT")
        assert asset["position_size_signed"] == pytest.approx(
            float(expected[symbol].remaining_signed)
        )
        assert asset["stop_protection"] == ("missing" if partial_close else "flat")
        assert asset["protective_exit_pending"] is partial_close
        assert asset["fees_net_usd"] == pytest.approx(float(expected[symbol].fees))
        assert asset["realized_pnl_usd"] == pytest.approx(float(expected[symbol].gross))
        journal = build_live_journal(replay.engines[symbol]._ledger.read_all())
        if partial_close:
            assert asset["opened_at_ms"] == originals[symbol].opened_at_ms
            assert len(journal["open_lifecycles"]) == 1 and not journal["trades"]
        else:
            assert len(journal["trades"]) == 1 and not journal["open_lifecycles"]
            assert journal["trades"][0]["net_pnl_usd"] == pytest.approx(
                float(expected[symbol].gross - expected[symbol].fees)
            )
