"""Execution-incapable multi-asset venue and sizing preflight tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.hyperliquid_protocol import (
    HyperliquidFeeSchedule,
    Hip3MarketFeeMetadata,
    SolBookLevel,
    SolBookSnapshot,
    SolMarketMetadata,
    SolOpenOrder,
    SolPositionSnapshot,
    SolVenuePreflight,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_read_only_preflight import (
    AssetLedgerExpectation,
    collect_multi_asset_read_only_preflight,
)
from hypervector.live.multi_asset_retired_transition import (
    apply_retired_asset_reports,
    collect_retired_asset_report,
)

_PROFILE = Path("configs/multi_asset_bidirectional_growth_5000_candidate_v37.toml")
_NOW = datetime(2026, 8, 10, 22, 0, tzinfo=UTC)


def _position(size: float = 0.0) -> SolPositionSnapshot:
    return SolPositionSnapshot(
        size_signed=size,
        entry_price=4362.0 if size else None,
        liquidation_price=3564.0 if size else None,
        margin_used_usd=15.0 if size else 0.0,
        position_value_usd=75.0 if size else 0.0,
        unrealized_pnl_usd=0.6 if size else 0.0,
        leverage_type="isolated" if size else None,
        leverage=5 if size else None,
    )


def _stop(oid: int = 91, size: float = 0.0171) -> SolOpenOrder:
    return SolOpenOrder(
        oid=oid,
        size=size,
        original_size=size,
        side="A",
        reduce_only=True,
        is_trigger=True,
        trigger_price=90.0,
        order_type="Stop Market",
        timestamp_ms=1_786_379_426_694,
        limit_price=90.0,
    )


class FakeReader:
    """Return deterministic public venue facts for one configured asset."""

    def __init__(
        self,
        symbol: str,
        max_leverage: int,
        *,
        size: float = 0.0,
        orders: tuple[SolOpenOrder, ...] = (),
        depth_size: float = 10.0,
        growth_mode: bool | None = True,
    ) -> None:
        self.symbol = symbol
        self.growth_mode = growth_mode
        self.position = _position(size)
        self.orders = orders
        self.preflight_value = SolVenuePreflight(
            market=SolMarketMetadata(symbol, 4, max_leverage),
            mark_price=100.0,
            price_tick=0.01,
            size_step=0.0001,
            fees=HyperliquidFeeSchedule(0.00015, 0.00045, 0.04),
            account_value_usd=500.0,
            withdrawable_usd=485.0,
            position=self.position,
            account_abstraction_mode="unifiedAccount",
        )
        bids = (
            SolBookLevel(99.9, depth_size, 2),
            SolBookLevel(99.8, depth_size, 2),
        )
        asks = (
            SolBookLevel(100.1, depth_size, 2),
            SolBookLevel(100.2, depth_size, 2),
        )
        self.book = SolBookSnapshot(
            1_786_380_000_000,
            bids,
            asks,
            100.0,
            20.0,
            depth_size * 2,
            depth_size * 2,
            0.0,
        )

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        assert expected_max_leverage == self.preflight_value.market.max_leverage
        return self.preflight_value

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        assert depth_levels == 20
        return self.book

    def open_orders(self) -> tuple[SolOpenOrder, ...]:
        return self.orders

    def hip3_fee_metadata(self) -> Hip3MarketFeeMetadata:
        """Return deterministic official HIP-3 market modifiers."""
        if ":" not in self.symbol:
            raise AssertionError("core assets must not request HIP-3 fee metadata")
        return Hip3MarketFeeMetadata(
            deployer_fee_scale=1.0,
            growth_mode=self.growth_mode,
            collateral_token_index=0,
        )


def _readers(
    *,
    sndk_depth_size: float = 10.0,
) -> dict[str, FakeReader]:
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    return {
        asset.symbol: FakeReader(
            asset.symbol,
            int(asset.venue_max_leverage),
            depth_size=(sndk_depth_size if asset.symbol == "xyz:SNDK" else 10.0),
        )
        for asset in config.assets
    }


def _expectations() -> dict[str, AssetLedgerExpectation]:
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    return {
        asset.symbol: AssetLedgerExpectation(
            position_size_signed=0.0,
            owned_order_ids=frozenset(),
        )
        for asset in config.assets
    }


def test_flat_report_proves_percentage_sizing_depth_and_no_authority() -> None:
    """A flat $500 account derives $75 slots without constructing execution."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")

    report = collect_multi_asset_read_only_preflight(
        config=config,
        readers=_readers(),
        ledger_expectations=_expectations(),
        active_profile_id="multi_asset_bidirectional_all_live_canary_v35",
        active_profile_fingerprint="a" * 64,
        observed_at=_NOW,
    )

    assert report["authority"] == {
        "execution_authority": "none",
        "execution_client_constructed": False,
        "signing_key_required": False,
        "operation": "multi_asset_read_only_preflight",
    }
    portfolio = report["portfolio"]
    assert portfolio["flat_no_orders"] is True
    assert portfolio["ledger_reconciled"] is True
    assert portfolio["sizing_technically_ready"] is True
    assert portfolio["technically_ready_for_profile_transition"] is True
    assert portfolio["configured_assets"] == 8
    assert portfolio["maximum_positions"] == 10
    assert portfolio["maximum_configured_margin_fraction"] == pytest.approx(0.24)
    btc = report["assets"][0]
    assert btc["symbol"] == "BTC"
    assert btc["sizing"]["planned_margin_usd"] == pytest.approx(15.0)
    assert btc["sizing"]["planned_notional_usd"] == pytest.approx(75.0)
    assert btc["visible_depth"]["buy_complete"] is True
    assert btc["visible_depth"]["sell_complete"] is True
    assert btc["venue"]["effective_fee_status"] == "resolved_core_after_referral"
    assert btc["venue"]["account_base_taker_fee_rate"] == pytest.approx(0.00045)
    assert btc["venue"]["active_referral_discount"] == pytest.approx(0.04)
    assert btc["venue"]["effective_taker_fee_rate"] == pytest.approx(0.000432)
    assert btc["venue"]["one_way_taker_fee_bps"] == pytest.approx(4.32)
    sndk = next(asset for asset in report["assets"] if asset["symbol"] == "xyz:SNDK")
    assert sndk["venue"]["effective_fee_status"] == "resolved_hip3"
    assert sndk["venue"]["effective_taker_fee_rate"] == pytest.approx(0.0000864)
    assert sndk["venue"]["one_way_taker_fee_bps"] == pytest.approx(0.864)


def test_open_gold_with_exact_full_stop_reconciles_but_blocks_transition() -> None:
    """Protected exposure is honest current state, not a flat transition boundary."""
    report = collect_multi_asset_read_only_preflight(
        config=load_multi_asset_live_config(_PROFILE, mode="observe"),
        readers=_readers(),
        ledger_expectations=_expectations(),
        active_profile_id="multi_asset_bidirectional_all_live_canary_v35",
        active_profile_fingerprint="a" * 64,
        observed_at=_NOW,
    )

    active = load_multi_asset_live_config(
        Path("configs/multi_asset_bidirectional_all_live_canary_v35.toml"),
        mode="observe",
    )
    gold = next(asset for asset in active.assets if asset.symbol == "xyz:GOLD")
    retired = collect_retired_asset_report(
        gold,
        FakeReader("xyz:GOLD", 25, size=0.0171, orders=(_stop(),)),
        AssetLedgerExpectation(0.0171, frozenset({91})),
    )
    report = apply_retired_asset_reports(report, (retired,))

    assert report["retired_assets"][0]["position_size_signed"] == pytest.approx(0.0171)
    assert report["retired_assets"][0]["ledger_reconciled"] is True
    assert report["portfolio"]["ledger_reconciled"] is True
    assert report["portfolio"]["flat_no_orders"] is False
    assert report["portfolio"]["technically_ready_for_profile_transition"] is False
    assert report["portfolio"]["transition_blocking_assets"] == ("xyz:GOLD",)


def test_explicit_five_thousand_scenario_walks_seven_hundred_fifty_notional() -> None:
    """Target-equity sizing is visible-depth analysis, not a balance gate."""
    report = collect_multi_asset_read_only_preflight(
        config=load_multi_asset_live_config(_PROFILE, mode="observe"),
        readers=_readers(),
        ledger_expectations=_expectations(),
        active_profile_id="multi_asset_bidirectional_all_live_canary_v35",
        active_profile_fingerprint="a" * 64,
        observed_at=_NOW,
        sizing_reference_equity_usd=5_000.0,
    )

    btc = report["assets"][0]
    assert btc["sizing"]["actual_account_value_usd"] == pytest.approx(500.0)
    assert btc["sizing"]["sizing_reference_equity_usd"] == pytest.approx(5_000.0)
    assert btc["sizing"]["planned_margin_usd"] == pytest.approx(150.0)
    assert btc["sizing"]["planned_notional_usd"] == pytest.approx(750.0)
    assert report["portfolio"]["sizing_reference_equity_usd"] == pytest.approx(5_000.0)
    assert report["portfolio"]["sizing_reference_source"] == "explicit_scenario"
    assert report["portfolio"]["balance_gate"] is False


def test_incomplete_candidate_depth_is_a_technical_sizing_failure() -> None:
    """Finite visible books cannot success-shape an unfillable planned notional."""
    report = collect_multi_asset_read_only_preflight(
        config=load_multi_asset_live_config(_PROFILE, mode="observe"),
        readers=_readers(sndk_depth_size=0.1),
        ledger_expectations=_expectations(),
        active_profile_id="multi_asset_bidirectional_all_live_canary_v35",
        active_profile_fingerprint="a" * 64,
        observed_at=_NOW,
    )

    sndk = next(asset for asset in report["assets"] if asset["symbol"] == "xyz:SNDK")
    assert sndk["visible_depth"]["buy_complete"] is False
    assert sndk["visible_depth"]["sell_complete"] is False
    assert report["portfolio"]["sizing_technically_ready"] is False
    assert report["portfolio"]["technically_ready_for_profile_transition"] is False


def test_unresolved_hip3_growth_mode_fails_fee_readiness_without_hiding_asset() -> None:
    """Unknown HIP-3 fee scaling remains visible and blocks technical sizing."""
    readers = _readers()
    sndk = readers["xyz:SNDK"]
    sndk.growth_mode = None

    report = collect_multi_asset_read_only_preflight(
        config=load_multi_asset_live_config(_PROFILE, mode="observe"),
        readers=readers,
        ledger_expectations=_expectations(),
        active_profile_id="multi_asset_bidirectional_all_live_canary_v35",
        active_profile_fingerprint="a" * 64,
        observed_at=_NOW,
    )

    sndk_report = next(
        asset for asset in report["assets"] if asset["symbol"] == "xyz:SNDK"
    )
    assert sndk_report["venue"]["effective_fee_status"] == "unresolved_growth_mode"
    assert sndk_report["venue"]["effective_taker_fee_rate"] is None
    assert sndk_report["sizing_technically_ready"] is False
    assert report["portfolio"]["sizing_technically_ready"] is False
    assert "effective fee" in report["portfolio"]["readiness_reasons"][-1]


def test_exact_reader_and_ledger_coverage_is_required() -> None:
    """Missing one configured asset must abort rather than disappear from the report."""
    readers = _readers()
    readers.pop("ETH")

    with pytest.raises(ValueError, match="reader coverage"):
        collect_multi_asset_read_only_preflight(
            config=load_multi_asset_live_config(_PROFILE, mode="observe"),
            readers=readers,
            ledger_expectations=_expectations(),
            active_profile_id="multi_asset_bidirectional_all_live_canary_v35",
            active_profile_fingerprint="a" * 64,
            observed_at=_NOW,
        )


def test_naive_observation_time_is_rejected() -> None:
    """Every venue snapshot must carry an unambiguous UTC observation time."""
    with pytest.raises(ValueError, match="timezone-aware"):
        collect_multi_asset_read_only_preflight(
            config=load_multi_asset_live_config(_PROFILE, mode="observe"),
            readers=_readers(),
            ledger_expectations=_expectations(),
            active_profile_id="multi_asset_bidirectional_all_live_canary_v35",
            active_profile_fingerprint="a" * 64,
            observed_at=datetime(2026, 8, 10, 22, 0),
        )
