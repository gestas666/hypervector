"""Exact v51 exit-contract tests for HIP-3 prospective replays."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pandas as pd

from hypervector.cohort_profit_lock_policy import ProfitLockPolicy
from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowLifecycleConfig,
)
from hypervector.research.hip3_shadow_lifecycle_replay import (
    build_hip3_shadow_lifecycle_replay,
)
from hip3_shadow_lifecycle_fixtures import (
    book,
    candles,
    decision_time,
    decisions,
    funding,
    lifecycle_config,
    marks,
)


def test_v51_fixed_execution_stop_overrides_structural_stop() -> None:
    """Use the bound 80-bps stop rather than the signal's 120-bps ceiling."""
    rows = candles(32, 36)
    entry_time = decision_time(rows, 32) + 1_000
    trigger_time = entry_time + 10_000
    config = replace(
        lifecycle_config(),
        signal_config=replace(lifecycle_config().signal_config, maximum_stop_bps=120.0),
        fixed_stop_bps=80.0,
    )
    entry_ask = 102.01
    stop = entry_ask * (1.0 - 80.0 / 10_000.0)
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions(rows, eligible_positions={32}),
        book_rows=(book(entry_time, 102.0), book(trigger_time, stop - 0.01)),
        candles=rows,
        mark_rows=marks(entry_time, trigger_time, stop - 0.01),
        funding_rows=funding(rows),
        config=config,
    )

    lifecycle = report["nominal"]["lifecycles"][0]
    assert lifecycle["exit_reason"] == "stop"
    assert lifecycle["stop_price"] == stop


def test_v51_disables_generic_signal_exit_and_uses_maximum_hold() -> None:
    """Ignore generic EMA exits when the bound provider has no recipe exit."""
    rows = candles(32, 35, periods=140)
    entry_time = decision_time(rows, 32) + 1_000
    deadline = decision_time(rows, 32) + 24 * 60 * 60_000
    config = replace(
        lifecycle_config(),
        signal_exit_enabled=False,
        maximum_mark_gap_ms=60_000,
    )
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions(rows, eligible_positions={32}),
        book_rows=(book(entry_time, 102.0), book(deadline, 103.0)),
        candles=rows,
        mark_rows=marks(entry_time, deadline, 102.5, step_ms=30_000),
        funding_rows=funding(rows),
        config=config,
    )

    lifecycle = report["nominal"]["lifecycles"][0]
    assert lifecycle["exit_reason"] == "max_hold"
    assert lifecycle["exit_time_ms"] == deadline


def test_v51_completed_bar_profit_lock_exits_after_activation() -> None:
    """Exit only after a post-entry completed bar activates and later crosses."""
    rows = candles(32, None, periods=140)
    entry_time = decision_time(rows, 32) + 1_000
    first_bar = entry_time // 60_000 * 60_000 + 60_000
    trigger_exit = first_bar + 2 * 60_000
    config = _v51_config()
    profit_bars = _profit_lock_bars(first_bar, 102.01)
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions(rows, eligible_positions={32}),
        book_rows=(book(entry_time, 102.0), book(trigger_exit, 102.40)),
        candles=rows,
        mark_rows=marks(entry_time, trigger_exit, 102.5),
        funding_rows=funding(rows),
        config=config,
        profit_lock_bars=profit_bars,
    )

    lifecycle = report["nominal"]["lifecycles"][0]
    assert lifecycle["exit_reason"] == "profit_lock"
    assert lifecycle["exit_time_ms"] == trigger_exit


def test_v51_profit_lock_ignores_pre_entry_bars_and_censors_missing_path() -> None:
    """Pre-entry highs cannot arm a lock or success-shape an absent live path."""
    rows = candles(32, None, periods=140)
    entry_time = decision_time(rows, 32) + 1_000
    first_bar = entry_time // 60_000 * 60_000 + 60_000
    pre_entry = _price_bars(
        (first_bar - 120_000, first_bar - 60_000),
        ((102.01, 104.10, 102.01, 104.00), (104.00, 104.05, 101.00, 101.00)),
    )
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions(rows, eligible_positions={32}),
        book_rows=(book(entry_time, 102.0),),
        candles=rows,
        mark_rows=marks(entry_time, entry_time + 1_000, 102.5),
        funding_rows=funding(rows),
        config=_v51_config(),
        profit_lock_bars=pre_entry,
    )

    assert report["nominal"]["completed_lifecycles"] == 0
    assert report["nominal"]["censored"][0]["reason"] == "exit_event_censored"


def test_v51_trailing_giveback_can_trigger_above_the_fixed_floor() -> None:
    """Use the tighter peak-giveback stop after a sufficiently large advance."""
    rows = candles(32, None, periods=140)
    entry_time = decision_time(rows, 32) + 1_000
    first_bar = entry_time // 60_000 * 60_000 + 60_000
    trigger_exit = first_bar + 2 * 60_000
    entry = 102.01
    profit_bars = _price_bars(
        (first_bar, first_bar + 60_000),
        (
            (entry, entry * 1.020, entry, entry * 1.018),
            (entry * 1.018, entry * 1.019, entry * 1.010, entry * 1.010),
        ),
    )
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions(rows, eligible_positions={32}),
        book_rows=(book(entry_time, 102.0), book(trigger_exit, entry * 1.010)),
        candles=rows,
        mark_rows=marks(entry_time, trigger_exit, 102.5),
        funding_rows=funding(rows),
        config=_v51_config(),
        profit_lock_bars=profit_bars,
    )

    lifecycle = report["nominal"]["lifecycles"][0]
    assert lifecycle["exit_reason"] == "profit_lock"
    assert lifecycle["exit_price"] > lifecycle["entry_price"] * 1.004


def test_v51_opposite_eligible_onset_closes_without_same_cycle_reversal() -> None:
    """Mirror the live router's opposite-intent close-and-wait behavior."""
    rows = candles(32, None, periods=140)
    rows.loc[34, ["open", "high", "low", "close"]] = [96.2, 96.4, 95.8, 96.0]
    decision_rows = list(deepcopy(decisions(rows, eligible_positions={32, 34})))
    opposite = decision_rows[34]["decision"]
    assert isinstance(opposite, dict)
    opposite["side"] = "short"
    opposite["decision_imbalance_10"] = -0.8
    entry_time = decision_time(rows, 32) + 1_000
    opposite_time = decision_time(rows, 34) + 500
    config = replace(
        lifecycle_config(),
        fixed_stop_bps=80.0,
        signal_exit_enabled=False,
        opposite_entry_exit_enabled=True,
    )
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=tuple(decision_rows),
        book_rows=(book(entry_time, 102.0), book(opposite_time, 103.0)),
        candles=rows,
        mark_rows=marks(entry_time, opposite_time, 102.5),
        funding_rows=funding(rows),
        config=config,
    )

    lifecycle = report["nominal"]["lifecycles"][0]
    assert lifecycle["exit_reason"] == "opposite_strategy_intent"
    assert lifecycle["exit_time_ms"] == opposite_time
    assert report["nominal"]["completed_lifecycles"] == 1
    assert report["nominal"]["suppressed_overlapping_onsets"] == 1


def _profit_lock_bars(first_bar: int, entry: float) -> pd.DataFrame:
    activated_high = entry * 1.011
    trigger_low = entry * 1.003
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [first_bar, first_bar + 60_000], unit="ms", utc=True
            ),
            "open": [entry, entry * 1.009],
            "high": [activated_high, entry * 1.010],
            "low": [entry, trigger_low],
            "close": [entry * 1.009, trigger_low],
            "source": ["hl", "hl"],
        }
    )


def _v51_config() -> Hip3ShadowLifecycleConfig:
    return replace(
        lifecycle_config(),
        fixed_stop_bps=80.0,
        signal_exit_enabled=False,
        profit_lock_policy=ProfitLockPolicy("v51_100_40_80", 100.0, 40.0, 80.0),
    )


def _price_bars(
    timestamps: tuple[int, int],
    prices: tuple[tuple[float, float, float, float], ...],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, unit="ms", utc=True),
            "open": [row[0] for row in prices],
            "high": [row[1] for row in prices],
            "low": [row[2] for row in prices],
            "close": [row[3] for row in prices],
            "source": ["hl"] * len(prices),
        }
    )
