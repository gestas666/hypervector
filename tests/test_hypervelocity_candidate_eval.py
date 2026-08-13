"""Causal independent-outcome screening for regime candidates."""

import pandas as pd
import pytest

from hypervector.research.hypervelocity_candidate_eval import (
    CandidateBarrierConfig,
    evaluate_independent_barriers,
)


def _bars(
    opens: list[float],
    highs: list[float],
    lows: list[float],
) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(opens), freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": opens,
            "volume": [1.0] * len(opens),
        },
        index=index,
    )


def _decisions(bars: pd.DataFrame, directions: list[str | None]) -> pd.DataFrame:
    return pd.DataFrame({"entry_direction": directions}, index=bars.index)


def test_long_signal_enters_next_bar_and_completes_eight_percent_margin_target() -> (
    None
):
    bars = _bars(
        [100.0, 100.0, 100.1, 100.2],
        [100.0, 100.1, 100.25, 100.3],
        [100.0, 99.9, 100.0, 100.1],
    )

    report = evaluate_independent_barriers(
        bars,
        _decisions(bars, ["long", "long", "long", "long"]),
    )

    assert report.total_signals == 1
    assert report.targets_completed == 1
    assert report.liquidations == 0
    assert report.outcomes[0].entry_time_utc == bars.index[1].isoformat()
    assert report.outcomes[0].exit_time_utc == bars.index[2].isoformat()
    assert report.outcomes[0].target_price == pytest.approx(100.2)
    assert report.net_pnl_usd == pytest.approx(475.916)


def test_short_signal_completes_directional_target() -> None:
    bars = _bars(
        [100.0, 100.0, 99.9],
        [100.0, 100.1, 100.0],
        [100.0, 99.9, 99.75],
    )

    report = evaluate_independent_barriers(
        bars,
        _decisions(bars, ["short", "short", "short"]),
    )

    assert report.targets_completed == 1
    assert report.outcomes[0].target_price == pytest.approx(99.8)


def test_official_isolated_boundary_counts_liquidation_with_exit_fee() -> None:
    bars = _bars(
        [100.0, 100.0, 99.0],
        [100.0, 100.1, 99.2],
        [100.0, 99.9, 98.5],
    )

    report = evaluate_independent_barriers(
        bars,
        _decisions(bars, ["long", "long", "long"]),
    )

    assert report.liquidations == 1
    assert report.targets_completed == 0
    assert report.outcomes[0].liquidation_price == pytest.approx(98.749367, rel=1e-6)
    assert report.outcomes[0].fees_usd == pytest.approx(166.4242, rel=1e-6)
    assert report.net_pnl_usd == pytest.approx(-3668.1963, rel=1e-6)


def test_same_bar_target_and_liquidation_is_conservatively_liquidated() -> None:
    bars = _bars(
        [100.0, 100.0],
        [100.0, 101.0],
        [100.0, 98.0],
    )

    report = evaluate_independent_barriers(
        bars,
        _decisions(bars, ["long", "long"]),
    )

    assert report.ambiguous_barriers == 1
    assert report.liquidations == 1


def test_unreached_barriers_remain_right_censored() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0],
        [100.0, 100.1, 100.1],
        [100.0, 99.9, 99.9],
    )

    report = evaluate_independent_barriers(
        bars,
        _decisions(bars, ["long", "long", "long"]),
        CandidateBarrierConfig(),
    )

    assert report.total_signals == 1
    assert report.unresolved == 1
    assert report.net_pnl_usd == 0.0
