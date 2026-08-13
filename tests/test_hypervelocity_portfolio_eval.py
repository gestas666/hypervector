"""Serial one-position portfolio diagnostics for Hypervelocity candidates."""

import pandas as pd
import pytest

from hypervector.research.hypervelocity_portfolio_eval import (
    SerialPortfolioConfig,
    evaluate_serial_portfolio,
)


def _bars(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float] | None = None,
) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(opens), freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes or opens,
            "volume": [1.0] * len(opens),
        },
        index=index,
    )


def _decisions(
    bars: pd.DataFrame,
    entries: list[str | None],
    structural: list[str | None] | None = None,
    rsi_crosses: list[str | None] | None = None,
) -> pd.DataFrame:
    values: dict[str, list[str | None]] = {
        "entry_direction": entries,
        "structural_direction": structural or entries,
    }
    if rsi_crosses is not None:
        values["rsi_cross_direction"] = rsi_crosses
    return pd.DataFrame(values, index=bars.index)


def test_serial_portfolio_compounds_and_never_overlaps_positions() -> None:
    bars = _bars(
        [100.0] * 7,
        [100.0, 100.25, 100.0, 100.0, 100.0, 100.25, 100.0],
        [100.0] * 7,
    )
    decisions = _decisions(
        bars,
        ["long", "long", None, None, "long", "long", "long"],
        ["long", "long", None, None, "long", "long", "long"],
    )

    report = evaluate_serial_portfolio(bars, decisions)

    assert report.completed_trades == 2
    assert report.targets_completed == 2
    assert report.maximum_concurrent_positions == 1
    assert report.final_marked_equity == pytest.approx(10_974.4806, rel=1e-6)
    assert report.trades[0].exit_position < report.trades[1].entry_position


def test_same_direction_requires_structural_reset_before_reentry() -> None:
    bars = _bars(
        [100.0] * 6,
        [100.0, 100.25, 100.25, 100.25, 100.25, 100.25],
        [100.0] * 6,
    )

    report = evaluate_serial_portfolio(
        bars,
        _decisions(bars, ["long"] * 6, ["long"] * 6),
    )

    assert report.completed_trades == 1
    assert report.blocked_same_direction_bars > 0


def test_cooldown_only_serial_reentry_waits_configured_bars() -> None:
    bars = _bars(
        [100.0] * 7,
        [100.0, 100.25, 100.0, 100.0, 100.25, 100.0, 100.0],
        [100.0] * 7,
    )

    report = evaluate_serial_portfolio(
        bars,
        _decisions(bars, ["long"] * 7, ["long"] * 7),
        SerialPortfolioConfig(
            reentry_cooldown_bars=2,
            same_direction_reentry_policy="cooldown_only",
        ),
    )

    assert report.completed_trades == 2
    assert report.trades[1].signal_position == 3
    assert report.trades[1].entry_position == 4


def test_serial_config_rejects_unknown_same_direction_reentry_policy() -> None:
    with pytest.raises(ValueError, match="same_direction_reentry_policy"):
        SerialPortfolioConfig(same_direction_reentry_policy="immediate")


def test_target_continuation_serial_waits_for_fresh_clearance() -> None:
    bars = _bars(
        [100.0, 100.0, 100.22, 100.24, 100.24, 100.24],
        [100.0, 100.25, 100.22, 100.24, 100.50, 100.24],
        [100.0, 100.0, 100.20, 100.22, 100.20, 100.20],
        [100.0, 100.20, 100.22, 100.24, 100.44, 100.24],
    )

    report = evaluate_serial_portfolio(
        bars,
        _decisions(bars, ["long"] * 6, ["long"] * 6),
        SerialPortfolioConfig(
            reentry_cooldown_bars=1,
            same_direction_reentry_policy="target_continuation",
            same_direction_reentry_clearance_bps=3.0,
        ),
    )

    assert report.completed_trades == 2
    assert report.trades[1].signal_position == 3
    assert report.trades[1].entry_position == 4


def test_target_continuation_serial_blocks_same_side_after_liquidation() -> None:
    bars = _bars(
        [100.0] * 6,
        [100.0, 100.1, 100.5, 100.5, 100.5, 100.5],
        [100.0, 98.5, 100.0, 100.0, 100.0, 100.0],
    )

    report = evaluate_serial_portfolio(
        bars,
        _decisions(bars, ["long"] * 6, ["long"] * 6),
        SerialPortfolioConfig(
            reentry_cooldown_bars=1,
            same_direction_reentry_policy="target_continuation",
        ),
    )

    assert report.completed_trades == 1
    assert report.liquidations == 1


def test_serial_config_rejects_negative_reentry_clearance() -> None:
    with pytest.raises(ValueError, match="same_direction_reentry_clearance_bps"):
        SerialPortfolioConfig(same_direction_reentry_clearance_bps=-0.1)


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_serial_config_rejects_invalid_target_continuation_limit(
    limit: object,
) -> None:
    with pytest.raises(ValueError, match="target_continuation_limit_per_episode"):
        SerialPortfolioConfig(
            same_direction_reentry_policy="target_continuation",
            target_continuation_limit_per_episode=limit,
        )


def test_serial_config_rejects_target_limit_for_other_policy() -> None:
    with pytest.raises(ValueError, match="requires target_continuation"):
        SerialPortfolioConfig(target_continuation_limit_per_episode=2)


def test_serial_target_continuation_waits_for_mature_episode() -> None:
    bars = _bars(
        opens=[100.0] * 6,
        highs=[100.0, 100.25, 100.0, 100.0, 100.0, 100.0],
        lows=[100.0] * 6,
        closes=[100.0, 100.2, 100.2, 100.2, 100.2, 100.2],
    )
    report = evaluate_serial_portfolio(
        bars,
        _decisions(bars, ["long"] * 6),
        SerialPortfolioConfig(
            reentry_cooldown_bars=0,
            same_direction_reentry_policy="target_continuation",
            target_continuation_minimum_episode_bars=3,
        ),
    )

    assert [trade.signal_position for trade in report.trades] == [0]
    assert report.submitted_entries == 2
    assert report.trades[0].status == "target_completed"


def test_target_ladder_cap_blocks_third_target_in_one_episode() -> None:
    bars = _bars(
        [100.0, 100.0, 100.2, 100.2, 100.4004, 100.4004, 100.6012],
        [100.0, 100.25, 100.2, 100.45, 100.4004, 100.65, 100.6012],
        [100.0, 100.0, 100.2, 100.2, 100.4004, 100.4004, 100.6012],
        [100.0, 100.2, 100.2, 100.4004, 100.4004, 100.6012, 100.6012],
    )

    report = evaluate_serial_portfolio(
        bars,
        _decisions(bars, ["long"] * len(bars)),
        SerialPortfolioConfig(
            same_direction_reentry_policy="target_continuation",
            target_continuation_limit_per_episode=2,
        ),
    )

    assert report.targets_completed == 2
    assert [trade.entry_position for trade in report.trades] == [1, 3]


def test_target_ladder_count_resets_on_new_structural_episode() -> None:
    bars = _bars(
        [100.0, 100.0, 100.2, 100.2, 100.4004, 100.4004, 100.4004],
        [100.0, 100.25, 100.2, 100.45, 100.4004, 100.4004, 100.65],
        [100.0, 100.0, 100.2, 100.2, 100.4004, 100.4004, 100.4004],
        [100.0, 100.2, 100.2, 100.4004, 100.4004, 100.4004, 100.6012],
    )
    entries = ["long", "long", "long", "long", None, "long", "long"]

    report = evaluate_serial_portfolio(
        bars,
        _decisions(bars, entries, entries),
        SerialPortfolioConfig(
            same_direction_reentry_policy="target_continuation",
            target_continuation_limit_per_episode=2,
        ),
    )

    assert report.targets_completed == 3
    assert [trade.entry_position for trade in report.trades] == [1, 3, 6]


def test_target_rsi_reconfirmation_requires_a_fresh_same_side_cross() -> None:
    bars = _bars(
        [100.0] * 7,
        [100.0, 100.25, 100.0, 100.0, 100.25, 100.0, 100.0],
        [100.0] * 7,
    )
    decisions = _decisions(
        bars,
        ["long"] * 7,
        ["long"] * 7,
        [None, None, None, "BK_UPWARD", None, None, None],
    )

    report = evaluate_serial_portfolio(
        bars,
        decisions,
        SerialPortfolioConfig(
            reentry_cooldown_bars=1,
            same_direction_reentry_policy="target_rsi_reconfirmation",
        ),
    )

    assert report.completed_trades == 2
    assert report.trades[1].signal_position == 3
    assert report.trades[1].entry_position == 4


def test_target_rsi_reconfirmation_does_not_rearm_after_liquidation() -> None:
    bars = _bars(
        [100.0] * 6,
        [100.0, 100.1, 100.5, 100.5, 100.5, 100.5],
        [100.0, 98.5, 100.0, 100.0, 100.0, 100.0],
    )
    decisions = _decisions(
        bars,
        ["long"] * 6,
        ["long"] * 6,
        [None, None, "BK_UPWARD", "BK_UPWARD", None, None],
    )

    report = evaluate_serial_portfolio(
        bars,
        decisions,
        SerialPortfolioConfig(
            same_direction_reentry_policy="target_rsi_reconfirmation"
        ),
    )

    assert report.completed_trades == 1
    assert report.liquidations == 1


def test_target_rsi_reconfirmation_requires_rsi_telemetry() -> None:
    bars = _bars([100.0] * 3, [100.0] * 3, [100.0] * 3)

    with pytest.raises(ValueError, match="rsi_cross_direction"):
        evaluate_serial_portfolio(
            bars,
            _decisions(bars, ["long"] * 3),
            SerialPortfolioConfig(
                same_direction_reentry_policy="target_rsi_reconfirmation"
            ),
        )


def test_range_does_not_force_close_open_position() -> None:
    bars = _bars(
        [100.0] * 5,
        [100.0, 100.1, 100.1, 100.25, 100.0],
        [100.0] * 5,
    )
    report = evaluate_serial_portfolio(
        bars,
        _decisions(
            bars,
            ["long", None, None, None, None],
            ["long", None, None, None, None],
        ),
    )

    assert report.targets_completed == 1
    assert report.trades[0].entry_position == 1
    assert report.trades[0].exit_position == 3


def test_liquidation_changes_equity_and_bounded_drawdown() -> None:
    bars = _bars(
        [100.0, 100.0, 99.0],
        [100.0, 100.1, 99.2],
        [100.0, 99.9, 98.5],
    )

    report = evaluate_serial_portfolio(
        bars,
        _decisions(bars, ["long", "long", "long"]),
    )

    assert report.liquidations == 1
    assert report.final_marked_equity == pytest.approx(6_331.8037, rel=1e-6)
    assert -100.0 <= report.maximum_drawdown_pct < 0.0
    assert report.liquidation_model == "full_close_at_isolated_boundary_v1"
