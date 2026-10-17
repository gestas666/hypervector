"""Vectorised regime alignment must equal the original per-position loop.

Performance regression: ``_window_alignment`` sliced the full decisions frame
for every position and lookback, ``_decision_directions`` ran per window, and
``_future_extreme`` was rebuilt eight times per tuning trial although it
depends only on bars and horizon. These tests pin numerical identity against
the original implementation and bound the repeated work.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.regime import hypervelocity_eval as hv_eval
from hypervector.regime import tuning
from hypervector.regime.hypervelocity_eval import (
    _available_decisions,
    _decision_directions,
    _unique_entry_decisions,
    evaluate_breakout_quality,
    evaluate_entry_alignment,
    evaluate_range_quality,
)
from hypervector.regime.models import PrimaryRegime

_REGIMES = ["TREND_UP", "TREND_DOWN", "BREAKOUT", "RANGE", "TRANSITION", "UNKNOWN"]


# --- original implementation (reference) -----------------------------------


def _reference_window_alignment(decisions, positions, minutes):  # type: ignore[no-untyped-def]
    matches = 0
    range_only = 0
    normalized_index = decisions.index.as_unit("ns")
    for row in positions.itertuples(index=False):
        timestamp = pd.Timestamp(row.event_time).as_unit("ns")
        end_position = int(normalized_index.searchsorted(timestamp, side="right")) - 1
        if end_position < 0:
            continue
        end_time = decisions.index[end_position]
        start = end_time - pd.Timedelta(minutes=minutes)
        window = decisions.loc[(decisions.index >= start) & (decisions.index <= end_time)]
        predicted = set(_decision_directions(window).dropna().astype(str))
        matches += int(str(row.side).lower() in predicted)
        range_only += int(
            len(window) > 0 and window["primary_regime"].eq(PrimaryRegime.RANGE.value).all()
        )
    return matches, range_only


def _reference_alignment(decisions, positions, lookbacks=(0, 1, 5, 10, 30)):  # type: ignore[no-untyped-def]
    unique = _unique_entry_decisions(positions, cluster_seconds=1.0)
    available = _available_decisions(decisions, pd.Timedelta(minutes=1))
    aligned = available.reindex(pd.DatetimeIndex(unique["event_time"]), method="ffill")
    wanted = unique["side"].astype(str).str.lower().to_numpy()
    predicted = _decision_directions(aligned).to_numpy()
    primary = aligned["primary_regime"]
    total = len(unique)
    by_window = {m: _reference_window_alignment(available, unique, m) for m in lookbacks}
    return {
        "recorded_positions": len(positions),
        "unique_entry_decisions": total,
        "total_entries": total,
        "direction_matches": int((predicted == wanted).sum()),
        "direction_recall_pct": (100.0 * int((predicted == wanted).sum()) / total)
        if total
        else 0.0,
        "false_range_at_entries": int(primary.eq(PrimaryRegime.RANGE.value).sum()),
        "no_entry_state_at_entries": int(pd.isna(predicted).sum()),
        "direction_recall_by_lookback_pct": {
            f"{m}m": (100.0 * v[0] / total) if total else 0.0 for m, v in by_window.items()
        },
        "range_only_entries_by_lookback": {f"{m}m": v[1] for m, v in by_window.items()},
    }


def _reference_future_extreme(series: pd.Series, horizon: int, kind: str) -> pd.Series:
    future = pd.concat([series.shift(-step) for step in range(1, horizon + 1)], axis=1)
    if kind == "max":
        return future.max(axis=1, skipna=False)
    return future.min(axis=1, skipna=False)


# --- synthetic inputs ---------------------------------------------------------


def _decisions(rng: np.random.Generator, n: int, tactical: bool, unit: str) -> pd.DataFrame:
    index = pd.date_range("2026-03-01", periods=n, freq="1min", tz="UTC").as_unit(unit)
    # Runs of states so multi-minute windows contain both pure and mixed spans.
    run_states = rng.choice(_REGIMES, size=n // 3 + 1, p=[0.2, 0.2, 0.15, 0.3, 0.1, 0.05])
    primary = np.repeat(run_states, 3)[:n]
    breakout = np.where(
        primary == "BREAKOUT",
        rng.choice(["BK_UPWARD", "BK_DOWNWARD", None], size=n),
        None,
    )
    frame = pd.DataFrame(
        {"primary_regime": primary, "breakout_direction": breakout, "filler": 1.0},
        index=index,
    )
    if tactical:
        frame["entry_direction"] = rng.choice(["long", "short", None, "flat"], size=n)
    return frame


def _positions(rng: np.random.Generator, index: pd.DatetimeIndex, count: int) -> pd.DataFrame:
    start = index[0] - pd.Timedelta(minutes=3)  # some entries precede every decision
    span = (index[-1] - start).total_seconds() + 120
    seconds = np.sort(rng.uniform(0, span, size=count))
    times = [start + pd.Timedelta(seconds=float(value)) for value in seconds]
    # Exact candle-close boundaries are the delicate case for "right" searches.
    times[: count // 5] = [index[int(i)] + pd.Timedelta(minutes=1) for i in rng.integers(0, len(index), count // 5)]
    sides = rng.choice(["long", "short", "LONG", "Short", "flat"], size=count)
    return pd.DataFrame(
        {"open_time_utc": [t.isoformat() for t in times], "side": sides, "symbol": "BTC"}
    )


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("tactical", [False, True])
def test_vectorised_alignment_equals_the_original_loop(seed: int, tactical: bool) -> None:
    rng = np.random.default_rng(seed)
    unit = ["ns", "us", "ms"][seed % 3]
    decisions = _decisions(rng, 240, tactical, unit)
    positions = _positions(rng, decisions.index, 90)
    lookbacks = (0, 1, 2, 5, 10, 30)

    report = evaluate_entry_alignment(decisions, positions, lookback_minutes=lookbacks)

    expected = _reference_alignment(decisions, positions, lookbacks)
    assert {key: getattr(report, key) for key in expected} == expected


def test_alignment_of_entries_before_any_decision_counts_nothing() -> None:
    rng = np.random.default_rng(9)
    decisions = _decisions(rng, 30, False, "ns")
    positions = pd.DataFrame(
        {
            "open_time_utc": [decisions.index[0] - pd.Timedelta(minutes=5)],
            "side": ["long"],
            "symbol": ["BTC"],
        }
    )
    report = evaluate_entry_alignment(decisions, positions)
    expected = _reference_alignment(decisions, positions)
    assert {key: getattr(report, key) for key in expected} == expected
    assert set(report.range_only_entries_by_lookback.values()) == {0}
    assert report.no_entry_state_at_entries == 1


@pytest.mark.parametrize("horizon", [1, 2, 5, 30])
def test_future_extreme_equals_the_shift_concat_reference(horizon: int) -> None:
    rng = np.random.default_rng(horizon)
    values = rng.normal(100.0, 1.0, size=200)
    values[[3, 50, 51, 120]] = np.nan
    series = pd.Series(values, index=pd.date_range("2026-01-01", periods=200, freq="1min"))
    for kind in ("max", "min"):
        result = hv_eval._future_extreme(series, horizon, kind)
        expected = _reference_future_extreme(series, horizon, kind)
        pd.testing.assert_series_equal(result, expected, check_names=False)


def test_quality_reports_accept_precomputed_future_extremes() -> None:
    rng = np.random.default_rng(4)
    index = pd.date_range("2026-01-01", periods=120, freq="1min", tz="UTC")
    close = 100.0 + np.cumsum(rng.normal(0, 0.2, 120))
    bars = pd.DataFrame({"close": close, "high": close + 0.1, "low": close - 0.1}, index=index)
    decisions = _decisions(rng, 120, False, "ns").set_axis(index)
    high = hv_eval._future_extreme(bars["high"], 5, "max")
    low = hv_eval._future_extreme(bars["low"], 5, "min")
    for function in (evaluate_breakout_quality, evaluate_range_quality):
        plain = function(bars, decisions, target_price_fraction=0.002, forward_horizon=5)
        cached = function(
            bars,
            decisions,
            target_price_fraction=0.002,
            forward_horizon=5,
            future_high=high,
            future_low=low,
        )
        assert cached == plain


def _tuning_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(12)
    n = 900
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.0015, n)))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, 0.0005, n)) * close
    bars = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": rng.lognormal(3, 1, n),
        },
        index=index,
    )
    picks = np.sort(rng.choice(np.arange(320, n - 5), 40, replace=False))
    positions = pd.DataFrame(
        {
            "open_time_utc": [index[p] + pd.Timedelta(seconds=17) for p in picks],
            "side": rng.choice(["long", "short"], 40),
            "symbol": "BTC",
        }
    )
    return bars, positions


def test_tuning_trials_match_independent_reference_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bars, positions = _tuning_inputs()
    candidates = tuning.generate_candidate_parameters(n_trials=3, seed=7)
    captured: list[pd.DataFrame] = []
    original = tuning.classify_multitimeframe

    def classify(*args: object, **kwargs: object) -> pd.DataFrame:
        decisions = original(*args, **kwargs)
        captured.append(decisions)
        return decisions

    monkeypatch.setattr(tuning, "classify_multitimeframe", classify)
    board = tuning.autotune_regime_candidates(
        bars, positions, candidates, train_fraction=0.7, forward_horizon=30
    )

    split = tuning._split_positions(positions, 0.7)
    train_mask = bars.index <= split.split_time
    for trial, decisions in zip(board.trials, captured):
        assert trial.status == "completed"
        expected_train = _reference_alignment(decisions, split.train_positions)
        expected_holdout = _reference_alignment(decisions, split.holdout_positions)
        assert {k: getattr(trial.train_alignment, k) for k in expected_train} == expected_train
        assert {
            k: getattr(trial.holdout_alignment, k) for k in expected_holdout
        } == expected_holdout
        for mask, breakout, ranges in (
            (train_mask, trial.train_breakout_quality, trial.train_range_quality),
            (~train_mask, trial.holdout_breakout_quality, trial.holdout_range_quality),
        ):
            selected_bars = bars.loc[mask]
            selected = decisions.loc[mask]
            assert breakout == evaluate_breakout_quality(
                selected_bars, selected, target_price_fraction=0.002, forward_horizon=30
            )
            assert ranges == evaluate_range_quality(
                selected_bars, selected, target_price_fraction=0.002, forward_horizon=30
            )


def test_tuning_does_not_repeat_parameter_independent_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bars, positions = _tuning_inputs()
    candidates = tuning.generate_candidate_parameters(n_trials=4, seed=3)
    counts = {"future": 0, "directions": 0, "unique": 0}
    future = hv_eval._future_extreme
    directions = hv_eval._decision_directions
    unique = hv_eval._unique_entry_decisions

    def count(name, function):  # type: ignore[no-untyped-def]
        def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            counts[name] += 1
            return function(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(hv_eval, "_future_extreme", count("future", future))
    monkeypatch.setattr(hv_eval, "_decision_directions", count("directions", directions))
    monkeypatch.setattr(hv_eval, "_unique_entry_decisions", count("unique", unique))
    monkeypatch.setattr(tuning, "_unique_entry_decisions", count("unique", unique))

    board = tuning.autotune_regime_candidates(
        bars, positions, candidates, train_fraction=0.7, forward_horizon=30
    )

    assert all(trial.status == "completed" for trial in board.trials)
    # Future extremes: high+low for the train and holdout slices, once per run.
    assert counts["future"] == 4
    # Directions are derived once per trial and shared by both splits.
    assert counts["directions"] == len(candidates)
    # Entry de-duplication runs for the split and each prepared split, not per trial.
    assert counts["unique"] <= 3
