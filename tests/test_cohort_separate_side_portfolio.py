"""Tests for report-only separate-side shared-portfolio experiments."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hypervector.research.cohort_separate_side_portfolio import (
    SidePortfolioVariant,
    build_side_portfolio_experiment,
)
from hypervector.research.current_cohort_shared_portfolio import CohortOutcome
from hypervector.research.shared_trade_portfolio import SharedTradeOutcome


def _outcome(
    strategy: str,
    symbol: str,
    side: str,
    entry_ms: int,
    net_pnl_usd: float,
) -> CohortOutcome:
    """Build one deterministic completed route-side lifecycle."""
    return CohortOutcome(
        strategy_id=strategy,
        side=side,
        outcome=SharedTradeOutcome(
            trade_id=f"{strategy}|{symbol}|{side}|{entry_ms}",
            symbol=symbol,
            entry_time_ms=entry_ms,
            exit_time_ms=entry_ms + 60_000,
            source_equity_usd=500.0,
            margin_fraction=0.03,
            entry_fee_usd=0.01,
            net_pnl_usd=net_pnl_usd,
            outcome="fixture_exit",
        ),
    )


def _ms(value: str) -> int:
    """Convert one UTC fixture timestamp to milliseconds."""
    return int(datetime.fromisoformat(value).replace(tzinfo=UTC).timestamp() * 1_000)


def test_variant_keeps_only_predeclared_route_sides() -> None:
    """A separate-side variant must exclude the opposite source direction."""
    development = _ms("2026-05-01T00:00:00")
    final = _ms("2026-06-01T00:00:00")
    outcomes = (
        _outcome("hype", "HYPE", "long", development, 2.0),
        _outcome("hype", "HYPE", "short", development + 120_000, -5.0),
        _outcome("range", "SOL", "short", development + 240_000, 3.0),
        _outcome("hype", "HYPE", "long", final, 1.0),
        _outcome("range", "SOL", "short", final + 120_000, 4.0),
    )
    variant = SidePortfolioVariant(
        variant_id="separate_core",
        route_sides=(
            ("hype", "HYPE", "long"),
            ("range", "SOL", "short"),
        ),
        strategy_priority=("hype", "range"),
        maximum_positions=2,
    )

    report = build_side_portfolio_experiment(
        outcomes,
        variants=(variant,),
        initial_equity_usd=500.0,
        development_end_utc="2026-05-28T00:00:00Z",
        final_start_utc="2026-05-29T00:00:00Z",
        final_end_utc="2026-07-28T00:00:00Z",
        evidence={"fixture": {"sha256": "0" * 64, "bytes": 1}},
    )

    result = report["variants"]["separate_core"]
    assert result["input_counts"] == {
        "development": 2,
        "opened_final_block": 2,
        "purged": 0,
    }
    assert result["development"]["net_pnl_usd"] == 5.0
    assert result["opened_final_block"]["net_pnl_usd"] == 5.0
    accepted = result["combined_available_blocks"]["accepted"]
    assert {(row["strategy_id"], row["side"]) for row in accepted} == {
        ("hype", "long"),
        ("range", "short"),
    }
    assert report["execution_authority"] == "none"
    assert report["automatic_promotion"] is False
    assert report["contract"]["source_friction_scope"] == (
        "source_lifecycle_net_after_stated_fees_funding_slippage"
    )
    assert report["contract"]["friction_recomputed"] is False


def test_experiment_rejects_unhashed_evidence() -> None:
    """Every source must carry immutable SHA-256 and byte-count identity."""
    development = _ms("2026-05-01T00:00:00")
    final = _ms("2026-06-01T00:00:00")
    outcomes = (
        _outcome("hype", "HYPE", "long", development, 1.0),
        _outcome("hype", "HYPE", "long", final, 1.0),
    )
    variant = SidePortfolioVariant(
        "long_only",
        (("hype", "HYPE", "long"),),
        ("hype",),
        1,
    )

    with pytest.raises(ValueError, match="evidence.*SHA-256"):
        build_side_portfolio_experiment(
            outcomes,
            variants=(variant,),
            initial_equity_usd=500.0,
            development_end_utc="2026-05-28T00:00:00Z",
            final_start_utc="2026-05-29T00:00:00Z",
            final_end_utc="2026-07-28T00:00:00Z",
            evidence={"fixture": {"bytes": 1}},
        )
