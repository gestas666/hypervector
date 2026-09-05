"""Causal replay contract for BTC liquidation-triggered long candidates."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hypervector.research.btc_liquidation_covariate_replay import (
    BookSnapshot,
    FundingSettlement,
    PublicTrade,
    PurgeCandidate,
    ReplayEpisode,
    VisibleLevel,
    assess_book_timing,
    evaluate_entry,
    flow_imbalance,
    apply_long_funding,
    long_funding_cashflow,
    purge_overlapping_entries,
    replay_outcomes,
)

_D = Decimal


def _levels(
    best: str,
    *,
    ascending: bool,
    first_size: str = "100",
    second_size: str = "100",
    remaining_size: str = "100",
    count: int = 20,
) -> tuple[VisibleLevel, ...]:
    """Build an ordered visible-depth side with configurable first levels."""
    start = _D(best)
    step = _D("1") if ascending else _D("-1")
    sizes = (first_size, second_size)
    return tuple(
        VisibleLevel(
            start + step * index,
            _D(sizes[index] if index < 2 else remaining_size),
        )
        for index in range(count)
    )


def _book(
    timestamp_ms: int,
    *,
    best_bid: str = "99",
    best_ask: str = "101",
    bid_sizes: tuple[str, str] = ("100", "100"),
    ask_sizes: tuple[str, str] = ("100", "100"),
    bid_tail_size: str = "100",
    ask_tail_size: str = "100",
    count: int = 20,
) -> BookSnapshot:
    """Build one deterministic BTC snapshot."""
    return BookSnapshot(
        ts_exchange_ms=timestamp_ms,
        bids=_levels(
            best_bid,
            ascending=False,
            first_size=bid_sizes[0],
            second_size=bid_sizes[1],
            remaining_size=bid_tail_size,
            count=count,
        ),
        asks=_levels(
            best_ask,
            ascending=True,
            first_size=ask_sizes[0],
            second_size=ask_sizes[1],
            remaining_size=ask_tail_size,
            count=count,
        ),
    )


def _episode(
    branch: str,
    *,
    end_ms: int = 1_000,
    vwap: str = "100",
) -> ReplayEpisode:
    """Build one frozen treatment episode."""
    return ReplayEpisode(
        episode_id=f"episode-{branch}",
        partition="development",
        branch=branch,
        end_ms=end_ms,
        volume_weighted_price=_D(vwap),
        eligible_arms=("5s_p95",),
    )


def _positive_flow(decision_ms: int) -> tuple[PublicTrade, ...]:
    """Build public flow that is strictly positive at the decision boundary."""
    return (
        PublicTrade(decision_ms - 1_000, 1, "buy", _D("100"), _D("2")),
        PublicTrade(decision_ms, 2, "sell", _D("100"), _D("1")),
    )


def test_flow_interval_is_open_left_and_closed_right() -> None:
    """Exclude the left boundary and future trades while including decision time."""
    decision_ms = 10_000
    trades = (
        PublicTrade(5_000, 1, "sell", _D("100"), _D("100")),
        PublicTrade(5_001, 2, "buy", _D("100"), _D("2")),
        PublicTrade(10_000, 3, "sell", _D("100"), _D("1")),
        PublicTrade(10_001, 4, "sell", _D("100"), _D("100")),
    )

    result = flow_imbalance(trades, decision_ms=decision_ms, window_ms=5_000)

    assert result == _D("0.3333333333333333333333333333")


def test_continuation_uses_first_complete_book_at_or_after_decision() -> None:
    """Never use pre-decision or incomplete depth for a continuation entry."""
    episode = _episode("continuation_long")
    decision_ms = 11_000
    books = (
        _book(10_999, best_bid="109", best_ask="111"),
        _book(11_000, count=19),
        _book(11_005, best_bid="99", best_ask="101"),
    )

    result = evaluate_entry(
        episode,
        trades=_positive_flow(decision_ms),
        books=books,
    )

    assert result.status == "eligible"
    assert result.decision_book_time_ms == 11_005
    assert result.decision_midpoint == _D("100")
    assert result.entry_fill is not None
    assert result.entry_fill.best_price == _D("101")


def test_continuation_requires_decision_midpoint_at_episode_vwap_or_higher() -> None:
    """Reject a continuation whose first executable midpoint remains below VWAP."""
    decision_ms = 11_000
    result = evaluate_entry(
        _episode("continuation_long"),
        trades=_positive_flow(decision_ms),
        books=(_book(decision_ms, best_bid="98", best_ask="100"),),
    )

    assert result.status == "signal_blocked"
    assert result.blockers == ("decision_midpoint_below_episode_vwap",)
    assert result.entry_fill is None


def test_exhaustion_requires_strict_predecision_cross_and_reclaim() -> None:
    """A midpoint equal to VWAP is not a strict exhaustion cross below it."""
    decision_ms = 11_000
    no_cross = evaluate_entry(
        _episode("exhaustion_reclaim_long"),
        trades=_positive_flow(decision_ms),
        books=(
            _book(5_000, best_bid="99", best_ask="101"),
            _book(decision_ms, best_bid="99", best_ask="101"),
        ),
    )
    crossed = evaluate_entry(
        _episode("exhaustion_reclaim_long"),
        trades=_positive_flow(decision_ms),
        books=(
            _book(5_000, best_bid="98", best_ask="100"),
            _book(decision_ms, best_bid="99", best_ask="101"),
        ),
    )

    assert no_cross.status == "signal_blocked"
    assert no_cross.blockers == ("predecision_midpoint_never_below_episode_vwap",)
    assert crossed.status == "eligible"


def test_entry_and_exit_walk_visible_depth_for_fixed_quantity() -> None:
    """Walk multiple levels and retain the entry quantity at exit."""
    decision_ms = 11_000
    entry = evaluate_entry(
        _episode("continuation_long"),
        trades=_positive_flow(decision_ms),
        books=(
            _book(
                decision_ms,
                ask_sizes=("25", "30"),
                bid_sizes=("30", "30"),
            ),
        ),
    )
    outcomes = replay_outcomes(
        entry,
        books=(
            _book(
                decision_ms + 30_000,
                best_bid="102",
                best_ask="104",
                bid_sizes=("25", "30"),
            ),
        ),
        horizons_ms=(30_000,),
    )

    assert entry.entry_fill is not None
    expected_quantity = _D("5000") / _D("101")
    assert entry.entry_fill.requested_quantity == expected_quantity
    assert entry.entry_fill.levels_consumed == 2
    assert outcomes[0].status == "resolved"
    assert outcomes[0].exit_fill is not None
    assert outcomes[0].exit_fill.requested_quantity == expected_quantity
    assert outcomes[0].exit_fill.levels_consumed == 2
    assert outcomes[0].nominal_net_pnl_before_funding_usd is not None
    assert outcomes[0].stressed_net_pnl_before_funding_usd is not None
    assert (
        outcomes[0].stressed_net_pnl_before_funding_usd
        < outcomes[0].nominal_net_pnl_before_funding_usd
    )


def test_exit_horizon_starts_at_actual_entry_book_timestamp() -> None:
    """Anchor exits to the first executable entry book, not the decision clock."""
    decision_ms = 11_000
    entry = evaluate_entry(
        _episode("continuation_long"),
        trades=_positive_flow(decision_ms),
        books=(_book(12_000),),
    )
    outcomes = replay_outcomes(
        entry,
        books=(
            _book(41_999, best_bid="110", best_ask="112"),
            _book(42_001, best_bid="102", best_ask="104"),
        ),
        horizons_ms=(30_000,),
    )

    assert outcomes[0].target_time_ms == 42_000
    assert outcomes[0].exit_book_time_ms == 42_001
    assert outcomes[0].exit_fill is not None
    assert outcomes[0].exit_fill.best_price == _D("102")


def test_book_timing_preflight_anchors_coverage_to_entry() -> None:
    """Prove each required horizon has a complete post-entry snapshot."""
    episode = _episode("continuation_long")
    books = (
        _book(10_999),
        _book(11_002),
        _book(41_001),
        _book(41_999, count=19),
        _book(42_003),
    )

    result = assess_book_timing(episode, books=books, horizons_ms=(30_000,))

    assert result.decision_time_ms == 11_000
    assert result.entry_book_time_ms == 11_002
    assert result.entry_delay_ms == 2
    assert result.horizon_book_times_ms == ((30_000, 42_003),)
    assert result.technical_complete is True


@pytest.mark.parametrize(
    ("books", "expected_blocker"),
    [
        ((), "decision_book_unavailable"),
        (
            (
                _book(
                    11_000,
                    ask_sizes=("0.01", "0.01"),
                    ask_tail_size="0.01",
                    count=20,
                ),
            ),
            "entry_visible_depth_insufficient",
        ),
    ],
)
def test_entry_technical_exclusions_are_explicit(
    books: tuple[BookSnapshot, ...],
    expected_blocker: str,
) -> None:
    """Keep missing books and insufficient depth out of signal failures."""
    decision_ms = 11_000

    result = evaluate_entry(
        _episode("continuation_long"),
        trades=_positive_flow(decision_ms),
        books=books,
    )

    assert result.status == "technical_excluded"
    assert result.blockers == (expected_blocker,)


def test_entry_book_delay_boundary_excludes_stale_archive_recovery() -> None:
    """Admit five seconds exactly and exclude a later first complete book."""
    decision_ms = 11_000
    timely = evaluate_entry(
        _episode("continuation_long"),
        trades=_positive_flow(decision_ms),
        books=(_book(decision_ms + 5_000),),
    )
    stale = evaluate_entry(
        _episode("continuation_long"),
        trades=_positive_flow(decision_ms),
        books=(_book(decision_ms + 5_001),),
    )

    assert timely.status == "eligible"
    assert stale.status == "technical_excluded"
    assert stale.blockers == ("decision_book_delay_exceeded",)


def test_exit_depth_failure_is_horizon_specific() -> None:
    """Resolve one horizon while retaining another as a technical exclusion."""
    decision_ms = 11_000
    entry = evaluate_entry(
        _episode("continuation_long"),
        trades=_positive_flow(decision_ms),
        books=(_book(decision_ms),),
    )
    outcomes = replay_outcomes(
        entry,
        books=(
            _book(decision_ms + 30_000),
            _book(
                decision_ms + 120_000,
                bid_sizes=("0.01", "0.01"),
                bid_tail_size="0.01",
                count=20,
            ),
        ),
        horizons_ms=(30_000, 120_000),
    )

    assert outcomes[0].status == "resolved"
    assert outcomes[1].status == "technical_excluded"
    assert outcomes[1].reason == "exit_visible_depth_insufficient"


def test_exit_book_delay_boundary_excludes_stale_horizon_recovery() -> None:
    """Admit 30 seconds exactly and reject a later horizon snapshot."""
    decision_ms = 11_000
    entry = evaluate_entry(
        _episode("continuation_long"),
        trades=_positive_flow(decision_ms),
        books=(_book(decision_ms),),
    )
    outcomes = replay_outcomes(
        entry,
        books=(
            _book(decision_ms + 60_000),
            _book(decision_ms + 150_001),
        ),
        horizons_ms=(30_000, 120_000),
    )

    assert outcomes[0].status == "resolved"
    assert outcomes[0].exit_book_time_ms == decision_ms + 60_000
    assert outcomes[1].status == "technical_excluded"
    assert outcomes[1].reason == "exit_book_delay_exceeded"


def test_overlap_purge_is_grouped_and_boundary_inclusive() -> None:
    """Suppress through retained entry plus 15 minutes within exact groups only."""
    rows = (
        PurgeCandidate("a", "development", "continuation_long", "5s_p95", 1_000, 1_100),
        PurgeCandidate(
            "b", "development", "continuation_long", "5s_p95", 901_100, 901_200
        ),
        PurgeCandidate(
            "c", "development", "continuation_long", "5s_p95", 901_101, 901_201
        ),
        PurgeCandidate("d", "development", "continuation_long", "5s_p99", 1_001, 1_101),
        PurgeCandidate("e", "validation", "continuation_long", "5s_p95", 1_002, 1_102),
        PurgeCandidate(
            "f", "development", "exhaustion_reclaim_long", "5s_p95", 1_003, 1_103
        ),
    )

    result = purge_overlapping_entries(rows, overlap_horizon_ms=900_000)

    assert tuple(row.episode_id for row in result.retained) == ("a", "d", "e", "f", "c")
    assert tuple(row.episode_id for row in result.suppressed) == ("b",)


def test_long_funding_uses_open_entry_closed_exit_interval_and_exact_sign() -> None:
    """A long pays positive funding only for settlements in (entry, exit]."""
    settlements = (
        FundingSettlement(1_000, _D("0.00010")),
        FundingSettlement(2_000, _D("0.00020")),
        FundingSettlement(3_000, _D("-0.00005")),
        FundingSettlement(4_000, _D("0.00040")),
    )

    result = long_funding_cashflow(
        settlements,
        entry_time_ms=1_000,
        exit_time_ms=3_000,
        entry_notional_usd=_D("5000"),
    )

    assert result.settlement_count == 2
    assert result.total_funding_rate == _D("0.00015")
    assert result.cashflow_usd == _D("-0.75000")


def test_long_funding_rejects_duplicate_settlement_timestamps() -> None:
    """Duplicate official settlements cannot be silently double-counted."""
    settlements = (
        FundingSettlement(2_000, _D("0.0001")),
        FundingSettlement(2_000, _D("0.0002")),
    )

    with pytest.raises(ValueError, match="unique"):
        long_funding_cashflow(
            settlements,
            entry_time_ms=1_000,
            exit_time_ms=3_000,
        )


def test_resolved_horizon_adds_same_signed_funding_to_nominal_and_stress() -> None:
    """Funding adjusts both cost surfaces without changing their execution fills."""
    decision_ms = 11_000
    entry = evaluate_entry(
        _episode("continuation_long"),
        trades=_positive_flow(decision_ms),
        books=(_book(decision_ms),),
    )
    replay = replay_outcomes(
        entry,
        books=(_book(decision_ms + 300_000, best_bid="102", best_ask="104"),),
        horizons_ms=(300_000,),
    )[0]

    adjusted = apply_long_funding(
        replay,
        entry_time_ms=decision_ms,
        settlements=(FundingSettlement(200_000, _D("0.0001")),),
    )

    assert adjusted.funding is not None
    assert adjusted.funding.cashflow_usd == _D("-0.5000")
    assert adjusted.nominal_net_pnl_usd == (
        replay.nominal_net_pnl_before_funding_usd + _D("-0.5000")
    )
    assert adjusted.stressed_net_pnl_usd == (
        replay.stressed_net_pnl_before_funding_usd + _D("-0.5000")
    )
