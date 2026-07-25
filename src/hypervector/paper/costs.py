"""Hybrid paper costs: HL fee tiers (config) + live signed hourly funding."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests

from hypervector.data.hl import HL_INFO_URL, hl_coin

# Official Hyperliquid perp base schedule (Tier 0) and volume tiers (fractions).
# Source: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees
HL_PERP_FEE_TIERS: dict[int, tuple[float, float]] = {
    0: (0.00045, 0.00015),
    1: (0.00040, 0.00012),  # >5M 14d weighted
    2: (0.00035, 0.00008),  # >25M
    3: (0.00030, 0.00004),  # >100M
    4: (0.00028, 0.00000),  # >500M
    5: (0.00026, 0.00000),  # >2B
    6: (0.00024, 0.00000),  # >7B
}

FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1 = "bar_close_slippage_v1"


def fees_for_tier(tier: int) -> tuple[float, float]:
    if tier not in HL_PERP_FEE_TIERS:
        raise ValueError(f"unknown fee_tier={tier}; known={sorted(HL_PERP_FEE_TIERS)}")
    return HL_PERP_FEE_TIERS[tier]


def funding_payment(
    *,
    position_qty: float,
    oracle_px: float,
    funding_rate_hourly: float,
    hours: float = 1.0,
) -> float:
    """Signed funding cashflow for the position holder.

    Positive return = cash paid by the position (drag for that side).
    HL: payment ≈ position_size * oracle_price * funding_rate (hourly).
    """
    return float(position_qty) * float(oracle_px) * float(funding_rate_hourly) * float(hours)


@dataclass(frozen=True)
class CostSnapshot:
    taker_fee: float
    maker_fee: float
    slippage_bps: float
    funding_rate_hourly: float
    fee_tier: int
    fill_model_id: str
    asof_ts: str
    sources: dict[str, str] = field(default_factory=dict)

    def trade_fee_rate(self, *, assume_taker: bool = True) -> float:
        return self.taker_fee if assume_taker else self.maker_fee


@dataclass(frozen=True)
class HyperliquidMarketState:
    """Public venue contract fields required by the shadow backend."""

    coin: str
    size_decimals: int
    max_leverage: float
    funding_rate_hourly: float
    oracle_px: float


class CostProvider:
    def __init__(
        self,
        *,
        fee_tier: int = 0,
        slippage_bps: float = 2.0,
        fill_model_id: str = FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1,
        assume_taker: bool = True,
        funding_poll_secs: float = 60.0,
        funding_rate_hourly: float = 0.0,
    ) -> None:
        self.fee_tier = int(fee_tier)
        self.slippage_bps = float(slippage_bps)
        self.fill_model_id = str(fill_model_id)
        self.assume_taker = bool(assume_taker)
        self.funding_poll_secs = float(funding_poll_secs)
        self._funding_rate_hourly = float(funding_rate_hourly)
        self._taker, self._maker = fees_for_tier(self.fee_tier)

    def trade_fee_rate(self) -> float:
        return self._taker if self.assume_taker else self._maker

    def snapshot(self) -> CostSnapshot:
        now = datetime.now(timezone.utc).isoformat()
        return CostSnapshot(
            taker_fee=self._taker,
            maker_fee=self._maker,
            slippage_bps=self.slippage_bps,
            funding_rate_hourly=self._funding_rate_hourly,
            fee_tier=self.fee_tier,
            fill_model_id=self.fill_model_id,
            asof_ts=now,
            sources={
                "fees": "config_tier",
                "slippage": "config",
                "funding": "live_or_last" if self._funding_rate_hourly else "unset",
            },
        )

    def refresh_funding(
        self,
        coin: str,
        *,
        session: requests.Session | None = None,
    ) -> float:
        """Pull hourly funding for coin from public metaAndAssetCtxs."""
        return self.refresh_market_state(coin, session=session).funding_rate_hourly

    def refresh_market_state(
        self,
        coin: str,
        *,
        session: requests.Session | None = None,
    ) -> HyperliquidMarketState:
        """Pull current public instrument metadata and funding from Hyperliquid."""
        sess = session or requests.Session()
        resp = sess.post(
            HL_INFO_URL,
            json={"type": "metaAndAssetCtxs"},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        meta, ctxs = payload[0], payload[1]
        universe = meta.get("universe") or []
        name = hl_coin(coin)
        idx = next(i for i, u in enumerate(universe) if u.get("name") == name)
        instrument = universe[idx]
        context = ctxs[idx]
        rate = float(context["funding"])
        self._funding_rate_hourly = rate
        return HyperliquidMarketState(
            coin=name,
            size_decimals=int(instrument["szDecimals"]),
            max_leverage=float(instrument["maxLeverage"]),
            funding_rate_hourly=rate,
            oracle_px=float(context["oraclePx"]),
        )
