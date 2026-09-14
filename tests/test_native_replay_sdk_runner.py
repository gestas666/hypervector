"""Actual recorded acquisition and native routing through reusable offline SDK ports."""

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

import pytest
from test_native_replay_adapter import deny_external_ports
from test_native_replay_sdk_engines import cohort_sdk

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.sol_range_onset_state import SolLiveState
from hypervector.research.native_replay_runner import build_native_replay_runner
from hypervector.research.native_runner_recorded_fetch import RecordedRunnerFetch

__all__ = ["deny_external_ports"]
INPUTS = Path(__file__).parent / "fixtures/native_runner_cold_warm_20260911"


def test_real_cold_warm_polls_run_through_shared_sdk(tmp_path: Path) -> None:
    """Original no-entry packets retain provider output and account/telemetry identities."""
    config = load_multi_asset_live_config(
        "configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    replay = cohort_sdk(config, {})
    fetch = RecordedRunnerFetch(replay.runtime_clock)
    native = build_native_replay_runner(
        config=config,
        replay=replay,
        fetch_bars=fetch,
        output_root=tmp_path / "run",
        finish_poll=fetch.finish_poll,
    )
    manifest = json.loads((INPUTS / "manifest.json").read_text())
    assert sha256(config.source_path.read_bytes()).hexdigest() == manifest["profile_sha256"]
    for index, label in enumerate(("cold", "warm1", "warm2")):
        path = INPUTS / f"profile_{label}.json"
        record = json.loads(path.read_text())
        cutoff = int(datetime.fromisoformat(record["observed_cutoff_utc"]).timestamp() * 1000)
        replay.advance_to(cutoff)
        if index == 0:
            native.runner.start(activation_time_ms=cutoff)
        checksum = next(row["sha256"] for row in manifest["files"] if row["relative"] == path.name)
        fetch.load_packet(path, checksum)
        assert native.runner.poll_once() == 0
    assert fetch.completed_packets == 3
    assert replay.account.snapshot().equity_usd == 5000
    assert not replay.orders and not replay.fill_rows
    rows = native.cohort_ledger.read_all()
    snapshots = [r["payload"] for r in rows if r["event_type"] == "cohort_snapshot"]
    assert len(snapshots) == 3
    assert all(s["account_value_usd"] == 5000 for s in snapshots)
    assert all([a["symbol"] for a in s["assets"]] == list(config.symbols) for s in snapshots)
    assert all(engine.snapshot.state is SolLiveState.FLAT for engine in native.engines.values())


def test_real_engine_entry_uses_its_durable_decision_origin(tmp_path: Path) -> None:
    """The account receives the original plan decision, independent of SDK dispatch time."""
    config = load_multi_asset_live_config(
        "configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    replay = cohort_sdk(config, {})
    native = build_native_replay_runner(
        config=config,
        replay=replay,
        fetch_bars=RecordedRunnerFetch(replay.clock),
        output_root=tmp_path / "run",
    )
    native.runner.start(activation_time_ms=replay.clock.now_ms)
    for asset in config.assets:
        ledger = native.ledgers[asset.symbol]
        assert ledger.profile_id == asset.profile_id
        assert ledger.profile_fingerprint == asset.profile_fingerprint
        assert ledger.run_fingerprint == asset.run_fingerprint
        provider = next(p for p in config.providers if asset.symbol in p.execution_symbols)
        side = sorted(provider.executable_sides(asset.symbol))[0]
        decision = replay.clock.now_ms - 1234
        plan = provider.execution_for(asset.symbol, side).bind(
            strategy_id=provider.strategy_id,
            stop_anchor=98 if side == "long" else 102,
        )
        engine = native.engines[asset.symbol]
        engine.record_strategy_decision(
            {"execution_plan": plan.as_payload(), "decision_time_ms": decision}
        )
        assert (
            engine.enter(
                side=side,
                mark_price=100,
                decision_time_ms=decision,
                entry_sizing=provider.entry_sizing(asset.symbol, side),
            ).state
            is SolLiveState.OPEN
        )
        assert replay.account.snapshot().positions[asset.symbol].decision_time_ms == decision
    for engine in native.engines.values():
        assert engine.exit(mark_price=100, reason="offline_origin_test").state is SolLiveState.FLAT
    assert len(replay.fill_rows) == 14 and not replay.account.snapshot().positions


def test_native_replay_refuses_existing_output_root(tmp_path: Path) -> None:
    """Research cannot append native-shaped rows into an existing live or prior replay tree."""
    config = load_multi_asset_live_config(
        "configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    replay = cohort_sdk(config, {})
    with pytest.raises(FileExistsError):
        build_native_replay_runner(
            config=config,
            replay=replay,
            fetch_bars=RecordedRunnerFetch(replay.clock),
            output_root=tmp_path,
        )
    assert not replay.orders and not list(tmp_path.iterdir())
