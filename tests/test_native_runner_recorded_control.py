"""Original cold/warm candles through actual configured providers and the native runner."""

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from native_replay_protective_fixture import ProtectiveEngineFixture
from native_replay_runner_fixture import configured_recorded_runner
from test_native_replay_adapter import deny_external_ports

from hypervector.research.native_runner_recorded_fetch import RecordedRunnerFetch

__all__ = ["deny_external_ports"]
INPUTS = Path(__file__).parent / "fixtures/native_runner_cold_warm_20260911"


def test_original_cold_warm_packets_reach_native_cohort_telemetry(tmp_path: Path) -> None:
    """No-entry captures qualify acquisition/runner observability, not execution economics."""
    manifest = json.loads((INPUTS / "manifest.json").read_text())
    replay = ProtectiveEngineFixture(tmp_path)
    assert sha256(replay.config.source_path.read_bytes()).hexdigest() == manifest["profile_sha256"]
    fetch = RecordedRunnerFetch(replay.clock)
    runner, ledger = configured_recorded_runner(replay, fetch)
    totals = []
    for index, label in enumerate(("cold", "warm1", "warm2")):
        relative = f"profile_{label}.json"
        packet = json.loads((INPUTS / relative).read_text())
        cutoff = int(datetime.fromisoformat(packet["observed_cutoff_utc"]).timestamp() * 1000)
        replay.clock.advance_to(cutoff)
        if index == 0:
            runner.start(activation_time_ms=cutoff)
        checksum = next(row["sha256"] for row in manifest["files"] if row["relative"] == relative)
        fetch.load_packet(INPUTS / relative, checksum)
        totals.append(runner.poll_once())
    assert totals == [0, 0, 0]
    assert fetch.completed_packets == 3
    assert replay.mutations == ["configure"] * 7
    assert not replay.account.snapshot().positions and not replay.orders
    rows = [json.loads(line) for line in ledger.path.read_text().splitlines()]
    snapshots = [row["payload"] for row in rows if row["event_type"] == "cohort_snapshot"]
    assert len(snapshots) == 3
    for snapshot in snapshots:
        assert snapshot["account_value_usd"] == 5000
        assert snapshot["open_position_count"] == 0
        assert [asset["symbol"] for asset in snapshot["assets"]] == list(replay.symbols)
    assert len([row for row in rows if row["event_type"] == "heartbeat"]) == 3
    assert len([row for row in rows if row["event_type"] == "canonical_regime_evaluations"]) == 2
    _assert_recorded_telemetry(rows)


def _assert_recorded_telemetry(rows: list[dict[str, object]]) -> None:
    expected = json.loads((INPUTS / "expected_telemetry.json").read_text())
    routing = [row["payload"] for row in rows if row["event_type"] == "intent_routing"]
    regimes = [
        row["payload"]["evaluations"]
        for row in rows
        if row["event_type"] == "canonical_regime_evaluations"
    ]
    snapshots = [row["payload"] for row in rows if row["event_type"] == "cohort_snapshot"]
    for baseline, route, snapshot in zip(expected, routing, snapshots, strict=True):
        assert route["evaluations"] == _live_expected_evaluations(baseline["evaluations"])
        assert route["setup_coverage"]["complete"] is True
        assert {
            asset["symbol"]: asset["market_reference_price"] for asset in snapshot["assets"]
        } == baseline["reference_prices"]
    for actual, baseline in zip(regimes, expected[1:], strict=True):
        assert actual == _live_expected_evaluations(baseline["regime_evaluations"])


def _live_expected_evaluations(evaluations: list[dict[str, object]]) -> list[dict[str, object]]:
    """Account explicitly for the live HYPE authority and the TUI's derived fraction."""
    for evaluation in evaluations:
        readiness = evaluation["readiness"]
        if readiness is None:
            continue
        assert readiness["conditions_required"] > 0
        readiness["readiness_fraction"] = (
            readiness["conditions_met"] / readiness["conditions_required"]
        )
        if evaluation["strategy_id"] != "hype_breakout_compression_alignment_bidirectional_v2":
            continue
        for key in ("candidate_authority", "entry_policy_authority"):
            assert readiness["metrics"][key] == "report_only"
            readiness["metrics"][key] = "automatic_execution"
        assert readiness["indicators"].count("EXIT 80BPS STOP [REPORT ONLY]") == 1
        readiness["indicators"] = [
            "EXIT 80BPS STOP [AUTOMATIC EXECUTION]"
            if value == "EXIT 80BPS STOP [REPORT ONLY]"
            else value
            for value in readiness["indicators"]
        ]
    return evaluations
