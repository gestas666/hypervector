"""Hand-computable activity and payoff evidence, including empty trials."""

import pandas as pd
import pytest

from hypervector.research.trade_activity import summarize_trade_activity


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "entry_time_utc": [
                "2026-01-01T00:00Z",
                "2026-01-01T12:00Z",
                "2026-01-03T00:00Z",
            ],
            "exit_time_utc": [
                "2026-01-01T01:00Z",
                "2026-01-01T14:00Z",
                "2026-01-03T03:00Z",
            ],
            "net_pnl_usd": [20.0, -5.0, 0.0],
        }
    )


def _summary(trades: pd.DataFrame) -> dict[str, object]:
    return summarize_trade_activity(
        trades,
        start=pd.Timestamp("2026-01-01T00:00Z"),
        end=pd.Timestamp("2026-01-05T00:00Z"),
    )


def test_activity_and_win_rate_include_zero_trades_as_neither_win_nor_loss() -> None:
    """Three completed trades span four observed days and two entry-active days."""
    result = _summary(_trades())
    assert result["trades_per_calendar_day"] == 0.75
    assert result["trades_per_entry_active_day"] == 1.5
    assert result["net_win_rate_pct"] == pytest.approx(100 / 3)
    assert (result["wins"], result["losses"], result["breakeven"]) == (1, 1, 1)
    assert result["mean_win_usd"] == 20.0
    assert result["mean_loss_usd"] == -5.0
    assert result["net_usd"] == 15.0
    assert result["net_excluding_largest_usd"] == -5.0
    assert result["net_excluding_top_three_winners_usd"] == -5.0
    assert result["mean_hold_hours"] == 2.0
    assert result["maximum_entry_gap_hours"] == 36.0


def test_empty_trial_is_preserved_without_inventing_win_rate() -> None:
    """A zero-trade trial reports zero activity and undefined payoff statistics."""
    result = _summary(_trades().iloc[:0])
    assert result["completed_trades"] == 0
    assert result["trades_per_calendar_day"] == 0.0
    assert result["net_win_rate_pct"] is None
    assert result["mean_win_usd"] is None
    assert result["maximum_entry_gap_hours"] is None


@pytest.mark.parametrize(
    "problem", ["nan", "early_exit", "outside", "naive", "missing"]
)
def test_invalid_trade_evidence_is_rejected(problem: str) -> None:
    """Invalid time/cost observations cannot yield a success-shaped summary."""
    trades = _trades()
    if problem == "nan":
        trades.loc[0, "net_pnl_usd"] = float("nan")
    elif problem == "early_exit":
        trades.loc[0, "exit_time_utc"] = "2025-12-31T23:00Z"
    elif problem == "outside":
        trades.loc[0, "exit_time_utc"] = "2026-01-06T00:00Z"
    elif problem == "naive":
        trades.loc[0, "entry_time_utc"] = "2026-01-01T00:00"
    else:
        trades = trades.drop(columns="net_pnl_usd")
    with pytest.raises(ValueError):
        _summary(trades)
