"""Tests for report-only creator selective-recipe interpretation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.hypervelocity_selective_recipe import (
    SELECTIVE_RECIPE_CANDIDATES,
    SELECTIVE_REPLAY_CANDIDATES,
    align_creator_recipe_entries,
    build_selective_recipe_events,
    load_selective_recipe_bars,
    selective_recipe_replay_inputs,
    summarize_selective_recipe_alignment,
)


def test_bar_loader_accepts_multiple_contiguous_evidence_files(
    tmp_path: Path,
) -> None:
    """Forward replay may extend the warmup history with more than one day."""
    paths: list[Path] = []
    for offset in range(3):
        path = tmp_path / f"bars-{offset}.parquet"
        timestamp = pd.Timestamp("2026-07-27T00:00:00Z") + pd.Timedelta(minutes=offset)
        pd.DataFrame(
            {
                "timestamp": [timestamp],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1.0],
            }
        ).to_parquet(path)
        paths.append(path)

    bars = load_selective_recipe_bars(*paths)

    assert len(bars) == 3
    assert bars.index[-1] == pd.Timestamp("2026-07-27T00:02:00Z")


def _decision_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2026-07-21T06:56:00Z", periods=10, freq="1min")
    decisions = pd.DataFrame(
        {
            "primary_regime": [
                "TREND_UP",
                "BREAKOUT",
                "BREAKOUT",
                "TREND_UP",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_DOWN",
            ],
            "breakout_direction": [
                None,
                "BK_UPWARD",
                "BK_UPWARD",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ],
            "state_1m": [
                "RANGE",
                "RANGE",
                "BREAKOUT",
                "TREND_UP",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_UP",
                "TREND_UP",
                "TREND_DOWN",
                "TREND_UP",
            ],
            "state_5m": [
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_DOWN",
            ],
            "structural_direction": [
                "long",
                "long",
                "long",
                "long",
                "long",
                "short",
                "short",
                "short",
                "short",
                "short",
            ],
            "confidence": [0.4, 0.7, 0.5, 0.8, 0.7, 0.55, 0.65, 0.6, 0.5, 0.7],
        },
        index=index,
    )
    raw_1m = pd.DataFrame(
        {
            "primary_regime": [
                "RANGE",
                "RANGE",
                "BREAKOUT",
                "TREND_UP",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_UP",
                "TREND_UP",
                "TREND_DOWN",
                "TREND_UP",
            ],
            "breakout_direction": [
                None,
                None,
                "BK_UPWARD",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ],
        },
        index=index,
    )
    return decisions, raw_1m


def test_candidate_family_and_causal_events_are_exact() -> None:
    assert SELECTIVE_RECIPE_CANDIDATES == (
        "b_confirmed_5m_breakout_up_onset",
        "b_raw_1m_breakout_up_onset_in_5m_long",
        "b_1m_trend_up_onset_in_5m_long",
        "c_5m_trend_down_onset",
        "c_1m_trend_up_recovery_in_5m_down",
    )
    decisions, raw_1m = _decision_rows()

    events = build_selective_recipe_events(decisions, raw_1m)

    grouped = {
        candidate: group["event_time_utc"].tolist()
        for candidate, group in events.groupby("candidate_id", sort=False)
    }
    assert grouped[SELECTIVE_RECIPE_CANDIDATES[0]] == [
        pd.Timestamp("2026-07-21T06:58:00Z")
    ]
    assert grouped[SELECTIVE_RECIPE_CANDIDATES[1]] == [
        pd.Timestamp("2026-07-21T06:59:00Z")
    ]
    assert grouped[SELECTIVE_RECIPE_CANDIDATES[2]] == [
        pd.Timestamp("2026-07-21T07:00:00Z")
    ]
    assert grouped[SELECTIVE_RECIPE_CANDIDATES[3]] == [
        pd.Timestamp("2026-07-21T07:02:00Z")
    ]
    assert grouped[SELECTIVE_RECIPE_CANDIDATES[4]] == [
        pd.Timestamp("2026-07-21T07:03:00Z"),
        pd.Timestamp("2026-07-21T07:06:00Z"),
    ]
    assert events["side"].eq("long").all()
    assert (
        events.loc[
            events["event_time_utc"].eq(pd.Timestamp("2026-07-21T06:59:00Z")),
            "passes_current_confidence_06",
        ]
        .eq(False)
        .all()
    )


def test_session_masks_apply_to_available_event_time_without_boundary_pulses() -> None:
    decisions, raw_1m = _decision_rows()
    shifted = decisions.copy()
    shifted.index = shifted.index + pd.Timedelta(hours=7)
    raw_shifted = raw_1m.copy()
    raw_shifted.index = shifted.index

    events = build_selective_recipe_events(shifted, raw_shifted)

    assert not events["recipe_id"].eq("bk_up_asia_conf06").any()
    assert events["recipe_id"].eq("fade_td_eu").any()


def test_event_builder_rejects_unusable_decisions() -> None:
    decisions, raw_1m = _decision_rows()
    naive = decisions.copy()
    naive.index = naive.index.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        build_selective_recipe_events(naive, raw_1m)

    with pytest.raises(ValueError, match="share the same index"):
        build_selective_recipe_events(decisions, raw_1m.iloc[:-1])


def _source_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_id": ["c2", "b1", "c1"],
            "recipe_id": [
                "fade_td_eu",
                "bk_up_asia_conf06",
                "fade_td_eu",
            ],
            "side": ["long", "long", "long"],
            "entry_time_utc_inferred": [
                "2026-07-21T07:00:30Z",
                "2026-07-21T07:02:00Z",
                "2026-07-21T07:07:00Z",
            ],
        }
    )


def test_alignment_separates_backward_causality_from_nearest_sensitivity() -> None:
    decisions, raw_1m = _decision_rows()
    events = build_selective_recipe_events(decisions, raw_1m)

    aligned = align_creator_recipe_entries(_source_rows(), events)

    b = aligned.loc[
        aligned["candidate_id"].eq("b_1m_trend_up_onset_in_5m_long")
        & aligned["source_id"].eq("b1")
    ].iloc[0]
    assert b["causal_event_time_utc"] == pd.Timestamp("2026-07-21T07:00:00Z")
    assert b["causal_lag_seconds"] == 120.0
    assert bool(b["matched_within_maker_ttl"])
    assert bool(b["matched_within_maker_ttl_conf06"])

    c = aligned.loc[
        aligned["candidate_id"].eq("c_5m_trend_down_onset")
        & aligned["source_id"].eq("c2")
    ].iloc[0]
    assert pd.isna(c["causal_event_time_utc"])
    assert c["nearest_event_time_utc"] == pd.Timestamp("2026-07-21T07:02:00Z")
    assert c["nearest_offset_seconds"] == 90.0
    assert bool(c["nearest_is_future"])
    assert not bool(c["matched_within_maker_ttl"])


def test_alignment_summary_reports_coverage_and_unobserved_cadence() -> None:
    decisions, raw_1m = _decision_rows()
    events = build_selective_recipe_events(decisions, raw_1m)
    source = _source_rows()
    aligned = align_creator_recipe_entries(source, events)

    summary = summarize_selective_recipe_alignment(source, events, aligned)

    candidate = summary["b_1m_trend_up_onset_in_5m_long"]
    assert candidate["source_rows"] == 1
    assert candidate["matched_within_maker_ttl"] == 1
    assert candidate["source_coverage_pct"] == 100.0
    assert candidate["total_candidate_events"] == 1
    assert candidate["unobserved_event_count"] == 0
    assert candidate["precision_estimable"] is False


def test_alignment_rejects_duplicate_or_naive_source_rows() -> None:
    decisions, raw_1m = _decision_rows()
    events = build_selective_recipe_events(decisions, raw_1m)
    duplicate = pd.concat([_source_rows(), _source_rows().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="source_id"):
        align_creator_recipe_entries(duplicate, events)

    naive = _source_rows()
    naive["entry_time_utc_inferred"] = pd.to_datetime(
        naive["entry_time_utc_inferred"]
    ).dt.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        align_creator_recipe_entries(naive, events)

    unsorted = _source_rows().iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError, match="ordered"):
        align_creator_recipe_entries(unsorted, events)


def test_replay_inputs_freeze_closest_proxies_and_per_recipe_deadlines() -> None:
    decisions, raw_1m = _decision_rows()
    events = build_selective_recipe_events(decisions, raw_1m)

    grid, configs = selective_recipe_replay_inputs(decisions, events)

    assert SELECTIVE_REPLAY_CANDIDATES == (
        "b_trend_up_onset_all",
        "b_trend_up_onset_current_conf06",
        "c_trend_down_onset",
        "c_1m_recovery_in_5m_down",
        "combined_b_conf06_c",
    )
    assert tuple(grid) == SELECTIVE_REPLAY_CANDIDATES
    assert tuple(configs) == SELECTIVE_REPLAY_CANDIDATES
    assert all(config.fill_rule == "trade-through" for config in configs.values())
    assert all(config.fixed_margin_stop_pct is None for config in configs.values())
    assert all(config.maximum_hold_seconds is None for config in configs.values())

    b = grid["b_trend_up_onset_all"]
    c = grid["c_trend_down_onset"]
    recovery = grid["c_1m_recovery_in_5m_down"]
    combined = grid["combined_b_conf06_c"]
    assert b["entry_direction"].notna().sum() == 1
    assert (
        b.loc[b["entry_direction"].notna(), "maximum_hold_seconds"].iloc[0] == 14_400.0
    )
    assert c["entry_direction"].notna().sum() == 1
    assert (
        c.loc[c["entry_direction"].notna(), "maximum_hold_seconds"].iloc[0] == 86_400.0
    )
    assert recovery["entry_direction"].notna().sum() == 2
    assert (
        recovery.loc[recovery["entry_direction"].notna(), "maximum_hold_seconds"]
        .eq(86_400.0)
        .all()
    )
    assert combined["entry_direction"].notna().sum() == 2
    assert combined["structural_direction"].eq("long").sum() >= 6


def test_replay_inputs_reject_conflicting_recipe_events_at_one_minute() -> None:
    decisions, raw_1m = _decision_rows()
    events = build_selective_recipe_events(decisions, raw_1m)
    c = events.loc[events["candidate_id"].eq("c_5m_trend_down_onset")].iloc[0]
    conflict = events.copy()
    conflict.loc[
        conflict["candidate_id"].eq("b_1m_trend_up_onset_in_5m_long"),
        "event_time_utc",
    ] = c["event_time_utc"]

    with pytest.raises(ValueError, match="conflicting recipe deadlines"):
        selective_recipe_replay_inputs(decisions, conflict)
