"""Execution cost model for Hyperliquid research realism (fees, slippage, hourly funding).

Hyperliquid perp fee schedule by 14-day volume tier (taker / maker; from the
published schedule, re-verify tier details before relying on them):
  - Tier 0 (base, < $5M):  4.5 bps / 1.5 bps; 4.32 bps taker with the 4% referral discount
  - Tier 1 (> $5M):        4.0 bps / 1.2 bps
  - Tier 2 (> $25M):       3.5 bps / 0.8 bps
  - Tier 3 (> $100M):      3.0 bps / 0.4 bps
  - Tiers 4-6 (> $500M):   2.8 / 2.6 / 2.4 bps taker, 0 maker
  - Funding: paid HOURLY (60m periods), not 8h
  - Slippage: 1.0-1.5 bps for top-of-book small size; 2.0-5.0 bps for large size

A ~$5K account pays the base tier. The preset names ``hl_vip1_taker`` and
``hl_vip2_taker`` (and the legacy aliases ``hl_taker_default`` /
``hl_taker_tight``) are historical labels for the 3.5 bps (tier 2) and 2.5 bps
(roughly tiers 5-6) schedules; they are not the base rate. The research
default everywhere is ``hl_base_taker``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CostModel:
    """Per-side and holding costs applied in VectorBT research runs."""

    # Taker fee fraction (0.00045 = 4.5 bps base)
    taker_fee: float = 0.00045
    # Maker fee fraction (0.00015 = 1.5 bps base)
    maker_fee: float = 0.00015
    # Adverse fill slippage in basis points (2.0 bps per side default)
    slippage_bps: float = 2.0
    # Hourly funding rate on notional (0.0000125 = 0.125 bps/hour, ~3.0 bps/day default)
    funding_rate_1h: float = 0.0000125
    # Backward compatibility 8h funding rate parameter
    funding_rate_8h: float | None = None
    # Hyperliquid funding period is 1 hour (60 minutes)
    minutes_per_funding: float = 60.0

    def __post_init__(self) -> None:
        if self.funding_rate_8h is not None:
            object.__setattr__(self, "funding_rate_1h", self.funding_rate_8h / 8.0)

    @property
    def slippage(self) -> float:
        return self.slippage_bps / 10_000.0

    @property
    def fees(self) -> float:
        """VectorBT fees= is fraction of trade value per side."""
        return float(self.taker_fee)

    def funding_cost(
        self,
        notional: float,
        hold_minutes: float,
    ) -> float:
        """Absolute funding cost for holding position (paid hourly on Hyperliquid)."""
        if notional <= 0 or hold_minutes <= 0:
            return 0.0
        periods = hold_minutes / self.minutes_per_funding
        return abs(notional) * abs(self.funding_rate_1h) * periods

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["slippage_frac"] = self.slippage
        return d


# Official Hyperliquid Presets
HL_BASE_TAKER = CostModel(
    taker_fee=0.00045,  # 4.5 bps base taker
    slippage_bps=2.0,
    funding_rate_1h=0.0000125,
)

HL_REFERRED_TAKER = CostModel(
    taker_fee=0.000432,  # 4.32 bps (4% referral discount)
    slippage_bps=2.0,
    funding_rate_1h=0.0000125,
)

HL_VIP1_TAKER = CostModel(
    taker_fee=0.00035,  # 3.5 bps: volume tier 2 (> $25M / 14d), not base
    slippage_bps=1.5,
    funding_rate_1h=0.0000125,
)

HL_VIP2_TAKER = CostModel(
    taker_fee=0.00025,  # 2.5 bps: roughly tiers 5-6 (> $2B / 14d)
    slippage_bps=1.0,
    funding_rate_1h=0.0000125,
)

# All-maker approximation: every fill (stops and liquidations included) pays
# 1.5 bps with no slippage. Optimistic for anything that exits by stop.
HL_MAKER = CostModel(
    taker_fee=0.00015,  # 1.5 bps base maker
    slippage_bps=0.0,  # Passive fill on book
    funding_rate_1h=0.0000125,
)

ZERO_COST = CostModel(taker_fee=0.0, slippage_bps=0.0, funding_rate_1h=0.0)


COST_MODEL_NAMES: tuple[str, ...] = (
    "hl_base_taker",
    "hl_referred_taker",
    "hl_vip1_taker",
    "hl_vip2_taker",
    "hl_maker",
    "zero",
)
COST_MODEL_ALIASES: dict[str, str] = {
    "base": "hl_base_taker",
    "default": "hl_base_taker",
    "hl": "hl_base_taker",
    "referred": "hl_referred_taker",
    "ref": "hl_referred_taker",
    "vip1": "hl_vip1_taker",
    "hl_taker_default": "hl_vip1_taker",
    "vip2": "hl_vip2_taker",
    "hl_taker_tight": "hl_vip2_taker",
    "tight": "hl_vip2_taker",
    "maker": "hl_maker",
    "none": "zero",
    "off": "zero",
}
_COST_MODELS: dict[str, CostModel] = {
    "hl_base_taker": HL_BASE_TAKER,
    "hl_referred_taker": HL_REFERRED_TAKER,
    "hl_vip1_taker": HL_VIP1_TAKER,
    "hl_vip2_taker": HL_VIP2_TAKER,
    "hl_maker": HL_MAKER,
    "zero": ZERO_COST,
}
DEFAULT_COST_MODEL = "hl_base_taker"
COST_MODEL_DESCRIPTIONS: dict[str, str] = {
    "hl_base_taker": "4.5 bps taker + 2.0 bps slippage: Hyperliquid base tier (< $5M / 14d)",
    "hl_referred_taker": "4.32 bps taker + 2.0 bps slippage: base tier with 4% referral discount",
    "hl_vip1_taker": "3.5 bps taker + 1.5 bps slippage: volume tier 2 (> $25M / 14d), not the base rate",
    "hl_vip2_taker": "2.5 bps taker + 1.0 bps slippage: roughly volume tiers 5-6 (> $2B / 14d)",
    "hl_maker": "1.5 bps on every fill, no slippage: all-maker approximation (stops too)",
    "zero": "no fees, slippage or funding: diagnostic only",
}
# Aliases whose names suggest something other than what they resolve to. They
# keep resolving as before so historical labels stay truthful.
LEGACY_COST_MODEL_ALIASES: dict[str, str] = {
    "hl_taker_default": "legacy alias for hl_vip1_taker (3.5 bps, tier 2), not the base rate",
    "hl_taker_tight": "legacy alias for hl_vip2_taker (2.5 bps), not the base rate",
}


def canonical_cost_model_name(name: str | None = DEFAULT_COST_MODEL) -> str:
    """Canonical preset name for ``name`` or an alias; unknown names are a ValueError."""
    key = (name or DEFAULT_COST_MODEL).lower().strip().replace("-", "_")
    key = COST_MODEL_ALIASES.get(key, key)
    if key not in _COST_MODELS:
        raise ValueError(
            f"unknown fee model {name!r}; choose one of {', '.join(COST_MODEL_NAMES)}"
        )
    return key


def resolve_cost_model(name: str = DEFAULT_COST_MODEL) -> CostModel:
    """Return a named preset (or alias); unknown names are a ValueError."""
    return _COST_MODELS[canonical_cost_model_name(name)]
