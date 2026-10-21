"""Native engine lifecycles share exact cash through strictly offline SDK ports."""

from decimal import Decimal, ROUND_DOWN
from fractions import Fraction
from pathlib import Path

import pytest

from hypervector.live.asset_state import AssetLiveState
from hypervector.live.multi_asset_live_config import AssetLiveConfig
from native_replay_engine_fixture import EngineReplayFixture, SIZE_DECIMALS
from test_native_replay_adapter import deny_external_ports as deny_external_ports


@pytest.mark.parametrize("last_side", [False, True])
@pytest.mark.parametrize("partial_entry", [False, True])
@pytest.mark.parametrize("initial_cash", [Decimal(500), Decimal(5000)])
def test_seven_native_engines_size_protect_restart_and_close_shared_cash(
    tmp_path: Path,
    last_side: bool,
    partial_entry: bool,
    initial_cash: Decimal,
) -> None:
    """Exercise current configured provider scopes with synthetic full/partial receipts."""
    replay = EngineReplayFixture(tmp_path, partial_entry=partial_entry, initial_cash=initial_cash)
    decisions = {asset.symbol: _open_verified(replay, asset, last_side) for asset in replay.config.assets}
    assert len(replay.account.snapshot().positions) == 7
    replay.assert_native_account_agreement()
    for asset in reversed(replay.config.assets):
        symbol = asset.symbol
        restarted = replay.engine(asset)
        mutations = len(replay.mutations)
        assert restarted.start().state is AssetLiveState.OPEN
        assert restarted.snapshot.opened_at_ms == decisions[symbol]
        assert len(replay.mutations) == mutations
        replay.prepare_close(symbol)
        assert (
            restarted.exit(mark_price=100, reason="synthetic_account_bridge_check").state is AssetLiveState.FLAT
        )
        assert symbol not in replay.account.snapshot().positions
        replay.assert_native_account_agreement()
    assert not replay.orders
    _independent_fill_cash(replay, initial_cash)
    assert len(replay.fills) == 14
    assert all(close["stop_present"] for close in replay.close_requests)
    assert all(value["flat_before_cancel"] for value in replay.cancel_requests if value["is_stop"])


def _independent_fill_cash(replay: EngineReplayFixture, initial_cash: Decimal) -> None:
    """Recompute price PnL independently instead of trusting account-authored closedPnl."""
    gross = Fraction(0)
    for symbol in replay.symbols:
        entry, close = [fill for fill in replay.fills if fill["coin"] == symbol]
        quantity = Fraction(entry["sz"])
        assert quantity == Fraction(close["sz"])
        direction = 1 if entry["side"] == "B" else -1
        realized = direction * quantity * (Fraction(close["px"]) - Fraction(entry["px"]))
        assert Fraction(close["closedPnl"]) == realized
        gross += realized
    fees = Fraction(0)
    for fill in replay.fills:
        fee = Fraction(fill["sz"]) * Fraction(fill["px"]) * Fraction(9, 10000)
        assert Fraction(fill["fee"]) == fee
        fees += fee
    assert Fraction(replay.account.snapshot().equity_usd) == Fraction(initial_cash) + gross - fees


def _open_verified(replay: EngineReplayFixture, asset: AssetLiveConfig, last_side: bool) -> int:
    """Verify one current provider contract through the native protected-entry path."""
    symbol = asset.symbol
    provider = next(p for p in replay.config.providers if symbol in p.execution_symbols)
    sides = sorted(provider.executable_sides(symbol))
    side = sides[-1] if last_side else sides[0]
    engine = replay.engine(asset)
    assert engine.start().state is AssetLiveState.FLAT
    decision = replay.clock.now_ms
    replay.prepare_entry(symbol, side, decision)
    stop = 98.0 if side == "long" else 102.0
    plan = provider.execution_for(symbol, side).bind(strategy_id=provider.strategy_id, stop_anchor=stop)
    engine.record_strategy_decision({"execution_plan": plan.as_payload(), "decision_time_ms": decision})
    before = replay.account.snapshot()
    sizing = provider.entry_sizing(symbol, side)
    result = engine.enter(side=side, mark_price=100, decision_time_ms=decision, entry_sizing=sizing)
    assert result.state is AssetLiveState.OPEN
    assert result.opened_at_ms == decision
    assert result.execution_plan == plan
    position = replay.account.snapshot().positions[symbol]
    assert position.first_fill_time_ms > decision
    policy_margin = sizing.margin_fraction if sizing is not None else asset.margin_fraction
    policy_cap = sizing.max_notional_usd if sizing is not None else asset.max_notional_usd
    expected = min(float(before.equity_usd) * policy_margin * asset.leverage, policy_cap)
    quantity = Decimal(str(expected / 100)).quantize(
        Decimal(1).scaleb(-SIZE_DECIMALS[symbol]), rounding=ROUND_DOWN
    )
    assert replay.entry_requests[-1][1] == quantity
    stop_order = replay.orders[result.stop_oid]
    assert Decimal(stop_order["sz"]) == abs(position.quantity_signed)
    assert stop_order["reduceOnly"] is True and stop_order["isTrigger"] is True
    replay.engines[symbol] = engine
    return decision
