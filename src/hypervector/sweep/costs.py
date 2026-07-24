"""Execution cost model for Hyperliquid research realism (fees, slippage, hourly funding).

Hyperliquid Perp Fee & Funding Schedule (2026):
  - Base Taker Fee: 4.5 bps (0.00045); 4.32 bps (0.000432) with 4% referral discount
  - VIP 1 Taker Fee: 3.5 bps (0.00035)
  - VIP 2 Taker Fee: 2.5 bps (0.00025)
  - Base Maker Fee: 1.5 bps (0.00015) down to 0.0 bps / rebate
  - Funding: Paid HOURLY (60m periods), not 8h
  - Slippage: 1.0-1.5 bps for top-of-book small size; 2.0-5.0 bps for large size
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
    # Hourly funding rate on notional (0.0000125 = 1.25 bps / day default)
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
    taker_fee=0.00035,  # 3.5 bps VIP 1
    slippage_bps=1.5,
    funding_rate_1h=0.0000125,
)

HL_VIP2_TAKER = CostModel(
    taker_fee=0.00025,  # 2.5 bps VIP 2
    slippage_bps=1.0,
    funding_rate_1h=0.0000125,
)

HL_MAKER = CostModel(
    taker_fee=0.00015,  # 1.5 bps base maker
    slippage_bps=0.0,   # Passive fill on book
    funding_rate_1h=0.0000125,
)

ZERO_COST = CostModel(taker_fee=0.0, slippage_bps=0.0, funding_rate_1h=0.0)


def resolve_cost_model(name: str = "hl_base_taker") -> CostModel:
    key = (name or "hl_base_taker").lower().strip().replace("-", "_")
    if key in ("hl_base_taker", "base", "default", "hl"):
        return HL_BASE_TAKER
    if key in ("hl_referred_taker", "referred", "ref"):
        return HL_REFERRED_TAKER
    if key in ("hl_vip1_taker", "vip1", "hl_taker_default"):
        return HL_VIP1_TAKER
    if key in ("hl_vip2_taker", "vip2", "hl_taker_tight", "tight"):
        return HL_VIP2_TAKER
    if key in ("hl_maker", "maker"):
        return HL_MAKER
    if key in ("zero", "none", "off"):
        return ZERO_COST
    return HL_BASE_TAKER
