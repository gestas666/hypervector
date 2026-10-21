"""Idle polls retain input validation and avoid rebuilding consumed decisions."""

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from hypervector.live import canonical_regime_decisions as regime_decisions


def _bars(minutes: int = 1) -> pd.DataFrame:
    values = 100.0 + np.sin(np.arange(128) / 7.0)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=128, freq=f"{minutes}min", tz="UTC"),
            "open": values,
            "high": values + 1.0,
            "low": values - 1.0,
            "close": values,
            "volume": 10.0,
        }
    )


def _record_calls(monkeypatch: pytest.MonkeyPatch, module: object, name: str) -> list[pd.DataFrame]:
    original: Callable[..., pd.DataFrame] = getattr(module, name)
    calls: list[pd.DataFrame] = []

    def recording(frame: pd.DataFrame, *args: object, **kwargs: object) -> pd.DataFrame:
        calls.append(frame.copy())
        return original(frame, *args, **kwargs)

    monkeypatch.setattr(module, name, recording)
    return calls


def test_consumed_regime_decisions_do_not_rebuild_indicators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A changing forming bar and revised consumed history cannot create a new decision."""
    bars = _bars()
    observed = bars.timestamp.iloc[-1] + pd.Timedelta(seconds=30)
    boundary = int(bars.timestamp.iloc[-1].timestamp() * 1000)
    calls = _record_calls(monkeypatch, regime_decisions, "classify_multitimeframe")
    assert (
        regime_decisions.build_completed_regime_decisions(
            bars, observed_at=observed, after_decision_time_ms=boundary
        )
        == ()
    )
    bars.loc[126:, ["open", "high", "low", "close"]] += 10.0
    assert (
        regime_decisions.build_completed_regime_decisions(
            bars, observed_at=observed, after_decision_time_ms=boundary
        )
        == ()
    )
    assert calls == []


def test_boundary_beyond_pandas_range_remains_an_empty_selection() -> None:
    """The nonnegative integer boundary contract is independent of Pandas timestamp limits."""
    bars = _bars()
    assert (
        regime_decisions.build_completed_regime_decisions(
            bars,
            observed_at=bars.timestamp.iloc[-1] + pd.Timedelta(minutes=1),
            after_decision_time_ms=2**100,
        )
        == ()
    )


@pytest.mark.parametrize("damage", ["nan", "negative", "bounds", "unaligned", "naive", "missing"])
def test_idle_input_errors_remain_visible(damage: str) -> None:
    """An early return cannot turn malformed completed source data into success."""
    bars = _bars()
    observed = bars.timestamp.iloc[-1] + pd.Timedelta(hours=1)
    boundary = int(observed.timestamp() * 1000)
    if damage == "nan":
        bars.loc[127, "close"] = np.nan
    elif damage == "negative":
        bars.loc[127, "close"] = -1.0
    elif damage == "bounds":
        bars.loc[127, "high"] = 1.0
    elif damage == "unaligned":
        bars["timestamp"] += pd.Timedelta(seconds=1)
    elif damage == "naive":
        observed = observed.tz_localize(None)
    elif damage == "missing":
        bars = bars.drop(columns="volume")
    with pytest.raises(ValueError):
        regime_decisions.build_completed_regime_decisions(
            bars, observed_at=observed, after_decision_time_ms=boundary
        )


@pytest.mark.parametrize("damage", ["volume", "empty", "forming_only", "boundary"])
def test_idle_source_and_clock_failures(damage: str) -> None:
    """No completed bars, invalid volume and invalid caller clocks remain failures."""
    bars = _bars()
    observed = bars.timestamp.iloc[-1] + pd.Timedelta(minutes=1)
    boundary = int(observed.timestamp() * 1000)
    if damage == "volume":
        bars.loc[127, "volume"] = -1.0
    elif damage == "empty":
        bars = bars.iloc[:0]
    elif damage == "forming_only":
        observed = bars.timestamp.iloc[0]
    elif damage == "boundary":
        boundary = True
    with pytest.raises(ValueError):
        regime_decisions.build_completed_regime_decisions(
            bars, observed_at=observed, after_decision_time_ms=boundary
        )


@pytest.mark.parametrize("change", ["ordinary", "revision", "gap", "retention", "duplicate"])
def test_range_new_decisions_match_full_current_history(change: str) -> None:
    """A new close uses current causal history, including repairs and history expiry."""
    bars = _bars()
    boundary = int(bars.timestamp.iloc[-2].timestamp() * 1000)
    observed = bars.timestamp.iloc[-1] + pd.Timedelta(minutes=1)
    if change == "revision":
        bars.loc[120:, ["open", "high", "low", "close"]] += 20.0
    elif change == "gap":
        bars = bars.drop(index=110)
    elif change == "retention":
        bars = bars.iloc[60:]
    elif change == "duplicate":
        duplicate = bars.iloc[120:121].copy()
        duplicate[["open", "high", "low", "close"]] += 20.0
        bars = pd.concat([bars, duplicate], ignore_index=True)
    full = regime_decisions.build_completed_regime_decisions(bars, observed_at=observed)
    incremental = regime_decisions.build_completed_regime_decisions(
        bars, observed_at=observed, after_decision_time_ms=boundary
    )
    assert incremental == tuple(row for row in full if row.decision_time_ms > boundary)
    assert len(incremental) == 2


