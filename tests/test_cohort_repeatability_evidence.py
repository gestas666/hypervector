"""Tests for report-only live trade repeatability evidence."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_repeatability_evidence import (
    build_repeatability_evidence,
)

_BASE_MS = 1_700_000_000_000
_HOUR_MS = 3_600_000
_PAIR = "test_fade_1m|HYPE"


def test_repeatability_discloses_cadence_and_winner_concentration() -> None:
    """A positive total must disclose whether one winner dominates it."""
    report = build_repeatability_evidence(
        [
            _trade("short", 0.232488, entry_hour=0, exit_hour=8),
            _trade("long", -0.223917, entry_hour=10, exit_hour=11),
            _trade("long", 0.899488, entry_hour=20, exit_hour=28),
            _trade("long", 0.096600, entry_hour=30, exit_hour=32),
        ]
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
        "trade_count_gate": False,
    }
    pair = report["by_provider_symbol"][_PAIR]
    assert pair["closed_trades"] == 4
    assert pair["evidence_state"] == "descriptive_multi_trade_sample"
    assert pair["observation_span_hours"] == pytest.approx(32.0)
    assert pair["trades_per_24h_observed"] == pytest.approx(3.0)
    assert pair["net_pnl_usd"] == pytest.approx(1.004659)
    assert pair["mean_net_pnl_usd"] == pytest.approx(0.25116475)
    assert pair["median_net_pnl_usd"] == pytest.approx(0.164544)
    assert pair["sample_stddev_net_pnl_usd"] == pytest.approx(0.4726749371)
    assert pair["largest_winner_usd"] == pytest.approx(0.899488)
    assert pair["largest_winner_share_of_gross_profit_pct"] == pytest.approx(
        73.21386711
    )
    assert pair["net_pnl_excluding_largest_winner_usd"] == pytest.approx(0.105171)
    assert pair["profit_forecast"] is None
    assert pair["by_side"]["long"]["net_pnl_usd"] == pytest.approx(0.772171)
    assert pair["by_side"]["long"][
        "net_pnl_excluding_largest_winner_usd"
    ] == pytest.approx(-0.127317)
    assert pair["by_side"]["short"]["trades_per_24h_observed"] is None


def test_single_trade_never_claims_an_observed_cadence() -> None:
    """One lifecycle is an outcome, not a repeatable arrival-rate estimate."""
    report = build_repeatability_evidence(
        [_trade("long", 0.25, entry_hour=0, exit_hour=1)]
    )

    pair = report["by_provider_symbol"][_PAIR]
    assert pair["evidence_state"] == "single_trade_only"
    assert pair["observation_span_hours"] == pytest.approx(1.0)
    assert pair["trades_per_24h_observed"] is None
    assert pair["sample_stddev_net_pnl_usd"] is None


def _trade(
    side: str,
    net_pnl_usd: float,
    *,
    entry_hour: int,
    exit_hour: int,
) -> dict[str, object]:
    return {
        "strategy_id": "test_fade_1m",
        "symbol": "HYPE",
        "side": side,
        "net_pnl_usd": net_pnl_usd,
        "entry": {"venue_timestamp_ms": _BASE_MS + entry_hour * _HOUR_MS},
        "exit": {"venue_timestamp_ms": _BASE_MS + exit_hour * _HOUR_MS},
    }
