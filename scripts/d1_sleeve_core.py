#!/usr/bin/env python3
"""Pure core of the D1 sleeve executor (Sleeve S1 on a Hyperliquid sub-account).

This module holds everything that does not talk to a network peer: the frozen
configuration and its fingerprint, address fingerprints and redaction, venue
arithmetic (price and size rounding, units, client order ids), parsers for the
Hyperliquid info and order responses, the read-only view of the observe-only
shadow ledger, the executor journal (read, verify, append, derive the book),
entry sizing and the exit and protection planners.

It imports only the standard library and ``d1_shadow_runner`` (the pinned
shadow whose ledger is the only source of universe, signals and exits). It has
no network client, no SDK, no environment access and no subprocess. The only
files it touches are the journal (appends are fsynced) and, read-only, the
shadow ledger through ``runner.load_ledger``.

Rules (pre-registered in docs/plans/2026-09-27-d1-shadow-prereg.md, extended by
the sleeve amendment): risk ``risk_fraction`` of BOOK equity (master + sub) at
a stop of 2 x ATR(signal) x unit from the Hyperliquid fill; at most 10 slots
and gross <= 1.5 x book counted over every sub position; isolated leverage
L = min(3, floor(1 / (MMR + 2.5 x stop_fraction))), shorts capped at 2, with
MMR from the VENUE maxLeverage. No drawdown, P&L or kill limit exists
(SRS_HV1_NO_GATES); ``max_order_to_book`` is a technical sanity bound against
unit or data errors, not a size cap.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any

import d1_shadow_runner as runner

SCHEMA = "d1_sleeve_journal_v1"
HL_HOST = "api.hyperliquid.xyz"
HL_URL = "https://api.hyperliquid.xyz"
REPO_ROOT = Path(__file__).resolve().parents[1]

ENV_MASTER = "HYPERVECTOR_HL_WALLET_ADDRESS"
ENV_SUB = "HYPERVECTOR_D1_SUBACCOUNT_ADDRESS"
ENV_AGENT = "HYPERVECTOR_D1_AGENT_ADDRESS"
ENV_KEY = "HYPERVECTOR_D1_API_PRIVATE_KEY"
ENV_ENGINE_KEY = "HYPERVECTOR_HL_API_PRIVATE_KEY"
ENV_WEBHOOK = "HYPERVECTOR_ALERT_WEBHOOK_URL"
ENV_DEADMAN = "HYPERVECTOR_D1_DEADMAN_URL"
PUBLIC_ENV_KEYS = (ENV_MASTER, ENV_SUB, ENV_AGENT, ENV_WEBHOOK, ENV_DEADMAN)

ACCOUNT_MODES = frozenset({"unifiedAccount", "disabled"})
ORDER_ROLES = frozenset(
    {
        "entry",
        "exit",
        "stop",
        "breach",
        "flatten",
        "dust",
        "canary_entry",
        "canary_stop",
        "canary_close",
        # A protective reduce-only stop on a position the sleeve cannot
        # attribute (A2: every position in the sub ends a sweep covered).
        "guard",
    }
)
# Journal trade_id of the guard stops on one coin (their cloids count up by n).
GUARD_TRADE_PREFIX = "guard:"
# A guard stop's distance when neither the shadow nor the journal holds an
# ATR for the coin: a conservative 15% of the position's entry price.
GUARD_FALLBACK_FRACTION = 0.15
# A stop that would sit at or beyond the liquidation price is moved to this
# fraction of the way from the liquidation price back to the mark.
GUARD_LIQ_FRACTION = 0.5
CLOSE_ROLES = frozenset({"exit", "breach", "flatten", "dust", "canary_close"})
_CLOSE_ROLE_BY_REASON = {
    "breach": "breach",
    "manual_flatten": "flatten",
    "dust_fill": "dust",
}
SHADOW_EXIT_REASONS = {
    "channel_exit": "channel_exit",
    "stop_intrabar": "shadow_stop",
    "gap_stop": "gap_stop",
    "liquidation_gap": "liquidation_gap",
}
JOURNAL_EVENTS = frozenset(
    {
        "run_start",
        "identity_verified",
        "snapshot",
        "intent",
        "outcome",
        "leverage",
        "trade_opened",
        "position_grew",
        "stop_placed",
        "stop_cancelled",
        "trade_closed",
        "trade_report",
        "skip",
        "alert",
        "canary_result",
        "run_end",
    }
)
CRITICAL = "critical"
NOTICE = "notice"
CRITICAL_CODES = frozenset(
    {
        "unprotected_position",
        "unprotectable",
        "stop_behind_liquidation",
        "not_isolated",
        "liquidation",
        "venue_flat_other",
        "exit_incomplete",
        "unknown_position",
        "unknown_order",
        "direction_conflict",
        "trade_unknown_to_shadow",
        "shadow_ledger_invalid",
        "shadow_config_mismatch",
        "identity_refused_with_positions",
        "run_stuck",
        "hl_budget_exhausted",
        "unit_mismatch",
        "sizing_sanity",
        "coin_held_unowned",
        "equity_invalid",
        "canary_failed",
        "technical_failure",
        "slots_gross_violation",
        "preflight_refused",
        "preflight_failed",
        "canary_residue",
        "unresolved_entry",
        "fill_not_visible",
        "stop_missing",
        "clock_skew",
        "entry_overfill",
    }
)
TERMINAL_SKIPS = frozenset(
    {
        "invalid_stop",
        "unit_mismatch",
        "rule_stop_breached",
        "sizing_sanity",
        "slots_full",
        "gross_cap",
        "below_min_notional",
        "coin_not_tradeable",
        "coin_held_unowned",
        "window_expired",
        "attempts_exhausted",
    }
)
CRITICAL_SKIPS = frozenset({"unit_mismatch", "sizing_sanity", "coin_held_unowned"})
# frontendOpenOrders orderType of a market stop trigger ("" when the field is absent).
STOP_ORDER_TYPES = frozenset({"Stop Market", ""})
DAY_MS = 86_400_000


class SleeveError(RuntimeError):
    """A fail-closed condition; ``exit_code`` is what the CLI returns."""

    exit_code = 2


class RefusalError(SleeveError):
    """Refused before any mutation: flags, approval, env, identity, integrity."""

    exit_code = 3


class TechnicalError(SleeveError):
    """A technical failure (the only thing that aborts; SRS_HV1_NO_GATES)."""

    exit_code = 2


class JournalError(TechnicalError):
    """The sleeve journal is torn, edited or out of chain."""


class ShadowUnavailable(SleeveError):
    """The shadow ledger was being written during every read attempt."""


class ShadowViewError(SleeveError):
    """The shadow ledger cannot drive the sleeve (no mark, unreadable state)."""


class ShadowConfigMismatch(ShadowViewError):
    """The shadow ledger belongs to another shadow configuration."""


# ----------------------------------------------------------------- config


@dataclass(frozen=True)
class SleeveConfig:
    sleeve_id: str = "d1_sleeve_v1"
    risk_fraction: float = 0.01
    max_slots: int = 10
    gross_cap: float = 1.5
    min_fill_fraction: float = 0.25
    min_order_usd: float = 11.0
    max_order_to_book: float = 0.5
    collateral_reserve_fraction: float = 0.05
    entry_window_hours: int = 6
    entry_slippage_bps: int = 50
    entry_max_attempts: int = 3
    exit_ladder_bps: tuple[int, ...] = (100, 200, 400)
    expires_after_seconds: int = 45
    trade_minute_first: int = 5
    trade_minute_last: int = 45
    sweep_minute_last: int = 56
    quiet_minutes: tuple[int, ...] = (57, 58, 59, 0, 1, 2, 3)
    hl_min_spacing_s: float = 0.5
    hl_weight_per_minute: int = 200
    hl_max_info_weight_per_run: int = 900
    hl_max_info_calls_per_run: int = 150
    hl_max_exchange_actions_per_run: int = 120
    hl_sweep_reserve_weight: int = 120
    hl_sweep_reserve_actions: int = 30
    hl_sweep_reserve_calls: int = 20
    http_timeout_s: float = 10.0
    shadow_read_retries: int = 6
    shadow_read_retry_s: float = 10.0
    agent_name: str = "d1-sleeve"
    engine_agent_name: str = "hl-api"
    agent_min_days_to_arm: int = 1
    agent_warn_days: int = 14
    agent_critical_days: int = 3
    shadow_runner_sha256: str = (
        "3496738ee6e98c8dd54ecb75f933b17aae80c36466b7eef3ca48ed713fba4471"
    )
    shadow_config_fingerprint: str = "c9ea5f06dd1658e4"
    cloid_prefix: str = "0xd15e"
    liq_buffer_warn_fraction: float = 0.9
    alert_remind_hours: int = 6
    shadow_stale_notice_hour_utc: int = 4
    shadow_stale_critical_hour_utc: int = 12

    def fingerprint(self) -> str:
        return runner._sha256(runner._canonical(asdict(self)))[:16]


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    journal: Path
    stop_file: Path
    lock: Path
    runtime_dir: Path
    alerts: Path
    status: Path
    shadow_ledger: Path
    census: Path
    host_lock_dir: Path

    @classmethod
    def default(cls, root: Path | None = None) -> Paths:
        """Repo-relative data paths plus one host-wide lock directory.

        The host lock (one per sub-account fingerprint) serialises armed runs
        from ANY checkout of the repository against the same sub-account; with
        an explicit ``root`` (tests) it lives under that root instead.
        """
        base = REPO_ROOT if root is None else Path(root)
        live = base / "data" / "live" / "d1_sleeve"
        runtime = base / "data" / "runtime" / "d1_sleeve"
        research = base / "data" / "research" / "d1_shadow"
        host = (
            Path.home() / ".config" / "hypervector"
            if root is None
            else base / "host-locks"
        )
        return cls(
            repo_root=base,
            journal=live / "journal.jsonl",
            stop_file=live / "STOP",
            lock=live / "executor.lock",
            runtime_dir=runtime,
            alerts=runtime / "alerts.jsonl",
            status=runtime / "status.json",
            shadow_ledger=research / "ledger.jsonl",
            census=research / "census_perps.csv",
            host_lock_dir=host,
        )

    def host_lock(self, sub_fp: str) -> Path:
        return self.host_lock_dir / f"d1_sleeve.{sub_fp}.lock"


# ----------------------------------------------------------------- helpers

_ADDRESS = re.compile(r"0x[0-9a-f]{40}")
_ADDRESS_ANY_CASE = re.compile(r"0x[0-9a-fA-F]{40}")
_HEX64 = re.compile(r"(?:0x)?[0-9a-fA-F]{64,}")


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def now_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def normalize_address(value: object, label: str) -> str:
    """Lowercase ``0x`` + 40 hex, or a refusal that never echoes the value."""
    if not isinstance(value, str):
        raise RefusalError(f"{label} is missing or not a string")
    text = value.strip().lower()
    if not _ADDRESS.fullmatch(text):
        raise RefusalError(f"{label} is not a 0x-prefixed 40-hex address")
    return text


def is_address(value: object) -> bool:
    return isinstance(value, str) and bool(_ADDRESS.fullmatch(value.strip().lower()))


def address_fp(address: str, sleeve_id: str = SleeveConfig.sleeve_id) -> str:
    """Fingerprint for logs and approvals; the address itself is never printed."""
    return hashlib.sha256(f"{sleeve_id}|{address.lower()}".encode()).hexdigest()[:12]


def redact(text: object, limit: int = 200) -> str:
    """Hide addresses and 64-hex values (keys, hashes) and truncate."""
    value = _HEX64.sub("<hex64>", str(text))
    value = _ADDRESS_ANY_CASE.sub("0x<addr>", value)
    return value[:limit]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ----------------------------------------------------------------- venue math


def normalize_price(px: float, sz_decimals: int) -> float:
    """Five significant figures, then 6 - szDecimals decimals (SDK/engine rule)."""
    if not (_finite(px) and px > 0):
        raise TechnicalError("price must be a positive finite number")
    return round(float(f"{px:.5g}"), 6 - int(sz_decimals))


def round_size_down(sz: float, sz_decimals: int) -> float:
    try:
        quantum = Decimal(1).scaleb(-int(sz_decimals))
        value = Decimal(repr(float(sz))).quantize(quantum, rounding=ROUND_DOWN)
    except (InvalidOperation, ValueError) as exc:
        raise TechnicalError("size is not a finite number") from exc
    if not value.is_finite():
        raise TechnicalError("size is not a finite number")
    if value <= 0:
        raise TechnicalError("size rounds down to zero")
    return float(value)


def size_remainder(want: float, filled: float, sz_decimals: int) -> float:
    """``want - filled`` in exact decimals, rounded down to the lot (0.0 if none).

    A float subtraction (0.3 - 0.1 = 0.19999...) would lose a whole lot.
    """
    try:
        quantum = Decimal(1).scaleb(-int(sz_decimals))
        rest = Decimal(repr(float(want))) - Decimal(repr(float(filled)))
        value = rest.quantize(quantum, rounding=ROUND_DOWN)
    except (InvalidOperation, ValueError) as exc:
        raise TechnicalError("size is not a finite number") from exc
    if not value.is_finite():
        raise TechnicalError("size is not a finite number")
    return float(value) if value > 0 else 0.0


def ioc_limit(mid: float, is_buy: bool, bps: float, sz_decimals: int) -> float:
    factor = 1.0 + bps / 1e4 if is_buy else 1.0 - bps / 1e4
    return normalize_price(mid * factor, sz_decimals)


def price_unit(coin: str) -> float:
    """Hyperliquid 1000x contracts (kPEPE) quote 1000 Binance units."""
    return 1000.0 if runner._KILO_PREFIX.fullmatch(coin) else 1.0


def cloid_for(cfg: SleeveConfig, sub: str, trade_id: str, role: str, n: int) -> str:
    """Per-attempt client order id: the prefix marks sleeve ownership."""
    if role not in ORDER_ROLES:
        raise TechnicalError(f"unknown order role {role}")
    digest = hashlib.sha256(
        f"{cfg.sleeve_id}|{sub.lower()}|{trade_id}|{role}|{n}".encode()
    ).hexdigest()
    return cfg.cloid_prefix + digest[: 34 - len(cfg.cloid_prefix)]


def is_owned_cloid(cfg: SleeveConfig, cloid: object) -> bool:
    return isinstance(cloid, str) and cloid.lower().startswith(cfg.cloid_prefix)


def close_role(reason: str) -> str:
    return _CLOSE_ROLE_BY_REASON.get(reason, "exit")


def sizes_equal(a: float, b: float, sz_decimals: int) -> bool:
    return abs(float(a) - float(b)) < 0.5 * 10 ** (-int(sz_decimals))


def prices_equal(a: float | None, b: float) -> bool:
    if a is None:
        return False
    return abs(float(a) - float(b)) <= 1e-9 * max(abs(float(b)), 1e-12)


# ----------------------------------------------------------------- parsers


def _number(value: object, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise TechnicalError(f"{label} is not a number") from exc
    if not math.isfinite(number):
        raise TechnicalError(f"{label} is not finite")
    return number


def _optional_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    return _number(value, label)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TechnicalError(f"{label} is not an object")
    return value


def _sequence(value: object, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise TechnicalError(f"{label} is not a list")
    return value


@dataclass(frozen=True)
class MarketInfo:
    name: str
    asset: int
    sz_decimals: int
    max_leverage: float
    is_delisted: bool
    only_isolated: bool


def parse_meta(value: object) -> dict[str, MarketInfo]:
    universe = _sequence(_mapping(value, "meta").get("universe"), "meta universe")
    markets: dict[str, MarketInfo] = {}
    for asset, raw in enumerate(universe):
        item = _mapping(raw, "meta asset")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise TechnicalError("meta asset has no name")
        markets[name] = MarketInfo(
            name=name,
            asset=asset,
            sz_decimals=int(_number(item.get("szDecimals"), "szDecimals")),
            max_leverage=_number(item.get("maxLeverage"), "maxLeverage"),
            is_delisted=bool(item.get("isDelisted", False)),
            only_isolated=bool(item.get("onlyIsolated", False)),
        )
    return markets


def tradeable(markets: Mapping[str, MarketInfo], coin: str) -> bool:
    market = markets.get(coin)
    return market is not None and ":" not in coin and not market.is_delisted


def parse_mids(value: object) -> dict[str, float]:
    mids: dict[str, float] = {}
    for coin, raw in _mapping(value, "allMids").items():
        try:
            price = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(price) and price > 0:
            mids[str(coin)] = price
    return mids


@dataclass(frozen=True)
class VenuePosition:
    coin: str
    szi: float
    entry_px: float
    position_value: float
    liquidation_px: float | None
    leverage_type: str
    leverage_value: int
    margin_used: float

    @property
    def direction(self) -> int:
        return 1 if self.szi > 0 else -1

    @property
    def size(self) -> float:
        return abs(self.szi)


def parse_positions(value: object) -> dict[str, VenuePosition]:
    state = _mapping(value, "clearinghouse state")
    positions: dict[str, VenuePosition] = {}
    for raw in _sequence(state.get("assetPositions"), "asset positions"):
        item = _mapping(_mapping(raw, "asset position").get("position"), "position")
        coin = item.get("coin")
        if not isinstance(coin, str) or not coin:
            raise TechnicalError("position has no coin")
        szi = _number(item.get("szi"), "szi")
        if szi == 0:
            continue
        if coin in positions:
            raise TechnicalError(f"two positions reported for {coin}")
        leverage = _mapping(item.get("leverage"), "position leverage")
        positions[coin] = VenuePosition(
            coin=coin,
            szi=szi,
            entry_px=_number(item.get("entryPx"), "entryPx"),
            position_value=_number(item.get("positionValue", 0.0), "positionValue"),
            liquidation_px=_optional_number(item.get("liquidationPx"), "liqPx"),
            leverage_type=str(leverage.get("type", "")),
            leverage_value=int(_number(leverage.get("value"), "leverage value")),
            margin_used=_number(item.get("marginUsed", 0.0), "marginUsed"),
        )
    return positions


@dataclass(frozen=True)
class VenueOrder:
    coin: str
    oid: int
    cloid: str | None
    is_buy: bool
    sz: float
    is_trigger: bool
    trigger_px: float | None
    reduce_only: bool
    order_type: str
    has_cloid_field: bool = False


def parse_open_orders(value: object) -> list[VenueOrder]:
    orders: list[VenueOrder] = []
    for raw in _sequence(value, "open orders"):
        item = _mapping(raw, "open order")
        coin = item.get("coin")
        if not isinstance(coin, str):
            raise TechnicalError("open order has no coin")
        is_trigger = bool(item.get("isTrigger", False))
        size = item.get("origSz") if item.get("origSz") is not None else item.get("sz")
        cloid = item.get("cloid")
        orders.append(
            VenueOrder(
                coin=coin,
                oid=int(_number(item.get("oid"), "oid")),
                cloid=cloid.lower() if isinstance(cloid, str) else None,
                is_buy=item.get("side") == "B",
                sz=_number(size, "order size"),
                is_trigger=is_trigger,
                trigger_px=(
                    _number(item.get("triggerPx"), "triggerPx") if is_trigger else None
                ),
                reduce_only=bool(item.get("reduceOnly", False)),
                order_type=str(item.get("orderType", "")),
                has_cloid_field="cloid" in item,
            )
        )
    return orders


@dataclass(frozen=True)
class AccountValue:
    equity_usd: float
    free_usd: float


def parse_account_mode(value: object) -> str:
    if not isinstance(value, str) or value not in ACCOUNT_MODES:
        shown = value if isinstance(value, str) else type(value).__name__
        raise RefusalError(f"account abstraction {redact(shown, 40)} is not supported")
    return value


def parse_account_value(
    mode: str, perp_state: object, spot_state: object | None
) -> AccountValue:
    """Equity and free collateral with the engine's abstraction semantics."""
    if mode == "unifiedAccount":
        balances = _sequence(
            _mapping(spot_state, "spot clearinghouse state").get("balances"),
            "spot balances",
        )
        usdc = [
            item
            for item in balances
            if isinstance(item, Mapping) and item.get("coin") == "USDC"
        ]
        if len(usdc) != 1:
            raise TechnicalError(
                "unified spot state must hold exactly one USDC balance"
            )
        total = _number(usdc[0].get("total"), "USDC total")
        hold = _number(usdc[0].get("hold"), "USDC hold")
        if total < 0 or hold < 0:
            raise TechnicalError("USDC balance is negative")
        if hold > total:
            raise TechnicalError("USDC hold exceeds the unified USDC total")
        return AccountValue(equity_usd=total, free_usd=max(0.0, total - hold))
    if mode == "disabled":
        state = _mapping(perp_state, "clearinghouse state")
        summary = _mapping(state.get("marginSummary"), "margin summary")
        return AccountValue(
            equity_usd=_number(summary.get("accountValue"), "accountValue"),
            free_usd=max(0.0, _number(state.get("withdrawable"), "withdrawable")),
        )
    raise RefusalError(f"account abstraction {redact(mode, 40)} is not supported")


@dataclass(frozen=True)
class OrderAck:
    status: str  # filled | resting | no_fill | error
    oid: int | None = None
    filled_sz: float = 0.0
    avg_px: float | None = None
    error: str | None = None


def _order_statuses(value: object) -> list[Any] | list[OrderAck]:
    """The raw statuses of an ok order response, or one error ack per order."""
    response = _mapping(value, "order response")
    status = response.get("status")
    if status == "err":
        return [OrderAck("error", error=redact(response.get("response", "error")))]
    if status != "ok":
        raise TechnicalError("order response has neither ok nor err status")
    try:
        statuses = response["response"]["data"]["statuses"]
    except (KeyError, TypeError) as exc:
        raise TechnicalError("order response lacks statuses") from exc
    if not isinstance(statuses, list):
        raise TechnicalError("order response has an unexpected status count")
    return statuses


def _order_ack(item: object) -> OrderAck:
    """One order status. A bare-string or unknown status is a TechnicalError."""
    if not isinstance(item, Mapping):
        raise TechnicalError(f"unknown order status {redact(item, 60)}")
    if "filled" in item:
        filled = _mapping(item["filled"], "filled status")
        return OrderAck(
            "filled",
            oid=int(_number(filled.get("oid"), "oid")),
            filled_sz=_number(filled.get("totalSz"), "totalSz"),
            avg_px=_number(filled.get("avgPx"), "avgPx"),
        )
    if "resting" in item:
        resting = _mapping(item["resting"], "resting status")
        return OrderAck("resting", oid=int(_number(resting.get("oid"), "oid")))
    if "error" in item:
        text = str(item["error"])
        kind = "no_fill" if "could not immediately match" in text.lower() else "error"
        return OrderAck(kind, error=redact(text))
    raise TechnicalError(f"unknown order status {redact(item, 60)}")


def parse_order_statuses(value: object, expected: int = 1) -> list[OrderAck]:
    """Order acks. A bare-string or unknown status is a TechnicalError (ambiguous)."""
    statuses = _order_statuses(value)
    if statuses and isinstance(statuses[0], OrderAck):  # a top-level err
        return [statuses[0] for _ in range(expected)]
    if len(statuses) != expected:
        raise TechnicalError("order response has an unexpected status count")
    return [_order_ack(item) for item in statuses]


def parse_grouped_statuses(value: object) -> tuple[OrderAck, OrderAck]:
    """Acks of an entry IOC sent with its reduce-only stop child (normalTpsl).

    The parent's status is parsed as strictly as any order's (an unknown one
    is a TechnicalError: the send is ambiguous and orderStatus resolves it).
    The child's never makes the send ambiguous. It is ``resting`` (with its
    oid when the reply gives one), ``error``, or ``waiting`` for anything else
    (the waitingForFill / waitingForTrigger strings, or no status at all):
    whether the child rests follows from the parent, since the venue places
    the children of a parent that fully fills and cancels them with a parent
    that does not."""
    statuses = _order_statuses(value)
    if statuses and isinstance(statuses[0], OrderAck):  # a top-level err
        return statuses[0], statuses[0]
    if not 1 <= len(statuses) <= 2:
        raise TechnicalError("order response has an unexpected status count")
    parent = _order_ack(statuses[0])
    item = statuses[1] if len(statuses) == 2 else None
    child = OrderAck("waiting")
    if isinstance(item, Mapping) and "error" in item:
        child = OrderAck("error", error=redact(str(item["error"])))
    elif isinstance(item, Mapping) and isinstance(item.get("resting"), Mapping):
        oid = item["resting"].get("oid")
        child = OrderAck("resting", oid=int(oid) if _finite(oid) else None)
    return parent, child


def parse_cancel_ack(value: object) -> tuple[bool, str | None]:
    if not isinstance(value, Mapping):
        return False, "cancel response is not an object"
    if value.get("status") != "ok":
        return False, redact(value.get("response", "error"))
    try:
        statuses = value["response"]["data"]["statuses"]
    except (KeyError, TypeError):
        return False, "cancel response lacks statuses"
    if statuses == ["success"]:
        return True, None
    return False, redact(statuses)


def cancel_target_gone(error: object) -> bool:
    """A cancel rejected because the order no longer rests (filled, triggered,
    or auto-cancelled by the venue, e.g. a reduce-only stop on a flat coin)."""
    text = str(error or "").lower()
    return "never placed" in text or "already canceled" in text


def parse_leverage_ack(value: object) -> tuple[bool, str | None]:
    if isinstance(value, Mapping) and value.get("status") == "ok":
        return True, None
    shown = value.get("response") if isinstance(value, Mapping) else value
    return False, redact(shown)


@dataclass(frozen=True)
class QueriedStatus:
    # never_landed | filled | partial | open | no_fill | canceled | triggered | rejected
    status: str
    venue_status: str
    oid: int | None
    filled_sz: float


def parse_order_status(value: object) -> QueriedStatus:
    response = _mapping(value, "orderStatus response")
    if response.get("status") == "unknownOid":
        return QueriedStatus("never_landed", "unknownOid", None, 0.0)
    if response.get("status") != "order":
        raise TechnicalError("orderStatus response has an unknown status")
    outer = _mapping(response.get("order"), "orderStatus order")
    inner = _mapping(outer.get("order"), "orderStatus inner order")
    venue = str(outer.get("status", ""))
    remaining = _number(inner.get("sz", 0.0), "sz")
    original = _number(inner.get("origSz", remaining), "origSz")
    filled = max(0.0, original - remaining)
    oid = int(_number(inner.get("oid"), "oid"))
    if venue == "filled":
        status = "filled"
    elif venue == "open":
        status = "open"
    elif venue == "triggered":
        status = "triggered"
    elif venue == "iocCancelRejected":  # an IOC that found nothing to match
        status = "partial" if filled > 0 else "no_fill"
    elif venue == "canceled" or venue.endswith("Canceled"):
        status = "partial" if filled > 0 else "canceled"
    else:
        status = "partial" if filled > 0 else "rejected"
    return QueriedStatus(status, venue, oid, filled)


@dataclass(frozen=True)
class Fill:
    coin: str
    oid: int
    px: float
    sz: float
    is_buy: bool
    time_ms: int
    closed_pnl: float
    fee: float
    liquidation: bool


def parse_fills(value: object) -> list[Fill]:
    fills: list[Fill] = []
    for raw in _sequence(value, "fills"):
        item = _mapping(raw, "fill")
        fills.append(
            Fill(
                coin=str(item.get("coin", "")),
                oid=int(_number(item.get("oid"), "fill oid")),
                px=_number(item.get("px"), "fill px"),
                sz=_number(item.get("sz"), "fill sz"),
                is_buy=item.get("side") == "B",
                time_ms=int(_number(item.get("time"), "fill time")),
                closed_pnl=_number(item.get("closedPnl", 0.0), "closedPnl"),
                fee=_number(item.get("fee", 0.0), "fee"),
                liquidation=item.get("liquidation") is not None,
            )
        )
    return fills


@dataclass(frozen=True)
class FundingDelta:
    coin: str
    usdc: float
    time_ms: int


def parse_funding(value: object) -> list[FundingDelta]:
    deltas: list[FundingDelta] = []
    for raw in _sequence(value, "funding"):
        item = _mapping(raw, "funding item")
        delta = _mapping(item.get("delta"), "funding delta")
        deltas.append(
            FundingDelta(
                coin=str(delta.get("coin", "")),
                usdc=_number(delta.get("usdc", 0.0), "funding usdc"),
                time_ms=int(_number(item.get("time"), "funding time")),
            )
        )
    return deltas


@dataclass(frozen=True)
class AgentEntry:
    base_name: str
    address: str
    valid_until_ms: int | None


def agent_base_name(name: str) -> str:
    return name.split(" valid_until")[0].strip()


def parse_extra_agents(value: object) -> list[AgentEntry]:
    agents: list[AgentEntry] = []
    for raw in _sequence(value, "extraAgents"):
        item = _mapping(raw, "extraAgents entry")
        address = item.get("address")
        if not is_address(address):
            continue
        until = item.get("validUntil")
        agents.append(
            AgentEntry(
                base_name=agent_base_name(str(item.get("name", ""))),
                address=str(address).strip().lower(),
                valid_until_ms=int(_number(until, "validUntil")) if until else None,
            )
        )
    return agents


def parse_sub_accounts(value: object) -> list[tuple[str, str]]:
    """(sub-account, master) pairs, lowercase; the raw response is never kept."""
    if value is None:
        return []
    pairs: list[tuple[str, str]] = []
    for raw in _sequence(value, "subAccounts"):
        item = _mapping(raw, "subAccounts entry")
        sub, master = item.get("subAccountUser"), item.get("master")
        if is_address(sub) and is_address(master):
            pairs.append((str(sub).strip().lower(), str(master).strip().lower()))
    return pairs


# ----------------------------------------------------------------- shadow view


@dataclass(frozen=True)
class VirtualEntry:
    trade_id: str
    coin: str
    direction: int
    signal_date: str
    entry_date: str
    entry_px: float
    atr_signal: float
    priority_rank: int
    taken: bool
    skip_reason: str | None
    stop_px: float | None
    binance_symbol: str
    max_leverage: float | None = None


@dataclass(frozen=True)
class ClosedVirtual:
    trade_id: str
    exit_reason: str
    exit_px: float | None
    bar_date: str
    net_r: float | None


@dataclass
class ShadowView:
    today: date
    mark_date: date
    mode: str | None
    fresh: bool
    open_ids: frozenset[str]
    pending_exits: dict[str, str]
    closed_index: dict[str, ClosedVirtual]
    known_trade_ids: frozenset[str]
    entries_complete: bool
    entries_today: tuple[VirtualEntry, ...]
    pending_entries: int
    open_virtual: int
    chain_head: str
    entry_events: dict[str, dict] = field(default_factory=dict)

    @property
    def state(self) -> str:
        if not self.fresh:
            return "stale"
        if self.pending_entries and not self.entries_complete:
            return "pending"
        return "fresh"


def _virtual_entry(event: Mapping[str, Any]) -> VirtualEntry:
    stop = event.get("stop_px")
    return VirtualEntry(
        trade_id=str(event["trade_id"]),
        coin=str(event["coin"]),
        direction=1 if event.get("side") == "long" else -1,
        signal_date=str(event.get("signal_date")),
        entry_date=str(event.get("entry_date")),
        entry_px=float(event["entry_px"]),
        atr_signal=(
            float(event["atr_signal"])
            if event.get("atr_signal") is not None
            else math.nan
        ),
        priority_rank=int(event.get("priority_rank") or 0),
        taken=bool(event.get("taken")),
        skip_reason=event.get("skip_reason"),
        stop_px=float(stop) if stop is not None else None,
        binance_symbol=str(event.get("binance_symbol", "")),
        max_leverage=(
            float(event["max_leverage"])
            if event.get("max_leverage") is not None
            else None
        ),
    )


def build_shadow_view(
    events: Sequence[Mapping[str, Any]], now: datetime, cfg: SleeveConfig
) -> ShadowView:
    """What the shadow says at ``now``: open virtual trades, exits, today's entries."""
    today = (now.astimezone(UTC) - runner.SETTLE_DELAY).date()
    marks = [event for event in events if event.get("event") == "daily_mark"]
    if not marks:
        raise ShadowViewError("the shadow ledger has no daily_mark")
    mark = marks[-1]
    record = mark.get("state") or {}
    fingerprint = record.get("config_fingerprint")
    if fingerprint != cfg.shadow_config_fingerprint:
        raise ShadowConfigMismatch(
            f"shadow config fingerprint {redact(fingerprint, 40)} is not "
            f"{cfg.shadow_config_fingerprint}"
        )
    try:
        state = runner.EngineState.from_record(record)
        mark_date = date.fromisoformat(str(mark["bar_date"]))
    except (runner.LedgerError, KeyError, ValueError) as exc:
        raise ShadowViewError(f"the last daily_mark is unreadable ({exc})") from exc
    open_ids = {trade.trade_id for trade in state.trades.values()}
    pending_exits: dict[str, str] = {}
    for coin, order in state.pending.items():
        trade = state.trades.get(coin)
        if order.exit_direction and trade and trade.direction == order.exit_direction:
            open_ids.discard(trade.trade_id)
            pending_exits[trade.trade_id] = "channel_exit"
    open_day = (mark_date + timedelta(days=1)).isoformat()
    closed_index: dict[str, ClosedVirtual] = {}
    known: set[str] = set()
    entry_events: dict[str, dict] = {}
    open_step_coins: set[str] = set()
    todays: list[VirtualEntry] = []
    for event in events:
        kind = event.get("event")
        if kind == "hypothetical_entry":
            known.add(str(event["trade_id"]))
            entry_events[str(event["trade_id"])] = dict(event)
            if event.get("bar_date") == open_day:
                open_step_coins.add(str(event.get("coin")))
                if event.get("skip_reason") != "invalid_stop":
                    open_ids.add(str(event["trade_id"]))
                    if event.get("mode") == "daily":
                        todays.append(_virtual_entry(event))
        elif kind in ("hypothetical_exit", "hypothetical_stop_hit"):
            trade_id = str(event["trade_id"])
            closed_index[trade_id] = ClosedVirtual(
                trade_id=trade_id,
                exit_reason=str(event.get("exit_reason")),
                exit_px=event.get("exit_px"),
                bar_date=str(event.get("bar_date")),
                net_r=event.get("net_r"),
            )
            if event.get("bar_date") == open_day:
                open_ids.discard(trade_id)
                pending_exits.pop(trade_id, None)
    wanted = {coin for coin, order in state.pending.items() if order.entry_direction}
    complete = wanted <= open_step_coins
    fresh = mark_date == today - timedelta(days=1)
    entries: tuple[VirtualEntry, ...] = ()
    if fresh and complete:
        entries = tuple(sorted(todays, key=lambda e: (e.priority_rank, e.coin)))
    return ShadowView(
        today=today,
        mark_date=mark_date,
        mode=mark.get("mode"),
        fresh=fresh,
        open_ids=frozenset(open_ids),
        pending_exits=pending_exits,
        closed_index=closed_index,
        known_trade_ids=frozenset(known),
        entries_complete=complete,
        entries_today=entries,
        pending_entries=len(wanted),
        open_virtual=len(open_ids),
        chain_head=runner.ledger_chain(events),
        entry_events=entry_events,
    )


# ----------------------------------------------------------------- journal

JOURNAL_GENESIS = hashlib.sha256(f"{SCHEMA}|genesis".encode()).hexdigest()[:32]
_JOURNAL_UNHASHED = frozenset({"recorded_at", "content_digest"})


def journal_digest(event: Mapping[str, Any]) -> str:
    body = {k: v for k, v in event.items() if k not in _JOURNAL_UNHASHED}
    return runner._sha256(runner._canonical(body))[:24]


def journal_step(chain: str, event: Mapping[str, Any]) -> str:
    return runner._sha256(f"{chain}|{event['content_digest']}")[:32]


def journal_chain(events: Iterable[Mapping[str, Any]]) -> str:
    chain = JOURNAL_GENESIS
    for event in events:
        chain = journal_step(chain, event)
    return chain


def make_journal_event(
    run_id: str,
    seq: int,
    kind: str,
    payload: Mapping[str, Any],
    recorded_at: str,
) -> dict:
    if kind not in JOURNAL_EVENTS:
        raise TechnicalError(f"unknown journal event {kind}")
    event = {
        "schema": SCHEMA,
        "event": kind,
        "run_id": run_id,
        "seq": seq,
        "event_id": runner._sha256(f"{SCHEMA}|{run_id}|{seq}")[:24],
        **runner._jsonable(payload),
    }
    event["content_digest"] = journal_digest(event)
    event["recorded_at"] = recorded_at
    return event


def load_journal(path: Path) -> list[dict]:
    """Read and verify: line digests, every run_end's chain, no torn tail."""
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        keep = raw.rfind(b"\n") + 1
        raise JournalError(
            f"the journal's last line is incomplete (a crash mid-append?). Keep a "
            f"copy, truncate the file to {keep} bytes (the end of the last complete "
            "line) and re-run"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JournalError(f"the journal is not UTF-8 ({exc})") from exc
    events: list[dict] = []
    chain = JOURNAL_GENESIS
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JournalError(f"journal line {number} is not valid JSON") from exc
        if not isinstance(event, dict) or event.get("schema") != SCHEMA:
            raise JournalError(f"journal line {number} is not a {SCHEMA} event")
        if event.get("content_digest") != journal_digest(event):
            raise JournalError(
                f"journal line {number} does not match its digest (edited or "
                "corrupted); refusing to continue"
            )
        if (
            event.get("event") == "run_end"
            and event.get("journal_chain_before") != chain
        ):
            raise JournalError(
                f"journal line {number} breaks the chain: an earlier line was "
                "deleted, inserted or reordered; refusing to continue"
            )
        chain = journal_step(chain, event)
        events.append(event)
    return events


def append_journal(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(runner._canonical(event) + "\n" for event in events)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


# An entry whose orderStatus said never_landed (possibly a lagging info node)
# and whose position re-read FAILED: it may have filled, so it owns a
# same-direction position on its coin (pending_opens) until a later run's
# position read settles it.
POSITION_UNVERIFIED = "position_unverified"


@dataclass
class IntentRecord:
    cloid: str
    role: str
    trade_id: str
    coin: str
    n: int
    is_buy: bool
    sz: float
    reduce_only: bool
    expires_after_ms: int | None
    context: dict
    canary: bool
    order: int
    outcome: dict | None = None

    @property
    def status(self) -> str | None:
        return None if self.outcome is None else self.outcome.get("status")

    @property
    def resolved(self) -> bool:
        return self.status not in (None, "ambiguous")

    @property
    def filled(self) -> bool:
        return self.status in ("filled", "partial")

    @property
    def unverified(self) -> bool:
        return self.status == POSITION_UNVERIFIED


@dataclass
class OpenTrade:
    trade_id: str
    coin: str
    direction: int
    sz: float
    entry_px: float
    stop_px: float
    stop_dist: float
    stop_fraction: float
    leverage: int
    risk_usd: float
    entry_date: str
    signal_date: str
    opened_ms: int
    recovered: bool
    virtual: dict
    actual_risk_usd: float = 0.0


@dataclass
class SleeveBook:
    open_trades: dict[str, OpenTrade] = field(default_factory=dict)
    opened_ids: set[str] = field(default_factory=set)
    closed_ids: set[str] = field(default_factory=set)
    attempts: dict[tuple[str, str], int] = field(default_factory=dict)
    terminal_skips: dict[str, str] = field(default_factory=dict)
    last_skip: dict[str, str] = field(default_factory=dict)
    known_oids: dict[int, tuple[str, str]] = field(default_factory=dict)
    intents: dict[str, IntentRecord] = field(default_factory=dict)
    stop_oids: dict[str, set[int]] = field(default_factory=dict)
    canary_open: dict[str, IntentRecord] = field(default_factory=dict)
    # trade_id -> the largest venue size already raised as entry_overfill
    # after the trade opened (position_grew): raised once per new size.
    grown_sz: dict[str, float] = field(default_factory=dict)
    last_identity: dict | None = None
    last_run_start: dict | None = None
    last_run_end: dict | None = None
    open_run_start: dict | None = None
    events_seen: int = 0

    def apply(self, event: Mapping[str, Any]) -> None:
        kind = event.get("event")
        self.events_seen += 1
        if kind == "intent" and event.get("action") == "order":
            record = IntentRecord(
                cloid=str(event["cloid"]),
                role=str(event["role"]),
                trade_id=str(event["trade_id"]),
                coin=str(event["coin"]),
                n=int(event["n"]),
                is_buy=bool(event["is_buy"]),
                sz=float(event["sz"]),
                reduce_only=bool(event["reduce_only"]),
                expires_after_ms=event.get("expires_after_ms"),
                context=dict(event.get("context") or {}),
                canary=event.get("kind") == "canary",
                order=self.events_seen,
            )
            self.intents[record.cloid] = record
            key = (record.trade_id, record.role)
            self.attempts[key] = max(self.attempts.get(key, 0), record.n)
            if record.role == "canary_entry":
                self.canary_open[record.coin] = record
        elif kind == "outcome" and event.get("action") == "order":
            record = self.intents.get(str(event.get("cloid")))
            if record is not None:
                record.outcome = dict(event)
            oid = event.get("oid")
            if oid is not None and record is not None:
                self.known_oids[int(oid)] = (record.trade_id, record.role)
                if record.role in ("stop", "canary_stop"):
                    self.stop_oids.setdefault(record.trade_id, set()).add(int(oid))
        elif kind == "trade_opened":
            trade = OpenTrade(
                trade_id=str(event["trade_id"]),
                coin=str(event["coin"]),
                direction=int(event["direction"]),
                sz=float(event["sz"]),
                entry_px=float(event["entry_px"]),
                stop_px=float(event["stop_px"]),
                stop_dist=float(event["stop_dist"]),
                stop_fraction=float(event.get("stop_fraction") or 0.0),
                leverage=int(event.get("leverage") or 0),
                risk_usd=float(event.get("risk_usd") or 0.0),
                entry_date=str(event.get("entry_date")),
                signal_date=str(event.get("signal_date")),
                opened_ms=int(event.get("opened_ms") or 0),
                recovered=bool(event.get("recovered")),
                virtual=dict(event.get("virtual") or {}),
                actual_risk_usd=float(event.get("actual_risk_usd") or 0.0),
            )
            self.open_trades[trade.coin] = trade
            self.opened_ids.add(trade.trade_id)
        elif kind == "position_grew":
            trade_id = str(event["trade_id"])
            self.grown_sz[trade_id] = max(
                self.grown_sz.get(trade_id, 0.0), float(event["sz"])
            )
        elif kind == "trade_closed":
            trade_id = str(event["trade_id"])
            self.closed_ids.add(trade_id)
            for coin, trade in list(self.open_trades.items()):
                if trade.trade_id == trade_id:
                    del self.open_trades[coin]
        elif kind == "skip":
            trade_id = str(event["trade_id"])
            self.last_skip[trade_id] = str(event["reason"])
            if not event.get("retryable"):
                self.terminal_skips[trade_id] = str(event["reason"])
        elif kind == "stop_placed":
            if event.get("oid") is not None:
                oid = int(event["oid"])
                self.known_oids[oid] = (str(event["trade_id"]), "stop")
                self.stop_oids.setdefault(str(event["trade_id"]), set()).add(oid)
        elif kind == "canary_result":
            if not event.get("residue"):
                self.canary_open.pop(str(event.get("coin")), None)
        elif kind == "identity_verified":
            self.last_identity = dict(event)
        elif kind == "run_start":
            self.last_run_start = dict(event)
            self.open_run_start = dict(event)
        elif kind == "run_end":
            self.last_run_end = dict(event)
            if self.open_run_start and self.open_run_start.get("run_id") == event.get(
                "run_id"
            ):
                self.open_run_start = None

    @property
    def unresolved(self) -> dict[str, IntentRecord]:
        return {c: r for c, r in self.intents.items() if not r.resolved}

    def unresolved_coins(self) -> set[str]:
        return {record.coin for record in self.unresolved.values()}

    def pending_opens(self) -> dict[str, IntentRecord]:
        """Entry intents that filled (or may have) with no trade_opened: recovery."""
        found: dict[str, IntentRecord] = {}
        for record in sorted(self.intents.values(), key=lambda r: r.order):
            if record.role != "entry" or record.canary:
                continue
            if record.trade_id in self.opened_ids or record.trade_id in self.closed_ids:
                continue
            if record.filled or not record.resolved or record.unverified:
                found[record.coin] = record
        return found

    def canary_residue(self) -> dict[str, IntentRecord]:
        """Canary entries that filled (or may have) with no clean canary_result.

        An interrupted canary (process killed after its fill) leaves such a
        position; ``flatten`` adopts it so it can be closed without the UI.
        """
        return {
            coin: record
            for coin, record in self.canary_open.items()
            if record.filled or not record.resolved
        }

    def entry_filled(self, trade_id: str) -> bool:
        return any(
            r.trade_id == trade_id and r.role == "entry" and r.filled
            for r in self.intents.values()
        )

    def sized_entry(self, trade_id: str) -> float | None:
        """The largest size any entry attempt of this trade was sized for."""
        sizes = [
            float(r.context["sizing_sz"])
            for r in self.intents.values()
            if r.trade_id == trade_id
            and r.role == "entry"
            and not r.canary
            and isinstance(r.context.get("sizing_sz"), (int, float))
        ]
        return max(sizes) if sizes else None

    def stop_version(self, trade_id: str) -> int:
        return self.attempts.get((trade_id, "stop"), 0)


def derive_book(events: Iterable[Mapping[str, Any]]) -> SleeveBook:
    book = SleeveBook()
    for event in events:
        book.apply(event)
    return book


# ----------------------------------------------------------------- sizing


@dataclass(frozen=True)
class EntrySizing:
    take: bool
    reason: str | None = None
    retryable: bool = False
    critical: bool = False
    unit: float = 1.0
    ratio: float | None = None
    sz: float = 0.0
    notional: float = 0.0
    leverage: int = 0
    mmr: float = 0.0
    liq_distance: float = 0.0
    buffer_ok: bool = False
    stop_dist: float = 0.0
    stop_fraction: float = 0.0
    want: float = 0.0
    risk_usd: float = 0.0
    rule_stop: float = 0.0
    room: float = 0.0
    scaled: bool = False
    collateral_shortfall_usd: float | None = None


def _skip(reason: str, **values: Any) -> EntrySizing:
    return EntrySizing(
        take=False,
        reason=reason,
        retryable=reason not in TERMINAL_SKIPS,
        critical=reason in CRITICAL_SKIPS,
        **values,
    )


def size_entry(
    entry: VirtualEntry,
    mid: float,
    market: MarketInfo,
    book_equity: float,
    gross_used: float,
    slots_used: int,
    sub_free: float,
    sub_equity: float,
    cfg: SleeveConfig,
) -> EntrySizing:
    """Size one virtual entry against the REAL book (steps in spec order)."""
    d = entry.direction
    unit = price_unit(entry.coin)
    if not (_finite(entry.atr_signal) and entry.atr_signal > 0):
        return _skip("invalid_stop", unit=unit)
    if not (
        _finite(mid) and mid > 0 and _finite(entry.entry_px) and entry.entry_px > 0
    ):
        return _skip("unit_mismatch", unit=unit)
    ratio = mid / (entry.entry_px * unit)
    if not 0.5 <= ratio <= 2.0:
        return _skip("unit_mismatch", unit=unit, ratio=ratio)
    stop_dist = runner.STOP_ATR_MULT * entry.atr_signal * unit
    rule_stop = (entry.entry_px - d * runner.STOP_ATR_MULT * entry.atr_signal) * unit
    base: dict[str, Any] = {
        "unit": unit,
        "ratio": ratio,
        "stop_dist": stop_dist,
        "rule_stop": rule_stop,
    }
    if d * (mid - rule_stop) <= 0:
        return _skip("rule_stop_breached", **base)
    stop_fraction = stop_dist / mid
    leverage, mmr, liq_distance, buffer_ok = runner.leverage_for(
        stop_fraction, market.max_leverage, d
    )
    risk = cfg.risk_fraction * book_equity
    want = risk / stop_fraction
    base.update(
        stop_fraction=stop_fraction,
        leverage=leverage,
        mmr=mmr,
        liq_distance=liq_distance,
        buffer_ok=buffer_ok,
        risk_usd=risk,
        want=want,
    )
    if want > cfg.max_order_to_book * book_equity:
        return _skip("sizing_sanity", **base)
    if slots_used >= cfg.max_slots:
        return _skip("slots_full", **base)
    gross_room = cfg.gross_cap * book_equity - gross_used
    reserve = cfg.collateral_reserve_fraction * sub_equity
    margin_room = (sub_free - reserve) * leverage
    room = min(want, gross_room, margin_room)
    if room < cfg.min_fill_fraction * want:
        if gross_room <= margin_room:
            return _skip("gross_cap", room=room, **base)
        shortfall = want / leverage - (sub_free - reserve)
        return _skip(
            "sub_collateral", room=room, collateral_shortfall_usd=shortfall, **base
        )
    try:
        sz = round_size_down(room / mid, market.sz_decimals)
    except TechnicalError:
        return _skip("below_min_notional", room=room, **base)
    if sz * min(mid, mid - d * stop_dist) < cfg.min_order_usd:
        return _skip("below_min_notional", room=room, sz=sz, **base)
    return EntrySizing(
        take=True,
        sz=sz,
        notional=sz * mid,
        room=room,
        scaled=room < want,
        **base,
    )


# ----------------------------------------------------------------- planning


@dataclass(frozen=True)
class ExitDecision:
    action: str  # hold | close | unknown
    reason: str | None = None
    expected_date: date | None = None
    virtual: dict | None = None


def plan_exit(trade_id: str, view: ShadowView) -> ExitDecision:
    """Follow the shadow: hold while the virtual trade is open, close once it is not."""
    if trade_id in view.open_ids:
        return ExitDecision("hold")
    if trade_id in view.pending_exits:
        return ExitDecision(
            "close",
            view.pending_exits[trade_id],
            expected_date=view.mark_date + timedelta(days=1),
            virtual={"exit_reason": "channel_exit", "exit_px": None, "net_r": None},
        )
    closed = view.closed_index.get(trade_id)
    if closed is not None:
        reason = SHADOW_EXIT_REASONS.get(closed.exit_reason, closed.exit_reason)
        expected = date.fromisoformat(closed.bar_date)
        if closed.exit_reason == "stop_intrabar":
            # Known only after the bar closes: the next day's first run acts.
            expected += timedelta(days=1)
        return ExitDecision(
            "close",
            reason,
            expected_date=expected,
            virtual={
                "exit_reason": closed.exit_reason,
                "exit_px": closed.exit_px,
                "net_r": closed.net_r,
            },
        )
    return ExitDecision("unknown", "trade_unknown_to_shadow")


@dataclass(frozen=True)
class ProtectionPlan:
    action: str  # ok | place | breach
    expected_px: float
    size: float
    is_buy: bool
    keep: VenueOrder | None
    cancel: tuple[VenueOrder, ...]


def plan_protection(
    position: VenuePosition,
    stop_px: float,
    owned_orders: Sequence[VenueOrder],
    mid: float | None,
    market: MarketInfo,
) -> ProtectionPlan:
    """I6: exactly one resting reduce-only market stop, opposite side, |szi|, journal price."""
    d = position.direction
    szd = market.sz_decimals
    expected = normalize_price(stop_px, szd)
    is_buy = position.szi < 0
    on_coin = [order for order in owned_orders if order.coin == position.coin]
    good = [
        order
        for order in on_coin
        if order.is_trigger
        and order.reduce_only
        and order.order_type in STOP_ORDER_TYPES
        and order.is_buy == is_buy
        and prices_equal(order.trigger_px, expected)
        and sizes_equal(order.sz, position.size, szd)
    ]
    if good:
        keep = min(good, key=lambda order: order.oid)
        others = tuple(order for order in on_coin if order.oid != keep.oid)
        return ProtectionPlan("ok", expected, position.size, is_buy, keep, others)
    if mid is not None and d * (mid - expected) <= 0:
        return ProtectionPlan("breach", expected, position.size, is_buy, None, ())
    return ProtectionPlan(
        "place", expected, position.size, is_buy, None, tuple(on_coin)
    )


def plan_flat_cancels(
    positions: Mapping[str, VenuePosition], owned_orders: Sequence[VenueOrder]
) -> list[VenueOrder]:
    return [order for order in owned_orders if order.coin not in positions]


def stop_covers(
    position: VenuePosition, orders: Sequence[VenueOrder], sz_decimals: int
) -> bool:
    """A2 coverage: one resting reduce-only stop trigger (not a take-profit)
    on the closing side closes the whole position, whoever placed it."""
    half_lot = 0.5 * 10.0**-sz_decimals
    is_buy = position.szi < 0
    return any(
        order.coin == position.coin
        and order.is_trigger
        and order.reduce_only
        and order.is_buy == is_buy
        and "take profit" not in order.order_type.lower()
        and order.sz >= position.size - half_lot
        for order in orders
    )


def guard_stop_px(
    position: VenuePosition,
    mark: float | None,
    desired: float,
    dist: float,
    sz_decimals: int,
) -> float | None:
    """A2: the trigger of a protective stop for ``position``.

    ``desired`` (the rule stop, or entry -/+ ``dist``) is moved to mark -/+
    ``dist`` when the mark is already at or beyond it, so the stop rests on
    the protective side of the mark, and to GUARD_LIQ_FRACTION of the way
    from the liquidation price back to the mark when it would sit at or
    beyond the liquidation price, so it fires first. None when no such
    price exists (the mark at or beyond the liquidation price)."""
    d = position.direction
    ref = mark if mark is not None and _finite(mark) and mark > 0 else None
    px = float(desired)
    if ref is not None and d * (ref - px) <= 0:
        px = ref - d * float(dist)
    liq = position.liquidation_px
    if liq is not None and d * (px - liq) <= 0:
        base = ref if ref is not None else position.entry_px
        px = liq + d * GUARD_LIQ_FRACTION * abs(base - liq)
    if not _finite(px) or px <= 0:
        return None
    px = normalize_price(px, sz_decimals)
    if px <= 0 or (ref is not None and d * (ref - px) <= 0):
        return None
    if liq is not None and d * (px - liq) <= 0:
        return None
    return px


def late_exit_days(decision: ExitDecision, today: date) -> int:
    if decision.expected_date is None:
        return 0
    return max(0, (today - decision.expected_date).days)


def utc_now_iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")
