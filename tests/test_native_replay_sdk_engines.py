"""Seven actual execution engines around reusable offline SDK ports and one account."""

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from native_replay_engine_fixture import SIZE_DECIMALS
from test_native_replay_adapter import ADDRESS, deny_external_ports

from hypervector.live.hyperliquid_perp_adapter import HyperliquidPerpAdapter
from hypervector.live.multi_asset_directional_adapter import MultiAssetDirectionalAdapter
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_runner_support import shared_account_facts
from hypervector.live.asset_engine import AssetLiveEngine
from hypervector.live.asset_ledger import AssetLiveLedger
from hypervector.live.asset_state import AssetLiveState
from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_depth import ExactLevel, RecordedBook
from hypervector.research.native_replay_sdk import ReplaySdk, ReplaySdkTiming
from hypervector.research.native_replay_unified import MaintenanceTier

__all__ = ["deny_external_ports"]
D = Decimal


def cohort_sdk(config: MultiAssetLiveConfig, decisions: dict[str, int]) -> ReplaySdk:
    """Provide explicit synthetic metadata, prices, timing and native decision origins."""
    clock = ReplayClock(1_789_135_200_000)
    metadata = {
        dex: {
            "collateralToken": 0,
            "universe": [
                {
                    "name": a.symbol,
                    "szDecimals": SIZE_DECIMALS[a.symbol],
                    "maxLeverage": int(a.venue_max_leverage),
                    "growthMode": "enabled",
                    "deployerFeeScale": "1",
                }
                for a in config.assets
                if ("xyz" if ":" in a.symbol else "") == dex
            ],
        }
        for dex in ("", "xyz")
    }
    replay = ReplaySdk(
        clock=clock,
        initial_cash=D(5000),
        symbols=config.symbols,
        metadata_by_dex=metadata,
        dexes=[None, {"name": "xyz"}],
        fees={"userAddRate": ".00015", "userCrossRate": ".0009", "activeReferralDiscount": "0"},
        maintenance={
            a.symbol: (MaintenanceTier(D(0), D(".5") / D(str(a.venue_max_leverage)), D(0)),)
            for a in config.assets
        },
        execution_book=source_book,
        timing=ReplaySdkTiming(100, 200, 300, 400, 50),
        decision_time=lambda symbol, reduce: clock.now_ms if reduce else decisions[symbol],
    )
    for symbol in config.symbols:
        replay.observe_prices(symbol, source_time_ms=clock.now_ms, mark=D(100), mid=D(100))
        replay.observe_book(
            symbol,
            {
                "coin": symbol,
                "time": clock.now_ms,
                "levels": [
                    [{"px": "99.99", "sz": "100", "n": 2}],
                    [{"px": "100.01", "sz": "100", "n": 3}],
                ],
            },
        )
    return replay


def source_book(symbol: str, arrival_ms: int, step: Decimal) -> RecordedBook:
    """Declare finite depth inside the actual configured entry-price caps."""
    return RecordedBook(
        f"synthetic:{symbol}:{arrival_ms}",
        symbol,
        arrival_ms,
        step,
        (ExactLevel(D("99.99"), D(100)),),
        (ExactLevel(D("100.01"), D(100)),),
    )


def engine(replay: ReplaySdk, asset: AssetLiveConfig, root: Path) -> AssetLiveEngine:
    """Construct the real execution engine with isolated ledgers and offline clocks."""
    asset = replace(asset, live_ledger=root / "live/bidirectional_cohort" / f"{asset.symbol}.jsonl")
    adapter = MultiAssetDirectionalAdapter(
        HyperliquidPerpAdapter(
            info=replay.info,
            exchange=replay.exchange,
            account_address=ADDRESS,
            max_notional_usd=asset.max_notional_usd,
            slippage_fraction=asset.market_slippage_cap_fraction,
            entry_slippage_fraction=asset.entry_slippage_cap_fraction,
            symbol=asset.symbol,
            perp_dex="xyz" if ":" in asset.symbol else "",
        )
    )
    ledger = AssetLiveLedger(
        path=asset.live_ledger,
        profile_id=asset.profile_id,
        profile_fingerprint=asset.profile_fingerprint,
        run_fingerprint=asset.run_fingerprint,
        run_id="offline-sdk-native-engines",
    )
    return AssetLiveEngine(
        config=asset,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=replay.clock.now,
        sleep_fn=replay.clock.sleep,
    )


@pytest.mark.parametrize("last_sides", [False, True])
def test_all_configured_assets_complete_native_engine_lifecycles_with_shared_sdk(
    tmp_path: Path,
    last_sides: bool,
) -> None:
    """Configured plans preserve decision clocks, protection and funded account identity."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/noncrypto_live.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    decisions: dict[str, int] = {}
    replay = cohort_sdk(config, decisions)
    engines = {
        asset.symbol: _enter_configured(replay, config, asset, tmp_path, last_sides, decisions)
        for asset in config.assets
    }
    assert len(replay.account.snapshot().positions) == 7
    for symbol in config.symbols:
        replay.settle_funding(
            f"hour:{symbol}",
            symbol,
            rate=D(".0001"),
            oracle_price=D(101),
            effective_time_ms=replay.clock.now_ms,
            visible_delay_ms=0,
        )
    _assert_shared_account(replay, engines)
    for asset in reversed(config.assets):
        restored = engine(replay, asset, tmp_path)
        assert restored.start().state is AssetLiveState.OPEN
        assert restored.snapshot.opened_at_ms == decisions[asset.symbol]
        assert (
            restored.exit(mark_price=100, reason="offline_sdk_qualification").state
            is AssetLiveState.FLAT
        )
        engines[asset.symbol] = restored
        _assert_shared_account(replay, engines)
    assert not replay.account.snapshot().positions
    _assert_fraction_receipts(replay)


def _enter_configured(
    replay: ReplaySdk,
    config: MultiAssetLiveConfig,
    asset: AssetLiveConfig,
    root: Path,
    last_sides: bool,
    decisions: dict[str, int],
) -> AssetLiveEngine:
    """Preserve a configured provider's exact decision, plan and sizing through the real engine."""
    machine = engine(replay, asset, root)
    assert machine.start().state is AssetLiveState.FLAT
    provider = next(p for p in config.providers if asset.symbol in p.execution_symbols)
    side = sorted(provider.executable_sides(asset.symbol))[-1 if last_sides else 0]
    decisions[asset.symbol] = replay.clock.now_ms - 1000
    plan = provider.execution_for(asset.symbol, side).bind(
        strategy_id=provider.strategy_id, stop_anchor=98 if side == "long" else 102
    )
    machine.record_strategy_decision(
        {"execution_plan": plan.as_payload(), "decision_time_ms": decisions[asset.symbol]}
    )
    opened = machine.enter(
        side=side,
        mark_price=100,
        decision_time_ms=decisions[asset.symbol],
        entry_sizing=provider.entry_sizing(asset.symbol, side),
    )
    assert opened.state is AssetLiveState.OPEN and opened.opened_at_ms == decisions[asset.symbol]
    assert (
        replay.account.snapshot().positions[asset.symbol].decision_time_ms
        == decisions[asset.symbol]
    )
    return machine


def _assert_shared_account(replay: ReplaySdk, engines: dict[str, AssetLiveEngine]) -> None:
    snapshots = tuple(machine._adapter.reconcile() for machine in engines.values())
    facts = shared_account_facts(tuple(engines), snapshots)
    assert facts.account_value_usd == pytest.approx(float(replay.account.snapshot().equity_usd))
    assert facts.total_notional_position_usd == pytest.approx(
        float(replay.account.snapshot().gross_notional_usd)
    )


def _assert_fraction_receipts(replay: ReplaySdk) -> None:
    gross = fees = funding = Fraction(0)
    for symbol in replay.symbols:
        opening, closing = [row for _, row in replay.fill_rows if row["coin"] == symbol]
        quantity = Fraction(opening["sz"])
        assert quantity == Fraction(closing["sz"])
        direction = 1 if opening["side"] == "B" else -1
        trade_gross = direction * quantity * (Fraction(closing["px"]) - Fraction(opening["px"]))
        assert Fraction(closing["closedPnl"]) == trade_gross
        gross += trade_gross
        for row in (opening, closing):
            fee = (
                Fraction(row["sz"])
                * Fraction(row["px"])
                * Fraction(replay.markets[symbol].taker_rate)
            )
            assert Fraction(row["fee"]) == fee
            fees += fee
        funding -= direction * quantity * Fraction(101, 10000)
    view = replay.account.snapshot()
    assert Fraction(view.funding_usd) == funding
    assert Fraction(view.equity_usd) == Fraction(5000) + gross - fees + funding
