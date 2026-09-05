"""Frozen signal contracts for BTC subminute sell-flow absorption."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_subminute_absorption_signals import (
    build_btc_absorption_signals,
)


_START = pd.Timestamp("2026-01-01T00:00:00Z")


def _row(available_at: pd.Timestamp, **changes: float | int) -> dict[str, object]:
    """Return one exact-boundary candidate input row."""
    values: dict[str, object] = {
        "bucket_ms": int((available_at - pd.Timedelta(seconds=10)).timestamp() * 1000),
        "bucket_start_utc": available_at - pd.Timedelta(seconds=10),
        "available_at_utc": available_at,
        "snapshot_count": 5,
        "sell_notional_usd": 5_500_000.0,
        "sell_share": 0.75,
        "adverse_midpoint_bps": 3.0,
        "bid_depletion_fraction": 0.20,
        "bid_recovery_fraction": 0.75,
        "terminal_imbalance_10": 0.0,
        "maximum_spread_bps": 5.0,
        "prior_60m_trend_bps": 25.0,
        "last_mid": 100.0,
    }
    values.update(changes)
    return values


def test_exact_candidate_boundaries_emit_one_deterministic_long() -> None:
    """Every inclusive frozen boundary must admit the candidate unchanged."""
    features = pd.DataFrame([_row(_START)])

    first = build_btc_absorption_signals(features)
    second = build_btc_absorption_signals(features.copy())

    assert len(first.candidate) == 1
    assert len(first.control) == 1
    assert first.candidate.iloc[0]["side"] == "long"
    assert first.candidate.iloc[0]["event_id"] == second.candidate.iloc[0]["event_id"]
    assert first.execution_authority == "none"
    assert first.orders_attempted is False


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("snapshot_count", 4, "insufficient_book_snapshots"),
        ("sell_notional_usd", 5_499_999.0, "sell_notional_below_minimum"),
        ("sell_share", 0.749, "sell_share_below_minimum"),
        ("prior_60m_trend_bps", 24.99, "prior_trend_below_minimum"),
        ("adverse_midpoint_bps", 3.01, "midpoint_impact_above_maximum"),
        ("bid_depletion_fraction", 0.199, "bid_depletion_below_minimum"),
        ("bid_recovery_fraction", 0.749, "bid_recovery_below_minimum"),
        ("terminal_imbalance_10", -0.001, "terminal_imbalance_below_minimum"),
        ("maximum_spread_bps", 5.01, "spread_above_maximum"),
    ],
)
def test_each_primary_threshold_has_explicit_blocker(
    field: str,
    value: float | int,
    reason: str,
) -> None:
    """A one-field failure must be attributed and never relaxed implicitly."""
    report = build_btc_absorption_signals(
        pd.DataFrame([_row(_START, **{field: value})])
    )

    assert report.candidate.empty
    assert report.candidate_blockers[reason] == 1
    expected_control = field not in {
        "snapshot_count",
        "sell_notional_usd",
        "sell_share",
        "prior_60m_trend_bps",
    }
    assert (len(report.control) == 1) is expected_control


def test_one_hour_greedy_cooldown_is_arm_specific_and_prefix_invariant() -> None:
    """Candidate cooldown must not depend on later rows or control-only events."""
    rows = [
        _row(_START),
        _row(_START + pd.Timedelta(minutes=30), adverse_midpoint_bps=4.0),
        _row(_START + pd.Timedelta(minutes=59, seconds=59)),
        _row(_START + pd.Timedelta(minutes=60)),
    ]
    full = build_btc_absorption_signals(pd.DataFrame(rows))
    prefix = build_btc_absorption_signals(pd.DataFrame(rows[:2]))

    assert full.candidate["available_at_utc"].tolist() == [
        _START,
        _START + pd.Timedelta(minutes=60),
    ]
    assert full.control["available_at_utc"].tolist() == [
        _START,
        _START + pd.Timedelta(minutes=60),
    ]
    assert prefix.candidate.equals(full.candidate.iloc[:1].reset_index(drop=True))
    assert prefix.control.equals(full.control.iloc[:1].reset_index(drop=True))
    assert full.candidate_blockers["candidate_cooldown_active"] == 1
    assert full.control_blockers["control_cooldown_active"] == 2


def test_signal_input_rejects_duplicates_missing_columns_and_nonfinite_values() -> None:
    """Signal construction must fail closed on ambiguous feature evidence."""
    row = _row(_START)
    with pytest.raises(ValueError, match="duplicated"):
        build_btc_absorption_signals(pd.DataFrame([row, row]))
    with pytest.raises(ValueError, match="missing"):
        build_btc_absorption_signals(pd.DataFrame([row]).drop(columns="sell_share"))
    with pytest.raises(ValueError, match="finite"):
        build_btc_absorption_signals(
            pd.DataFrame([_row(_START, sell_share=float("nan"))])
        )
