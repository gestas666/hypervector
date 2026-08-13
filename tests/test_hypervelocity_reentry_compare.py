"""Bounded same-regime re-entry comparison tests."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hypervelocity_reentry_compare import (
    bounded_target_ladder_candidate_matrix,
    evaluate_original_alignment,
    mature_target_continuation_candidate_matrix,
    reentry_candidate_matrix,
    screen_bounded_target_ladder_candidates,
    screen_reentry_candidates,
    screen_target_rsi_candidates,
    screen_target_continuation_candidates,
    source_episode_compatibility,
    target_continuation_candidate_matrix,
    target_rsi_candidate_matrix,
)


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=10, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * 10,
            "high": [100.0, 100.25, 100.0, 100.25, 100.0] * 2,
            "low": [100.0] * 10,
            "close": [100.0] * 10,
            "volume": [1.0] * 10,
        },
        index=index,
    )


def _decisions(bars: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "entry_direction": ["long"] * len(bars),
            "structural_direction": ["long"] * len(bars),
            "rsi_cross_direction": [
                None,
                "BK_UPWARD",
                None,
                None,
                "BK_UPWARD",
                None,
                None,
                None,
                None,
                None,
            ],
        },
        index=bars.index,
    )


def _positions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time_utc": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:02:30Z",
                "2026-01-01T00:06:40Z",
            ],
            "close_time_utc": [
                "2026-01-01T00:01:00Z",
                "2026-01-01T00:03:30Z",
                "2026-01-01T00:07:40Z",
            ],
            "side": ["long", "long", "long"],
            "entry_price": [100.0, 101.0, 102.0],
            "exit_price": [100.2, 101.2, 102.2],
            "status": ["closed", "closed", "closed"],
        }
    )


def test_reentry_matrix_is_predeclared_and_bounded() -> None:
    candidates = reentry_candidate_matrix()

    assert [candidate.candidate_id for candidate in candidates] == [
        "regime_reset_60s",
        "cooldown_only_60s",
        "cooldown_only_120s",
        "cooldown_only_300s",
    ]
    assert [candidate.cooldown_seconds for candidate in candidates] == [
        60.0,
        60.0,
        120.0,
        300.0,
    ]


def test_original_alignment_separates_regime_reset_from_cooldown() -> None:
    candidates = {item.candidate_id: item for item in reentry_candidate_matrix()}
    decisions = _decisions(_bars())

    reset = evaluate_original_alignment(
        _positions(), decisions, candidates["regime_reset_60s"]
    )
    sixty = evaluate_original_alignment(
        _positions(), decisions, candidates["cooldown_only_60s"]
    )
    two_minutes = evaluate_original_alignment(
        _positions(), decisions, candidates["cooldown_only_120s"]
    )
    five_minutes = evaluate_original_alignment(
        _positions(), decisions, candidates["cooldown_only_300s"]
    )

    assert reset["same_side_reentries"] == 2
    assert reset["eligible_same_side_reentries"] == 0
    assert sixty["eligible_same_side_reentries"] == 2
    assert two_minutes["eligible_same_side_reentries"] == 1
    assert five_minutes["eligible_same_side_reentries"] == 0


def test_original_alignment_requires_entry_direction_at_source_open() -> None:
    positions = _positions().iloc[:2].copy()
    decisions = _decisions(_bars())
    decisions.loc[decisions.index[1], "structural_direction"] = "short"
    decisions.loc[decisions.index[1], "entry_direction"] = "short"
    candidate = {item.candidate_id: item for item in reentry_candidate_matrix()}[
        "regime_reset_60s"
    ]

    alignment = evaluate_original_alignment(positions, decisions, candidate)

    assert alignment["policy_eligible_same_side_reentries"] == 1
    assert alignment["eligible_same_side_reentries"] == 0
    assert alignment["direction_mismatched_same_side_reentries"] == 1


def test_original_alignment_reconciles_duplicate_source_records() -> None:
    positions = _positions().iloc[:2].copy()
    positions["record_source"] = ["position_peak_only", "trade_only"]
    positions["symbol"] = "BTC"
    positions["side"] = "long"
    positions["entry_price"] = 100.0
    positions["quantity"] = 0.01
    positions["close_time_utc"] = [
        "2026-01-01T00:03:00Z",
        "2026-01-01T00:03:05Z",
    ]
    candidate = reentry_candidate_matrix()[0]

    alignment = evaluate_original_alignment(positions, _decisions(_bars()), candidate)

    assert alignment["source_rows"] == 2
    assert alignment["logical_positions"] == 1


def test_target_continuation_matrix_is_fixed_to_three_clearances() -> None:
    candidates = target_continuation_candidate_matrix()

    assert [candidate.candidate_id for candidate in candidates] == [
        "regime_reset_60s",
        "target_continuation_0bps",
        "target_continuation_1bps",
        "target_continuation_3bps",
    ]
    assert [candidate.clearance_bps for candidate in candidates] == [
        0.0,
        0.0,
        1.0,
        3.0,
    ]


def test_bounded_target_ladder_matrix_is_exact_and_source_bounded() -> None:
    candidates = bounded_target_ladder_candidate_matrix()

    assert [candidate.candidate_id for candidate in candidates] == [
        "regime_reset_60s",
        "target_ladder_cap2",
        "target_ladder_cap3",
        "target_ladder_cap6",
    ]
    assert [candidate.target_limit_per_episode for candidate in candidates] == [
        None,
        2,
        3,
        6,
    ]
    assert [candidate.clearance_bps for candidate in candidates] == [0.0] * 4


def test_mature_continuation_matrix_freezes_one_challenger() -> None:
    candidates = mature_target_continuation_candidate_matrix()

    assert [candidate.candidate_id for candidate in candidates] == [
        "regime_reset_60s",
        "target_ladder_cap2",
        "mature_target_ladder_cap2",
    ]
    assert [candidate.minimum_episode_seconds for candidate in candidates] == [
        0.0,
        0.0,
        1_800.0,
    ]
    assert [candidate.minimum_episode_bars for candidate in candidates] == [0, 0, 30]


def test_source_episode_compatibility_merges_supplemental_and_caps_counts() -> None:
    supplemental = pd.DataFrame(
        {
            "open_time_utc": ["2026-01-01T00:08:00Z"],
            "side": ["short"],
            "entry_price": [99.0],
        }
    )
    decisions = _decisions(_bars())
    decisions.index = decisions.index - pd.Timedelta(minutes=1)

    result = source_episode_compatibility(
        _positions(),
        decisions,
        supplemental=supplemental,
        limits=(2, 3, 6),
    )

    assert result == {
        "source_rows": 3,
        "supplemental_rows": 1,
        "logical_positions": 4,
        "direction_matched_positions": 3,
        "direction_mismatched_positions": 1,
        "matched_regime_episodes": 1,
        "repeated_regime_episodes": 1,
        "entries_in_repeated_episodes": 3,
        "maximum_entries_per_episode": 3,
        "entries_per_episode_distribution": {"3": 1},
        "timestamp_provenance_counts": {
            "screenshot_outcome_backed": 1,
            "tracker_only": 3,
        },
        "limit_compatibility": {
            "2": {"preserved_entries": 2, "preserved_entries_pct": 200.0 / 3.0},
            "3": {"preserved_entries": 3, "preserved_entries_pct": 100.0},
            "6": {"preserved_entries": 3, "preserved_entries_pct": 100.0},
        },
    }


def test_target_alignment_uses_prior_exit_as_price_reference() -> None:
    positions = _positions()
    positions["entry_price"] = [100.0, 100.21, 100.24]
    positions["exit_price"] = [100.2, 100.22, 100.26]
    decisions = _decisions(_bars())
    candidates = {
        item.candidate_id: item for item in target_continuation_candidate_matrix()
    }

    zero = evaluate_original_alignment(
        positions, decisions, candidates["target_continuation_0bps"]
    )
    one = evaluate_original_alignment(
        positions, decisions, candidates["target_continuation_1bps"]
    )
    three = evaluate_original_alignment(
        positions, decisions, candidates["target_continuation_3bps"]
    )

    assert zero["eligible_same_side_reentries"] == 2
    assert one["eligible_same_side_reentries"] == 1
    assert three["eligible_same_side_reentries"] == 0
    assert zero["missing_continuation_reference"] == 0
    assert zero["source_target_outcomes_available"] is False


def test_screen_retains_every_candidate_and_reports_trade_cadence() -> None:
    bars = _bars()

    results = screen_reentry_candidates(bars, _decisions(bars), _positions())

    assert len(results) == 4
    assert {row["candidate"]["candidate_id"] for row in results} == {
        "regime_reset_60s",
        "cooldown_only_60s",
        "cooldown_only_120s",
        "cooldown_only_300s",
    }
    assert all("final_marked_equity" in row["serial"] for row in results)
    assert all("completed_trades_per_day" in row["serial"] for row in results)
    assert all(
        "eligible_same_side_reentries" in row["original_alignment"] for row in results
    )


def test_target_screen_retains_control_and_three_challengers() -> None:
    bars = _bars()

    results = screen_target_continuation_candidates(
        bars, _decisions(bars), _positions()
    )

    assert len(results) == 4
    assert {row["candidate"]["candidate_id"] for row in results} == {
        "regime_reset_60s",
        "target_continuation_0bps",
        "target_continuation_1bps",
        "target_continuation_3bps",
    }


def test_bounded_target_ladder_screen_retains_every_candidate() -> None:
    bars = _bars()

    results = screen_bounded_target_ladder_candidates(
        bars, _decisions(bars), _positions()
    )

    assert [row["candidate"]["candidate_id"] for row in results] == [
        "regime_reset_60s",
        "target_ladder_cap2",
        "target_ladder_cap3",
        "target_ladder_cap6",
    ]
    assert [row["candidate"]["target_limit_per_episode"] for row in results] == [
        None,
        2,
        3,
        6,
    ]


def test_target_rsi_matrix_has_one_predeclared_challenger() -> None:
    candidates = target_rsi_candidate_matrix()

    assert [candidate.candidate_id for candidate in candidates] == [
        "regime_reset_60s",
        "target_rsi_reconfirmation_60s",
    ]


def test_target_rsi_alignment_requires_a_causal_cross_in_each_window() -> None:
    candidates = {item.candidate_id: item for item in target_rsi_candidate_matrix()}

    alignment = evaluate_original_alignment(
        _positions(),
        _decisions(_bars()),
        candidates["target_rsi_reconfirmation_60s"],
    )

    assert alignment["same_side_reentries"] == 2
    assert alignment["eligible_same_side_reentries"] == 2


def test_target_rsi_screen_retains_control_and_challenger() -> None:
    bars = _bars()

    results = screen_target_rsi_candidates(bars, _decisions(bars), _positions())

    assert [row["candidate"]["candidate_id"] for row in results] == [
        "regime_reset_60s",
        "target_rsi_reconfirmation_60s",
    ]
