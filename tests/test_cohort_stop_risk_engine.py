"""Real engine and adapter execution of the optional sizing contract, offline."""

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path

import pytest
from native_replay_engine_fixture import EngineReplayFixture

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_stop_risk_sizing import StopRiskBudget
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.sol_range_onset_state import SolLiveState
from hypervector.live.cohort_profile_stage import _toml
from hypervector.research.cohort_configuration_exit_policy import (
    provider_exit_expectation,
    provider_exit_policy_evidence,
)


@pytest.mark.parametrize("side", ["long", "short"])
def test_native_size_is_lot_rounded_below_budget_and_journaled(
    tmp_path: Path, side: str
) -> None:
    replay = EngineReplayFixture(
        tmp_path, partial_entry=False, initial_cash=Decimal(5000)
    )
    symbol = "xyz:SNDK"
    engine = replay.engine(replay.assets[symbol])
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=250,
        target_policy="none",
        maximum_hold_seconds=86400,
        stop_risk_budget=StopRiskBudget(10, 20),
    )
    engine.start()
    replay.prepare_entry(symbol, side, replay.clock.now_ms)
    engine.record_strategy_decision(
        {
            "routing_action": "enter",
            "execution_plan": contract.bind(
                strategy_id="test", stop_anchor=None
            ).as_payload(),
        }
    )
    result = engine.enter(
        side=side, mark_price=100, decision_time_ms=replay.clock.now_ms
    )
    assert result.state is SolLiveState.OPEN
    assert result.stop_oid is not None
    assert result.execution_plan is not None
    assert result.execution_plan.stop_risk_budget == contract.stop_risk_budget
    assert abs(result.position_size_signed) < 4
    ledger = tmp_path / "live/bidirectional_cohort" / f"{symbol}.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    risk_idx = next(
        i for i, r in enumerate(rows) if r["event_type"] == "entry_stop_risk_sizing"
    )
    intent_idx = next(
        i for i, r in enumerate(rows) if r["event_type"] == "order_intent"
    )
    assert risk_idx < intent_idx
    assert rows[risk_idx]["payload"]["estimated_loss_usd"] == pytest.approx(10)
    restored = replay.engine(replay.assets[symbol])
    assert restored.start().execution_plan == result.execution_plan


def test_v91_fingerprint_unchanged_and_risk_budget_changes_identity() -> None:
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_growth_first_5000_adaptive_eight_asset_v91.toml",
        mode="observe",
    )
    assert (
        config.profile_fingerprint
        == "00ca7e008e8b2ec7cbeac4b9541cabf39a8576a23769b92a169e984616fe8d8c"
    )
    first = config.providers[0]
    changed = replace(
        first,
        execution=replace(first.execution, stop_risk_budget=StopRiskBudget(10, 20)),
    )
    assert (
        replace(config, providers=(changed, *config.providers[1:])).profile_fingerprint
        != config.profile_fingerprint
    )


def test_budget_survives_profile_staging_and_checkpoint_projection(
    tmp_path: Path,
) -> None:
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_growth_first_5000_adaptive_eight_asset_v91.toml",
        mode="observe",
    )
    first = config.providers[0]
    changed = replace(
        first,
        execution=replace(first.execution, stop_risk_budget=StopRiskBudget(10, 20)),
    )
    candidate = replace(
        config, providers=(changed, *config.providers[1:]), transition_approval=None
    )
    target = tmp_path / "risk.toml"
    target.write_text(_toml(candidate))
    loaded = load_multi_asset_live_config(target, mode="observe")
    assert loaded.profile_fingerprint == candidate.profile_fingerprint
    evidence = provider_exit_policy_evidence(provider_exit_expectation(loaded))
    assert evidence[first.strategy_id]["stop_risk_budget"] == {
        "maximum_loss_usd": 10,
        "cost_buffer_bps": 20,
    }


def test_proposal_keeps_existing_strategies_and_has_no_live_approval() -> None:
    original = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_growth_first_5000_adaptive_eight_asset_v91.toml",
        mode="observe",
    )
    candidate = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_v92_risk_control_proposal.toml", mode="observe"
    )
    assert not candidate.enabled and not candidate.accepts_live_risk
    assert candidate.transition_approval is None
    assert candidate.maximum_positions == original.maximum_positions == 8
    for proposed, previous in zip(candidate.providers, original.providers, strict=True):
        assert proposed.execution.stop_risk_budget == StopRiskBudget(10, 20)
        assert (
            replace(
                proposed, execution=replace(proposed.execution, stop_risk_budget=None)
            )
            == previous
        )


@pytest.mark.parametrize("side,anchor", [("long", 99.9), ("short", 100.1)])
def test_structural_anchor_inside_slippage_interval_still_enters_and_protects(
    tmp_path: Path, side: str, anchor: float
) -> None:
    """An anchor closer than the entry slippage cap sizes from the adverse bound and opens."""
    replay = EngineReplayFixture(
        tmp_path, partial_entry=False, initial_cash=Decimal(5000)
    )
    symbol = "xyz:SNDK"
    engine = replay.engine(replay.assets[symbol])
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="structural_clamped_bps",
        minimum_stop_bps=20,
        maximum_stop_bps=250,
        target_policy="none",
        maximum_hold_seconds=86400,
        stop_risk_budget=StopRiskBudget(2, 20),
    )
    engine.start()
    replay.prepare_entry(symbol, side, replay.clock.now_ms)
    engine.record_strategy_decision(
        {
            "routing_action": "enter",
            "execution_plan": contract.bind(
                strategy_id="test", stop_anchor=anchor
            ).as_payload(),
        }
    )
    result = engine.enter(
        side=side, mark_price=100, decision_time_ms=replay.clock.now_ms
    )
    assert result.state is SolLiveState.OPEN
    assert result.stop_oid is not None
    ledger = tmp_path / "live/bidirectional_cohort" / f"{symbol}.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    risk = next(r for r in rows if r["event_type"] == "entry_stop_risk_sizing")
    assert risk["payload"]["notional_usd"] < risk["payload"]["original_notional_usd"]
    assert abs(result.position_size_signed) <= risk["payload"]["quantity"] + 1e-9
    assert risk["payload"]["estimated_loss_usd"] == pytest.approx(2)
    assert risk["payload"]["entry_bound"] == pytest.approx(
        100.2 if side == "long" else 99.8
    )
