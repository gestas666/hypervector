"""Tests for backend-authored compatible-profile performance summaries."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_trade_performance import (
    build_all_time_trade_performance,
    build_trade_performance,
)


def test_all_time_live_performance_keeps_profiles_out_of_compatible_scope() -> None:
    """The user ledger must aggregate every live lifecycle across profiles."""
    report = build_all_time_trade_performance(
        [
            _trade("hulk", 1.25, symbol="BTC", side="long"),
            _trade("breakout", -0.25, symbol="HYPE", side="short"),
        ]
    )

    assert report["scope"] == "all_live_history"
    assert report["total"]["closed_trades"] == 2
    assert report["total"]["net_pnl_usd"] == pytest.approx(1.0)
    assert report["by_strategy"]["hulk"]["wins"] == 1
    assert report["by_strategy"]["breakout"]["losses"] == 1
    assert "current_profile" not in report
    assert "current_run" not in report


def test_profit_factor_uses_gross_wins_over_absolute_gross_losses() -> None:
    """Profit factor must retain gross outcomes rather than infer from net PnL."""
    report = build_trade_performance(
        [
            _trade("alpha", 1.25),
            _trade("alpha", -0.25),
            _trade("beta", 0.50),
        ]
    )

    total = report["total"]
    strategies = report["by_strategy"]
    assert total["profit_factor"] == pytest.approx(7.0)
    assert strategies["alpha"]["profit_factor"] == pytest.approx(5.0)
    assert strategies["beta"]["profit_factor"] is None


def test_performance_reports_concentration_friction_and_sequence_drawdown() -> None:
    """Sparse positive totals must expose outlier and friction sensitivity."""
    report = build_all_time_trade_performance(
        [
            _trade("alpha", 2.0),
            _trade("alpha", -1.0),
            _trade("alpha", 3.0),
            _trade("alpha", -2.0),
        ]
    )

    total = report["total"]
    assert total["mean_trade_net_pnl_usd"] == pytest.approx(0.5)
    assert total["median_trade_net_pnl_usd"] == pytest.approx(0.5)
    assert total["median_trade_return_on_margin_pct"] == pytest.approx(10.0)
    assert total["largest_winner_usd"] == pytest.approx(3.0)
    assert total["largest_winner_share_of_gross_profit_pct"] == pytest.approx(60.0)
    assert total["net_pnl_excluding_largest_winner_usd"] == pytest.approx(-1.0)
    assert total["maximum_closed_sequence_drawdown_usd"] == pytest.approx(2.0)
    assert total["gross_market_pnl_usd"] == pytest.approx(2.076)
    assert total["fees_as_pct_of_positive_gross_market_pnl"] == pytest.approx(
        0.08 / 5.038 * 100.0
    )
    assert total["execution_cash_drag_usd"] == pytest.approx(0.076)
    assert total[
        "execution_cash_drag_as_pct_of_positive_gross_market_pnl"
    ] == pytest.approx(0.076 / 5.038 * 100.0)


def test_empty_performance_has_explicit_null_diagnostics() -> None:
    """An empty current run must not manufacture repeatability evidence."""
    total = build_all_time_trade_performance([])["total"]

    for field in (
        "mean_trade_net_pnl_usd",
        "median_trade_net_pnl_usd",
        "median_trade_return_on_margin_pct",
        "largest_winner_usd",
        "largest_winner_share_of_gross_profit_pct",
        "net_pnl_excluding_largest_winner_usd",
        "fees_as_pct_of_positive_gross_market_pnl",
        "execution_cash_drag_as_pct_of_positive_gross_market_pnl",
    ):
        assert total[field] is None
    assert total["maximum_closed_sequence_drawdown_usd"] == 0.0
    assert total["gross_market_pnl_usd"] == 0.0
    assert total["execution_cash_drag_usd"] == 0.0


def test_performance_partitions_one_strategy_by_exact_symbol() -> None:
    """Portfolio learning must not pool unlike provider-symbol executions."""
    report = build_trade_performance(
        [
            _trade("alpha", 1.25, symbol="BTC"),
            _trade("alpha", -0.25, symbol="HYPE"),
        ]
    )

    pairs = report["by_provider_symbol"]
    assert pairs["alpha|BTC"]["closed_trades"] == 1
    assert pairs["alpha|BTC"]["net_pnl_usd"] == pytest.approx(1.25)
    assert pairs["alpha|HYPE"]["closed_trades"] == 1
    assert pairs["alpha|HYPE"]["net_pnl_usd"] == pytest.approx(-0.25)
    assert report["total"]["net_pnl_usd"] == pytest.approx(1.0)


def test_provider_symbol_performance_retains_exact_side_splits() -> None:
    """Opposite directions must remain visible inside one provider pair."""
    report = build_trade_performance(
        [
            _trade("alpha", 1.25, symbol="BTC", side="long"),
            _trade("alpha", -0.25, symbol="BTC", side="short"),
        ]
    )

    sides = report["by_provider_symbol"]["alpha|BTC"]["by_side"]
    assert sides["long"]["closed_trades"] == 1
    assert sides["long"]["net_pnl_usd"] == pytest.approx(1.25)
    assert sides["short"]["closed_trades"] == 1
    assert sides["short"]["net_pnl_usd"] == pytest.approx(-0.25)


def test_reduced_research_trade_omits_unavailable_side_breakdown() -> None:
    """Total-only challenger records remain valid without inventing direction."""
    trade = _trade("alpha", 1.25)
    trade.pop("side")

    report = build_trade_performance([trade])

    pair = report["by_provider_symbol"]["alpha|BTC"]
    assert pair["closed_trades"] == 1
    assert "by_side" not in pair


def test_partial_side_coverage_fails_instead_of_publishing_a_partial_split() -> None:
    """One known side cannot silently represent a pair with unknown directions."""
    unknown = _trade("alpha", -0.25)
    unknown.pop("side")

    with pytest.raises(ValueError, match="side coverage"):
        build_trade_performance([_trade("alpha", 1.25), unknown])


def test_current_profile_is_partitioned_from_compatible_history() -> None:
    """Current policy evidence cannot inherit outcomes from older fingerprints."""
    old_win = _trade("alpha", 1.25)
    old_win["source_profile_fingerprint"] = "old-profile"
    current_loss = _trade("alpha", -0.25)
    current_loss["source_profile_fingerprint"] = "current-profile"

    report = build_trade_performance(
        [old_win, current_loss],
        current_profile_fingerprint="current-profile",
    )

    assert report["mixed_profile_history"] is True
    assert report["profile_fingerprint_count"] == 2
    assert report["total"]["net_pnl_usd"] == pytest.approx(1.0)
    current = report["current_profile"]
    assert current["profile_fingerprint"] == "current-profile"
    assert current["total"]["closed_trades"] == 1
    assert current["total"]["net_pnl_usd"] == pytest.approx(-0.25)
    assert current["by_strategy"]["alpha"] == current["total"]


def test_current_profile_partition_requires_complete_trade_provenance() -> None:
    """A partially tagged journal must fail instead of publishing a false subset."""
    tagged = _trade("alpha", 1.25)
    tagged["source_profile_fingerprint"] = "current-profile"

    with pytest.raises(ValueError, match="profile fingerprint coverage"):
        build_trade_performance(
            [tagged, _trade("alpha", -0.25)],
            current_profile_fingerprint="current-profile",
        )


def test_current_run_is_separate_from_same_profile_history() -> None:
    """A reused profile must not leak an older run into the session record."""
    prior = _trade("alpha", 1.25)
    prior["source_profile_fingerprint"] = "same-profile"
    prior["source_run_id"] = "prior-run"
    current = _trade("alpha", -0.25)
    current["source_profile_fingerprint"] = "same-profile"
    current["source_run_id"] = "current-run"

    report = build_trade_performance(
        [prior, current],
        current_profile_fingerprint="same-profile",
        current_run_id="current-run",
    )

    assert report["current_profile"]["total"]["closed_trades"] == 2
    assert report["current_run"]["run_id"] == "current-run"
    assert report["current_run"]["total"]["closed_trades"] == 1
    assert report["current_run"]["total"]["net_pnl_usd"] == pytest.approx(-0.25)


def test_process_run_windows_keep_profile_strategy_and_side_attribution() -> None:
    """Process runs must be comparable without claiming independent samples."""
    first_long = _trade("alpha", 1.25, side="long")
    first_long.update(
        source_run_id="run-a",
        source_profile_fingerprint="profile-a",
    )
    first_short = _trade("alpha", -0.25, side="short")
    first_short.update(
        source_run_id="run-a",
        source_profile_fingerprint="profile-a",
    )
    second_long = _trade("alpha", -0.50, side="long")
    second_long.update(
        source_run_id="run-b",
        source_profile_fingerprint="profile-b",
    )

    report = build_trade_performance([first_long, first_short, second_long])

    windows = report["process_run_windows"]
    assert windows["contract"] == {
        "report_only": True,
        "performance_gate": False,
        "balance_gate": False,
        "automatic_strategy_changes": False,
        "execution_authority": "none",
    }
    assert windows["window_basis"] == "backend_process_run_id"
    assert windows["statistical_independence_established"] is False
    assert windows["run_count"] == 2
    assert windows["positive_runs"] == 1
    assert windows["negative_runs"] == 1
    assert windows["by_run"]["run-a"]["profile_fingerprint"] == "profile-a"
    assert windows["by_run"]["run-a"]["total"]["net_pnl_usd"] == pytest.approx(1.0)
    assert windows["by_run"]["run-b"]["profile_fingerprint"] == "profile-b"
    pair = windows["by_provider_symbol"]["alpha|BTC"]
    assert pair["runs_with_closes"] == 2
    assert pair["positive_runs"] == 1
    assert pair["negative_runs"] == 1
    assert pair["by_side"]["long"]["runs_with_closes"] == 2
    assert pair["by_side"]["long"]["positive_runs"] == 1
    assert pair["by_side"]["short"]["runs_with_closes"] == 1
    assert pair["by_side"]["short"]["negative_runs"] == 1


def test_process_run_window_rejects_one_run_bound_to_multiple_profiles() -> None:
    """One process run cannot silently combine incompatible profile identities."""
    first = _trade("alpha", 1.25)
    first.update(source_run_id="run-a", source_profile_fingerprint="profile-a")
    second = _trade("alpha", -0.25)
    second.update(source_run_id="run-a", source_profile_fingerprint="profile-b")

    with pytest.raises(ValueError, match="multiple profile fingerprints"):
        build_trade_performance([first, second])


def _trade(
    strategy_id: str,
    net_pnl_usd: float,
    *,
    symbol: str = "BTC",
    side: str = "long",
) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "side": side,
        "net_pnl_usd": net_pnl_usd,
        "entry_margin_used_usd": 5.0,
        "net_return_on_margin_pct": net_pnl_usd / 5.0 * 100.0,
        "fees_usd": 0.02,
        "funding_usd": 0.001,
    }
