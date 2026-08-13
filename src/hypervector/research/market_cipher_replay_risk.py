"""Pricing, stop, margin, and liquidation mechanics for Cipher replay."""

from __future__ import annotations

from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPosition,
    maintenance_rate_for_max_leverage,
)
from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayConfig,
)
from hypervector.research.market_cipher_replay_state import (
    ReplayCandidate,
    ReplayOpenPosition,
)
from hypervector.research.shared_portfolio_models import Direction


def adverse_price(
    price: float,
    direction: Direction,
    config: MarketCipherReplayConfig,
    *,
    entering: bool,
) -> float:
    """Apply configured slippage only in the adverse direction."""
    bps = config.entry_slippage_bps if entering else config.market_exit_slippage_bps
    higher = (direction == "long") == entering
    multiplier = 1.0 + bps / 10_000.0 if higher else 1.0 - bps / 10_000.0
    return price * multiplier


def candidate_entry_price(
    candidate: ReplayCandidate, config: MarketCipherReplayConfig
) -> float:
    """Return the next-bar open with adverse entry slippage."""
    if candidate.entry_price_override is not None:
        return candidate.entry_price_override
    return adverse_price(
        candidate.entry_open, candidate.direction, config, entering=True
    )


def candidate_stop_terms(
    candidate: ReplayCandidate,
    entry: float,
    config: MarketCipherReplayConfig,
) -> tuple[float, float]:
    """Clip the adverse wick anchor into the frozen 20–50 bps interval."""
    direction = candidate.direction
    raw_bps = abs(candidate.stop_anchor - entry) / entry * 10_000.0
    if not stop_anchor_is_adverse(candidate, entry):
        raise ValueError("stop anchor must be adverse to entry direction")
    distance = min(max(raw_bps, config.minimum_stop_bps), config.maximum_stop_bps)
    if direction == "long":
        return entry * (1.0 - distance / 10_000.0), distance
    return entry * (1.0 + distance / 10_000.0), distance


def stop_anchor_is_adverse(candidate: ReplayCandidate, entry: float) -> bool:
    """Return whether the structural anchor remains beyond next-bar entry."""
    if candidate.direction == "long":
        return candidate.stop_anchor < entry
    return candidate.stop_anchor > entry


def remaining_margin(opened: ReplayOpenPosition) -> float:
    """Return pro-rata isolated margin retained by remaining quantity."""
    fraction = opened.remaining_quantity / opened.initial_quantity
    return opened.initial_margin * fraction


def position_liquidation_price(
    opened: ReplayOpenPosition, config: MarketCipherReplayConfig
) -> float:
    """Return the modeled isolated maintenance boundary."""
    fraction = opened.remaining_quantity / opened.initial_quantity
    position = IsolatedMarginPosition(
        symbol=opened.candidate.symbol,
        side=opened.candidate.direction,
        quantity=opened.remaining_quantity,
        entry_price=opened.entry_price,
        isolated_margin=opened.initial_margin * fraction,
        maintenance_rate=maintenance_rate_for_max_leverage(
            config.venue_max_leverage_for(opened.candidate.symbol)
        ),
        fees_paid_usd=opened.entry_fee * fraction,
        funding_net_usd=opened.funding_open_basis,
    )
    return position.liquidation_price()


def gap_adverse_price(direction: Direction, barrier: float, bar_open: float) -> float:
    """Prevent a stop or liquidation fill from improving through a gap."""
    return min(barrier, bar_open) if direction == "long" else max(barrier, bar_open)
