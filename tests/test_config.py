"""Lookback and research config (SRS_HV1_HIST_*)."""

from __future__ import annotations

import pytest

from hypervector.config import (
    DEFAULT_LOOKBACK,
    FLOOR_LOOKBACK,
    PROMO_LOOKBACK,
    ResearchConfig,
    validate_lookback,
)


def test_lookback_constants():
    assert FLOOR_LOOKBACK == 30
    assert DEFAULT_LOOKBACK == 90
    assert PROMO_LOOKBACK == 180


def test_validate_lookback_accepts_floor_default_promo():
    assert validate_lookback(30) == 30
    assert validate_lookback(90) == 90
    assert validate_lookback(180) == 180


def test_validate_lookback_rejects_below_floor():
    with pytest.raises(ValueError, match="30"):
        validate_lookback(29)


def test_research_config_defaults():
    c = ResearchConfig()
    assert c.symbol == "BTC"
    assert c.timeframe == "1m"
    assert c.lookback_days == 90
    assert c.backfill_priority == ("binance", "bybit")
    assert c.strict_hl_only is False


def test_research_config_rejects_short_lookback():
    with pytest.raises(ValueError):
        ResearchConfig(lookback_days=10)
