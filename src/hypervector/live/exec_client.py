"""Live execution client: protocol + Hyperliquid mainnet place adapter (F2).

Fail-closed: construct only after ``LivePolicy.require_start()``. Paper/shadow
must never import or construct this client. Offline tests inject a mock
transport; production uses the official Hyperliquid SDK transport below.

Order honesty contract:

* opening orders are checked against the hard notional cap before any call;
* closes are sent reduce-only (never capped, never able to open exposure) and
  are refused on a transport that cannot express reduce-only;
* a result is ``submitted`` only when the venue acknowledged the order, and it
  carries the venue-reported filled size and average price when available;
* the kill switch cancels only resting orders this client placed, so it never
  strips another strategy's protective orders on the same account.
"""

from __future__ import annotations

import inspect
import math
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any, Protocol, runtime_checkable

from hypervector.data.hl import HL_INFO_URL, hl_coin
from hypervector.live.capabilities import is_submit_wired as is_submit_wired
from hypervector.live.policy import (
    LivePolicy,
    LivePolicyError,
    SECRET_ENV_API_KEY,
    SECRET_ENV_WALLET,
    require_notional_cap,
)

# Mainnet exchange endpoint only (no testnet path).
HL_EXCHANGE_URL = "https://api.hyperliquid.xyz/exchange"
NETWORK_MAINNET = "mainnet"

# Aggressive IOC limit distance from the live mid (the official SDK default).
DEFAULT_MARKET_SLIPPAGE = 0.05
_MAX_MARKET_SLIPPAGE = 0.05
# Hyperliquid perp wire precision: 5 significant figures and at most
# ``6 - szDecimals`` price decimals (the SDK's ``_slippage_price`` rule).
_PERP_MAX_DECIMALS = 6
_PRICE_SIGNIFICANT_FIGURES = 5
_IOC_ORDER_TYPE = {"limit": {"tif": "Ioc"}}

# Re-export for structural barriers / readiness surface.
__all__ = [
    "DEFAULT_MARKET_SLIPPAGE",
    "HL_EXCHANGE_URL",
    "HL_INFO_URL",
    "HyperliquidLiveExecClient",
    "LiveExecClient",
    "LiveVenueError",
    "PlaceResult",
    "PlaceTransport",
    "create_live_exec_client",
    "create_live_exec_client_from_env",
    "is_submit_wired",
]


class LiveVenueError(RuntimeError):
    """A venue read or order could not be performed correctly (technical failure)."""


@dataclass(frozen=True)
class PlaceResult:
    """Outcome of a venue place or cancel attempt.

    ``filled_qty``/``avg_px`` are the venue-reported fill when the response
    carries one (``0.0`` for an order left resting); ``None`` means the
    transport did not report fill details.
    """

    submitted: bool
    venue_order_id: str | None
    error: str | None
    filled_qty: float | None = None
    avg_px: float | None = None
    detail: str | None = None


@runtime_checkable
class PlaceTransport(Protocol):
    """Low-level venue place/cancel/read (injectable for offline tests)."""

    def place_market(
        self,
        *,
        coin: str,
        is_buy: bool,
        sz: float,
        wallet_address: str,
        private_key: str,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """Send one IOC market-style order; return the venue response dict."""
        ...

    def cancel_all(
        self,
        *,
        wallet_address: str,
        private_key: str,
        coin: str | None = None,
        oids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Cancel exactly the listed still-open orders; return the venue response."""
        ...

    def position(self, *, wallet_address: str, private_key: str, coin: str) -> float:
        """Return the venue's signed position size for ``coin`` (0.0 when flat)."""
        ...


@runtime_checkable
class LiveExecClient(Protocol):
    """Public place + kill + reconciliation surface for armed live execution."""

    def place_market(
        self,
        symbol: str,
        side: str,
        qty: float,
        *,
        mark_px: float | None = None,
        client_order_id: str | None = None,
        reduce_only: bool = False,
    ) -> PlaceResult: ...

    def cancel_all(self, *, symbol: str | None = None) -> PlaceResult: ...

    def venue_position(self, symbol: str) -> float: ...


def _parse_oid(response: Mapping[str, Any]) -> str | None:
    if not isinstance(response, Mapping):
        return None
    for key in ("oid", "order_id", "venue_order_id", "id"):
        val = response.get(key)
        if val is not None and val != "":
            return str(val)
    # Nested HL-style response.statuses[0].resting.oid etc.
    first = _first_status(response)
    if first is not None:
        for nest in ("resting", "filled"):
            node = first.get(nest)
            if isinstance(node, Mapping) and node.get("oid") is not None:
                return str(node["oid"])
        if first.get("oid") is not None:
            return str(first["oid"])
    return None


def _status_list(response: Mapping[str, Any]) -> list[Any] | None:
    statuses = response.get("response") or response.get("statuses")
    if not isinstance(statuses, Mapping):
        return None
    data = statuses.get("data") if isinstance(statuses.get("data"), Mapping) else statuses
    st_list = data.get("statuses") if isinstance(data, Mapping) else None
    return st_list if isinstance(st_list, list) else None


def _first_status(response: Mapping[str, Any]) -> Mapping[str, Any] | None:
    st_list = _status_list(response)
    if st_list and isinstance(st_list[0], Mapping):
        return st_list[0]
    return None


def _check_venue_error(response: Mapping[str, Any]) -> str | None:
    if not isinstance(response, Mapping):
        return None
    if response.get("status") in ("err", "error") or "error" in response:
        return str(response.get("error") or response.get("response") or response)
    first = _first_status(response)
    if first is not None and "error" in first:
        return str(first["error"])
    return None


def _optional_float(value: Any, *, positive: bool) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0.0 or (positive and number == 0.0):
        return None
    return number


def _parse_fill(response: Mapping[str, Any]) -> tuple[float | None, float | None, bool]:
    """Return ``(filled_qty, avg_px, resting)`` from an HL order acknowledgement."""
    first = _first_status(response)
    if first is None:
        return None, None, False
    filled = first.get("filled")
    if isinstance(filled, Mapping):
        return (
            _optional_float(filled.get("totalSz"), positive=False),
            _optional_float(filled.get("avgPx"), positive=True),
            False,
        )
    if isinstance(first.get("resting"), Mapping):
        return 0.0, None, True
    return None, None, False


def _cancel_error(response: Any) -> str | None:
    """Return why a cancel response is not a verified success, or None."""
    if not isinstance(response, Mapping):
        return f"cancel returned a non-object response ({type(response).__name__})"
    note = response.get("note")
    if note:
        return f"transport reported a no-op cancel: {note}"
    top = _check_venue_error(response)
    if top is not None:
        return top
    if response.get("status") not in (None, "ok"):
        return f"cancel status {response.get('status')!r}"
    errors = [
        str(item["error"])
        for item in _status_list(response) or []
        if isinstance(item, Mapping) and "error" in item
    ]
    return "; ".join(errors) if errors else None


def _normalize_side(side: str) -> bool:
    s = str(side).strip().lower()
    if s in ("buy", "long", "b"):
        return True
    if s in ("sell", "short", "s"):
        return False
    raise ValueError(f"unsupported side: {side!r}")


def _accepts_keyword(fn: Any, name: str) -> bool:
    """Whether callable ``fn`` accepts keyword ``name`` (directly or via **kwargs)."""
    try:
        parameters = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    for parameter in parameters:
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return True
        if parameter.name == name and parameter.kind in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            return True
    return False


def _oid_int(value: Any) -> int | None:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


class HyperliquidLiveExecClient:
    """Mainnet-only Hyperliquid place adapter.

    Does not place on construct. Enforces the notional cap on opening orders
    before calling the injected transport.
    """

    network: str = NETWORK_MAINNET

    def __init__(
        self,
        *,
        wallet_address: str,
        private_key: str,
        transport: PlaceTransport,
        max_notional_usd: float,
    ) -> None:
        wallet = (wallet_address or "").strip()
        key = (private_key or "").strip()
        if not wallet or not key:
            raise LivePolicyError(
                "live secrets missing — set "
                f"{SECRET_ENV_WALLET} and {SECRET_ENV_API_KEY}"
            )
        self._wallet = wallet
        self._private_key = key
        self._transport = transport
        self._max_notional_usd = require_notional_cap(max_notional_usd)
        # Resting orders this client placed, by coin (IOC orders never rest).
        self._owned_resting: dict[str, set[int]] = {}

    def place_market(
        self,
        symbol: str,
        side: str,
        qty: float,
        *,
        mark_px: float | None = None,
        client_order_id: str | None = None,
        reduce_only: bool = False,
    ) -> PlaceResult:
        del client_order_id  # reserved for F3 daemon intent stamping
        try:
            is_buy = _normalize_side(side)
            q = float(qty)
            if not math.isfinite(q) or q <= 0:
                return _refused(f"qty must be a finite positive number, got {qty!r}")
            if mark_px is None:
                return _refused("mark_px required for notional cap check")
            mark = float(mark_px)
            if not math.isfinite(mark) or mark <= 0:
                return _refused(f"mark_px must be a finite positive number, got {mark_px!r}")
            if not reduce_only:
                # Cap check without constructing a full LivePolicy (gates passed).
                notional = q * mark
                cap = self._max_notional_usd
                if notional > cap + 1e-12:
                    return _refused(
                        f"notional {notional:.6f} exceeds max_notional_usd {cap:.6f}"
                    )
            coin = hl_coin(symbol)
            place = self._transport.place_market
            kwargs: dict[str, Any] = {
                "coin": coin,
                "is_buy": is_buy,
                "sz": q,
                "wallet_address": self._wallet,
                "private_key": self._private_key,
            }
            if _accepts_keyword(place, "reduce_only"):
                kwargs["reduce_only"] = bool(reduce_only)
            elif reduce_only:
                return _refused(
                    "transport cannot send reduce-only orders; refusing a close "
                    "that could open exposure"
                )
            raw = place(**kwargs)
            if not isinstance(raw, Mapping):
                return _refused(
                    "transport returned a non-object response "
                    f"({type(raw).__name__}); order outcome unknown"
                )
            err_msg = _check_venue_error(raw)
            if err_msg:
                return _refused(err_msg)
            oid = _parse_oid(raw)
            filled_qty, avg_px, resting = _parse_fill(raw)
            if resting:
                owned = _oid_int(oid)
                if owned is not None:
                    self._owned_resting.setdefault(coin, set()).add(owned)
            return PlaceResult(
                submitted=True,
                venue_order_id=oid,
                error=None,
                filled_qty=filled_qty,
                avg_px=avg_px,
            )
        except Exception as exc:  # noqa: BLE001 — surface venue/transport failures
            return _refused(str(exc))

    def venue_position(self, symbol: str) -> float:
        """Return the venue's signed position for ``symbol``; raise if unreadable."""
        coin = hl_coin(symbol)
        reader = getattr(self._transport, "position", None)
        if not callable(reader):
            raise LiveVenueError(
                f"transport cannot read the venue position for {coin}; "
                "refusing to trade without venue reconciliation"
            )
        try:
            value = float(
                reader(
                    wallet_address=self._wallet,
                    private_key=self._private_key,
                    coin=coin,
                )
            )
        except LiveVenueError:
            raise
        except Exception as exc:  # noqa: BLE001 — every read failure is technical
            raise LiveVenueError(
                f"venue position read for {coin} failed: {exc}"
            ) from exc
        if not math.isfinite(value):
            raise LiveVenueError(f"venue position for {coin} is not finite: {value!r}")
        return value

    def cancel_all(self, *, symbol: str | None = None) -> PlaceResult:
        """Cancel every resting order this client placed (F4 kill switch).

        Market IOC orders never rest, so for the generic daemon this is normally
        a verified no-op. Orders this client did not place are never touched.
        """
        try:
            coin = hl_coin(symbol) if symbol else None
            targets = {
                name: set(oids)
                for name, oids in self._owned_resting.items()
                if oids and (coin is None or name == coin)
            }
            if not targets:
                return PlaceResult(
                    submitted=True,
                    venue_order_id=None,
                    error=None,
                    detail="no owned resting orders to cancel (market IOC orders never rest)",
                )
            cancel = getattr(self._transport, "cancel_all", None)
            if cancel is None or not _accepts_keyword(cancel, "oids"):
                listed = ", ".join(
                    f"{name}:{sorted(oids)}" for name, oids in sorted(targets.items())
                )
                return _refused(
                    "transport cannot cancel by order id; owned resting orders "
                    f"left open: {listed}"
                )
            errors: list[str] = []
            for name, oids in sorted(targets.items()):
                raw = cancel(
                    wallet_address=self._wallet,
                    private_key=self._private_key,
                    coin=name,
                    oids=sorted(oids),
                )
                failure = _cancel_error(raw)
                if failure is not None:
                    errors.append(f"{name}: {failure}")
                else:
                    self._owned_resting[name] -= oids
            if errors:
                return _refused("; ".join(errors))
            done = ", ".join(f"{n}:{sorted(o)}" for n, o in sorted(targets.items()))
            return PlaceResult(
                submitted=True,
                venue_order_id=None,
                error=None,
                detail=f"cancelled owned resting orders {done}",
            )
        except Exception as exc:  # noqa: BLE001 — best-effort kill path
            return _refused(str(exc))


def _refused(error: str) -> PlaceResult:
    return PlaceResult(submitted=False, venue_order_id=None, error=error)


class SdkClientBuilder(Protocol):
    """Builds paired official-SDK ``Info``/``Exchange`` clients for one account."""

    def build(
        self,
        *,
        account_address: str,
        private_key: str,
        perp_dexes: tuple[str, ...] = (),
    ) -> tuple[Any, Any]:
        """Return ``(info, exchange)`` bound to mainnet and the given perp dexes."""
        ...


def _official_sdk_builder() -> SdkClientBuilder:
    """Mainnet-only builder shared with cohort live (API-agent parent check)."""
    from hypervector.live.hyperliquid_sdk_factory import OfficialHyperliquidSdkBuilder

    return OfficialHyperliquidSdkBuilder()


@dataclass
class _SdkSession:
    info: Any
    exchange: Any
    account_address: str
    perp_dex: str
    size_decimals: dict[str, int] = field(default_factory=dict)


def _perp_dex(coin: str) -> str:
    return coin.split(":", 1)[0] if ":" in coin else ""


def _validated_account(wallet_address: str) -> str:
    address = (wallet_address or "").strip()
    if len(address) != 42 or not address.startswith("0x"):
        raise LiveVenueError("wallet address must be a 42-character 0x address")
    return address


def _market_size_decimals(meta: Any, coin: str) -> int:
    universe = meta.get("universe") if isinstance(meta, Mapping) else None
    if not isinstance(universe, list):
        raise LiveVenueError(f"venue metadata for {coin} has no market universe")
    matches = [m for m in universe if isinstance(m, Mapping) and m.get("name") == coin]
    if len(matches) != 1:
        raise LiveVenueError(f"venue metadata must contain exactly one {coin} market")
    market = matches[0]
    if market.get("isDelisted") is True:
        raise LiveVenueError(f"{coin} is delisted on the venue")
    decimals = market.get("szDecimals")
    if isinstance(decimals, bool) or not isinstance(decimals, int):
        raise LiveVenueError(f"{coin} szDecimals is not an integer: {decimals!r}")
    if not 0 <= decimals <= _PERP_MAX_DECIMALS:
        raise LiveVenueError(f"{coin} szDecimals {decimals} outside perp precision")
    return decimals


def _round_size_down(size: float, decimals: int, coin: str) -> float:
    quantum = Decimal(1).scaleb(-decimals)
    try:
        rounded = Decimal(repr(float(size))).quantize(quantum, rounding=ROUND_DOWN)
    except (InvalidOperation, ValueError) as exc:
        raise LiveVenueError(f"{coin} order size {size!r} cannot be rounded") from exc
    if rounded <= 0:
        raise LiveVenueError(
            f"{coin} order size {size!r} rounds to zero at venue precision "
            f"({decimals} size decimals)"
        )
    return float(rounded)


def _wire_price(price: float, decimals: int, coin: str) -> float:
    if not math.isfinite(price) or price <= 0:
        raise LiveVenueError(f"{coin} limit price {price!r} is not positive")
    significant = float(f"{price:.{_PRICE_SIGNIFICANT_FIGURES}g}")
    rounded = round(significant, _PERP_MAX_DECIMALS - decimals)
    if rounded <= 0:
        raise LiveVenueError(f"{coin} limit price {price!r} rounds to zero")
    return rounded


def _live_mid(mids: Any, coin: str) -> float:
    value = mids.get(coin) if isinstance(mids, Mapping) else None
    mid = _optional_float(value, positive=True)
    if mid is None:
        raise LiveVenueError(f"venue has no live mid for {coin}")
    return mid


def _signed_position(state: Any, coin: str) -> float:
    positions = state.get("assetPositions") if isinstance(state, Mapping) else None
    if not isinstance(positions, list):
        raise LiveVenueError("clearinghouse state has no asset positions")
    sizes: list[float] = []
    for wrapper in positions:
        position = wrapper.get("position") if isinstance(wrapper, Mapping) else None
        if isinstance(position, Mapping) and position.get("coin") == coin:
            try:
                size = float(position.get("szi"))  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise LiveVenueError(f"{coin} position size is not numeric") from exc
            if not math.isfinite(size):
                raise LiveVenueError(f"{coin} position size is not finite")
            sizes.append(size)
    if len(sizes) > 1:
        raise LiveVenueError(f"clearinghouse returned duplicate {coin} positions")
    return sizes[0] if sizes else 0.0


class _SdkPlaceTransport:
    """Production transport over the official ``hyperliquid-python-sdk``.

    One authenticated session per (account, perp dex) per process, built lazily
    on first use by the mainnet-only official builder (which also verifies the
    signing key is an API agent of the configured account). Orders are
    aggressive IOC limits ``slippage`` through the live mid, with the size
    rounded down to ``szDecimals`` and the price to the venue's 5-significant
    figure grid, so every order survives the SDK's wire encoding. HIP-3
    ``dex:ASSET`` coins bind their builder perp dex.
    """

    def __init__(
        self,
        *,
        sdk_builder: SdkClientBuilder | None = None,
        slippage: float = DEFAULT_MARKET_SLIPPAGE,
    ) -> None:
        slip = float(slippage)
        if not math.isfinite(slip) or not 0.0 < slip <= _MAX_MARKET_SLIPPAGE:
            raise ValueError(
                f"slippage must be in (0, {_MAX_MARKET_SLIPPAGE}], got {slippage!r}"
            )
        self._builder = sdk_builder
        self._slippage = slip
        self._sessions: dict[tuple[str, str], _SdkSession] = {}

    @property
    def session_count(self) -> int:
        """Number of authenticated SDK sessions built so far (0 until first use)."""
        return len(self._sessions)

    def place_market(
        self,
        *,
        coin: str,
        is_buy: bool,
        sz: float,
        wallet_address: str,
        private_key: str,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        session = self._session(wallet_address, private_key, coin)
        decimals = self._size_decimals(session, coin)
        size = _round_size_down(sz, decimals, coin)
        mid = _live_mid(session.info.all_mids(session.perp_dex), coin)
        reference = mid * (1.0 + self._slippage if is_buy else 1.0 - self._slippage)
        limit_px = _wire_price(reference, decimals, coin)
        raw = session.exchange.order(
            coin,
            bool(is_buy),
            size,
            limit_px,
            dict(_IOC_ORDER_TYPE),
            reduce_only=bool(reduce_only),
        )
        if not isinstance(raw, Mapping):
            raise LiveVenueError(
                f"SDK order returned {type(raw).__name__}; order outcome unknown"
            )
        result = dict(raw)
        result["request"] = {
            "coin": coin,
            "is_buy": bool(is_buy),
            "sz": size,
            "limit_px": limit_px,
            "tif": "Ioc",
            "reduce_only": bool(reduce_only),
        }
        return result

    def position(self, *, wallet_address: str, private_key: str, coin: str) -> float:
        session = self._session(wallet_address, private_key, coin)
        state = session.info.user_state(session.account_address, session.perp_dex)
        return _signed_position(state, coin)

    def cancel_all(
        self,
        *,
        wallet_address: str,
        private_key: str,
        coin: str | None = None,
        oids: Iterable[int] | None = None,
    ) -> dict[str, Any]:
        if coin is None or oids is None:
            raise LiveVenueError(
                "refusing to cancel orders this client does not own; an explicit "
                "coin and owned order ids are required"
            )
        wanted = {oid for oid in (_oid_int(value) for value in oids) if oid is not None}
        if not wanted:
            return {"status": "ok", "cancel_requested": []}
        session = self._session(wallet_address, private_key, coin)
        open_orders = session.info.open_orders(session.account_address, session.perp_dex)
        if not isinstance(open_orders, list):
            raise LiveVenueError("open orders response is not a list")
        targets = sorted(
            oid
            for order in open_orders
            if isinstance(order, Mapping) and order.get("coin") == coin
            for oid in [_oid_int(order.get("oid"))]
            if oid is not None and oid in wanted
        )
        if not targets:
            return {"status": "ok", "cancel_requested": [], "not_open": sorted(wanted)}
        raw = session.exchange.bulk_cancel([{"coin": coin, "oid": oid} for oid in targets])
        if not isinstance(raw, Mapping):
            raise LiveVenueError(
                f"SDK cancel returned {type(raw).__name__}; cancel outcome unknown"
            )
        result = dict(raw)
        result["cancel_requested"] = targets
        return result

    def _session(self, wallet_address: str, private_key: str, coin: str) -> _SdkSession:
        account = _validated_account(wallet_address)
        dex = _perp_dex(coin)
        key = (account.lower(), dex)
        session = self._sessions.get(key)
        if session is None:
            builder = self._builder if self._builder is not None else _official_sdk_builder()
            info, exchange = builder.build(
                account_address=account,
                private_key=private_key,
                perp_dexes=(dex,) if dex else (),
            )
            session = _SdkSession(
                info=info,
                exchange=exchange,
                account_address=account,
                perp_dex=dex,
            )
            self._sessions[key] = session
        return session

    @staticmethod
    def _size_decimals(session: _SdkSession, coin: str) -> int:
        cached = session.size_decimals.get(coin)
        if cached is None:
            cached = _market_size_decimals(session.info.meta(dex=session.perp_dex), coin)
            session.size_decimals[coin] = cached
        return cached


def create_live_exec_client(
    policy: LivePolicy,
    *,
    wallet_address: str,
    private_key: str,
    transport: PlaceTransport | None = None,
) -> HyperliquidLiveExecClient:
    """Construct client only after policy start gates pass."""
    policy.require_start()
    return HyperliquidLiveExecClient(
        wallet_address=wallet_address,
        private_key=private_key,
        transport=transport if transport is not None else _SdkPlaceTransport(),
        max_notional_usd=policy.max_notional_usd,
    )


def create_live_exec_client_from_env(
    policy: LivePolicy,
    *,
    transport: PlaceTransport | None = None,
    environ: dict[str, str] | None = None,
) -> HyperliquidLiveExecClient:
    """Read secrets from env (or injected mapping); never log values."""
    policy.require_start()
    env = environ if environ is not None else os.environ
    wallet = (env.get(SECRET_ENV_WALLET) or "").strip()
    key = (env.get(SECRET_ENV_API_KEY) or "").strip()
    if not wallet or not key:
        raise LivePolicyError(
            f"live secrets missing — set {SECRET_ENV_WALLET} and {SECRET_ENV_API_KEY}"
        )
    return create_live_exec_client(
        policy,
        wallet_address=wallet,
        private_key=key,
        transport=transport,
    )
