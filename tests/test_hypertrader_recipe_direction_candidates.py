"""Direction-candidate contracts for exact pinned Hypertrader Recipe C."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd

from hypervector.research.hypertrader_source_adapter import (
    extract_source_breakout_events,
    extract_source_fade_events,
    extract_source_follow_all_day_events,
    extract_source_follow_asia_events,
    extract_source_follow_events,
    extract_source_follow_session_06_15_events,
    extract_source_follow_session_08_17_events,
    extract_source_follow_us_events,
)
from hypervector.research.hypertrader_source_confidence import (
    extract_source_follow_all_day_confidence_70_events,
    extract_source_follow_session_06_15_confidence_70_events,
)


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_hypertrader_maker_replay.py")
    spec = importlib.util.spec_from_file_location("hypertrader_maker_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Hypertrader maker replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _labels() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2026-07-27T00:00:00Z",
                "2026-07-27T00:05:00Z",
                "2026-07-27T07:00:00Z",
                "2026-07-27T07:05:00Z",
            ],
            utc=True,
        )
    )
    return pd.DataFrame(
        {
            "primary_code": ["RANGE", "BREAKOUT", "RANGE", "TREND_DOWN"],
            "secondary_code": [None, "BK_UPWARD", None, None],
            "confidence": [0.5, 0.7, 0.5, 0.85],
        },
        index=index,
    )


def test_source_follow_events_flip_only_exact_recipe_c() -> None:
    fade = extract_source_fade_events(_labels())

    follow = extract_source_follow_events(_labels())

    expected = fade.copy(deep=True)
    expected["recipe_id"] = "follow_td_eu"
    expected["side"] = "short"
    pd.testing.assert_frame_equal(follow, expected)


def test_source_follow_session_controls_partition_trend_down_onsets() -> None:
    index = pd.date_range("2026-07-27T00:00:00Z", periods=7, freq="4h")
    labels = pd.DataFrame(
        {
            "primary_code": [
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_DOWN",
                "RANGE",
            ],
            "secondary_code": [None] * 7,
            "confidence": [0.5, 0.8, 0.5, 0.9, 0.5, 0.85, 0.5],
        },
        index=index,
    )

    asia = extract_source_follow_asia_events(labels)
    all_day = extract_source_follow_all_day_events(labels)
    early = extract_source_follow_session_06_15_events(labels)
    late = extract_source_follow_session_08_17_events(labels)
    us = extract_source_follow_us_events(labels)

    assert len(all_day) == 3
    assert all_day["recipe_id"].eq("follow_td_all_day").all()
    assert early["label_time_utc"].tolist() == [pd.Timestamp("2026-07-27T12:00Z")]
    assert late["label_time_utc"].tolist() == [pd.Timestamp("2026-07-27T12:00Z")]
    assert asia["label_time_utc"].tolist() == [pd.Timestamp("2026-07-27T04:00Z")]
    assert us["label_time_utc"].tolist() == [pd.Timestamp("2026-07-27T20:00Z")]
    assert asia["recipe_id"].tolist() == ["follow_td_asia_control"]
    assert us["recipe_id"].tolist() == ["follow_td_us_control"]
    assert asia["side"].tolist() == us["side"].tolist() == ["short"]
    assert asia["maximum_hold_seconds"].tolist() == [86_400.0]


def test_source_follow_early_confidence_challenger_retains_seventy_or_more() -> None:
    index = pd.date_range("2026-07-27T05:55:00Z", periods=6, freq="5min")
    labels = pd.DataFrame(
        {
            "primary_code": [
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_DOWN",
            ],
            "secondary_code": [None] * 6,
            "confidence": [0.5, 0.69, 0.5, 0.70, 0.5, 0.95],
        },
        index=index,
    )

    events = extract_source_follow_session_06_15_confidence_70_events(labels)

    assert events["confidence"].tolist() == [0.70, 0.95]
    assert events["recipe_id"].eq("follow_td_session_06_15_conf70").all()


def test_source_follow_all_day_confidence_challenger_has_no_clock_gate() -> None:
    index = pd.date_range("2026-07-27T00:00:00Z", periods=6, freq="4h")
    labels = pd.DataFrame(
        {
            "primary_code": [
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_DOWN",
            ],
            "secondary_code": [None] * 6,
            "confidence": [0.5, 0.69, 0.5, 0.70, 0.5, 0.95],
        },
        index=index,
    )

    events = extract_source_follow_all_day_confidence_70_events(labels)

    assert events["confidence"].tolist() == [0.70, 0.95]
    assert events["label_time_utc"].tolist() == [
        pd.Timestamp("2026-07-27T12:00Z"),
        pd.Timestamp("2026-07-27T20:00Z"),
    ]
    assert events["recipe_id"].eq("follow_td_all_day_conf70").all()


def test_source_breakout_events_select_only_exact_recipe_b() -> None:
    breakout = extract_source_breakout_events(_labels())

    assert breakout["recipe_id"].tolist() == ["bk_up_asia_conf06"]
    assert breakout["side"].tolist() == ["long"]
    assert breakout["maximum_hold_seconds"].tolist() == [14_400.0]


def test_maker_replay_discloses_exact_source_direction_contracts() -> None:
    module = _load_script()

    fade = module._experiment_contract("source-fade-only")
    follow = module._experiment_contract("source-follow-only")
    all_day = module._experiment_contract("source-follow-all-day")
    all_day_confidence = module._experiment_contract(
        "source-follow-all-day-confidence-70"
    )
    opposite_exit = module._experiment_contract("source-follow-all-day-opposite-exit")
    margin_stop = module._experiment_contract("source-follow-all-day-margin-stop")
    early = module._experiment_contract("source-follow-session-06-15")
    early_confidence = module._experiment_contract(
        "source-follow-session-06-15-confidence-70"
    )
    early_peak = module._experiment_contract(
        "source-follow-session-06-15-confidence-70-peak-tier0"
    )
    early_spread = module._experiment_contract(
        "source-follow-session-06-15-confidence-70-spread-1"
    )
    late = module._experiment_contract("source-follow-session-08-17")
    asia = module._experiment_contract("source-follow-asia-only")
    us = module._experiment_contract("source-follow-us-only")
    breakout = module._experiment_contract("source-breakout-only")

    assert fade["event_policy"] == "pinned_source_recipe_c_fade_only"
    assert follow["event_policy"] == "pinned_source_recipe_c_follow_only"
    assert all_day["event_policy"] == "trend_down_all_day_operational_control"
    assert all_day_confidence["event_policy"] == (
        "trend_down_all_day_minimum_confidence_0_70_development"
    )
    assert all_day_confidence["minimum_source_confidence"] == 0.70
    assert opposite_exit["event_policy"] == "trend_down_all_day_opposite_source_exit"
    assert opposite_exit["opposite_regime_exit"] is True
    assert margin_stop["event_policy"] == "trend_down_all_day_margin_stop_grid"
    assert early["event_policy"] == "trend_down_session_06_15_sensitivity"
    assert early_confidence["event_policy"] == (
        "trend_down_session_06_15_minimum_confidence_0_70_development"
    )
    assert early_confidence["minimum_source_confidence"] == 0.70
    assert early_confidence["selection_is_promotion"] is False
    assert early_peak["event_policy"] == (
        "trend_down_session_06_15_confidence_0_70_source_peak_tier0_development"
    )
    assert early_peak["minimum_source_confidence"] == 0.70
    assert early_peak["peak_protection_policy"] == ("source tier0: +6% peak, lock 55%")
    assert early_spread["event_policy"] == (
        "trend_down_session_06_15_confidence_0_70_spread_1_0_development"
    )
    assert early_spread["minimum_source_confidence"] == 0.70
    assert early_spread["maximum_entry_spread_bps"] == 1.0
    assert late["event_policy"] == "trend_down_session_08_17_sensitivity"
    assert asia["event_policy"] == "trend_down_asia_negative_control"
    assert us["event_policy"] == "trend_down_us_negative_control"
    assert breakout["event_policy"] == "pinned_source_recipe_b_breakout_only"
    assert follow["model_authority"] == "observe"
    assert follow["runtime_strategy_changed"] is False


def test_maker_replay_routes_session_negative_controls(tmp_path: Path) -> None:
    module = _load_script()
    index = pd.date_range("2026-07-27T00:00:00Z", periods=7, freq="4h")
    labels = pd.DataFrame(
        {
            "primary_code": [
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_DOWN",
                "RANGE",
            ],
            "secondary_code": [None] * 7,
            "confidence": [0.5, 0.8, 0.5, 0.9, 0.5, 0.85, 0.5],
        },
        index=index,
    )
    path = tmp_path / "labels.parquet"
    labels.to_parquet(path)

    asia = module._events(path, [], None, "source-follow-asia-only")
    all_day = module._events(path, [], None, "source-follow-all-day")
    opposite_exit = module._events(
        path, [], None, "source-follow-all-day-opposite-exit"
    )
    margin_stop = module._events(path, [], None, "source-follow-all-day-margin-stop")
    early = module._events(path, [], None, "source-follow-session-06-15")
    early_confidence = module._events(
        path, [], None, "source-follow-session-06-15-confidence-70"
    )
    early_peak = module._events(
        path, [], None, "source-follow-session-06-15-confidence-70-peak-tier0"
    )
    early_spread = module._events(
        path, [], None, "source-follow-session-06-15-confidence-70-spread-1"
    )
    late = module._events(path, [], None, "source-follow-session-08-17")
    us = module._events(path, [], None, "source-follow-us-only")

    assert len(all_day) == 3
    assert all_day["recipe_id"].eq("follow_td_all_day").all()
    pd.testing.assert_frame_equal(opposite_exit, all_day)
    pd.testing.assert_frame_equal(margin_stop, all_day)
    assert early["recipe_id"].tolist() == ["follow_td_session_06_15"]
    assert early_confidence["recipe_id"].tolist() == ["follow_td_session_06_15_conf70"]
    assert early_confidence["confidence"].tolist() == [0.9]
    pd.testing.assert_frame_equal(early_peak, early_confidence)
    pd.testing.assert_frame_equal(early_spread, early_confidence)
    assert late["recipe_id"].tolist() == ["follow_td_session_08_17"]
    assert asia["recipe_id"].tolist() == ["follow_td_asia_control"]
    assert us["recipe_id"].tolist() == ["follow_td_us_control"]


def test_source_direction_families_route_identical_recipe_c_times(
    tmp_path: Path,
) -> None:
    module = _load_script()
    path = tmp_path / "labels.parquet"
    _labels().to_parquet(path)

    fade = module._events(path, [], None, "source-fade-only")
    follow = module._events(path, [], None, "source-follow-only")
    breakout = module._events(path, [], None, "source-breakout-only")

    pd.testing.assert_series_equal(
        fade["decision_time_utc"], follow["decision_time_utc"]
    )
    assert fade["recipe_id"].tolist() == ["fade_td_eu"]
    assert fade["side"].tolist() == ["long"]
    assert follow["recipe_id"].tolist() == ["follow_td_eu"]
    assert follow["side"].tolist() == ["short"]
    assert follow["maximum_hold_seconds"].tolist() == [86_400.0]
    assert breakout["recipe_id"].tolist() == ["bk_up_asia_conf06"]
    assert breakout["side"].tolist() == ["long"]
