"""Fail-closed, development-only diagnostics for exact HIP-3 archives."""

from __future__ import annotations

import pandas as pd

from hypervector.data.oxa_api import validate_market_symbol
from hypervector.research.hip3_gap_loss_sensitivity import (
    conservative_gap_loss_sensitivity,
)
from hypervector.research.mu_hip3_archive_candidate import (
    MuArchiveCandidateResult,
    MuArchiveFamilyResult,
    MuArchiveTrack,
    MuArchiveTrial,
    select_hip3_development_track,
)
from hypervector.research.mu_hip3_archive_reporting import (
    _evidence_at_or_before,
    _stale_exit_quote,
    _stale_l2_row,
    _verified_entry_risk_path_resolution,
    _verified_risk_path_resolution,
    partition_trade_path_quality,
    report_summary,
    track_identity,
)
from hypervector.research.mu_hip3_candidate import (
    MuPartitionResult,
    summarize_trades,
)
from hypervector.research.mu_hip3_development_path_diagnostic import (
    hip3_development_path_threshold_diagnostic,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)


def build_hip3_development_diagnostic(
    results: tuple[MuArchiveCandidateResult, ...],
    bars_by_timeframe: dict[str, pd.DataFrame],
    *,
    expected_symbol: str,
    expected_start_utc: pd.Timestamp,
    expected_end_utc: pd.Timestamp,
    funding_complete: bool,
) -> dict[str, object]:
    """Freeze one selected development track without evaluating OOS economics."""
    _require_scope(
        results,
        bars_by_timeframe,
        expected_symbol,
        expected_start_utc,
        expected_end_utc,
        funding_complete,
    )
    track = select_hip3_development_track(results)
    result, family, partition, trial = _selected_evidence(results, track)
    bars = _development_bars(bars_by_timeframe[track.timeframe], partition)
    path = _path_evidence(bars, partition, track)
    thresholds = hip3_development_path_threshold_diagnostic(
        bars_by_timeframe[track.timeframe],
        partition,
        track=track,
        windows=result.windows,
    )
    economics = _economics(partition, result.symbol)
    gap_sensitivity = _gap_sensitivity(partition, thresholds)
    folds = _fold_stability(trial, result)
    suitability = _suitability(partition, path, folds)
    return {
        "development_selected_track": track_identity(track),
        "development_window": {
            "start_utc": partition.start_utc.isoformat(),
            "end_utc": partition.end_utc.isoformat(),
        },
        "selected_family_trial_count": len(family.trials),
        "development_economics": economics,
        "fold_stability": folds,
        "technical_path_evidence": path,
        "development_path_thresholds": thresholds,
        "development_gap_loss_sensitivity": gap_sensitivity,
        "out_of_sample_economics": "WITHHELD_NOT_EVALUATED",
        "future_live_research_suitability": suitability,
    }


def _gap_sensitivity(
    partition: MuPartitionResult,
    thresholds: dict[str, object],
) -> dict[str, object]:
    cumulative = thresholds["cumulative_thresholds_ms"]
    if not isinstance(cumulative, dict):
        raise ValueError("HIP-3 threshold evidence must be an object")
    threshold = cumulative["15000"]
    if not isinstance(threshold, dict):
        raise ValueError("HIP-3 15000ms threshold evidence must be an object")
    return conservative_gap_loss_sensitivity(
        partition.nominal,
        partition.stress,
        threshold,
        threshold_ms=15_000,
    )


def _require_scope(
    results: tuple[MuArchiveCandidateResult, ...],
    bars_by_timeframe: dict[str, pd.DataFrame],
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    funding_complete: bool,
) -> None:
    validate_market_symbol(symbol, "hip3")
    if not results:
        raise ValueError("HIP-3 development diagnostic requires results")
    if not funding_complete:
        raise ValueError(
            "HIP-3 development diagnostic requires complete funding evidence"
        )
    expected = (_utc(start), _utc(end))
    for result in results:
        if result.symbol != symbol:
            raise ValueError("HIP-3 development result does not match exact symbol")
        observed = (
            _utc(result.windows.development_start_utc),
            _utc(result.windows.holdout_end_utc),
        )
        if observed != expected:
            raise ValueError(
                "HIP-3 development result bounds do not match exact window"
            )
        _require_development_partitions(result)
    if set(bars_by_timeframe) != {item.timeframe for item in results}:
        raise ValueError("HIP-3 development bars and result timeframes disagree")


def _require_development_partitions(result: MuArchiveCandidateResult) -> None:
    for family in result.families:
        names = tuple(partition.name for partition in family.partitions)
        if names != ("development",):
            raise ValueError("HIP-3 diagnostic accepts one development partition only")


def _selected_evidence(
    results: tuple[MuArchiveCandidateResult, ...],
    track: MuArchiveTrack,
) -> tuple[
    MuArchiveCandidateResult,
    MuArchiveFamilyResult,
    MuPartitionResult,
    MuArchiveTrial,
]:
    matches = [
        (result, family)
        for result in results
        for family in result.families
        if result.timeframe == track.timeframe
        and family.proposed_provider_id == track.provider_id
    ]
    if len(matches) != 1:
        raise ValueError("HIP-3 development track must match one family")
    result, family = matches[0]
    trials = [trial for trial in family.trials if trial.config == track.config]
    if len(trials) != 1 or len(family.partitions) != 1:
        raise ValueError("HIP-3 selected development evidence is ambiguous")
    return result, family, family.partitions[0], trials[0]


def _development_bars(
    bars: pd.DataFrame,
    partition: MuPartitionResult,
) -> pd.DataFrame:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("HIP-3 development bars require a timezone-aware index")
    selected = bars.index.to_series().ge(
        partition.start_utc
    ) & bars.index.to_series().lt(partition.end_utc)
    scoped = bars.loc[selected].copy()
    if (
        scoped.empty
        or not scoped.index.is_monotonic_increasing
        or not scoped.index.is_unique
    ):
        raise ValueError(
            "HIP-3 development bars must be ordered, unique, and non-empty"
        )
    return scoped


def _economics(partition: MuPartitionResult, symbol: str) -> dict[str, object]:
    return {
        "nominal": report_summary(
            partition.nominal,
            partition.start_utc,
            partition.end_utc,
            symbol=symbol,
        ),
        "stress": report_summary(
            partition.stress,
            partition.start_utc,
            partition.end_utc,
            symbol=symbol,
        ),
    }


def _fold_stability(
    trial: MuArchiveTrial,
    result: MuArchiveCandidateResult,
) -> dict[str, object]:
    bounds = result.windows.development_folds
    if len(trial.folds) != len(bounds) or not trial.folds:
        raise ValueError("HIP-3 selected trial fold evidence is incomplete")
    reports = [
        report_summary(report, start, end, symbol=result.symbol)
        for report, (start, end) in zip(trial.folds, bounds, strict=True)
    ]
    sides = {trade.direction for report in trial.folds for trade in report.trades}
    return {
        "scenario": "nominal_selection_friction",
        "folds": reports,
        "positive_folds": sum(report.net_pnl_usd > 0.0 for report in trial.folds),
        "total_folds": len(trial.folds),
        "worst_fold_net_pnl_usd": min(report.net_pnl_usd for report in trial.folds),
        "observed_sides": sorted(sides),
    }


def _path_evidence(
    bars: pd.DataFrame,
    partition: MuPartitionResult,
    track: MuArchiveTrack,
) -> dict[str, object]:
    summary = partition_trade_path_quality(
        bars,
        partition,
        timeframe=track.timeframe,
        family=track.family,
    )
    output: dict[str, object] = {"status": summary["status"]}
    for scenario, report in (
        ("nominal", partition.nominal),
        ("stress", partition.stress),
    ):
        lifecycles = _unresolved_lifecycles(bars, report, track.timeframe, track.family)
        expected = int(summary[scenario]["unresolved_lifecycle_trades"])
        if len(lifecycles) != expected:
            raise ValueError("HIP-3 lifecycle causes disagree with path summary")
        output[scenario] = {"summary": summary[scenario], "lifecycles": lifecycles}
    return output


def _unresolved_lifecycles(
    bars: pd.DataFrame,
    report: SharedPortfolioReport,
    timeframe: str,
    family: str,
) -> list[dict[str, object]]:
    full = _verified_risk_path_resolution(bars)
    entry = _verified_entry_risk_path_resolution(bars, full)
    interval = pd.Timedelta(minutes=5 if timeframe == "5m" else 15)
    output: list[dict[str, object]] = []
    for trade in report.trades:
        causes = _trade_causes(bars, trade, full, entry, interval, family)
        if any(causes.values()):
            output.append({"lifecycle_key": _lifecycle_key(trade), **causes})
    return output


def _trade_causes(
    bars: pd.DataFrame,
    trade: SharedPortfolioTrade,
    full: pd.Series,
    entry: pd.Series,
    interval: pd.Timedelta,
    family: str,
) -> dict[str, bool]:
    entry_at = pd.Timestamp(trade.entry_time_utc)
    exit_at = pd.Timestamp(trade.exit_time_utc)
    active = bars.index.to_series().lt(exit_at) & (bars.index + interval > entry_at)
    return {
        "mark_path_unresolved": bool((~full.loc[active]).any()),
        "entry_mark_path_unresolved": not _evidence_at_or_before(entry, entry_at),
        "stale_l2_decision": family == "breakout_pressure"
        and _stale_l2_row(bars, pd.Timestamp(trade.signal_time_utc), "decision"),
        "stale_l2_entry": _stale_l2_row(bars, entry_at, "entry"),
        "stale_l2_exit": _stale_exit_quote(bars, trade),
        "data_gap_exit": trade.exit_reason == "data_gap",
    }


def _lifecycle_key(trade: SharedPortfolioTrade) -> str:
    return (
        f"{trade.direction}|{trade.signal_time_utc}|"
        f"{trade.entry_time_utc}|{trade.exit_time_utc}"
    )


def _suitability(
    partition: MuPartitionResult,
    path: dict[str, object],
    folds: dict[str, object],
) -> dict[str, object]:
    stress = summarize_trades(partition.stress.trades)["all"]
    sides = {trade.direction for trade in partition.stress.trades}
    checks = {
        "technical_paths_resolved": path["status"] == "resolved",
        "nominal_net_positive": partition.nominal.net_pnl_usd > 0.0,
        "stress_net_positive": partition.stress.net_pnl_usd > 0.0,
        "stress_positive_without_largest_winner": (
            stress.net_without_largest_winner_usd > 0.0
        ),
        "both_sides_observed": sides == {"long", "short"},
        "majority_positive_development_folds": (
            int(folds["positive_folds"]) * 2 > int(folds["total_folds"])
        ),
        "no_liquidations": (
            partition.nominal.liquidations + partition.stress.liquidations == 0
        ),
    }
    if not checks["technical_paths_resolved"]:
        status = "NOT_SUITABLE_TECHNICALLY_UNRESOLVED"
    elif not all(checks.values()):
        status = "NOT_SUITABLE_DEVELOPMENT_ECONOMICS"
    else:
        status = "DEVELOPMENT_SUPPORTED_REQUIRES_UNTOUCHED_OOS_AND_RUNTIME_PARITY"
    return {
        "status": status,
        "checks": checks,
        "automatic_promotion": False,
        "live_roster_change": False,
    }


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError("HIP-3 diagnostic bounds require UTC offsets")
    return timestamp.tz_convert("UTC")
