"""Exact short-only versus close-only opposite HIP-3 replay tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from hypervector.research.hip3_close_only_opposite_exit import (
    build_close_only_opposite_exit_comparison,
)
from hypervector.research.hip3_shadow_lifecycle_replay import (
    build_hip3_shadow_lifecycle_replay,
)
from hip3_shadow_lifecycle_fixtures import (
    book,
    candles,
    decision_time,
    decisions,
    funding,
    lifecycle_config,
    marks,
)


def test_short_only_entry_scope_does_not_turn_long_decision_into_entry() -> None:
    """A close-only side has no authority when the modeled route is flat."""
    rows = candles(32, None, periods=140)
    config = replace(lifecycle_config(), entry_sides=frozenset({"short"}))

    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decisions(rows, eligible_positions={32}),
        book_rows=(book(decision_time(rows, 32) + 1_000, 102.0),),
        candles=rows,
        mark_rows=(),
        funding_rows=funding(rows),
        config=config,
    )

    assert report["nominal"]["completed_lifecycles"] == 0
    assert report["nominal"]["censored_lifecycles"] == 0
    assert report["replay_contract"]["entry_sides"] == ["short"]


def test_close_only_long_closes_short_without_opening_or_reversing() -> None:
    """Compare the exact short-only control with one close-only long exit."""
    rows = candles(32, None, periods=140, side="short")
    rows.loc[34, ["open", "high", "low", "close"]] = [103.8, 104.2, 103.6, 104.0]
    decision_rows = list(
        deepcopy(decisions(rows, eligible_positions={32, 34}, side="short"))
    )
    opposite = decision_rows[34]["decision"]
    assert isinstance(opposite, dict)
    opposite["side"] = "long"
    opposite["decision_imbalance_10"] = 0.8
    entry_time = decision_time(rows, 32) + 1_000
    opposite_time = decision_time(rows, 34) + 500
    deadline = decision_time(rows, 32) + 24 * 60 * 60_000
    config = replace(
        lifecycle_config(),
        fixed_stop_bps=80.0,
        signal_exit_enabled=False,
        opposite_entry_exit_enabled=False,
        maximum_mark_gap_ms=60_000,
        entry_sides=frozenset({"short"}),
    )

    report = build_close_only_opposite_exit_comparison(
        decision_rows=tuple(decision_rows),
        book_rows=(
            book(entry_time, 98.0),
            book(opposite_time, 97.0),
            book(deadline, 96.0),
        ),
        candles=rows,
        mark_rows=marks(entry_time, deadline, 97.0, step_ms=60_000),
        funding_rows=funding(rows),
        config=config,
    )

    control = report["control"]["nominal"]
    challenger = report["challenger"]["nominal"]
    assert control["lifecycles"][0]["exit_reason"] == "max_hold"
    assert challenger["lifecycles"][0]["exit_reason"] == ("opposite_strategy_intent")
    assert challenger["completed_lifecycles"] == 1
    assert challenger["by_side"]["long"]["lifecycles"] == 0
    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
        "entry_sides": ["short"],
        "close_only_sides": ["long"],
    }
