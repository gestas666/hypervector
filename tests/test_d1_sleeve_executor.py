"""D1 sleeve executor contracts, offline: fake venue, fake exchange, fake clock.

The fake venue answers every /info request the executor makes through the real
reader, guard and pacer; the fake exchange stands in for the signing SDK behind
the real gateway. Nothing here reaches a network.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import d1_shadow_runner as runner
import d1_sleeve_core as core
import d1_sleeve_executor as executor
from eth_account import Account
import pytest
import requests
from requests.adapters import BaseAdapter
from test_d1_sleeve_core import ShadowLedger, pending_order, vtrade

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "d1_sleeve_executor.py"
_CORE = _ROOT / "scripts" / "d1_sleeve_core.py"
_PLIST = _ROOT / "scripts" / "local.hypervector.sleeve.d1_executor.plist.example"

CFG = core.SleeveConfig()
MASTER = "0x" + "a1" * 20
SUB = "0x" + "b2" * 20
ENGINE = "0x" + "e5" * 20
KEY = "0x" + "4f" * 32
AGENT = Account.from_key(KEY).address.lower()
WEBHOOK = "https://hooks.example.invalid/sleeve-secret-path"
T = date(2026, 9, 27)
T0 = datetime(2026, 9, 27, 0, 15, tzinfo=UTC)
DAY = timedelta(days=1)
ENV_NAMES = (
    core.ENV_MASTER,
    core.ENV_SUB,
    core.ENV_AGENT,
    core.ENV_KEY,
    core.ENV_ENGINE_KEY,
    core.ENV_WEBHOOK,
    core.ENV_DEADMAN,
)
SECRETS = (MASTER, SUB, AGENT, ENGINE, KEY, KEY[2:])
BANNED = (
    "usd_transfer",
    "usd_class_transfer",
    "sub_account_transfer",
    "sub_account_spot_transfer",
    "vault_usd_transfer",
    "send_asset",
    "spot_transfer",
    "withdraw_from_bridge",
    "approve_agent",
    "create_sub_account",
    "user_set_abstraction",
    "agent_set_abstraction",
    "user_dex_abstraction",
    "agent_enable_dex_abstraction",
    "schedule_cancel",
    "market_open",
    "market_close",
    "update_isolated_margin",
    "modify_order",
    "bulk_modify_orders_new",
    "set_referrer",
    "convert_to_multi_sig_user",
    "multi_sig",
    "token_delegate",
)
# The real alert helpers, captured before the autouse ``sinks`` fixture
# replaces them with recorders in every test.
REAL_HTTP_GET = executor._http_get
REAL_HTTP_POST = executor._http_post_json


# ----------------------------------------------------------------- isolation


def _refuse(*args: object, **kwargs: object) -> None:
    raise AssertionError("real network or credential lookup attempted")


@pytest.fixture(autouse=True)
def sinks(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """No network, no inherited credentials, recorded alert channels."""
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    record = SimpleNamespace(banners=[], webhooks=[], pings=[])
    monkeypatch.setattr(
        executor,
        "_notify_mac",
        lambda title, body: record.banners.append((title, body)),
    )
    monkeypatch.setattr(
        executor,
        "_http_post_json",
        lambda url, data, title: record.webhooks.append((url, json.loads(data), title)),
    )
    monkeypatch.setattr(executor, "_http_get", lambda url: record.pings.append(url))
    return record


# ----------------------------------------------------------------- fakes


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)


COINS: dict[str, tuple[int, float, float]] = {
    "BTC": (5, 40.0, 100_000.0),
    "ETH": (4, 25.0, 2000.0),
    "AAA": (2, 10.0, 100.0),
    "BBB": (2, 10.0, 100.0),
    "CCC": (2, 10.0, 100.0),
    "DDD": (2, 10.0, 100.0),
    "kPEPE": (0, 10.0, 0.0101),
    "DEAD": (2, 10.0, 100.0),
    **{f"C{i:02d}": (2, 10.0, 100.0) for i in range(1, 12)},
}


class FakeVenue:
    """Hyperliquid as the executor sees it (sub-account and master)."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.universe = [
            {"name": name, "szDecimals": szd, "maxLeverage": lev}
            for name, (szd, lev, _) in COINS.items()
        ]
        for item in self.universe:
            if item["name"] == "DEAD":
                item["isDelisted"] = True
        self.mids = {name: px for name, (_, _, px) in COINS.items()}
        self.modes = {MASTER: "unifiedAccount", SUB: "unifiedAccount"}
        self.usdc = {MASTER: 2300.0, SUB: 2500.0}
        self.positions: dict[str, dict] = {}
        self.leverage: dict[str, tuple[str, int]] = {}
        self.orders: list[dict] = []
        self.history: dict[str, dict] = {}
        self.fills: list[dict] = []
        self.funding: list[dict] = []
        self.role: Any = {"role": "agent", "data": {"user": MASTER}}
        valid = _ms(clock() + timedelta(days=170))
        self.agents: list[dict] = [
            {
                "name": f"d1-sleeve valid_until {valid}",
                "address": AGENT,
                "validUntil": valid,
            },
            {"name": "hl-api", "address": ENGINE, "validUntil": valid},
        ]
        self.subs: Any = [
            {
                "name": "d1-sleeve",
                "subAccountUser": SUB,
                "master": MASTER,
                "clearinghouseState": {"withdrawable": "1"},
            },
        ]
        self.calls: list[tuple[str, str, str | None]] = []
        self.call_times: list[datetime] = []
        self.omit_cloid = False
        self.hold_margin = False  # unified realism: USDC hold = isolated margin
        self.realize = False  # fills move the sub's USDC by closedPnl - fee
        self.trigger_echo_scale = 1.0  # listed triggerPx = placed x this
        self.order_reads = 0
        self.lag_reads: set[int] = set()  # these order reads miss the newest order
        self.landings: list[tuple[datetime, Any]] = []  # orders still in flight
        self.auto_cancel_reduce_only = False  # a closed position's stops vanish
        self.date_offset: timedelta | None = None  # Date header = clock + offset
        self._oid = 5000

    def next_oid(self) -> int:
        self._oid += 1
        return self._oid

    def szd(self, coin: str) -> int:
        return COINS[coin][0]

    def land_due(self) -> None:
        """Orders whose POST failed at the client but reach the book later."""
        for item in [x for x in self.landings if x[0] <= self.clock()]:
            self.landings.remove(item)
            item[1]()

    def info(self, payload: dict) -> Any:
        self.land_due()
        kind = payload["type"]
        user = payload.get("user")
        self.calls.append(("info", kind, user))
        self.call_times.append(self.clock())
        if kind == "meta":
            return {"universe": [dict(item) for item in self.universe]}
        if kind == "allMids":
            return {coin: str(px) for coin, px in self.mids.items()}
        if kind == "clearinghouseState":
            if user != SUB:
                return {
                    "assetPositions": [],
                    "marginSummary": {"accountValue": "0"},
                    "withdrawable": "0",
                }
            return {
                "assetPositions": [
                    {"position": self.position_record(coin, pos), "type": "oneWay"}
                    for coin, pos in self.positions.items()
                ],
                "marginSummary": {"accountValue": str(self.usdc[SUB])},
                "withdrawable": str(self.usdc[SUB]),
            }
        if kind == "spotClearinghouseState":
            hold = 0.0
            if self.hold_margin and user == SUB:
                hold = sum(
                    abs(p["szi"]) * p["entryPx"] / p["value"]
                    for p in self.positions.values()
                )
            return {
                "balances": [
                    {
                        "coin": "USDC",
                        "token": 0,
                        "total": str(self.usdc.get(user, 0.0)),
                        "hold": str(hold),
                        "entryNtl": "0.0",
                    },
                ]
            }
        if kind == "frontendOpenOrders":
            out = []
            self.order_reads += 1
            visible = self.orders
            if self.order_reads in self.lag_reads:
                visible = self.orders[:-1]
            for order in visible:
                item = dict(order)
                if self.omit_cloid or item.get("cloid") is None:
                    item.pop("cloid", None)
                if item.get("isTrigger") and self.trigger_echo_scale != 1.0:
                    scaled = float(item["triggerPx"]) * self.trigger_echo_scale
                    item["triggerPx"] = str(scaled)
                out.append(item)
            return out
        if kind == "orderStatus":
            record = self.history.get(payload["oid"])
            if record is None:
                return {"status": "unknownOid"}
            return {
                "status": "order",
                "order": {
                    "order": {
                        "coin": record["coin"],
                        "oid": record["oid"],
                        "sz": str(record["sz"]),
                        "origSz": str(record["origSz"]),
                        "cloid": payload["oid"],
                    },
                    "status": record["status"],
                    "statusTimestamp": _ms(self.clock()),
                },
            }
        if kind == "userRole":
            return self.role
        if kind == "extraAgents":
            return self.agents
        if kind == "subAccounts":
            return self.subs
        if kind == "userAbstraction":
            return self.modes.get(user, "default")
        if kind == "userFillsByTime":
            return [
                f
                for f in self.fills
                if payload["startTime"] <= f["time"] <= payload["endTime"]
            ]
        if kind == "userFunding":
            return [
                f
                for f in self.funding
                if payload["startTime"] <= f["time"] <= payload["endTime"]
            ]
        raise AssertionError(f"unexpected info request {kind}")

    def position_record(self, coin: str, pos: dict) -> dict:
        return {
            "coin": coin,
            "szi": str(pos["szi"]),
            "entryPx": str(pos["entryPx"]),
            "positionValue": str(abs(pos["szi"]) * self.mids[coin]),
            "liquidationPx": None if pos["liq"] is None else str(pos["liq"]),
            "leverage": {"type": pos["type"], "value": pos["value"]},
            "marginUsed": "0.0",
        }

    def apply_fill(
        self,
        coin: str,
        is_buy: bool,
        sz: float,
        px: float,
        oid: int,
        *,
        liquidation: bool = False,
    ) -> None:
        delta = sz if is_buy else -sz
        pos = self.positions.get(coin)
        old = pos["szi"] if pos else 0.0
        new = round(old + delta, 10)
        closed_pnl = 0.0
        if pos and (old > 0) != (delta > 0):
            closed_pnl = (
                (px - pos["entryPx"])
                * min(abs(delta), abs(old))
                * (1 if old > 0 else -1)
            )
        if abs(new) < 1e-12:
            self.positions.pop(coin, None)
            if self.auto_cancel_reduce_only:
                for order in [o for o in self.orders if o["coin"] == coin]:
                    if order["reduceOnly"]:
                        self.orders.remove(order)
        elif pos is None or (old > 0) != (new > 0):
            kind, value = self.leverage.get(coin, ("cross", 20))
            d = 1 if new > 0 else -1
            mmr = 1 / (2 * COINS[coin][1])
            liq = px * (1 - d * (1 / value - mmr)) if kind == "isolated" else None
            self.positions[coin] = {
                "szi": new,
                "entryPx": px,
                "type": kind,
                "value": value,
                "liq": liq,
            }
        elif abs(new) > abs(old):
            entry = (pos["entryPx"] * abs(old) + px * abs(delta)) / abs(new)
            pos.update(szi=new, entryPx=entry)
        else:
            pos["szi"] = new
        self.fills.append(
            {
                "coin": coin,
                "oid": oid,
                "px": str(px),
                "sz": str(sz),
                "side": "B" if is_buy else "A",
                "time": _ms(self.clock()),
                "closedPnl": str(closed_pnl),
                "fee": str(px * sz * 4.5e-4),
                "liquidation": {"method": "market"} if liquidation else None,
            }
        )
        if self.realize:
            self.usdc[SUB] += closed_pnl - px * sz * 4.5e-4

    def add_stop(
        self,
        coin: str,
        *,
        is_buy: bool,
        sz: float,
        trigger: float,
        cloid: str | None,
        reduce_only: bool = True,
    ) -> int:
        oid = self.next_oid()
        self.orders.append(
            {
                "coin": coin,
                "oid": oid,
                "cloid": cloid,
                "side": "B" if is_buy else "A",
                "sz": str(sz),
                "origSz": str(sz),
                "isTrigger": True,
                "triggerPx": str(trigger),
                "reduceOnly": reduce_only,
                "orderType": "Stop Market",
                "limitPx": str(trigger),
                "timestamp": _ms(self.clock()),
            }
        )
        if cloid:
            self.history[cloid] = {
                "coin": coin,
                "oid": oid,
                "status": "open",
                "sz": sz,
                "origSz": sz,
            }
        return oid

    def stops(self, coin: str) -> list[dict]:
        return [o for o in self.orders if o["coin"] == coin and o["isTrigger"]]

    def trigger_stop(self, coin: str) -> None:
        (stop,) = self.stops(coin)
        self.orders.remove(stop)
        pos = self.positions[coin]
        self.apply_fill(
            coin,
            stop["side"] == "B",
            abs(pos["szi"]),
            float(stop["triggerPx"]),
            stop["oid"],
        )
        if stop.get("cloid"):
            self.history[stop["cloid"]]["status"] = "filled"

    def liquidate(self, coin: str) -> None:
        pos = self.positions[coin]
        self.orders = [o for o in self.orders if o["coin"] != coin]
        self.apply_fill(
            coin,
            pos["szi"] < 0,
            abs(pos["szi"]),
            pos["liq"] or 1.0,
            self.next_oid(),
            liquidation=True,
        )


class FakeExchange:
    """The signing client's surface; behaviour is scripted per coin."""

    def __init__(
        self,
        venue: FakeVenue,
        harness: Harness,
        *,
        vault_address: str,
        wallet_address: str,
    ) -> None:
        self.venue = venue
        self.h = harness
        self.vault_address = vault_address
        self.wallet = SimpleNamespace(address=wallet_address)
        self.expires_after: int | None = None

    def _record(self, action: str, **details: Any) -> None:
        self.h.calls.append(
            {
                "action": action,
                "vault": self.vault_address,
                "expires_after": self.expires_after,
                **details,
            }
        )
        self.venue.calls.append(("exchange", action, details.get("coin")))
        self.venue.call_times.append(self.venue.clock())

    def set_expires_after(self, expires_after: int | None) -> None:
        self.expires_after = expires_after

    def update_leverage(self, leverage: int, name: str, is_cross: bool = True) -> Any:
        self._record("updateLeverage", coin=name, leverage=leverage, is_cross=is_cross)
        if name in self.h.leverage_fail:
            return {"status": "err", "response": "Cannot switch leverage type"}
        self.venue.leverage[name] = ("cross" if is_cross else "isolated", leverage)
        return {"status": "ok", "response": {"type": "default"}}

    def order(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: dict,
        reduce_only: bool = False,
        cloid: Any = None,
    ) -> Any:
        raw = cloid.to_raw() if hasattr(cloid, "to_raw") else cloid
        trigger = "trigger" in order_type
        self._record(
            "order",
            coin=name,
            is_buy=is_buy,
            sz=sz,
            limit_px=limit_px,
            order_type=order_type,
            reduce_only=reduce_only,
            cloid=raw,
            trigger=trigger,
        )
        if trigger:
            queue = self.h.trigger.get(name) or []
            mode = queue.pop(0) if queue else "rest"
            if mode == "reject":
                return _ack({"error": "Invalid TP/SL price. asset=3"})
            oid = self.venue.add_stop(
                name,
                is_buy=is_buy,
                sz=sz,
                trigger=order_type["trigger"]["triggerPx"],
                cloid=raw,
            )
            return _ack({"resting": {"oid": oid}})
        queue = self.h.ioc.get(name) or []
        spec = queue.pop(0) if queue else {"mode": "fill"}
        mode = spec["mode"]
        if mode == "raise_before":
            raise requests.ConnectionError("connection reset before apply")
        if mode == "land_later":  # the client times out; the order lands later
            when = self.venue.clock() + timedelta(seconds=spec["delay"])

            def land() -> None:
                oid = self.venue.next_oid()
                self.venue.apply_fill(name, is_buy, sz, self.venue.mids[name], oid)
                self.venue.history[raw] = {
                    "coin": name,
                    "oid": oid,
                    "status": "filled",
                    "sz": 0.0,
                    "origSz": sz,
                }

            self.venue.landings.append((when, land))
            raise requests.ReadTimeout("read timed out")
        if mode == "reject":
            return _ack({"error": "Insufficient margin to place order."})
        if mode == "no_fill":
            self.venue.history[raw] = {
                "coin": name,
                "oid": self.venue.next_oid(),
                "status": "canceled",
                "sz": sz,
                "origSz": sz,
            }
            return _ack(
                {
                    "error": "Order could not immediately match against any resting "
                    "orders. asset=3"
                }
            )
        pos = self.venue.positions.get(name)
        fill = round(sz * spec.get("fraction", 1.0), 10)
        if reduce_only:
            if pos is None or (pos["szi"] > 0) == is_buy:
                return _ack({"error": "Reduce only order would increase position."})
            fill = min(fill, abs(pos["szi"]))
        side = 1 if is_buy else -1
        taker = round(self.venue.mids[name] * (1 + side * self.h.taker_bps / 1e4), 6)
        px = spec.get("px", taker)
        oid = self.venue.next_oid()
        self.venue.apply_fill(name, is_buy, fill, px, oid)
        self.venue.history[raw] = {
            "coin": name,
            "oid": oid,
            "status": "filled" if fill >= sz else "canceled",
            "sz": round(sz - fill, 10),
            "origSz": sz,
        }
        if mode == "raise_after":
            raise requests.ConnectionError("connection reset after apply")
        return _ack({"filled": {"totalSz": str(fill), "avgPx": str(px), "oid": oid}})

    def bulk_orders(
        self, order_requests: list[dict], builder: Any = None, grouping: str = "na"
    ) -> Any:
        """An entry IOC with its reduce-only stop child (grouping normalTpsl).

        The parent behaves exactly as ``order`` (every scripted IOC mode);
        the venue places the child, sized to the parent, only when the parent
        fully fills (a late landing places it when it lands), and cancels it
        otherwise. ``h.child[coin]`` scripts the child: ``rest`` (default),
        ``reject`` (an error status, nothing placed), ``no_cloid`` (placed,
        listed without its cloid) or ``garbled`` (placed, but the reply has a
        status count the parser does not know: the send is ambiguous)."""
        assert grouping == "normalTpsl" and builder is None
        parent, child = order_requests
        name = parent["coin"]
        raw = parent["cloid"]
        raw = raw.to_raw() if hasattr(raw, "to_raw") else raw
        craw = child["cloid"]
        craw = craw.to_raw() if hasattr(craw, "to_raw") else craw
        assert (
            child["coin"] == name and child["reduce_only"] and not parent["reduce_only"]
        )
        assert child["is_buy"] != parent["is_buy"] and child["sz"] == parent["sz"]
        assert "trigger" in child["order_type"] and parent["order_type"] == executor.IOC
        queue = self.h.child.get(name) or []
        mode = queue.pop(0) if queue else "rest"
        placed: list[int] = []

        def place_child() -> None:
            record = self.venue.history.get(raw)
            full = (
                record is not None
                and record["status"] == "filled"
                and float(record["sz"]) <= 1e-12
            )
            if not full or mode == "reject" or placed:
                return
            placed.append(
                self.venue.add_stop(
                    name,
                    is_buy=child["is_buy"],
                    sz=child["sz"],
                    trigger=child["order_type"]["trigger"]["triggerPx"],
                    cloid=None if mode == "no_cloid" else craw,
                )
            )
            if mode == "no_cloid":
                self.venue.history[craw] = {
                    "coin": name,
                    "oid": placed[0],
                    "status": "open",
                    "sz": child["sz"],
                    "origSz": child["sz"],
                }

        size_before = len(self.h.calls)
        try:
            response = self.order(
                name,
                parent["is_buy"],
                parent["sz"],
                parent["limit_px"],
                parent["order_type"],
                reduce_only=False,
                cloid=parent["cloid"],
            )
        except requests.ReadTimeout:  # land_later: the child lands with it
            when = self.venue.landings[-1][0] if self.venue.landings else None
            if when is not None:
                self.venue.landings.append((when, place_child))
            raise
        except Exception:
            place_child()  # raise_after: applied, so the child rests
            raise
        finally:
            if len(self.h.calls) > size_before:
                self.h.calls[size_before].update(
                    grouping=grouping,
                    child={
                        "cloid": craw,
                        "is_buy": child["is_buy"],
                        "sz": child["sz"],
                        "trigger_px": child["order_type"]["trigger"]["triggerPx"],
                        "reduce_only": child["reduce_only"],
                    },
                )
        place_child()
        statuses = response["response"]["data"]["statuses"]
        if mode == "reject" and "filled" in statuses[0]:
            child_status: Any = {"error": "Invalid TP/SL price. asset=3"}
        elif placed:
            child_status = "waitingForTrigger"
        else:
            child_status = "waitingForFill"
        if mode == "garbled":
            statuses = [*statuses, child_status, child_status]
        else:
            statuses = [*statuses, child_status]
        return {
            "status": "ok",
            "response": {"type": "order", "data": {"statuses": statuses}},
        }

    def _cancel(self, name: str, match: Any) -> Any:
        for order in list(self.venue.orders):
            if order["coin"] == name and match(order):
                self.venue.orders.remove(order)
                if order.get("cloid") in self.venue.history:
                    self.venue.history[order["cloid"]]["status"] = "canceled"
                return {
                    "status": "ok",
                    "response": {"type": "cancel", "data": {"statuses": ["success"]}},
                }
        return {
            "status": "ok",
            "response": {
                "type": "cancel",
                "data": {
                    "statuses": [
                        {
                            "error": "Order was never placed, already canceled, or filled."
                        }
                    ]
                },
            },
        }

    def cancel(self, name: str, oid: int) -> Any:
        self._record("cancel", coin=name, oid=oid)
        return self._cancel(name, lambda order: order["oid"] == oid)

    def cancel_by_cloid(self, name: str, cloid: Any) -> Any:
        raw = cloid.to_raw() if hasattr(cloid, "to_raw") else cloid
        self._record("cancelByCloid", coin=name, cloid=raw)
        return self._cancel(name, lambda order: order.get("cloid") == raw)


def _ack(status: dict) -> dict:
    return {
        "status": "ok",
        "response": {"type": "order", "data": {"statuses": [status]}},
    }


class VenueAdapter(BaseAdapter):
    """Network adapter behind the real guard: routes /info to the fake venue."""

    def __init__(self, venue: FakeVenue) -> None:
        super().__init__()
        self.venue = venue
        self.requests: list[requests.PreparedRequest] = []

    def send(self, request: requests.PreparedRequest, **kwargs: Any) -> Any:
        self.requests.append(request)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(
            self.venue.info(json.loads(request.body))
        ).encode()
        if self.venue.date_offset is not None:
            server = self.venue.clock() + self.venue.date_offset
            response.headers["Date"] = format_datetime(server, usegmt=True)
        response.url = request.url
        response.request = request
        response.encoding = "utf-8"
        return response

    def close(self) -> None:
        pass


@dataclass(frozen=True)
class E:
    coin: str
    side: str = "long"
    px: float = 100.0
    atr: float = 2.0
    taken: bool = True
    day: date = T


class Harness:
    def __init__(self, tmp_path: Path, *, start: datetime = T0) -> None:
        self.tmp = tmp_path
        self.clock = FakeClock(start)
        self.venue = FakeVenue(self.clock)
        self.paths = core.Paths.default(tmp_path / "repo")
        self.env_file = tmp_path / "cfg" / "d1_sleeve.env"
        self.calls: list[dict] = []
        self.ioc: dict[str, list[dict]] = {}
        self.trigger: dict[str, list[str]] = {}
        self.child: dict[str, list[str]] = {}
        # A taker fill: an IOC with no scripted px fills this many bps from
        # the mid on the adverse side (0: at the mid). Away from the mid an
        # entry's child trigger differs from its fill-anchored rule stop, so
        # protect() re-anchors: it places the rule stop and cancels the child.
        self.taker_bps = 0.0
        self.leverage_fail: set[str] = set()
        self.factory_calls = 0
        self.readers: list[executor.HlInfoReader] = []
        self.write_env()
        census = self.paths.census
        census.parent.mkdir(parents=True, exist_ok=True)
        census.write_text("dex,coin\n")
        stamp = datetime(2026, 9, 26, 12, tzinfo=UTC).timestamp()
        os.utime(census, (stamp, stamp))
        self.amendment = self.paths.repo_root / "docs" / "plans" / "amendment.txt"
        self.amendment.parent.mkdir(parents=True, exist_ok=True)
        self.amendment.write_text(
            "sleeve amendment: 1% of book, sub-account, 6 h window\n"
        )
        self.approval = tmp_path / "approval.json"
        self.write_approval(self.approval_doc())

    def write_env(self, **values: str | None) -> None:
        base: dict[str, str | None] = {
            core.ENV_KEY: KEY,
            core.ENV_AGENT: AGENT,
            core.ENV_SUB: SUB,
            core.ENV_MASTER: MASTER,
        }
        base.update(values)
        self.env_file.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(f"{k}={v}\n" for k, v in base.items() if v is not None)
        self.env_file.write_text("# d1 sleeve\n" + text)
        self.env_file.chmod(0o600)

    def approval_doc(self) -> dict:
        env = executor.load_sleeve_env(
            self.env_file, include_private_key=False, repo_root=self.paths.repo_root
        )
        doc = executor.approval_template(CFG, env)
        assert doc["approval_status"] != "approved_for_live"  # the template never arms
        doc["approval_status"] = "approved_for_live"
        doc["operator_approval"] = "arm the d1 sleeve at one percent"
        doc["approved_at_utc"] = "2026-09-27T00:00:00Z"
        doc["prereg_amendment"] = {
            "path": "docs/plans/amendment.txt",
            "sha256": hashlib.sha256(self.amendment.read_bytes()).hexdigest(),
        }
        return doc

    def write_approval(self, doc: dict) -> None:
        self.approval.write_text(json.dumps(doc))

    def factory(self, *, key: str, meta: dict, sub: str, cfg: core.SleeveConfig) -> Any:
        self.factory_calls += 1
        assert meta["universe"] and cfg == CFG
        return FakeExchange(
            self.venue,
            self,
            vault_address=sub,
            wallet_address=Account.from_key(key).address,
        )

    def main(self, argv: list[str]) -> int:
        reader = executor.HlInfoReader(CFG, transport=VenueAdapter(self.venue))
        self.readers.append(reader)
        return executor.main(
            argv,
            reader=reader,
            exchange_factory=self.factory,
            clock=self.clock,
            sleep=self.clock.sleep,
            paths=self.paths,
            env_file=self.env_file,
        )

    def run(self, *extra: str, armed: bool = True) -> int:
        argv = ["run", *extra]
        if armed:
            argv += [
                "--approval",
                str(self.approval),
                "--enabled",
                "--i-accept-live-risk",
            ]
        return self.main(argv)

    def at(self, when: datetime) -> Harness:
        self.clock.now = when
        return self

    def journal(self) -> list[dict]:
        return core.load_journal(self.paths.journal)

    def of(self, kind: str, **match: Any) -> list[dict]:
        return [
            e
            for e in self.journal()
            if e["event"] == kind and all(e.get(k) == v for k, v in match.items())
        ]

    def book(self) -> core.SleeveBook:
        return core.derive_book(self.journal())

    def actions(self, action: str | None = None, **match: Any) -> list[dict]:
        return [
            c
            for c in self.calls
            if (action is None or c["action"] == action)
            and all(c.get(k) == v for k, v in match.items())
        ]

    def shadow(
        self,
        day: date = T,
        *,
        entries: tuple[E, ...] = (),
        holding: tuple[E, ...] = (),
        exits: tuple[str, ...] = (),
        open_closes: tuple[tuple[str, str], ...] = (),
        past_closes: tuple[tuple[str, str, date], ...] = (),
        mode: str = "daily",
    ) -> ShadowLedger:
        """A ledger whose last mark is ``day - 1`` and whose open step is ``day``."""
        ledger = ShadowLedger()
        mark = day - DAY
        for trade_id, reason, when in past_closes:
            ledger.close(trade_id, when, reason=reason, exit_px=96.0, net_r=-1.0)
        pending: dict[str, dict] = {}
        for coin in exits:
            trade = next(e for e in holding if e.coin == coin)
            pending[coin] = pending_order(
                coin,
                signal_date=mark.isoformat(),
                exit_direction=1 if trade.side == "long" else -1,
            )
        for e in entries:
            order = pending_order(
                e.coin,
                signal_date=mark.isoformat(),
                entry_direction=1 if e.side == "long" else -1,
                atr=e.atr,
            )
            if e.coin in pending:
                pending[e.coin].update(
                    {
                        k: order[k]
                        for k in (
                            "entry_direction",
                            "atr",
                            "max_leverage",
                            "census_rank",
                            "priority_quote_volume_30d",
                        )
                    }
                )
            else:
                pending[e.coin] = order
        ledger.mark(
            mark,
            trades=[
                vtrade(
                    e.coin,
                    side=e.side,
                    entry_date=e.day.isoformat(),
                    entry_px=e.px,
                    atr=e.atr,
                    taken=e.taken,
                )
                for e in holding
            ],
            pending=list(pending.values()),
            mode=mode,
        )
        for trade_id, reason in open_closes:
            ledger.close(
                trade_id, day, reason=reason, exit_px=99.0, net_r=-0.2, mode=mode
            )
        for rank, e in enumerate(entries, start=1):
            ledger.entry(
                e.coin,
                day,
                side=e.side,
                entry_px=e.px,
                atr=e.atr,
                rank=rank,
                taken=e.taken,
                mode=mode,
            )
        ledger.write(self.paths.shadow_ledger)
        return ledger


def tid(coin: str, side: str = "long", day: date = T) -> str:
    return f"{coin}:{side}:{day.isoformat()}"


def outputs(capsys: pytest.CaptureFixture) -> str:
    captured = capsys.readouterr()
    return captured.out + captured.err


def assert_no_secrets(h: Harness, text: str = "") -> None:
    blobs = [text]
    for path in (h.paths.journal, h.paths.status, h.paths.alerts):
        if path.exists():
            blobs.append(path.read_text())
    everything = "\n".join(blobs)
    lowered = everything.lower()
    for secret in SECRETS:
        assert secret.lower() not in lowered, "an address or key leaked"
        assert secret[2:].lower() not in lowered
    assert Account.from_key(KEY).address[2:] not in everything
    assert not core._ADDRESS_ANY_CASE.search(everything)


@pytest.fixture
def h(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def open_day_one(h: Harness, *coins: str, **ioc: dict) -> None:
    h.shadow(entries=tuple(E(c) for c in coins))
    for coin, spec in ioc.items():
        h.ioc[coin] = [spec]
    assert h.at(T0).run() == 0


def next_day(h: Harness, **kwargs: Any) -> None:
    h.at(T0 + DAY)
    h.shadow(T + DAY, **kwargs)


def criticals(h: Harness) -> set[str]:
    """Keys of the critical problems left at the end of the last run."""
    end = h.of("run_end")[-1]
    return {p["key"] for p in end["problems"] if p["severity"] == "critical"}


def entry_outcomes(h: Harness, role: str = "entry") -> list[str]:
    """Outcome statuses of the entry orders only (each entry's stop child
    has outcomes of its own)."""
    cloids = {i["cloid"] for i in h.of("intent", role=role)}
    return [
        o["status"] for o in h.of("outcome", action="order") if o["cloid"] in cloids
    ]


def child_cloid(
    coin: str, n: int = 1, side: str = "long", day: date = T, role: str = "stop"
) -> str:
    """The cloid of an entry's venue-attached stop child (stop version n)."""
    return core.cloid_for(CFG, SUB, tid(coin, side, day), role, n)


def no_children(h: Harness, *coins: str) -> None:
    """The venue attaches no stop child to these coins' entries (as after a
    partial fill, whose children the venue cancels): the fallback path,
    where only the sleeve's own reads and stop placement protect a fill."""
    for coin in coins:
        h.child[coin] = ["reject"] * 20


# ----------------------------------------------------------------- env file


def test_env_file_refusals(h: Harness, tmp_path: Path) -> None:
    load = executor.load_sleeve_env
    h.env_file.chmod(0o644)
    with pytest.raises(core.RefusalError, match="0600"):
        load(h.env_file, include_private_key=False)
    h.env_file.chmod(0o600)
    link = tmp_path / "cfg" / "link.env"
    link.symlink_to(h.env_file)
    with pytest.raises(core.RefusalError, match="symlink"):
        load(link, include_private_key=False)
    inside = h.paths.repo_root / "sleeve.env"
    inside.write_text(h.env_file.read_text())
    inside.chmod(0o600)
    with pytest.raises(core.RefusalError, match="outside the repository"):
        load(inside, include_private_key=False, repo_root=h.paths.repo_root)
    h.write_env(**{core.ENV_ENGINE_KEY: "0x" + "9" * 64})
    with pytest.raises(core.RefusalError, match=core.ENV_ENGINE_KEY):
        load(h.env_file, include_private_key=False)
    h.write_env(**{core.ENV_SUB: "not-an-address"})
    with pytest.raises(core.RefusalError) as info:
        load(h.env_file, include_private_key=False)
    assert "not-an-address" not in str(info.value)


def test_env_loader_precedence_and_key_handling(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    dry = executor.load_sleeve_env(h.env_file, include_private_key=False)
    assert dry.private_key is None and dry.sub == SUB and dry.agent == AGENT
    armed = executor.load_sleeve_env(h.env_file, include_private_key=True)
    assert armed.private_key == KEY
    for text in (repr(armed), str(armed)):
        assert KEY not in text and KEY[2:] not in text and SUB not in text
        assert "key_loaded=True" in text
    other = "0x" + "c7" * 20
    monkeypatch.setenv(core.ENV_SUB, other)
    assert executor.load_sleeve_env(h.env_file, include_private_key=False).sub == other
    h.write_env(**{core.ENV_KEY: None})
    with pytest.raises(core.RefusalError, match=core.ENV_KEY):
        executor.load_sleeve_env(h.env_file, include_private_key=True)


def test_env_loader_never_opens_the_repo_dotenv(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    real = io.open

    def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(file))
        return real(file, *args, **kwargs)

    monkeypatch.setattr(io, "open", spy)
    executor.load_sleeve_env(h.env_file, include_private_key=True)
    assert opened == [str(h.env_file)]
    assert not any(name.endswith(os.sep + ".env") for name in opened)


# ----------------------------------------------------------------- approval and flags


def test_approval_matches_and_every_mismatch_refuses(h: Harness) -> None:
    env = executor.load_sleeve_env(h.env_file, include_private_key=False)
    root = h.paths.repo_root
    digest = executor.verify_approval(h.approval, CFG, env, repo_root=root)
    assert digest == hashlib.sha256(h.approval.read_bytes()).hexdigest()
    good = h.approval_doc()

    def mutate(path: tuple[str, ...], value: Any) -> dict:
        doc = json.loads(json.dumps(good))
        target = doc
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return doc

    bad = [
        mutate(("code", "scripts/d1_sleeve_executor.py"), "0" * 64),
        mutate(("code", "scripts/d1_shadow_runner.py"), "0" * 64),
        mutate(("config_fingerprint",), "0" * 16),
        mutate(("risk_fraction",), 0.005),
        mutate(("accounts", "sub_fp"), "0" * 12),
        mutate(("operator_approval",), ""),
        mutate(("operator_approval",), executor.APPROVAL_PLACEHOLDER),
        mutate(("prereg_amendment", "path"), "docs/plans/missing.txt"),
        mutate(("prereg_amendment", "sha256"), "0" * 64),
        mutate(("prereg_amendment", "path"), "../outside.txt"),
        mutate(("approval_status",), "draft"),
        mutate(("shadow_config_fingerprint",), "0" * 16),
    ]
    for doc in bad:
        h.write_approval(doc)
        with pytest.raises(core.RefusalError, match="approval refused"):
            executor.verify_approval(h.approval, CFG, env, repo_root=root)
    h.write_approval(mutate(("code", "scripts/d1_sleeve_core.py"), "0" * 64))
    h.shadow(entries=(E("AAA"),))
    assert h.run() == 3
    assert h.factory_calls == 0 and not h.paths.journal.exists()


def test_approval_template_fills_computed_fields_without_network(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    assert h.main(["approval-template"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["operator_approval"] == executor.APPROVAL_PLACEHOLDER
    assert doc["approval_status"] == executor.APPROVAL_TEMPLATE_STATUS
    assert doc["approved_at_utc"] == "" and doc["prereg_amendment"] == {
        "path": "",
        "sha256": "",
    }
    assert doc["config_fingerprint"] == CFG.fingerprint()
    assert (
        doc["code"]["scripts/d1_sleeve_core.py"]
        == hashlib.sha256(_CORE.read_bytes()).hexdigest()
    )
    assert doc["code"]["scripts/d1_shadow_runner.py"] == CFG.shadow_runner_sha256
    assert doc["accounts"]["sub_fp"] == core.address_fp(SUB)
    assert h.venue.calls == [] and h.factory_calls == 0
    assert SUB not in json.dumps(doc)


@pytest.mark.parametrize(
    "flags",
    [
        ["--enabled"],
        ["--i-accept-live-risk"],
        ["--enabled", "--approval", "x.json"],
        ["--enabled", "--i-accept-live-risk"],
    ],
)
def test_arming_flags_are_all_or_nothing(h: Harness, flags: list[str]) -> None:
    h.shadow(entries=(E("AAA"),))
    assert h.main(["run", *flags]) == 3
    assert h.venue.calls == [] and h.factory_calls == 0


# ----------------------------------------------------------------- dry run


def test_dry_run_plans_without_a_key_sdk_or_writes(
    h: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    h.shadow(entries=(E("AAA"), E("BBB", taken=False)))

    def no_sdk() -> None:
        raise AssertionError("dry run imported the SDK")

    monkeypatch.setattr(executor, "_load_sdk", no_sdk)
    loads: list[bool] = []
    real_load = executor.load_sleeve_env

    def load(*args: Any, **kwargs: Any) -> Any:
        loads.append(kwargs["include_private_key"])
        return real_load(*args, **kwargs)

    monkeypatch.setattr(executor, "load_sleeve_env", load)
    before = sorted(p for p in h.tmp.rglob("*"))
    assert h.run(armed=False) == 0
    assert sorted(p for p in h.tmp.rglob("*")) == before
    assert loads == [False] and h.factory_calls == 0
    out = capsys.readouterr().out
    plans = [
        json.loads(line) for line in out.splitlines() if line.startswith('{"plan"')
    ]
    kinds = [(p["plan"], p.get("coin")) for p in plans]
    assert kinds == [
        ("update_leverage", "AAA"),
        ("entry", "AAA"),
        ("stop", "AAA"),
        ("update_leverage", "BBB"),
        ("entry", "BBB"),
        ("stop", "BBB"),
    ]
    entry = plans[1]
    assert (
        entry["sz"] == 12.0
        and entry["limit_px"] == 100.5
        and entry["reduce_only"] is False
    )
    assert plans[2]["trigger_px"] == 96.0 and plans[2]["reduce_only"] is True
    assert "signing_client=none exchange_posts=0 (dry-run)" in out
    assert "mode=dry" in out and "entries=2" in out
    assert not [c for c in h.venue.calls if c[0] == "exchange"]
    guard = h.readers[-1].guard
    assert guard.allow_exchange is False and "/exchange" not in guard.sent
    with pytest.raises(executor.EgressRefusedError):
        h.readers[-1].session.post("https://api.hyperliquid.xyz/exchange", json={})
    assert_no_secrets(h, out)


# ----------------------------------------------------------------- guard and pacer


def test_guard_refuses_everything_but_posts_to_the_info_path() -> None:
    clock = FakeClock(T0)
    capture = VenueAdapter(FakeVenue(clock))
    reader = executor.HlInfoReader(CFG, transport=capture)
    reader.bind(executor.HlPacer(CFG, clock=clock, sleep=clock.sleep), clock.sleep)
    session = reader.session
    assert session.trust_env is False and session.max_redirects == 0
    for method, url in (
        ("GET", "https://api.hyperliquid.xyz/info"),
        ("POST", "https://api.hyperliquid.xyz/exchange"),
        ("POST", "http://api.hyperliquid.xyz/info"),
        ("POST", "https://api.hyperliquid-testnet.xyz/info"),
        ("POST", "https://data-api.binance.vision/info"),
        ("POST", "https://api.hyperliquid.xyz/info?x=1"),
    ):
        with pytest.raises(executor.EgressRefusedError):
            session.request(method, url, json={"type": "meta"})
    assert capture.requests == []
    assert reader.guard.refused["api.hyperliquid.xyz"] == 4
    reader.meta()
    reader.all_mids()
    assert reader.guard.sent == {"/info": 2}
    armed = executor.HlAllowListTransport(capture, allow_exchange=True)
    request = requests.Request(
        "POST", "https://api.hyperliquid.xyz/exchange", json={"type": "exchange-test"}
    ).prepare()
    with pytest.raises(AssertionError):  # passes the guard; the fake venue rejects it
        armed.send(request)
    assert armed.sent == {"/exchange": 1}


def test_reader_retries_throttles_and_server_errors() -> None:
    replies = [(429, {}), (502, {}), (200, {"universe": []})]
    seen: list[str] = []

    class Flaky(BaseAdapter):
        def send(self, request: requests.PreparedRequest, **kwargs: Any) -> Any:
            seen.append(request.url)
            status, body = replies.pop(0)
            response = requests.Response()
            response.status_code = status
            response._content = json.dumps(body).encode()
            response.url = request.url
            return response

        def close(self) -> None:
            pass

    clock = FakeClock(T0)
    reader = executor.HlInfoReader(CFG, transport=Flaky())
    reader.bind(executor.HlPacer(CFG, clock=clock, sleep=clock.sleep), clock.sleep)
    assert reader.meta() == {"universe": []}
    assert 10.0 in clock.sleeps and 2.0 in clock.sleeps and len(seen) == 3
    replies[:] = [(400, {})]
    with pytest.raises(core.TechnicalError, match="HTTP 400"):
        reader.all_mids()


def test_pacer_spacing_weight_cap_budget_and_reserve() -> None:
    clock = FakeClock(T0)
    pacer = executor.HlPacer(CFG, clock=clock, sleep=clock.sleep)
    pacer.before("info", 2)
    pacer.before("info", 2)
    assert clock.sleeps == [0.5]
    for _ in range(3):
        pacer.before("info", 60)
    start = clock.now
    pacer.before("info", 60)  # 184 + 60 > 200 within the minute
    assert clock.now - start >= timedelta(seconds=55)
    assert pacer.info_calls == 6 and pacer.info_weight == 244
    assert pacer.reserve_ok()
    held = executor.FINAL_RESERVE_ACTIONS
    # Entries and exits stop the sweep reserve ABOVE the P7 hold-back.
    reserve = CFG.hl_sweep_reserve_actions
    for _ in range(CFG.hl_max_exchange_actions_per_run - reserve - held):
        pacer.before("exchange", 1)
    assert pacer.remaining_actions() == reserve + held and pacer.reserve_ok()
    pacer.before("exchange", 1)
    assert not pacer.reserve_ok()
    for _ in range(reserve - 1):  # the sweep may use its whole reserve...
        pacer.before("exchange", 1)
    with pytest.raises(executor.BudgetExhausted, match="hl_budget_exhausted"):
        pacer.before("exchange", 1)  # ...but not what is held back for P7
    pacer.open_final_reserve()
    for _ in range(held):
        pacer.before("exchange", 1)
    assert pacer.exchange_actions == CFG.hl_max_exchange_actions_per_run
    with pytest.raises(executor.BudgetExhausted, match="hl_budget_exhausted"):
        pacer.before("exchange", 1)  # the configured maximum is never exceeded
    info = executor.HlPacer(CFG, clock=clock, sleep=clock.sleep)
    info.info_weight = CFG.hl_max_info_weight_per_run - (
        CFG.hl_sweep_reserve_weight + executor.FINAL_RESERVE_WEIGHT
    )
    assert info.reserve_ok()
    info.info_weight += 1
    assert not info.reserve_ok()
    info.info_weight = CFG.hl_max_info_weight_per_run - 100
    info.before("info", 20 - 1)  # 81 left: one above the P7 hold-back
    with pytest.raises(executor.BudgetExhausted):
        info.before("info", 2)
    info.open_final_reserve()
    info.before("info", 60)
    with pytest.raises(executor.BudgetExhausted):
        info.before("info", 60)
    calls = executor.HlPacer(CFG, clock=clock, sleep=clock.sleep)
    calls.info_calls = (
        CFG.hl_max_info_calls_per_run
        - CFG.hl_sweep_reserve_calls
        - executor.FINAL_RESERVE_CALLS
    )
    assert calls.reserve_ok() and calls.remaining_calls() == 32
    calls.before("info", 2)
    assert not calls.reserve_ok()  # the info-call budget has a reserve too
    calls.open_final_reserve()  # once released, the reserve is the sweep's alone
    assert calls.reserve_ok() and calls.remaining_calls() == 31


def test_an_exhausted_reserve_stops_entries_but_not_the_sweep(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_day_one(h, "AAA")
    h.venue.orders.clear()
    next_day(h, holding=(E("AAA"),), entries=(E("BBB"),))
    monkeypatch.setattr(executor.HlPacer, "reserve_ok", lambda self: False)
    assert h.run() == 2  # the vanished stop is critical...
    assert criticals(h) == {"stop_missing:AAA"}
    assert len(h.venue.stops("AAA")) == 1  # ...and the sweep used the reserve
    assert (
        not h.actions("updateLeverage", coin="BBB") and "BBB" not in h.venue.positions
    )


# ----------------------------------------------------------------- quiet window


def test_quiet_window_makes_no_hyperliquid_call(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    h.shadow(entries=(E("AAA"),))
    for minute in (57, 59, 0, 3):
        assert h.at(T0.replace(minute=minute)).run() == 0
    assert h.venue.calls == [] and not h.paths.journal.exists()
    assert "quiet window" in capsys.readouterr().out
    assert h.at(T0.replace(minute=59)).main(["probe"]) == 0
    arm = ["--approval", str(h.approval), "--enabled", "--i-accept-live-risk"]
    flatten = ["flatten", "--all", "--reason", "emergency", *arm]
    assert h.main(flatten) == 3  # did not happen: never exit 0
    assert h.main(["canary", "--coin", "BTC", *arm]) == 3
    assert h.venue.calls == [] and not h.paths.journal.exists()


def test_no_entries_after_minute_45_but_the_sweep_runs(h: Harness) -> None:
    open_day_one(h, "AAA")
    h.venue.orders.clear()
    h.shadow(entries=(E("AAA"), E("BBB")))
    assert h.at(T0.replace(hour=1, minute=46)).run() == 2
    assert criticals(h) == {"stop_missing:AAA"}
    assert not h.actions("updateLeverage", coin="BBB")
    assert len(h.venue.stops("AAA")) == 1  # the sweep re-placed the missing stop


def test_a_run_reaching_minute_57_stops_without_a_quiet_window_call(
    h: Harness,
) -> None:
    open_day_one(h, "AAA", "BBB")
    h.venue.orders.clear()
    h.venue.call_times.clear()
    assert h.at(T0.replace(hour=1, minute=56, second=55)).run() == 2
    assert criticals(h) and all(k.startswith("stop_missing:") for k in criticals(h))
    quiet = T0.replace(hour=1, minute=57, second=0)
    assert h.venue.call_times and all(t < quiet for t in h.venue.call_times)
    (end,) = h.of("run_end")[-1:]
    assert end["status"] == "deadline"
    assert {p["code"] for p in end["problems"]} >= {"quiet_window_reached"}
    clock = FakeClock(quiet)
    with pytest.raises(executor.QuietWindowReached):
        executor.HlPacer(CFG, clock=clock, sleep=clock.sleep).before("info", 2)


def test_gateway_refuses_mutations_in_the_quiet_minutes() -> None:
    clock = FakeClock(T0.replace(minute=57))
    env = executor.SleeveEnv(master=MASTER, sub=SUB, agent=AGENT)
    gateway = executor.BaseGateway(
        cfg=CFG,
        env=env,
        markets=core.parse_meta(FakeVenue(clock).info({"type": "meta"})),
        pacer=executor.HlPacer(CFG, clock=clock, sleep=clock.sleep),
        clock=clock,
    )
    with pytest.raises(executor.GatewayRefused, match="quiet"):
        gateway.check("order", "BTC", new_risk=False)
    clock.now = T0
    gateway.check("order", "BTC", new_risk=False)
    gateway.deadline = T0 - timedelta(seconds=1)
    with pytest.raises(executor.GatewayRefused, match="deadline"):
        gateway.check("order", "BTC", new_risk=False)


# ----------------------------------------------------------------- gateway


def _gateway(
    exchange: Any, clock: FakeClock | None = None
) -> executor.SubAccountGateway:
    clock = clock or FakeClock(T0)
    markets = core.parse_meta(FakeVenue(clock).info({"type": "meta"}))
    return executor.SubAccountGateway(
        exchange,
        cfg=CFG,
        env=executor.SleeveEnv(master=MASTER, sub=SUB, agent=AGENT),
        markets=markets,
        pacer=executor.HlPacer(CFG, clock=clock, sleep=clock.sleep),
        clock=clock,
    )


def test_gateway_refuses_every_unsafe_mutation(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    good = FakeExchange(h.venue, h, vault_address=SUB, wallet_address=AGENT)
    stop = {"trigger": {"triggerPx": 96.0, "isMarket": True, "tpsl": "sl"}}
    cases = [
        (FakeExchange(h.venue, h, vault_address=None, wallet_address=AGENT), "BTC"),  # type: ignore[arg-type]
        (FakeExchange(h.venue, h, vault_address=MASTER, wallet_address=AGENT), "BTC"),
        (FakeExchange(h.venue, h, vault_address=SUB, wallet_address=ENGINE), "BTC"),
        (good, "xyz:TSLA"),
        (good, "NOPE"),
        (good, "DEAD"),
    ]
    for exchange, coin in cases:
        with pytest.raises(executor.GatewayRefused):
            _gateway(exchange).order(
                coin, False, 1.0, 96.0, stop, True, "0xd15e" + "0" * 28
            )
    gateway = _gateway(good)
    with pytest.raises(executor.GatewayRefused, match="new risk"):
        gateway.order("AAA", True, 1.0, 100.5, executor.IOC, False, "0xd15e" + "1" * 28)
    with pytest.raises(executor.GatewayRefused, match="new risk"):
        gateway.update_leverage("AAA", 3)
    with pytest.raises(executor.GatewayRefused, match="allow-listed"):
        gateway._mutate("usdClassTransfer", "AAA", new_risk=False, send=_refuse)
    gateway.armed = False
    with pytest.raises(executor.GatewayRefused, match="not armed"):
        gateway.cancel("AAA", 1)
    assert h.calls == []
    gateway.armed = True
    gateway.allow_new_risk = True
    gateway.update_leverage("AAA", 3)
    assert h.calls[-1]["action"] == "updateLeverage" and h.calls[-1]["vault"] == SUB


def test_real_sdk_wiring_signs_for_the_sub_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hyperliquid.exchange as sdk_exchange
    import hyperliquid.utils.signing as signing

    sdk = executor._load_sdk()
    account = Account.create()
    vaults: list[Any] = []
    original = signing.sign_l1_action

    def spy(
        wallet: Any, action: Any, vault: Any, nonce: Any, expires: Any, mainnet: bool
    ) -> Any:
        vaults.append(vault)
        assert mainnet is True
        return original(wallet, action, vault, nonce, expires, mainnet)

    monkeypatch.setattr(signing, "sign_l1_action", spy)
    monkeypatch.setattr(sdk_exchange, "sign_l1_action", spy)
    captured: list[requests.PreparedRequest] = []

    class Capture(BaseAdapter):
        def send(self, request: requests.PreparedRequest, **kwargs: Any) -> Any:
            captured.append(request)
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(_ack({"resting": {"oid": 42}})).encode()
            response.url = request.url
            return response

        def close(self) -> None:
            pass

    meta = {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 40}]}
    exchange = executor.build_exchange(
        sdk, key=account.key.hex(), meta=meta, sub=SUB, cfg=CFG, transport=Capture()
    )
    assert captured == []
    for session in (exchange.session, exchange.info.session):
        assert session.trust_env is False and session.max_redirects == 0
        assert isinstance(
            session.get_adapter(core.HL_URL), executor.HlAllowListTransport
        )
    assert exchange.vault_address == SUB and exchange.account_address is None
    clock = FakeClock(T0)
    gateway = executor.SubAccountGateway(
        exchange,
        cfg=CFG,
        env=executor.SleeveEnv(master=MASTER, sub=SUB, agent=account.address.lower()),
        markets=core.parse_meta(meta),
        pacer=executor.HlPacer(CFG, clock=clock, sleep=clock.sleep),
        clock=clock,
        cloid_cls=sdk.Cloid,
    )
    cloid = core.cloid_for(CFG, SUB, tid("BTC"), "stop", 1)
    expires = _ms(T0) + 45_000
    gateway.set_expires_after(expires)
    trigger = {"trigger": {"triggerPx": 96100.0, "isMarket": True, "tpsl": "sl"}}
    response = gateway.order("BTC", False, 0.012, 96100.0, trigger, True, cloid)
    assert core.parse_order_statuses(response)[0].oid == 42
    (request,) = captured
    assert (
        request.url == "https://api.hyperliquid.xyz/exchange"
        and request.method == "POST"
    )
    body = json.loads(request.body)
    assert body["vaultAddress"] == SUB and body["expiresAfter"] == expires
    assert set(body["signature"]) == {"r", "s", "v"}
    (wire,) = body["action"]["orders"]
    assert wire["t"] == {
        "trigger": {"isMarket": True, "triggerPx": "96100", "tpsl": "sl"}
    }
    assert wire["r"] is True and wire["b"] is False and wire["c"] == cloid
    assert wire["s"] == "0.012" and wire["a"] == 0
    assert vaults == [SUB]


# ----------------------------------------------------------------- identity


def _flip(h: Harness, name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    valid = h.venue.agents[0]["validUntil"]
    if name == "addresses_distinct":
        h.write_env(**{core.ENV_SUB: MASTER})
        h.write_approval(h.approval_doc())
    elif name == "signer_is_agent_of_master":
        h.venue.role = {"role": "user"}
    elif name == "signer_listed":
        h.venue.agents = h.venue.agents[1:]
    elif name == "signer_name_ok":
        h.venue.agents[0]["name"] = f"other valid_until {valid}"
    elif name == "signer_named_hl_api":
        h.venue.agents = [{"name": "hl-api", "address": AGENT, "validUntil": valid}]
    elif name == "engine_entry_with_signer_address":
        h.venue.agents.append({"name": "hl-api", "address": AGENT, "validUntil": valid})
    elif name == "signer_valid":
        h.venue.agents[0]["validUntil"] = _ms(T0 + timedelta(hours=20))
    elif name == "sub_listed_under_master":
        h.venue.subs = []
    elif name == "sub_mode_default":
        h.venue.modes[SUB] = "default"
    elif name == "master_mode_portfolio":
        h.venue.modes[MASTER] = "portfolioMargin"
    elif name == "signer_matches_agent":
        h.write_env(**{core.ENV_AGENT: "0x" + "c7" * 20})
        h.venue.agents[0]["address"] = "0x" + "c7" * 20
        h.venue.role = {"role": "agent", "data": {"user": MASTER}}
        h.write_approval(h.approval_doc())
    elif name == "engine_key_in_environment":
        monkeypatch.setenv(core.ENV_ENGINE_KEY, "0x" + "1" * 64)


@pytest.mark.parametrize(
    "name",
    [
        "addresses_distinct",
        "signer_is_agent_of_master",
        "signer_listed",
        "signer_name_ok",
        "signer_named_hl_api",
        "engine_entry_with_signer_address",
        "signer_valid",
        "sub_listed_under_master",
        "sub_mode_default",
        "master_mode_portfolio",
        "signer_matches_agent",
        "engine_key_in_environment",
    ],
)
def test_identity_refusal_matrix(
    h: Harness,
    name: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    h.shadow(entries=(E("AAA"),))
    _flip(h, name, monkeypatch)
    assert h.run() == 3
    assert h.factory_calls == 0 and h.calls == []
    assert not [c for c in h.venue.calls if c[0] == "exchange"]
    assert not h.of("identity_verified")
    assert_no_secrets(h, outputs(capsys))


def test_identity_report_is_booleans_and_fingerprints(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    assert h.main(["probe"]) == 0
    out = capsys.readouterr().out
    line = next(item for item in out.splitlines() if item.startswith("identity:"))
    for check in (
        "signer_is_agent_of_master=true",
        "signer_not_engine_address=true",
        "sub_listed_under_master=true",
        "engine_agent_listed=true",
        "agent_days_left=170",
        "sub_mode=unifiedAccount",
        f"fp_sub={core.address_fp(SUB)}",
    ):
        assert check in line
    assert "signer_matches_agent" not in line
    assert "risk_per_trade_usd=48.00" in out and "book_equity_usd=4800.00" in out
    assert "est_full_book_margin_usd=2880.00" in out  # 0.6 x book
    assert "webhook_configured=false" in out and "deadman_configured=false" in out
    assert "signing_client=none" in out and h.factory_calls == 0
    kinds = [c[1] for c in h.venue.calls]
    assert kinds.count("userRole") == 1 and "orderStatus" not in kinds
    assert all(user != AGENT for (_, kind, user) in h.venue.calls if kind != "userRole")
    assert_no_secrets(h, out)


def test_identity_is_verified_once_a_day(h: Harness) -> None:
    open_day_one(h, "AAA")
    assert len(h.of("identity_verified")) == 1
    h.venue.calls.clear()
    assert h.at(T0 + timedelta(hours=1)).run() == 0
    assert len(h.of("identity_verified")) == 1
    assert "userRole" not in [c[1] for c in h.venue.calls]
    h.venue.calls.clear()
    next_day(h, holding=(E("AAA"),))
    assert h.run() == 0
    assert len(h.of("identity_verified")) == 2


# ----------------------------------------------------------------- end to end: entries


def test_entry_places_the_stop_from_the_venue_fill(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "fill", "px": 100.2}]
    assert h.run() == 0
    (lev, entry, stop, cancel) = h.actions()
    assert (lev["action"], lev["leverage"], lev["is_cross"]) == (
        "updateLeverage",
        3,
        False,
    )
    assert entry["is_buy"] and entry["sz"] == 12.0 and entry["limit_px"] == 100.5
    assert entry["order_type"] == {"limit": {"tif": "Ioc"}} and not entry["reduce_only"]
    # A1: the IOC carried its stop child in the same action, at the rule
    # distance from the reference mid (100 - 4); the venue placed it on the
    # full fill. The trade's stop is anchored to the venue fill (100.2 - 4):
    # the sleeve places it, then cancels the child (place, then cancel).
    assert entry["grouping"] == "normalTpsl"
    assert entry["child"] == {
        "cloid": child_cloid("AAA"),
        "is_buy": False,
        "sz": 12.0,
        "trigger_px": 96.0,
        "reduce_only": True,
    }
    assert stop["trigger"] and stop["reduce_only"] and not stop["is_buy"]
    assert stop["sz"] == 12.0 and stop["limit_px"] == 96.2
    assert stop["order_type"] == {
        "trigger": {"triggerPx": 96.2, "isMarket": True, "tpsl": "sl"}
    }
    assert (cancel["action"], cancel["cloid"]) == ("cancelByCloid", child_cloid("AAA"))
    (listed,) = h.venue.stops("AAA")
    assert float(listed["triggerPx"]) == 96.2 and float(listed["sz"]) == 12.0
    assert all(c["vault"] == SUB for c in h.calls)
    assert all(c["expires_after"] is not None for c in h.calls)
    for call in h.actions("order"):
        assert call["cloid"].startswith("0xd15e")
    (opened,) = h.of("trade_opened")
    assert opened["stop_px"] == 96.2 == normalize(100.2 - 4.0, 2)
    assert opened["entry_px"] == 100.2 and opened["risk_usd"] == pytest.approx(48.0)
    assert opened["actual_risk_usd"] == pytest.approx(12.0 * 4.0)
    assert opened["book_equity"] == pytest.approx(4800.0) and opened["leverage"] == 3
    assert opened["virtual"] == {"taken": True, "stop_px": 96.0, "priority_rank": 1}
    intents = h.of("intent", role="entry")
    assert intents[0]["context"]["L"] == 3 and intents[0]["context"]["stop_dist"] == 4.0
    assert h.venue.positions["AAA"]["type"] == "isolated"
    (end,) = h.of("run_end")
    assert end["status"] == "ok" and end["counts"]["entries"] == 1
    assert end["counts"]["stops_ok"] == 1 and end["traffic"]["exchange_actions"] == 4
    out = outputs(capsys)
    assert "signing_client=constructed" in out and "stops_ok=1/1" in out
    assert_no_secrets(h, out)


def normalize(px: float, szd: int) -> float:
    return core.normalize_price(px, szd)


def test_same_day_rerun_is_idempotent(h: Harness) -> None:
    open_day_one(h, "AAA", "BBB")
    count = len(h.calls)
    for hour in (1, 2, 5):
        assert h.at(T0.replace(hour=hour)).run() == 0
    assert len(h.calls) == count


def test_untaken_virtual_entries_are_taken_when_real_slots_are_free(h: Harness) -> None:
    h.shadow(entries=(E("AAA", taken=False),))
    assert h.run() == 0
    (opened,) = h.of("trade_opened")
    assert opened["virtual"]["taken"] is False and "AAA" in h.venue.positions
    (note,) = h.of("run_end")[-1]["problems"]  # no webhook or dead-man URL set
    assert (note["code"], note["severity"]) == ("no_offhost_alerts", "notice")


def test_open_virtual_trades_get_no_entry(h: Harness) -> None:
    h.shadow(
        holding=(E("AAA", day=T - 3 * DAY), E("BBB", day=T - 3 * DAY, taken=False))
    )
    assert h.run() == 0
    assert h.calls == [] and not h.venue.positions


def test_priority_order_and_terminal_slots_full(h: Harness) -> None:
    h.venue.usdc[SUB] = 5000.0
    coins = [f"C{i:02d}" for i in range(1, 12)]
    h.shadow(entries=tuple(E(c, atr=10.0) for c in coins))
    assert h.run() == 0
    opened = [e["coin"] for e in h.of("trade_opened")]
    assert opened == coins[:10]
    (skip,) = h.of("skip")
    assert skip["coin"] == "C11" and skip["reason"] == "slots_full"
    assert skip["retryable"] is False
    count = len(h.calls)
    assert h.at(T0.replace(hour=1)).run() == 0
    assert len(h.of("skip")) == 1 and len(h.calls) == count


def test_sub_collateral_is_retried_after_a_top_up(h: Harness) -> None:
    h.venue.usdc[SUB] = 100.0
    h.venue.usdc[MASTER] = 4700.0  # book equity stays 4800
    h.shadow(entries=(E("AAA"),))
    assert h.run() == 0
    (skip,) = h.of("skip")
    assert skip["reason"] == "sub_collateral" and skip["retryable"] is True
    assert skip["collateral_shortfall_usd"] == pytest.approx(1200 / 3 - (100 - 5))
    assert h.at(T0.replace(hour=1)).run() == 0
    assert len(h.of("skip")) == 1  # the same retryable reason is not re-journaled
    h.venue.usdc[SUB] = 2500.0
    assert h.at(T0.replace(hour=2)).run() == 0
    assert [e["coin"] for e in h.of("trade_opened")] == ["AAA"]


def test_partial_fill_keeps_its_size_and_dust_is_closed(h: Harness) -> None:
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["AAA"] = [
        {"mode": "fill", "fraction": 0.5},
        {"mode": "fill", "fraction": 0.5},
    ]
    h.ioc["BBB"] = [{"mode": "fill", "fraction": 0.005}, {"mode": "no_fill"}]
    assert h.run() == 0
    opened = {e["coin"]: e for e in h.of("trade_opened")}
    assert opened["AAA"]["sz"] == 9.0 and opened["AAA"]["fill_fraction"] == 0.75
    assert opened["AAA"]["actual_risk_usd"] == pytest.approx(9.0 * 4.0)
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 9.0
    assert "BBB" not in h.venue.positions
    (closed,) = h.of("trade_closed")
    assert closed["coin"] == "BBB" and closed["reason"] == "dust_fill"
    codes = {p["code"] for p in h.of("run_end")[0]["problems"]}
    assert "partial_fill" in codes
    count = len(h.calls)
    assert h.at(T0.replace(hour=1)).run() == 0
    assert len(h.calls) == count  # no top-up and no re-entry


def test_entry_window_expiry_is_terminal_but_late_exits_run(h: Harness) -> None:
    open_day_one(h, "AAA")
    later = datetime(2026, 9, 28, 7, 15, tzinfo=UTC)
    ledger = h.shadow(
        T + DAY,
        holding=(E("BBB", day=T - DAY),),
        entries=(E("CCC"),),
        past_closes=((tid("AAA"), "stop_intrabar", T),),
    )
    assert ledger
    assert h.at(later).run() == 0
    (skip,) = h.of("skip")
    assert skip["coin"] == "CCC" and skip["reason"] == "window_expired"
    assert skip["retryable"] is False
    (closed,) = h.of("trade_closed")
    assert closed["coin"] == "AAA" and closed["reason"] == "shadow_stop"
    assert (
        closed["late_exit_days"] == 0
        and closed["virtual"]["exit_reason"] == "stop_intrabar"
    )
    assert "AAA" not in h.venue.positions
    codes = {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert {"entry_missed", "shadow_stop_parity_close"} <= codes


# ----------------------------------------------------------------- end to end: ambiguity


def test_ambiguous_entry_resolves_to_filled_without_a_duplicate(h: Harness) -> None:
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}]
    assert h.run() == 0
    assert len(h.actions("order", coin="AAA", trigger=False)) == 1
    assert any(49.0 <= s <= 50.0 for s in h.clock.sleeps)
    assert entry_outcomes(h)[:2] == ["ambiguous", "filled"]
    assert h.of("outcome", status="filled")[0]["venue_status"] == "filled"
    # The lost reply left the child unknown: the sleeve placed its own stop,
    # P7 resolved the child (listed, same price) and kept one of the two.
    child = [o["status"] for o in h.of("outcome", cloid=child_cloid("AAA"))]
    assert child == ["ambiguous", "open"]
    assert len(h.venue.stops("AAA")) == 1 and len(h.of("trade_opened")) == 1


def test_never_landed_entry_retries_with_the_next_cloid(h: Harness) -> None:
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_before"}]
    assert h.run() == 0
    first, second = h.actions("order", coin="AAA", trigger=False)
    assert first["cloid"] != second["cloid"]
    assert first["cloid"] == core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    assert second["cloid"] == core.cloid_for(CFG, SUB, tid("AAA"), "entry", 2)
    assert entry_outcomes(h)[:3] == ["ambiguous", "never_landed", "filled"]
    assert h.venue.positions["AAA"]["szi"] == 12.0
    (stop,) = h.venue.stops("AAA")  # the second attempt's child
    assert stop["cloid"] == child_cloid("AAA", 2)


def test_a_crash_after_the_entry_intent_is_recovered(h: Harness) -> None:
    open_day_one(h, "AAA")
    lines = h.paths.journal.read_text().splitlines(keepends=True)
    events = [json.loads(line) for line in lines]
    cut = next(
        i
        for i, e in enumerate(events)
        if e["event"] == "intent" and e["role"] == "entry"
    )
    h.paths.journal.write_text("".join(lines[: cut + 1]))
    h.venue.orders.clear()  # the stop was never placed before the crash
    count = len(h.actions("order", trigger=False))
    assert h.at(T0.replace(hour=1)).run() == 2  # run_stuck is critical
    assert len(h.actions("order", trigger=False)) == count  # no second entry
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and opened["stop_px"] == 96.0
    assert len(h.venue.stops("AAA")) == 1
    codes = {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert "run_stuck" in codes


# ----------------------------------------------------------------- end to end: venue authority


def test_a_venue_stop_closes_the_journal_trade(h: Harness) -> None:
    open_day_one(h, "AAA")
    h.venue.trigger_stop("AAA")
    h.shadow(entries=(E("AAA"),))
    assert h.at(T0.replace(hour=1)).run() == 0
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "venue_stop" and closed["exit_px"] == 96.0
    (report,) = h.of("trade_report")
    assert report["closed_pnl"] == pytest.approx(-48.0)
    assert report["taker_fee_bps"] == pytest.approx(4.5)
    assert report["net_r"] == pytest.approx((-48.0 - report["fees"]) / 48.0)
    assert report["actual_risk_usd"] == pytest.approx(48.0)
    assert report["net_r_actual"] == pytest.approx(report["net_r"])
    assert report["truncated"] == {"fills": False, "funding": False}
    codes = {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert "real_stopped_early" in codes


def test_a_liquidation_is_critical(h: Harness) -> None:
    open_day_one(h, "AAA")
    h.venue.liquidate("AAA")
    assert h.at(T0.replace(hour=1)).run() == 2
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "liquidation"


def test_a_size_mismatch_is_resized_place_then_cancel(h: Harness) -> None:
    open_day_one(h, "AAA")
    (old,) = h.venue.stops("AAA")
    h.venue.positions["AAA"]["szi"] = 7.0
    h.calls.clear()
    assert h.at(T0.replace(hour=1)).run() == 0
    kinds = [(c["action"], c.get("trigger")) for c in h.calls]
    assert kinds == [("order", True), ("cancelByCloid", None)]
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 7.0 and stop["oid"] != old["oid"]
    assert h.calls[0]["cloid"] == core.cloid_for(CFG, SUB, tid("AAA"), "stop", 2)
    assert h.of("stop_cancelled")[0]["version"] == 1


# ----------------------------------------------------------------- end to end: sweep


def test_sweep_replaces_missing_and_cancels_duplicate_and_flat_orders(
    h: Harness,
) -> None:
    open_day_one(h, "AAA", "BBB")
    h.venue.orders = [o for o in h.venue.orders if o["coin"] != "AAA"]
    (bbb,) = h.venue.stops("BBB")
    dup = h.venue.add_stop(
        "BBB", is_buy=False, sz=12.0, trigger=96.0, cloid="0xd15e" + "f" * 28
    )
    flat = h.venue.add_stop(
        "CCC", is_buy=False, sz=1.0, trigger=90.0, cloid="0xd15e" + "e" * 28
    )
    assert h.at(T0.replace(hour=1)).run() == 2
    assert criticals(h) == {"stop_missing:AAA"}  # BBB's duplicate is not missing
    assert len(h.venue.stops("AAA")) == 1
    assert [o["oid"] for o in h.venue.stops("BBB")] == [bbb["oid"]]
    assert not h.venue.stops("CCC")
    cancelled = {c.get("cloid") for c in h.actions("cancelByCloid")}
    assert {"0xd15e" + "f" * 28, "0xd15e" + "e" * 28} <= cancelled
    assert dup and flat


def test_breach_closes_when_no_stop_rests_beyond_the_mid(h: Harness) -> None:
    open_day_one(h, "AAA")
    h.venue.orders.clear()
    h.venue.mids["AAA"] = 95.0
    assert h.at(T0.replace(hour=1)).run() == 2
    assert criticals(h) == {"stop_missing:AAA"}
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "breach" and "AAA" not in h.venue.positions
    (close,) = h.actions("order", coin="AAA", trigger=False, reduce_only=True)
    assert close["cloid"] == core.cloid_for(CFG, SUB, tid("AAA"), "breach", 1)
    assert close["limit_px"] == normalize(95.0 * 0.99, 2)


def test_a_stop_rejected_twice_closes_the_position(h: Harness) -> None:
    open_day_one(h, "AAA")
    h.venue.orders.clear()
    h.trigger["AAA"] = ["reject", "reject"]
    assert h.at(T0.replace(hour=1)).run() == 2
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "unprotectable" and "AAA" not in h.venue.positions
    codes = {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert "unprotectable" in codes


def test_a_failed_close_leaves_a_critical_unprotected_position(
    h: Harness, sinks: SimpleNamespace
) -> None:
    open_day_one(h, "AAA")
    h.venue.orders.clear()
    h.trigger["AAA"] = ["reject"] * 10
    h.ioc["AAA"] = [{"mode": "no_fill"}] * 20
    assert h.at(T0.replace(hour=1)).run() == 2
    codes = {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert {"unprotected_position", "exit_incomplete", "unprotectable"} <= codes
    assert "AAA" in h.venue.positions and not h.of("trade_closed")
    assert sinks.banners  # the critical reached the local banner


@pytest.mark.parametrize("fault", ["not_isolated", "stop_behind_liquidation"])
def test_leverage_faults_close_the_position(h: Harness, fault: str) -> None:
    open_day_one(h, "AAA")
    if fault == "not_isolated":
        h.venue.positions["AAA"]["type"] = "cross"
    else:
        h.venue.positions["AAA"]["liq"] = 97.0
    assert h.at(T0.replace(hour=1)).run() == 2
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == fault and "AAA" not in h.venue.positions


def test_unknown_positions_are_guarded_never_traded_and_orders_never_touched(
    h: Harness,
) -> None:
    """I9 as amended by A2: a position the sleeve does not own is never
    traded down or closed and still critical, but it gets a protective
    reduce-only stop (no ATR known for the coin: 15% from its entry price);
    an order the sleeve did not place is never touched."""
    h.venue.positions["AAA"] = {
        "szi": 3.0,
        "entryPx": 90.0,
        "type": "cross",
        "value": 5,
        "liq": None,
    }
    h.venue.add_stop("BBB", is_buy=False, sz=1.0, trigger=80.0, cloid=None)
    h.shadow(entries=(E("AAA"), E("BBB"), E("CCC")))
    assert h.run() == 2
    assert {c["coin"] for c in h.calls} == {"AAA", "CCC"}
    (guard,) = h.actions(coin="AAA")
    assert guard["action"] == "order" and guard["trigger"] and guard["reduce_only"]
    assert not guard["is_buy"] and guard["sz"] == 3.0 and guard["limit_px"] == 76.5
    assert guard["cloid"] == core.cloid_for(CFG, SUB, "guard:AAA", "guard", 1)
    (intent,) = h.of("intent", role="guard")
    assert intent["context"]["source"] == "fallback"
    skips = {s["coin"]: s["reason"] for s in h.of("skip")}
    assert skips == {"AAA": "coin_held_unowned", "BBB": "coin_held_unowned"}
    (snapshot,) = h.of("snapshot")
    assert snapshot["slots_used"] == 1 and snapshot["orders"] == {
        "owned": 0,
        "unowned": 1,
    }
    severities = _severities(h)
    assert severities["unknown_position"] == "critical"
    assert severities["position_guarded"] == "notice"
    assert {"unknown_order", "coin_held_unowned"} <= set(severities)
    assert h.venue.positions["AAA"]["szi"] == 3.0 and len(h.venue.stops("BBB")) == 1
    assert h.at(T0 + HOUR).run() == 2  # covered now: no second guard
    assert len(h.actions(coin="AAA")) == 1 and len(h.venue.stops("AAA")) == 1


def test_a_trade_unknown_to_the_shadow_is_held_and_flagged(h: Harness) -> None:
    open_day_one(h, "AAA")
    next_day(h, holding=(E("BBB", day=T - 5 * DAY),))
    assert h.run() == 2
    assert not h.of("trade_closed") and "AAA" in h.venue.positions
    codes = {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert "trade_unknown_to_shadow" in codes


# ----------------------------------------------------------------- exits, STOP, reversal


def test_exits_run_before_entries_and_each_stop_before_the_next_entry(
    h: Harness,
) -> None:
    open_day_one(h, "AAA")
    h.calls.clear()
    next_day(h, holding=(E("AAA"),), exits=("AAA",), entries=(E("BBB"), E("CCC")))
    assert h.run() == 0
    order = [(c["action"], c["coin"], c.get("trigger")) for c in h.calls]
    assert order == [
        ("order", "AAA", False),
        ("cancelByCloid", "AAA", None),
        ("updateLeverage", "BBB", None),
        ("order", "BBB", False),
        ("updateLeverage", "CCC", None),
        ("order", "CCC", False),
    ]
    # Each entry carries its stop in the same action (A1): filled at the
    # reference mid, the child IS the stop from the fill (nothing re-placed).
    for coin in ("BBB", "CCC"):
        (entry,) = h.actions("order", coin=coin)
        assert entry["child"]["trigger_px"] == 96.0
        (stop,) = h.venue.stops(coin)
        assert stop["cloid"] == child_cloid(coin, day=T + DAY)
        (opened,) = h.of("trade_opened", coin=coin)
        assert opened["stop_px"] == 96.0
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "channel_exit" and closed["late_exit_days"] == 0
    assert h.calls[0]["reduce_only"] and not h.calls[0]["is_buy"]


def test_stop_file_blocks_new_risk_but_not_exits_or_repair(h: Harness) -> None:
    open_day_one(h, "AAA", "BBB")
    h.venue.orders = [o for o in h.venue.orders if o["coin"] != "BBB"]
    h.paths.stop_file.write_text("")
    h.calls.clear()
    next_day(h, holding=(E("AAA"), E("BBB")), exits=("AAA",), entries=(E("CCC"),))
    assert h.run() == 2
    assert criticals(h) == {"stop_missing:BBB"}
    assert not h.actions("updateLeverage")
    assert not [c for c in h.actions("order") if not c["reduce_only"]]
    assert "AAA" not in h.venue.positions and len(h.venue.stops("BBB")) == 1
    (skip,) = h.of("skip")
    assert skip["reason"] == "stop_file" and skip["retryable"] is True
    assert h.of("run_start")[-1]["stop_file_present"] is True


def test_reversal_exits_then_enters_the_other_side(h: Harness) -> None:
    open_day_one(h, "AAA")
    h.calls.clear()
    next_day(h, holding=(E("AAA"),), exits=("AAA",), entries=(E("AAA", side="short"),))
    h.venue.mids["AAA"] = 98.0
    assert h.run() == 0
    assert h.venue.positions["AAA"]["szi"] < 0
    assert [e["trade_id"] for e in h.of("trade_opened")] == [
        tid("AAA"),
        tid("AAA", "short", T + DAY),
    ]
    short = h.of("trade_opened")[-1]
    assert short["leverage"] == 2 and short["label"] == "hedge"
    assert short["entry_px"] == 98.0 and short["stop_px"] == 102.0
    (stop,) = h.venue.stops("AAA")
    assert stop["side"] == "B" and float(stop["triggerPx"]) == 102.0
    # The closed long's report counts only its own fills, not the short's entry.
    (report,) = h.of("trade_report")
    assert report["trade_id"] == tid("AAA") and report["avg_exit_px"] == 98.0
    assert report["closed_pnl"] == pytest.approx(-24.0)
    assert report["fees"] == pytest.approx((12 * 100.0 + 12 * 98.0) * 4.5e-4)
    assert report["net_r"] == pytest.approx((-24.0 - report["fees"]) / 48.0)
    (closed,) = h.of("trade_closed")
    assert closed["exit_px"] == 98.0


# ----------------------------------------------------------------- shadow handling


def test_stale_shadow_blocks_entries_and_alerts_by_hour(h: Harness) -> None:
    open_day_one(h, "AAA")
    h.venue.orders.clear()
    h.at(T0 + DAY)  # the shadow did not run for the 27th
    assert h.run() == 2
    assert criticals(h) == {"stop_missing:AAA"}
    assert len(h.venue.stops("AAA")) == 1
    codes = {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert "shadow_stale" not in codes
    assert h.at(T0 + DAY + timedelta(hours=4)).run() == 0
    (stale,) = [
        p for p in h.of("run_end")[-1]["problems"] if p["code"] == "shadow_stale"
    ]
    assert stale["severity"] == "notice"
    assert h.at(T0 + DAY + timedelta(hours=12)).run() == 2
    (stale,) = [
        p for p in h.of("run_end")[-1]["problems"] if p["code"] == "shadow_stale"
    ]
    assert stale["severity"] == "critical"
    assert len(h.of("trade_opened")) == 1


def test_an_unstable_shadow_ledger_is_retried_then_unavailable(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow(entries=(E("AAA"),))
    ticks = iter(range(10_000))
    monkeypatch.setattr(executor, "_ledger_stat", lambda path: (next(ticks), 0))
    assert h.run() == 0
    assert h.clock.sleeps.count(10.0) == CFG.shadow_read_retries
    codes = {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert "shadow_unavailable" in codes and not h.of("trade_opened")


def test_the_shadow_lock_file_is_never_opened(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow(entries=(E("AAA"),))
    lock = h.paths.shadow_ledger.with_name("ledger.jsonl.lock")
    lock.write_text("")
    opened: list[str] = []
    real_io, real_os = io.open, os.open

    def io_spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(file))
        return real_io(file, *args, **kwargs)

    def os_spy(path: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(path))
        return real_os(path, *args, **kwargs)

    monkeypatch.setattr(io, "open", io_spy)
    monkeypatch.setattr(os, "open", os_spy)
    assert h.run() == 0
    assert str(h.paths.shadow_ledger) in opened
    assert not [name for name in opened if name.endswith("ledger.jsonl.lock")]


def test_a_changed_shadow_runner_is_refused(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow(entries=(E("AAA"),))
    monkeypatch.setattr(executor, "runner_file_sha256", lambda: "0" * 64)
    assert h.run(armed=False) == 3
    assert h.run() == 3
    assert h.venue.calls == [] and h.factory_calls == 0


def test_a_shadow_config_mismatch_skips_shadow_phases(h: Harness) -> None:
    open_day_one(h, "AAA")
    ledger = ShadowLedger()
    ledger.mark(T, fingerprint="f" * 16)
    ledger.write(h.paths.shadow_ledger)
    h.venue.orders.clear()
    assert h.at(T0 + DAY).run() == 2
    assert len(h.venue.stops("AAA")) == 1 and not h.of("trade_closed")
    codes = {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert "shadow_config_mismatch" in codes


# ----------------------------------------------------------------- flatten, canary, status


def test_flatten_all_closes_owned_positions_only(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    open_day_one(h, "AAA", "BBB")
    h.venue.positions["CCC"] = {
        "szi": 2.0,
        "entryPx": 90.0,
        "type": "cross",
        "value": 5,
        "liq": None,
    }
    h.paths.stop_file.write_text("")
    argv = [
        "flatten",
        "--all",
        "--reason",
        "rollback 0x" + "ab" * 20,
        "--approval",
        str(h.approval),
        "--enabled",
        "--i-accept-live-risk",
    ]
    assert h.at(T0.replace(hour=2)).main(argv) == 2  # the unowned CCC stays critical
    assert set(h.venue.positions) == {"CCC"}
    closed = h.of("trade_closed")
    assert {c["coin"] for c in closed} == {"AAA", "BBB"}
    assert {c["reason"] for c in closed} == {"manual_flatten"}
    assert closed[0]["operator_reason"] == "rollback 0x<addr>"
    # The unowned CCC is never closed, but ends guarded by a reduce-only
    # stop (A2); nothing else is left resting.
    (guard,) = [c for c in h.calls if c.get("coin") == "CCC"]
    assert guard["trigger"] and guard["reduce_only"] and not guard["is_buy"]
    assert guard["sz"] == 2.0 and h.venue.positions["CCC"]["szi"] == 2.0
    assert [o["coin"] for o in h.venue.orders] == ["CCC"]
    assert all(c["cloid"].startswith("0xd15e") for c in h.actions("order"))
    assert_no_secrets(h, outputs(capsys))


def test_canary_runs_every_step_and_reports_booleans(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    h.shadow()
    argv = [
        "canary",
        "--coin",
        "BTC",
        "--approval",
        str(h.approval),
        "--enabled",
        "--i-accept-live-risk",
    ]
    assert h.main(argv) == 0
    out = capsys.readouterr().out
    for name in (
        "canary_leverage_ok",
        "canary_entry_ack_parsed",
        "canary_entry_filled",
        "canary_isolated_ok",
        "canary_liq_px_present",
        "canary_liq_behind_stop",
        "canary_stop_resting",
        "canary_stop_listed",
        "canary_stop_reduce_only",
        "canary_stop_cloid_field_present",
        "canary_stop_cloid_matches",
        "canary_stop_trigger_px_matches",
        "canary_stop_sz_matches",
        "canary_stop_order_type_ok",
        "canary_order_status_by_cloid_ok",
        "canary_stop_survives_expiry",
        "canary_child_listed",
        "canary_child_cloid_matches",
        "canary_child_trigger_px_matches",
        "canary_child_sz_matches",
        "canary_child_order_type_ok",
        "canary_small_reduce_only_accepted",
        "canary_flat",
        "canary_no_orders_left",
    ):
        assert f"{name}=true" in out, name
    # A1: the canary's entry is the live entry shape: the IOC and its stop
    # child at 0.9 x the reference mid, one normalTpsl action.
    child_intent, stop_intent = h.of("intent", role="canary_stop")
    assert (
        child_intent["context"]["child_of"]
        == h.of("intent", role="canary_entry")[0]["cloid"]
    )
    assert child_intent["trigger_px"] == 90_000.0 and child_intent["grouping"]
    # The stop is re-queried only after its action's expiresAfter has passed.
    queried = [
        when
        for call, when in zip(h.venue.calls, h.venue.call_times)
        if call[1] == "orderStatus"
    ]
    assert len(queried) == 2
    assert _ms(queried[-1]) >= stop_intent["expires_after_ms"] + 5000
    assert "canary_taker_fee_bps=4.50" in out and "canary_leverage=3.00" in out
    assert not h.venue.positions and not h.venue.orders
    (leverage,) = h.actions("updateLeverage")
    assert leverage["leverage"] == 3 and leverage["is_cross"] is False
    entry = h.actions("order")[0]
    assert entry["sz"] == 0.00015 and entry["limit_px"] == 100_500.0
    assert entry["child"]["sz"] == 0.00015 and entry["child"]["trigger_px"] == 90_000.0
    cancels = {c["cloid"] for c in h.actions("cancelByCloid")}
    assert cancels == {child_intent["cloid"], stop_intent["cloid"]}
    (stop,) = h.actions("order", trigger=True)
    assert stop["sz"] * stop["limit_px"] >= CFG.min_order_usd  # $13.50 at 0.9 x
    assert "canary_stop_notional_usd=13.50" in out
    (result,) = h.of("canary_result")
    assert result["kind"] == "canary" and all(result["checks"].values())
    assert all(e.get("kind") == "canary" for e in h.of("intent"))
    assert not h.of("trade_opened")


def test_canary_failure_after_the_fill_flattens(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    h.shadow()
    h.trigger["BTC"] = ["reject"]
    argv = [
        "canary",
        "--coin",
        "BTC",
        "--approval",
        str(h.approval),
        "--enabled",
        "--i-accept-live-risk",
    ]
    assert h.main(argv) == 2
    out = capsys.readouterr().out
    assert "canary_stop_resting=false" in out and "canary_flat=true" in out
    assert not h.venue.positions and not h.venue.orders
    codes = {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert "canary_failed" in codes


def test_canary_without_flags_prints_the_plan(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    assert h.main(["canary", "--coin", "BTC"]) == 0
    out = capsys.readouterr().out
    assert '"plan":"canary"' in out and h.venue.calls == []


def test_status_is_offline_unless_asked_for_the_venue(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    open_day_one(h, "AAA")
    capsys.readouterr()
    h.venue.calls.clear()
    assert h.main(["status", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert h.venue.calls == []
    assert doc["open_trades"][0]["coin"] == "AAA" and doc["runner_sha_ok"] is True
    assert doc["shadow"]["shadow_state"] == "fresh"
    assert h.main(["status", "--venue"]) == 0
    assert len(h.venue.calls) <= 4
    out = capsys.readouterr().out
    assert "venue:" in out
    assert_no_secrets(h, out)


# ----------------------------------------------------------------- alerts and hygiene


def test_alert_dedup_reminders_and_critical_webhook(
    tmp_path: Path, sinks: SimpleNamespace
) -> None:
    paths = core.Paths.default(tmp_path)
    crit = executor.Problem("unknown_position", "critical", "unknown_position:AAA", "x")
    note = executor.Problem("partial_fill", "notice", "partial_fill:BBB", "0.5")
    now = T0

    def send(problems: dict, previous: dict | None, when: datetime) -> tuple:
        return executor.dispatch_alerts(
            problems=problems,
            previous=previous,
            now=when,
            cfg=CFG,
            paths=paths,
            webhook=WEBHOOK,
        )

    last, alerted = send({note.key: note}, None, now)
    assert [p.key for p in alerted] == [note.key] and sinks.webhooks == []
    status = {"problems": [note.record()], "last_alerted": last}
    last, alerted = send({note.key: note}, status, now + timedelta(hours=7))
    assert alerted == []  # unchanged notices never remind
    both = {note.key: note, crit.key: crit}
    last, alerted = send(both, status, now)
    assert len(sinks.webhooks) == 1 and sinks.webhooks[0][0] == WEBHOOK
    assert sinks.webhooks[0][1]["alert_class"] == "backend_critical"
    status = {"problems": [note.record(), crit.record()], "last_alerted": last}
    assert send(both, status, now + timedelta(hours=5))[1] == []
    last, alerted = send(both, status, now + timedelta(hours=6))
    assert [p.key for p in alerted] == [crit.key] and len(sinks.webhooks) == 2
    last, alerted = send({}, status, now + timedelta(hours=7))
    assert last == {} and len(sinks.webhooks) == 2
    records = [json.loads(line) for line in paths.alerts.read_text().splitlines()]
    assert records[-1]["title"] == executor.RECOVERED_TITLE
    assert len(sinks.banners) == len(records)
    assert WEBHOOK not in paths.alerts.read_text()


def test_armed_run_writes_status_alerts_and_pings(
    h: Harness, sinks: SimpleNamespace, capsys: pytest.CaptureFixture
) -> None:
    h.write_env(
        **{
            core.ENV_WEBHOOK: WEBHOOK,
            core.ENV_DEADMAN: "https://dead.example.invalid/p",
        }
    )
    h.write_approval(h.approval_doc())
    h.venue.positions["DDD"] = {
        "szi": 1.0,
        "entryPx": 90.0,
        "type": "cross",
        "value": 5,
        "liq": None,
    }
    h.shadow(entries=(E("AAA"),))
    assert h.run() == 2
    status = json.loads(h.paths.status.read_text())
    assert status["last_run"]["mode"] == "armed" and status["slots"]["used"] == 2
    assert {p["code"] for p in status["problems"]} == {
        "unknown_position",
        "position_guarded",  # A2: the unowned DDD got a protective stop
    }
    assert "no_offhost_alerts" not in {p["code"] for p in status["problems"]}
    assert len(sinks.webhooks) == 1 and sinks.pings == [
        "https://dead.example.invalid/p"
    ]
    alerts = {a["code"]: a["severity"] for a in h.of("alert")}
    assert alerts == {"unknown_position": "critical", "position_guarded": "notice"}
    assert h.at(T0.replace(hour=1)).run() == 2
    assert len(sinks.webhooks) == 1  # unchanged problem set, no reminder yet
    assert h.at(T0.replace(hour=7)).run() == 2
    assert len(sinks.webhooks) == 2  # the critical reminder after 6 h
    text = outputs(capsys)
    assert WEBHOOK not in text and "dead.example" not in text
    assert_no_secrets(h, text)
    assert WEBHOOK not in h.paths.journal.read_text()
    assert WEBHOOK not in h.paths.status.read_text()


def test_budget_exhaustion_is_critical(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow(entries=(E("AAA"),))
    tight = core.SleeveConfig(hl_max_info_calls_per_run=8)
    monkeypatch.setattr(executor, "SleeveConfig", lambda: tight)
    assert h.run(armed=False) == 2
    assert not h.paths.journal.exists()


# ----------------------------------------------------------------- review round 1

HOUR = timedelta(hours=1)
ARM = ("--enabled", "--i-accept-live-risk")


def _severities(h: Harness) -> dict[str, str]:
    return {p["code"]: p["severity"] for p in h.of("run_end")[-1]["problems"]}


def _exchange_times(h: Harness) -> list[datetime]:
    times = [t for c, t in zip(h.venue.calls, h.venue.call_times) if c[0] == "exchange"]
    assert len(times) == len(h.calls)
    return times


def test_gross_drift_on_owned_positions_is_a_notice_not_a_critical(
    h: Harness,
) -> None:
    coins = tuple(f"C{i:02d}" for i in range(1, 11))
    h.shadow(entries=tuple(E(c) for c in coins))
    assert h.run() == 0
    held = dict(h.venue.positions)
    gross = sum(abs(p["szi"]) * h.venue.mids[c] for c, p in held.items())
    assert gross <= 1.5 * 4800.0 + 1e-6  # the cap held at entry
    for coin, pos in held.items():  # a correlated -3% move; no stop is touched
        h.venue.mids[coin] = 97.0
        h.venue.usdc[SUB] -= abs(pos["szi"]) * 3.0
    assert h.at(T0 + HOUR).run() == 0
    problems = {p["code"]: p for p in h.of("run_end")[-1]["problems"]}
    assert problems["gross_drift"]["severity"] == "notice"
    assert "unowned=0" in problems["gross_drift"]["message"]
    assert "gross_to_book=1.5" in problems["gross_drift"]["message"]
    assert "slots_gross_violation" not in problems
    assert all(len(h.venue.stops(c)) == 1 for c in held)
    assert not h.of("trade_closed")  # nothing is sold to restore the ratio


def test_gross_over_the_cap_with_unowned_exposure_is_critical(h: Harness) -> None:
    open_day_one(h, "AAA")
    h.venue.positions["DDD"] = {
        "szi": 70.0,
        "entryPx": 100.0,
        "type": "cross",
        "value": 5,
        "liq": None,
    }
    assert h.at(T0 + HOUR).run() == 2
    problems = {p["code"]: p for p in h.of("run_end")[-1]["problems"]}
    assert problems["slots_gross_violation"]["severity"] == "critical"
    assert "unowned=1" in problems["slots_gross_violation"]["message"]


def test_exits_free_collateral_and_equity_for_entries_at_the_same_open(
    h: Harness,
) -> None:
    h.venue.hold_margin = True
    h.venue.usdc = {MASTER: 4200.0, SUB: 600.0}
    open_day_one(h, "AAA")
    (first,) = h.of("trade_opened")
    assert first["notional"] == pytest.approx(1200.0) and first["scaled"] is False
    h.venue.realize = True
    next_day(h, holding=(E("AAA"),), exits=("AAA",), entries=(E("BBB"),))
    h.venue.mids["AAA"] = 97.0  # the exit realises -36 plus its fee
    assert h.run() == 0
    snapshot = h.of("snapshot")[-1]
    assert snapshot["sub_free"] == pytest.approx(200.0)  # 600 - 1200 / 3 held
    book = 4800.0 - 36.0 - 12 * 97.0 * 4.5e-4
    (bbb,) = h.of("trade_opened", coin="BBB")
    assert bbb["book_equity"] == pytest.approx(book)
    assert bbb["risk_usd"] == pytest.approx(0.01 * book)
    assert bbb["scaled"] is False and bbb["sz"] == 11.9  # not the stale $510
    assert "scaled_by_cap" not in _severities(h)


def test_the_info_call_reserve_stops_entries_before_the_budget_runs_out(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow(entries=(E("AAA"),))
    original = executor.SleeveSession.p6_entries

    def squeezed(self: executor.SleeveSession) -> None:
        cfg = self.cfg
        self.pacer.info_calls = (
            cfg.hl_max_info_calls_per_run - cfg.hl_sweep_reserve_calls + 1
        )
        assert not self.pacer.reserve_ok()
        return original(self)

    monkeypatch.setattr(executor.SleeveSession, "p6_entries", squeezed)
    assert h.run() == 0
    assert h.calls == [] and "AAA" not in h.venue.positions
    (end,) = h.of("run_end")
    assert end["status"] == "ok" and "hl_budget_exhausted" not in _severities(h)


def _fault(h: Harness, fault: str) -> None:
    if fault == "torn_journal":
        with h.paths.journal.open("ab") as handle:
            handle.write(b'{"schema":"d1_sleeve_journal_v1","event":"outc')
    elif fault == "stale_approval":
        doc = h.approval_doc()
        doc["code"]["scripts/d1_sleeve_executor.py"] = "0" * 64  # a merged edit
        h.write_approval(doc)
    elif fault == "env_mode":
        h.env_file.chmod(0o644)
    elif fault == "missing_key":
        h.write_env(**{core.ENV_KEY: None, core.ENV_WEBHOOK: WEBHOOK})


@pytest.mark.parametrize(
    ("fault", "code", "exit_code", "webhook"),
    [
        ("torn_journal", "preflight_failed", 2, True),
        ("stale_approval", "preflight_refused", 3, True),
        ("env_mode", "preflight_refused", 3, False),
        ("missing_key", "preflight_refused", 3, True),
    ],
)
def test_armed_refusals_before_the_session_alert_off_the_log(
    h: Harness,
    sinks: SimpleNamespace,
    capsys: pytest.CaptureFixture,
    fault: str,
    code: str,
    exit_code: int,
    webhook: bool,
) -> None:
    h.write_env(**{core.ENV_WEBHOOK: WEBHOOK, core.ENV_DEADMAN: "https://d.invalid/p"})
    h.write_approval(h.approval_doc())
    open_day_one(h, "AAA")
    for sink in (sinks.banners, sinks.webhooks, sinks.pings):
        sink.clear()
    _fault(h, fault)
    assert h.at(T0 + HOUR).run() == exit_code
    assert sinks.banners and sinks.banners[-1][0] == executor.CRITICAL_TITLE
    assert bool(sinks.webhooks) is webhook and sinks.pings == []
    status = json.loads(h.paths.status.read_text())
    assert [p["code"] for p in status["problems"]] == [code]
    assert status["preflight"]["result"] == code
    banners = len(sinks.banners)
    assert h.at(T0 + 2 * HOUR).run() == exit_code
    assert len(sinks.banners) == banners  # deduplicated...
    assert h.at(T0 + 8 * HOUR).run() == exit_code
    assert len(sinks.banners) == banners + 1  # ...and reminded after 6 h
    text = outputs(capsys)
    assert WEBHOOK not in text and WEBHOOK not in h.paths.status.read_text()
    assert_no_secrets(h, text)


def test_a_cleared_preflight_refusal_recovers_on_the_next_run(
    h: Harness, sinks: SimpleNamespace
) -> None:
    h.write_env(**{core.ENV_WEBHOOK: WEBHOOK})
    open_day_one(h, "AAA")
    good = h.approval.read_text()
    _fault(h, "stale_approval")
    assert h.at(T0 + HOUR).run() == 3
    h.approval.write_text(good)
    assert h.at(T0 + 2 * HOUR).run() == 0
    status = json.loads(h.paths.status.read_text())
    assert status["problems"] == [] and sinks.banners[-1][0] == executor.RECOVERED_TITLE


def test_dry_refusals_never_write_or_alert(h: Harness, sinks: SimpleNamespace) -> None:
    h.shadow(entries=(E("AAA"),))
    h.env_file.chmod(0o644)
    assert h.run(armed=False) == 3
    assert sinks.banners == [] and not h.paths.status.exists()


def test_two_checkouts_cannot_trade_the_same_sub_account_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    live = Harness(tmp_path / "live")
    other = Harness(tmp_path / "worktree")
    other.venue, other.clock, other.env_file = live.venue, live.clock, live.env_file
    other.paths = replace(other.paths, host_lock_dir=live.paths.host_lock_dir)
    other.write_approval(other.approval_doc())
    for harness in (live, other):
        harness.shadow(entries=(E("AAA"),))
    original = executor.SleeveSession.p6_entries
    nested: list[int] = []

    def interleave(self: executor.SleeveSession) -> None:
        if not nested:  # the other checkout runs while this one trades
            nested.append(other.run())
        return original(self)

    monkeypatch.setattr(executor.SleeveSession, "p6_entries", interleave)
    assert live.at(T0).run() == 0
    assert nested == [0] and "holds this sub-account's lock" in outputs(capsys)
    assert live.paths.lock != other.paths.lock
    assert live.venue.positions["AAA"]["szi"] == pytest.approx(12.0)  # one entry
    assert len(live.actions("order", coin="AAA", trigger=False)) == 1
    assert not other.paths.journal.exists()
    assert live.paths.host_lock(core.address_fp(SUB)).exists()


def test_an_interrupted_canary_is_flagged_and_flatten_closes_it(
    h: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    h.shadow()
    original = executor.SleeveSession.send_order

    def killed(self: executor.SleeveSession, **kwargs: Any) -> Any:
        if kwargs.get("role") == "canary_stop":  # SIGKILL after the fill
            raise KeyboardInterrupt("process killed")
        return original(self, **kwargs)

    monkeypatch.setattr(executor.SleeveSession, "send_order", killed)
    arm = ["--approval", str(h.approval), *ARM]
    with pytest.raises(KeyboardInterrupt):
        h.main(["canary", "--coin", "BTC", *arm])
    monkeypatch.setattr(executor.SleeveSession, "send_order", original)
    # A1: the kill came before the canary's own stop, but its entry's child
    # rests: the residue is protected at the venue from the fill on.
    (child,) = h.venue.stops("BTC")
    assert child["reduceOnly"] and child["side"] == "A"
    assert child["cloid"] == h.of("intent", role="canary_stop")[0]["cloid"]
    assert "BTC" in h.venue.positions
    assert set(h.book().canary_residue()) == {"BTC"}
    assert h.at(T0 + HOUR).run() == 2
    severities = _severities(h)
    assert severities["canary_residue"] == "critical"
    assert "unknown_position" not in severities
    assert "BTC" in h.venue.positions  # the hourly run never trades it
    capsys.readouterr()
    flatten = ["flatten", "--coin", "BTC", "--reason", "canary residue", *arm]
    assert h.at(T0 + 2 * HOUR).main(flatten) == 0
    assert "BTC" not in h.venue.positions and not h.venue.orders
    closes = h.actions("order", coin="BTC", trigger=False, reduce_only=True)
    assert closes and all(c["cloid"].startswith("0xd15e") for c in closes)
    assert '"closed":"canary_residue"' in capsys.readouterr().out
    assert h.book().canary_residue() == {}
    assert h.at(T0 + 3 * HOUR).run() == 0


def test_a_canary_whose_stop_echo_differs_fails_and_flattens(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    h.shadow()
    h.venue.trigger_echo_scale = 1.001  # the venue reformats the trigger price
    arm = ["--approval", str(h.approval), *ARM]
    assert h.main(["canary", "--coin", "BTC", *arm]) == 2
    out = capsys.readouterr().out
    assert "canary_stop_trigger_px_matches=false" in out
    assert "canary_stop_sz_matches=true" in out and "canary_flat=true" in out
    assert not h.venue.positions and not h.venue.orders
    assert h.book().canary_residue() == {}


def _day_two_with_a_full_window(h: Harness, scenario: str) -> None:
    btc = E("BTC", px=100_000.0, atr=2000.0)
    h.shadow(entries=(btc, E("AAA")))
    assert h.run() == 0
    if scenario == "repair_after_reconcile":
        h.venue.trigger_stop("BTC")  # P2 reads the fills (weight 21)...
        h.venue.orders = [o for o in h.venue.orders if o["coin"] != "AAA"]
        later: dict[str, Any] = {"holding": (btc, E("AAA"))}
    else:
        (stop,) = h.venue.stops("BTC")
        h.venue.add_stop(  # an owned duplicate: the sweep cancels it first
            "BTC",
            is_buy=False,
            sz=float(stop["sz"]),
            trigger=float(stop["triggerPx"]),
            cloid="0xd15e" + "ab" * 14,
        )
        later = {
            "holding": (btc, E("AAA")),
            "exits": ("BTC",),
            "entries": (E("BBB", day=T + DAY),),
        }
    h.calls.clear()
    h.venue.calls.clear()
    h.venue.call_times.clear()
    h.clock.sleeps.clear()
    next_day(h, **later)


@pytest.mark.parametrize("scenario", ["repair_after_reconcile", "exit_then_entry"])
def test_no_exchange_action_waits_between_its_expiry_and_its_post(
    h: Harness, scenario: str
) -> None:
    _day_two_with_a_full_window(h, scenario)
    expected = {"stop_missing:AAA"} if scenario == "repair_after_reconcile" else set()
    assert h.run() == (2 if expected else 0)
    assert criticals(h) == expected
    assert any(s > 30 for s in h.clock.sleeps)  # the 200/min window filled up
    assert h.calls  # ...while exchange actions were due
    # Pacing (spacing and the weight window) happens BEFORE the expiry is
    # fixed: every action leaves with its full 45 s, never after its expiry.
    for call, when in zip(h.calls, _exchange_times(h)):
        assert call["expires_after"] - _ms(when) == 45_000, call["action"]


def test_each_stop_follows_its_fill_without_a_window_wait(h: Harness) -> None:
    coins = ("AAA", "BBB", "CCC", "DDD", "C01", "C02")
    h.shadow(entries=tuple(E(c) for c in coins))
    assert h.run() == 0
    assert any(s > 30 for s in h.clock.sleeps)  # identity filled the window
    # A1: every entry action carries its stop; the venue places it with the
    # fill, so no window wait (or anything else) can come between them.
    for coin in coins:
        (entry,) = h.actions("order", coin=coin)
        assert entry["child"]["reduce_only"] and entry["child"]["sz"] == entry["sz"]
        (stop,) = h.venue.stops(coin)
        assert stop["cloid"] == entry["child"]["cloid"]
    # Without a child (the fallback), the sleeve's own stop still follows
    # its fill within seconds.
    fallback = Harness(h.tmp / "fallback")
    no_children(fallback, *coins)
    fallback.shadow(entries=tuple(E(c) for c in coins))
    assert fallback.run() == 0
    placed: dict[str, list[datetime]] = {}
    for (kind, action, coin), when in zip(
        fallback.venue.calls, fallback.venue.call_times
    ):
        if kind == "exchange" and action == "order":
            placed.setdefault(coin, []).append(when)
    for coin in coins:
        entry_at, stop_at = placed[coin]
        assert stop_at - entry_at < timedelta(seconds=5), coin


def test_a_stop_file_touched_mid_run_blocks_the_next_entries(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow(entries=(E("AAA"), E("BBB")))
    original = executor.SleeveSession.open_trade

    def then_touch(self: executor.SleeveSession, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        self.paths.stop_file.write_text("")

    monkeypatch.setattr(executor.SleeveSession, "open_trade", then_touch)
    assert h.run() == 0
    assert "AAA" in h.venue.positions and len(h.venue.stops("AAA")) == 1
    assert "BBB" not in h.venue.positions and not h.actions(coin="BBB")
    (skip,) = h.of("skip")
    assert skip["coin"] == "BBB" and skip["reason"] == "stop_file"


def test_the_final_check_rereads_orders_before_closing_as_unprotectable(
    h: Harness,
) -> None:
    open_day_one(h, "AAA")
    h.venue.order_reads = 0
    h.venue.lag_reads = {3}  # P1, P7 refresh, then the final read lags
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0
    assert h.venue.order_reads == 4 and h.calls == []
    assert "AAA" in h.venue.positions and not h.of("trade_closed")
    assert h.of("run_end")[-1]["counts"]["stops_ok"] == 1
    # H3: the re-read waits REREAD_DELAY_S like every other re-read (the
    # pacer's 0.5 s spacing alone would not outlast a lagging info node).
    reads = [
        when
        for call, when in zip(h.venue.calls, h.venue.call_times)
        if call[1] == "frontendOpenOrders"
    ]
    assert reads[-1] - reads[-2] >= timedelta(seconds=executor.REREAD_DELAY_S)


def test_a_direction_conflict_skips_entries_as_not_flat(h: Harness) -> None:
    open_day_one(h, "AAA")
    h.venue.positions["AAA"]["szi"] = -12.0  # the venue side opposes the journal
    h.venue.positions["AAA"]["liq"] = 150.0  # a short's liquidation is above
    next_day(h, holding=(E("AAA"),), exits=("AAA",), entries=(E("AAA", side="short"),))
    h.calls.clear()
    assert h.run() == 2
    (skip,) = h.of("skip")
    assert skip["reason"] == "coin_not_flat" and skip["retryable"] is True
    severities = _severities(h)
    assert severities["direction_conflict"] == "critical"
    assert "coin_held_unowned" not in severities
    assert h.venue.positions["AAA"]["szi"] == -12.0
    # A2: the long's sell stop does not cover a short; the short gets a buy
    # guard at the rule distance its entry was sized with (2 x ATR = 4).
    (guard,) = h.actions(coin="AAA")
    assert guard["trigger"] and guard["reduce_only"] and guard["is_buy"]
    assert guard["sz"] == 12.0 and guard["limit_px"] == 104.0
    assert h.of("intent", role="guard")[0]["context"]["source"] == "journal_atr"
    assert severities["position_guarded"] == "notice"


def test_paged_history_keeps_same_timestamp_items_and_flags_truncation() -> None:
    history: list[dict] = []

    def fill(hours: int) -> None:
        history[:] = [
            {
                "time": 1_000 + hour * 3_600_000,
                "hash": f"0x{hour:064x}",
                "delta": {"type": "funding", "coin": coin, "usdc": "-0.01"},
            }
            for hour in range(hours)
            for coin in ("AAA", "BBB", "CCC")
        ]

    def post(payload: dict) -> list:
        start, end = payload["startTime"], payload["endTime"]
        page = [x for x in history if start <= x["time"] <= end]
        return page[: executor.FUNDING_PAGE_LIMIT]

    def reader() -> executor.HlInfoReader:
        clock = FakeClock(T0)
        info = executor.HlInfoReader(CFG, post=post)
        info.bind(executor.HlPacer(CFG, clock=clock, sleep=clock.sleep), clock.sleep)
        return info

    fill(400)  # 1,200 items; 500-item pages end inside an hour's three coins
    got = reader().user_funding(SUB, 0, 10**13)
    assert len(got) == 1200 and not got.truncated
    assert len(core.parse_funding(got)) == 1200
    fill(800)
    got = reader().user_funding(SUB, 0, 10**13)
    assert len(got) == executor.MAX_REPORT_ITEMS and got.truncated
    history[:] = [dict(history[0], hash=f"0x{i:064x}") for i in range(600)]
    got = reader().user_funding(SUB, 0, 10**13)  # a full page of one timestamp
    assert len(got) == executor.FUNDING_PAGE_LIMIT and got.truncated


# ----------------------------------------------------------------- review round 2


def _late_entries(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """A long candidate queue: the entry phase reaches its entry at :45:40."""
    original = executor.SleeveSession.enter

    def late(self: executor.SleeveSession, entry: core.VirtualEntry) -> None:
        h.clock.now = max(h.clock.now, h.clock.now.replace(minute=45, second=40))
        return original(self, entry)

    monkeypatch.setattr(executor.SleeveSession, "enter", late)


def _bad_order_status(h: Harness, monkeypatch: pytest.MonkeyPatch) -> Any:
    real_info = h.venue.info

    def bad(payload: dict) -> Any:
        if payload["type"] == "orderStatus":
            return {"status": "weird"}  # a shape the parser rejects
        return real_info(payload)

    monkeypatch.setattr(h.venue, "info", bad)
    return real_info


def test_an_entry_ambiguous_near_minute_45_is_resolved_and_protected_in_the_run(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow(entries=(E("AAA"),))
    # The client times out at :45:40; the order reaches the book 20 s later,
    # inside its 45 s expiry and after the :46 entry deadline.
    h.ioc["AAA"] = [{"mode": "land_later", "delay": 20.0}]
    _late_entries(h, monkeypatch)
    assert h.at(T0.replace(minute=44)).run() == 0
    assert len(h.actions("order", coin="AAA", trigger=False)) == 1
    assert entry_outcomes(h)[:2] == ["ambiguous", "filled"]
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is False  # adopted by the entry step itself
    assert len(h.venue.stops("AAA")) == 1
    (stop,) = h.actions("order", trigger=True)
    stop_at = _exchange_times(h)[h.calls.index(stop)]
    assert stop_at >= T0.replace(minute=46)  # the resolve read outlived :46
    assert not criticals(h)


def test_an_entry_left_unresolved_at_run_end_is_critical(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["AAA"] = [{"mode": "raise_after"}]  # it filled; the ack was lost
    real_info = _bad_order_status(h, monkeypatch)
    assert h.run() == 2
    assert {
        "unresolved_entry:AAA",
        "technical_failure:p6_entries",
        "technical_failure:resolve:AAA",
    } <= criticals(h)
    assert len(h.venue.stops("AAA")) == 1  # P7 still adopted and protected it
    assert h.of("trade_opened")[0]["recovered"] is True
    assert not h.actions(coin="BBB")  # entries halted after the failure
    monkeypatch.setattr(h.venue, "info", real_info)
    assert h.at(T0 + HOUR).run() == 0  # resolved at P2; BBB is retried
    assert not criticals(h) and "BBB" in h.venue.positions
    assert len(h.actions("order", coin="AAA", trigger=False)) == 1


def test_entries_halt_after_an_unprotected_fill_and_resume_next_run(
    h: Harness,
) -> None:
    h.shadow(entries=(E("AAA"), E("BBB")))
    no_children(h, "AAA")  # the venue attached no child: the fallback path
    h.trigger["AAA"] = ["reject"] * 20
    h.ioc["AAA"] = [{"mode": "fill"}] + [{"mode": "reject"}] * 20
    assert h.run() == 2
    assert {
        "unprotectable:AAA",
        "exit_incomplete:AAA",
        "unprotected_position:AAA",
    } <= criticals(h)
    assert "AAA" in h.venue.positions and h.venue.stops("AAA") == []
    assert not h.actions(coin="BBB") and not h.of("skip")  # halted, not skipped
    (halted,) = [
        p for p in h.of("run_end")[-1]["problems"] if p["code"] == "entries_halted"
    ]
    assert halted["severity"] == "notice" and halted["message"] == "unprotectable:AAA"
    h.trigger["AAA"], h.ioc["AAA"] = [], []
    h.calls.clear()
    # The next run's P3 treats the opened trade with no stop as stop_missing
    # (critical) and places that stop before anything else.
    assert h.at(T0 + HOUR).run() == 2
    assert criticals(h) == {"stop_missing:AAA"}
    first = h.calls[0]
    assert (first["action"], first["coin"], first["trigger"]) == ("order", "AAA", True)
    assert len(h.venue.stops("AAA")) == 1 and "BBB" in h.venue.positions
    assert h.at(T0 + 2 * HOUR).run() == 0 and not criticals(h)


COINS10 = tuple(f"C{i:02d}" for i in range(1, 11))


def _full_book_with_an_exit_due(h: Harness) -> None:
    h.venue.usdc[SUB] = 5000.0
    h.shadow(entries=tuple(E(c, atr=10.0) for c in COINS10))
    assert h.at(T0).run() == 0 and len(h.of("trade_opened")) == 10
    next_day(
        h,
        holding=tuple(E(c, atr=10.0) for c in COINS10),
        exits=("C01",),
        entries=(E("BBB", atr=10.0),),
    )


def test_an_incomplete_exit_halts_entries_so_the_slot_is_retried(h: Harness) -> None:
    _full_book_with_an_exit_due(h)
    h.ioc["C01"] = [{"mode": "reject"}] * 3
    assert h.run() == 2
    assert "exit_incomplete:C01" in criticals(h)
    assert not h.of("skip")  # no terminal slots_full while the exit is pending
    assert h.at(T0 + DAY + HOUR).run() == 0
    closed = [(c["coin"], c["reason"]) for c in h.of("trade_closed")]
    assert closed == [("C01", "channel_exit")]
    assert h.of("trade_opened")[-1]["coin"] == "BBB"


def test_a_technical_failure_in_the_exits_halts_entries_on_the_stale_book(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    _full_book_with_an_exit_due(h)
    real_read = executor.HlInfoReader.clearinghouse_state
    real_send = executor.SleeveSession.send_order
    state = {"fail_next": False}

    def flaky(self: executor.HlInfoReader, user: str) -> Any:
        if state["fail_next"]:
            state["fail_next"] = False
            raise core.TechnicalError("hl info clearinghouseState HTTP 502")
        return real_read(self, user)

    def send(self: executor.SleeveSession, **kwargs: Any) -> Any:
        result = real_send(self, **kwargs)
        if kwargs["role"] == "exit" and result.filled_sz > 0:
            state["fail_next"] = True  # the ladder's re-read after the fill
        return result

    monkeypatch.setattr(executor.HlInfoReader, "clearinghouse_state", flaky)
    monkeypatch.setattr(executor.SleeveSession, "send_order", send)
    assert h.run() == 2
    assert "technical_failure:p5_exits" in criticals(h)
    assert "C01" not in h.venue.positions and not h.of("trade_closed")
    assert not h.of("skip") and not h.actions("updateLeverage", coin="BBB")
    assert len(h.venue.stops("C01")) == 1  # unconfirmed flat: its stop is kept
    monkeypatch.setattr(executor.HlInfoReader, "clearinghouse_state", real_read)
    monkeypatch.setattr(executor.SleeveSession, "send_order", real_send)
    assert h.at(T0 + DAY + HOUR).run() == 0
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "channel_exit" and closed["reconciled"] is True
    assert h.of("trade_opened")[-1]["coin"] == "BBB" and not h.venue.stops("C01")


def _hide_position(
    h: Harness, monkeypatch: pytest.MonkeyPatch, coin: str, reads: int
) -> Any:
    """The next ``reads`` sub position reads that should show ``coin`` miss it."""
    real_info = h.venue.info
    left = {"n": reads}

    def lagging(payload: dict) -> Any:
        answer = real_info(payload)
        if (
            payload["type"] == "clearinghouseState"
            and payload.get("user") == SUB
            and coin in h.venue.positions
            and left["n"] > 0
        ):
            left["n"] -= 1
            answer = dict(answer)
            answer["assetPositions"] = [
                a for a in answer["assetPositions"] if a["position"]["coin"] != coin
            ]
        return answer

    monkeypatch.setattr(h.venue, "info", lagging)
    return real_info


def test_a_fill_missing_from_one_position_read_is_reread_before_its_stop(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow(entries=(E("AAA"), E("BBB")))
    no_children(h, "AAA")  # the fallback path: the sleeve sizes the stop
    _hide_position(h, monkeypatch, "AAA", 1)
    assert h.run() == 0
    assert executor.REREAD_DELAY_S in h.clock.sleeps
    opened = h.of("trade_opened")
    assert [e["coin"] for e in opened] == ["AAA", "BBB"]
    assert not any(e["recovered"] for e in opened)
    order = [(c["action"], c["coin"], c.get("trigger")) for c in h.calls]
    assert order.index(("order", "AAA", True)) < order.index(
        ("updateLeverage", "BBB", None)
    )


def test_a_fill_the_position_reads_never_show_halts_entries_and_is_critical(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow(entries=(E("AAA"), E("BBB")))
    real_info = _hide_position(h, monkeypatch, "AAA", 100)
    assert h.run() == 2
    assert "fill_not_visible:AAA" in criticals(h)
    assert not h.actions(coin="BBB") and not h.of("skip")
    # A1 (the gap: no stop, since none can be sized from nothing): the
    # entry's venue-attached child protects the fill no read shows.
    (stop,) = h.venue.stops("AAA")
    assert stop["cloid"] == child_cloid("AAA") and float(stop["sz"]) == 12.0
    assert float(stop["triggerPx"]) == 96.0 and stop["side"] == "A"
    monkeypatch.setattr(h.venue, "info", real_info)  # the info node catches up
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0
    (opened,) = h.of("trade_opened", coin="AAA")
    assert opened["recovered"] is True and opened["stop_px"] == 96.0
    (stop,) = h.venue.stops("AAA")  # the child is the stop from the fill
    assert stop["cloid"] == child_cloid("AAA")
    assert not h.actions(coin="AAA") and "BBB" in h.venue.positions


def test_a_technical_error_on_one_coin_does_not_stop_the_sweep(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_day_one(h, "AAA", "BBB")
    h.venue.orders.clear()
    original = FakeExchange.order

    def flaky(self: FakeExchange, name: str, *args: Any, **kwargs: Any) -> Any:
        order_type = args[3] if len(args) > 3 else kwargs.get("order_type")
        if name == "AAA" and "trigger" in (order_type or {}):
            raise requests.ConnectionError("reset")  # an ambiguous stop placement
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(FakeExchange, "order", flaky)
    _bad_order_status(h, monkeypatch)
    assert h.at(T0 + HOUR).run() == 2
    assert len(h.venue.stops("BBB")) == 1  # reached despite AAA's failure
    assert "technical_failure:AAA" in criticals(h)
    # P7 still ran: AAA could not be protected, so it was closed.
    assert "AAA" not in h.venue.positions
    assert h.of("trade_closed")[-1]["reason"] == "unprotectable"
    assert h.of("run_end")[-1]["counts"]["stops_ok"] == 1


def test_one_stale_position_read_does_not_close_a_live_trade(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_day_one(h, "AAA")
    _hide_position(h, monkeypatch, "AAA", 1)  # the P1 snapshot misses AAA
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0
    assert executor.REREAD_DELAY_S in h.clock.sleeps
    assert not h.of("trade_closed") and h.calls == []
    assert len(h.venue.stops("AAA")) == 1


def test_a_trade_flat_with_no_known_fill_keeps_its_stop_until_a_later_run(
    h: Harness,
) -> None:
    open_day_one(h, "AAA")
    del h.venue.positions["AAA"]  # gone, with no fill the sleeve can explain
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 2
    assert "venue_flat_other:AAA" in criticals(h)
    assert h.of("trade_closed")[-1]["reason"] == "venue_flat_other"
    assert len(h.venue.stops("AAA")) == 1 and h.calls == []  # kept this run
    assert h.at(T0 + 2 * HOUR).run() == 0
    assert h.venue.stops("AAA") == []
    assert len(h.actions("cancelByCloid", coin="AAA")) == 1


def test_a_failed_reconcile_still_sweeps_and_keeps_unconfirmed_stops(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_day_one(h, "AAA", "BBB")
    del h.venue.positions["AAA"]  # reconciling it needs the fills read...
    h.venue.orders = [o for o in h.venue.orders if o["coin"] != "BBB"]
    next_day(h, holding=(E("AAA"), E("BBB")), entries=(E("CCC"),))
    real_info = h.venue.info

    def no_fills(payload: dict) -> Any:
        if payload["type"] == "userFillsByTime":
            return {"error": "busy"}  # ...which fails
        return real_info(payload)

    monkeypatch.setattr(h.venue, "info", no_fills)
    assert h.run() == 2
    assert {"technical_failure:p2_reconcile", "stop_missing:BBB"} <= criticals(h)
    assert len(h.venue.stops("BBB")) == 1  # the protective sweep still ran
    assert len(h.venue.stops("AAA")) == 1  # an unreconciled trade keeps its stop
    assert not h.actions(coin="CCC") and not h.of("trade_closed")


@pytest.mark.parametrize(
    ("offset_s", "halts"), [(-10.0, True), (10.0, True), (-1.0, False)]
)
def test_a_host_clock_skewed_from_the_venue_halts_entries(
    h: Harness, offset_s: float, halts: bool
) -> None:
    h.venue.date_offset = timedelta(seconds=offset_s)  # venue Date header
    h.shadow(entries=(E("AAA"),))
    code = h.run()
    skew = h.of("run_end")[-1]["traffic"]["clock_skew_s"]
    assert skew == pytest.approx(-offset_s, abs=1.0)
    if halts:
        assert code == 2 and "clock_skew" in criticals(h)
        assert h.calls == [] and not h.of("skip")
    else:
        assert code == 0 and "AAA" in h.venue.positions


def test_a_cancel_of_an_order_the_venue_already_removed_counts_as_done(
    h: Harness,
) -> None:
    open_day_one(h, "AAA")
    h.venue.auto_cancel_reduce_only = True  # a flat coin's stop is dropped
    next_day(h, holding=(E("AAA"),), exits=("AAA",))
    h.calls.clear()
    assert h.run() == 0
    (cancel,) = h.of("outcome", action="cancel")
    assert cancel["status"] == "gone"
    assert len(h.actions("cancelByCloid")) == 1  # not retried by the final sweep
    assert not h.of("stop_cancelled") and not criticals(h)


def _canary(h: Harness) -> int:
    return h.main(["canary", "--coin", "BTC", "--approval", str(h.approval), *ARM])


def test_a_canary_failing_after_its_stop_rests_still_closes_and_leaves_no_residue(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow()
    real = core.parse_order_status

    def boom(value: object) -> Any:
        raise core.TechnicalError("orderStatus response has an unknown status")

    monkeypatch.setattr(core, "parse_order_status", boom)
    assert _canary(h) == 2
    monkeypatch.setattr(core, "parse_order_status", real)
    assert not h.venue.positions and not h.venue.orders
    assert h.of("canary_result")[-1]["residue"] is False
    assert "canary_failed:BTC" in criticals(h)
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)


def test_a_canary_read_failure_right_after_its_fill_still_closes_it(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow()
    original = executor.SleeveSession.refresh_positions

    def failing(self: executor.SleeveSession) -> None:
        if self.phase == "canary":
            raise core.TechnicalError("hl info clearinghouseState HTTP 502")
        return original(self)

    monkeypatch.setattr(executor.SleeveSession, "refresh_positions", failing)
    assert _canary(h) == 2
    assert not h.venue.positions and not h.venue.orders
    assert h.of("canary_result")[-1]["residue"] is False


def test_a_canary_left_open_blind_is_recorded_as_residue_for_flatten(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.shadow()
    original = executor.SleeveSession.refresh_positions

    def failing(self: executor.SleeveSession) -> None:
        if self.phase in ("canary", "flatten"):  # cleanup cannot read either
            raise core.TechnicalError("hl info clearinghouseState HTTP 502")
        return original(self)

    monkeypatch.setattr(executor.SleeveSession, "refresh_positions", failing)
    assert _canary(h) == 2
    monkeypatch.setattr(executor.SleeveSession, "refresh_positions", original)
    assert "BTC" in h.venue.positions
    assert h.of("canary_result")[-1]["residue"] is True
    assert h.at(T0 + HOUR).run() == 2
    assert "canary_residue:BTC" in criticals(h)
    assert "unknown_position:BTC" not in criticals(h)
    flat = ["flatten", "--coin", "BTC", "--reason", "canary residue"]
    assert h.at(T0 + 2 * HOUR).main([*flat, "--approval", str(h.approval), *ARM]) == 0
    assert not h.venue.positions and not h.venue.orders


def test_a_canary_stop_that_vanishes_after_its_expiry_fails_the_canary(
    h: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    h.shadow()
    real_info = h.venue.info
    queries: list[str] = []

    def expiring(payload: dict) -> Any:
        if payload["type"] == "orderStatus":
            queries.append(payload["oid"])
            if len(queries) == 2:  # the venue dropped it when its action expired
                h.venue.history[payload["oid"]]["status"] = "canceled"
                h.venue.orders = [
                    o for o in h.venue.orders if o.get("cloid") != payload["oid"]
                ]
        return real_info(payload)

    monkeypatch.setattr(h.venue, "info", expiring)
    assert _canary(h) == 2
    out = capsys.readouterr().out
    assert "canary_order_status_by_cloid_ok=true" in out
    assert "canary_stop_survives_expiry=false" in out
    assert not h.venue.positions and not h.venue.orders


# ----------------------------------------------------------------- final review hardening
# Ports of the final reviewers' probes (scratchpad d1final/): each gap probe
# now fails at its gap assertion, which these tests pin as a safety property.


def _lagging_order_status(
    h: Harness, monkeypatch: pytest.MonkeyPatch, cloid: str, times: int | None = None
) -> None:
    """orderStatus(cloid) answers unknownOid (a lagging info node): always, or
    for the first ``times`` queries."""
    real_info = h.venue.info
    left = {"n": times}

    def lagging(payload: dict) -> Any:
        if (
            payload["type"] == "orderStatus"
            and payload["oid"] == cloid
            and (left["n"] is None or left["n"] > 0)
        ):
            if left["n"] is not None:
                left["n"] -= 1
            h.venue.calls.append(("info", "orderStatus", SUB))
            h.venue.call_times.append(h.clock())
            return {"status": "unknownOid"}
        return real_info(payload)

    monkeypatch.setattr(h.venue, "info", lagging)


def test_a_lagging_order_status_never_doubles_an_entry(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H1 (probe test_gap_lagging_order_status_doubles_the_entry_silently)."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)  # never catches up this run
    assert h.run() == 0
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    assert len(entries) == 1  # the gap: a second non-reduce-only IOC
    assert h.venue.positions["AAA"]["szi"] == 12.0
    (opened,) = h.of("trade_opened")
    assert opened["fill_fraction"] == 1.0 and opened["recovered"] is False
    assert opened["actual_risk_usd"] == pytest.approx(opened["risk_usd"])
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0
    assert executor.REREAD_DELAY_S in h.clock.sleeps  # re-read before the retry
    assert _severities(h)["order_status_lag"] == "notice" and not criticals(h)
    outcomes = h.of("outcome", cloid=first)  # the requery's unknownOid is dropped
    assert [o["status"] for o in outcomes] == ["ambiguous", "never_landed", "filled"]
    assert outcomes[-1]["venue_status"] == "position_reread"


def test_an_entry_adopted_after_a_status_lag_journals_the_status_once_it_catches_up(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H1 (probe test_never_landed_retry_after_info_lag): lagging once."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first, times=1)
    assert h.run() == 0
    assert len(h.actions("order", coin="AAA", trigger=False)) == 1
    outcomes = h.of("outcome", cloid=first)
    assert [o["status"] for o in outcomes] == [
        "ambiguous",
        "never_landed",
        "filled",  # the position re-read, journaled before the stop
        "filled",  # orderStatus caught up: its oid joins the trade
    ]
    assert outcomes[2]["venue_status"] == "position_reread"
    assert outcomes[2]["oid"] is None and outcomes[2]["filled_sz"] == 12.0
    assert outcomes[3]["venue_status"] == "filled"
    assert h.book().known_oids[outcomes[-1]["oid"]] == (tid("AAA"), "entry")
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0 and not criticals(h)


def _flapping_position_read(
    h: Harness, monkeypatch: pytest.MonkeyPatch, coin: str, hidden: int
) -> None:
    """Once ``coin`` is held: the first sub position read shows it (a fresh
    info node), the next ``hidden`` reads miss it (a node behind it)."""
    real_info = h.venue.info
    seen = {"n": 0}

    def flapping(payload: dict) -> Any:
        answer = real_info(payload)
        if (
            payload["type"] == "clearinghouseState"
            and payload.get("user") == SUB
            and coin in h.venue.positions
        ):
            seen["n"] += 1
            if 2 <= seen["n"] <= 1 + hidden:
                answer = dict(answer)
                answer["assetPositions"] = [
                    a for a in answer["assetPositions"] if a["position"]["coin"] != coin
                ]
        return answer

    monkeypatch.setattr(h.venue, "info", flapping)


@pytest.mark.parametrize("hidden", [1, 2, 3])
def test_a_position_read_that_flaps_after_a_lagging_fill_never_orphans_it(
    h: Harness, monkeypatch: pytest.MonkeyPatch, hidden: int
) -> None:
    """H1 follow-up (probes verifier_live_safety/test_flipflop.py and
    verifier_correctness test_probe_h1_flap_detail): the pre-retry re-read
    SEES the lagging fill, the reads after it miss it. The re-read is the
    proof: the fill is journaled for the attempt, adopted and protected at
    once, never left unowned with exit 0."""
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    no_children(h, "AAA")  # the fallback path (no venue child)
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)  # never catches up this run
    _flapping_position_read(h, monkeypatch, "AAA", hidden)
    assert h.run() == 0 and not criticals(h)
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    assert len(entries) == 1 and h.venue.positions["AAA"]["szi"] == 12.0
    (stop,) = h.venue.stops("AAA")  # the gap: no stop, no trade_opened
    assert float(stop["sz"]) == 12.0
    (opened,) = h.of("trade_opened", coin="AAA")
    assert opened["recovered"] is False and opened["sz"] == 12.0
    assert float(stop["triggerPx"]) == opened["stop_px"]
    assert h.of("outcome", cloid=first)[-1]["venue_status"] == "position_reread"
    assert _severities(h)["order_status_lag"] == "notice"
    assert h.of("trade_opened", coin="BBB")  # a notice halts nothing
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert h.calls == [] and len(h.venue.stops("AAA")) == 1


def _fail_the_reread(
    h: Harness, monkeypatch: pytest.MonkeyPatch, cloid: str, error: Exception
) -> None:
    """The first sub position read after ``cloid`` resolved never_landed (the
    H1 re-read before the retry) raises ``error``."""
    original = executor.SleeveSession.refresh_positions
    state = {"fired": False}

    def failing(self: executor.SleeveSession) -> None:
        record = self.book.intents.get(cloid)
        if (
            not state["fired"]
            and self.phase == "entry"
            and record is not None
            and record.status == "never_landed"
        ):
            state["fired"] = True
            raise error
        original(self)

    monkeypatch.setattr(executor.SleeveSession, "refresh_positions", failing)


@pytest.mark.parametrize(
    ("error", "critical"),
    [
        (core.TechnicalError("hl read failed"), "technical_failure:p6_entries"),
        (executor.BudgetExhausted("hl_budget_exhausted"), "hl_budget_exhausted"),
        (KeyError("assetPositions"), "technical_failure:p6_entries"),
    ],
)
def test_a_failed_reread_after_a_lagging_entry_still_owns_and_protects_its_fill(
    h: Harness, monkeypatch: pytest.MonkeyPatch, error: Exception, critical: str
) -> None:
    """Non-blocking review item (probe cmp/test_cmp_reread_failure.py): the
    re-read that would prove a lagging fill FAILS. The attempt is journaled
    position_unverified first, so P7 owns the fill and places its stop."""
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    _fail_the_reread(h, monkeypatch, first, error)
    assert h.run() == 2
    assert criticals(h) == {critical}  # no unresolved_entry: P7 adopted it
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    assert len(entries) == 1 and h.venue.positions["AAA"]["szi"] == 12.0
    (opened,) = h.of("trade_opened")  # P7 adopted it (the gap: unowned, no stop)
    assert opened["coin"] == "AAA" and opened["recovered"] is True
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0 and float(stop["triggerPx"]) == opened["stop_px"]
    outcomes = h.of("outcome", cloid=first)
    assert [o["status"] for o in outcomes] == [
        "ambiguous",
        "never_landed",
        core.POSITION_UNVERIFIED,
    ]
    assert outcomes[-1]["venue_status"] == "reread_failed"
    assert not h.actions(coin="BBB")  # entries halted for the rest of the run
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert len(h.venue.stops("AAA")) == 1
    assert len([c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]) == 1


def test_a_quiet_window_at_the_reread_leaves_the_fill_owned_for_the_next_run(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The re-read is stopped by the quiet window: no P7. The run is critical
    (unresolved_entry) and the next run's P3 adopts and protects the fill."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    no_children(h, "AAA")  # the fallback path (no venue child)
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first, times=1)
    _fail_the_reread(h, monkeypatch, first, executor.QuietWindowReached("quiet"))
    assert h.run() == 2
    assert h.of("run_end")[-1]["status"] == "deadline"
    assert criticals(h) == {"unresolved_entry:AAA"}
    assert "AAA" in h.venue.positions and h.venue.stops("AAA") == []
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    first_call = h.calls[0]
    assert (first_call["coin"], first_call["trigger"]) == ("AAA", True)
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0
    assert len([c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]) == 0


def test_an_unverified_entry_the_next_run_reads_flat_is_settled_and_retried(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """position_unverified owns a position until a later session's P1 read,
    at least UNVERIFIED_SETTLE_AFTER after the mark, shows the coin flat:
    that settles it as never_landed, so a later position on the coin is not
    owned through it. Until then the trade takes no entry; then it retries."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_before"}]  # it truly never landed
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _fail_the_reread(h, monkeypatch, first, core.TechnicalError("read failed"))
    assert h.run() == 2
    assert criticals(h) == {"technical_failure:p6_entries", "unresolved_entry:AAA"}
    assert h.book().pending_opens()["AAA"].cloid == first
    h.calls.clear()
    assert h.at(T0 + timedelta(minutes=5)).run() == 2  # too soon to settle
    assert criticals(h) == {"unresolved_entry:AAA"}
    assert h.calls == [] and h.book().intents[first].unverified
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    outcomes = h.of("outcome", cloid=first)
    assert [o["status"] for o in outcomes] == [
        "ambiguous",
        "never_landed",
        core.POSITION_UNVERIFIED,
        "never_landed",
    ]
    assert outcomes[-1]["venue_status"] == "position_flat"
    (opened,) = h.of("trade_opened")  # the retry (attempt 2) opened the trade
    assert opened["recovered"] is False and h.venue.positions["AAA"]["szi"] == 12.0
    assert len(h.venue.stops("AAA")) == 1
    assert not h.book().intents[first].unverified


def test_an_opposite_position_at_the_reread_is_unowned_and_blocks_only_its_coin(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H1 branch: the re-read shows the OTHER side (not this entry's fill):
    critical unknown_position, never touched, no retry; other coins enter."""
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["AAA"] = [{"mode": "raise_before"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    real_info = h.venue.info

    def short_appears(payload: dict) -> Any:
        if payload["type"] == "orderStatus" and payload["oid"] == first:
            h.venue.apply_fill("AAA", False, 5.0, 100.0, h.venue.next_oid())
        return real_info(payload)

    monkeypatch.setattr(h.venue, "info", short_appears)
    assert h.run() == 2
    assert criticals(h) == {"unknown_position:AAA"}
    entry, guard = h.actions("order", coin="AAA")  # no retry; A2 guards the short
    assert not entry["reduce_only"] and entry["is_buy"]
    assert guard["trigger"] and guard["reduce_only"] and guard["is_buy"]
    assert guard["sz"] == 5.0 and guard["limit_px"] == 104.0  # 2 x shadow ATR
    assert h.venue.positions["AAA"]["szi"] == -5.0  # never traded down
    assert h.of("intent", role="guard")[0]["context"]["source"] == "shadow_atr"
    assert h.book().pending_opens() == {}
    assert h.of("trade_opened", coin="BBB") and len(h.venue.stops("BBB")) == 1


def test_an_overfilled_entry_is_critical_and_halts_entries(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H1: if the position read lags too, the retry doubles the position; that
    fill_fraction > 1 is critical, halts entries and the stop covers it all."""
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    _hide_position(h, monkeypatch, "AAA", 1)  # the pre-retry re-read lags as well
    assert h.run() == 2
    assert h.venue.positions["AAA"]["szi"] == 24.0
    assert criticals(h) == {"entry_overfill:AAA"}
    (opened,) = h.of("trade_opened")
    assert opened["fill_fraction"] == pytest.approx(2.0)
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 24.0  # protected in full; nothing is sold
    assert not h.actions(coin="BBB") and not h.of("skip")  # halted, not skipped
    (halted,) = [
        p for p in h.of("run_end")[-1]["problems"] if p["code"] == "entries_halted"
    ]
    assert halted["message"] == "entry_overfill:AAA"


def test_a_recovered_entry_larger_than_its_sizing_is_an_overfill(h: Harness) -> None:
    """H1: the recovery path (ensure_trade) checks the same bound."""
    open_day_one(h, "AAA")
    lines = h.paths.journal.read_text().splitlines(keepends=True)
    events = [json.loads(line) for line in lines]
    cut = next(
        i
        for i, e in enumerate(events)
        if e["event"] == "intent" and e["role"] == "entry"
    )
    h.paths.journal.write_text("".join(lines[: cut + 1]))
    h.venue.orders.clear()
    h.venue.positions["AAA"]["szi"] = 24.0  # a second fill the journal lacks
    assert h.at(T0.replace(hour=1)).run() == 2
    assert {"entry_overfill:AAA", "run_stuck"} <= criticals(h)
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and opened["sz"] == 24.0
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 24.0


def _fail_the_read_after_the_loop(
    h: Harness, monkeypatch: pytest.MonkeyPatch, cloid: str, error: Exception
) -> None:
    """The first sub position read in the entry phase after ``cloid`` resolved
    never_landed that is NOT the re-read before a retry (so: the first read
    after the entry loop) raises ``error``."""
    original = executor.SleeveSession.refresh_positions
    original_reread = executor.SleeveSession.reread_before_retry
    state = {"fired": False, "in_reread": False}

    def reread(self: executor.SleeveSession, coin: str, other: str) -> Any:
        state["in_reread"] = True
        try:
            return original_reread(self, coin, other)
        finally:
            state["in_reread"] = False

    def failing(self: executor.SleeveSession) -> None:
        record = self.book.intents.get(cloid)
        if (
            not state["fired"]
            and not state["in_reread"]
            and self.phase == "entry"
            and record is not None
            and record.status == "never_landed"
        ):
            state["fired"] = True
            raise error
        original(self)

    monkeypatch.setattr(executor.SleeveSession, "reread_before_retry", reread)
    monkeypatch.setattr(executor.SleeveSession, "refresh_positions", failing)


@pytest.mark.parametrize("scenario", ["second_attempt", "window_closed"])
def test_a_failed_read_after_the_entry_loop_still_owns_a_lagging_last_attempt(
    h: Harness, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    """Round-2 review (probes verifier_live_safety/r2 test_gap_postloop_*): the
    LAST attempt filled, its ack was lost and orderStatus lagged (never_landed),
    and the loop ended without a re-read before a retry: at its send limit
    (second_attempt) or because the resolve wait crossed minute 45
    (window_closed). The first read after the loop FAILS. The attempt is
    journaled position_unverified, so P7 owns the fill and places its stop.
    second_attempt: both attempts said never_landed and the trade is open,
    so one status was wrong and the other proves nothing: the size held is
    unproven (12 or 24) until a read shows both, so the run is also critical
    fill_not_visible (d1protect round 2, N1; the next run's read settles it)."""
    if scenario == "second_attempt":
        h.ioc["AAA"] = [{"mode": "raise_before"}, {"mode": "raise_after"}]
        n = 2  # attempt 1 truly never landed; the re-read showed the coin flat
    else:
        h.at(T0.replace(minute=45, second=20))
        h.ioc["AAA"] = [{"mode": "raise_after"}]
        n = 1
    h.shadow(entries=(E("AAA"),))
    last = core.cloid_for(CFG, SUB, tid("AAA"), "entry", n)
    _lagging_order_status(h, monkeypatch, last)
    _fail_the_read_after_the_loop(h, monkeypatch, last, core.TechnicalError("x"))
    assert h.run() == 2
    expected = {"technical_failure:p6_entries"}  # P7 adopted it
    if n == 2:
        expected.add("fill_not_visible:AAA")
    assert criticals(h) == expected
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    assert len(entries) == n and h.venue.positions["AAA"]["szi"] == 12.0
    (opened,) = h.of("trade_opened")  # the gap: no trade_opened, no stop
    assert opened["recovered"] is True
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0 and float(stop["triggerPx"]) == opened["stop_px"]
    outcome = h.of("outcome", cloid=last)[-1]
    assert (outcome["status"], outcome["venue_status"]) == (
        core.POSITION_UNVERIFIED,
        "reread_failed",
    )
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert h.calls == [] and len(h.venue.stops("AAA")) == 1


def test_a_failed_read_after_a_definitive_no_fill_marks_nothing(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a never_landed answer can hide a fill: after no_fill the failed
    read after the loop leaves no position_unverified mark behind."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "no_fill"}, {"mode": "no_fill"}]
    original = executor.SleeveSession.refresh_positions
    state = {"entry_reads": 0}

    def failing(self: executor.SleeveSession) -> None:
        if self.phase == "entry":
            state["entry_reads"] += 1
            if state["entry_reads"] == 2:  # the re-read passes; the next fails
                raise core.TechnicalError("x")
        original(self)

    monkeypatch.setattr(executor.SleeveSession, "refresh_positions", failing)
    assert h.run() == 2
    assert criticals(h) == {"technical_failure:p6_entries"}
    assert not any(r.unverified for r in h.book().intents.values())
    assert "AAA" not in h.venue.positions and h.book().pending_opens() == {}


def _scripted_position_reads(
    h: Harness, monkeypatch: pytest.MonkeyPatch, coin: str, script: list
) -> dict:
    """Once ``coin`` is held, the n-th sub position read answers script[n]:
    'hide' drops the coin, a number is its szi (an info node between two
    fills). Past the script, or once state['truth'] is set, reads are true."""
    real_info = h.venue.info
    state: dict[str, Any] = {"n": 0, "truth": False}

    def info(payload: dict) -> Any:
        answer = real_info(payload)
        if (
            payload["type"] != "clearinghouseState"
            or payload.get("user") != SUB
            or coin not in h.venue.positions
            or state["truth"]
        ):
            return answer
        step = script[state["n"]] if state["n"] < len(script) else None
        state["n"] += 1
        if step is None:
            return answer
        answer = dict(answer)
        if step == "hide":
            answer["assetPositions"] = [
                a for a in answer["assetPositions"] if a["position"]["coin"] != coin
            ]
        else:
            answer["assetPositions"] = [
                {**a, "position": {**a["position"], "szi": str(step)}}
                if a["position"]["coin"] == coin
                else a
                for a in answer["assetPositions"]
            ]
        return answer

    monkeypatch.setattr(h.venue, "info", info)
    return state


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
@pytest.mark.parametrize("seen", ["same_run", "next_run"])
def test_a_duplicate_fill_the_read_at_open_missed_is_critical_once_and_covered(
    h: Harness, monkeypatch: pytest.MonkeyPatch, seen: str, taker_bps: float
) -> None:
    """Round-2 review (probes verifier_correctness_r2 test_known_limit_*): the
    re-read before the retry lags (flat), the retry fills, and the read at
    open comes from a node between the two fills (12 of 24): the trade opens
    at the single size. The first read that shows 24, in P7 (same_run) or in
    the next run's P3 (next_run), raises critical entry_overfill once (the
    gap: silent) and the stop covers the whole position.

    ``taker``: both IOCs fill 3 bps above the mid (d1protect round 1, live
    safety P1): the entry-phase protect() re-anchors the stop to the fill
    and cancels the retry's child, which the retry's ack still proves. P7
    lists only the first attempt's child; the proof is per attempt (child
    OR ack), so it is still 24 (the gap: max(children, acks) = 12, the first
    child cancelled as a duplicate, exit 0, 12 of 24 without a stop)."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    script: list = ["hide", 12.0] if seen == "same_run" else ["hide"] + [12.0] * 50
    reads = _scripted_position_reads(h, monkeypatch, "AAA", script)
    code = h.run()
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    assert len(entries) == 2 and h.venue.positions["AAA"]["szi"] == 24.0
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 12.0 and opened["fill_fraction"] == 1.0
    if seen == "next_run":  # every read of run 1 missed the retry's fill
        # A1 (the gap: exit 0 with a 12 stop on 24): both entries' children
        # are listed and prove 24, so the stop covers 24, both children stay
        # while the reads lag, and the run is critical at once.
        assert code == 2
        assert criticals(h) == {"entry_overfill:AAA", "fill_not_visible:AAA"}
        stops = sorted(
            (float(s["sz"]), float(s["triggerPx"])) for s in h.venue.stops("AAA")
        )
        if taker_bps:  # the retry's child was replaced by the fill's stop
            assert stops == [(12.0, 96.0), (24.0, 96.03)]
        else:
            assert stops == [(12.0, 96.0), (12.0, 96.0), (24.0, 96.0)]
        reads["truth"] = True
        assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    else:
        assert code == 2 and criticals(h) == {"entry_overfill:AAA"}
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [24.0]
    (grew,) = h.of("position_grew")
    assert (grew["sz"], grew["opened_sz"], grew["sized_sz"]) == (24.0, 12.0, 12.0)
    (problem,) = [  # raised by run 1 in both cases
        p for p in h.of("run_end")[0]["problems"] if p["code"] == "entry_overfill"
    ]
    assert problem["message"].startswith("the position grew to 2.000 x")
    reads["truth"] = True
    h.calls.clear()
    assert h.at(T0 + 2 * HOUR).run() == 0 and not criticals(h)  # raised once
    assert len(h.of("position_grew")) == 1 and h.calls == []


def test_a_position_that_grows_only_up_to_its_sized_entry_raises_nothing(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read at open may lag the entry's own second fill (6 of 12): the
    trade opens at 6. Growth up to the SIZED entry is that fill, not a
    duplicate (risk at most 1R): the stop is re-sized, nothing is raised."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.5}, {"mode": "fill"}]
    _scripted_position_reads(h, monkeypatch, "AAA", [6.0, 6.0])
    assert h.run() == 0 and not criticals(h)
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 6.0 and h.venue.positions["AAA"]["szi"] == 12.0
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [12.0]
    assert h.of("position_grew") == [] and "entry_overfill" not in _severities(h)


@pytest.mark.parametrize("final", ["p7_reads_lag", "quiet_window_abort", "p7_deadline"])
def test_an_entry_opened_below_its_acked_fills_is_critical_until_a_read_shows_them(
    h: Harness, monkeypatch: pytest.MonkeyPatch, final: str
) -> None:
    """Pass-2 review round 3 (known limit e; probe test_h_partial_then_fill_
    read_between_the_two_fills[10-True], lag-fuzz C20754): IOC 1 fills 30 %
    and IOC 2 the rest, both acked (12). Every read from the one after the
    loop on comes from a node between the two fills (3.6), so the trade
    opens at 3.6 with a 3.6 stop and 8.4 of 12 has none; the run exited 0
    with a partial_fill notice only. A trade still read below its acked
    fills when P7 ends (or when the run loses P7) is critical
    fill_not_visible now; the next run's first true read re-sizes the stop
    (growth up to the sized entry raises nothing, as before)."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.3}, {"mode": "fill"}]
    reads = _scripted_position_reads(h, monkeypatch, "AAA", [3.6] * 50)
    if final != "p7_reads_lag":
        _p7_fault(h, monkeypatch, final)
    code = h.run()
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    assert [c["sz"] for c in entries] == [12.0, 8.4]
    assert h.venue.positions["AAA"]["szi"] == 12.0
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 3.6 and opened["fill_fraction"] == pytest.approx(0.3)
    # The acks prove 12: the stop covers 12 (before: 3.6, so 8.4 had none),
    # and the remainder's 8.4 child is kept while the reads lag it.
    stops = sorted(float(s["sz"]) for s in h.venue.stops("AAA"))
    assert stops == [8.4, 12.0]
    assert code == 2 and criticals(h) == {"fill_not_visible:AAA"}  # the gap: 0
    reads["truth"] = True
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [12.0]


def test_an_entry_opened_below_its_acked_fills_and_closed_in_the_run_raises_nothing(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control for the acked-fill check: the trade opened at 3.6 of an acked
    12 (its stop covers the acked 12), then P7's true read shows 12 with the
    mid through the stop and the listed stop no longer verifies (the venue
    echoes another trigger), so the final sweep closes it (breach). A trade
    closed in the run is skipped: no fill_not_visible for a position that no
    longer exists."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.3}, {"mode": "fill"}]
    _scripted_position_reads(h, monkeypatch, "AAA", [3.6, 3.6])
    original_p7 = executor.SleeveSession.p7_final

    def through_the_stop(self: executor.SleeveSession) -> None:
        h.venue.mids["AAA"] = 90.0
        h.venue.trigger_echo_scale = 1.001
        self.mids["AAA"] = 90.0  # as read by a later entry's mid
        original_p7(self)

    monkeypatch.setattr(executor.SleeveSession, "p7_final", through_the_stop)
    assert h.run() == 0 and not criticals(h)
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 3.6
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "breach"
    assert "AAA" not in h.venue.positions and h.venue.stops("AAA") == []


def test_an_acked_fill_both_reads_at_open_miss_is_critical_even_when_p7_opens_it(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass-2 review round 3 (N1; probe test_gap_neither_fill_at_open_then_p7_
    reads_one_fill_is_silent, reversal-fuzz R30417): attempt 1 filled unseen
    (lost ack, lagging orderStatus, a flat re-read) and the retry filled,
    acked: the venue holds 24. Both reads at open hid AAA, then P7's reads
    came from a node between the two fills (12): P7 opened the trade at 12
    and check_entry_intents accepted it, so the run exited 0 with a 12 stop
    on 24. Reads at open that miss an acked fill of an entry with a
    never_landed attempt are critical fill_not_visible at once now (that
    attempt may have filled too); the next true read raises entry_overfill
    and covers 24."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    script: list = ["hide"] * 3 + [12.0] * 50
    reads = _scripted_position_reads(h, monkeypatch, "AAA", script)
    code = h.run()
    assert reads["n"] >= 5
    assert h.venue.positions["AAA"]["szi"] == 24.0
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and opened["sz"] == 12.0
    # A1: both children are listed and prove 24: the stop covers 24 in this
    # run (before: a 12 stop until the next run) and the doubling is raised.
    stops = sorted(float(s["sz"]) for s in h.venue.stops("AAA"))
    assert stops == [12.0, 12.0, 24.0]
    assert code == 2  # the gap: 0
    assert criticals(h) == {"fill_not_visible:AAA", "entry_overfill:AAA"}
    reads["truth"] = True
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)  # raised once
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [24.0]


@pytest.mark.parametrize("final", ["p7_shows_all", "p7_shows_part"])
def test_an_acked_fill_the_reads_at_open_miss_is_checked_against_the_final_reads(
    h: Harness, monkeypatch: pytest.MonkeyPatch, final: str
) -> None:
    """Pass-2 review round 3 (N1 without a never_landed attempt): both reads
    at open miss the acked fills, so the trade opens from P7's reads. When
    they show every acked fill, nothing is raised (entries halt for the run
    only; no false alarm). When they come from a node between two acked
    fills (3.6 of 12), P7 opened the trade at 3.6 with a 3.6 stop and the
    run exited 0 (the gap); it is critical fill_not_visible now."""
    h.shadow(entries=(E("AAA"), E("BBB")))
    if final == "p7_shows_all":
        script: list = ["hide", "hide"]
    else:
        h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.3}, {"mode": "fill"}]
        script = ["hide", "hide"] + [3.6] * 50
    reads = _scripted_position_reads(h, monkeypatch, "AAA", script)
    code = h.run()
    assert h.venue.positions["AAA"]["szi"] == 12.0
    (opened,) = h.of("trade_opened", coin="AAA")
    assert opened["recovered"] is True
    assert "BBB" not in h.venue.positions  # entries halt for the run
    if final == "p7_shows_all":
        assert code == 0 and not criticals(h)
        assert _severities(h)["entries_halted"] == "notice"
        assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [12.0]
        return
    assert opened["sz"] == 3.6
    stops = sorted(float(s["sz"]) for s in h.venue.stops("AAA"))
    assert stops == [8.4, 12.0]  # the acked 12 is covered; the child stays
    assert code == 2 and criticals(h) == {"fill_not_visible:AAA"}  # the gap: 0
    reads["truth"] = True
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [12.0]


def test_a_never_landed_attempt_an_earlier_run_settled_is_not_a_hidden_fill(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control for the immediate fill_not_visible: only a never_landed attempt
    of THIS session counts. Run 1's attempt truly never landed and a later
    run's flat read settled it; the retry in that run fills (acked), both of
    its reads at open miss it and P7 shows it all: nothing is raised."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_before"}]  # it truly never landed
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _fail_the_reread(h, monkeypatch, first, core.TechnicalError("read failed"))
    assert h.run() == 2 and "unresolved_entry:AAA" in criticals(h)
    reads = _scripted_position_reads(h, monkeypatch, "AAA", ["hide", "hide"])
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert reads["n"] >= 3
    assert h.book().intents[first].status == "never_landed"
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and opened["sz"] == 12.0
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [12.0]


def test_the_order_status_lag_notice_stands_when_the_open_fails(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round-2 review (trivial): the notice is raised before open_trade, so a
    failing open keeps it; the re-read's fill still owns the position."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)

    def broken(self: executor.SleeveSession, *args: Any, **kwargs: Any) -> None:
        raise core.TechnicalError("open failed")

    monkeypatch.setattr(executor.SleeveSession, "open_trade", broken)
    assert h.run() == 2
    assert _severities(h)["order_status_lag"] == "notice"
    assert criticals(h) == {"technical_failure:p6_entries"}
    (opened,) = h.of("trade_opened")  # P7 recovered it from the re-read's fill
    assert opened["recovered"] is True
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [12.0]


# ----------------------------------------------------------------- pass-2 review hardening
# Ports of the pass-2 reviewers' probes (scratchpad d1verify2/): each gap probe
# now fails at its gap assertion, which these tests pin as a safety property.


@pytest.mark.parametrize(
    ("retry", "script"),
    [
        ("no_fill", ["hide", "hide"]),
        ("lost", ["hide", "hide"]),
        ("no_fill", ["hide", "hide", "hide"]),
        ("no_fill", ["hide", "hide", None, "hide"]),
    ],
    ids=["first_final_read", "doubled", "second_final_read", "flapping_final_reads"],
)
def test_a_lagging_fill_every_entry_read_missed_is_adopted_by_the_final_check(
    h: Harness, monkeypatch: pytest.MonkeyPatch, retry: str, script: list
) -> None:
    """Pass-2 review (probe test_gap_known_limit_b_p7_sees_the_fill_but_exits_0,
    fuzz B10063): attempt 1 filled, its ack was lost, and a node about 50 s
    behind answered its orderStatus (never_landed) and the entry's position
    reads (the re-read before the retry and the read after the loop: flat).
    The retry is a definitive no_fill, or (doubled) it filled unseen as well.
    A final (P7) read shows the position: it is adopted for the attempt and
    protected in this run, from the first final read (even if the second one
    lags again) or, if the first lags too, from the second. The gap:
    unowned, no stop, exit 0, and the next run flagged it unknown_position
    and never touched it. A doubled position is critical entry_overfill with
    a stop over all of it."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [
        {"mode": "raise_after"},
        {"mode": "no_fill" if retry == "no_fill" else "raise_after"},
    ]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    second = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 2)
    _lagging_order_status(h, monkeypatch, first)
    if retry == "lost":
        _lagging_order_status(h, monkeypatch, second)
    reads = _scripted_position_reads(h, monkeypatch, "AAA", script)
    code = h.run()
    size = 12.0 if retry == "no_fill" else 24.0
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    assert len(entries) == 2 and h.venue.positions["AAA"]["szi"] == size
    assert reads["n"] > script.count("hide")  # a final read was true
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and opened["sz"] == size
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == size and float(stop["triggerPx"]) == opened["stop_px"]
    adopted = h.of("outcome", cloid=first if retry == "no_fill" else second)[-1]
    assert (adopted["status"], adopted["venue_status"], adopted["filled_sz"]) == (
        "filled",
        "position_reread",
        size,
    )
    assert _severities(h)["order_status_lag"] == "notice"
    if retry == "no_fill":
        assert code == 0 and not criticals(h)
    else:
        assert code == 2 and criticals(h) == {"entry_overfill:AAA"}
    if script[-1] != "hide":  # the last final read showed the position
        counts = h.of("run_end")[-1]["counts"]
        assert (counts["owned"], counts["unowned"], counts["stops_ok"]) == (1, 0, 1)
    reads["truth"] = True
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert h.calls == [] and len(h.venue.stops("AAA")) == 1
    assert h.of("position_grew") == []


def test_an_owned_fill_the_first_final_read_missed_is_protected_in_the_run(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass-2 fuzz (B10090): the re-read before the retry fails, so attempt 1
    (never_landed, filled unseen) is marked position_unverified; P7's first
    read lags, its second shows the fill. The coin is owned (pending_opens)
    but was never swept: P7 sweeps again and protects it in this run (the
    gap: unprotected_position until the next run's P3)."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    _fail_the_reread(h, monkeypatch, first, core.TechnicalError("hl read failed"))
    reads = _scripted_position_reads(h, monkeypatch, "AAA", ["hide"])
    assert h.run() == 2
    assert criticals(h) == {"technical_failure:p6_entries"}
    assert reads["n"] == 2  # P7's first read lagged, its second was true
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and opened["sz"] == 12.0
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0 and float(stop["triggerPx"]) == opened["stop_px"]
    assert h.of("outcome", cloid=first)[-1]["status"] == core.POSITION_UNVERIFIED
    counts = h.of("run_end")[-1]["counts"]
    assert (counts["owned"], counts["stops_ok"]) == (1, 1)
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h) and h.calls == []


def test_a_stop_placed_by_the_final_resweep_is_verified_from_a_venue_read(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stop that P7's second sweep places for a fill adopted from its
    second read is verified like every final stop, from a fresh orders read,
    never from its ack alone: a stop the venue acked but does not list leaves
    the position unprotectable, and it is closed."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "no_fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    _scripted_position_reads(h, monkeypatch, "AAA", ["hide", "hide", "hide"])
    real_add = h.venue.add_stop

    def acked_never_listed(coin: str, **kwargs: Any) -> int:
        oid = real_add(coin, **kwargs)
        h.venue.orders = [o for o in h.venue.orders if o["oid"] != oid]
        return oid

    monkeypatch.setattr(h.venue, "add_stop", acked_never_listed)
    assert h.run() == 2
    assert "unprotectable:AAA" in criticals(h)
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "unprotectable" and "AAA" not in h.venue.positions


@pytest.mark.parametrize("landed", [True, False])
def test_a_never_landed_entry_no_read_of_its_run_can_prove_flat_is_marked(
    h: Harness, monkeypatch: pytest.MonkeyPatch, landed: bool
) -> None:
    """Known limit (b) closed: attempt 1 said never_landed, the retry was a
    definitive no_fill, and EVERY position read of the run, P7's included,
    showed the coin flat. With a lagging node (landed: the fill is real) the
    run exited 0 with a naked, unowned position (the gap). A flat read in the
    same run proves nothing, so P7 marks the attempt position_unverified:
    the run is critical unresolved_entry, and the next run's read adopts and
    protects the fill (landed) or settles the mark and retries the entry
    (not landed: the precaution costs one alert and one hour)."""
    h.shadow(entries=(E("AAA"),))
    no_children(h, "AAA")  # the fallback path (no venue child)
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    if landed:
        h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "no_fill"}]
        _lagging_order_status(h, monkeypatch, first)
    else:
        h.ioc["AAA"] = [{"mode": "raise_before"}, {"mode": "no_fill"}]
    reads = _scripted_position_reads(h, monkeypatch, "AAA", ["hide"] * 50)
    assert h.run() == 2
    assert criticals(h) == {"unresolved_entry:AAA"}
    outcome = h.of("outcome", cloid=first)[-1]
    assert (outcome["status"], outcome["venue_status"]) == (
        core.POSITION_UNVERIFIED,
        "flat_in_run",
    )
    assert h.venue.stops("AAA") == [] and not h.of("trade_opened")
    assert ("AAA" in h.venue.positions) is landed
    reads["truth"] = True
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    (opened,) = h.of("trade_opened")
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0 and h.venue.positions["AAA"]["szi"] == 12.0
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    if landed:  # adopted and protected first; no new entry
        assert opened["recovered"] is True and entries == []
        assert (h.calls[0]["coin"], h.calls[0]["trigger"]) == ("AAA", True)
    else:  # settled flat, then attempt 3 entered
        settled = h.of("outcome", cloid=first)[-1]
        assert (settled["status"], settled["venue_status"]) == (
            "never_landed",
            "position_flat",
        )
        assert opened["recovered"] is False and len(entries) == 1


def test_the_final_check_adopts_only_this_sessions_never_landed_entries(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An earlier session's never_landed attempt, settled by a later
    session's flat read, owns nothing: after the entry window, a same-side
    position that appears on the coin is not the sleeve's. P7 raises it
    unknown_position and never adopts or touches it."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_before"}, {"mode": "no_fill"}]
    assert h.run() == 2  # the run-end mark: a precaution, settled next run
    assert criticals(h) == {"unresolved_entry:AAA"}
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    assert h.of("outcome", cloid=first)[-1]["status"] == core.POSITION_UNVERIFIED
    original = executor.SleeveSession.p7_final

    def placed_by_hand(self: executor.SleeveSession) -> None:
        h.venue.apply_fill("AAA", True, 12.0, 100.0, h.venue.next_oid())
        original(self)

    monkeypatch.setattr(executor.SleeveSession, "p7_final", placed_by_hand)
    assert h.at(T0 + 7 * HOUR).run() == 2  # the 6 h entry window has closed
    assert criticals(h) == {"unknown_position:AAA"}
    settled = h.of("outcome", cloid=first)[-1]
    assert (settled["status"], settled["venue_status"]) == (
        "never_landed",
        "position_flat",
    )
    assert not h.of("trade_opened")
    (guard,) = h.venue.stops("AAA")  # A2: guarded, never adopted or traded
    assert guard["side"] == "A" and float(guard["sz"]) == 12.0
    assert h.venue.positions["AAA"]["szi"] == 12.0


def test_the_final_check_raises_positions_it_does_not_own_and_adopts_none(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass-2 review: P7 raises critical unknown_position for any position it
    does not own, in the run that first reads it (the gap: exit 0, raised
    only by the next run's P2). Only a never_landed answer can hide a fill:
    after two definitive no_fill answers a same-side position on the entry's
    coin is not adopted, and neither position is touched."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "no_fill"}, {"mode": "no_fill"}]
    original = executor.SleeveSession.p7_final

    def placed_by_hand(self: executor.SleeveSession) -> None:
        h.venue.apply_fill("AAA", True, 12.0, 100.0, h.venue.next_oid())
        h.venue.apply_fill("DDD", False, 5.0, 100.0, h.venue.next_oid())
        original(self)

    monkeypatch.setattr(executor.SleeveSession, "p7_final", placed_by_hand)
    assert h.run() == 2
    assert criticals(h) == {"unknown_position:AAA", "unknown_position:DDD"}
    assert not h.of("trade_opened") and h.book().pending_opens() == {}
    # A2: both are guarded in the run that first reads them, never traded.
    (aaa,) = h.venue.stops("AAA")
    (ddd,) = h.venue.stops("DDD")
    assert (aaa["side"], float(aaa["sz"])) == ("A", 12.0)
    assert (ddd["side"], float(ddd["sz"])) == ("B", 5.0)
    assert h.venue.positions["AAA"]["szi"] == 12.0
    assert h.venue.positions["DDD"]["szi"] == -5.0
    assert len(h.actions("order", coin="AAA")) == 3  # two entries, one guard
    (guard,) = h.actions(coin="DDD")
    assert guard["trigger"] and guard["reduce_only"]
    counts = h.of("run_end")[-1]["counts"]
    assert (counts["owned"], counts["unowned"]) == (0, 2)


def _fail_the_read_after_a_flat_reread(
    h: Harness, monkeypatch: pytest.MonkeyPatch, cloid: str, where: str
) -> dict:
    """After ``cloid`` said never_landed and the re-read before the retry ran:
    the mid read for the retry fails (where='mid'), or the first sub position
    read after the entry loop fails (where='read_after_the_loop')."""
    original_read = executor.SleeveSession.refresh_positions
    original_reread = executor.SleeveSession.reread_before_retry
    original_mid = executor.SleeveSession.mid_now
    state = {"fired": False, "in_reread": False, "rereads": 0}

    def reread(self: executor.SleeveSession, coin: str, other: str) -> Any:
        state["in_reread"] = True
        state["rereads"] += 1
        try:
            return original_reread(self, coin, other)
        finally:
            state["in_reread"] = False

    def read(self: executor.SleeveSession) -> None:
        if (
            where == "read_after_the_loop"
            and not state["fired"]
            and not state["in_reread"]
            and self.phase == "entry"
            and state["rereads"] >= 1
        ):
            state["fired"] = True
            raise core.TechnicalError("hl read failed")
        original_read(self)

    def mid(self: executor.SleeveSession, coin: str) -> Any:
        record = self.book.intents.get(cloid)
        if (
            where == "mid"
            and not state["fired"]
            and self.phase == "entry"
            and record is not None
            and record.status == "never_landed"
        ):
            state["fired"] = True
            raise core.TechnicalError("hl info allMids transport error")
        return original_mid(self, coin)

    monkeypatch.setattr(executor.SleeveSession, "reread_before_retry", reread)
    monkeypatch.setattr(executor.SleeveSession, "refresh_positions", read)
    monkeypatch.setattr(executor.SleeveSession, "mid_now", mid)
    return state


@pytest.mark.parametrize("where", ["read_after_the_loop", "mid"])
def test_a_failure_in_the_entry_marks_every_never_landed_attempt_of_the_trade(
    h: Harness, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    """Pass-2 review (probes test_gap_postloop_read_failure_marks_only_the_
    last_attempt and test_gap_mid_read_failure_between_a_flat_reread_and_the_
    retry): attempt 1 filled unseen (lost ack, lagging orderStatus, lagging
    re-read), then a read fails: the read after the loop that followed a
    definitive no_fill retry, or the mid read for the retry. Every read of
    that run lags, P7's too, so only the mark can own the fill: attempt 1,
    not just the last attempt, is journaled position_unverified, the run is
    critical unresolved_entry, and the next run's P3 adopts and protects the
    fill (the gap: owned by nothing; the next run flagged it unknown_position
    and never touched it)."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "no_fill"}]
    no_children(h, "AAA")  # the fallback path (no venue child)
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    state = _fail_the_read_after_a_flat_reread(h, monkeypatch, first, where)
    reads = _scripted_position_reads(h, monkeypatch, "AAA", ["hide"] * 50)
    assert h.run() == 2
    assert state["fired"]
    assert criticals(h) == {"technical_failure:p6_entries", "unresolved_entry:AAA"}
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    assert len(entries) == (2 if where == "read_after_the_loop" else 1)
    assert h.venue.positions["AAA"]["szi"] == 12.0 and h.venue.stops("AAA") == []
    outcome = h.of("outcome", cloid=first)[-1]
    assert (outcome["status"], outcome["venue_status"]) == (
        core.POSITION_UNVERIFIED,
        "reread_failed",
    )
    reads["truth"] = True
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    first_call = h.calls[0]
    assert (first_call["coin"], first_call["trigger"]) == ("AAA", True)
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and opened["sz"] == 12.0
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0
    assert not [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]


@pytest.mark.parametrize("skip", ["quiet_window_abort", "p7_deadline"])
def test_a_run_that_skips_the_final_check_marks_its_never_landed_entries(
    h: Harness, monkeypatch: pytest.MonkeyPatch, skip: str
) -> None:
    """Pass-2 review (non-blocking; fuzz B10053 and B10268 with the reviewer's
    prototype): attempt 1 filled unseen, the retry was a definitive no_fill,
    the entry's reads lagged (flat), and the run lost its final check (P7):
    a quiet-window abort, or P7 skipped at its deadline. flag_unprotected
    marks attempt 1 position_unverified: the run is critical
    unresolved_entry (the gap: exit 0, nothing raised) and the next run's P3
    adopts and protects the fill."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "no_fill"}]
    no_children(h, "AAA")  # the fallback path (no venue child)
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    reads = _scripted_position_reads(h, monkeypatch, "AAA", ["hide", "hide"])
    original = executor.SleeveSession.p7_final

    def no_final_check(self: executor.SleeveSession) -> None:
        if skip == "quiet_window_abort":
            raise executor.QuietWindowReached("quiet window")
        h.clock.now = T0.replace(minute=57, second=1)
        original(self)

    monkeypatch.setattr(executor.SleeveSession, "p7_final", no_final_check)
    assert h.run() == 2
    assert criticals(h) == {"unresolved_entry:AAA"}
    assert h.venue.positions["AAA"]["szi"] == 12.0 and h.venue.stops("AAA") == []
    outcome = h.of("outcome", cloid=first)[-1]
    assert (outcome["status"], outcome["venue_status"]) == (
        core.POSITION_UNVERIFIED,
        "no_final_check",
    )
    second = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 2)
    assert h.of("outcome", cloid=second)[-1]["status"] == "no_fill"  # not marked
    assert reads["n"] == 2
    monkeypatch.setattr(executor.SleeveSession, "p7_final", original)
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    first_call = h.calls[0]
    assert (first_call["coin"], first_call["trigger"]) == ("AAA", True)
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0


def test_a_skipped_final_check_after_clean_entries_marks_nothing(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control: only never_landed attempts of trades not opened are marked;
    a quiet-window abort after ordinary fills and no_fill answers stays a
    notice (exit 0) and the next run is clean."""
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["BBB"] = [{"mode": "no_fill"}, {"mode": "no_fill"}]

    def quiet(self: executor.SleeveSession) -> None:
        raise executor.QuietWindowReached("quiet window")

    monkeypatch.setattr(executor.SleeveSession, "p7_final", quiet)
    assert h.run() == 0 and not criticals(h)
    assert h.of("run_end")[-1]["status"] == "deadline"
    assert not any(r.unverified for r in h.book().intents.values())
    assert len(h.venue.stops("AAA")) == 1


# ------------------------------------------------------- pass-2 review, round 2
# Ports of the round-2 reviewers' probes (scratchpad d1verify2/*/r2/).


def _p7_fault(
    h: Harness, monkeypatch: pytest.MonkeyPatch, fault: str
) -> dict[str, bool]:
    """The run loses its final check (P7), once: a quiet-window abort before
    it; P7 skipped at its deadline (the host slept to :57); P7's first
    position read fails; or the quiet window reached right after P7's first
    position read (before adopt_lagging_entries)."""
    state = {"fired": False}
    original_p7 = executor.SleeveSession.p7_final
    original_read = executor.SleeveSession.refresh_positions
    original_orders = executor.SleeveSession.refresh_orders

    def p7(self: executor.SleeveSession) -> None:
        if not state["fired"] and fault == "quiet_window_abort":
            state["fired"] = True
            raise executor.QuietWindowReached("quiet window")
        if not state["fired"] and fault == "p7_deadline":
            state["fired"] = True
            h.clock.now = h.clock.now.replace(minute=57, second=1)
        original_p7(self)

    def read(self: executor.SleeveSession) -> None:
        if not state["fired"] and fault == "p7_read_fails" and self.phase == "final":
            state["fired"] = True
            raise core.TechnicalError("hl info clearinghouseState transport error")
        original_read(self)

    def orders(self: executor.SleeveSession) -> None:
        if (
            not state["fired"]
            and fault == "quiet_after_p7_read"
            and self.phase == "final"
        ):
            state["fired"] = True
            h.clock.now = h.clock.now.replace(minute=57, second=0)
        original_orders(self)

    monkeypatch.setattr(executor.SleeveSession, "p7_final", p7)
    monkeypatch.setattr(executor.SleeveSession, "refresh_positions", read)
    monkeypatch.setattr(executor.SleeveSession, "refresh_orders", orders)
    return state


@pytest.mark.parametrize(
    "fault",
    ["quiet_window_abort", "p7_deadline", "p7_read_fails", "quiet_after_p7_read"],
)
def test_a_lost_final_check_marks_a_lagging_fill_a_later_read_showed_same_side(
    h: Harness, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    """Pass-2 review round 2 (G1; probes test_gap_resolvers_own_abort_test_
    with_a_second_candidate_is_silent, test_gap_p7_first_read_fails_leaves_
    the_seen_lagging_fill_orphaned and test_i_abort_mark_skips_a_coin_the_
    local_reads_show_held_same_side): AAA attempt 1 filled unseen (lost ack,
    orderStatus and the entry's reads from a lagging node), the retry was a
    definitive no_fill; then BBB entered and its true reads showed AAA held
    long, the side of AAA's entry. The run then lost P7. The abort mark
    skipped every coin the local reads showed held, so AAA's attempt stayed
    never_landed: nothing owned the fill, the run exited 0 with no critical
    (or loud only as technical_failure), and every later run raised
    unknown_position and never protected it. Only a coin held on the OTHER
    side is skipped now: the attempt is marked, AAA is owned and critical
    stop_missing and unresolved_entry are raised, and the next run's P3
    adopts and protects it first."""
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "no_fill"}]
    no_children(h, "AAA")  # the fallback path (no venue child)
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    _scripted_position_reads(h, monkeypatch, "AAA", ["hide", "hide"])
    state = _p7_fault(h, monkeypatch, fault)
    assert h.run() == 2
    assert state["fired"]
    expected = {"stop_missing:AAA", "unresolved_entry:AAA"}
    if fault == "p7_read_fails":
        expected.add("technical_failure:final")
    assert criticals(h) == expected
    assert h.venue.positions["AAA"]["szi"] == 12.0 and h.venue.stops("AAA") == []
    assert len(h.venue.stops("BBB")) == 1  # BBB's read showed AAA held
    outcome = h.of("outcome", cloid=first)[-1]
    assert (outcome["status"], outcome["venue_status"]) == (
        core.POSITION_UNVERIFIED,
        "no_final_check",
    )
    assert h.of("run_end")[-1]["counts"]["owned"] == 2
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    first_call = h.calls[0]
    assert (first_call["coin"], first_call["trigger"]) == ("AAA", True)
    (opened,) = h.of("trade_opened", coin="AAA")
    assert opened["recovered"] is True and opened["sz"] == 12.0
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0
    assert not [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]


@pytest.mark.parametrize(
    "case", ["short_after_entry", "short_seen_after_the_loop", "short_gone_by_p7"]
)
def test_the_marks_skip_a_coin_held_or_seen_on_the_other_side(
    h: Harness, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """Control for the round-2 mark scope: a coin held on the OTHER side from
    a never_landed attempt is not the sleeve's to own, whether P7's end mark
    sees it (short_after_entry), a run that lost P7 saw it after the entry
    loop (short_seen_after_the_loop), or the entry's re-read saw it and it
    was gone by P7 (short_gone_by_p7: blocked unowned). The attempt stays
    never_landed and owns nothing."""
    h.shadow(entries=(E("AAA"),))
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    second = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 2)
    h.ioc["AAA"] = [{"mode": "raise_before"}, {"mode": "no_fill"}]
    if case == "short_after_entry":
        original_p7 = executor.SleeveSession.p7_final

        def placed_by_hand(self: executor.SleeveSession) -> None:
            h.venue.apply_fill("AAA", False, 5.0, 100.0, h.venue.next_oid())
            original_p7(self)

        monkeypatch.setattr(executor.SleeveSession, "p7_final", placed_by_hand)
    elif case == "short_seen_after_the_loop":
        original_read = executor.SleeveSession.refresh_positions

        def read(self: executor.SleeveSession) -> None:
            record = self.book.intents.get(second)
            if self.phase == "entry" and record is not None and record.resolved:
                if "AAA" not in h.venue.positions:
                    h.venue.apply_fill("AAA", False, 5.0, 100.0, h.venue.next_oid())
            original_read(self)

        def quiet(self: executor.SleeveSession) -> None:
            raise executor.QuietWindowReached("quiet window")

        monkeypatch.setattr(executor.SleeveSession, "refresh_positions", read)
        monkeypatch.setattr(executor.SleeveSession, "p7_final", quiet)
    else:
        real_info = h.venue.info

        def short_appears(payload: dict) -> Any:
            if payload["type"] == "orderStatus" and payload["oid"] == first:
                h.venue.apply_fill("AAA", False, 5.0, 100.0, h.venue.next_oid())
            return real_info(payload)

        original_p7 = executor.SleeveSession.p7_final

        def closed_by_hand(self: executor.SleeveSession) -> None:
            h.venue.positions.pop("AAA", None)
            original_p7(self)

        monkeypatch.setattr(h.venue, "info", short_appears)
        monkeypatch.setattr(executor.SleeveSession, "p7_final", closed_by_hand)
    code = h.run()
    record = h.book().intents[first]
    assert record.status == "never_landed" and not record.unverified
    assert h.book().pending_opens() == {}
    assert not h.of("trade_opened")
    if case == "short_after_entry":  # A2: P7 guards the short it reads
        (guard,) = h.venue.stops("AAA")
        assert (guard["side"], float(guard["sz"])) == ("B", 5.0)
    else:
        assert h.venue.stops("AAA") == []
    if case == "short_seen_after_the_loop":  # no final check: flagged now (A2)
        assert code == 2 and criticals(h) == {"unknown_position:AAA"}
        assert h.of("run_end")[-1]["status"] == "deadline"
    else:
        assert code == 2 and criticals(h) == {"unknown_position:AAA"}


def _reads_show_the_closed_long(
    h: Harness, monkeypatch: pytest.MonkeyPatch, coin: str
) -> dict:
    """An info node that lags from before this run's close of ``coin``'s
    long: once the venue holds ``coin`` short, every sub position read shows
    the closed long instead, until state['truth'] is set."""
    closed_long = dict(h.venue.positions[coin])
    real_info = h.venue.info
    state: dict[str, Any] = {"n": 0, "truth": False}

    def info(payload: dict) -> Any:
        answer = real_info(payload)
        held = h.venue.positions.get(coin)
        if (
            payload["type"] != "clearinghouseState"
            or payload.get("user") != SUB
            or held is None
            or held["szi"] > 0
            or state["truth"]
        ):
            return answer
        state["n"] += 1
        answer = dict(answer)
        answer["assetPositions"] = [
            {"position": h.venue.position_record(coin, closed_long), "type": "oneWay"}
            if a["position"]["coin"] == coin
            else a
            for a in answer["assetPositions"]
        ]
        return answer

    monkeypatch.setattr(h.venue, "info", info)
    return state


@pytest.mark.parametrize("final", ["p7_reads_lag", "quiet_window_abort", "p7_deadline"])
@pytest.mark.parametrize("start", ["retry", "cutoff"])
def test_a_reversal_fill_hidden_by_a_read_of_the_closed_side_is_owned_and_protected(
    h: Harness, monkeypatch: pytest.MonkeyPatch, start: str, final: str
) -> None:
    """Pass-2 review round 3 (B1; probes test_gap_reversal_entry_fill_hidden_
    behind_the_closed_side_is_orphaned and test_gap_reversal_at_the_cutoff_
    then_lost_p7): P5 closes the AAA long and P6 enters AAA short in the same
    run. The short fills, but its POST response is lost and orderStatus lags
    (never_landed), and every read after it comes from a node that lags from
    before the close: it shows the sleeve's OWN closed long. The entry's
    re-read raised unknown_position and blocked AAA as unowned (retry), or,
    at the :45 cut-off with no retry, the read after the loop just returned
    (cutoff). The marks skipped AAA as held on the other side, so nothing
    owned the short: every later run raised unknown_position and never
    protected it, and a run that lost P7 at the cut-off exited 0 with no
    critical. A side this session closed proves nothing now: the attempt is
    marked, unresolved_entry is critical, and the next run's P3 adopts the
    short and places its stop first."""
    open_day_one(h, "AAA")
    next_day(h, holding=(E("AAA"),), exits=("AAA",), entries=(E("AAA", side="short"),))
    h.venue.mids["AAA"] = 98.0
    h.ioc["AAA"] = [{"mode": "fill"}, {"mode": "raise_after"}, {"mode": "fill"}]
    no_children(h, "AAA")  # the fallback path (no venue child)
    short_id = tid("AAA", "short", T + DAY)
    short = core.cloid_for(CFG, SUB, short_id, "entry", 1)
    _lagging_order_status(h, monkeypatch, short)
    reads = _reads_show_the_closed_long(h, monkeypatch, "AAA")
    if final != "p7_reads_lag":
        _p7_fault(h, monkeypatch, final)
    when = T0 + DAY if start == "retry" else (T0 + DAY).replace(minute=44, second=20)
    h.calls.clear()
    code = h.at(when).run()
    assert reads["n"] > 0
    assert [(c["reason"]) for c in h.of("trade_closed")] == ["channel_exit"]
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    assert len(entries) == 1  # never a second IOC on top of it
    assert h.venue.positions["AAA"]["szi"] == -12.0
    # No venue child here (the fallback path): nothing covers the real short
    # in this run. A stale read shows the closed long, so a P7 that runs
    # guards THAT (A2): a reduce-only sell stop, inert on the short.
    assert not [o for o in h.venue.stops("AAA") if o["side"] == "B"]
    assert all(o["reduceOnly"] for o in h.venue.stops("AAA"))
    assert code == 2 and "unresolved_entry:AAA" in criticals(h)  # the gap: absent
    outcome = h.of("outcome", cloid=short)[-1]
    why = "flat_in_run" if final == "p7_reads_lag" else "no_final_check"
    assert (outcome["status"], outcome["venue_status"]) == (
        core.POSITION_UNVERIFIED,
        why,
    )
    reads["truth"] = True
    h.calls.clear()
    assert h.at(when + HOUR).run() == 0 and not criticals(h)
    first_call = h.calls[0]
    assert (first_call["coin"], first_call["trigger"], first_call["is_buy"]) == (
        "AAA",
        True,
        True,
    )
    (opened,) = h.of("trade_opened", trade_id=short_id)
    assert opened["recovered"] is True and opened["direction"] == -1
    assert opened["sz"] == 12.0
    (stop,) = h.venue.stops("AAA")  # the stale read's guard is cancelled
    assert float(stop["sz"]) == 12.0 and stop["side"] == "B"
    assert not [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]


def test_a_failure_in_one_entry_marks_only_that_trades_attempts(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scope of enter()'s mark (a surviving round-1 mutant): AAA's attempt
    said never_landed and its re-read showed a short (not the sleeve's);
    then BBB's re-read failed after a lagging never_landed. Only BBB's
    attempt is marked: AAA's stays never_landed and owns nothing."""
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["AAA"] = [{"mode": "raise_before"}]
    h.ioc["BBB"] = [{"mode": "raise_after"}]
    first_aaa = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    first_bbb = core.cloid_for(CFG, SUB, tid("BBB"), "entry", 1)
    real_info = h.venue.info

    def short_appears(payload: dict) -> Any:
        if payload["type"] == "orderStatus" and payload["oid"] == first_aaa:
            h.venue.apply_fill("AAA", False, 5.0, 100.0, h.venue.next_oid())
        return real_info(payload)

    monkeypatch.setattr(h.venue, "info", short_appears)
    _lagging_order_status(h, monkeypatch, first_bbb)
    _fail_the_reread(h, monkeypatch, first_bbb, core.TechnicalError("hl read failed"))
    assert h.run() == 2
    assert criticals(h) == {"unknown_position:AAA", "technical_failure:p6_entries"}
    assert h.book().intents[first_aaa].status == "never_landed"
    outcome = h.of("outcome", cloid=first_bbb)[-1]
    assert (outcome["status"], outcome["venue_status"]) == (
        core.POSITION_UNVERIFIED,
        "reread_failed",
    )
    (opened,) = h.of("trade_opened")  # P7 adopted BBB's fill through the mark
    assert opened["coin"] == "BBB" and opened["recovered"] is True
    (stop,) = h.venue.stops("BBB")  # its venue child: the stop from the fill
    assert stop["cloid"] == child_cloid("BBB")
    (guard,) = h.venue.stops("AAA")  # A2: the unowned short, guarded only
    assert guard["side"] == "B" and h.venue.positions["AAA"]["szi"] == -5.0


def _hide_once_after_a_close(
    h: Harness, monkeypatch: pytest.MonkeyPatch, closing: str, hidden: str
) -> dict[str, bool]:
    """The first sub position read after the first reduce-only IOC on
    ``closing`` comes from an info node that lags the entry fill of
    ``hidden``: that coin is missing from it. Every other read is true."""
    real_info = h.venue.info
    state = {"hid": False}

    def info(payload: dict) -> Any:
        answer = real_info(payload)
        sent = any(
            c["action"] == "order"
            and c["coin"] == closing
            and c["reduce_only"]
            and not c["trigger"]
            for c in h.calls
        )
        if (
            state["hid"]
            or not sent
            or payload["type"] != "clearinghouseState"
            or payload.get("user") != SUB
        ):
            return answer
        state["hid"] = True
        answer = dict(answer)
        answer["assetPositions"] = [
            a for a in answer["assetPositions"] if a["position"]["coin"] != hidden
        ]
        return answer

    monkeypatch.setattr(h.venue, "info", info)
    return state


@pytest.mark.parametrize("case", ["unprotectable_no_fill", "unprotectable_half"])
def test_a_flat_read_the_close_fills_do_not_explain_never_closes_the_trade(
    h: Harness, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """Pass-2 review round 2 (probe test_f_close_ladder_trusts_one_lagging_
    read_and_orphans_the_position; 64 of 78 lag-fuzz orphans): both stop
    placements are rejected, so the position is closed as unprotectable; the
    reduce-only IOC fills nothing (or half) and the read after it comes from
    a node that lags the entry fill: flat. close_position journaled
    trade_closed on that one read, so the position was left open with no
    stop and no owner for good. Now the acked close fills must explain a flat
    read: critical exit_incomplete, the trade stays open, and P7's true read
    protects what is left in the same run."""
    h.shadow(entries=(E("AAA"),))
    close = (
        {"mode": "no_fill"}
        if case.endswith("no_fill")
        else {"mode": "fill", "fraction": 0.5}
    )
    h.ioc["AAA"] = [{"mode": "fill"}, close]
    no_children(h, "AAA")  # the fallback path (no venue child)
    h.trigger["AAA"] = ["reject", "reject"]
    state = _hide_once_after_a_close(h, monkeypatch, "AAA", "AAA")
    assert h.run() == 2
    assert state["hid"]
    assert criticals(h) == {"unprotectable:AAA", "exit_incomplete:AAA"}
    assert not h.of("trade_closed")
    left = 12.0 if case.endswith("no_fill") else 6.0
    assert h.venue.positions["AAA"]["szi"] == left
    (stop,) = h.venue.stops("AAA")  # placed by P7 from its true read
    assert float(stop["sz"]) == left
    assert h.of("run_end")[-1]["counts"]["stops_ok"] == 1
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert len(h.venue.stops("AAA")) == 1 and not h.of("trade_closed")


def test_a_breach_close_confirmed_only_by_a_lagging_read_keeps_the_trade(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass-2 review round 2 (probe test_g_breach_close_confirmed_by_a_
    lagging_read): the price falls through the stop right after the fill,
    the stop is rejected, the breach close IOC does not fill and the read
    after it lags the entry fill (flat). trade_closed(breach) was journaled
    with no problem, the position left naked and unowned. Now the run is
    critical exit_incomplete and P7's true read closes it as a breach."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "fill"}, {"mode": "no_fill"}]
    no_children(h, "AAA")  # the fallback path (no venue child)
    h.trigger["AAA"] = ["reject"]
    real_order = FakeExchange.order

    def order(
        self: FakeExchange, name: str, is_buy: bool, *args: Any, **kw: Any
    ) -> Any:
        out = real_order(self, name, is_buy, *args, **kw)
        if name == "AAA" and is_buy and self.venue.positions.get("AAA"):
            self.venue.mids["AAA"] = 95.0  # through the stop
        return out

    monkeypatch.setattr(FakeExchange, "order", order)
    state = _hide_once_after_a_close(h, monkeypatch, "AAA", "AAA")
    assert h.run() == 2
    assert state["hid"]
    assert criticals(h) == {"exit_incomplete:AAA"}
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "breach" and "AAA" not in h.venue.positions
    closes = [
        c
        for c in h.actions("order", coin="AAA")
        if c["reduce_only"] and not c["trigger"]
    ]
    assert len(closes) == 2  # the unexplained one, then P7's


def test_flatten_keeps_a_trade_an_earlier_close_read_showed_flat(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass-2 review round 2 (lag-fuzz C20122 after the first remedy): the
    read after AAA's close lags BBB's entry fill, so BBB's close starts from
    a read that already shows it flat: no IOC is sent. close_position
    journaled trade_closed for BBB with no fill and flatten cancelled its
    stop: BBB open, naked and unowned. Now BBB is critical exit_incomplete,
    keeps its trade and its stop, and the next flatten closes it."""
    open_day_one(h, "AAA", "BBB")
    state = _hide_once_after_a_close(h, monkeypatch, "AAA", "BBB")
    argv = ["flatten", "--all", "--reason", "rollback", "--approval", str(h.approval)]
    assert h.at(T0.replace(hour=2)).main([*argv, *ARM]) == 2
    assert state["hid"]
    assert criticals(h) == {"exit_incomplete:BBB"}
    assert [c["coin"] for c in h.of("trade_closed")] == ["AAA"]
    assert "AAA" not in h.venue.positions and h.venue.stops("AAA") == []
    assert h.venue.positions["BBB"]["szi"] == 12.0 and len(h.venue.stops("BBB")) == 1
    assert not h.actions("order", coin="BBB", reduce_only=True, trigger=False)
    assert h.at(T0.replace(hour=3)).main([*argv, *ARM]) == 0
    assert [c["coin"] for c in h.of("trade_closed")] == ["AAA", "BBB"]
    assert "BBB" not in h.venue.positions and not h.venue.orders


def test_flatten_of_one_coin_keeps_the_stop_of_a_trade_reconciled_venue_flat_other(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass-2 review round 3 (B2; probe test_gap_flatten_coin_strips_the_stop_
    of_a_position_two_reads_missed): flatten --coin AAA within the node lag of
    AAA's entry. P1's read and P2's re-read both miss the live 12, so P2
    closes the trade as venue_flat_other and holds its orders
    (hold_orders_on), but flatten's own cancel loop ignored that hold and
    cancelled the stop: the position stayed open with no stop and no owner.
    It keeps its stop now, as in the hourly run."""
    open_day_one(h, "AAA")
    reads = _scripted_position_reads(h, monkeypatch, "AAA", ["hide", "hide"])
    argv = ["flatten", "--coin", "AAA", "--reason", "rollback"]
    h.calls.clear()
    code = h.at(T0 + timedelta(minutes=3)).main(
        [*argv, "--approval", str(h.approval), *ARM]
    )
    assert code == 2 and reads["n"] == 2
    assert criticals(h) == {"venue_flat_other:AAA"}
    assert [(c["coin"], c["reason"]) for c in h.of("trade_closed")] == [
        ("AAA", "venue_flat_other")
    ]
    assert h.venue.positions["AAA"]["szi"] == 12.0
    assert len(h.venue.stops("AAA")) == 1  # the gap: flatten cancelled it
    assert h.calls == []
    reads["truth"] = True
    assert h.at(T0 + HOUR).run() == 2 and "unknown_position:AAA" in criticals(h)
    assert len(h.venue.stops("AAA")) == 1 and h.calls == []


def test_flatten_of_one_coin_cancels_orders_left_on_a_coin_its_fills_show_closed(
    h: Harness,
) -> None:
    """Control for the hold: a coin P2 reconciles from a known close fill (the
    venue stop) is flat, so flatten --coin still cancels the owned orders
    left on it."""
    open_day_one(h, "AAA")
    h.venue.trigger_stop("AAA")
    leftover = core.cloid_for(CFG, SUB, tid("AAA"), "stop", 9)
    h.venue.add_stop("AAA", is_buy=False, sz=12.0, trigger=96.0, cloid=leftover)
    argv = ["flatten", "--coin", "AAA", "--reason", "rollback"]
    code = h.at(T0 + timedelta(minutes=3)).main(
        [*argv, "--approval", str(h.approval), *ARM]
    )
    assert code == 0 and not criticals(h)
    assert [(c["coin"], c["reason"]) for c in h.of("trade_closed")] == [
        ("AAA", "venue_stop")
    ]
    assert h.venue.stops("AAA") == []
    (cancel,) = h.actions("cancel") or h.actions("cancelByCloid")
    assert cancel["coin"] == "AAA"


def test_two_fills_the_read_at_open_both_shows_raise_growth_only_once(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass-2 review (probe test_two_lagging_fills_open_reads_lag_both_then_p7_
    sees_24): the trade opens at the doubled size (24) with entry_overfill at
    open; its opened size bounds the growth check, so neither P7 nor a later
    run journals position_grew for that same size."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    _scripted_position_reads(h, monkeypatch, "AAA", ["hide"])
    assert h.run() == 2 and criticals(h) == {"entry_overfill:AAA"}
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 24.0 and opened["recovered"] is False
    assert h.of("position_grew") == []
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [24.0]
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert h.of("position_grew") == []


@pytest.mark.parametrize(("extra", "raised"), [(0.004, False), (0.01, True)])
def test_growth_is_raised_from_one_lot_above_the_sized_entry(
    h: Harness, extra: float, raised: bool
) -> None:
    """check_growth's bound (AAA trades in lots of 0.01): less than half a lot
    above the sized entry is size noise, not growth; one lot above is."""
    open_day_one(h, "AAA")
    h.venue.apply_fill("AAA", True, extra, 100.0, h.venue.next_oid())
    code = h.at(T0 + HOUR).run()
    grew = h.of("position_grew")
    if raised:
        assert code == 2 and criticals(h) == {"entry_overfill:AAA"}
        assert [e["sz"] for e in grew] == [12.01]
    else:
        assert code == 0 and not criticals(h) and grew == []


def test_a_grown_position_closed_as_a_breach_raises_no_growth_alert(
    h: Harness,
) -> None:
    """Pass-2 review (probe test_growth_then_breach_closes_and_what_is_raised):
    the position grew and its mid is through the stop, so P3 closes it
    (breach). The growth check runs after protect() and skips a trade it
    closed: no position_grew, no entry_overfill (the gap: a critical for a
    position that no longer exists, and halted entries)."""
    open_day_one(h, "AAA")
    (stop,) = h.venue.stops("AAA")
    h.venue.apply_fill("AAA", True, 5.0, 100.0, h.venue.next_oid())  # 12 -> 17
    h.venue.mids["AAA"] = float(stop["triggerPx"]) - 1.0
    h.at(T0 + HOUR).run()
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "breach"
    assert "AAA" not in h.venue.positions and h.venue.stops("AAA") == []
    assert h.of("position_grew") == []
    assert "entry_overfill:AAA" not in criticals(h)


def _suspend_before_the_stop(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """The host sleeps between trade_opened and the stop, waking at :57:01."""
    original = executor.SleeveSession.protect
    state = {"done": False}

    def suspended(
        self: executor.SleeveSession,
        trade: core.OpenTrade,
        position: core.VenuePosition,
    ) -> bool:
        if not state["done"]:
            state["done"] = True
            h.clock.now = T0.replace(minute=57, second=1)
        return original(self, trade, position)

    monkeypatch.setattr(executor.SleeveSession, "protect", suspended)


def _quiet_calls(h: Harness) -> list[tuple[str, str, str | None]]:
    start = T0.replace(minute=57)
    return [c for c, t in zip(h.venue.calls, h.venue.call_times) if t >= start]


def test_a_deadline_between_trade_opened_and_its_stop_still_places_the_stop(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H2 (probe test_quiet_window_between_trade_opened_and_stop)."""
    h.shadow(entries=(E("AAA"), E("BBB")))
    no_children(h, "AAA")  # the fallback path (no venue child)
    _suspend_before_the_stop(h, monkeypatch)
    assert h.run() == 0
    (opened,) = h.of("trade_opened")
    (stop,) = h.venue.stops("AAA")  # the gap: no stop, exit 0, no critical
    assert float(stop["sz"]) == 12.0 and float(stop["triggerPx"]) == opened["stop_px"]
    # Inside the quiet window: the one protective stop order, no read at all.
    assert _quiet_calls(h) == [("exchange", "order", "AAA")]
    assert h.calls[-1]["trigger"] and h.calls[-1]["reduce_only"]
    assert not h.actions(coin="BBB") and not criticals(h)
    assert "sweep_deadline" in _severities(h)


def test_a_stop_that_cannot_rest_by_the_quiet_window_is_critical_and_placed_first(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H2: still unplaced -> critical stop_missing, exit 2; the next run's P3
    treats the opened trade without a stop as stop_missing and places it first."""
    h.shadow(entries=(E("AAA"),))
    no_children(h, "AAA")  # the fallback path (no venue child)
    h.trigger["AAA"] = ["reject", "reject"]
    _suspend_before_the_stop(h, monkeypatch)
    assert h.run() == 2
    assert criticals(h) == {"stop_missing:AAA"}
    assert _quiet_calls(h) == [("exchange", "order", "AAA")] * 2  # stops only
    assert not h.actions("order", coin="AAA", trigger=False, reduce_only=True)
    assert "AAA" in h.venue.positions and h.venue.stops("AAA") == []
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 2
    assert criticals(h) == {"stop_missing:AAA"}
    first = h.calls[0]
    assert (first["action"], first["coin"], first["trigger"]) == ("order", "AAA", True)
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0
    assert h.at(T0 + 2 * HOUR).run() == 0 and not criticals(h)


def test_only_a_reduce_only_stop_order_passes_the_quiet_window(tmp_path: Path) -> None:
    """H2: the exemption is one action type; every other mutation and every
    read stays refused in minutes 57-03 and after the phase deadline."""
    h = Harness(tmp_path)
    clock = FakeClock(T0.replace(minute=58))
    exchange = FakeExchange(h.venue, h, vault_address=SUB, wallet_address=AGENT)
    gateway = _gateway(exchange, clock)
    gateway.deadline = T0.replace(minute=57)
    stop = {"trigger": {"triggerPx": 96.0, "isMarket": True, "tpsl": "sl"}}
    cloid = "0xd15e" + "2" * 28
    for args, protective in (
        (("AAA", False, 1.0, 96.0, stop, True, cloid), False),  # not marked
        (("AAA", False, 1.0, 99.0, executor.IOC, True, cloid), True),  # an IOC
        (("AAA", True, 1.0, 96.0, stop, False, cloid), True),  # not reduce-only
    ):
        with pytest.raises(executor.GatewayRefused):
            gateway.order(*args, protective=protective)
    with pytest.raises(executor.GatewayRefused, match="quiet"):
        gateway.cancel("AAA", 1)
    with pytest.raises(executor.GatewayRefused, match="protective"):
        gateway._mutate("cancel", "AAA", new_risk=False, protective=True, send=_refuse)
    for protective in (False, True):
        with pytest.raises(executor.QuietWindowReached):
            gateway.pacer.before("info", 2, protective=protective)
    assert h.calls == []
    gateway.order("AAA", False, 1.0, 96.0, stop, True, cloid, protective=True)
    assert [(c["action"], c["trigger"]) for c in h.calls] == [("order", True)]


def test_a_quiet_window_abort_flags_positions_left_without_a_stop(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H2 backstop: any QuietWindowReached that skips P7 flags stop_missing
    (critical, exit 2) for owned positions the local book shows unprotected."""
    open_day_one(h, "AAA", "BBB")

    def vanish_then_quiet(self: executor.SleeveSession) -> None:
        h.venue.orders = [o for o in h.venue.orders if o["coin"] != "AAA"]
        self.orders = [o for o in self.orders if o.coin != "AAA"]
        raise executor.QuietWindowReached("quiet window")

    monkeypatch.setattr(executor.SleeveSession, "p5_exits", vanish_then_quiet)
    assert h.at(T0 + HOUR).run() == 2
    assert h.of("run_end")[-1]["status"] == "deadline"
    assert criticals(h) == {"stop_missing:AAA"}  # BBB keeps its stop


def test_a_stop_smaller_than_its_position_is_no_cover_at_an_abort(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H2 backstop: flag_unprotected counts a stop as cover only if it closes
    the whole position."""
    open_day_one(h, "AAA", "BBB")

    def shrink_then_quiet(self: executor.SleeveSession) -> None:
        self.orders = [
            replace(o, sz=o.sz / 2) if o.coin == "AAA" else o for o in self.orders
        ]
        raise executor.QuietWindowReached("quiet window")

    monkeypatch.setattr(executor.SleeveSession, "p5_exits", shrink_then_quiet)
    assert h.at(T0 + HOUR).run() == 2
    assert criticals(h) == {"stop_missing:AAA"}


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (executor.BudgetExhausted("hl_budget_exhausted"), 2),
        (core.TechnicalError("final read failed"), 2),
        (KeyError("oid"), 2),
        (core.RefusalError("the SDK's mainnet URL changed"), 3),
    ],
)
def test_every_abort_that_skips_p7_flags_positions_left_without_a_stop(
    h: Harness, monkeypatch: pytest.MonkeyPatch, error: Exception, code: int
) -> None:
    """H2 backstop on every outer handler (probe test_probe_flag_unprotected_
    outer_paths), the refusal branch included."""
    open_day_one(h, "AAA", "BBB")

    def vanish_then_fail(self: executor.SleeveSession) -> None:
        h.venue.orders = [o for o in h.venue.orders if o["coin"] != "AAA"]
        self.orders = [o for o in self.orders if o.coin != "AAA"]
        raise error

    monkeypatch.setattr(executor.SleeveSession, "p7_final", vanish_then_fail)
    assert h.at(T0 + HOUR).run() == code
    problems = {p["key"]: p["severity"] for p in h.of("run_end")[-1]["problems"]}
    assert problems["stop_missing:AAA"] == "critical"
    assert "stop_missing:BBB" not in problems


def test_the_sweep_places_missing_stops_before_it_repairs_others(h: Harness) -> None:
    """H2: positions with no stop at all go first, whatever the read order."""
    open_day_one(h, "AAA", "BBB")
    h.venue.positions["AAA"]["szi"] = 7.0  # AAA (read first) needs a resize
    h.venue.orders = [o for o in h.venue.orders if o["coin"] != "BBB"]
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 2
    assert criticals(h) == {"stop_missing:BBB"}
    first, second = h.calls[0], h.calls[1]
    assert (first["coin"], first["trigger"]) == ("BBB", True)
    assert (second["coin"], second["trigger"]) == ("AAA", True)
    assert len(h.venue.stops("AAA")) == 1 and len(h.venue.stops("BBB")) == 1
    assert float(h.venue.stops("AAA")[0]["sz"]) == 7.0


def test_any_exception_in_a_phase_is_critical_by_type_and_p7_still_runs(
    h: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """H4: a non-TechnicalError is caught per phase, recorded by TYPE only,
    and the final check still repairs protection."""
    open_day_one(h, "AAA")
    secret = "https://hooks.example.invalid/T000/SECRET-token"
    original = executor.SleeveSession.p6_entries

    def broken(self: executor.SleeveSession) -> None:
        original(self)
        h.venue.orders.clear()  # the stop vanished; only P7 can see it now
        raise ValueError(f"unexpected reply from {secret}")

    monkeypatch.setattr(executor.SleeveSession, "p6_entries", broken)
    capsys.readouterr()
    assert h.at(T0 + HOUR).run() == 2
    assert criticals(h) == {"technical_failure:p6_entries"}
    (problem,) = [
        p
        for p in h.of("run_end")[-1]["problems"]
        if p["key"] == "technical_failure:p6_entries"
    ]
    assert problem["message"] == "ValueError"
    assert len(h.venue.stops("AAA")) == 1  # P7 re-placed it
    assert h.of("run_end")[-1]["counts"]["stops_ok"] == 1
    text = outputs(capsys) + h.paths.journal.read_text() + h.paths.status.read_text()
    assert "SECRET-token" not in text and "hooks.example" not in text
    assert "ValueError" in text


def test_only_the_hourly_run_holds_budget_back_for_a_final_check(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H4 (review nit): run() holds FINAL_RESERVE_* back until P7; flatten,
    probe and status --venue have no P7, so they keep the full budget."""
    seen: list[bool] = []
    original = executor.HlPacer.before

    def spy(self: executor.HlPacer, kind: str, weight: int, **kw: Any) -> None:
        seen.append(self.final_reserve_open)
        original(self, kind, weight, **kw)

    monkeypatch.setattr(executor.HlPacer, "before", spy)
    open_day_one(h, "AAA")
    assert seen[0] is False and seen[-1] is True  # held back until P7
    for argv in (["probe"], ["status", "--venue"]):
        seen.clear()
        assert h.main(argv) == 0
        assert seen and all(seen)
    seen.clear()
    reason = ["--reason", "operator off switch"]
    flatten = ["flatten", "--all", *reason, "--approval", str(h.approval), *ARM]
    assert h.at(T0.replace(hour=2)).main(flatten) == 0
    assert seen and all(seen) and "AAA" not in h.venue.positions


def test_budget_exhaustion_before_p7_still_leaves_p7_its_reserve(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H4: an earlier phase exhausts the per-run budget; P7 still re-reads the
    book and places the missing stop on the budget held back for it."""
    open_day_one(h, "AAA")
    h.venue.orders.clear()  # P3 would re-place it...
    h.shadow(entries=(E("AAA"), E("BBB")))
    original = executor.SleeveSession.p2_reconcile

    def exhaust(self: executor.SleeveSession) -> None:
        original(self)
        held = getattr(executor, "FINAL_RESERVE_CALLS", 0)
        self.pacer.info_calls = self.cfg.hl_max_info_calls_per_run - held
        self.reader.all_mids()  # ...but P2 exhausts the budget first

    monkeypatch.setattr(executor.SleeveSession, "p2_reconcile", exhaust)
    assert h.at(T0 + HOUR).run() == 2
    assert criticals(h) == {"hl_budget_exhausted"}
    assert len(h.venue.stops("AAA")) == 1
    assert not h.actions(coin="BBB")  # no entry on the exhausted budget
    end = h.of("run_end")[-1]
    assert end["counts"]["stops_ok"] == 1
    assert end["traffic"]["info_calls"] <= CFG.hl_max_info_calls_per_run


@pytest.mark.parametrize(
    "value",
    [
        "https://hooks.example.invalid/t0k # note",  # an inline comment
        "'https://hooks.example.invalid/t0k # quoted note'",
        "https://hooks.example.invalid/t0k\tx",
        "http://hooks.example.invalid/t0k",
        "hooks.example.invalid/t0k",
        "https:///t0k",
    ],
)
def test_alert_urls_must_be_one_plain_https_url(
    h: Harness, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """H5: the loader refuses what urllib would choke on, never echoing it."""
    for name in (core.ENV_WEBHOOK, core.ENV_DEADMAN):
        h.write_env(**{name: value})
        with pytest.raises(core.RefusalError, match=name) as info:
            executor.load_sleeve_env(h.env_file, include_private_key=False)
        assert "t0k" not in str(info.value) and "hooks.example" not in str(info.value)
    h.write_env()
    monkeypatch.setenv(core.ENV_DEADMAN, value)  # the process env is checked too
    with pytest.raises(core.RefusalError, match=core.ENV_DEADMAN):
        executor.load_sleeve_env(h.env_file, include_private_key=False)
    fragment = "https://hc-ping.example.invalid/t0k#no-space-fragment"
    monkeypatch.setenv(core.ENV_DEADMAN, fragment)
    env = executor.load_sleeve_env(h.env_file, include_private_key=False)
    assert env.deadman == fragment


@pytest.mark.parametrize("name", [core.ENV_DEADMAN, core.ENV_WEBHOOK])
def test_an_alert_url_with_an_inline_comment_refuses_the_run_without_leaking(
    h: Harness,
    sinks: SimpleNamespace,
    capsys: pytest.CaptureFixture,
    name: str,
) -> None:
    """H5 (probes test_gap_deadman_url_with_inline_comment_leaks_and_fails_the_run
    and test_safe_webhook_with_inline_comment_does_not_leak_but_goes_silent)."""
    token = "0f1e2d3c-4b5a-6978-8a9b-abcdef012345"
    h.write_env(**{name: f"https://hc-ping.example.invalid/{token} # note"})
    h.shadow(entries=(E("AAA"),))
    assert h.run() == 3  # refused at env load: no run, no order, no ping
    assert h.calls == [] and h.venue.calls == [] and not h.paths.journal.exists()
    assert sinks.pings == [] and sinks.webhooks == []
    assert sinks.banners and sinks.banners[-1][0] == executor.CRITICAL_TITLE
    assert h.main(["probe"]) == 3  # the operator's probe refuses it first
    text = outputs(capsys) + h.paths.status.read_text() + h.paths.alerts.read_text()
    assert token not in text and "hc-ping" not in text
    assert name in text


def test_http_helpers_never_raise_and_log_the_exception_type_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """H5 (probe show_deadman.py): InvalidURL carries the URL in its message."""
    token = "0f1e2d3c-4b5a-6978-8a9b-abcdef012345"
    REAL_HTTP_GET(f"https://hc-ping.example.invalid/{token} # dm")
    REAL_HTTP_POST(f"https://hooks.example.invalid/{token} # hook", b"{}", "t")

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"failed for https://hc-ping.example.invalid/{token}")

    monkeypatch.setattr(executor.urllib.request, "urlopen", boom)
    REAL_HTTP_GET(f"https://hc-ping.example.invalid/{token}")
    REAL_HTTP_POST(f"https://hooks.example.invalid/{token}", b"{}", "t")
    err = capsys.readouterr().err
    failures = [json.loads(line) for line in err.splitlines()]
    assert [(f["channel"], f["failure"]) for f in failures] == [
        ("deadman", "InvalidURL"),
        ("webhook", "InvalidURL"),
        ("deadman", "RuntimeError"),
        ("webhook", "RuntimeError"),
    ]
    assert token not in err and "hc-ping" not in err


def test_a_venue_flat_other_coin_takes_no_entry_in_the_same_run(h: Harness) -> None:
    """H6: a same-run reversal must not trade against a position the reads miss."""
    open_day_one(h, "AAA")
    del h.venue.positions["AAA"]  # flat with no fill the sleeve can explain
    next_day(
        h,
        holding=(E("AAA"),),
        exits=("AAA",),
        entries=(E("AAA", side="short", day=T + DAY),),
    )
    h.calls.clear()
    assert h.run() == 2
    assert "venue_flat_other:AAA" in criticals(h)
    (skip,) = h.of("skip")
    assert skip["reason"] == "coin_not_flat" and skip["retryable"] is True
    assert h.calls == []  # no leverage update, no entry, and its stop is kept
    assert len(h.venue.stops("AAA")) == 1


def test_a_canary_coin_whose_half_size_is_below_one_lot_is_refused(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    """H7 (venue-mechanics canary nit): refused BEFORE any order."""
    h.shadow()
    h.venue.universe.append({"name": "LOTS", "szDecimals": 0, "maxLeverage": 10})
    h.venue.mids["LOTS"] = 14.0  # $15 buys 1 lot; its stop (12.60) clears the minimum
    arm = ["--approval", str(h.approval), *ARM]
    assert h.main(["canary", "--coin", "LOTS", *arm]) == 3
    assert h.calls == [] and "LOTS" not in h.venue.positions
    assert "half its size must be at least one lot" in outputs(capsys)


def test_probe_capacity_is_a_hint_never_a_failure(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    """H8: below the 0.6 x book guideline the probe says what happens (later
    entries scale or skip as sub_collateral), not that something failed."""
    assert h.main(["probe"]) == 0  # sub free 2,500 < 0.6 x 4,800
    out = capsys.readouterr().out
    assert "est_full_book_margin_usd=2880.00" in out
    assert "capacity_guideline=0.6 x book" in out
    hint = next(line for line in out.splitlines() if line.startswith("capacity_hint="))
    assert hint.startswith("capacity_hint=below_guideline_not_a_failure")
    assert "sub_collateral" in hint and "25%" in hint
    assert "capacity_ok" not in out
    h.venue.usdc = {MASTER: 1000.0, SUB: 3000.0}  # 3,000 >= 0.6 x 4,000
    assert h.main(["probe"]) == 0
    assert "capacity_hint=full_book_fits_guideline" in capsys.readouterr().out


# ----------------------------------------------------------------- static


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def test_executor_imports_and_sdk_confinement() -> None:
    tree = _tree(_SCRIPT)
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    sdk_imports: list[str] = []
    roots: set[str] = set()
    load_sdk = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_load_sdk"
    )
    inside = {id(node) for node in ast.walk(load_sdk)}
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            root = name.split(".")[0]
            if root in {"hyperliquid", "eth_account"}:
                assert id(node) in inside, name
                sdk_imports.append(name)
            else:
                roots.add(root)
    assert sorted(sdk_imports) == [
        "eth_account",
        "hyperliquid.exchange",
        "hyperliquid.utils.constants",
        "hyperliquid.utils.types",
    ]
    assert roots - stdlib == {"requests", "d1_shadow_runner", "d1_sleeve_core"}
    assert not any(root.startswith("cohort") or root == "hypervector" for root in roots)


def test_executor_has_one_exchange_construction_and_no_banned_calls() -> None:
    for path in (_SCRIPT, _CORE):
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in BANNED, (path.name, node.attr)
            if isinstance(node, ast.Name):
                assert node.id not in BANNED, (path.name, node.id)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value != ".env" and not node.value.endswith("/.env")
    calls = [
        node
        for node in ast.walk(_tree(_SCRIPT))
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "Exchange")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "Exchange")
        )
    ]
    assert len(calls) == 1
    (call,) = calls
    keywords = {k.arg: k for k in call.keywords}
    assert set(keywords) == {
        "meta",
        "vault_address",
        "account_address",
        "spot_meta",
        "timeout",
    }
    assert isinstance(keywords["account_address"].value, ast.Constant)
    assert keywords["account_address"].value.value is None


def test_only_the_stop_placement_is_protective() -> None:
    """The quiet-window exemption has exactly one call site: place_stop."""
    tree = _tree(_SCRIPT)
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    sites: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.keyword)
            and node.arg == "protective"
            and isinstance(node.value, ast.Constant)
            and node.value.value is True
        ):
            owner = [
                f.name for f in functions if id(node) in {id(x) for x in ast.walk(f)}
            ]
            sites.append(owner[-1])
    assert sites == ["place_stop"]


def test_environment_and_subprocess_are_confined() -> None:
    tree = _tree(_SCRIPT)
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        ):
            owner = [
                f.name for f in functions if id(node) in {id(x) for x in ast.walk(f)}
            ]
            assert owner and owner[-1] in {"load_sleeve_env", "engine_key_absent"}, (
                owner
            )
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "subprocess"
            and node.attr == "run"
        ):
            owner = [
                f.name for f in functions if id(node) in {id(x) for x in ast.walk(f)}
            ]
            assert owner == ["_notify_mac"], owner
        if isinstance(node, ast.Name):
            assert node.id not in {"__import__", "eval", "exec", "compile"}
    source = _SCRIPT.read_text()
    assert "getenv" not in source and "load_dotenv" not in source
    assert "hyperliquid-testnet" not in source


def test_plist_example_is_unarmed_hourly_and_isolated() -> None:
    raw = _PLIST.read_bytes()
    comment = raw.split(b"<!--", 1)[1].split(b"-->", 1)[0]
    assert b"--" not in comment
    plist = plistlib.loads(raw)
    repo = "/Users/gestas/Prototypes/hypervector"
    assert plist["Label"] == "local.hypervector.sleeve.d1_executor"
    arguments = plist["ProgramArguments"]
    assert arguments[:5] == [
        f"{repo}/.venv/bin/python",
        "-I",
        "-u",
        f"{repo}/scripts/d1_sleeve_executor.py",
        "run",
    ]
    approval = arguments[arguments.index("--approval") + 1]
    assert approval.startswith(f"{repo}/docs/live-approvals/")
    assert "--enabled" not in arguments and "--i-accept-live-risk" not in arguments
    assert plist["StartCalendarInterval"] == {"Minute": 15}
    assert plist["RunAtLoad"] is False and "KeepAlive" not in plist
    assert "EnvironmentVariables" not in plist
    log = f"{repo}/data/runtime/d1_sleeve/executor.log"
    assert plist["StandardOutPath"] == log and plist["StandardErrorPath"] == log
    assert plist["ProcessType"] == "Standard" and plist["ExitTimeOut"] == 60
    assert plist["WorkingDirectory"] == repo


def test_script_runs_under_isolated_python() -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "approval-template" in result.stdout


def test_importing_the_executor_has_no_side_effects(tmp_path: Path) -> None:
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import d1_sleeve_executor, "
        "d1_sleeve_core; print('hyperliquid' in sys.modules, 'eth_account' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, str(_SCRIPT.parent)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False"
    assert list(tmp_path.iterdir()) == []


def test_runner_is_unchanged() -> None:
    digest = hashlib.sha256((_ROOT / "scripts" / "d1_shadow_runner.py").read_bytes())
    assert digest.hexdigest() == CFG.shadow_runner_sha256
    assert runner.ShadowConfig().fingerprint() == CFG.shadow_config_fingerprint


# ------------------------------------------------ A1 venue-attached stop, A2 guard
# The failure class the H1 rounds kept patching: a lost POST response plus an
# info node lagging >= 50 s made the sleeve's own fill look unowned or flat,
# leaving it without a stop. A1 attaches the stop to the entry at the venue;
# A2 gives every position a read shows a stop, owned or not.


@pytest.mark.parametrize(
    "scenario",
    ["p7_reads_lag", "quiet_window_abort", "p7_deadline", "p7_read_fails"],
)
def test_a_lost_reply_and_a_lagging_node_leave_the_fill_protected_by_its_child(
    h: Harness, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    """A1: the entry's reply is lost, orderStatus lags (never_landed), the
    retry is a definitive no_fill and every position read of the run misses
    the fill (the H1 fault with P7 reading the same node, or P7 lost). Before
    A1 the fill had no stop until a later run adopted it (and none at all if
    the adoption failed). Now the venue placed its child with the fill: it
    rests at the rule distance from the reference mid in this run, whatever
    the reads say, and the next run adopts the trade with the child as its
    stop (the fill was at the reference: nothing is re-placed)."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "no_fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    reads = _scripted_position_reads(h, monkeypatch, "AAA", ["hide"] * 50)
    if scenario != "p7_reads_lag":
        _p7_fault(h, monkeypatch, scenario)
    assert h.run() == 2
    assert "unresolved_entry:AAA" in criticals(h)
    assert h.venue.positions["AAA"]["szi"] == 12.0
    (child,) = h.venue.stops("AAA")  # the gap: no stop at all in this run
    assert child["cloid"] == child_cloid("AAA") and child["reduceOnly"]
    assert (child["side"], float(child["sz"]), float(child["triggerPx"])) == (
        "A",
        12.0,
        96.0,
    )
    assert not h.of("trade_opened")
    reads["truth"] = True
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and opened["stop_px"] == 96.0
    (stop,) = h.venue.stops("AAA")
    assert stop["cloid"] == child_cloid("AAA")  # kept: it is the rule stop
    assert h.calls == []  # nothing placed, nothing cancelled, no new entry
    assert h.book().known_oids[stop["oid"]] == (tid("AAA"), "stop")


@pytest.mark.parametrize("final", ["p7_reads_lag", "quiet_window_abort"])
def test_a_reversal_entry_whose_reads_show_the_closed_side_rests_its_child(
    h: Harness, monkeypatch: pytest.MonkeyPatch, final: str
) -> None:
    """A1 on the round-3 B1 path: P5 closes the AAA long, P6 enters AAA short,
    the short's reply is lost, orderStatus lags, and every read shows the
    sleeve's own closed long. The short's buy-stop child rests from the fill
    (the gap: a naked short, exit 0 when P7 was lost at the cut-off)."""
    open_day_one(h, "AAA")
    next_day(h, holding=(E("AAA"),), exits=("AAA",), entries=(E("AAA", side="short"),))
    h.venue.mids["AAA"] = 98.0
    h.ioc["AAA"] = [{"mode": "fill"}, {"mode": "raise_after"}, {"mode": "fill"}]
    short_id = tid("AAA", "short", T + DAY)
    short = core.cloid_for(CFG, SUB, short_id, "entry", 1)
    _lagging_order_status(h, monkeypatch, short)
    reads = _reads_show_the_closed_long(h, monkeypatch, "AAA")
    if final != "p7_reads_lag":
        _p7_fault(h, monkeypatch, final)
    when = (T0 + DAY).replace(minute=44, second=20)  # the cut-off: no retry
    assert h.at(when).run() == 2
    assert reads["n"] > 0 and h.venue.positions["AAA"]["szi"] == -12.0
    buys = [o for o in h.venue.stops("AAA") if o["side"] == "B"]
    (child,) = buys
    assert child["cloid"] == child_cloid("AAA", 1, "short", T + DAY)
    assert (float(child["sz"]), float(child["triggerPx"])) == (12.0, 102.0)
    reads["truth"] = True
    assert h.at(when + HOUR).run() == 0 and not criticals(h)
    (opened,) = h.of("trade_opened", trade_id=short_id)
    assert opened["recovered"] is True and opened["stop_px"] == 102.0
    (stop,) = h.venue.stops("AAA")  # the stale read's guard was cancelled
    assert stop["cloid"] == child["cloid"]


def test_a_partially_filled_entry_has_no_child_and_is_stopped_from_its_fill(
    h: Harness,
) -> None:
    """The venue cancels the children of a parent that does not fully fill
    (an IOC's remainder is cancelled): the sleeve places the stop from the
    fill, as before A1. The remainder's own full fill rests a child of the
    remainder's size only; it is replaced by the stop over the position."""
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.5}, {"mode": "no_fill"}]
    h.ioc["BBB"] = [{"mode": "fill", "fraction": 0.5}, {"mode": "fill"}]
    assert h.run() == 0
    outcomes = {
        o["cloid"]: o["status"] for o in h.of("outcome", action="order")
    }  # each cloid's last outcome
    assert outcomes[child_cloid("AAA", 1)] == "canceled"  # partial: no child
    assert outcomes[child_cloid("AAA", 2)] == "canceled"  # no fill: no child
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 6.0 and float(stop["triggerPx"]) == 96.0
    assert stop["cloid"] == child_cloid("AAA", 3)  # placed by the sleeve
    assert outcomes[child_cloid("BBB", 1)] == "canceled"
    assert outcomes[child_cloid("BBB", 2)] == "resting"  # the 6.0 remainder's
    (stop,) = h.venue.stops("BBB")
    assert float(stop["sz"]) == 12.0 and stop["cloid"] == child_cloid("BBB", 3)
    cancelled = h.actions("cancelByCloid", coin="BBB")
    assert [c["cloid"] for c in cancelled] == [child_cloid("BBB", 2)]
    assert _severities(h)["partial_fill"] == "notice"


def test_a_child_on_a_coin_the_reads_show_flat_is_never_cancelled(
    h: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A resting child proves its entry fully filled, so a read that shows the
    coin flat lags: neither the sweep's flat-coin cleanup nor flatten may
    cancel it while its trade never opened (keeps_on_flat)."""
    h.shadow(entries=(E("AAA"),))
    real_info = _hide_position(h, monkeypatch, "AAA", 100)
    assert h.run() == 2 and "fill_not_visible:AAA" in criticals(h)
    assert len(h.venue.stops("AAA")) == 1
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0  # still hidden: the child survives P3 and P7
    argv = ["flatten", "--coin", "AAA", "--reason", "rollback"]
    assert h.at(T0 + 2 * HOUR).main([*argv, "--approval", str(h.approval), *ARM]) == 0
    assert '"skipped":"not_owned_or_flat"' in capsys.readouterr().out
    assert not h.actions("cancelByCloid") and not h.actions("cancel")
    (child,) = h.venue.stops("AAA")
    assert child["cloid"] == child_cloid("AAA")
    monkeypatch.setattr(h.venue, "info", real_info)
    assert h.at(T0 + 3 * HOUR).run() == 0 and not criticals(h)
    assert h.of("trade_opened")[0]["recovered"] is True
    assert h.venue.stops("AAA") == [child]


def test_the_leftover_stop_of_a_closed_trade_on_a_flat_coin_is_still_cancelled(
    h: Harness,
) -> None:
    """Control for keeps_on_flat: once a trade is closed, its orders left on
    the flat coin are cancelled (the venue stop fired; a duplicate remains)."""
    open_day_one(h, "AAA")
    h.venue.add_stop("AAA", is_buy=False, sz=12.0, trigger=95.0, cloid=None)
    stale = h.venue.orders[-1]
    h.venue.orders.remove(stale)
    duplicate = core.cloid_for(CFG, SUB, tid("AAA"), "stop", 7)
    h.venue.trigger_stop("AAA")
    h.venue.add_stop("AAA", is_buy=False, sz=12.0, trigger=96.0, cloid=duplicate)
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "venue_stop"
    assert [c["cloid"] for c in h.actions("cancelByCloid")] == [duplicate]
    assert not h.venue.orders


def test_a_child_that_fires_before_any_stop_placement_reconciles_as_a_venue_stop(
    h: Harness,
) -> None:
    """The child's ack carries no oid; the first listing of it journals one
    (learn_listed_oids), so its fill reconciles the trade as venue_stop, not
    as a critical venue_flat_other."""
    open_day_one(h, "AAA")
    (child,) = h.venue.stops("AAA")
    assert child["cloid"] == child_cloid("AAA")
    learned = h.of("outcome", cloid=child_cloid("AAA"))[-1]
    assert (learned["status"], learned["venue_status"], learned["oid"]) == (
        "open",
        "listed",
        child["oid"],
    )
    h.venue.trigger_stop("AAA")
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "venue_stop"


def test_an_unverified_mark_is_not_settled_while_its_child_is_listed(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A listed child proves its entry filled: a later session's flat read
    (a node an hour behind) must not settle the position_unverified mark,
    or the trade would retry and double the position. It stays owned and
    unresolved until a read shows the fill."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    _fail_the_reread(h, monkeypatch, first, core.TechnicalError("hl read failed"))
    reads = _scripted_position_reads(h, monkeypatch, "AAA", ["hide"] * 200)
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    assert h.run() == 2
    assert h.book().intents[first].unverified
    assert h.at(T0 + HOUR).run() == 2
    assert "unresolved_entry:AAA" in criticals(h)
    assert h.book().intents[first].unverified  # not settled: the child is listed
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    assert len(entries) == 1 and h.venue.positions["AAA"]["szi"] == 12.0
    reads["truth"] = True
    assert h.at(T0 + 2 * HOUR).run() == 0 and not criticals(h)
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and len(h.venue.stops("AAA")) == 1


def test_an_owned_position_whose_protection_raised_is_guarded_at_its_rule_stop(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2 behind protect(): the owned AAA lost its stop and its protection
    raised before placing one. The sweep's guard pass gives it the rule stop
    (the trade's own stop price), which P7 then verifies as its stop (I6)."""
    open_day_one(h, "AAA")
    h.venue.orders.clear()
    original = executor.SleeveSession.check_leverage
    state = {"fired": False}

    def broken(self: executor.SleeveSession, *args: Any, **kwargs: Any) -> bool:
        if not state["fired"]:
            state["fired"] = True
            raise core.TechnicalError("hl info transport error")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(executor.SleeveSession, "check_leverage", broken)
    assert h.at(T0 + HOUR).run() == 2
    assert "technical_failure:AAA" in criticals(h)
    (guard,) = h.of("intent", role="guard")
    assert guard["context"]["source"] == "rule_stop" and guard["trigger_px"] == 96.0
    (stop,) = h.venue.stops("AAA")
    assert float(stop["triggerPx"]) == 96.0 and float(stop["sz"]) == 12.0
    assert h.of("run_end")[-1]["counts"]["stops_ok"] == 1
    assert "AAA" in h.venue.positions and not h.of("trade_closed")


def test_a_guard_that_cannot_rest_is_critical_and_never_trades(h: Harness) -> None:
    """A2: a position the sleeve does not own whose guard stop is rejected
    stays critical (unprotected_position); it is never closed or reduced."""
    h.venue.positions["AAA"] = {
        "szi": -3.0,
        "entryPx": 100.0,
        "type": "isolated",
        "value": 2,
        "liq": 145.0,
    }
    h.trigger["AAA"] = ["reject"] * 10
    h.shadow()
    assert h.run() == 2
    assert {"unknown_position:AAA", "unprotected_position:AAA"} <= criticals(h)
    guards = h.actions("order", coin="AAA")
    assert len(guards) == 4  # two in P3's sweep, two in P7's
    assert all(g["trigger"] and g["reduce_only"] and g["is_buy"] for g in guards)
    assert all(g["limit_px"] == 115.0 for g in guards)  # 15% from the entry
    assert h.venue.positions["AAA"]["szi"] == -3.0 and h.venue.stops("AAA") == []


def test_a_canary_whose_child_is_not_listed_with_its_cloid_fails(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    """The canary proves A1 live: the venue must place the entry's child on
    the full fill and list it with its cloid, size and trigger."""
    h.shadow()
    h.child["BTC"] = ["no_cloid"]
    argv = ["canary", "--coin", "BTC", "--approval", str(h.approval), *ARM]
    assert h.main(argv) == 2
    out = capsys.readouterr().out
    assert "canary_child_listed=true" in out
    assert "canary_child_cloid_matches=false" in out
    assert "canary_failed" in {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert not h.venue.positions
    h2 = Harness(h.tmp / "rejected")
    h2.shadow()
    h2.child["BTC"] = ["reject"]
    assert (
        h2.main(["canary", "--coin", "BTC", "--approval", str(h2.approval), *ARM]) == 2
    )
    out = capsys.readouterr().out
    assert "canary_child_listed=false" in out and not h2.venue.positions


def test_a_canary_whose_grouped_reply_does_not_parse_fails(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    """d1protect round 1 (verifier non-blocking): the canary proves the live
    grouped reply parses as the entry path needs it (the IOC acked filled,
    so its child resting). A reply the parser does not know makes the send
    ambiguous: orderStatus still resolves the fill and the venue still lists
    the child, but every live entry would take the ambiguous path, so the
    canary fails (and is flattened)."""
    h.shadow()
    h.child["BTC"] = ["garbled"]
    argv = ["canary", "--coin", "BTC", "--approval", str(h.approval), *ARM]
    assert h.main(argv) == 2
    out = capsys.readouterr().out
    assert "canary_entry_ack_parsed=false" in out
    assert "canary_entry_filled=true" in out and "canary_child_listed=true" in out
    assert "canary_failed" in {p["code"] for p in h.of("run_end")[-1]["problems"]}
    assert not h.venue.positions


def test_the_gateway_sends_the_entry_and_its_child_as_one_normal_tpsl_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A1 on the real SDK: one signed /exchange POST for the sub-account whose
    action groups the IOC and a reduce-only stop-market child (normalTpsl) of
    the same size on the closing side; a child on the wrong side of the limit
    is refused before anything is sent."""
    import hyperliquid.exchange as sdk_exchange
    import hyperliquid.utils.signing as signing

    sdk = executor._load_sdk()
    account = Account.create()
    vaults: list[Any] = []
    original = signing.sign_l1_action

    def spy(
        wallet: Any, action: Any, vault: Any, nonce: Any, expires: Any, mainnet: bool
    ) -> Any:
        vaults.append(vault)
        return original(wallet, action, vault, nonce, expires, mainnet)

    monkeypatch.setattr(sdk_exchange, "sign_l1_action", spy)
    captured: list[requests.PreparedRequest] = []

    class Capture(BaseAdapter):
        def send(self, request: requests.PreparedRequest, **kwargs: Any) -> Any:
            captured.append(request)
            response = requests.Response()
            response.status_code = 200
            filled = {"filled": {"totalSz": "0.012", "avgPx": "100000", "oid": 42}}
            body = {
                "status": "ok",
                "response": {
                    "type": "order",
                    "data": {"statuses": [filled, "waitingForTrigger"]},
                },
            }
            response._content = json.dumps(body).encode()
            response.url = request.url
            return response

        def close(self) -> None:
            pass

    meta = {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 40}]}
    exchange = executor.build_exchange(
        sdk, key=account.key.hex(), meta=meta, sub=SUB, cfg=CFG, transport=Capture()
    )
    clock = FakeClock(T0)
    gateway = executor.SubAccountGateway(
        exchange,
        cfg=CFG,
        env=executor.SleeveEnv(master=MASTER, sub=SUB, agent=account.address.lower()),
        markets=core.parse_meta(meta),
        pacer=executor.HlPacer(CFG, clock=clock, sleep=clock.sleep),
        clock=clock,
        cloid_cls=sdk.Cloid,
    )
    gateway.allow_new_risk = True
    entry = core.cloid_for(CFG, SUB, tid("BTC"), "entry", 1)
    child = core.cloid_for(CFG, SUB, tid("BTC"), "stop", 1)
    with pytest.raises(executor.GatewayRefused, match="protective side"):
        gateway.order_with_stop("BTC", True, 0.012, 100_500.0, entry, 101_000.0, child)
    assert captured == []
    gateway.set_expires_after(_ms(T0) + 45_000)
    response = gateway.order_with_stop(
        "BTC", True, 0.012, 100_500.0, entry, 96_000.0, child
    )
    parent, placed = core.parse_grouped_statuses(response)
    assert parent.status == "filled" and placed.status == "waiting"
    (request,) = captured
    body = json.loads(request.body)
    assert body["vaultAddress"] == SUB and vaults == [SUB]
    action = body["action"]
    assert action["type"] == "order" and action["grouping"] == "normalTpsl"
    ioc, stop = action["orders"]
    assert ioc["t"] == {"limit": {"tif": "Ioc"}} and ioc["r"] is False
    assert ioc["b"] is True and ioc["c"] == entry and ioc["s"] == "0.012"
    assert stop["t"] == {
        "trigger": {"isMarket": True, "triggerPx": "96000", "tpsl": "sl"}
    }
    assert stop["r"] is True and stop["b"] is False and stop["s"] == "0.012"
    assert stop["c"] == child and stop["a"] == ioc["a"] == 0
    gateway.allow_new_risk = False  # an entry is new risk: never in the sweep
    with pytest.raises(executor.GatewayRefused, match="new risk"):
        gateway.order_with_stop("BTC", True, 0.012, 100_500.0, entry, 96_000.0, child)


def test_a_position_first_read_by_the_last_final_read_is_guarded_in_that_run(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2: a position no stop covers that only P7's second read shows gets
    its guard in that run (P7 sweeps once more), not first in the next."""
    h.shadow()
    original = executor.SleeveSession.adopt_lagging_entries
    state = {"n": 0}

    def appears(self: executor.SleeveSession) -> None:
        state["n"] += 1
        if state["n"] == 1:  # after P7's first read: the second read shows it
            h.venue.apply_fill("DDD", False, 4.0, 100.0, h.venue.next_oid())
        original(self)

    monkeypatch.setattr(executor.SleeveSession, "adopt_lagging_entries", appears)
    assert h.run() == 2 and criticals(h) == {"unknown_position:DDD"}
    (guard,) = h.venue.stops("DDD")
    assert (guard["side"], float(guard["sz"])) == ("B", 4.0)
    assert float(guard["triggerPx"]) == 115.0  # no ATR anywhere: 15% from entry
    assert h.venue.positions["DDD"]["szi"] == -4.0


def test_a_guard_acked_but_never_listed_is_critical_at_the_final_check(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2: the final check verifies guards from the listing, not the ack: a
    guard the venue acked but does not list leaves the position bare, which
    is critical unprotected_position (P7 re-sweeps once, within the cap)."""
    h.venue.positions["DDD"] = {
        "szi": 2.0,
        "entryPx": 100.0,
        "type": "isolated",
        "value": 3,
        "liq": 70.0,
    }
    real_add = FakeVenue.add_stop

    def dropped(self: FakeVenue, coin: str, **kwargs: Any) -> int:
        oid = real_add(self, coin, **kwargs)
        if kwargs.get("cloid", "").startswith("0xd15e"):
            self.orders = [o for o in self.orders if o["oid"] != oid]
        return oid

    monkeypatch.setattr(FakeVenue, "add_stop", dropped)
    h.shadow()
    assert h.run() == 2
    assert criticals(h) == {"unknown_position:DDD", "unprotected_position:DDD"}
    guards = h.actions("order", coin="DDD")
    assert len(guards) == 3  # P3, P7's sweep, P7's re-sweep: one each, acked
    assert all(g["trigger"] and g["reduce_only"] and not g["is_buy"] for g in guards)
    assert h.venue.positions["DDD"]["szi"] == 2.0 and h.venue.stops("DDD") == []


def test_a_dry_run_plans_the_guard_of_a_position_it_does_not_own(
    h: Harness, capsys: pytest.CaptureFixture
) -> None:
    """A2 in a dry run: the guard is planned, never sent (no signing)."""
    h.venue.positions["DDD"] = {
        "szi": 2.0,
        "entryPx": 100.0,
        "type": "isolated",
        "value": 3,
        "liq": 70.0,
    }
    h.shadow()
    assert h.run(armed=False) == 2
    plans = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith('{"plan"')
    ]
    (guard,) = [p for p in plans if p["plan"] == "guard"]
    assert guard["coin"] == "DDD" and guard["reduce_only"] and guard["sz"] == 2.0
    assert guard["trigger_px"] == 85.0 and not guard["is_buy"]
    assert not [c for c in h.venue.calls if c[0] == "exchange"]


def test_a_guard_on_a_coin_a_read_shows_flat_is_never_cancelled(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2: a guard protects a position the sleeve does not own; a later read
    that shows the coin flat may lag it, so the flat-coin cleanup keeps the
    guard (keeps_on_flat)."""
    h.venue.positions["DDD"] = {
        "szi": 2.0,
        "entryPx": 100.0,
        "type": "isolated",
        "value": 3,
        "liq": 70.0,
    }
    h.shadow()
    assert h.run() == 2 and criticals(h) == {"unknown_position:DDD"}
    (guard,) = h.venue.stops("DDD")
    _hide_position(h, monkeypatch, "DDD", 100)
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0  # every read misses DDD
    assert h.venue.stops("DDD") == [guard] and h.calls == []


def test_a_close_sent_in_the_session_voids_the_proof_of_its_fills(
    h: Harness,
) -> None:
    """The proof of fills (children, acks) holds only while nothing reduced
    the position: after this session's own partial close, a read below the
    child's size is the close, not a lag. No false fill_not_visible; the
    stop is re-sized to what is left and the child is cancelled."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [
        {"mode": "fill", "px": 100.2},  # the child (96.0) is not the fill's stop
        {"mode": "fill", "fraction": 0.5},  # the unprotectable close: half
        {"mode": "no_fill"},
        {"mode": "no_fill"},
    ]
    h.trigger["AAA"] = ["reject", "reject"]
    assert h.run() == 2
    assert criticals(h) == {"unprotectable:AAA", "exit_incomplete:AAA"}
    assert h.venue.positions["AAA"]["szi"] == 6.0
    (stop,) = h.venue.stops("AAA")  # the child is cancelled
    assert float(stop["sz"]) == 6.0 and float(stop["triggerPx"]) == 96.2
    assert child_cloid("AAA") in {c["cloid"] for c in h.actions("cancelByCloid")}


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
def test_a_close_is_verified_against_the_fills_the_children_prove(
    h: Harness, monkeypatch: pytest.MonkeyPatch, taker_bps: float
) -> None:
    """A doubled lost-reply entry: its two children prove 24 while every read
    shows 12. P7 closes it as a breach; the close IOC takes the 12 the read
    shows, and the read after it (a node lagging the close) shows the coin
    flat. The acked close fills explain that read's 12 but not the 24 the
    children prove: critical exit_incomplete, and the trade and both
    children stay (without the proof: trade_closed, children cancelled, 12
    left naked). ``taker`` (fills 3 bps above the mid): the retry's child
    was replaced at open by the fill-anchored stop, and the retry's ack
    proves its 12 in its place (d1protect round 1: exit 0, 12 naked)."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [
        {"mode": "raise_after"},
        {"mode": "fill"},
        {"mode": "fill"},  # the breach close: 12 of the 24
        {"mode": "no_fill"},
        {"mode": "no_fill"},
    ]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    real_info = h.venue.info
    seen = {"n": 0}

    def info(payload: dict) -> Any:
        answer = real_info(payload)
        if (
            payload["type"] != "clearinghouseState"
            or payload.get("user") != SUB
            or "AAA" not in h.venue.positions
        ):
            return answer
        seen["n"] += 1
        closing = any(
            c["action"] == "order"
            and c["coin"] == "AAA"
            and c["reduce_only"]
            and not c["trigger"]
            for c in h.calls
        )
        answer = dict(answer)
        rows = [a for a in answer["assetPositions"] if a["position"]["coin"] != "AAA"]
        if seen["n"] > 1 and not closing:  # the re-read hides it; then 12
            pos = dict(h.venue.positions["AAA"], szi=12.0)
            rows.append(
                {"position": h.venue.position_record("AAA", pos), "type": "oneWay"}
            )
        answer["assetPositions"] = rows
        return answer

    monkeypatch.setattr(h.venue, "info", info)
    original_p7 = executor.SleeveSession.p7_final

    def through_the_stop(self: executor.SleeveSession) -> None:
        h.venue.mids["AAA"] = 95.0
        self.mids["AAA"] = 95.0
        original_p7(self)

    monkeypatch.setattr(executor.SleeveSession, "p7_final", through_the_stop)
    assert h.run() == 2
    assert "exit_incomplete:AAA" in criticals(h)
    assert not h.of("trade_closed") and h.venue.positions["AAA"]["szi"] == 12.0
    stops = h.venue.stops("AAA")
    kept = 3 if taker_bps else 2  # the fill-anchored stop, or the retry's child
    assert sorted(o["cloid"] for o in stops) == sorted(
        [child_cloid("AAA", 1), child_cloid("AAA", kept)]
    )
    assert all(float(o["sz"]) == 12.0 for o in stops)


def _position_node_lagging(
    h: Harness,
    monkeypatch: pytest.MonkeyPatch,
    lag_s: float,
    fresh: frozenset[int] = frozenset(),
) -> None:
    """A physically consistent lag: every sub position read is answered by
    one info node ``lag_s`` seconds behind the venue (the state it held
    then), except the reads numbered in ``fresh`` (0-based), which a
    current node answers; order reads and orderStatus are current (another
    node)."""
    snaps: list[tuple[datetime, dict]] = []
    real_info = h.venue.info
    real_order = FakeExchange.order
    reads = {"n": 0}

    def snap() -> None:
        snaps.append((h.clock(), copy.deepcopy(h.venue.positions)))

    def order(self: FakeExchange, *args: Any, **kwargs: Any) -> Any:
        try:
            return real_order(self, *args, **kwargs)
        finally:
            snap()

    def info(payload: dict) -> Any:
        h.venue.land_due()
        snap()
        if payload["type"] != "clearinghouseState" or payload.get("user") != SUB:
            return real_info(payload)
        reads["n"] += 1
        if reads["n"] - 1 in fresh:
            return real_info(payload)
        when = h.clock() - timedelta(seconds=lag_s)
        base = [s for s in snaps if s[0] <= when] or snaps[:1]
        live = h.venue.positions
        h.venue.positions = copy.deepcopy(base[-1][1])
        try:
            return real_info(payload)
        finally:
            h.venue.positions = live

    monkeypatch.setattr(FakeExchange, "order", order)
    monkeypatch.setattr(h.venue, "info", info)


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
@pytest.mark.parametrize("lag_s", [51.5, 53.0, 55.25])
def test_a_doubled_entry_behind_one_lagging_position_node_is_covered_and_critical(
    h: Harness, monkeypatch: pytest.MonkeyPatch, lag_s: float, taker_bps: float
) -> None:
    """d1protect round 1 (live safety P7, trace lag 53): one node about 50 s
    behind answers every position read of the run. Attempt 1's reply is
    lost and its orderStatus lags (never_landed); the re-read is flat, the
    retry fills and is acked, and the read at open shows the first fill
    only (12). With a taker fill the entry-phase protect() re-anchors the
    stop and cancels the retry's child; P7 lists attempt 1's child. Each
    attempt proves its own fill (its ack, or its listed child): 24, so the
    stop covers 24 and the run is critical at once (the gap: exit 0, no
    critical, 24 held under one 12 stop)."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    _position_node_lagging(h, monkeypatch, lag_s)
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    code = h.run()
    entries = [c for c in h.actions("order", coin="AAA") if not c["reduce_only"]]
    assert len(entries) == 2 and h.venue.positions["AAA"]["szi"] == 24.0
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 12.0  # the read at open lagged the retry's fill
    assert code == 2
    assert criticals(h) == {"entry_overfill:AAA", "fill_not_visible:AAA"}
    stops = h.venue.stops("AAA")
    assert all(s["reduceOnly"] and s["side"] == "A" for s in stops)
    assert max(float(s["sz"]) for s in stops) == 24.0
    assert child_cloid("AAA", 1) in {s["cloid"] for s in stops}  # kept: proof
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 24.0


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
@pytest.mark.parametrize("order", ["partial_then_lost_full", "lost_full_then_partial"])
def test_each_entry_attempt_proves_its_fill_by_its_ack_or_its_child(
    h: Harness, monkeypatch: pytest.MonkeyPatch, order: str, taker_bps: float
) -> None:
    """d1protect round 1 (verifier probes test_mixed_proof_next_run): one
    attempt's fill is proven only by its ack (a partial fill: no child), the
    other's only by its listed child (a full fill whose reply was lost and
    whose orderStatus lags: never_landed). Every read of the run lags the
    child's fill. The proof adds the attempts up, so the stop covers the
    whole position and the child is kept while the reads lag it (the gap:
    max(children, acks) matched the read, a stop was cancelled as a
    duplicate, exit 0 with 6 of 12, or 6 of 18, without a stop)."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"),))
    if order == "partial_then_lost_full":
        # IOC 1 fills 6 of 12 (acked, no child); the 6 remainder fully fills
        # (a 6 child rests) but its reply is lost.
        h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.5}, {"mode": "raise_after"}]
        lost, child, size, seen = 2, 6.0, 12.0, 6.0
        expected = {"fill_not_visible:AAA"}
    else:
        # IOC 1 fully fills (a 12 child rests), its reply is lost; the flat
        # re-read allows the retry, which fills 6 of 12 (acked, no child).
        h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill", "fraction": 0.5}]
        lost, child, size, seen = 1, 12.0, 18.0, 12.0
        expected = {"entry_overfill:AAA", "fill_not_visible:AAA"}
    _lagging_order_status(
        h, monkeypatch, core.cloid_for(CFG, SUB, tid("AAA"), "entry", lost)
    )
    script = (["hide"] if lost == 1 else []) + [seen] * 200
    reads = _scripted_position_reads(h, monkeypatch, "AAA", script)
    assert h.run() == 2 and criticals(h) == expected
    assert h.venue.positions["AAA"]["szi"] == size
    stops = h.venue.stops("AAA")
    assert all(s["reduceOnly"] and s["side"] == "A" for s in stops)
    assert max(float(s["sz"]) for s in stops) == size  # one stop covers it all
    (kept,) = [s for s in stops if s["cloid"] == child_cloid("AAA", lost)]
    assert float(kept["sz"]) == child
    reads["truth"] = True
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == size


@pytest.mark.parametrize("p7_first_read", ["lags", "shows_24"])
def test_a_doubled_entry_whose_final_reads_show_the_coin_flat_is_critical(
    h: Harness, monkeypatch: pytest.MonkeyPatch, p7_first_read: str
) -> None:
    """d1protect round 1 (live safety sweep case 12-1-hide): the H1 doubled
    entry opens at the 12 the read at open shows, and the final reads hide
    the coin. The two stops together cover the 24 held, but no read showed
    more than 12: this session's proof (24) is more than any read of the
    trade showed, so the run is critical fill_not_visible (the gap: exit 0,
    no critical, a doubled position unreported until a later read showed
    it). Control (shows_24): P7's first read shows 24, which is raised as
    entry_overfill and stopped in full; the last read hiding the coin adds
    nothing (the flapping-read control is the lagging-fill test above)."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    p7_first = 24.0 if p7_first_read == "shows_24" else "hide"
    script = ["hide", 12.0, p7_first] + ["hide"] * 50
    reads = _scripted_position_reads(h, monkeypatch, "AAA", script)
    code = h.run()
    assert h.venue.positions["AAA"]["szi"] == 24.0
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 12.0
    stops = h.venue.stops("AAA")
    if p7_first_read == "lags":
        assert code == 2 and criticals(h) == {"fill_not_visible:AAA"}
        # d1protect round 3 (B1): the final reads show the coin flat, so the
        # sweep protects nothing; one stop for the proof covers all 24.
        assert max(float(s["sz"]) for s in stops) == 24.0
        assert child_cloid("AAA", 1) in {s["cloid"] for s in stops}
    else:
        assert code == 2 and criticals(h) == {"entry_overfill:AAA"}
        assert [float(s["sz"]) for s in stops] == [24.0]
    reads["truth"] = True
    code = h.at(T0 + HOUR).run()
    if p7_first_read == "lags":  # raised once, by the first read that shows it
        assert code == 2 and criticals(h) == {"entry_overfill:AAA"}
    else:
        assert code == 0 and not criticals(h)
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 24.0


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
def test_a_child_the_session_cancelled_still_proves_its_fill(
    h: Harness, monkeypatch: pytest.MonkeyPatch, taker_bps: float
) -> None:
    """d1protect round 1: the H1 doubled entry; P7's first read shows 24, so
    the sweep stops 24 and cancels both children (the read does not lag).
    P7's second read comes from a node between the two fills (12). The
    first attempt's child was listed (journaled open), so it still proves
    its 12 after the cancel: the 24 stop verifies against the proven 24
    (without it the proof is 12, the 24 stop fails I6 and P7 closes the
    position as unprotectable)."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    script = ["hide", 12.0, 24.0] + [12.0] * 50
    reads = _scripted_position_reads(h, monkeypatch, "AAA", script)
    assert h.run() == 2
    assert criticals(h) == {"entry_overfill:AAA", "fill_not_visible:AAA"}
    assert h.venue.positions["AAA"]["szi"] == 24.0 and not h.of("trade_closed")
    assert not [c for c in h.actions("order") if c["reduce_only"] and not c["trigger"]]
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 24.0
    cancelled = {c["cloid"] for c in h.actions("cancelByCloid")}
    assert child_cloid("AAA", 1) in cancelled
    reads["truth"] = True
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert h.venue.stops("AAA") == [stop]


def test_a_child_the_first_final_order_read_missed_is_stopped_in_the_run(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """d1protect round 1: the H1 doubled entry, and the first attempt's
    child is invisible to its orderStatus (a lagging node) and to P7's first
    order read. P7's second order read lists it: the proof rises to 24 after
    the sweep, and no single stop covers 24. P7 sweeps once more and stops
    the 24, keeping both children while the reads lag (without the listed
    child the run ended silent under two 12 stops; without the re-sweep the
    final check closed the whole position as unprotectable)."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    _lagging_order_status(
        h, monkeypatch, core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    )
    _lagging_order_status(h, monkeypatch, child_cloid("AAA", 1))
    reads = _scripted_position_reads(h, monkeypatch, "AAA", ["hide"] + [12.0] * 50)
    real_info = h.venue.info
    order_reads = {"n": 0}

    def info(payload: dict) -> Any:
        answer = real_info(payload)
        if payload["type"] == "frontendOpenOrders":
            order_reads["n"] += 1
            if order_reads["n"] <= 2:  # P1's read and P7's first read
                answer = [o for o in answer if o.get("cloid") != child_cloid("AAA", 1)]
        return answer

    monkeypatch.setattr(h.venue, "info", info)
    assert h.run() == 2
    assert criticals(h) == {"entry_overfill:AAA", "fill_not_visible:AAA"}
    assert h.venue.positions["AAA"]["szi"] == 24.0 and not h.of("trade_closed")
    assert not [c for c in h.actions("order") if c["reduce_only"] and not c["trigger"]]
    stops = sorted(float(s["sz"]) for s in h.venue.stops("AAA"))
    assert stops == [12.0, 12.0, 24.0]
    reads["truth"] = True
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 24.0


@pytest.mark.parametrize("fault", ["quiet_window", "read_fails_then_reads_lag"])
def test_an_acked_fill_whose_read_after_the_loop_fails_is_stopped_from_the_acks(
    h: Harness, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    """d1protect round 1 (fuzz A5): IOC 1 fills 6 of 12 (acked; a partial
    leaves no child), the remainder does not fill, and the read after the
    loop never happens: the clock reaches the quiet window (the run stops)
    or the read fails and every later read of the run lags the fill. The
    acks prove the 6 and its price, so the entry's failure path places the
    reduce-only stop from the acks (exempt from the quiet window) before the
    failure goes on (the gap: no stop until the next run's first read)."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.5}, {"mode": "no_fill"}]
    real_info = h.venue.info
    if fault == "read_fails_then_reads_lag":
        real_info = _hide_position(h, monkeypatch, "AAA", 100)
    original_read = executor.SleeveSession.refresh_positions
    state = {"fired": False}

    def read(self: executor.SleeveSession) -> None:
        if not state["fired"] and self.phase == "entry":
            state["fired"] = True
            if fault == "quiet_window":
                h.clock.now = h.clock.now.replace(minute=57, second=5)
            else:
                raise core.TechnicalError("hl info clearinghouseState transport error")
        original_read(self)

    monkeypatch.setattr(executor.SleeveSession, "refresh_positions", read)
    assert h.run() == 2 and state["fired"]
    assert "fill_not_visible:AAA" in criticals(h)
    end = h.of("run_end")[-1]
    if fault == "quiet_window":  # the failure went on: the run stopped there
        assert end["status"] == "deadline"
    else:
        assert "technical_failure:p6_entries" in criticals(h)
    assert h.venue.positions["AAA"]["szi"] == 6.0
    (stop,) = h.venue.stops("AAA")
    assert (stop["side"], float(stop["sz"]), float(stop["triggerPx"])) == (
        "A",
        6.0,
        96.0,
    )
    assert stop["reduceOnly"] and not h.of("trade_opened")
    monkeypatch.setattr(executor.SleeveSession, "refresh_positions", original_read)
    monkeypatch.setattr(h.venue, "info", real_info)
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and opened["sz"] == 6.0
    assert h.venue.stops("AAA") == [stop] and not h.actions("order")


def test_a_guard_rests_on_the_protective_side_of_the_mark(h: Harness) -> None:
    """A2: a position the sleeve does not own that is already past its
    rule-distance stop (entry 100, 15%: 85; the mark is 80) is guarded at the
    rule distance from the MARK (65), below it, so the stop rests instead of
    firing at once; never at or beyond the liquidation price."""
    h.venue.positions["DDD"] = {
        "szi": 2.0,
        "entryPx": 100.0,
        "type": "isolated",
        "value": 3,
        "liq": 50.0,
    }
    h.venue.mids["DDD"] = 80.0
    h.shadow()
    assert h.run() == 2
    (guard,) = h.venue.stops("DDD")
    assert float(guard["triggerPx"]) == 65.0 and guard["side"] == "A"


def test_a_guard_that_fires_on_an_owned_trade_reconciles_as_a_venue_stop(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A guard placed for an owned trade whose protection raised is that
    trade's stop at the venue: when it fires, the trade is closed venue_stop,
    not critical venue_flat_other."""
    open_day_one(h, "AAA")
    h.venue.orders.clear()
    original = executor.SleeveSession.check_leverage
    state = {"fired": False}

    def broken(self: executor.SleeveSession, *args: Any, **kwargs: Any) -> bool:
        if not state["fired"]:
            state["fired"] = True
            raise core.TechnicalError("hl info transport error")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(executor.SleeveSession, "check_leverage", broken)
    assert h.at(T0 + HOUR).run() == 2
    (guard,) = h.venue.stops("AAA")
    assert guard["cloid"] == core.cloid_for(CFG, SUB, "guard:AAA", "guard", 1)
    h.venue.trigger_stop("AAA")
    assert h.at(T0 + 2 * HOUR).run() == 0 and not criticals(h)
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "venue_stop"


@pytest.mark.parametrize("fills", ["partial_only", "partial_then_remainder"])
def test_acked_fills_no_read_shows_are_stopped_from_the_acks(
    h: Harness, monkeypatch: pytest.MonkeyPatch, fills: str
) -> None:
    """A1's fallback when no read shows the fill: a partial fill leaves no
    child (and a remainder's child covers only the remainder), and an info
    node lags every read of the run. The acks prove the fill and its price,
    so the sleeve places a reduce-only stop for the acked size at the rule
    distance from the acked average (before: nothing until a read showed
    it), keeps it while reads show the coin flat, and the first read that
    shows the position adopts the trade with that stop."""
    h.shadow(entries=(E("AAA"),))
    if fills == "partial_only":
        h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.5}, {"mode": "no_fill"}]
        acked = 6.0
    else:
        h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.3}, {"mode": "fill"}]
        acked = 12.0
    real_info = _hide_position(h, monkeypatch, "AAA", 100)
    assert h.run() == 2 and "fill_not_visible:AAA" in criticals(h)
    assert h.venue.positions["AAA"]["szi"] == acked
    covering = [s for s in h.venue.stops("AAA") if float(s["sz"]) == acked]
    (stop,) = covering
    assert float(stop["triggerPx"]) == 96.0 and stop["side"] == "A"
    assert not h.of("trade_opened")
    monkeypatch.setattr(h.venue, "info", real_info)
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and opened["sz"] == acked
    assert h.venue.stops("AAA") == [stop]  # the stop from the acks is kept
    assert not h.actions("order")


# ---------------------------------------------------------------- d1protect r2
def _position_reads_seen(h: Harness, monkeypatch: pytest.MonkeyPatch) -> list:
    """Records the AAA size each sub position read answered (outermost)."""
    real_info = h.venue.info
    seen: list[float] = []

    def info(payload: dict) -> Any:
        answer = real_info(payload)
        if payload["type"] == "clearinghouseState" and payload.get("user") == SUB:
            rows = [
                a for a in answer["assetPositions"] if a["position"]["coin"] == "AAA"
            ]
            seen.append(abs(float(rows[0]["position"]["szi"])) if rows else 0.0)
        return answer

    monkeypatch.setattr(h.venue, "info", info)
    return seen


@pytest.mark.parametrize(
    "case,lag_s",
    [
        ("lost_partial_then_partial", 52.0),
        ("lost_partial_then_partial", 54.0),
        ("partial_then_lost_partial", 54.0),
        ("partial_then_lost_partial", 58.0),
    ],
)
def test_a_stale_read_later_in_the_run_never_shrinks_a_stop_a_read_sized(
    h: Harness, monkeypatch: pytest.MonkeyPatch, case: str, lag_s: float
) -> None:
    """d1protect round 2 (verifier B1): one info node ``lag_s`` behind
    answers orderStatus of the lost attempt and every position read but
    one, which a current node answers and which shows the whole position,
    so the trade opens at it with a stop for all of it. A partial fill
    whose reply was lost leaves no child and no ack, so only that read
    proves it. P7's reads come from the lagging node and show less. The
    largest size a read of this session showed is part of the proof of
    fills, so the stop placed at open is kept and the run is critical
    fill_not_visible (the gap: a smaller stop placed, the full one
    cancelled, exit 0 with 6 of 12, or 3 of 9, unstopped)."""
    h.shadow(entries=(E("AAA"),))
    if case == "lost_partial_then_partial":
        # IOC 1 fills 6 of 12 (reply lost, orderStatus lags); the re-read is
        # flat; IOC 2 fills 6 of 12 (acked). Read 2, after the loop, is fresh.
        h.ioc["AAA"] = [
            {"mode": "raise_after", "fraction": 0.5},
            {"mode": "fill", "fraction": 0.5},
            {"mode": "no_fill"},
        ]
        lost, fresh, size, stale = 1, 2, 12.0, 6.0
    else:
        # IOC 1 fills 6 of 12 (acked); the 6 remainder fills 3 (reply lost,
        # orderStatus lags). Read 1 (the re-read after the loop) is fresh.
        h.ioc["AAA"] = [
            {"mode": "fill", "fraction": 0.5},
            {"mode": "raise_after", "fraction": 0.5},
        ]
        lost, fresh, size, stale = 2, 1, 9.0, 6.0
    true_info, true_order = h.venue.info, FakeExchange.order
    _position_node_lagging(h, monkeypatch, lag_s, frozenset({fresh}))
    _lagging_order_status(
        h, monkeypatch, core.cloid_for(CFG, SUB, tid("AAA"), "entry", lost)
    )
    seen = _position_reads_seen(h, monkeypatch)
    code = h.run()
    assert h.venue.positions["AAA"]["szi"] == size
    assert seen[fresh] == size and seen[-1] == stale  # P7's reads lag the fill
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == size
    assert code == 2 and criticals(h) == {"fill_not_visible:AAA"}
    (placed,) = h.of("stop_placed")  # the stop at open, never re-sized
    (stop,) = h.venue.stops("AAA")
    assert stop["cloid"] == placed["cloid"] and float(stop["sz"]) == size
    assert not h.actions("cancelByCloid") and not h.actions("cancel")
    monkeypatch.setattr(h.venue, "info", true_info)
    monkeypatch.setattr(FakeExchange, "order", true_order)
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert h.venue.stops("AAA") == [stop] and h.calls == []


def test_a_read_after_the_open_that_showed_more_is_kept_in_the_proof(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """d1protect round 2 (B1, a read after the open): IOC 1 fills 6 of 12
    (acked), the remainder fills 3 with a lost reply and a lagging
    orderStatus; the read at open shows 6 (the trade opens at 6), P7's
    first read shows 9 and the sweep re-sizes the stop to 9, P7's second
    read shows 6 again. The 9 a read showed stays proven: the 9 stop is
    kept and the run is critical fill_not_visible (without it the proof
    fell to the acked 6, the 9 stop failed I6 and P7 closed the trade as
    unprotectable)."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [
        {"mode": "fill", "fraction": 0.5},
        {"mode": "raise_after", "fraction": 0.5},
    ]
    _lagging_order_status(
        h, monkeypatch, core.cloid_for(CFG, SUB, tid("AAA"), "entry", 2)
    )
    reads = _scripted_position_reads(h, monkeypatch, "AAA", [6.0, 9.0] + [6.0] * 50)
    code = h.run()
    assert h.venue.positions["AAA"]["szi"] == 9.0
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 6.0
    assert code == 2 and criticals(h) == {"fill_not_visible:AAA"}
    assert not h.of("trade_closed")
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 9.0
    reads["truth"] = True
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert h.venue.stops("AAA") == [stop] and h.calls == []


def test_a_lost_entry_adopted_by_the_final_check_keeps_the_size_it_was_adopted_at(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """d1protect round 2 (B1, a trade recovered in P7): both attempts fill
    6 of 12 with lost replies and lagging orderStatus (never_landed), and
    the entry's reads are flat. P7's first read shows 12 and adopts the
    last attempt (position_reread): the trade is recovered at 12 with a 12
    stop. P7's second read shows 6 (a node between the fills). The 12 the
    adopting read showed stays proven, so the stop is kept (without it the
    proof was 6, the 12 stop failed I6 and P7 closed the trade); two
    attempts said never_landed, so the run is critical fill_not_visible."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [
        {"mode": "raise_after", "fraction": 0.5},
        {"mode": "raise_after", "fraction": 0.5},
    ]
    for n in (1, 2):
        _lagging_order_status(
            h, monkeypatch, core.cloid_for(CFG, SUB, tid("AAA"), "entry", n)
        )
    script = ["hide", "hide", 12.0] + [6.0] * 50
    reads = _scripted_position_reads(h, monkeypatch, "AAA", script)
    code = h.run()
    assert h.venue.positions["AAA"]["szi"] == 12.0
    (opened,) = h.of("trade_opened")
    assert opened["recovered"] is True and opened["sz"] == 12.0
    assert code == 2 and criticals(h) == {"fill_not_visible:AAA"}
    assert not h.of("trade_closed")
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0
    reads["truth"] = True
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert h.venue.stops("AAA") == [stop] and h.calls == []


def test_a_venue_stop_firing_in_the_run_on_an_older_trade_is_not_a_missing_fill(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The size-seen floor of the proof applies only to a trade with an
    entry attempt in this session: a trade opened in an earlier run at 6
    and read at 12 now (grown within its sized entry) has its stop re-sized
    to 12; P7's first read shows 12, the stop fires, and P7's second read
    shows the coin flat. No false fill_not_visible: nothing this session
    sent proves a fill, and a read is no proof for an older trade."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.5}, {"mode": "no_fill"}]
    assert h.run() == 0
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 6.0
    h.venue.positions["AAA"]["szi"] = 12.0
    original_sweep = executor.SleeveSession.sweep

    def stop_fires(self: executor.SleeveSession, *, first: bool = False) -> None:
        original_sweep(self, first=first)
        if not first and h.venue.stops("AAA"):
            h.venue.trigger_stop("AAA")  # after P7's first read and sweep

    monkeypatch.setattr(executor.SleeveSession, "sweep", stop_fires)
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert "AAA" not in h.venue.positions
    placed = h.of("stop_placed")
    assert [float(p["sz"]) for p in placed] == [6.0, 12.0]


def test_a_read_that_shows_the_other_side_is_never_proof_of_a_fill(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The size-seen floor counts only reads on the trade's own side: a
    long opened at 12, a P7 read showing the coin short 30 (the direction
    conflict is critical on its own), then long 12 again. The stop stays
    at 12 (a floor from the short's 30 would re-size it to 30 and raise a
    false fill_not_visible)."""
    h.shadow(entries=(E("AAA"),))
    reads = _scripted_position_reads(h, monkeypatch, "AAA", [12.0, -30.0] + [12.0] * 50)
    h.run()
    assert "fill_not_visible:AAA" not in criticals(h)
    placed = [float(p["sz"]) for p in h.of("stop_placed")]
    assert 30.0 not in placed
    assert [float(s["sz"]) for s in h.venue.stops("AAA") if s["side"] == "A"] == [12.0]
    reads["truth"] = True


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
def test_the_session_counts_only_uncancelled_acked_stops(
    h: Harness, monkeypatch: pytest.MonkeyPatch, taker_bps: float
) -> None:
    """acked_stops (the stops P7 may wait for a lagging listing to show)
    holds each stop this session saw acked resting and sent no cancel for:
    at a taker fill protect() places the fill-anchored stop and cancels
    the child, which then no longer counts; at the mid the child is the
    trade's stop and still counts."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"),))
    seen: dict[str, set[str]] = {}
    original_p7 = executor.SleeveSession.p7_final

    def capture(self: executor.SleeveSession) -> None:
        seen["acked"] = set(self.acked_stops)
        original_p7(self)

    monkeypatch.setattr(executor.SleeveSession, "p7_final", capture)
    assert h.run() == 0 and not criticals(h)
    (stop,) = h.venue.stops("AAA")
    assert seen["acked"] == {stop["cloid"]}
    if taker_bps:
        assert stop["cloid"] != child_cloid("AAA")
        assert child_cloid("AAA") in {c["cloid"] for c in h.actions("cancelByCloid")}
    else:
        assert stop["cloid"] == child_cloid("AAA")


@pytest.mark.parametrize("children", ["listed_first", "rejected"])
def test_two_never_landed_attempts_of_an_open_trade_are_critical(
    h: Harness, monkeypatch: pytest.MonkeyPatch, children: str
) -> None:
    """d1protect round 2 (live safety N1): both entry replies are lost and
    both orderStatus answers lag (never_landed); the re-read before the
    retry is flat and every later read shows 12, one fill of the 24 held.
    listed_first: the trade opens at 12 and only the first child is ever
    listed. rejected: the venue rejects both children, the entry's reads
    are flat and P7 adopts the last attempt at 12. The proof (12) matches
    the reads, so the run ended exit 0 with 24 held (covered only by the
    sum of its stops, or 12 unstopped). Two attempts said never_landed and
    the trade is open: one status was wrong, so the other proves nothing:
    critical fill_not_visible in the run. The first truthful read raises
    entry_overfill and stops the 24."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "raise_after"}]
    for n in (1, 2):
        _lagging_order_status(
            h, monkeypatch, core.cloid_for(CFG, SUB, tid("AAA"), "entry", n)
        )
    if children == "rejected":
        no_children(h, "AAA")
        script = ["hide", "hide"] + [12.0] * 50
    else:
        _lagging_order_status(h, monkeypatch, child_cloid("AAA", 2))
        script = ["hide"] + [12.0] * 50
    reads = _scripted_position_reads(h, monkeypatch, "AAA", script)
    real_info = h.venue.info

    def info(payload: dict) -> Any:
        answer = real_info(payload)
        if payload["type"] == "frontendOpenOrders" and not reads["truth"]:
            answer = [o for o in answer if o.get("cloid") != child_cloid("AAA", 2)]
        return answer

    monkeypatch.setattr(h.venue, "info", info)
    code = h.run()
    assert h.venue.positions["AAA"]["szi"] == 24.0
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 12.0
    assert code == 2 and criticals(h) == {"fill_not_visible:AAA"}
    reads["truth"] = True
    assert h.at(T0 + HOUR).run() == 2 and criticals(h) == {"entry_overfill:AAA"}
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 24.0


def _order_reads_missing(
    h: Harness, monkeypatch: pytest.MonkeyPatch, hide: dict[int, set[str]]
) -> None:
    """The n-th frontendOpenOrders read (1-based) omits these cloids."""
    real_info = h.venue.info
    state = {"n": 0}

    def info(payload: dict) -> Any:
        answer = real_info(payload)
        if payload["type"] == "frontendOpenOrders":
            state["n"] += 1
            drop = hide.get(state["n"], set())
            answer = [o for o in answer if o.get("cloid") not in drop]
        return answer

    monkeypatch.setattr(h.venue, "info", info)


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
@pytest.mark.parametrize("sized", ["doubled", "sized_entry"])
def test_growth_first_seen_by_the_second_final_read_is_stopped_not_closed(
    h: Harness, monkeypatch: pytest.MonkeyPatch, sized: str, taker_bps: float
) -> None:
    """d1protect round 2 (live safety N4): the position first reads larger
    in P7's SECOND read, after the sweep protected the smaller size, and
    the stop child that proves it is listed only by that second order read
    (so the proof equals the read). doubled: the H1 doubled entry (reads
    12, 12, then 24). sized_entry: 6 of 12 acked, the remainder fills with
    a lost reply (reads 6, 6, then 12). P7 sweeps once more and stops the
    whole position (the gap: the final check failed I6 and closed it at
    market as unprotectable). A doubled one is critical entry_overfill."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"),))
    if sized == "doubled":
        h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
        lost, size = 1, 24.0
        script = ["hide", 12.0, 12.0, 24.0] + [24.0] * 50
    else:
        h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.5}, {"mode": "raise_after"}]
        lost, size = 2, 12.0
        script = [6.0, 6.0, 12.0] + [12.0] * 50
    _lagging_order_status(
        h, monkeypatch, core.cloid_for(CFG, SUB, tid("AAA"), "entry", lost)
    )
    _lagging_order_status(h, monkeypatch, child_cloid("AAA", lost))
    _order_reads_missing(h, monkeypatch, {2: {child_cloid("AAA", lost)}})
    reads = _scripted_position_reads(h, monkeypatch, "AAA", script)
    code = h.run()
    assert h.venue.positions["AAA"]["szi"] == size and not h.of("trade_closed")
    assert not [c for c in h.actions("order") if c["reduce_only"] and not c["trigger"]]
    if sized == "doubled":
        assert code == 2 and criticals(h) == {"entry_overfill:AAA"}
    else:
        assert code == 0 and not criticals(h)
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == size
    reads["truth"] = True
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert h.venue.stops("AAA") == [stop] and h.calls == []


def _order_node_lagging(
    h: Harness, monkeypatch: pytest.MonkeyPatch, lag_s: float
) -> dict:
    """Every frontendOpenOrders read is answered by one info node ``lag_s``
    behind (the order list it held then); position reads and orderStatus
    are current. state['off'] makes the reads current again."""
    snaps: list[tuple[datetime, list]] = [(h.clock(), copy.deepcopy(h.venue.orders))]
    state = {"off": False}
    real_info = h.venue.info
    for name in ("order", "bulk_orders", "cancel", "cancel_by_cloid"):
        real_fn = getattr(FakeExchange, name)

        def wrapped(
            self: FakeExchange, *args: Any, _real: Any = real_fn, **kw: Any
        ) -> Any:
            try:
                return _real(self, *args, **kw)
            finally:
                snaps.append((h.clock(), copy.deepcopy(h.venue.orders)))

        monkeypatch.setattr(FakeExchange, name, wrapped)

    def info(payload: dict) -> Any:
        if payload["type"] != "frontendOpenOrders" or state["off"]:
            return real_info(payload)
        when = h.clock() - timedelta(seconds=lag_s)
        base = [s for s in snaps if s[0] <= when] or snaps[:1]
        live = h.venue.orders
        h.venue.orders = copy.deepcopy(base[-1][1])
        try:
            return real_info(payload)
        finally:
            h.venue.orders = live

    monkeypatch.setattr(h.venue, "info", info)
    return state


def _second_run_entry(h: Harness, taker_bps: float) -> None:
    """A second run of the day enters AAA (the first run's leverage update
    failed): the identity is reused, so P7 follows the entry within seconds."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"),))
    h.leverage_fail.add("AAA")
    assert h.run() == 0 and not h.venue.positions
    h.leverage_fail.discard("AAA")


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
@pytest.mark.parametrize("lag_s", [5.0, 10.0, 15.0])
def test_a_lagging_order_listing_never_closes_a_stop_this_run_saw_acked(
    h: Harness, monkeypatch: pytest.MonkeyPatch, lag_s: float, taker_bps: float
) -> None:
    """d1protect round 2 (live safety N5): no lost reply; the entry fills in
    full and its stop rests (acked), but the order listing comes from a node
    ``lag_s`` behind. P7 cannot list the stop placed seconds earlier and
    places another; its re-read a second later still lags. The stops this
    run saw acked resting would verify I6, so P7 re-reads the listing, 5 s
    apart, up to three more times before closing anything: the listing
    catches up and the position stays (the gap: closed at market as
    unprotectable, two inert stops left on the flat coin). The next run
    keeps one stop and cancels the duplicate."""
    _second_run_entry(h, taker_bps)
    state = _order_node_lagging(h, monkeypatch, lag_s)
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert h.venue.positions["AAA"]["szi"] == 12.0 and not h.of("trade_closed")
    assert not [c for c in h.actions("order") if c["reduce_only"] and not c["trigger"]]
    stops = h.venue.stops("AAA")
    assert len(stops) == 2 and all(float(s["sz"]) == 12.0 for s in stops)
    state["off"] = True
    assert h.at(T0 + 2 * HOUR).run() == 0 and not criticals(h)
    (stop,) = h.venue.stops("AAA")
    assert stop in stops and float(stop["sz"]) == 12.0


def test_a_listing_lag_past_the_reread_bound_still_closes_as_unprotectable(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The re-reads for a lagging listing are bounded (LISTING_REREAD_TRIES
    x LISTING_REREAD_BACKOFF_S after the first re-read): a listing 30 s
    behind is not waited out, and the position is closed at market as
    unprotectable (loud), as before."""
    _second_run_entry(h, 0.0)
    _order_node_lagging(h, monkeypatch, 30.0)
    assert h.at(T0 + HOUR).run() == 2 and criticals(h) == {"unprotectable:AAA"}
    assert "AAA" not in h.venue.positions
    waits = [
        b - a
        for (ca, a), (cb, b) in zip(
            zip(h.venue.calls, h.venue.call_times),
            zip(h.venue.calls[1:], h.venue.call_times[1:]),
        )
        if ca[1] == cb[1] == "frontendOpenOrders"
    ]
    backoff = timedelta(seconds=executor.LISTING_REREAD_BACKOFF_S)
    assert sum(w >= backoff for w in waits) == executor.LISTING_REREAD_TRIES


def test_the_listing_rereads_stop_at_the_sweep_reserve(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The extra listing re-reads never eat into the sweep reserve (the
    budget a close still needs): with the reserve reached, P7 closes after
    its one re-read, as before."""
    _second_run_entry(h, 0.0)
    _order_node_lagging(h, monkeypatch, 5.0)
    original_p7 = executor.SleeveSession.p7_final

    def reserve_reached(self: executor.SleeveSession) -> None:
        monkeypatch.setattr(self.pacer, "reserve_ok", lambda: False)
        original_p7(self)

    monkeypatch.setattr(executor.SleeveSession, "p7_final", reserve_reached)
    assert h.at(T0 + HOUR).run() == 2 and criticals(h) == {"unprotectable:AAA"}
    assert "AAA" not in h.venue.positions


def test_the_listing_rereads_stop_at_the_sweep_deadline(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The extra listing re-reads stop at the sweep deadline: P7 starts at
    56:48 and the listing never shows this run's stops, so the re-reads run
    into minute 57. No read goes out in the quiet window and the run does
    not fail on it; nothing may be sent then, so the position is left open,
    critical, and the next run's P3 verifies its stop."""
    _second_run_entry(h, 0.0)
    state = _order_node_lagging(h, monkeypatch, 3600.0)
    original_p7 = executor.SleeveSession.p7_final

    def late(self: executor.SleeveSession) -> None:
        h.clock.now = h.clock.now.replace(minute=56, second=48)
        original_p7(self)

    monkeypatch.setattr(executor.SleeveSession, "p7_final", late)
    assert h.at(T0 + HOUR).run() == 2
    assert _quiet_calls_after(h, T0 + HOUR) == []
    reads = [
        t
        for c, t in zip(h.venue.calls, h.venue.call_times)
        if c[1] == "frontendOpenOrders" and t > (T0 + HOUR).replace(minute=56)
    ]
    assert reads[-1] - reads[-2] >= timedelta(seconds=executor.LISTING_REREAD_BACKOFF_S)
    assert h.of("run_end")[-1]["status"] != "deadline"
    assert criticals(h) == {"unprotectable:AAA", "unprotected_position:AAA"}
    assert h.venue.positions["AAA"]["szi"] == 12.0 and not h.of("trade_closed")
    state["off"] = True
    monkeypatch.setattr(executor.SleeveSession, "p7_final", original_p7)
    assert h.at(T0 + 2 * HOUR).run() == 0 and not criticals(h)
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0


def _quiet_calls_after(h: Harness, start: datetime) -> list:
    quiet = start.replace(minute=57, second=0)
    return [
        c
        for c, t in zip(h.venue.calls, h.venue.call_times)
        if quiet <= t < quiet + HOUR
    ]


def test_an_older_stop_the_final_reads_stop_listing_is_not_waited_for(
    h: Harness,
) -> None:
    """The longer listing re-reads are only for a stop THIS run saw acked
    resting: a stop an earlier run placed that the final reads no longer
    list (gone, not lagging: a node behind still lists an hour-old stop) is
    closed after the one re-read, as before, with no extra reads."""
    open_day_one(h, "AAA")
    h.venue.order_reads = 0
    h.venue.lag_reads = {3, 4}  # P1, P7 refresh, then the final reads miss it
    h.calls.clear()
    assert h.at(T0 + HOUR).run() == 2 and criticals(h) == {"unprotectable:AAA"}
    assert h.venue.order_reads == 4


def test_a_child_its_order_status_shows_open_proves_its_fill_while_unlisted(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The H1 doubled entry, where no read shows more than 12 and the order
    listing never lists the first attempt's child (a listing node behind
    it), but P7's resolve of that child's orderStatus says it rests. A child
    journaled open proves its entry's full fill even while unlisted, so the
    proof is 24: a 24 stop and a critical run (without it the proof was the
    retry's 12 and the run ended exit 0 with 24 held under a 12 stop)."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "raise_after"}, {"mode": "fill"}]
    _lagging_order_status(
        h, monkeypatch, core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    )
    reads = _scripted_position_reads(h, monkeypatch, "AAA", ["hide"] + [12.0] * 50)
    real_info = h.venue.info

    def info(payload: dict) -> Any:
        answer = real_info(payload)
        if payload["type"] == "frontendOpenOrders" and not reads["truth"]:
            answer = [o for o in answer if o.get("cloid") != child_cloid("AAA", 1)]
        return answer

    monkeypatch.setattr(h.venue, "info", info)
    assert h.run() == 2
    assert criticals(h) == {"entry_overfill:AAA", "fill_not_visible:AAA"}
    assert h.venue.positions["AAA"]["szi"] == 24.0
    child = h.of("outcome", cloid=child_cloid("AAA", 1))[-1]
    assert child["status"] == "open"  # from its orderStatus, never listed
    assert max(float(s["sz"]) for s in h.venue.stops("AAA")) == 24.0
    reads["truth"] = True
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 24.0


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
def test_a_coin_the_first_final_read_hid_gets_no_duplicate_for_a_lagging_listing(
    h: Harness, monkeypatch: pytest.MonkeyPatch, taker_bps: float
) -> None:
    """A normal full fill whose stop rests (acked); P7's first position read
    hides the coin (a lagging node) and its second shows it, while the order
    listing lags the stop placed seconds earlier. The coin's size grew past
    what the first final sweep protected (nothing), but a stop this run saw
    acked resting covers it: no re-sweep and no duplicate stop; the listing
    re-reads verify it and the run is clean (the re-sweep would place a
    second, inert stop)."""
    _second_run_entry(h, taker_bps)
    state = _order_node_lagging(h, monkeypatch, 5.0)
    reads = _scripted_position_reads(
        h, monkeypatch, "AAA", [12.0, "hide"] + [12.0] * 50
    )
    placed_before = len(h.of("stop_placed"))
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert reads["n"] >= 3  # the hidden first final read, then the second
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0
    assert len(h.of("stop_placed")) - placed_before == (1 if taker_bps else 0)
    state["off"] = True
    reads["truth"] = True
    assert h.at(T0 + 2 * HOUR).run() == 0 and not criticals(h)
    assert h.venue.stops("AAA") == [stop]


# ---------------------------------------------------------------- round 3
def _position_nodes(
    h: Harness, monkeypatch: pytest.MonkeyPatch, plan: dict[int, object]
) -> None:
    """Physically consistent position reads from several info nodes: sub
    position read n (0-based) is answered by plan.get(n, 'fresh'): 'fresh'
    (the venue now), a number L (a node L seconds behind: the state it held
    then) or 'stalled' (a node frozen at the run's first read). Order reads
    and orderStatus are current."""
    snaps: list[tuple[datetime, dict]] = []
    real_info = h.venue.info
    real_order = FakeExchange.order
    reads = {"n": 0}

    def snap() -> None:
        snaps.append((h.clock(), copy.deepcopy(h.venue.positions)))

    def order(self: FakeExchange, *args: Any, **kwargs: Any) -> Any:
        try:
            return real_order(self, *args, **kwargs)
        finally:
            snap()

    def info(payload: dict) -> Any:
        h.venue.land_due()
        snap()
        if payload["type"] != "clearinghouseState" or payload.get("user") != SUB:
            return real_info(payload)
        node = plan.get(reads["n"], "fresh")
        reads["n"] += 1
        if node == "fresh":
            return real_info(payload)
        if node == "stalled":
            state = snaps[0][1]
        else:
            when = h.clock() - timedelta(seconds=float(node))  # type: ignore[arg-type]
            state = ([s for s in snaps if s[0] <= when] or snaps[:1])[-1][1]
        live = h.venue.positions
        h.venue.positions = copy.deepcopy(state)
        try:
            return real_info(payload)
        finally:
            h.venue.positions = live

    monkeypatch.setattr(FakeExchange, "order", order)
    monkeypatch.setattr(h.venue, "info", info)


def _ioc_sells(h: Harness, coin: str = "AAA") -> list[float]:
    return [
        c["sz"]
        for c in h.actions("order", coin=coin)
        if c["reduce_only"] and not c["trigger"]
    ]


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
@pytest.mark.parametrize("lag_s", [1.75, 3.0, 51.0])
def test_a_dust_read_below_the_acked_remainder_is_never_closed_as_dust(
    h: Harness, monkeypatch: pytest.MonkeyPatch, lag_s: float, taker_bps: float
) -> None:
    """d1protect round 3 (live safety D1-DUST a-c): attempt 1 fills 0.5% of
    the entry (dust), the remainder fills in full and is acked (its child
    acked resting), and every position read comes from one node ``lag_s``
    behind: the read at open shows the dust partial only. Dust is decided
    on the proof of fills (the acks: 12), not the read, so nothing is sold,
    one stop covers 12 and the acked child is kept while a read lags it
    (the gap: the dust close sold the whole entry at market, or sold part
    of it and cancelled the acked child, leaving 11.82 under a 0.06 stop).
    Critical only while the final reads still lag the acks."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.005}, {"mode": "fill"}]
    _position_node_lagging(h, monkeypatch, lag_s)
    code = h.run()
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 0.06
    assert h.venue.positions["AAA"]["szi"] == 12.0
    assert _ioc_sells(h) == [] and not h.of("trade_closed")
    stops = h.venue.stops("AAA")
    assert max(float(s["sz"]) for s in stops) == 12.0
    assert h.of("stop_placed")[0]["sz"] == 12.0  # at open: the acks, not the read
    if lag_s > 50:
        assert code == 2 and criticals(h) == {"fill_not_visible:AAA"}
        assert child_cloid("AAA", 2) in {s["cloid"] for s in stops}
    else:
        assert code == 0 and not criticals(h)


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
@pytest.mark.parametrize(
    "settle,lag_s",
    [
        ("never_landed", 51.0),
        ("never_landed", 52.5),
        ("never_landed", 53.5),
        ("ambiguous", 51.0),
    ],
)
def test_a_dust_read_while_the_remainder_is_unsettled_is_never_sold(
    h: Harness,
    monkeypatch: pytest.MonkeyPatch,
    settle: str,
    lag_s: float,
    taker_bps: float,
) -> None:
    """d1protect round 3 (live safety D1-DUST d, the d1verify2 class): the
    remainder's reply is lost and its orderStatus lags (never_landed), or
    its resolution would pass the deadline (still ambiguous), and every
    position read comes from one node about 51 s behind. The read at open
    shows the dust partial and nothing yet proves the remainder filled, but
    it may have: no dust close. The stop covers what the attempts could
    have filled (0.06 + 11.94) from the open on, so nothing is sold and the
    12 held is covered (the gap: the whole position sold at market)."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.005}, {"mode": "raise_after"}]
    _position_node_lagging(h, monkeypatch, lag_s)
    second = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 2)
    if settle == "never_landed":
        _lagging_order_status(h, monkeypatch, second)
    else:
        real_resolve = executor.SleeveSession.resolve

        def resolve(
            self: executor.SleeveSession, record: core.IntentRecord
        ) -> executor.SendResult:
            if record.cloid == second:  # as if its wait passed the deadline
                return executor.SendResult(record.cloid, "ambiguous")
            return real_resolve(self, record)

        monkeypatch.setattr(executor.SleeveSession, "resolve", resolve)
    code = h.run()
    (opened,) = h.of("trade_opened")
    assert opened["sz"] == 0.06
    assert h.venue.positions["AAA"]["szi"] == 12.0
    assert _ioc_sells(h) == [] and not h.of("trade_closed")
    assert h.of("stop_placed")[0]["sz"] == 12.0  # at open
    assert max(float(s["sz"]) for s in h.venue.stops("AAA")) == 12.0
    assert (code == 2) == bool(criticals(h))
    if settle == "ambiguous":
        assert "unresolved_entry:AAA" in criticals(h)


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
def test_a_dust_remainder_that_never_landed_is_stopped_not_sold(
    h: Harness, taker_bps: float
) -> None:
    """The remainder's POST truly never reached the venue: the sleeve cannot
    tell that from a lost reply behind a lagging orderStatus, so it does not
    close the dust. The stop covers 12 for the rest of the session (inert
    beyond the 0.06 held; no later read re-sizes it down) and the run is
    critical. The next run's read settles it: its stop covers the 0.06."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [{"mode": "fill", "fraction": 0.005}, {"mode": "raise_before"}]
    assert h.run() == 2 and criticals(h) == {"fill_not_visible:AAA"}
    assert h.venue.positions["AAA"]["szi"] == 0.06
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [12.0]
    assert _ioc_sells(h) == []
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [0.06]
    assert _ioc_sells(h) == [] and not h.of("trade_closed")


@pytest.mark.parametrize("dust_fill", [1.0, 0.5], ids=["sold", "half_sold"])
def test_a_dust_close_never_sells_more_than_the_dust_it_was_decided_on(
    h: Harness, monkeypatch: pytest.MonkeyPatch, dust_fill: float
) -> None:
    """Every attempt settled (a dust partial, then no fill): the dust close
    is right. After its first IOC (which sells all or half of the dust), a
    read shows more than is left of the dust (here an order the sleeve did
    not send): the ladder stops there instead of selling it, the run is
    critical, and the stop covers what that read shows."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [
        {"mode": "fill", "fraction": 0.005},
        {"mode": "no_fill"},
        {"mode": "fill", "fraction": dust_fill},  # the dust close's IOC
    ]
    real_order = FakeExchange.order

    def order(self: FakeExchange, name: str, *args: Any, **kwargs: Any) -> Any:
        out = real_order(self, name, *args, **kwargs)
        reduce_only = kwargs.get("reduce_only", args[4] if len(args) > 4 else False)
        if name == "AAA" and reduce_only and "trigger" not in args[3]:
            h.venue.apply_fill("AAA", True, 5.0, 100.0, h.venue.next_oid())
        return out

    monkeypatch.setattr(FakeExchange, "order", order)
    code = h.run()
    held = round(5.0 + 0.06 * (1 - dust_fill), 10)
    assert _ioc_sells(h) == [0.06]
    assert h.venue.positions["AAA"]["szi"] == held and not h.of("trade_closed")
    assert code == 2 and "exit_incomplete:AAA" in criticals(h)
    assert h.of("stop_placed")[0]["sz"] == held
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [held]


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
@pytest.mark.parametrize("far", [70.0, 150.0, "stalled"])
def test_a_fill_a_read_showed_is_stopped_when_the_final_reads_show_the_coin_flat(
    h: Harness, monkeypatch: pytest.MonkeyPatch, far: object, taker_bps: float
) -> None:
    """d1protect round 3 (verifier B1): attempt 1 fills 6 of 12, its reply
    lost (no child) and its orderStatus lagging; the re-read before the
    retry comes from a node far behind (flat), the retry fills 6 (acked, no
    child) and the read at open (a node 2 s behind) shows 6: the trade opens
    at 6 under a 6 stop. BBB's entry read is current and shows 12; both
    final reads come from the far node and show AAA flat, so the sweep
    protects nothing. The proof (the 12 a read showed) gets one stop at the
    final check (the gap: 12 held under the 6 stop, loud). The next run
    keeps one stop for 12."""
    h.taker_bps = taker_bps
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["AAA"] = [
        {"mode": "raise_after", "fraction": 0.5},
        {"mode": "fill", "fraction": 0.5},
    ]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    # reads: 0 P1, 1 the re-read before the retry, 2 at open, 3 BBB's, 4+ P7
    _position_nodes(
        h, monkeypatch, {1: far, 2: 2.0, 3: "fresh", **dict.fromkeys(range(4, 20), far)}
    )
    assert h.run() == 2 and "fill_not_visible:AAA" in criticals(h)
    (opened,) = [e for e in h.of("trade_opened") if e["coin"] == "AAA"]
    assert opened["sz"] == 6.0
    assert h.venue.positions["AAA"]["szi"] == 12.0
    sizes = sorted(float(s["sz"]) for s in h.venue.stops("AAA"))
    assert sizes == [6.0, 12.0]
    monkeypatch.undo()
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert [float(s["sz"]) for s in h.venue.stops("AAA")] == [12.0]


@pytest.mark.parametrize("taker_bps", [0.0, 3.0], ids=["at_mid", "taker"])
@pytest.mark.parametrize("reread_lag", [52.0, 55.0])
def test_a_reversal_whose_final_reads_show_the_closed_side_stops_the_proof(
    h: Harness, monkeypatch: pytest.MonkeyPatch, reread_lag: float, taker_bps: float
) -> None:
    """d1protect round 3 (verifier B2, the reversal twin of B1): P5 closes
    the AAA long and P6 enters AAA short; attempt 1 fills 6 of 12 with its
    reply lost and its orderStatus lagging, the re-read before the retry
    (a node behind the close) shows flat, the retry fills 6, the read at
    open shows short 6. BBB's entry read shows short 12. Both final reads
    come from a node stalled before the close and show the closed LONG: a
    read of the other side shows nothing of the short, so it counts as flat.
    The proof (12) gets one buy stop and the run is critical (the gap:
    exit 0, no critical, short 12 under a single 6 buy stop)."""
    open_day_one(h, "AAA")
    next_day(
        h,
        holding=(E("AAA"),),
        exits=("AAA",),
        entries=(E("AAA", side="short"), E("BBB")),
    )
    h.venue.mids["AAA"] = 98.0
    h.taker_bps = taker_bps
    h.ioc["AAA"] = [
        {"mode": "fill"},  # the exit ladder closes the long
        {"mode": "raise_after", "fraction": 0.5},
        {"mode": "fill", "fraction": 0.5},
    ]
    first = core.cloid_for(CFG, SUB, tid("AAA", "short", T + DAY), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    # reads: 0 P1, 1-2 P5, 3 the re-read before the retry, 4 at open, 5 BBB's
    _position_nodes(
        h,
        monkeypatch,
        {3: reread_lag, 4: 2.0, 5: "fresh", **dict.fromkeys(range(6, 20), "stalled")},
    )
    code = h.run()
    assert h.venue.positions["AAA"]["szi"] == -12.0
    assert code == 2 and "fill_not_visible:AAA" in criticals(h)
    buys = sorted(float(s["sz"]) for s in h.venue.stops("AAA") if s["side"] == "B")
    assert buys == [6.0, 12.0]


def test_a_trade_the_final_reads_hide_gets_no_stop_its_acked_stop_covers(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flat-read stop is for fills no stop covers: a full fill whose
    child rests (acked), both final reads hiding the coin and the order
    listing lagging the child. The acked child covers the proof: no stop
    is placed, nothing is raised (the listing need not show it)."""
    _second_run_entry(h, 0.0)
    _order_node_lagging(h, monkeypatch, 30.0)
    _scripted_position_reads(h, monkeypatch, "AAA", [12.0] + ["hide"] * 50)
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    (stop,) = h.venue.stops("AAA")
    assert float(stop["sz"]) == 12.0 and not h.of("stop_placed")
    assert [i["role"] for i in h.of("intent", action="order")][-2:] == ["entry", "stop"]


@pytest.mark.parametrize("second", ["reject", "rest"])
def test_a_flat_read_stop_that_cannot_rest_is_critical(
    h: Harness, monkeypatch: pytest.MonkeyPatch, second: str
) -> None:
    """B1's stop for the proof is tried twice: rejected twice, stop_missing
    is raised (the next run places it first) with fill_not_visible; rejected
    once, the second try rests and covers it."""
    h.shadow(entries=(E("AAA"), E("BBB")))
    h.ioc["AAA"] = [
        {"mode": "raise_after", "fraction": 0.5},
        {"mode": "fill", "fraction": 0.5},
    ]
    h.trigger["AAA"] = ["rest", "reject", second]
    first = core.cloid_for(CFG, SUB, tid("AAA"), "entry", 1)
    _lagging_order_status(h, monkeypatch, first)
    _position_nodes(
        h,
        monkeypatch,
        {1: 70.0, 2: 2.0, 3: "fresh", **dict.fromkeys(range(4, 20), 70.0)},
    )
    assert h.run() == 2
    sizes = sorted(float(s["sz"]) for s in h.venue.stops("AAA"))
    if second == "reject":
        assert {"stop_missing:AAA", "fill_not_visible:AAA"} <= criticals(h)
        assert sizes == [6.0]
    else:
        assert criticals(h) == {"fill_not_visible:AAA"}
        assert sizes == [6.0, 12.0]


def test_an_earlier_session_s_settled_attempt_never_blocks_a_dust_close(
    h: Harness,
) -> None:
    """Only THIS session's unsettled attempts keep a dust read open: run 1's
    attempt never landed (marked unverified at its end, settled flat by run
    2's first read), run 1's retry did not fill, and run 2's last attempt
    fills a dust partial. Every attempt of run 2 is settled, so its dust is
    closed (the proof is the read)."""
    h.shadow(entries=(E("AAA"),))
    h.ioc["AAA"] = [
        {"mode": "raise_before"},
        {"mode": "no_fill"},
        {"mode": "fill", "fraction": 0.005},
    ]
    assert h.run() == 2 and "unresolved_entry:AAA" in criticals(h)
    assert not h.venue.positions and not h.of("trade_opened")
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    (closed,) = h.of("trade_closed")
    assert closed["reason"] == "dust_fill" and "AAA" not in h.venue.positions
    assert _ioc_sells(h) == [0.06]


def test_an_older_trade_the_final_reads_show_flat_gets_no_stop(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stop for a proof the final reads miss is only for a trade with an
    entry attempt in this session: an older trade whose venue stop fires
    during the run (after P7's first sweep) and whose last read shows it
    flat gets no new order, and nothing is raised."""
    open_day_one(h, "AAA")
    original_sweep = executor.SleeveSession.sweep

    def stop_fires(self: executor.SleeveSession, *, first: bool = False) -> None:
        original_sweep(self, first=first)
        if not first and h.venue.stops("AAA"):
            h.venue.trigger_stop("AAA")

    monkeypatch.setattr(executor.SleeveSession, "sweep", stop_fires)
    orders = len(h.of("intent", action="order"))
    assert h.at(T0 + HOUR).run() == 0 and not criticals(h)
    assert "AAA" not in h.venue.positions
    assert len(h.of("intent", action="order")) == orders


@pytest.mark.parametrize(
    "coin,szd,mid,d,dist,sz",
    [
        ("BTC", 5, 96123.0, -1, 2400.0, 0.012),
        ("SOL", 2, 187.123, -1, 9.87, 3.21),
        ("kPEPE", 0, 0.012345, 1, 0.00061, 10000.0),
        ("HYPE", 2, 41.2345, -1, 2.345, 12.34),
    ],
)
def test_the_normal_tpsl_wire_on_the_real_sdk_for_both_sides(
    coin: str, szd: int, mid: float, d: int, dist: float, sz: float
) -> None:
    """d1protect round 3 (live safety, adopted from its wire probe): the
    entry and its child on the real SDK's signed POST, for shorts and for
    coarse and whole-unit size decimals. One normalTpsl action with no
    builder: the parent an IOC on the entry side, not reduce-only; the
    child a reduce-only stop-market (sl) on the closing side, its size the
    parent's, its limit its trigger, on the protective side of the limit.
    Nothing leaves the process (a local capture transport)."""
    sdk = executor._load_sdk()
    account = Account.create()
    captured: list[requests.PreparedRequest] = []

    class Capture(BaseAdapter):
        def send(self, request: requests.PreparedRequest, **kwargs: Any) -> Any:
            captured.append(request)
            response = requests.Response()
            response.status_code = 200
            filled = {"filled": {"totalSz": str(sz), "avgPx": str(mid), "oid": 7}}
            body = {
                "status": "ok",
                "response": {
                    "type": "order",
                    "data": {"statuses": [filled, "waitingForTrigger"]},
                },
            }
            response._content = json.dumps(body).encode()
            response.url = request.url
            return response

        def close(self) -> None:
            pass

    meta = {"universe": [{"name": coin, "szDecimals": szd, "maxLeverage": 20}]}
    exchange = executor.build_exchange(
        sdk, key=account.key.hex(), meta=meta, sub=SUB, cfg=CFG, transport=Capture()
    )
    clock = FakeClock(T0)
    gateway = executor.SubAccountGateway(
        exchange,
        cfg=CFG,
        env=executor.SleeveEnv(master=MASTER, sub=SUB, agent=account.address.lower()),
        markets=core.parse_meta(meta),
        pacer=executor.HlPacer(CFG, clock=clock, sleep=clock.sleep),
        clock=clock,
        cloid_cls=sdk.Cloid,
    )
    gateway.allow_new_risk = True
    entry = core.cloid_for(CFG, SUB, tid(coin), "entry", 1)
    child = core.cloid_for(CFG, SUB, tid(coin), "stop", 1)
    limit_px = core.ioc_limit(mid, d > 0, CFG.entry_slippage_bps, szd)
    stop_px = core.normalize_price(mid - d * dist, szd)
    expires = _ms(T0) + 45_000
    gateway.set_expires_after(expires)
    response = gateway.order_with_stop(
        coin, d > 0, round(sz, szd), limit_px, entry, stop_px, child
    )
    parent_ack, child_ack = core.parse_grouped_statuses(response)
    assert parent_ack.status == "filled" and child_ack.status == "waiting"
    (request,) = captured
    body = json.loads(request.body)
    assert body["vaultAddress"] == SUB and body["expiresAfter"] == expires
    action = body["action"]
    assert action["type"] == "order" and action["grouping"] == "normalTpsl"
    assert "builder" not in action
    parent, stop = action["orders"]
    assert parent["b"] is (d > 0) and parent["r"] is False and parent["c"] == entry
    assert parent["t"] == {"limit": {"tif": "Ioc"}}
    assert float(parent["p"]) == limit_px
    assert stop["b"] is (d < 0) and stop["r"] is True and stop["c"] == child
    assert stop["t"]["trigger"]["isMarket"] is True
    assert stop["t"]["trigger"]["tpsl"] == "sl"
    assert float(stop["t"]["trigger"]["triggerPx"]) == stop_px == float(stop["p"])
    assert stop["s"] == parent["s"] and parent["a"] == stop["a"] == 0
    assert (limit_px - stop_px) * d > 0
