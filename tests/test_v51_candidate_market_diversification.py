"""Tests for the source-native v51 candidate market-diversification report."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.v51_candidate_market_diversification import (
    CandidateMarketDiversificationConfig,
    build_candidate_market_diversification_report,
)

_BASELINE = ("BTC", "ETH", "SOL", "HYPE", "xyz:SP500", "xyz:SPCX")
_CANDIDATES = ("xyz:BRENTOIL", "xyz:MU")


def _frame(returns: np.ndarray, *, drop: int | None = None) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2026-06-08", periods=len(returns) + 1, freq="1h", tz="UTC"
    )
    closes = 100.0 * np.cumprod(np.r_[1.0, 1.0 + returns])
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": np.ones(len(closes)),
            "source": "hl",
        }
    )
    return frame.drop(index=drop).reset_index(drop=True) if drop is not None else frame


def _inputs(*, gap_symbol: str | None = None) -> dict[str, pd.DataFrame]:
    x = np.linspace(0.0, 12.0 * np.pi, 120)
    crypto = 0.0010 * np.sin(x) + 0.0003 * np.cos(0.3 * x)
    index = 0.0008 * np.cos(0.7 * x) + 0.0002 * np.sin(1.3 * x)
    returns = {
        "BTC": crypto,
        "ETH": 0.8 * crypto + 0.0002 * np.sin(2.1 * x),
        "SOL": 1.1 * crypto - 0.0002 * np.cos(1.7 * x),
        "HYPE": 0.6 * crypto + 0.0003 * np.sin(0.9 * x),
        "xyz:SP500": index,
        "xyz:SPCX": 0.9 * index + 0.0001 * np.sin(2.0 * x),
        "xyz:BRENTOIL": 0.0007 * np.sin(3.7 * x),
        "xyz:MU": 0.7 * index + 0.0003 * np.cos(1.1 * x),
    }
    return {
        symbol: _frame(values, drop=60 if symbol == gap_symbol else None)
        for symbol, values in returns.items()
    }


def _config() -> CandidateMarketDiversificationConfig:
    return CandidateMarketDiversificationConfig(
        baseline_symbols=_BASELINE,
        candidate_symbols=_CANDIDATES,
        start_utc=pd.Timestamp("2026-06-08T00:00:00Z"),
        end_utc=pd.Timestamp("2026-06-13T01:00:00Z"),
        minimum_shared_returns=90,
        chronological_folds=3,
    )


def test_report_is_report_only_and_uses_only_shared_contiguous_returns() -> None:
    report = build_candidate_market_diversification_report(
        _inputs(gap_symbol="xyz:BRENTOIL"), _config()
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "covariance_weights_generated": False,
    }
    assert report["coverage"]["shared_return_rows"] == 118
    assert report["coverage"]["excluded_noncontiguous_returns"]["xyz:BRENTOIL"] == 1
    assert report["method"]["return_interval"] == "1h"
    assert len(report["chronological_folds"]) == 3


def test_report_separates_market_diversification_from_strategy_edge() -> None:
    report = build_candidate_market_diversification_report(_inputs(), _config())

    brent = report["candidate_diagnostics"]["xyz:BRENTOIL"]
    micron = report["candidate_diagnostics"]["xyz:MU"]
    assert (
        brent["mean_absolute_correlation_to_baseline"]
        < micron["mean_absolute_correlation_to_baseline"]
    )
    assert report["candidate_pair_correlation"] != pytest.approx(1.0)
    assert report["conclusion"]["strategy_edge_established"] is False
    assert report["conclusion"]["live_addition_authorized"] is False
    assert report["source_evidence"]["xyz:BRENTOIL"]["rows"] == 121


def test_duplicate_candle_identity_fails_closed() -> None:
    inputs = _inputs()
    inputs["xyz:MU"] = pd.concat(
        [inputs["xyz:MU"], inputs["xyz:MU"].iloc[[0]]], ignore_index=True
    )

    with pytest.raises(ValueError, match="duplicate candle timestamps"):
        build_candidate_market_diversification_report(inputs, _config())
