"""Read-only Hyperliquid portfolio valuation without execution authority."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import math
from typing import Protocol

from hypervector.live.hyperliquid_parsing import validate_address

_USDC_TOKEN_INDEX = 0
_USDC_SYMBOL = "USDC"


class HyperliquidPortfolioValueError(RuntimeError):
    """Venue portfolio inputs cannot produce one complete USD valuation."""


class HyperliquidPortfolioInfoProtocol(Protocol):
    """Execution-incapable Info API methods required for portfolio telemetry."""

    def spot_user_state(self, address: str) -> object:
        """Return the account's unified spot balances."""
        ...

    def spot_meta(self) -> object:
        """Return token identities and spot market mappings."""
        ...

    def all_mids(self, dex: str = "") -> object:
        """Return current perpetual and spot midpoints."""
        ...

    def user_vault_equities(self, address: str) -> object:
        """Return current equity delegated to vaults."""
        ...


@dataclass(frozen=True)
class ValuedSpotAsset:
    """One positive unified spot balance marked against USDC."""

    symbol: str
    token_index: int
    total: float
    price_usd: float
    value_usd: float
    market: str

    def as_payload(self) -> dict[str, object]:
        """Return a secret-free JSON representation."""
        return {
            "symbol": self.symbol,
            "token_index": self.token_index,
            "total": self.total,
            "price_usd": self.price_usd,
            "value_usd": self.value_usd,
            "market": self.market,
        }


@dataclass(frozen=True)
class HyperliquidPortfolioValue:
    """Current portfolio value separated from USDC execution collateral."""

    portfolio_value_usd: float
    execution_collateral_value_usd: float
    non_usdc_spot_value_usd: float
    vault_equity_usd: float
    valued_spot_assets: tuple[ValuedSpotAsset, ...]
    observed_at_utc: str
    valuation_source: str = "spot_midpoints_plus_vault_equity"

    def as_payload(self) -> dict[str, object]:
        """Return a strict report-only checkpoint payload."""
        return {
            "status": "observed",
            "portfolio_value_usd": self.portfolio_value_usd,
            "execution_collateral_value_usd": self.execution_collateral_value_usd,
            "non_usdc_spot_value_usd": self.non_usdc_spot_value_usd,
            "vault_equity_usd": self.vault_equity_usd,
            "valued_spot_assets": [
                asset.as_payload() for asset in self.valued_spot_assets
            ],
            "observed_at_utc": self.observed_at_utc,
            "valuation_source": self.valuation_source,
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "execution_collateral_unchanged": True,
            },
        }


class HyperliquidPortfolioValueReader:
    """Value every positive spot balance and vault deposit using public reads."""

    def __init__(
        self,
        *,
        info: HyperliquidPortfolioInfoProtocol,
        account_address: str,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._info = info
        self._address = validate_address(account_address)
        self._now_fn = now_fn or (lambda: datetime.now(UTC))
        self._spot_meta: Mapping[str, object] | None = None

    def snapshot(self) -> HyperliquidPortfolioValue:
        """Return one complete point-in-time portfolio valuation."""
        meta = self._metadata()
        mids = _mapping(self._info.all_mids(), "all mids")
        state = _mapping(self._info.spot_user_state(self._address), "spot state")
        balances = _sequence(state.get("balances"), "spot balances")
        assets = _value_balances(balances, meta, mids)
        collateral = _execution_collateral(assets)
        non_usdc = sum(
            asset.value_usd
            for asset in assets
            if asset.token_index != _USDC_TOKEN_INDEX
        )
        vault_equity = _vault_equity(self._info.user_vault_equities(self._address))
        observed_at = self._now_fn()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise HyperliquidPortfolioValueError(
                "portfolio clock must be timezone-aware"
            )
        return HyperliquidPortfolioValue(
            portfolio_value_usd=collateral + non_usdc + vault_equity,
            execution_collateral_value_usd=collateral,
            non_usdc_spot_value_usd=non_usdc,
            vault_equity_usd=vault_equity,
            valued_spot_assets=assets,
            observed_at_utc=observed_at.isoformat(),
        )

    def _metadata(self) -> Mapping[str, object]:
        if self._spot_meta is None:
            self._spot_meta = _mapping(self._info.spot_meta(), "spot metadata")
        return self._spot_meta


def _value_balances(
    raw_balances: Sequence[object],
    meta: Mapping[str, object],
    mids: Mapping[str, object],
) -> tuple[ValuedSpotAsset, ...]:
    token_names = _token_names(meta)
    direct_markets = _direct_usdc_markets(meta)
    assets: list[ValuedSpotAsset] = []
    seen: set[int] = set()
    for raw in raw_balances:
        balance = _mapping(raw, "spot balance")
        token_index = _integer(balance.get("token"), "spot token index")
        if token_index in seen:
            raise HyperliquidPortfolioValueError(
                "spot balances contain duplicate token index"
            )
        seen.add(token_index)
        symbol = _text(balance.get("coin"), "spot balance coin")
        if token_names.get(token_index) != symbol:
            raise HyperliquidPortfolioValueError(
                "spot balance coin disagrees with token metadata"
            )
        total = _nonnegative(balance.get("total"), f"{symbol} total")
        if total == 0.0:
            continue
        market, price = _market_price(token_index, symbol, direct_markets, mids)
        assets.append(
            ValuedSpotAsset(symbol, token_index, total, price, total * price, market)
        )
    return tuple(assets)


def _token_names(meta: Mapping[str, object]) -> dict[int, str]:
    result: dict[int, str] = {}
    for raw in _sequence(meta.get("tokens"), "spot tokens"):
        token = _mapping(raw, "spot token")
        index = _integer(token.get("index"), "spot token index")
        if index in result:
            raise HyperliquidPortfolioValueError(
                "spot metadata has duplicate token index"
            )
        result[index] = _text(token.get("name"), "spot token name")
    return result


def _direct_usdc_markets(meta: Mapping[str, object]) -> dict[int, str]:
    result: dict[int, str] = {}
    for raw in _sequence(meta.get("universe"), "spot universe"):
        market = _mapping(raw, "spot market")
        tokens = _sequence(market.get("tokens"), "spot market tokens")
        if len(tokens) != 2:
            raise HyperliquidPortfolioValueError("spot market must contain two tokens")
        base = _integer(tokens[0], "spot base token")
        quote = _integer(tokens[1], "spot quote token")
        if quote != _USDC_TOKEN_INDEX:
            continue
        if base in result:
            raise HyperliquidPortfolioValueError(
                "spot token has duplicate USDC markets"
            )
        result[base] = _text(market.get("name"), "spot market name")
    return result


def _market_price(
    token_index: int,
    symbol: str,
    markets: Mapping[int, str],
    mids: Mapping[str, object],
) -> tuple[str, float]:
    if token_index == _USDC_TOKEN_INDEX:
        if symbol != _USDC_SYMBOL:
            raise HyperliquidPortfolioValueError("token zero must be USDC")
        return "USDC_PAR", 1.0
    market = markets.get(token_index)
    if market is None:
        raise HyperliquidPortfolioValueError(
            f"positive {symbol} balance has no direct USDC market"
        )
    return market, _positive(mids.get(market), f"{market} midpoint")


def _execution_collateral(assets: Sequence[ValuedSpotAsset]) -> float:
    matches = [asset for asset in assets if asset.token_index == _USDC_TOKEN_INDEX]
    if len(matches) != 1:
        raise HyperliquidPortfolioValueError(
            "portfolio valuation requires exactly one positive USDC balance"
        )
    return matches[0].value_usd


def _vault_equity(value: object) -> float:
    return sum(
        _nonnegative(_mapping(raw, "vault equity").get("equity"), "vault equity")
        for raw in _sequence(value, "vault equities")
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HyperliquidPortfolioValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise HyperliquidPortfolioValueError(f"{label} must be an array")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HyperliquidPortfolioValueError(f"{label} must be non-empty text")
    return value.strip()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise HyperliquidPortfolioValueError(f"{label} must be finite")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise HyperliquidPortfolioValueError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise HyperliquidPortfolioValueError(f"{label} must be finite")
    return number


def _nonnegative(value: object, label: str) -> float:
    number = _number(value, label)
    if number < 0.0:
        raise HyperliquidPortfolioValueError(f"{label} must be nonnegative")
    return number


def _positive(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise HyperliquidPortfolioValueError(f"{label} must be positive")
    return number


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HyperliquidPortfolioValueError(f"{label} must be a nonnegative integer")
    return value
