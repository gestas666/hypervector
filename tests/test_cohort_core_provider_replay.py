"""Causal boundaries and source uncertainty in current-provider extraction."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.research.cohort_core_provider_replay import (
    CoreReplayWindow,
    iter_core_provider_batches,
    evaluation_contract,
)

_START = pd.Timestamp("2026-05-19T00:00:00Z")
_MINUTE = pd.Timedelta(minutes=1)


def _bars() -> pd.DataFrame:
    times = pd.date_range(_START - pd.Timedelta(days=1), periods=3 * 1440, freq="min")
    return pd.DataFrame(
        {
            "timestamp": times,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl",
        }
    )


def _collector(
    bars: pd.DataFrame,
    *,
    symbol: str,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None,
) -> IntentBatch:
    assert bars.timestamp.max() + _MINUTE <= observed_at
    boundary = int(observed_at.timestamp() * 1000)
    row = ProviderEvaluation(
        "test",
        symbol,
        boundary,
        100.0,
        "close_long",
        False,
        "opposite",
        "short",
        SignalReadiness("short", 1, 1, (), ("opposite onset",)),
        exit_sides=frozenset({"long"}),
        exit_reason="opposite",
    )
    return IntentBatch((), boundary, (row,))


def test_daily_extraction_preserves_exit_only_rows_and_disjoint_boundaries() -> None:
    """Opposite exits survive extraction even without any entry intents."""
    window = CoreReplayWindow(_START, _START + pd.Timedelta(days=2), 1)
    batches = list(iter_core_provider_batches(_bars(), "ETH", window, _collector))
    assert len(batches) == 2
    assert batches[0].end == batches[1].start
    assert batches[0].evaluations[0].exit_sides == frozenset({"long"})
    assert batches[1].evaluations[0].decision_time_ms > (
        batches[0].evaluations[0].decision_time_ms
    )
    assert batches[0].missing_input_minutes == 0
    assert batches[0].gap_filled_input_minutes == 0


def test_source_gaps_are_counted_without_becoming_synthetic_evidence() -> None:
    """Gap tags and genuinely absent minutes remain distinct source defects."""
    bars = _bars()
    bars.loc[0, "source"] = "hl_gap_fill"
    bars = bars.drop(index=1)
    window = CoreReplayWindow(_START, _START + _MINUTE, 1)
    batch = next(iter_core_provider_batches(bars, "ETH", window, _collector))
    assert batch.gap_filled_input_minutes == 1
    assert batch.missing_input_minutes == 1


@pytest.mark.parametrize("symbol", ["xyz:SNDK", "xyz:SPCX", "ZEC", ""])
def test_non_core_sources_require_their_own_adapter(symbol: str) -> None:
    """Prospective HIP-3 contracts cannot be relabeled as core candle inputs."""
    with pytest.raises(ValueError, match="core replay symbol"):
        list(
            iter_core_provider_batches(
                _bars(),
                symbol,
                CoreReplayWindow(_START, _START + _MINUTE, 1),
                _collector,
            )
        )


@pytest.mark.parametrize("defect", ["duplicate", "unordered", "source", "coverage"])
def test_invalid_source_fails_with_actionable_error(defect: str) -> None:
    """Extraction rejects ambiguous source identity and missing warmup bounds."""
    bars = _bars()
    if defect == "duplicate":
        bars = pd.concat([bars.iloc[:1], bars], ignore_index=True)
    elif defect == "unordered":
        bars = bars.iloc[::-1]
    elif defect == "source":
        bars.loc[0, "source"] = "unknown"
    else:
        bars = bars.iloc[2:]
    with pytest.raises(ValueError):
        list(
            iter_core_provider_batches(
                bars,
                "ETH",
                CoreReplayWindow(_START, _START + _MINUTE, 1),
                _collector,
            )
        )


@pytest.mark.parametrize(
    "start,end,days",
    [
        (_START.tz_localize(None), _START + _MINUTE, 1),
        (_START, _START, 1),
        (_START, _START + _MINUTE, 0),
        (_START, _START + _MINUTE, True),
        (_START, _START + pd.Timedelta(seconds=1), 1),
    ],
)
def test_invalid_window_is_rejected(
    start: pd.Timestamp,
    end: pd.Timestamp,
    days: int,
) -> None:
    """Unambiguous complete-minute boundaries are required for extraction."""
    with pytest.raises(ValueError):
        CoreReplayWindow(start, end, days)


def test_contract_keeps_side_exits_and_regime_without_readiness_rounding() -> None:
    """Execution and regime parity use underlying fields rather than UI text."""
    row = _collector(
        _bars().iloc[:1], symbol="ETH", observed_at=_START, after_decision_time_ms=0
    ).evaluations[0]
    actual = evaluation_contract(replace(row, context_15m="TREND"))
    assert actual["exit_sides"] == ["long"]
    assert actual["eligible"] is False
    assert actual["context_15m"] == "TREND"
    assert "readiness" not in actual


@pytest.mark.parametrize("defect", ["symbol", "duplicate", "past", "future"])
def test_malformed_provider_output_cannot_enter_replay(defect: str) -> None:
    """A collector may not corrupt chronology or route attribution silently."""

    def malformed(
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        batch = _collector(
            bars,
            symbol=symbol,
            observed_at=observed_at,
            after_decision_time_ms=after_decision_time_ms,
        )
        row = batch.evaluations[0]
        if defect == "duplicate":
            return replace(batch, evaluations=(row, row))
        if defect == "symbol":
            row = replace(row, symbol="BTC")
        else:
            offset = -60_000 if defect == "past" else 60_000
            row = replace(row, decision_time_ms=row.decision_time_ms + offset)
        return replace(batch, evaluations=(row,))

    with pytest.raises(ValueError, match="wrong-symbol or out-of-window"):
        list(
            iter_core_provider_batches(
                _bars(),
                "ETH",
                CoreReplayWindow(_START, _START + _MINUTE, 1),
                malformed,
            )
        )


def test_missing_schema_and_non_minute_source_are_rejected() -> None:
    """Minute coverage arithmetic cannot accept a different input frequency."""
    window = CoreReplayWindow(_START, _START + _MINUTE, 1)
    with pytest.raises(ValueError, match="missing columns"):
        list(
            iter_core_provider_batches(
                _bars().drop(columns="source"), "ETH", window, _collector
            )
        )
    bars = _bars()
    bars["timestamp"] += pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="minute-aligned"):
        list(iter_core_provider_batches(bars, "ETH", window, _collector))
