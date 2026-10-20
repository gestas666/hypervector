"""Tests for non-gating portfolio strategy scorecards."""

from __future__ import annotations

import pytest

from hypervector.live import multi_asset_strategy_evidence
from hypervector.live.multi_asset_strategy_evidence_models import (
    StrategyDirectionalEvidence,
    StrategyResearchEvidence,
)
from hypervector.research.cohort_strategy_scorecard import (
    build_strategy_scorecard,
)

_HYPE = "hype_breakout_onset_bidirectional_v1"
_RANGE = "range_onset_bidirectional_v1"


def test_scorecard_separates_adverse_signal_paths_from_edge_claims() -> None:
    """A resolved adverse signal is descriptive and cannot reject or pause."""
    scorecard = build_strategy_scorecard(
        frozenset({(_HYPE, "HYPE")}),
        {f"{_HYPE}|HYPE": {"count": 100, "eligible": 1}},
        {
            "by_provider_symbol": {
                f"{_HYPE}|HYPE": _outcome(1, (-49.6, -35.2, -13.8, -34.6))
            }
        },
    )

    record = scorecard["by_provider_symbol"][f"{_HYPE}|HYPE"]
    assert record["forward_assessment"] == "descriptive_adverse_paths"
    assert record["resolved_signal_horizons"] == 4
    assert record["strategy_edge_identifiable"] is False
    assert record["execution_outcomes_identifiable"] is False
    assert record["performance_gate"] is False
    assert scorecard["contract"]["balance_gate"] is False
    assert scorecard["summary"]["descriptive_adverse_paths"] == 1


def test_scorecard_reports_missing_signal_evidence_without_success_shape() -> None:
    """A frequently evaluated setup remains unknown until it actually fires."""
    scorecard = build_strategy_scorecard(
        frozenset({(_RANGE, "SOL")}),
        {f"{_RANGE}|SOL": {"count": 200, "eligible": 0}},
        {"by_provider_symbol": {f"{_RANGE}|SOL": _outcome(0, ())}},
    )

    record = scorecard["by_provider_symbol"][f"{_RANGE}|SOL"]
    assert record["forward_assessment"] == "no_eligible_signal_evidence"
    assert record["research_state"] == "unreviewed_exact_mapping"
    assert record["evidence_source"] == "none"
    assert record["directional_research"] == {}
    assert record["eligible_signals"] == 0
    assert record["resolved_signal_horizons"] == 0


def test_scorecard_binds_registered_research_evidence_without_a_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reviewed evidence is displayed for its exact mapping and nowhere else."""
    _register(
        monkeypatch,
        StrategyResearchEvidence(
            _HYPE,
            "HYPE",
            "historical_deployed_shape_negative",
            "medium",
            "782 trades over one year",
            "PF 0.6193 after modeled costs",
            "evidence/hype.json",
        ),
    )
    scorecard = build_strategy_scorecard(
        frozenset({(_HYPE, "HYPE"), (_HYPE, "BTC")}),
        {},
        {"by_provider_symbol": {}},
    )

    record = scorecard["by_provider_symbol"][f"{_HYPE}|HYPE"]
    assert record["research_state"] == "historical_deployed_shape_negative"
    assert record["confidence"] == "medium"
    assert record["historical_cadence"] == "782 trades over one year"
    assert record["historical_summary"] == "PF 0.6193 after modeled costs"
    assert record["evidence_source"] == "evidence/hype.json"
    assert record["directional_research"] == {}
    assert record["strategy_edge_identifiable"] is False
    assert record["performance_gate"] is False
    other = scorecard["by_provider_symbol"][f"{_HYPE}|BTC"]
    assert other["research_state"] == "unreviewed_exact_mapping"


def test_scorecard_preserves_directional_research_as_report_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pair-level display cannot hide opposite long and short qualifications."""
    _register(
        monkeypatch,
        StrategyResearchEvidence(
            _RANGE,
            "ETH",
            "directional_candidate",
            "medium",
            "86 trades",
            "long and short disagree",
            "evidence/range-eth.json",
            directional_evidence=(
                StrategyDirectionalEvidence(
                    "long",
                    "historical_candidate",
                    "medium",
                    "45 trades",
                    "long survives costs",
                    "evidence/range-eth.json",
                ),
                StrategyDirectionalEvidence(
                    "short",
                    "contradictory",
                    "low",
                    "41 trades",
                    "short reverses by phase",
                    "evidence/range-eth.json",
                ),
            ),
        ),
    )
    scorecard = build_strategy_scorecard(
        frozenset({(_RANGE, "ETH")}),
        {f"{_RANGE}|ETH": {"count": 10, "eligible": 1}},
        {"by_provider_symbol": {f"{_RANGE}|ETH": _outcome(1, (2.0,))}},
    )

    record = scorecard["by_provider_symbol"][f"{_RANGE}|ETH"]
    long = record["directional_research"]["long"]
    short = record["directional_research"]["short"]
    assert long["research_state"] == "historical_candidate"
    assert long["confidence"] == "medium"
    assert "45 trades" in long["cadence"]
    assert short["research_state"] == "contradictory"
    assert "41 trades" in short["cadence"]
    assert all(value["execution_effect"] == "report_only" for value in (long, short))


def test_scorecard_attaches_exact_live_execution_without_creating_a_gate() -> None:
    """Resolved live outcomes are visible but cannot identify or gate edge."""
    key = f"{_HYPE}|HYPE"
    scorecard = build_strategy_scorecard(
        frozenset({(_HYPE, "HYPE")}),
        {key: {"count": 100, "eligible": 1}},
        {"by_provider_symbol": {key: _outcome(1, (2.0,))}},
        execution_by_pair={key: _execution_summary()},
    )

    record = scorecard["by_provider_symbol"][key]
    assert record["execution_outcomes_identifiable"] is True
    assert record["execution_performance"] == _execution_summary()
    assert record["strategy_edge_identifiable"] is False
    assert record["performance_gate"] is False
    assert scorecard["contract"]["balance_gate"] is False
    assert scorecard["summary"]["mappings_with_live_outcomes"] == 1


def test_scorecard_retains_descriptive_long_short_execution_splits() -> None:
    """Side evidence remains visible without changing bidirectional authority."""
    key = f"{_HYPE}|HYPE"
    execution = {
        **_execution_summary(),
        "by_side": {"long": _execution_summary()},
    }
    scorecard = build_strategy_scorecard(
        frozenset({(_HYPE, "HYPE")}),
        {key: {"count": 100, "eligible": 1}},
        {"by_provider_symbol": {key: _outcome(1, (2.0,))}},
        execution_by_pair={key: execution},
    )

    record = scorecard["by_provider_symbol"][key]
    assert record["execution_performance_by_side"] == {"long": _execution_summary()}
    assert record["performance_gate"] is False


def test_scorecard_attaches_repeatability_without_a_trade_count_gate() -> None:
    """Cadence and concentration remain descriptive execution evidence."""
    key = f"{_HYPE}|HYPE"
    scorecard = build_strategy_scorecard(
        frozenset({(_HYPE, "HYPE")}),
        {key: {"count": 100, "eligible": 1}},
        {"by_provider_symbol": {key: _outcome(1, (2.0,))}},
        execution_by_pair={key: _execution_summary()},
        repeatability_by_pair={key: _repeatability_summary()},
    )

    record = scorecard["by_provider_symbol"][key]
    assert record["repeatability_evidence"] == _repeatability_summary()
    assert scorecard["contract"]["trade_count_gate"] is False
    assert record["strategy_edge_identifiable"] is False


def _register(
    monkeypatch: pytest.MonkeyPatch,
    evidence: StrategyResearchEvidence,
) -> None:
    monkeypatch.setitem(
        multi_asset_strategy_evidence._EVIDENCE,
        (evidence.strategy_id, evidence.symbol),
        evidence,
    )


def _execution_summary() -> dict[str, object]:
    return {
        "closed_trades": 4,
        "wins": 3,
        "losses": 1,
        "breakeven": 0,
        "win_rate_pct": 75.0,
        "net_pnl_usd": 1.004659,
        "entry_margin_used_usd": 20.0,
        "net_return_on_margin_pct": 5.023295,
        "mean_trade_return_on_margin_pct": 5.1,
        "profit_factor": 5.48675,
        "fees_usd": 0.08,
        "funding_usd": -0.001,
    }


def _repeatability_summary() -> dict[str, object]:
    return {
        "strategy_id": _HYPE,
        "symbol": "HYPE",
        "closed_trades": 4,
        "evidence_state": "descriptive_multi_trade_sample",
        "first_entry_timestamp_ms": 1_700_000_000_000,
        "last_exit_timestamp_ms": 1_700_115_200_000,
        "observation_span_hours": 32.0,
        "trades_per_24h_observed": 3.0,
        "net_pnl_usd": 1.004659,
        "mean_net_pnl_usd": 0.25116475,
        "median_net_pnl_usd": 0.164544,
        "sample_stddev_net_pnl_usd": 0.4726749371,
        "gross_profit_usd": 1.228576,
        "gross_loss_usd": 0.223917,
        "profit_factor": 5.48675,
        "largest_winner_usd": 0.899488,
        "largest_winner_share_of_gross_profit_pct": 73.21386711,
        "net_pnl_excluding_largest_winner_usd": 0.105171,
        "by_side": {},
        "profit_forecast": None,
    }


def _outcome(eligible: int, means: tuple[float, ...]) -> dict[str, object]:
    horizons = {
        str(minutes): {
            "resolved": 1,
            "non_overlapping_resolved": 1,
            "mean_directional_close_return_bps": mean,
            "positive_directional_rate": float(mean > 0.0),
        }
        for minutes, mean in zip((5, 15, 30, 60), means)
    }
    return {
        "evaluations": 100,
        "eligible_evaluations": eligible,
        "by_evidence_class": {
            "eligible_signal": {"evaluations": eligible, "horizons": horizons}
        },
    }
