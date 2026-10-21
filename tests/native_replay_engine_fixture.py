"""Synthetic SDK receipts for native lifecycle qualification, without venue clients.

Prices and fees are prescribed test inputs. Entry-cost collateral allocation is
conditional; partial-close allocation, liquidity and liquidation execution are
outside this fixture. Production engines, adapters, parsers and ledger run intact.
"""

from dataclasses import replace
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from unittest.mock import create_autospec

from hypervector.live.hyperliquid_perp_adapter import HyperliquidPerpAdapter
from hypervector.live.hyperliquid_protocol import (
    HyperliquidExchangeProtocol,
    HyperliquidInfoProtocol,
)
from hypervector.live.multi_asset_directional_adapter import (
    MultiAssetDirectionalAdapter,
)
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_runner_support import shared_account_facts
from hypervector.live.asset_engine import AssetLiveEngine
from hypervector.live.asset_ledger import AssetLiveLedger
from hypervector.research.native_replay_account import ExactFillAccount
from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_events import FillEvent
from hypervector.research.native_replay_unified import (
    IsolatedCollateral,
    MaintenanceTier,
    UnifiedAccountWire,
    project_unified_account,
)
from test_native_replay_adapter import ADDRESS, denied

D = Decimal
SIZE_DECIMALS = {
    "BTC": 5,
    "ETH": 4,
    "SOL": 2,
    "HYPE": 2,
    "xyz:BBB": 2,
    "xyz:CCC": 3,
    "xyz:EEE": 2,
}
FEE_RATE = D("0.0009")
RECEIPT_LATENCY_MS = 500


class EngineReplayFixture:
    """One shared economic account with seven native engine/adapter consumers."""

    def __init__(
        self, root: Path, *, partial_entry: bool, initial_cash: Decimal
    ) -> None:
        """Build inert ports and redirect every native ledger to the pytest directory."""
        self.config = load_multi_asset_live_config(
            "tests/fixtures/profiles/noncrypto_live.toml",
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        )
        self.root, self.partial_entry = root, partial_entry
        self.symbols = tuple(asset.symbol for asset in self.config.assets)
        self.assets = {asset.symbol: asset for asset in self.config.assets}
        self.clock = ReplayClock(1_789_135_200_000)
        self.account = ExactFillAccount(initial_cash, self.symbols)
        self.marks = dict.fromkeys(self.symbols, D(100))
        self.account.mark(
            self.clock.next_stamp(), source_time_ms=self.clock.now_ms, prices=self.marks
        )
        self.orders: dict[int, dict[str, object]] = {}
        self.fills: list[dict[str, object]] = []
        self.collateral: dict[str, IsolatedCollateral] = {}
        self.engines: dict[str, AssetLiveEngine] = {}
        self.adapters: dict[str, MultiAssetDirectionalAdapter] = {}
        self.decisions: dict[str, int] = {}
        self.prices: dict[str, Decimal] = {}
        self.mutations: list[str] = []
        self.entry_requests: list[tuple[str, Decimal]] = []
        self.close_requests: list[dict[str, bool]] = []
        self.cancel_requests: list[dict[str, bool]] = []
        self._oid = 100
        self._info, self._exchange = self._ports()

    def _ports(self) -> tuple[HyperliquidInfoProtocol, HyperliquidExchangeProtocol]:
        info = create_autospec(HyperliquidInfoProtocol, instance=True, spec_set=True)
        exchange = create_autospec(
            HyperliquidExchangeProtocol, instance=True, spec_set=True
        )
        for name in (
            "market_open",
            "market_close",
            "order",
            "cancel",
            "bulk_orders",
            "update_leverage",
            "modify_order",
        ):
            getattr(exchange, name).side_effect = denied
        info.query_user_abstraction_state.return_value = "unifiedAccount"
        info.spot_user_state.side_effect = lambda address: self.wire().spot_state
        info.user_state.side_effect = lambda address, dex: self.wire().perp_states[dex]
        info.frontend_open_orders.side_effect = lambda address, dex: list(
            self.orders.values()
        )
        info.user_fills.side_effect = lambda address: self.fills
        info.meta.side_effect = self._metadata
        info.all_mids.side_effect = lambda dex: {
            symbol: str(mark) for symbol, mark in self.marks.items()
        }
        info.user_fees.return_value = {
            "userAddRate": "0.00015",
            "userCrossRate": str(FEE_RATE),
            "activeReferralDiscount": "0",
        }
        info.perp_dexs.return_value = [None, {"name": "xyz"}]
        info.query_order_by_oid.side_effect = self._query_order
        exchange.update_leverage.side_effect = self._leverage
        exchange.market_open.side_effect = self._open
        exchange.market_close.side_effect = self._close
        exchange.order.side_effect = self._stop
        exchange.cancel.side_effect = self._cancel
        exchange.modify_order.side_effect = self._modify
        return info, exchange

    def _metadata(self, dex: str = "") -> dict[str, object]:
        return {
            "collateralToken": 0,
            "universe": [
                {
                    "name": asset.symbol,
                    "szDecimals": SIZE_DECIMALS[asset.symbol],
                    "maxLeverage": int(asset.venue_max_leverage),
                    "growthMode": "enabled",
                    "deployerFeeScale": "1",
                }
                for asset in self.config.assets
                if ("xyz" if ":" in asset.symbol else "") == dex
            ],
        }

    def wire(self) -> UnifiedAccountWire:
        """Project current explicit marks and conditional collateral at receipt time."""
        view = self.account.snapshot()
        return project_unified_account(
            view,
            symbols=self.symbols,
            marks={symbol: self.marks[symbol] for symbol in view.positions},
            collateral=self.collateral,
            additional_hold_usd=D(0),
            observed_time_ms=self.clock.now_ms,
        )

    def engine(self, asset: AssetLiveConfig) -> AssetLiveEngine:
        """Construct the real engine around fake SDK ports, without its armed factory."""
        config = replace(
            asset,
            live_ledger=self.root
            / "live/bidirectional_cohort"
            / f"{asset.symbol}.jsonl",
        )
        adapter = MultiAssetDirectionalAdapter(
            HyperliquidPerpAdapter(
                info=self._info,
                exchange=self._exchange,
                account_address=ADDRESS,
                max_notional_usd=asset.max_notional_usd,
                slippage_fraction=asset.market_slippage_cap_fraction,
                entry_slippage_fraction=asset.entry_slippage_cap_fraction,
                symbol=asset.symbol,
                perp_dex="xyz" if ":" in asset.symbol else "",
            )
        )
        self.adapters[asset.symbol] = adapter
        ledger = AssetLiveLedger(
            path=config.live_ledger,
            profile_id=config.profile_id,
            profile_fingerprint=config.profile_fingerprint,
            run_fingerprint=config.run_fingerprint,
            run_id="offline-native-account",
        )
        return AssetLiveEngine(
            config=config,
            adapter=adapter,
            ledger=ledger,
            credentials_present=True,
            now_fn=self.clock.now,
            sleep_fn=self.clock.sleep,
        )

    def prepare_entry(self, symbol: str, side: str, decision_time_ms: int) -> None:
        """Prescribe a synthetic executable receipt and its distinct decision clock."""
        self.decisions[symbol] = decision_time_ms
        self.prices[symbol] = D("100.1") if side == "long" else D("99.9")

    def prepare_close(self, symbol: str) -> None:
        """Prescribe a full reduce-only receipt at an unchanged reference price."""
        self.decisions[symbol] = self.clock.now_ms
        self.prices[symbol] = D(100)

    def _leverage(self, leverage: int, name: str, *, is_cross: bool) -> object:
        assert not is_cross and leverage == int(self.assets[name].leverage)
        assert name not in self.account.snapshot().positions
        self.mutations.append("configure")
        return {"status": "ok"}

    def _next_oid(self) -> int:
        self._oid += 1
        return self._oid

    def _open(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        *,
        px: float,
        slippage: float,
        cloid: object,
    ) -> object:
        assert px == 100 and abs(self.prices[name] / D(str(px)) - 1) <= D(str(slippage))
        quantity = D(str(sz))
        self.entry_requests.append((name, quantity))
        if self.partial_entry:
            quantity = (quantity / 2).quantize(
                D(1).scaleb(-SIZE_DECIMALS[name]), rounding=ROUND_DOWN
            )
        return self._fill(name, is_buy, quantity, reduce_only=False, cloid=cloid)

    def _close(
        self, name: str, *, sz: float, px: float, slippage: float, cloid: object
    ) -> object:
        assert px == 100 and abs(self.prices[name] / D(str(px)) - 1) <= D(str(slippage))
        position = self.account.snapshot().positions[name]
        self.close_requests.append(
            {
                "stop_present": any(
                    order["coin"] == name for order in self.orders.values()
                )
            }
        )
        return self._fill(
            name,
            position.quantity_signed < 0,
            D(str(sz)),
            reduce_only=True,
            cloid=cloid,
        )

    def _fill(
        self,
        name: str,
        is_buy: bool,
        quantity: Decimal,
        *,
        reduce_only: bool,
        cloid: object,
    ) -> object:
        oid, dispatch = self._next_oid(), self.clock.now_ms
        self.clock.advance_to(dispatch + RECEIPT_LATENCY_MS)
        price = self.prices[name]
        self.marks[name] = price
        self.account.mark(
            self.clock.next_stamp(),
            source_time_ms=self.clock.now_ms,
            prices={name: price},
        )
        before = self.account.snapshot()
        fee = quantity * price * FEE_RATE
        event = FillEvent(
            str(oid),
            str(oid),
            name,
            "buy" if is_buy else "sell",
            quantity,
            price,
            fee,
            D(str(self.assets[name].leverage)),
            self.decisions[name],
            dispatch,
            self.clock.now_ms,
            self.clock.next_stamp(),
            reduce_only,
        )
        self.account.apply_fill(event)
        after = self.account.snapshot()
        if reduce_only:
            assert name not in after.positions, "this fixture requires a full close"
            del self.collateral[name]
        else:
            initial = after.positions[name].allocated_initial_margin_usd
            rate = D("0.5") / D(str(self.assets[name].venue_max_leverage))
            self.collateral[name] = IsolatedCollateral(
                initial - fee, (MaintenanceTier(D(0), rate, D(0)),)
            )
        self._record_fill(
            event, after.realized_gross_usd - before.realized_gross_usd, cloid
        )
        self.mutations.append("close" if reduce_only else "entry")
        return self._ack(
            {"filled": {"oid": oid, "totalSz": str(quantity), "avgPx": str(price)}}
        )

    def _record_fill(self, event: FillEvent, gross: Decimal, cloid: object) -> None:
        is_buy, reduce_only = event.side == "buy", event.reduce_only
        side = "Long" if (is_buy != reduce_only) else "Short"
        oid = int(event.order_id)
        self.fills.append(
            {
                "coin": event.symbol,
                "oid": oid,
                "tid": oid,
                "px": str(event.price),
                "sz": str(event.quantity),
                "side": "B" if is_buy else "A",
                "time": event.fill_time_ms,
                "fee": str(event.fee_usd),
                "feeToken": "USDC",
                "closedPnl": str(gross),
                "crossed": True,
                "dir": f"{'Close' if reduce_only else 'Open'} {side}",
                "hash": f"0x{oid:064x}",
                "cloid": str(cloid),
            }
        )

    def _stop(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        *,
        order_type: object,
        reduce_only: bool,
        cloid: object,
    ) -> object:
        assert reduce_only
        trigger = "trigger" in order_type
        if trigger:
            assert order_type["trigger"]["isMarket"]
        else:
            assert order_type == {"limit": {"tif": "Alo"}}
        oid = self._next_oid()
        self.orders[oid] = {
            "coin": name,
            "oid": oid,
            "sz": str(sz),
            "origSz": str(sz),
            "side": "B" if is_buy else "A",
            "reduceOnly": True,
            "isTrigger": trigger,
            "triggerPx": str(order_type["trigger"]["triggerPx"]) if trigger else None,
            "orderType": "Stop Market" if trigger else "Limit",
            "timestamp": self.clock.now_ms,
            "limitPx": str(limit_px),
            "cloid": str(cloid),
        }
        self.mutations.append("stop" if trigger else "target")
        return self._ack({"resting": {"oid": oid}})

    def _query_order(self, user: str, identity: object) -> object:
        for order in self.orders.values():
            if order["oid"] == identity or order.get("cloid") == identity:
                return {
                    "status": "order",
                    "order": {
                        "order": dict(order),
                        "status": "open",
                        "statusTimestamp": self.clock.now_ms,
                    },
                }
        return {"status": "unknownOid"}

    def _modify(
        self,
        oid: int,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: object,
        reduce_only: bool = False,
        cloid: object | None = None,
    ) -> object:
        assert reduce_only and "trigger" in order_type
        previous = self.orders.get(oid)
        if previous is None or previous["coin"] != name:
            return self._ack({"error": "Order not found"})
        del self.orders[oid]
        new_oid = self._next_oid()
        self.orders[new_oid] = {
            **previous,
            "oid": new_oid,
            "sz": str(sz),
            "origSz": str(sz),
            "side": "B" if is_buy else "A",
            "triggerPx": str(order_type["trigger"]["triggerPx"]),
            "limitPx": str(limit_px),
            "timestamp": self.clock.now_ms,
            "cloid": str(cloid),
        }
        self.mutations.append("modify")
        return self._ack({"resting": {"oid": new_oid}})

    def _cancel(self, name: str, oid: int) -> object:
        assert self.orders[oid]["coin"] == name
        self.cancel_requests.append(
            {
                "flat_before_cancel": name not in self.account.snapshot().positions,
                "is_stop": self.orders[oid]["isTrigger"],
            }
        )
        del self.orders[oid]
        self.mutations.append("cancel")
        return self._ack("success")

    @staticmethod
    def _ack(status: object) -> dict[str, object]:
        return {
            "status": "ok",
            "response": {"type": "order", "data": {"statuses": [status]}},
        }

    def assert_native_account_agreement(self) -> None:
        """Require native reconciliation and namespace aggregation to match exact economics."""
        venues = tuple(self.adapters[symbol].reconcile() for symbol in self.adapters)
        facts = shared_account_facts(tuple(self.adapters), venues)
        view = self.account.snapshot()
        assert abs(D(str(facts.account_value_usd)) - view.equity_usd) < D("1e-10")
        assert abs(
            D(str(facts.total_notional_position_usd)) - view.gross_notional_usd
        ) < D("1e-10")
