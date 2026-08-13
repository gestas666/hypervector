"""Tests for causal historical oracle-price lookup."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.oracle_price_series import CausalOraclePriceSeries


def test_returns_latest_oracle_observed_at_or_before_settlement() -> None:
    """A funding reference must not use a post-settlement observation."""
    series = CausalOraclePriceSeries(
        pd.DataFrame(
            {
                "ts_ms": [1_000, 1_900, 2_100],
                "oracle_price": [99.0, 100.0, 101.0],
            }
        ),
        maximum_staleness_ms=200,
    )

    observation = series.at_or_before(2_000)

    assert observation.timestamp_ms == 1_900
    assert observation.oracle_price == pytest.approx(100.0)
    assert observation.staleness_ms == 100


def test_rejects_stale_or_missing_oracle_evidence() -> None:
    """An unobserved settlement must fail instead of using a bar-price fallback."""
    series = CausalOraclePriceSeries(
        pd.DataFrame({"ts_ms": [1_000, 2_000], "oracle_price": [99.0, 100.0]}),
        maximum_staleness_ms=100,
    )

    with pytest.raises(LookupError, match="no causal oracle observation"):
        series.at_or_before(500)
    with pytest.raises(LookupError, match="oracle observation is stale"):
        series.at_or_before(1_500)


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (pd.DataFrame({"ts_ms": [1_000]}), "missing columns"),
        (
            pd.DataFrame({"ts_ms": [1_000, 1_000], "oracle_price": [99.0, 100.0]}),
            "unique and increasing",
        ),
    ],
)
def test_rejects_invalid_oracle_series(frame: pd.DataFrame, message: str) -> None:
    """Reference evidence must have a complete chronological identity."""
    with pytest.raises(ValueError, match=message):
        CausalOraclePriceSeries(frame, maximum_staleness_ms=100)
