"""Read-only native SDK surface backed exclusively by an explicit replay account."""

from copy import deepcopy
from typing import TYPE_CHECKING

from hypervector.research.native_replay_book_source import RecordedBookUnavailable
from hypervector.research.native_replay_events import require_clock

if TYPE_CHECKING:
    from hypervector.research.native_replay_sdk import ReplaySdk


class ReplaySdkInfo:
    """Implement native Info readers without HTTP clients, credentials or fallback feeds."""

    def __init__(self, replay: "ReplaySdk") -> None:
        """Bind every reader to the same in-memory scenario and shared account."""
        self.replay = replay
        self.name_to_coin = {symbol: symbol for symbol in replay.symbols}
        self.coin_to_asset = {
            symbol: index + (110000 if ":" in symbol else 0)
            for index, symbol in enumerate(replay.symbols)
        }
        self.asset_to_sz_decimals = {
            self.coin_to_asset[symbol]: market.metadata.size_decimals
            for symbol, market in replay.markets.items()
        }

    def meta(self, dex: str = "") -> object:
        """Return the declared namespace metadata without sharing mutable input objects."""
        return deepcopy(self.replay.metadata_by_dex[dex])

    def perp_dexs(self) -> object:
        """Return the declared HIP-3 deployer metadata."""
        return deepcopy(self.replay.dexes)

    def user_fees(self, address: str) -> object:
        """Return the scenario's account fee terms used by native preflight."""
        return deepcopy(self.replay.fees)

    def all_mids(self, dex: str = "") -> object:
        """Expose only explicitly observed midpoint prices in the requested namespace."""
        symbols = [s for s, market in self.replay.markets.items() if market.perp_dex == dex]
        return {s: str(self.replay.mid_prices[s]) for s in symbols if s in self.replay.mid_prices}

    def l2_snapshot(self, name: str) -> object:
        """Return an observed book with its source clock; execution sources are separate."""
        if name not in self.replay.observed_books:
            raise RecordedBookUnavailable(f"no observed replay book for {name}")
        return deepcopy(self.replay.observed_books[name])

    def user_state(self, address: str, dex: str = "") -> object:
        """Project causal economic exposure for only the selected perp namespace."""
        return self.replay.account_wire().perp_states[dex]

    def query_user_abstraction_state(self, address: str) -> object:
        """Declare this replay's supported unified-USDC account abstraction."""
        return "unifiedAccount"

    def spot_user_state(self, address: str) -> object:
        """Project the one shared USDC balance and explicitly modeled holds."""
        return self.replay.account_wire().spot_state

    def user_role(self, address: str) -> object:
        """Declare the simulated account role without resolving a real wallet."""
        return {"role": "user"}

    def frontend_open_orders(self, address: str, dex: str = "") -> object:
        """Expose accepted resting orders only within their visibility interval."""
        self.replay.advance_to(self.replay.clock.now_ms)
        return [
            row.wire(self.replay.clock.now_ms)
            for row in self.replay.orders.values()
            if self.replay.markets[row.symbol].perp_dex == dex
            and row.visible_open(self.replay.clock.now_ms)
        ]

    def user_fills(self, address: str) -> object:
        """Return fill history only after each independently declared receipt clock."""
        self.replay.advance_to(self.replay.clock.now_ms)
        return [
            deepcopy(row)
            for visible, row in self.replay.fill_rows
            if visible <= self.replay.clock.now_ms
        ]

    def query_order_by_oid(self, user: str, oid: int | str) -> object:
        """Resolve exact venue or client identity while withholding future terminal state."""
        self.replay.advance_to(self.replay.clock.now_ms)
        rows = [
            row for row in self.replay.orders.values() if row.oid == oid or row.client_id == oid
        ]
        if not rows or self.replay.clock.now_ms < rows[0].opened_visible_ms:
            return {"status": "unknownOid"}
        row = rows[0].visible_revision(self.replay.clock.now_ms)
        if not row.resting and self.replay.clock.now_ms < row.changed_visible_ms:
            return {"status": "unknownOid"}
        pending = self.replay.clock.now_ms < row.changed_visible_ms
        return {
            "status": "order",
            "order": {
                "order": row.wire(self.replay.clock.now_ms),
                "status": "open" if pending else row.status,
                "statusTimestamp": row.created_ms if pending else row.status_ms,
            },
        }

    def user_funding_history(self, user: str, startTime: int, endTime: int | None = None) -> object:
        """Keep exact funding clocks and receipt visibility in the requested closed interval."""
        require_clock(startTime, "funding history start")
        end = self.replay.clock.now_ms if endTime is None else endTime
        require_clock(end, "funding history end")
        if startTime > end:
            raise ValueError("funding history start must not exceed end")
        return [
            deepcopy(row)
            for visible, row in self.replay.funding_rows
            if visible <= self.replay.clock.now_ms and startTime <= row["time"] <= end
        ]
