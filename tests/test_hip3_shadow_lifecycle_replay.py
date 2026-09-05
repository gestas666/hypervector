"""Causal report-only HIP-3 shadow lifecycle replay tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.research.hip3_shadow_lifecycle_replay import (
    build_hip3_shadow_lifecycle_replay,
)
from hypervector.research.hip3_shadow_lifecycle_archive_marks import (
    HIP3_ARCHIVE_REPAIR_MARK_SOURCE,
)
from hip3_shadow_lifecycle_fixtures import (
    book as _book,
    candles as _candles,
    decision_time as _decision_time,
    decisions as _decisions,
    funding as _funding,
    lifecycle_config as _config,
    mark as _mark,
    marks as _marks,
    timestamp as _timestamp,
)


def test_lifecycle_config_rejects_aliased_identity_and_invalid_costs() -> None:
    config = _config()

    with pytest.raises(ValueError, match="identity"):
        replace(config, provider_id="hip3_other_provider")
    with pytest.raises(ValueError, match="fee"):
        replace(config, fee_bps_per_side=-0.1)
    with pytest.raises(ValueError, match="stress"):
        replace(config, stress_extra_bps_per_side=-0.1)
    with pytest.raises(ValueError, match="notional"):
        replace(config, notional_usd=0.0)
    with pytest.raises(ValueError, match="24 hours"):
        replace(config, maximum_hold_minutes=60)


def test_entry_signal_identity_is_reproduced_and_report_stays_authority_none() -> None:
    candles = _candles(long_onset_position=32, exit_position=35)
    decisions = _decisions(candles, eligible_position=32)
    entry_time = _decision_time(candles, 32) + 1_000
    exit_time = _decision_time(candles, 37) + 1_000
    books = (_book(entry_time, 102.0), _book(exit_time, 101.0))
    marks = _marks(entry_time, exit_time, 102.5)

    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions,
        book_rows=books,
        candles=candles,
        mark_rows=marks,
        funding_rows=_funding(candles),
        config=_config(),
    )

    assert report["execution_authority"] == "none"
    assert report["automatic_promotion"] is False
    assert report["runtime_strategy_changed"] is False
    assert report["replay_contract"]["notional_usd"] == 5_000.0
    assert report["replay_contract"]["fee_bps_per_side"] == 0.864
    assert report["replay_contract"]["maximum_stop_bps"] == 80.0
    assert report["source_reconciliation"]["eligible_journal_onsets"] == 1
    assert report["source_reconciliation"]["computed_onsets"] == 1
    assert report["nominal"]["completed_lifecycles"] == 1
    assert report["nominal"]["lifecycles"][0]["exit_reason"] == "signal"


def test_pre_entry_mark_low_does_not_trigger_but_post_entry_low_does() -> None:
    candles = _candles(long_onset_position=32, exit_position=36)
    decisions = _decisions(candles, eligible_position=32)
    decision_time = _decision_time(candles, 32)
    entry_time = decision_time + 10_000
    books = (
        _book(entry_time, 102.0),
        _book(entry_time + 20_000, 100.0),
        _book(_decision_time(candles, 36) + 1_000, 101.0),
    )
    marks = (
        *_marks(decision_time + 1_000, entry_time - 1, 1.0),
        *_marks(entry_time, entry_time + 10_000, 102.0),
        *_marks(entry_time + 11_000, entry_time + 19_000, 100.0),
    )

    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions,
        book_rows=books,
        candles=candles,
        mark_rows=marks,
        funding_rows=_funding(candles),
        config=_config(),
    )

    lifecycle = report["nominal"]["lifecycles"][0]
    assert lifecycle["exit_reason"] == "stop"
    assert lifecycle["entry_time_ms"] == entry_time
    assert lifecycle["stop_trigger_time_ms"] > entry_time


def test_incomplete_mark_path_censors_instead_of_success_shaping() -> None:
    candles = _candles(long_onset_position=32, exit_position=35)
    decisions = _decisions(candles, eligible_position=32)
    entry_time = _decision_time(candles, 32) + 1_000
    books = (
        _book(entry_time, 100.0),
        _book(_decision_time(candles, 35) + 1_000, 101.0),
    )
    sparse_marks = (_mark(entry_time, 100.0), _mark(entry_time + 20_000, 100.0))

    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions,
        book_rows=books,
        candles=candles,
        mark_rows=sparse_marks,
        funding_rows=_funding(candles),
        config=_config(),
    )

    assert report["nominal"]["completed_lifecycles"] == 0
    assert report["nominal"]["censored_lifecycles"] == 1
    assert report["technical_assessment"]["all_lifecycle_paths_resolved"] is False


def test_rest_marks_cannot_certify_an_exact_lifecycle_path() -> None:
    """Receipt-timestamped REST contexts remain supplemental after parity failed."""
    candles = _candles(long_onset_position=32, exit_position=35)
    decisions = _decisions(candles, eligible_position=32)
    entry_time = _decision_time(candles, 32) + 1_000
    exit_time = _decision_time(candles, 37) + 1_000
    rest_marks = tuple(
        {**row, "source": "hyperliquid_info_metaAndAssetCtxs"}
        for row in _marks(entry_time, exit_time, 102.5)
    )

    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions,
        book_rows=(_book(entry_time, 102.0), _book(exit_time, 101.0)),
        candles=candles,
        mark_rows=rest_marks,
        funding_rows=_funding(candles),
        config=_config(),
    )

    assert report["nominal"]["completed_lifecycles"] == 0
    assert report["nominal"]["censored"][0]["reason"] == "mark_path_unresolved"
    assert report["source_reconciliation"]["exact_websocket_mark_rows"] == 0
    assert report["source_reconciliation"]["supplemental_rest_mark_rows"] > 0


def test_exact_archive_repair_marks_can_trigger_the_frozen_stop() -> None:
    candles = _candles(long_onset_position=32, exit_position=36)
    decisions = _decisions(candles, eligible_position=32)
    decision_time = _decision_time(candles, 32)
    entry_time = decision_time + 10_000
    stop_time = entry_time + 11_000
    books = (
        _book(entry_time, 102.0),
        _book(stop_time, 100.0),
        _book(_decision_time(candles, 36) + 1_000, 101.0),
    )
    marks = tuple(
        {
            **row,
            "source": HIP3_ARCHIVE_REPAIR_MARK_SOURCE,
            "mark_price": 100.0 if int(row["observed_ts_ms"]) >= stop_time else 102.0,
        }
        for row in _marks(entry_time, stop_time + 10_000, 102.0)
    )

    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions,
        book_rows=books,
        candles=candles,
        mark_rows=marks,
        funding_rows=_funding(candles),
        config=_config(),
    )

    lifecycle = report["nominal"]["lifecycles"][0]
    assert lifecycle["exit_reason"] == "stop"
    assert lifecycle["stop_trigger_time_ms"] == stop_time
    assert report["source_reconciliation"]["exact_archive_repair_mark_rows"] > 0
    assert report["source_reconciliation"]["exact_mark_sources"] == [
        "hyperliquid_ws_activeAssetCtx",
        HIP3_ARCHIVE_REPAIR_MARK_SOURCE,
    ]


def test_post_entry_censor_blocks_onsets_until_route_is_proven_flat() -> None:
    candles = _candles(long_onset_position=32, exit_position=35, second_onset=34)
    decisions = _decisions(candles, eligible_positions={32, 34})
    entry_time = _decision_time(candles, 32) + 1_000
    exit_time = _decision_time(candles, 37) + 1_000
    books = (_book(entry_time, 102.0), _book(exit_time, 101.0))
    sparse_marks = (_mark(entry_time, 102.0), _mark(entry_time + 20_000, 102.0))

    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions,
        book_rows=books,
        candles=candles,
        mark_rows=sparse_marks,
        funding_rows=_funding(candles),
        config=_config(),
    )

    assert report["nominal"]["completed_lifecycles"] == 0
    assert [row["reason"] for row in report["nominal"]["censored"]] == [
        "mark_path_unresolved",
        "portfolio_state_unresolved",
    ]
    assert report["nominal"]["censored"][0]["entry_time_ms"] == entry_time
    assert report["nominal"]["censored"][0]["route_state_resolved_time_ms"] == exit_time


def test_official_candle_source_identity_is_required() -> None:
    candles = _candles(long_onset_position=32, exit_position=35)
    candles["source"] = "unverified_proxy"

    with pytest.raises(ValueError, match="candle source"):
        build_hip3_shadow_lifecycle_replay(
            decision_rows=_decisions(candles, eligible_positions={32}),
            book_rows=(),
            candles=candles,
            mark_rows=(),
            funding_rows=_funding(candles),
            config=_config(),
        )


@pytest.mark.parametrize(("side", "expected_sign"), (("long", -1), ("short", 1)))
def test_positive_funding_is_charged_directionally(
    side: str, expected_sign: int
) -> None:
    candles = _candles(long_onset_position=32, exit_position=37, side=side)
    entry_time = _decision_time(candles, 32) + 1_000
    exit_time = _decision_time(candles, 39) + 1_000
    funding = _funding(candles)
    inside = (funding["timestamp"] > _timestamp(entry_time)) & (
        funding["timestamp"] <= _timestamp(exit_time)
    )
    funding.loc[inside, "funding_rate"] = 0.001
    entry_midpoint = 102.0 if side == "long" else 98.0
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=_decisions(candles, eligible_positions={32}, side=side),
        book_rows=(_book(entry_time, entry_midpoint), _book(exit_time, 101.0)),
        candles=candles,
        mark_rows=_marks(entry_time, exit_time, entry_midpoint),
        funding_rows=funding,
        config=_config(),
    )

    cashflow = report["nominal"]["lifecycles"][0]["funding_cashflow_usd"]
    assert cashflow * expected_sign > 0.0


def test_maximum_hold_is_secondary_exit_and_uses_exact_wall_clock() -> None:
    candles = _candles(
        long_onset_position=32, exit_position=None, periods=140, side="long"
    )
    decision_time = _decision_time(candles, 32)
    entry_time = decision_time + 1_000
    deadline = decision_time + 24 * 60 * 60_000
    config = replace(_config(), maximum_mark_gap_ms=60_000)
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=_decisions(candles, eligible_positions={32}),
        book_rows=(_book(entry_time, 102.0), _book(deadline, 103.0)),
        candles=candles,
        mark_rows=_marks(entry_time, deadline, 102.5, step_ms=30_000),
        funding_rows=_funding(candles),
        config=config,
    )

    lifecycle = report["nominal"]["lifecycles"][0]
    assert lifecycle["exit_reason"] == "max_hold"
    assert lifecycle["exit_time_ms"] == deadline


def test_overlapping_onset_is_suppressed_while_first_lifecycle_is_open() -> None:
    candles = _candles(long_onset_position=32, exit_position=35, second_onset=34)
    entry_time = _decision_time(candles, 32) + 1_000
    exit_time = _decision_time(candles, 37) + 1_000
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=_decisions(candles, eligible_positions={32, 34}),
        book_rows=(_book(entry_time, 102.0), _book(exit_time, 101.0)),
        candles=candles,
        mark_rows=_marks(entry_time, exit_time, 102.5),
        funding_rows=_funding(candles),
        config=_config(),
    )

    assert report["nominal"]["completed_lifecycles"] == 1
    assert report["nominal"]["suppressed_overlapping_onsets"] == 1


def test_insufficient_entry_depth_is_censored() -> None:
    candles = _candles(long_onset_position=32, exit_position=35)
    decision_time = _decision_time(candles, 32)
    shallow = _book(decision_time + 1_000, 102.0, size=0.001)
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=_decisions(candles, eligible_positions={32}),
        book_rows=(shallow,),
        candles=candles,
        mark_rows=(),
        funding_rows=_funding(candles),
        config=_config(),
    )

    assert report["nominal"]["completed_lifecycles"] == 0
    assert report["nominal"]["censored"][0]["reason"] == "entry_depth_incomplete"


def test_trailing_funding_gap_rejects_completed_lifecycle() -> None:
    candles = _candles(long_onset_position=32, exit_position=37)
    entry_time = _decision_time(candles, 32) + 1_000
    exit_time = _decision_time(candles, 39) + 1_000
    funding = _funding(candles)
    funding = funding.loc[funding["timestamp"] < _timestamp(exit_time).floor("h")]

    with pytest.raises(ValueError, match="lifecycle funding coverage"):
        build_hip3_shadow_lifecycle_replay(
            decision_rows=_decisions(candles, eligible_positions={32}),
            book_rows=(_book(entry_time, 102.0), _book(exit_time, 101.0)),
            candles=candles,
            mark_rows=_marks(entry_time, exit_time, 102.0),
            funding_rows=funding,
            config=_config(),
        )


def test_summary_reports_long_and_short_results_separately() -> None:
    candles = _candles(long_onset_position=32, exit_position=35)
    entry_time = _decision_time(candles, 32) + 1_000
    exit_time = _decision_time(candles, 37) + 1_000
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=_decisions(candles, eligible_positions={32}),
        book_rows=(_book(entry_time, 102.0), _book(exit_time, 101.0)),
        candles=candles,
        mark_rows=_marks(entry_time, exit_time, 102.5),
        funding_rows=_funding(candles),
        config=_config(),
    )

    assert report["nominal"]["by_side"]["long"]["lifecycles"] == 1
    assert report["nominal"]["by_side"]["short"]["lifecycles"] == 0


def test_missing_pressure_row_does_not_fabricate_a_market_candle_gap() -> None:
    candles = _candles(long_onset_position=32, exit_position=35)
    decisions = list(_decisions(candles, eligible_positions={32}))
    del decisions[10]
    entry_time = _decision_time(candles, 32) + 1_000
    exit_time = _decision_time(candles, 37) + 1_000

    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions,
        book_rows=(_book(entry_time, 102.0), _book(exit_time, 101.0)),
        candles=candles,
        mark_rows=_marks(entry_time, exit_time, 102.5),
        funding_rows=_funding(candles),
        config=_config(),
    )

    assert report["nominal"]["completed_lifecycles"] == 1
    assert report["source_reconciliation"]["unobserved_pressure_bars"] == 1


def test_distinct_same_millisecond_marks_preserve_nanosecond_order() -> None:
    candles = _candles(long_onset_position=32, exit_position=36)
    entry_time = _decision_time(candles, 32) + 1_000
    trigger_time = entry_time + 10_000
    low = _mark(trigger_time, 100.0)
    low["received_ts_ns"] = trigger_time * 1_000_000 + 500_000
    marks = (
        *_marks(entry_time, trigger_time, 102.5),
        low,
        _mark(trigger_time + 1, 100.0),
    )

    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=_decisions(candles, eligible_positions={32}),
        book_rows=(
            _book(entry_time, 102.0),
            _book(trigger_time + 1, 100.0),
        ),
        candles=candles,
        mark_rows=marks,
        funding_rows=_funding(candles),
        config=_config(),
    )

    lifecycle = report["nominal"]["lifecycles"][0]
    assert lifecycle["exit_reason"] == "stop"
    assert lifecycle["stop_trigger_time_ms"] == trigger_time + 1
