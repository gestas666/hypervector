"""Tests for the count-only BTC OI-expansion continuation preflight."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from hypervector.research.btc_oi_expansion_continuation import (
    build_oi_expansion_preflight,
)


_ARMS = [
    "positive_price_shock",
    "positive_price_and_oi_expansion",
    "positive_price_oi_and_trade_flow",
    "full_price_oi_trade_and_book_candidate",
]


def _minutes(
    closes: list[float],
    open_interests: list[float],
    *,
    gap_after_bar: int | None = None,
) -> pd.DataFrame:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for bar, (close, open_interest) in enumerate(
        zip(closes, open_interests, strict=True)
    ):
        gap = 5 if gap_after_bar is not None and bar > gap_after_bar else 0
        bar_start = start + timedelta(minutes=bar * 5 + gap)
        for offset in range(5):
            minute = bar_start + timedelta(minutes=offset)
            rows.append(
                {
                    "minute": minute,
                    "close": close,
                    "trade_imbalance": 0.4,
                    "book_imbalance": 0.3,
                    "open_interest": open_interest,
                    "first_bid": close - 0.01,
                    "first_ask": close + 0.01,
                    "first_quote_at": minute + timedelta(seconds=2),
                }
            )
    return pd.DataFrame.from_records(rows)


def _candidate_minutes() -> pd.DataFrame:
    return _minutes(
        [100.0, 100.1, 100.2, 101.0],
        [1_000.0, 1_001.0, 1_002.0, 1_010.0],
    )


def _build(minutes: pd.DataFrame, **overrides: object) -> pd.DataFrame:
    options: dict[str, object] = {
        "quantile": 0.75,
        "minimum_shock_bps": 1.0,
        "minimum_oi_expansion_pct": 0.0001,
        "warmup_bars": 2,
        "non_overlap_minutes": 60,
    }
    options.update(overrides)
    return build_oi_expansion_preflight(minutes, **options)  # type: ignore[arg-type]


def _onsets(result: pd.DataFrame) -> pd.DataFrame:
    return result.loc[result["onset"]].reset_index(drop=True)


def test_only_exact_completed_five_minute_groups_can_qualify() -> None:
    """Exclude an otherwise eligible bar when one common minute is absent."""
    complete = _onsets(_build(_candidate_minutes()))
    incomplete_minutes = _candidate_minutes().drop(index=17).reset_index(drop=True)
    incomplete = _onsets(_build(incomplete_minutes))

    assert complete["arm"].tolist() == _ARMS
    assert incomplete.empty


def test_gap_starts_a_new_segment_and_resets_rolling_history() -> None:
    """Require a fresh prior-only warmup after a common-minute gap."""
    minutes = _minutes(
        [100.0, 100.1, 100.2, 101.0, 102.0, 102.1, 102.2, 103.0],
        [1_000.0, 1_001.0, 1_002.0, 1_010.0, 1_020.0, 1_021.0, 1_022.0, 1_030.0],
        gap_after_bar=3,
    )

    candidate = _onsets(_build(minutes))

    full = candidate.loc[candidate["arm"].eq("full_price_oi_trade_and_book_candidate")]
    assert full["decision_at"].tolist() == [
        pd.Timestamp("2026-08-01T00:20:00Z"),
        pd.Timestamp("2026-08-01T00:45:00Z"),
    ]
    assert full["segment_id"].tolist() == [1, 2]


def test_price_and_oi_quantiles_use_prior_bars_only() -> None:
    """Keep the current event out of both rolling threshold estimates."""
    baseline = _build(_candidate_minutes())
    changed = _candidate_minutes()
    changed.loc[changed.index[-5:], "close"] = 110.0
    changed.loc[changed.index[-5:], "open_interest"] = 1_100.0
    stressed = _build(changed)

    baseline_row = baseline.loc[
        baseline["decision_at"].eq(pd.Timestamp("2026-08-01T00:20:00Z"))
    ].iloc[0]
    stressed_row = stressed.loc[
        stressed["decision_at"].eq(pd.Timestamp("2026-08-01T00:20:00Z"))
    ].iloc[0]
    assert stressed_row["price_threshold_bps"] == pytest.approx(
        baseline_row["price_threshold_bps"]
    )
    assert stressed_row["oi_threshold_pct"] == pytest.approx(
        baseline_row["oi_threshold_pct"]
    )


def test_positive_price_shock_and_oi_expansion_are_separate_nested_arms() -> None:
    """Attribute a price-only event without treating it as the OI candidate."""
    minutes = _candidate_minutes()
    minutes.loc[minutes.index[-5:], "open_interest"] = 1_001.0

    arms = _onsets(_build(minutes))["arm"].tolist()

    assert arms == ["positive_price_shock"]


def test_terminal_trade_and_book_confirmations_define_the_full_arm() -> None:
    """Require positive terminal trade flow and then positive displayed depth."""
    trade_opposed = _candidate_minutes()
    trade_opposed.loc[trade_opposed.index[-1], "trade_imbalance"] = -0.1
    book_opposed = _candidate_minutes()
    book_opposed.loc[book_opposed.index[-1], "book_imbalance"] = -0.1

    assert _onsets(_build(trade_opposed))["arm"].tolist() == _ARMS[:2]
    assert _onsets(_build(book_opposed))["arm"].tolist() == _ARMS[:3]
    assert _onsets(_build(_candidate_minutes()))["arm"].tolist() == _ARMS


def test_each_arm_uses_the_frozen_sixty_minute_non_overlap_rule() -> None:
    """Suppress rows at or before 60 minutes and retain the first later row."""
    closes = [100.0]
    open_interests = [1_000.0]
    for _ in range(16):
        closes.append(closes[-1] * 1.003)
        open_interests.append(open_interests[-1] * 1.002)

    full = _onsets(_build(_minutes(closes, open_interests)))
    full = full.loc[full["arm"].eq(_ARMS[-1])]

    assert full["decision_at"].tolist() == [
        pd.Timestamp("2026-08-01T00:20:00Z"),
        pd.Timestamp("2026-08-01T01:25:00Z"),
    ]


def test_naive_timestamps_fail_instead_of_becoming_utc() -> None:
    """Reject minutes whose original timestamp semantics are not timezone-aware."""
    minutes = _candidate_minutes()
    minutes["minute"] = minutes["minute"].dt.tz_localize(None)

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        _build(minutes)


def test_duplicate_minutes_fail_explicitly() -> None:
    """Reject duplicate causal decisions rather than silently aggregating them."""
    minutes = pd.concat([_candidate_minutes(), _candidate_minutes().iloc[[-1]]])

    with pytest.raises(ValueError, match="ordered unique"):
        _build(minutes)


def test_null_source_feature_fails_explicitly() -> None:
    """Reject incomplete common-source evidence before bar construction."""
    minutes = _candidate_minutes()
    minutes.loc[4, "book_imbalance"] = float("nan")

    with pytest.raises(ValueError, match="finite"):
        _build(minutes)


def test_unsupported_quantile_fails_explicitly() -> None:
    """Prevent an unregistered threshold from entering the preflight search."""
    with pytest.raises(ValueError, match="unsupported quantile"):
        _build(_candidate_minutes(), quantile=0.85)


def test_output_is_count_only_and_contains_no_outcome_or_authority_fields() -> None:
    """Keep the signal builder on the preregistered measurement side of the boundary."""
    result = _build(_candidate_minutes())
    forbidden = {
        "forward_quotes",
        "forward_prices",
        "returns",
        "fees",
        "funding",
        "pnl",
        "orders",
        "execution_authority",
    }

    assert forbidden.isdisjoint(result.columns)
    assert set(result["arm"]) == set(_ARMS)
    assert result["quantile"].eq(0.75).all()
