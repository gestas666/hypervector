"""Tests for development-only BTC liquidation economic materialization."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from hypervector.data.hl_funding_evidence import HlFundingEvidence
from hypervector.research.btc_liquidation_covariate_models import (
    BookSnapshot,
    PublicTrade,
    ReplayEpisode,
    VisibleLevel,
)
from hypervector.research.btc_liquidation_development_materializer import (
    evaluate_development_episode,
    funding_settlements,
)


def _levels(best: str, step: str) -> tuple[VisibleLevel, ...]:
    return tuple(
        VisibleLevel(Decimal(best) + Decimal(step) * row, Decimal("100"))
        for row in range(20)
    )


def _book(timestamp_ms: int, bid: str, ask: str) -> BookSnapshot:
    return BookSnapshot(timestamp_ms, _levels(bid, "-1"), _levels(ask, "1"))


def _labels() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "bar_open_at": pd.to_datetime(["1969-12-31T23:55:00Z"], utc=True),
            "available_at": pd.to_datetime(["1970-01-01T00:00:00Z"], utc=True),
            "primary_regime": ["TREND_UP"],
        }
    )


def _funding() -> HlFundingEvidence:
    return HlFundingEvidence(
        symbol="BTC",
        start_ms=0,
        end_ms=1_000_000,
        rows=(
            {
                "event_ts_ms": 200_000,
                "funding_rate": 0.0001,
                "source": "hl_funding_history",
            },
        ),
        evidence={"complete": True},
    )


def test_materializer_binds_entry_outcomes_funding_and_causal_regime() -> None:
    """One episode retains every frozen economic and descriptive component."""
    episode = ReplayEpisode(
        "episode-a",
        "development",
        "continuation_long",
        1_000,
        Decimal("100"),
        ("5s_p95",),
    )
    decision_ms = 11_000
    trades = (
        PublicTrade(10_000, 1, "buy", Decimal("100"), Decimal("2")),
        PublicTrade(11_000, 2, "sell", Decimal("100"), Decimal("1")),
    )
    books = (
        _book(decision_ms, "99", "101"),
        _book(decision_ms + 300_000, "102", "104"),
    )

    result = evaluate_development_episode(
        episode,
        trades=trades,
        books=books,
        funding=_funding(),
        settlements=funding_settlements(_funding()),
        regime_labels=_labels(),
        horizons_ms=(300_000,),
    )

    assert result.entry.status == "eligible"
    assert result.regime["primary_regime"] == "TREND_UP"
    assert result.outcomes[0].funding is not None
    assert result.outcomes[0].funding.cashflow_usd == Decimal("-0.5000")
    assert result.outcomes[0].nominal_net_pnl_usd is not None


def test_funding_conversion_preserves_verified_serialized_precision() -> None:
    """Float-backed official rows become exact Decimal string values once."""
    converted = funding_settlements(_funding())

    assert converted[0].funding_rate == Decimal("0.0001")
