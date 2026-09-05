"""Tests for non-gating portfolio strategy scorecards."""

from __future__ import annotations

from hypervector.research.cohort_strategy_scorecard import (
    build_strategy_scorecard,
)
from hypervector.live.sol_aligned_range_contract import (
    SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
)

_HYPE = "hype_breakout_onset_bidirectional_v1"
_HYPE_COMPRESSION = "hype_breakout_compression_pullback_bidirectional_v1"
_HYPE_ALIGNMENT = "hype_breakout_compression_alignment_bidirectional_v2"
_RANGE = "range_onset_bidirectional_v1"
_SOURCE = "hypervelocity_source_follow_bidirectional_5m_v1"
_ETH_PRECOMPRESSION = "eth_breakout_precompression_pullback_bidirectional_v1"
_HIP3_BREAKOUT_INDEX = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"
_HIP3_SWING_COMMODITY = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
_HIP3_SWING_INDEX = "hip3_swing_ha_sp500_spcx_bidirectional_v2"


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
    assert record["research_state"] == "historical_deployed_shape_negative"
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
    assert record["research_state"] == "historical_candidate"
    assert record["eligible_signals"] == 0
    assert record["resolved_signal_horizons"] == 0


def test_scorecard_preserves_eth_directional_research_as_report_only() -> None:
    """Pair-level display cannot hide opposite long and short qualifications."""
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


def test_scorecard_binds_sol_range_direction_stability() -> None:
    """SOL display must expose both sides and the long concentration caveat."""
    record = _scorecard_record(_RANGE, "SOL")
    long = record["directional_research"]["long"]
    short = record["directional_research"]["short"]
    assert long["research_state"] == "historical_candidate_concentrated"
    assert "19 trades" in long["cadence"]
    assert "49.2%" in long["summary"]
    assert short["research_state"] == "historical_candidate"
    assert "23 trades" in short["cadence"]
    assert "PF 4.580" in short["summary"]
    assert all(value["execution_effect"] == "report_only" for value in (long, short))


def test_scorecard_binds_eth_precompression_direction_rotation() -> None:
    """ETH display must bind the current report-only requalification state."""
    record = _scorecard_record(_ETH_PRECOMPRESSION, "ETH")
    long = record["directional_research"]["long"]
    short = record["directional_research"]["short"]
    assert long["research_state"] == "historical_candidate"
    assert "142 development" in long["cadence"]
    assert "PF 1.3109" in long["summary"]
    assert short["research_state"] == "contradictory"
    assert "140 development" in short["cadence"]
    assert "PF 0.9853" in short["summary"]
    assert record["research_state"] == "prospective_requalification_open_long_only"
    assert record["evidence_source"] == (
        "docs/research-journal/eth-breakout-precompression-pullback-v17.json"
    )
    assert "first exact long stopped" in record["historical_summary"]
    assert "zero short" in record["historical_summary"]


def test_scorecard_binds_hip3_side_instability() -> None:
    """HIP-3 aggregate gains must not conceal side and phase reversals."""
    sp500 = _scorecard_record(_HIP3_BREAKOUT_INDEX, "xyz:SP500")
    gold = _scorecard_record(_HIP3_SWING_COMMODITY, "xyz:GOLD")
    spcx = _scorecard_record(_HIP3_SWING_INDEX, "xyz:SPCX")

    assert {
        side["research_state"] for side in sp500["directional_research"].values()
    } == {"contradictory"}
    assert "+$1.1788" in sp500["directional_research"]["long"]["summary"]
    assert "+$1.0561" in sp500["directional_research"]["short"]["summary"]
    assert gold["directional_research"]["long"]["research_state"] == (
        "historical_transfer_negative"
    )
    assert gold["directional_research"]["short"]["research_state"] == "contradictory"
    assert {
        side["research_state"] for side in spcx["directional_research"].values()
    } == {"contradictory"}
    assert "+$14.2647" in spcx["directional_research"]["long"]["summary"]
    assert "+$3.1560" in spcx["directional_research"]["short"]["summary"]


def test_scorecard_marks_spcx_tested_side_timing_set_exhausted() -> None:
    """The route queue must not repeat timing splits already falsified."""
    spcx = _scorecard_record(_HIP3_SWING_INDEX, "xyz:SPCX")

    assert spcx["research_state"] == (
        "side_timing_set_falsified_new_mechanism_required"
    )
    assert spcx["evidence_source"] == (
        "docs/research-journal/spcx-side-mechanism-attribution-v1.json"
    )
    assert "eight timing/side arms" in spcx["historical_summary"]


def test_scorecard_marks_gold_tested_side_timing_set_exhausted() -> None:
    """GOLD must not remain queued for a side split already evaluated."""
    gold = _scorecard_record(_HIP3_SWING_COMMODITY, "xyz:GOLD")

    assert gold["research_state"] == (
        "side_timing_set_falsified_new_mechanism_required"
    )
    assert gold["evidence_source"] == (
        "docs/research-journal/hip3-entry-timing-challenger-v3.json"
    )
    assert "Zero of eight" in gold["historical_summary"]


def test_scorecard_binds_source_follow_deployed_shape_economics() -> None:
    """The source row must cite matched long, short, and combined mechanics."""
    key = f"{_SOURCE}|BTC"
    scorecard = build_strategy_scorecard(
        frozenset({(_SOURCE, "BTC")}),
        {key: {"count": 10, "eligible": 0}},
        {"by_provider_symbol": {key: _outcome(0, ())}},
    )

    record = scorecard["by_provider_symbol"][key]
    assert record["research_state"] == "historical_deployed_shape_negative"
    assert record["confidence"] == "medium"
    assert "782 trades" in record["historical_cadence"]
    assert "PF 0.6193" in record["historical_summary"]
    assert record["evidence_source"] == (
        "data/logs/research/source_follow_deployed_shape_btc_1y_20260804.json"
    )
    assert "365 trades" in record["directional_research"]["long"]["cadence"]
    assert "PF 0.5707" in record["directional_research"]["long"]["summary"]
    assert "417 trades" in record["directional_research"]["short"]["cadence"]
    assert "PF 0.6667" in record["directional_research"]["short"]["summary"]
    assert all(
        side["execution_effect"] == "report_only"
        for side in record["directional_research"].values()
    )
    assert record["strategy_edge_identifiable"] is False


def test_scorecard_binds_hype_deployed_extension_economics() -> None:
    """HYPE display must not conceal its exact negative historical replay."""
    key = f"{_HYPE}|HYPE"
    scorecard = build_strategy_scorecard(
        frozenset({(_HYPE, "HYPE")}),
        {key: {"count": 10, "eligible": 0}},
        {"by_provider_symbol": {key: _outcome(0, ())}},
    )

    record = scorecard["by_provider_symbol"][key]
    assert record["research_state"] == "historical_deployed_shape_negative"
    assert record["confidence"] == "medium"
    assert "2,029 raw onsets" in record["historical_cadence"]
    assert "PF 0.8524" in record["historical_summary"]
    assert "PF 0.9629" in record["historical_summary"]
    assert "5m intensity" in record["historical_summary"]
    assert "no cost-clearing feature" in record["historical_summary"]
    assert record["evidence_source"] == (
        "docs/reviews/2026-08-04-hype-authoritative-5m-entry-attribution.md"
    )
    assert record["directional_research"] == {}
    assert record["strategy_edge_identifiable"] is False


def test_scorecard_binds_exact_hype_compression_evidence() -> None:
    """The live 50/40 mapping must not appear as unreviewed in the cockpit."""
    record = _scorecard_record(_HYPE_COMPRESSION, "HYPE")

    assert record["research_state"] == (
        "development_positive_fold_unstable_confirmation_concentrated"
    )
    assert record["confidence"] == "low"
    assert "138 development" in record["historical_cadence"]
    assert "PF 1.1146" in record["historical_summary"]
    assert "-96.19 bps" in record["historical_summary"]
    assert record["evidence_source"] == (
        "data/logs/research/"
        "hype_compression_breakout_challenger_20260811_v4/report.json"
    )
    assert record["performance_gate"] is False


def test_scorecard_binds_causal_hype_alignment_replay() -> None:
    """The successor identity cites occupancy-aware evidence and its caveats."""
    record = _scorecard_record(_HYPE_ALIGNMENT, "HYPE")

    assert record["research_state"] == ("development_promising_exact_live_n2_mixed")
    assert record["confidence"] == "low"
    assert "41 causal development" in record["historical_cadence"]
    assert "3/5 positive folds" in record["historical_summary"]
    assert "+289.26 bps" in record["historical_summary"]
    assert "+$6.34" in record["historical_summary"]
    assert record["evidence_source"] == (
        "data/logs/research/bidirectional_cohort/"
        "v84_active_route_tui_evidence_refresh_20260903_v1.json"
    )
    assert record["performance_gate"] is False


def test_scorecard_binds_superseding_sol_aligned_rejection_without_a_gate() -> None:
    """The SOL row must retain the later nine-path rejection, not stale N4."""
    key = f"{SOL_ALIGNED_RANGE_FIXED60_STRATEGY}|SOL"
    scorecard = build_strategy_scorecard(
        frozenset({(SOL_ALIGNED_RANGE_FIXED60_STRATEGY, "SOL")}),
        {key: {"count": 4, "eligible": 4}},
        {"by_provider_symbol": {key: _outcome(4, (1.0, 2.0, 3.0, 4.0))}},
    )

    record = scorecard["by_provider_symbol"][key]
    assert record["research_state"] == "prospective_rejected_n9"
    assert record["confidence"] == "medium"
    assert "4W/5L" in record["historical_summary"]
    assert "-113.0855 bps" in record["historical_summary"]
    assert "PF 0.3472" in record["historical_summary"]
    assert "all-long" in record["historical_summary"]
    assert record["evidence_source"] == (
        "docs/research-journal/sol-aligned-range-v1.json"
    )
    assert record["performance_gate"] is False


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


def _scorecard_record(strategy_id: str, symbol: str) -> dict[str, object]:
    key = f"{strategy_id}|{symbol}"
    scorecard = build_strategy_scorecard(
        frozenset({(strategy_id, symbol)}),
        {key: {"count": 10, "eligible": 0}},
        {"by_provider_symbol": {key: _outcome(0, ())}},
    )
    return scorecard["by_provider_symbol"][key]


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
