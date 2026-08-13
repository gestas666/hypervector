"""Tests for source-style and serialized Hypertrader B/C close replay."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hypertrader_recipe_eval import (
    evaluate_close_recipe,
    summarize_close_recipe,
)


def _bars(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-07-01T00:00:00Z", periods=len(closes), freq="5min")
    return pd.DataFrame({"close": closes}, index=index)


def _event(
    label_time: pd.Timestamp,
    *,
    recipe_id: str = "fade_td_eu",
    maximum_hold_seconds: float = 900.0,
    side: str = "long",
) -> dict[str, object]:
    return {
        "recipe_id": recipe_id,
        "label_time_utc": label_time,
        "decision_time_utc": label_time + pd.Timedelta(minutes=5),
        "side": side,
        "maximum_hold_seconds": maximum_hold_seconds,
        "confidence": 0.8,
    }


def test_close_replay_uses_first_target_close_and_fixed_source_fee() -> None:
    bars = _bars([100.0, 100.1, 100.21, 100.0])
    events = pd.DataFrame([_event(bars.index[0])])

    trades = evaluate_close_recipe(events, bars, serialized=False)

    assert len(trades) == 1
    assert trades.loc[0, "exit_reason"] == "tp"
    assert trades.loc[0, "exit_time_utc"] == bars.index[2]
    assert trades.loc[0, "gross_bps"] == 21.0
    assert trades.loc[0, "net_bps"] == 13.0


def test_close_replay_uses_130_point_btc_target_when_it_is_closer() -> None:
    bars = _bars([100_000.0, 100_140.0, 100_210.0])
    events = pd.DataFrame([_event(bars.index[0])])

    trades = evaluate_close_recipe(events, bars, serialized=False)

    assert trades.loc[0, "exit_time_utc"] == bars.index[1]
    assert trades.loc[0, "gross_bps"] == 14.0
    assert trades.loc[0, "net_bps"] == 6.0


def test_close_replay_supports_trend_aligned_short_target() -> None:
    bars = _bars([100_000.0, 99_870.0, 99_800.0])
    events = pd.DataFrame([_event(bars.index[0], side="short")])

    trades = evaluate_close_recipe(events, bars, serialized=False)

    assert trades.loc[0, "exit_time_utc"] == bars.index[1]
    assert trades.loc[0, "gross_bps"] == 13.0
    assert trades.loc[0, "net_bps"] == 5.0


def test_serialized_replay_discloses_overlapping_event_skip() -> None:
    bars = _bars([100.0, 99.9, 100.21, 100.22])
    events = pd.DataFrame([_event(bars.index[0]), _event(bars.index[1])])

    independent = evaluate_close_recipe(events, bars, serialized=False)
    serialized = evaluate_close_recipe(events, bars, serialized=True)

    assert independent["admission"].tolist() == ["accepted", "accepted"]
    assert serialized["admission"].tolist() == ["accepted", "overlap_skipped"]


def test_close_replay_summary_separates_tp_timeout_and_overlap() -> None:
    trades = pd.DataFrame(
        {
            "admission": ["accepted", "accepted", "overlap_skipped"],
            "exit_reason": ["tp", "timeout", None],
            "net_bps": [12.0, -18.0, None],
        }
    )

    summary = summarize_close_recipe(trades)

    assert summary == {
        "events": 3,
        "accepted": 2,
        "overlap_skipped": 1,
        "closed": 2,
        "tp": 1,
        "timeout": 1,
        "win_rate": 0.5,
        "mean_net_bps": -3.0,
        "sum_net_bps": -6.0,
    }
