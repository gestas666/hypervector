"""Tests for the HYPE breakout-direction retest entry policy."""

from __future__ import annotations

import pytest

from hypervector.live.hype_breakout_retest_policy import (
    BreakoutRetestBar,
    HypeBreakoutRetestPolicy,
)

_MINUTE_MS = 60_000
_START_MS = 1_786_000_000_000


def _bar(
    minute: int,
    *,
    breakout_side: str | None,
    structural_side: str | None,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    state_5m: str = "BREAKOUT",
) -> BreakoutRetestBar:
    return BreakoutRetestBar(
        decision_time_ms=_START_MS + minute * _MINUTE_MS,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        state_5m=state_5m,
        breakout_side=breakout_side,
        structural_side=structural_side,
    )


def test_opposed_structure_arms_fade_in_structural_direction() -> None:
    """An opposed v1 direction becomes a reclaim fade, never a breakout chase."""
    policy = HypeBreakoutRetestPolicy()

    result = policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            0,
            breakout_side="short",
            structural_side="long",
            open_price=100.3,
            high_price=100.4,
            low_price=99.8,
            close_price=100.0,
        ),
        breakout_onset=True,
        breakout_boundary_price=100.1,
    )

    assert result.state == "armed"
    assert result.side == "long"
    assert result.breakout_side == "short"
    assert result.structural_side == "long"
    assert result.mode == "fade"
    assert result.eligible is False
    assert result.reason == "awaiting_failed_breakout_reclaim"
    assert result.boundary_price == pytest.approx(100.1)


def test_failed_short_breakout_bullish_reclaim_confirms_long_fade() -> None:
    """A v1 long fade waits for the short breakout boundary to be reclaimed."""
    policy = HypeBreakoutRetestPolicy()
    policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            0,
            breakout_side="short",
            structural_side="long",
            open_price=100.3,
            high_price=100.4,
            low_price=99.8,
            close_price=100.0,
        ),
        breakout_onset=True,
        breakout_boundary_price=100.1,
    )

    result = policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            1,
            breakout_side=None,
            structural_side="long",
            open_price=100.00,
            high_price=100.25,
            low_price=99.85,
            close_price=100.20,
            state_5m="RANGE",
        ),
        breakout_onset=False,
        breakout_boundary_price=None,
    )

    assert result.state == "confirmed"
    assert result.side == "long"
    assert result.mode == "fade"
    assert result.eligible is True
    assert result.reason == "failed_breakout_reclaim_confirmed"
    assert result.age_bars == 1


def test_aligned_short_retest_and_rejection_confirms_continuation() -> None:
    """An aligned short enters after a bearish rejection of the broken low."""
    policy = HypeBreakoutRetestPolicy()
    policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            0,
            breakout_side="short",
            structural_side="short",
            open_price=100.3,
            high_price=100.4,
            low_price=99.8,
            close_price=100.0,
        ),
        breakout_onset=True,
        breakout_boundary_price=100.1,
    )

    result = policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            1,
            breakout_side="short",
            structural_side="short",
            open_price=100.05,
            high_price=100.12,
            low_price=99.85,
            close_price=99.90,
        ),
        breakout_onset=False,
        breakout_boundary_price=None,
    )

    assert result.state == "confirmed"
    assert result.side == "short"
    assert result.mode == "continuation"
    assert result.eligible is True
    assert result.reason == "breakout_retest_confirmed"


def test_long_continuation_and_short_fade_are_symmetric() -> None:
    """Both entry directions use the same touch-and-close confirmation contract."""
    long_policy = HypeBreakoutRetestPolicy()
    short_policy = HypeBreakoutRetestPolicy()
    long_policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            0,
            breakout_side="long",
            structural_side="long",
            open_price=99.7,
            high_price=100.2,
            low_price=99.6,
            close_price=100.1,
        ),
        breakout_onset=True,
        breakout_boundary_price=100.0,
    )
    short_policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            0,
            breakout_side="long",
            structural_side="short",
            open_price=99.7,
            high_price=100.2,
            low_price=99.6,
            close_price=100.1,
        ),
        breakout_onset=True,
        breakout_boundary_price=100.0,
    )

    long_result = long_policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            1,
            breakout_side="long",
            structural_side="long",
            open_price=99.98,
            high_price=100.2,
            low_price=99.95,
            close_price=100.15,
        ),
        breakout_onset=False,
        breakout_boundary_price=None,
    )
    short_result = short_policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            1,
            breakout_side=None,
            structural_side="short",
            open_price=100.08,
            high_price=100.15,
            low_price=99.8,
            close_price=99.9,
            state_5m="RANGE",
        ),
        breakout_onset=False,
        breakout_boundary_price=None,
    )

    assert (long_result.side, long_result.mode, long_result.eligible) == (
        "long",
        "continuation",
        True,
    )
    assert (short_result.side, short_result.mode, short_result.eligible) == (
        "short",
        "fade",
        True,
    )


def test_failed_short_reversal_expires_after_three_completed_bars() -> None:
    """A breakout chased by price reversal cannot remain armed indefinitely."""
    policy = HypeBreakoutRetestPolicy(window_bars=3)
    policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            0,
            breakout_side="short",
            structural_side="short",
            open_price=100.3,
            high_price=100.4,
            low_price=99.8,
            close_price=100.0,
        ),
        breakout_onset=True,
        breakout_boundary_price=100.1,
    )

    results = [
        policy.evaluate(
            symbol="HYPE",
            bar=_bar(
                minute,
                breakout_side="short",
                structural_side="short",
                open_price=100.1,
                high_price=100.2 + minute * 0.1,
                low_price=100.0,
                close_price=100.15 + minute * 0.1,
            ),
            breakout_onset=False,
            breakout_boundary_price=None,
        )
        for minute in range(1, 4)
    ]

    assert [result.state for result in results] == ["pending", "pending", "expired"]
    assert all(result.eligible is False for result in results)
    assert results[-1].reason == "retest_window_expired"


def test_breakout_state_loss_cancels_pending_setup() -> None:
    """A setup cannot confirm after its originating breakout state disappears."""
    policy = HypeBreakoutRetestPolicy()
    policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            0,
            breakout_side="long",
            structural_side="long",
            open_price=99.8,
            high_price=100.2,
            low_price=99.7,
            close_price=100.1,
        ),
        breakout_onset=True,
        breakout_boundary_price=100.0,
    )

    result = policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            1,
            breakout_side=None,
            structural_side="long",
            open_price=100.0,
            high_price=100.2,
            low_price=99.9,
            close_price=100.1,
            state_5m="RANGE",
        ),
        breakout_onset=False,
        breakout_boundary_price=None,
    )

    assert result.state == "expired"
    assert result.reason == "breakout_state_lost"
    assert result.eligible is False


def test_onset_without_direction_or_boundary_fails_closed() -> None:
    """Missing causal breakout information cannot create a success-shaped setup."""
    policy = HypeBreakoutRetestPolicy()

    missing_side = policy.evaluate(
        symbol="HYPE",
        bar=_bar(
            0,
            breakout_side=None,
            structural_side="long",
            open_price=100.0,
            high_price=100.2,
            low_price=99.8,
            close_price=100.1,
        ),
        breakout_onset=True,
        breakout_boundary_price=100.0,
    )
    missing_boundary = policy.evaluate(
        symbol="BTC",
        bar=_bar(
            0,
            breakout_side="long",
            structural_side="long",
            open_price=100.0,
            high_price=100.2,
            low_price=99.8,
            close_price=100.1,
        ),
        breakout_onset=True,
        breakout_boundary_price=None,
    )

    missing_structure = policy.evaluate(
        symbol="ETH",
        bar=_bar(
            0,
            breakout_side="long",
            structural_side=None,
            open_price=100.0,
            high_price=100.2,
            low_price=99.8,
            close_price=100.1,
        ),
        breakout_onset=True,
        breakout_boundary_price=100.0,
    )

    assert missing_side.reason == "breakout_direction_unavailable"
    assert missing_boundary.reason == "breakout_boundary_unavailable"
    assert missing_structure.reason == "structural_direction_unavailable"
    assert missing_side.state == missing_boundary.state == missing_structure.state
    assert missing_side.state == "unavailable"
