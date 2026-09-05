"""Route-native SOL one-blocker forward-shadow contracts."""

from __future__ import annotations

import importlib.util

import pytest

from hypervector.data.hl_events import StreamGap
from hypervector.research.cohort_one_blocker_execution_types import Book
from hypervector.research.cohort_signal_candidates import SignalCandidate
from hypervector.research.market_depth_fill import DepthLevel
import hypervector.research.sol_route_native_one_blocker_shadow as subject

_RUN = "bidirectional-live-test"


def test_route_native_shadow_module_exists() -> None:
    """The predeclared SOL experiment has a dedicated report-only evaluator."""
    assert (
        importlib.util.find_spec(
            "hypervector.research.sol_route_native_one_blocker_shadow"
        )
        is not None
    )


def test_venue_mark_stop_precedes_a_later_opposite_signal() -> None:
    """The deployed stop has causal precedence over a later provider reversal."""
    assert hasattr(subject, "SolRouteNativeShadowSpec")
    assert hasattr(subject, "MarkObservation")
    assert hasattr(subject, "build_sol_route_native_one_blocker_shadow")
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(
            _candidate(60_000, "long", eligible=False),
            _candidate(180_000, "short", eligible=True, blockers=()),
        ),
        books=(
            _book(59_000, bid=99.9, ask=100.0),
            _book(61_000, bid=99.9, ask=100.0),
            _book(121_000, bid=99.0, ask=99.1),
            _book(181_000, bid=98.9, ask=99.0),
        ),
        marks=(subject.MarkObservation(120_000, 99.19),),
        funding_evidence=_funding(1, 300_000),
        gaps=(),
        spec=_spec(),
    )

    assert report["contract"]["execution_authority"] == "none"
    execution = report["contract"]["execution"]
    assert execution["candidate_rule"] == (
        "exact v51 SOL evaluation blocked only by awaiting_hourly_sma_cross"
    )
    assert execution["exit_rule"] == (
        "first venue-mark stop, eligible opposite signal, then 48h maximum hold"
    )
    assert execution["reentry_rule"] == (
        "one SOL position at a time; next independent episode onset after exit"
    )
    assert "opi_cohort" not in execution
    assert "minimum_entry_spacing_minutes" not in execution
    assert report["coverage"]["resolved_executions"] == 1
    assert report["executions"][0]["exit_reason"] == "venue_mark_stop"
    assert report["executions"][0]["exit_time_ms"] == 121_000


def test_consecutive_exact_rows_are_one_independent_episode() -> None:
    """A persistent setup cannot re-enter immediately after its first stop."""
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(
            _candidate(60_000, "long", eligible=False),
            _candidate(120_000, "long", eligible=False),
        ),
        books=(
            _book(59_000, bid=99.9, ask=100.0),
            _book(61_000, bid=99.9, ask=100.0),
            _book(91_000, bid=99.0, ask=99.1),
            _book(119_000, bid=99.0, ask=99.1),
            _book(121_000, bid=99.0, ask=99.1),
        ),
        marks=(subject.MarkObservation(90_000, 99.19),),
        funding_evidence=_funding(1, 300_000),
        gaps=(),
        spec=_spec(),
    )

    assert report["coverage"]["raw_exact_evaluations"] == 2
    assert report["coverage"]["exact_candidates"] == 1
    assert report["coverage"]["attempts"] == 1


def test_episode_active_before_cutoff_is_not_retroactively_opened() -> None:
    """A prospective shadow waits for a new post-cutoff setup transition."""
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(
            _candidate(60_000, "long", eligible=False),
            _candidate(120_000, "long", eligible=False),
        ),
        books=(_book(121_000, bid=99.9, ask=100.0),),
        marks=(subject.MarkObservation(122_000, 100.0),),
        funding_evidence=None,
        gaps=(),
        spec=_spec(cutoff_time_ms=100_000),
    )

    assert report["coverage"]["raw_exact_evaluations"] == 1
    assert report["coverage"]["exact_candidates"] == 0
    assert report["coverage"]["attempts"] == 0


def test_unelapsed_maximum_hold_remains_pending() -> None:
    """A quiet future deadline cannot become a fabricated missing exit."""
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(_candidate(60_000, "short", eligible=False),),
        books=(
            _book(59_000, bid=99.9, ask=100.0),
            _book(61_000, bid=99.9, ask=100.0),
            _book(120_000, bid=100.1, ask=100.2),
        ),
        marks=(subject.MarkObservation(119_000, 100.1),),
        funding_evidence=None,
        gaps=(),
        spec=_spec(),
    )

    assert report["coverage"]["resolved_executions"] == 0
    assert report["coverage"]["pending_or_unresolved"] == 1
    assert report["attempts"][0]["status"] == "exit_pending"


def test_pending_lifecycle_reports_causal_marked_economics() -> None:
    """A funded open shadow exposes executable trajectory without closing it."""
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(_candidate(60_000, "short", eligible=False),),
        books=(
            _book(59_000, bid=99.8, ask=99.9),
            _book(61_000, bid=99.9, ask=100.0),
            _book(120_000, bid=100.1, ask=100.2),
        ),
        marks=(subject.MarkObservation(119_000, 100.1),),
        funding_evidence=_funding(1, 120_000),
        gaps=(),
        spec=_spec(),
    )

    pending = report["attempts"][0]
    assert pending["status"] == "exit_pending"
    assert pending["entry_price"] == pytest.approx(99.9)
    assert pending["latest_book_time_ms"] == 120_000
    assert pending["current_estimated_net_return_bps"] < 0.0
    assert pending["mae_bps"] <= pending["mfe_bps"]
    assert pending["current_exit_visible_depth_capacity"] is True
    assert "exit_time_ms" not in pending


def test_pending_mark_uses_full_visible_depth_instead_of_thin_top() -> None:
    """The marked close walks the same depth contract as a resolved exit."""
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(_candidate(60_000, "short", eligible=False),),
        books=(
            _book(59_000, bid=99.8, ask=99.9),
            _book(61_000, bid=99.9, ask=100.0),
            _thin_top_book(120_000),
        ),
        marks=(subject.MarkObservation(119_000, 100.1),),
        funding_evidence=_funding(1, 120_000),
        gaps=(),
        spec=_spec(),
    )

    pending = report["attempts"][0]
    assert pending["current_exit_visible_depth_capacity"] is True
    assert "current_exit_top_level_capacity" not in pending
    assert pending["current_gross_return_bps"] < -40.0
    assert pending["visible_depth_path_complete"] is True


def test_pending_path_capacity_ignores_pre_entry_context_depth() -> None:
    """Only executable quotes during the holding interval define path coverage."""
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(_candidate(60_000, "short", eligible=False),),
        books=(
            _insufficient_exit_book(59_000),
            _book(61_000, bid=99.9, ask=100.0),
            _book(120_000, bid=100.1, ask=100.2),
        ),
        marks=(subject.MarkObservation(119_000, 100.1),),
        funding_evidence=_funding(1, 120_000),
        gaps=(),
        spec=_spec(),
    )

    assert report["attempts"][0]["visible_depth_path_complete"] is True


def test_stream_gap_censors_a_would_be_stop_exit() -> None:
    """A disconnected mark/L2 path cannot become resolved synthetic economics."""
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(_candidate(60_000, "long", eligible=False),),
        books=(
            _book(59_000, bid=99.9, ask=100.0),
            _book(61_000, bid=99.9, ask=100.0),
            _book(121_000, bid=99.0, ask=99.1),
        ),
        marks=(subject.MarkObservation(120_000, 99.19),),
        funding_evidence=None,
        gaps=(
            StreamGap(
                symbol="SOL",
                channel="l2Book,trades,activeAssetCtx",
                detected_ts_ns=90_000_000_000,
                reason="disconnect",
                previous_exchange_ts_ms=89_000,
                next_exchange_ts_ms=150_000,
            ),
        ),
        spec=_spec(),
    )

    assert report["coverage"]["resolved_executions"] == 0
    assert report["attempts"][0]["status"] == "technical_gap_unresolved"


def test_bounded_disconnect_with_observed_channel_paths_remains_resolved() -> None:
    """A reconnect inside frozen mark/L2 cadence cannot censor exact economics."""
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(
            _candidate(60_000, "short", eligible=False),
            _candidate(180_000, "long", eligible=True, blockers=()),
        ),
        books=(
            _book(59_000, bid=99.9, ask=100.0),
            _book(61_000, bid=99.9, ask=100.0),
            _book(89_000, bid=99.9, ask=100.0),
            _book(97_000, bid=99.9, ask=100.0),
            _book(181_000, bid=100.0, ask=100.1),
        ),
        marks=(
            subject.MarkObservation(89_000, 100.0),
            subject.MarkObservation(92_000, 100.0),
            subject.MarkObservation(179_000, 100.0),
        ),
        funding_evidence=_funding(1, 300_000),
        gaps=(
            StreamGap(
                symbol="SOL",
                channel="l2Book,trades,activeAssetCtx",
                detected_ts_ns=90_000_000_000,
                reason="disconnect",
                previous_exchange_ts_ms=89_000,
                next_exchange_ts_ms=96_000,
            ),
        ),
        spec=_spec(),
    )

    assert report["coverage"]["resolved_executions"] == 1
    assert report["attempts"][0]["status"] == "resolved"
    assert report["executions"][0]["exit_reason"] == "opposite_signal"


def test_coverage_separates_observed_exact_and_wrong_run_candidates() -> None:
    """The shadow reports selection attrition instead of hiding non-candidates."""
    wrong_run = _candidate(
        70_000,
        "long",
        eligible=False,
        source_run_id="different-run",
    )
    inexact = _candidate(
        80_000,
        "long",
        eligible=False,
        blockers=("awaiting_hourly_sma_cross", "5m_regime_not_admitted"),
    )
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(wrong_run, inexact, _candidate(90_000, "long", eligible=False)),
        books=(
            _book(89_000, bid=99.9, ask=100.0),
            _book(91_000, bid=99.9, ask=100.0),
        ),
        marks=(subject.MarkObservation(92_000, 100.0),),
        funding_evidence=None,
        gaps=(),
        spec=_spec(),
    )

    assert report["coverage"]["observed_candidates"] == 3
    assert report["coverage"]["exact_candidates"] == 1
    assert report["coverage"]["wrong_run_excluded"] == 1
    assert report["contract"]["exit_rule"] == (
        "first venue-mark stop, eligible opposite signal, then 48h maximum hold"
    )


def test_mark_observation_rejects_non_venue_source_provenance() -> None:
    """A midpoint or fabricated timestamp cannot stand in for venue mark truth."""
    with pytest.raises(ValueError, match="activeAssetCtx"):
        subject.MarkObservation(
            120_000,
            99.19,
            source="derived_midpoint",
            timestamp_source="local_receive_no_exchange_timestamp",
        )


def test_conflicting_duplicate_mark_timestamp_fails_closed() -> None:
    """Conflicting venue marks at one receipt millisecond are not ordered truth."""
    with pytest.raises(ValueError, match="mark timestamps"):
        subject.build_sol_route_native_one_blocker_shadow(
            candidates=(),
            books=(),
            marks=(
                subject.MarkObservation(120_000, 99.19),
                subject.MarkObservation(120_000, 99.20),
            ),
            funding_evidence=None,
            gaps=(),
            spec=_spec(),
        )


def test_identical_mark_receipt_millisecond_is_deduplicated() -> None:
    """Nanosecond-separated messages with one mark retain one causal mark row."""
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(_candidate(60_000, "short", eligible=False),),
        books=(
            _book(59_000, bid=99.8, ask=99.9),
            _book(61_000, bid=99.9, ask=100.0),
            _book(120_000, bid=100.1, ask=100.2),
        ),
        marks=(
            subject.MarkObservation(119_000, 100.1),
            subject.MarkObservation(119_000, 100.1),
        ),
        funding_evidence=_funding(1, 120_000),
        gaps=(),
        spec=_spec(),
    )

    assert report["attempts"][0]["status"] == "exit_pending"


def test_resolved_path_requires_official_funding_window_coverage() -> None:
    """Missing funding history cannot become a zero-cost resolved lifecycle."""
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(_candidate(60_000, "long", eligible=False),),
        books=(
            _book(59_000, bid=99.9, ask=100.0),
            _book(61_000, bid=99.9, ask=100.0),
            _book(121_000, bid=99.0, ask=99.1),
        ),
        marks=(subject.MarkObservation(120_000, 99.19),),
        funding_evidence=None,
        gaps=(),
        spec=_spec(),
    )

    assert report["coverage"]["resolved_executions"] == 0
    assert report["attempts"][0]["status"] == "funding_coverage_unresolved"


def test_pending_entry_blocks_overlapping_later_candidate() -> None:
    """An unresolved hypothetical position preserves one-position-per-symbol."""
    report = subject.build_sol_route_native_one_blocker_shadow(
        candidates=(
            _candidate(60_000, "long", eligible=False),
            _candidate(120_000, "short", eligible=False),
        ),
        books=(
            _book(59_000, bid=99.9, ask=100.0),
            _book(61_000, bid=99.9, ask=100.0),
            _book(121_000, bid=100.0, ask=100.1),
        ),
        marks=(subject.MarkObservation(119_000, 100.0),),
        funding_evidence=None,
        gaps=(),
        spec=_spec(),
    )

    assert report["coverage"]["exact_candidates"] == 2
    assert report["coverage"]["attempts"] == 1
    assert report["attempts"][0]["status"] == "exit_pending"
    assert report["attempts"][0]["decision_time_ms"] == 60_000
    assert report["attempts"][0]["side"] == "long"


def _spec(*, cutoff_time_ms: int = 1) -> object:
    return subject.SolRouteNativeShadowSpec(
        source_run_id=_RUN,
        source_profile_id="v51-test",
        source_profile_fingerprint="a" * 64,
        cutoff_time_ms=cutoff_time_ms,
        notional_usd=5_000.0,
        taker_fee_rate=0.000432,
    )


def _funding(start_ms: int, end_ms: int) -> object:
    return subject.SolFundingEvidence(
        requested_start_ms=start_ms,
        requested_end_ms=end_ms,
        events=(),
    )


def _candidate(
    available_time_ms: int,
    side: str,
    *,
    eligible: bool,
    blockers: tuple[str, ...] = ("awaiting_hourly_sma_cross",),
    source_run_id: str = _RUN,
) -> SignalCandidate:
    return SignalCandidate(
        strategy_id="range_onset_bidirectional_v1",
        symbol="SOL",
        decision_time_ms=available_time_ms,
        available_time_ms=available_time_ms,
        reference_price=100.0,
        side=side,
        eligible=eligible,
        blockers=blockers,
        metrics={"state_5m": "RANGE"},
        source_run_id=source_run_id,
    )


def _book(recv_ts_ms: int, *, bid: float, ask: float) -> Book:
    bids = (DepthLevel(bid, 100.0),)
    asks = (DepthLevel(ask, 100.0),)
    return Book(recv_ts_ms, 0.1, bid, 100.0, ask, 100.0, bids, asks)


def _thin_top_book(recv_ts_ms: int) -> Book:
    bids = (DepthLevel(99.9, 100.0),)
    asks = (DepthLevel(100.0, 1.0), DepthLevel(100.4, 100.0))
    return Book(recv_ts_ms, 0.1, 99.9, 100.0, 100.0, 1.0, bids, asks)


def _insufficient_exit_book(recv_ts_ms: int) -> Book:
    bids = (DepthLevel(99.8, 100.0),)
    asks = (DepthLevel(99.9, 1.0),)
    return Book(recv_ts_ms, 0.1, 99.8, 100.0, 99.9, 1.0, bids, asks)
