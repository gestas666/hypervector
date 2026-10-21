"""Real engine execution of equity-fraction stop budgets and their refusal, offline."""

from decimal import Decimal
import json
from pathlib import Path

import pytest
from native_replay_engine_fixture import EngineReplayFixture

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_stop_risk_sizing import StopRiskBudget
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_execution_plan import entry_notional
from hypervector.live.sol_range_onset_state import SolLiveState

SYMBOL = "xyz:CCC"


def _engine(tmp_path: Path, budget: StopRiskBudget, side: str = "long"):
    replay = EngineReplayFixture(
        tmp_path, partial_entry=False, initial_cash=Decimal(5000)
    )
    engine = replay.engine(replay.assets[SYMBOL])
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=250,
        target_policy="none",
        maximum_hold_seconds=86400,
        stop_risk_budget=budget,
    )
    engine.start()
    replay.prepare_entry(SYMBOL, side, replay.clock.now_ms)
    engine.record_strategy_decision(
        {
            "routing_action": "enter",
            "execution_plan": contract.bind(
                strategy_id="test", stop_anchor=None
            ).as_payload(),
        }
    )
    return replay, engine


def _rows(tmp_path: Path) -> list[dict[str, object]]:
    ledger = tmp_path / "live/bidirectional_cohort" / f"{SYMBOL}.jsonl"
    return [json.loads(line) for line in ledger.read_text().splitlines()]


@pytest.mark.parametrize("side", ["long", "short"])
def test_fraction_budget_sizes_from_the_entry_account_value_and_journals_it(
    tmp_path: Path, side: str
) -> None:
    replay, engine = _engine(tmp_path, StopRiskBudget(100, 20, 0.002), side)
    result = engine.enter(
        side=side, mark_price=100, decision_time_ms=replay.clock.now_ms
    )
    assert result.state is SolLiveState.OPEN and result.stop_oid is not None
    rows = _rows(tmp_path)
    risk = next(r for r in rows if r["event_type"] == "entry_stop_risk_sizing")
    payload = risk["payload"]
    account = payload["account_value_usd"]
    assert 4000 < account <= 5000
    assert payload["maximum_loss_fraction_of_equity"] == 0.002
    assert payload["maximum_loss_usd"] == 100.0
    assert payload["effective_maximum_loss_usd"] == pytest.approx(0.002 * account)
    assert payload["estimated_loss_usd"] == pytest.approx(0.002 * account)
    intent = next(
        r
        for r in rows
        if r["event_type"] == "order_intent" and r["payload"]["operation"] == "entry"
    )
    assert rows.index(risk) < rows.index(intent)
    restored = replay.engine(replay.assets[SYMBOL])
    assert restored.start().execution_plan == result.execution_plan


@pytest.mark.parametrize("account", [0.0, -5.0, float("nan"), float("inf")])
def test_fraction_budget_refuses_an_unusable_account_value_with_a_journaled_fault(
    tmp_path: Path, account: float
) -> None:
    replay, engine = _engine(tmp_path, StopRiskBudget(None, 20, 0.006))
    with pytest.raises(SolLiveEngineError, match="account value"):
        engine._enter_with_protection(
            side="long",
            mark_price=100,
            notional=500.0,
            decision_time_ms=replay.clock.now_ms,
            account_value_usd=account,
        )
    rows = _rows(tmp_path)
    faults = [r for r in rows if r["event_type"] == "fault"]
    assert faults and "account value" in faults[-1]["payload"]["reason"]
    assert not any(r["event_type"] == "entry_stop_risk_sizing" for r in rows)
    assert not any(
        r["event_type"] == "order_intent" and r["payload"]["operation"] == "entry"
        for r in rows
    )
    assert replay.entry_requests == []


@pytest.mark.parametrize("account", [float("nan"), float("inf")])
def test_non_finite_live_account_value_is_a_journaled_entry_refusal(
    account: float,
) -> None:
    class _Config:
        margin_fraction = 0.1
        max_notional_usd = 1000.0
        leverage = 5.0

    reasons: list[str] = []
    with pytest.raises(SolLiveEngineError, match="finite"):
        entry_notional(_Config(), account, fault=reasons.append)  # type: ignore[arg-type]
    assert reasons == ["live account value must be finite and positive"]
