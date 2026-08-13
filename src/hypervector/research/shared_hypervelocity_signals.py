"""Canonical Hypervelocity eligibility for continuous shared-account replay."""

from __future__ import annotations

import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig
from hypervector.strategies.hypervelocity_contract import faithful_regime_config


def hypervelocity_portfolio_config(
    *,
    margin_fraction: float = 0.70,
    leverage: float = 40.0,
    target_margin_pct: float = 8.0,
) -> SharedPortfolioConfig:
    """Return the faithful $15k maker-only Hypervelocity replay contract."""
    return SharedPortfolioConfig(
        initial_equity=15_000.0,
        margin_fraction=margin_fraction,
        leverage=leverage,
        venue_max_leverage=40.0,
        target_margin_pct=target_margin_pct,
        stop_margin_pct=None,
        entry_fee_rate=0.00015,
        target_fee_rate=0.00015,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=0.0,
        market_exit_slippage_bps=2.0,
        max_hold_bars=None,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=True,
        close_on_opposite_signal=False,
        reverse_on_opposite_signal=False,
    )


def build_hypervelocity_event_signals(
    bars: pd.DataFrame,
    *,
    regime_config: RegimeClassifierConfig | None = None,
) -> pd.DataFrame:
    """Expose eligible regimes while the simulator enforces reset-only reentry."""
    decisions = classify_multitimeframe(
        bars,
        config=regime_config or faithful_regime_config(),
    )
    if "entry_direction" not in decisions:
        raise ValueError("Hypervelocity decisions require entry_direction")
    direction = decisions["entry_direction"].astype(object)
    invalid = direction.dropna().loc[~direction.dropna().isin(("long", "short"))]
    if not invalid.empty:
        raise ValueError(
            "Hypervelocity entry direction must be long, short, or missing"
        )
    inactive = pd.Series(False, index=bars.index, dtype=bool)
    return pd.DataFrame(
        {
            "long_entry": direction.eq("long"),
            "short_entry": direction.eq("short"),
            "long_exit": inactive,
            "short_exit": inactive,
            "long_signal_name": "hypervelocity_control_long",
            "short_signal_name": "hypervelocity_control_short",
        },
        index=bars.index,
    )
