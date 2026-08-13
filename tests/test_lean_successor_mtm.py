"""Lean-successor mark-to-market input tests."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.current_cohort_shared_portfolio import (
    CohortOutcome,
    CohortTradeSpec,
)
from hypervector.research.evidence_selected_portfolio import AcceptedPortfolioOutcome
from hypervector.research.lean_successor_mtm import (
    RawLifecycleTerms,
    active_completed_bar_marks,
    build_marked_lifecycles,
    scale_cohort_outcomes,
)
from hypervector.research.shared_trade_portfolio import SharedTradeOutcome


def _cohort() -> CohortOutcome:
    source = SharedTradeOutcome(
        "trade",
        "SOL",
        100,
        300,
        500.0,
        0.03,
        0.03375,
        0.30,
        "signal",
    )
    return CohortOutcome("range", "long", source)


def test_scale_cohort_outcomes_changes_only_economic_exposure() -> None:
    scaled = scale_cohort_outcomes((_cohort(),), 2.0)[0]

    assert scaled.trade_id == "trade"
    assert scaled.outcome.margin_fraction == pytest.approx(0.06)
    assert scaled.outcome.entry_fee_usd == pytest.approx(0.0675)
    assert scaled.outcome.net_pnl_usd == pytest.approx(0.60)


def test_raw_terms_join_to_exact_accepted_shared_account_size() -> None:
    spec = CohortTradeSpec("range", "SOL", 75.0, 5.0, 4.5)
    accepted = AcceptedPortfolioOutcome(
        "trade",
        "range",
        "SOL",
        "long",
        100,
        300,
        500.0,
        15.0,
        0.03375,
        0.6825,
        500.6825,
        "signal",
    )
    raw = RawLifecycleTerms(
        "range",
        "SOL",
        "long",
        100,
        300,
        100.0,
        101.0,
        0.75,
        75.0,
        0.0675,
        0.0,
        0.6825,
    )

    marked = build_marked_lifecycles((accepted,), (raw,), {("range", "SOL"): spec})

    assert marked[0].quantity == pytest.approx(0.75)
    assert marked[0].entry_fee_usd == pytest.approx(0.03375)
    assert marked[0].exit_fee_usd == pytest.approx(0.03375)
    assert marked[0].net_pnl_usd == pytest.approx(0.6825)


def test_completed_marks_are_shifted_and_restricted_to_open_lifecycles() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("1970-01-01", periods=5, freq="1min", tz="UTC"),
            "close": [100.0] * 5,
            "high": [101.0] * 5,
            "low": [99.0] * 5,
        }
    )
    lifecycle = RawLifecycleTerms(
        "range",
        "SOL",
        "long",
        60_000,
        240_000,
        100.0,
        100.0,
        1.0,
        100.0,
        0.0,
        0.0,
        0.0,
    )

    marks = active_completed_bar_marks(bars, (lifecycle,), bar_minutes=1)

    assert list(marks.index.as_unit("ns").asi8 // 1_000_000) == [
        120_000,
        180_000,
        240_000,
    ]


def test_raw_lifecycle_terms_require_economic_reconciliation() -> None:
    with pytest.raises(ValueError, match="does not reconcile"):
        RawLifecycleTerms(
            "range",
            "SOL",
            "long",
            100,
            200,
            100.0,
            101.0,
            1.0,
            100.0,
            0.0,
            0.0,
            2.0,
        )
