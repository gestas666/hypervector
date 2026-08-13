"""Report-only screening and shortlist selection for archive replay candidates."""

from __future__ import annotations

import hashlib
from typing import cast

import pandas as pd

from hypervector.regime.composite import classify_multitimeframe
from hypervector.regime.hypervelocity_eval import evaluate_hypervelocity_regimes
from hypervector.regime.hypervelocity_candidates import (
    HypervelocityRegimeCandidate,
    hypervelocity_candidate_matrix,
)
from hypervector.research.hypervelocity_candidate_eval import (
    CandidateBarrierReport,
    evaluate_independent_barriers,
)
from hypervector.research.hypervelocity_portfolio_eval import (
    SerialPortfolioReport,
    evaluate_serial_portfolio,
)
from hypervector.research.maker_replay_models import MakerReplayReport

Screening = dict[str, object]


def _indexed_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if isinstance(bars.index, pd.DatetimeIndex):
        return bars.copy()
    if "timestamp" not in bars:
        raise ValueError("archive comparison bars require timestamps")
    indexed = bars.copy()
    indexed.index = pd.DatetimeIndex(pd.to_datetime(indexed["timestamp"], utc=True))
    return indexed


def _barrier_summary(report: CandidateBarrierReport) -> dict[str, object]:
    count = report.total_signals
    return {
        "total_signals": count,
        "targets_completed": report.targets_completed,
        "liquidations": report.liquidations,
        "unresolved": report.unresolved,
        "ambiguous_barriers": report.ambiguous_barriers,
        "target_rate_pct": 100.0 * report.targets_completed / count if count else 0.0,
        "liquidation_rate_pct": 100.0 * report.liquidations / count if count else 0.0,
        "net_pnl_usd": report.net_pnl_usd,
        "net_pnl_per_signal_usd": report.net_pnl_usd / count if count else 0.0,
        "median_hold_seconds": report.median_hold_seconds,
        "median_adverse_excursion_margin_pct": (
            report.median_adverse_excursion_margin_pct
        ),
    }


def _portfolio_summary(report: SerialPortfolioReport) -> dict[str, object]:
    summary = report.to_dict()
    summary.pop("trades")
    return summary


def _decision_fingerprint(decisions: pd.DataFrame) -> str:
    required = ["entry_direction", "structural_direction"]
    missing = set(required).difference(decisions.columns)
    if missing:
        raise ValueError(f"candidate decisions missing columns: {sorted(missing)}")
    canonical = (
        decisions[required]
        .fillna("")
        .astype(str)
        .to_csv(index=False, header=False, lineterminator="\n")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _screen_candidate(
    bars: pd.DataFrame,
    positions: pd.DataFrame,
    candidate: HypervelocityRegimeCandidate,
) -> Screening:
    decisions = classify_multitimeframe(bars, config=candidate.config)
    barrier = evaluate_independent_barriers(bars, decisions)
    portfolio = evaluate_serial_portfolio(bars, decisions)
    regime = evaluate_hypervelocity_regimes(
        bars,
        positions,
        config=candidate.config,
    )
    return {
        "candidate": candidate.to_dict(),
        "decision_fingerprint": _decision_fingerprint(decisions),
        "regime": regime.to_dict(),
        "barrier": _barrier_summary(barrier),
        "portfolio": _portfolio_summary(portfolio),
    }


def screen_candidate_matrix(
    bars: pd.DataFrame,
    positions: pd.DataFrame,
) -> tuple[Screening, ...]:
    """Retain report-only screening results for every bounded candidate."""
    indexed = _indexed_bars(bars)
    return tuple(
        _screen_candidate(indexed, positions, candidate)
        for candidate in hypervelocity_candidate_matrix()
    )


def _rank_key(screening: Screening) -> tuple[float, float, float, float, str]:
    portfolio = cast(dict[str, object], screening["portfolio"])
    regime = cast(dict[str, object], screening["regime"])
    alignment = cast(dict[str, object], regime["entry_alignment"])
    candidate = cast(dict[str, object], screening["candidate"])
    return (
        float(portfolio["final_marked_equity"]),
        float(portfolio["maximum_drawdown_pct"]),
        -float(portfolio["liquidations"]),
        float(alignment["direction_recall_pct"]),
        str(candidate["candidate_id"]),
    )


def _changed_count(screening: Screening) -> int:
    candidate = cast(dict[str, object], screening["candidate"])
    return len(cast(list[str], candidate["changed_groups"]))


def _identifier(screening: Screening) -> str:
    candidate = cast(dict[str, object], screening["candidate"])
    return str(candidate["candidate_id"])


def select_archive_shortlist(
    screenings: tuple[Screening, ...],
) -> tuple[Screening, ...]:
    """Keep controls plus the strongest single- and pair-change diagnostics."""
    by_id = {_identifier(item): item for item in screenings}
    required = {"pareto60_baseline", "bbwp_blueprint_full"}
    if not required.issubset(by_id):
        raise ValueError("screenings require baseline and full BBWP controls")
    singles = [item for item in screenings if _changed_count(item) == 1]
    pairs = [item for item in screenings if _changed_count(item) == 2]
    if not singles or not pairs:
        raise ValueError("screenings require single- and pair-change candidates")
    controls = (by_id["pareto60_baseline"], by_id["bbwp_blueprint_full"])
    best_single = max(singles, key=_rank_key)
    used = {str(item["decision_fingerprint"]) for item in (*controls, best_single)}
    distinct_pairs = [
        item for item in pairs if str(item["decision_fingerprint"]) not in used
    ]
    best_pair = max(distinct_pairs or pairs, key=_rank_key)
    return (*controls, best_single, best_pair)


def summarize_execution_reports(
    reports: dict[str, MakerReplayReport],
) -> dict[str, object]:
    """Summarize fill sensitivity without hiding the full replay reports."""
    equities = [report.final_equity for report in reports.values()]
    completed = [report.completed_trades for report in reports.values()]
    liquidations = [report.liquidations for report in reports.values()]
    drawdowns = [report.maximum_drawdown_pct for report in reports.values()]
    return {
        "minimum_final_equity": min(equities),
        "maximum_final_equity": max(equities),
        "minimum_completed_trades": min(completed),
        "maximum_completed_trades": max(completed),
        "fill_assumption_equity_spread": max(equities) - min(equities),
        "minimum_liquidations": min(liquidations),
        "maximum_liquidations": max(liquidations),
        "best_maximum_drawdown_pct": max(drawdowns),
        "worst_maximum_drawdown_pct": min(drawdowns),
        "funding_adjusted": False,
        "liquidation_adjusted": True,
        "drawdown_available": True,
        "liquidation_model": "bbo_mark_proxy_partial_liquidation_v1",
    }
