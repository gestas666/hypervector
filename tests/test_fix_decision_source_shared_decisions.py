"""Live decisions classify once, share identical windows per poll, and stay exact.

The reference is the original builder: signals (which classify internally),
a second classification, components, then one ``.loc`` row lookup per frame
for every unseen bar.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from hypervector.live import sol_range_onset_decision_source as ranges
from hypervector.live.multi_asset_intent_poller import ConfiguredMultiAssetIntentPoller
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.regime.composite import classify_multitimeframe
from hypervector.regime.component_telemetry import build_regime_component_frame
from hypervector.research import range_onset_signals
from hypervector.research.range_onset_observation import completed_range_onset_bars
from hypervector.research.range_onset_signals import build_range_onset_signals

_MINUTE = pd.Timedelta(minutes=1)


def _bars(rows: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 150.0 * np.exp(np.cumsum(rng.normal(0, 0.002, rows)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    spread = np.abs(rng.normal(0, 0.001, rows)) * close
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-09-01", periods=rows, freq="1min", tz="UTC"),
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": rng.uniform(0, 1000, rows),
        }
    )


def _reference(
    raw: pd.DataFrame, observed: pd.Timestamp, after: int | None
) -> tuple[object, ...]:
    bars = completed_range_onset_bars(raw, observed_at=observed)
    positions = bars.index
    if after is not None:
        if after >= int((positions[-1] + _MINUTE).timestamp() * 1_000):
            return ()
        positions = positions[positions + _MINUTE > pd.Timestamp(after, unit="ms", tz="UTC")]
    signals = build_range_onset_signals(bars)
    regimes = classify_multitimeframe(bars)
    components = build_regime_component_frame(bars)
    return tuple(
        ranges._decision_from_rows(
            int((pd.Timestamp(timestamp) + _MINUTE).timestamp() * 1_000),
            bars.loc[timestamp],
            signals.loc[timestamp],
            regimes.loc[timestamp],
            components.loc[timestamp],
        )
        for timestamp in positions
    )


def _case(change: str) -> tuple[pd.DataFrame, pd.Timestamp]:
    raw = _bars(2_000, seed=len(change))
    if change == "gap":
        raw = raw.drop(index=1_600).reset_index(drop=True)
    elif change == "forming":
        raw = pd.concat([raw, raw.iloc[-1:].assign(timestamp=raw.timestamp.iloc[-1] + _MINUTE)])
    elif change == "flat":
        raw.loc[1_850:, ["open", "high", "low", "close"]] = 151.0
    observed = raw.timestamp.iloc[-1] + pd.Timedelta(seconds=5 if change == "forming" else 65)
    return raw, observed


@pytest.mark.parametrize("change", ["ordinary", "gap", "forming", "flat"])
def test_decisions_equal_the_reference_for_every_boundary(change: str) -> None:
    """Every decision field, including value types in readiness, is unchanged."""
    raw, observed = _case(change)
    last = int(raw.timestamp.iloc[-2].timestamp() * 1_000)
    # The 300-bar seed straddles the hourly SMA30 warmup; the gapped case's
    # latest contiguous segment is short enough to decide in full.
    first = None if change == "gap" else last - 300 * 60_000
    boundaries = [first, last, 2**40]
    for after in boundaries:
        expected = _reference(raw, observed, after)
        actual = ranges.build_completed_live_decisions(
            raw, observed_at=observed, after_decision_time_ms=after
        )
        assert actual == expected
        assert repr(actual) == repr(expected)
        with ranges.shared_completed_decisions():
            shared = ranges.build_completed_live_decisions(
                raw, observed_at=observed, after_decision_time_ms=after
            )
            again = ranges.build_completed_live_decisions(
                raw, observed_at=observed, after_decision_time_ms=after
            )
        assert repr(shared) == repr(again) == repr(expected)


def _count(monkeypatch: pytest.MonkeyPatch, module: object, name: str) -> list[int]:
    original = getattr(module, name)
    calls: list[int] = []

    def counting(frame: pd.DataFrame, *args: object, **kwargs: object) -> pd.DataFrame:
        calls.append(len(frame))
        return original(frame, *args, **kwargs)

    monkeypatch.setattr(module, name, counting)
    return calls


def test_each_build_classifies_the_window_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Signals reuse the regimes the decision builder already classified."""
    raw = _bars(600, seed=4)
    observed = raw.timestamp.iloc[-1] + pd.Timedelta(minutes=1)
    builder = _count(monkeypatch, ranges, "classify_multitimeframe")
    internal = _count(monkeypatch, range_onset_signals, "classify_multitimeframe")
    ranges.build_completed_live_decisions(raw, observed_at=observed)
    assert len(builder) + len(internal) == 1


def test_identical_windows_share_one_build_only_inside_a_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Consumers of one window build its frames once per poll, never across polls."""
    raw = _bars(600, seed=5)
    observed = raw.timestamp.iloc[-1] + pd.Timedelta(minutes=1)
    newest = int(raw.timestamp.iloc[-1].timestamp() * 1_000) - 60_000
    history = newest - 60 * 60_000 - 1
    requests = [newest, history, newest, None]
    unshared = [
        ranges.build_completed_live_decisions(
            raw, observed_at=observed, after_decision_time_ms=after
        )
        for after in requests
    ]
    regimes = _count(monkeypatch, ranges, "classify_multitimeframe")
    components = _count(monkeypatch, ranges, "build_regime_component_frame")
    with ranges.shared_completed_decisions():
        shared = [
            ranges.build_completed_live_decisions(
                raw.copy(), observed_at=observed, after_decision_time_ms=after
            )
            for after in requests
        ]
    # The first request retains enough history for the 61-bar consumer; the
    # full-window request reaches past it and rebuilds once.
    assert len(regimes) == len(components) == 2
    assert repr(shared) == repr(unshared)
    assert all(left is right for left, right in zip(shared[0], shared[1][-len(shared[0]) :]))
    ranges.build_completed_live_decisions(raw, observed_at=observed)
    assert len(regimes) == len(components) == 3
    assert ranges._SHARED_DECISIONS.get() is None


def test_unrequested_bars_never_raise_and_are_not_shared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An older bar that cannot be decided stays a failure for whoever requests it."""
    raw = _bars(400, seed=11)
    observed = raw.timestamp.iloc[-1] + pd.Timedelta(minutes=1)
    newest = int(raw.timestamp.iloc[-1].timestamp() * 1_000) - 60_000
    poisoned = newest - 10 * 60_000
    original = ranges._decision_from_rows

    def poisoning(decision_time_ms: int, *rows: object) -> object:
        if decision_time_ms == poisoned:
            raise ValueError("SOL live primary_regime must be non-empty text")
        return original(decision_time_ms, *rows)

    monkeypatch.setattr(ranges, "_decision_from_rows", poisoning)
    reference = ranges.build_completed_live_decisions(
        raw, observed_at=observed, after_decision_time_ms=newest
    )
    with pytest.raises(ValueError, match="primary_regime"):
        ranges.build_completed_live_decisions(
            raw, observed_at=observed, after_decision_time_ms=newest - 20 * 60_000
        )
    with ranges.shared_completed_decisions():
        shared = ranges.build_completed_live_decisions(
            raw, observed_at=observed, after_decision_time_ms=newest
        )
        later = ranges.build_completed_live_decisions(
            raw, observed_at=observed, after_decision_time_ms=poisoned
        )
        assert len(later) == 12
        with pytest.raises(ValueError, match="primary_regime"):
            ranges.build_completed_live_decisions(
                raw, observed_at=observed, after_decision_time_ms=newest - 20 * 60_000
            )
    assert repr(shared) == repr(reference)


@pytest.mark.parametrize("damage", ["ulp", "negative_zero", "index_unit"])
def test_a_window_differing_by_one_bit_is_rebuilt(
    monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    """Sharing requires bit-identical bars, index values and index dtype."""
    raw = _bars(600, seed=6)
    raw.loc[300, "volume"] = 0.0
    observed = raw.timestamp.iloc[-1] + pd.Timedelta(minutes=1)
    other = raw.copy()
    if damage == "ulp":
        other.loc[599, "close"] = np.nextafter(other.loc[599, "close"], np.inf)
        other.loc[599, "high"] = max(other.loc[599, "high"], other.loc[599, "close"])
    elif damage == "negative_zero":
        other.loc[300, "volume"] = -0.0
    else:
        other["timestamp"] = other["timestamp"].astype("datetime64[ms, UTC]")
    regimes = _count(monkeypatch, ranges, "classify_multitimeframe")
    with ranges.shared_completed_decisions():
        first = ranges.build_completed_live_decisions(raw, observed_at=observed)
        second = ranges.build_completed_live_decisions(other, observed_at=observed)
    assert len(regimes) == 2
    monkeypatch.undo()
    assert repr(first) == repr(_reference(raw, observed, None))
    assert repr(second) == repr(_reference(other, observed, None))


def test_eviction_keeps_results_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bounded cycle cache only changes how often frames are rebuilt."""
    monkeypatch.setattr(ranges, "_SHARED_WINDOW_LIMIT", 1)
    monkeypatch.setattr(ranges, "_SHARED_DECISION_LIMIT", 3)
    windows = [_bars(500, seed=seed) for seed in (7, 8)]
    observed = windows[0].timestamp.iloc[-1] + pd.Timedelta(minutes=1)
    newest = int(windows[0].timestamp.iloc[-1].timestamp() * 1_000) - 5 * 60_000
    expected = [_reference(raw, observed, newest) for raw in windows]
    with ranges.shared_completed_decisions():
        actual = [
            ranges.build_completed_live_decisions(
                raw, observed_at=observed, after_decision_time_ms=newest
            )
            for raw in (*windows, *windows)
        ]
    assert [repr(value) for value in actual] == [repr(value) for value in expected * 2]


def _frames(rows: int = 900) -> tuple[pd.DataFrame, ...]:
    raw = _bars(rows, seed=9)
    bars = completed_range_onset_bars(raw, observed_at=raw.timestamp.iloc[-1] + _MINUTE)
    return ranges._completed_frames(bars)


def test_row_reader_values_are_the_iloc_row_values() -> None:
    """Every element keeps the exact type and value the row Series would hold."""
    for frame in _frames():
        locations = np.arange(len(frame))
        reader = ranges._RowReader(frame)
        rows = [row for start in range(0, len(frame), 128) for row in reader.rows(locations[start : start + 128])]
        assert all(isinstance(row, dict) for row in rows)
        for location, row in zip(locations, rows, strict=True):
            expected = frame.iloc[int(location)]
            assert list(row) == list(expected.index)
            for left, right in zip(expected._values, row.values(), strict=True):
                assert ranges._same_element(left, right)


def test_row_reader_falls_back_to_row_series_when_it_cannot_vouch() -> None:
    """Duplicate labels or a mismatching element return the iloc rows unchanged."""
    _, signals, regimes, _ = _frames(300)
    duplicated = pd.concat([signals, signals[["long_entry"]]], axis=1)
    rows = ranges._RowReader(duplicated).rows(np.array([5, 6]))
    assert all(isinstance(row, pd.Series) for row in rows)
    empty = ranges._RowReader(signals[[]]).rows(np.array([5, 6]))
    assert len(empty) == 2 and all(row.empty for row in empty)
    reader = ranges._RowReader(regimes)
    reader._arrays = [np.asarray(values, dtype=object) for values in reader._arrays]  # type: ignore[union-attr]
    rows = reader.rows(np.array([10, 11]))
    assert all(isinstance(row, pd.Series) for row in rows)
    assert rows[0].equals(regimes.iloc[10])


class _SharingProbe:
    def __init__(self, strategy_id: str, seen: list[object]) -> None:
        self.strategy_id = strategy_id
        self.seen = seen

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del bars, observed_at
        self.seen.append(ranges._SHARED_DECISIONS.get())
        boundary = (after_decision_time_ms or 0) + 1
        evaluation = ProviderEvaluation(
            strategy_id=self.strategy_id,
            symbol=symbol,
            decision_time_ms=boundary,
            reference_price=100.0,
            decision_action="hold",
            eligible=False,
            reason="fixture_hold",
            side=None,
            readiness=SignalReadiness(None, 0, 1, ("fixture",), ("FIXTURE",)),
        )
        return IntentBatch((), boundary, (evaluation,))


def test_poller_shares_decisions_for_exactly_one_cycle() -> None:
    """Every collector in a poll sees one fresh cycle cache; none survives the poll."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/cohort_base.toml", mode="observe"
    )
    seen: list[object] = []
    collectors = {
        provider.strategy_id: _SharingProbe(provider.strategy_id, seen)
        for provider in config.providers
    }
    raw = _bars(10, seed=10).assign(
        timestamp=pd.date_range("2026-08-01T11:50:00Z", periods=10, freq="1min")
    )
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: raw.copy(),
        collectors=collectors,
    )
    observed = datetime(2026, 8, 1, 12, tzinfo=UTC)
    poller.activate(int(observed.timestamp() * 1_000) - 1_000)
    poller.poll(observed)
    first_cycle = list(seen)
    seen.clear()
    poller.poll(datetime(2026, 8, 1, 12, 0, 15, tzinfo=UTC))
    assert first_cycle and seen
    assert all(value is not None for value in first_cycle + seen)
    assert len({id(value) for value in first_cycle}) == 1
    assert len({id(value) for value in seen}) == 1
    assert first_cycle[0] is not seen[0]
    assert ranges._SHARED_DECISIONS.get() is None
