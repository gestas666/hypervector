"""Live execution client: protocol + Hyperliquid mainnet place adapter (F2).

Fail-closed: construct only after ``LivePolicy.require_start()``. Paper/shadow
must never import or construct this client. Offline tests inject a mock
transport; production uses an optional HL SDK/signing transport.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from hypervector.data.hl import HL_INFO_URL, hl_coin
from hypervector.live.policy import (
    LivePolicy,
    LivePolicyError,
    SECRET_ENV_API_KEY,
    SECRET_ENV_WALLET,
)

# Mainnet exchange endpoint only (no testnet path).
HL_EXCHANGE_URL = "https://api.hyperliquid.xyz/exchange"
NETWORK_MAINNET = "mainnet"

# Re-export for structural barriers / readiness surface.
__all__ = [
    "HL_EXCHANGE_URL",
    "HL_INFO_URL",
    "HyperliquidLiveExecClient",
    "LiveExecClient",
    "PlaceResult",
    "PlaceTransport",
    "create_live_exec_client",
    "create_live_exec_client_from_env",
    "is_submit_wired",
]


@dataclass(frozen=True)
class PlaceResult:
    """Outcome of a venue place attempt."""

    submitted: bool
    venue_order_id: str | None
    error: str | None


@runtime_checkable
class PlaceTransport(Protocol):
    """Low-level venue place/cancel (injectable for offline tests)."""

    def place_market(
        self,
        *,
        coin: str,
        is_buy: bool,
        sz: float,
        wallet_address: str,
        private_key: str,
    ) -> dict[str, Any]:
        """Return venue response dict; should include ``oid`` when accepted."""
        ...

    def cancel_all(
        self,
        *,
        wallet_address: str,
        private_key: str,
        coin: str | None = None,
    ) -> dict[str, Any]:
        """Best-effort cancel open orders; return venue response dict."""
        ...


@runtime_checkable
class LiveExecClient(Protocol):
    """Public place + kill surface for armed live execution."""

    def place_market(
        self,
        symbol: str,
        side: str,
        qty: float,
        *,
        mark_px: float | None = None,
        client_order_id: str | None = None,
    ) -> PlaceResult: ...

    def cancel_all(self, *, symbol: str | None = None) -> PlaceResult: ...

def is_submit_wired() -> bool:
    """True when the live exec client module is present (F2+)."""
    return True


def _parse_oid(response: dict[str, Any]) -> str | None:
    if not isinstance(response, dict):
        return None
    for key in ("oid", "order_id", "venue_order_id", "id"):
        val = response.get(key)
        if val is not None and val != "":
            return str(val)
    # Nested HL-style response.statuses[0].resting.oid etc.
    statuses = response.get("response") or response.get("statuses")
    if isinstance(statuses, dict):
        data = statuses.get("data") if isinstance(statuses.get("data"), dict) else statuses
        st_list = data.get("statuses") if isinstance(data, dict) else None
        if isinstance(st_list, list) and st_list:
            first = st_list[0]
            if isinstance(first, dict):
                for nest in ("resting", "filled", "oid"):
                    node = first.get(nest) if nest != "oid" else first
                    if isinstance(node, dict) and node.get("oid") is not None:
                        return str(node["oid"])
                    if nest == "oid" and first.get("oid") is not None:
                        return str(first["oid"])
    return None


def _check_venue_error(response: dict[str, Any]) -> str | None:
    if not isinstance(response, dict):
        return None
    if response.get("status") in ("err", "error") or "error" in response:
        return str(response.get("error") or response.get("response") or response)

    # Check nested Hyperliquid response.data.statuses[0].error
    statuses = response.get("response") or response.get("statuses")
    if isinstance(statuses, dict):
        data = statuses.get("data") if isinstance(statuses.get("data"), dict) else statuses
        st_list = data.get("statuses") if isinstance(data, dict) else None
        if isinstance(st_list, list) and st_list:
            first = st_list[0]
            if isinstance(first, dict) and "error" in first:
                return str(first["error"])
    return None


def _normalize_side(side: str) -> bool:
    s = str(side).strip().lower()
    if s in ("buy", "long", "b"):
        return True
    if s in ("sell", "short", "s"):
        return False
    raise ValueError(f"unsupported side: {side!r}")


class HyperliquidLiveExecClient:
    """Mainnet-only Hyperliquid place adapter.

    Does not place on construct. Enforces notional cap via policy before
    calling the injected transport.
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
        self._max_notional_usd = float(max_notional_usd)

    def place_market(
        self,
        symbol: str,
        side: str,
        qty: float,
        *,
        mark_px: float | None = None,
        client_order_id: str | None = None,
    ) -> PlaceResult:
        del client_order_id  # reserved for F3 daemon intent stamping
        try:
            is_buy = _normalize_side(side)
            q = float(qty)
            if q <= 0:
                return PlaceResult(
                    submitted=False,
                    venue_order_id=None,
                    error=f"qty must be positive, got {qty!r}",
                )
            if mark_px is None:
                return PlaceResult(
                    submitted=False,
                    venue_order_id=None,
                    error="mark_px required for notional cap check",
                )
            # Cap check without constructing a full LivePolicy (gates already passed).
            notional = abs(q) * float(mark_px)
            cap = self._max_notional_usd
            if notional > cap + 1e-12:
                return PlaceResult(
                    submitted=False,
                    venue_order_id=None,
                    error=(
                        f"notional {notional:.6f} exceeds max_notional_usd {cap:.6f}"
                    ),
                )
            coin = hl_coin(symbol)
            raw = self._transport.place_market(
                coin=coin,
                is_buy=is_buy,
                sz=q,
                wallet_address=self._wallet,
                private_key=self._private_key,
            )
            raw_dict = raw if isinstance(raw, dict) else {}
            err_msg = _check_venue_error(raw_dict)
            if err_msg:
                return PlaceResult(submitted=False, venue_order_id=None, error=err_msg)
            oid = _parse_oid(raw_dict)
            return PlaceResult(submitted=True, venue_order_id=oid, error=None)
        except LivePolicyError as exc:
            return PlaceResult(submitted=False, venue_order_id=None, error=str(exc))
        except Exception as exc:  # noqa: BLE001 — surface venue/transport failures
            return PlaceResult(submitted=False, venue_order_id=None, error=str(exc))

    def cancel_all(self, *, symbol: str | None = None) -> PlaceResult:
        """Best-effort cancel open orders (F4 kill switch)."""
        try:
            coin = hl_coin(symbol) if symbol else None
            cancel = getattr(self._transport, "cancel_all", None)
            if cancel is None:
                return PlaceResult(
                    submitted=False,
                    venue_order_id=None,
                    error="transport does not support cancel_all",
                )
            raw = cancel(
                wallet_address=self._wallet,
                private_key=self._private_key,
                coin=coin,
            )
            oid = _parse_oid(raw if isinstance(raw, dict) else {})
            # submitted=True means cancel request was accepted by transport.
            return PlaceResult(submitted=True, venue_order_id=oid, error=None)
        except Exception as exc:  # noqa: BLE001 — best-effort kill path
            return PlaceResult(submitted=False, venue_order_id=None, error=str(exc))


class _SdkPlaceTransport:
    """Optional production transport: hyperliquid-python-sdk when installed.

    Offline suite never constructs this without an inject; place raises a clear
    error if the SDK is absent.
    """

    def place_market(
        self,
        *,
        coin: str,
        is_buy: bool,
        sz: float,
        wallet_address: str,
        private_key: str,
    ) -> dict[str, Any]:
        del wallet_address  # account derived from private key in SDK path
        try:
            from eth_account import Account  # type: ignore[import-untyped]
            from hyperliquid.exchange import Exchange  # type: ignore[import-untyped]
            from hyperliquid.utils import constants  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "Hyperliquid place requires optional deps "
                "(hyperliquid-python-sdk + eth_account). "
                "Install them for live place, or inject a PlaceTransport in tests."
            ) from exc

        # Mainnet only — refuse testnet base URL constants.
        api_url = getattr(constants, "MAINNET_API_URL", "https://api.hyperliquid.xyz")
        if "testnet" in str(api_url).lower():
            raise RuntimeError("refusing testnet Hyperliquid URL")
        account = Account.from_key(private_key)
        exchange = Exchange(account, base_url=api_url)
        # Market: IOC at aggressive limit is the common HL pattern; SDK market_open if present.
        if hasattr(exchange, "market_open"):
            raw = exchange.market_open(coin, is_buy, sz)
        else:
            # Fallback: order with IOC market-style (px None / market flag varies by SDK version)
            raw = exchange.order(
                coin,
                is_buy,
                sz,
                0.0,
                {"limit": {"tif": "Ioc"}},
                reduce_only=False,
            )
        if isinstance(raw, dict):
            return raw
        return {"status": "ok", "raw": raw, "oid": None}

    def cancel_all(
        self,
        *,
        wallet_address: str,
        private_key: str,
        coin: str | None = None,
    ) -> dict[str, Any]:
        del wallet_address
        try:
            from eth_account import Account  # type: ignore[import-untyped]
            from hyperliquid.exchange import Exchange  # type: ignore[import-untyped]
            from hyperliquid.utils import constants  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "Hyperliquid cancel requires optional deps "
                "(hyperliquid-python-sdk + eth_account)."
            ) from exc

        api_url = getattr(constants, "MAINNET_API_URL", "https://api.hyperliquid.xyz")
        if "testnet" in str(api_url).lower():
            raise RuntimeError("refusing testnet Hyperliquid URL")
        account = Account.from_key(private_key)
        exchange = Exchange(account, base_url=api_url)
        if coin and hasattr(exchange, "cancel"):
            # Best-effort: schedule cancel-all for coin if SDK exposes bulk cancel.
            if hasattr(exchange, "cancel_all"):
                raw = exchange.cancel_all(coin)
            else:
                raw = {"status": "ok", "note": "no cancel_all on SDK; open orders untouched"}
        elif hasattr(exchange, "cancel_all"):
            raw = exchange.cancel_all()
        else:
            raw = {"status": "ok", "note": "cancel_all not available on SDK build"}
        if isinstance(raw, dict):
            return raw
        return {"status": "ok", "raw": raw}


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
            "live secrets missing — set "
            f"{SECRET_ENV_WALLET} and {SECRET_ENV_API_KEY}"
        )
    return create_live_exec_client(
        policy,
        wallet_address=wallet,
        private_key=key,
        transport=transport,
    )
