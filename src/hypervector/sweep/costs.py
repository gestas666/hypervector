"""Execution cost model for research realism (fees, slippage, funding).

HL-oriented defaults — approximate public taker + small slippage.
Full margin/liquidation realism is Phase 2 (Nautilus).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CostModel:
    """Per-side and holding costs applied in VectorBT research runs."""

    # Hyperliquid-ish taker (tune in config); applied each entry/exit
    taker_fee: float = 0.00035  # 3.5 bps
    # Adverse fill model: fraction of price (bps → fraction)
    slippage_bps: float = 2.0  # 2 bps per side
    # Perp funding: charged every 8h on notional; sign ignored (cost of carry)
    funding_rate_8h: float = 0.0001  # 1 bp / 8h default placeholder
    minutes_per_funding: float = 8 * 60  # 480

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
        """Absolute funding cost (always a drag in research estimate)."""
        if notional <= 0 or hold_minutes <= 0:
            return 0.0
        periods = hold_minutes / self.minutes_per_funding
        return abs(notional) * abs(self.funding_rate_8h) * periods

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["slippage_frac"] = self.slippage
        return d


# Named presets
HL_TAKER_DEFAULT = CostModel()
HL_TAKER_TIGHT = CostModel(taker_fee=0.00025, slippage_bps=1.0, funding_rate_8h=0.00005)
ZERO_COST = CostModel(taker_fee=0.0, slippage_bps=0.0, funding_rate_8h=0.0)


def resolve_cost_model(name: str = "hl_taker_default") -> CostModel:
    key = (name or "hl_taker_default").lower().strip()
    if key in ("hl_taker_default", "default", "hl"):
        return HL_TAKER_DEFAULT
    if key in ("hl_taker_tight", "tight"):
        return HL_TAKER_TIGHT
    if key in ("zero", "none", "off"):
        return ZERO_COST
    return HL_TAKER_DEFAULT
