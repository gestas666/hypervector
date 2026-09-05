"""Backward-compatible HYPE names for generic funding-exhaustion signals."""

from __future__ import annotations

import pandas as pd

from hypervector.research.funding_price_exhaustion_signals import (
    FundingPriceExhaustionConfig,
    FundingPriceExhaustionSignals,
    build_funding_price_exhaustion_signals,
)

HypeFundingExhaustionConfig = FundingPriceExhaustionConfig
HypeFundingExhaustionSignals = FundingPriceExhaustionSignals


def build_hype_funding_exhaustion_signals(
    bars: pd.DataFrame,
    funding: pd.DataFrame,
    config: FundingPriceExhaustionConfig | None = None,
) -> FundingPriceExhaustionSignals:
    """Build the frozen HYPE signal through the shared asset-generic contract."""
    return build_funding_price_exhaustion_signals(bars, funding, config)
