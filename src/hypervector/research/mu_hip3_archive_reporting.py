"""Immutable reporting helpers for multi-timeframe ``xyz:MU`` research."""

from __future__ import annotations

from dataclasses import asdict

from pandas.api.types import is_bool_dtype

import pandas as pd

from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars
from hypervector.research.hip3_market_session_reporting import (
    scheduled_session_trade_diagnostics,
)
from hypervector.research.mu_hip3_archive_candidate import (
    MuArchiveCandidateResult,
    MuArchiveFamilyResult,
    MuArchiveTrack,
)
from hypervector.research.mu_hip3_candidate import (
    MU_SYMBOL,
    MuPartitionResult,
    summarize_trades,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)

_SECONDS_PER_WEEK = 604_800.0
_MAXIMUM_HOLD_SECONDS = 86_400.0


def build_timeframe_report(
    midpoint: Hip3MidpointBars,
    audit: dict[str, object],
    result: MuArchiveCandidateResult,
) -> dict[str, object]:
    """Return coverage, recipes, and promotion evidence for one timeframe."""
    assessments = {
        family.family: family_assessment(family) for family in result.families
    }
    return {
        "archive_coverage": archive_coverage(midpoint, audit, result.timeframe),
        "windows": partition_windows(result),
        "families": {
            family.family: family_report(
                family, assessments[family.family], symbol=result.symbol
            )
            for family in result.families
        },
        "out_of_sample_track_membership_is_global_and_frozen_before_holdout": True,
        "side_assessments_are_diagnostics_not_selection_inputs": True,
    }


def family_report(
    family: MuArchiveFamilyResult,
    assessment: dict[str, object],
    *,
    symbol: str | None = None,
) -> dict[str, object]:
    """Serialize one tuned family without dropping chronological diagnostics."""
    return {
        "proposed_provider_id": family.proposed_provider_id,
        "proposed_profile_id": family.proposed_profile_id,
        "searched_trial_count": len(family.trials),
        "selected_config": asdict(family.selected_config),
        "trials": [_trial_summary(trial) for trial in family.trials],
        "partitions": {
            partition.name: {
                "start_utc": partition.start_utc.isoformat(),
                "end_utc": partition.end_utc.isoformat(),
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
            for partition in family.partitions
        },
        "assessment": assessment,
    }


def family_assessment(family: MuArchiveFamilyResult) -> dict[str, object]:
    """Return non-authoritative diagnostics for a fully evaluated family."""
    partitions = {item.name: item for item in family.partitions}
    if "validation" not in partitions or "holdout" not in partitions:
        return {
            "status": "development_only_not_advanced",
            "authoritative": False,
            "supportive": False,
            "checks": {},
            "side_assessments": {},
        }
    validation = partitions["validation"]
    holdout = partitions["holdout"]
    observed_sides = {
        trade.direction
        for partition in (validation, holdout)
        for trade in partition.nominal.trades
    }
    nominal_robustness = summarize_trades(holdout.nominal.trades)["all"]
    stress_robustness = summarize_trades(holdout.stress.trades)["all"]
    checks = {
        "validation_nominal_positive": validation.nominal.net_pnl_usd > 0.0,
        "validation_stress_positive": validation.stress.net_pnl_usd > 0.0,
        "holdout_nominal_positive": holdout.nominal.net_pnl_usd > 0.0,
        "holdout_stress_positive": holdout.stress.net_pnl_usd > 0.0,
        "combined_out_of_sample_observed_both_sides": observed_sides
        == {"long", "short"},
        "holdout_nominal_positive_without_largest_winner": (
            nominal_robustness.net_without_largest_winner_usd > 0.0
        ),
        "holdout_stress_positive_without_largest_winner": (
            stress_robustness.net_without_largest_winner_usd > 0.0
        ),
        "no_validation_or_holdout_liquidations": (
            validation.nominal.liquidations
            + validation.stress.liquidations
            + holdout.nominal.liquidations
            + holdout.stress.liquidations
            == 0
        ),
    }
    return {
        "status": "descriptive_non_authoritative",
        "authoritative": False,
        "supportive": False,
        "diagnostic_checks_pass": all(checks.values()),
        "checks": checks,
        "side_assessments": {
            side: _side_assessment(validation, holdout, side)
            for side in ("long", "short")
        },
    }


def validation_assessment(
    partition: MuPartitionResult,
    *,
    development_path_resolved: bool,
    validation_path_resolved: bool,
) -> dict[str, object]:
    """Decide advancement only with explicit technical path evidence."""
    if partition.name != "validation":
        raise ValueError("MU validation assessment requires validation evidence")
    return validation_assessment_with_path_evidence(
        partition,
        development_path_resolved,
        validation_path_resolved,
    )


def validation_assessment_with_path_evidence(
    partition: MuPartitionResult,
    development_path_resolved: bool,
    validation_path_resolved: bool,
) -> dict[str, object]:
    """Advance only when selected development and validation paths are resolved."""
    if partition.name != "validation":
        raise ValueError("MU validation assessment requires validation evidence")
    robustness = summarize_trades(partition.stress.trades)["all"]
    checks = {
        "nominal_positive": partition.nominal.net_pnl_usd > 0.0,
        "stress_positive": partition.stress.net_pnl_usd > 0.0,
        "stress_positive_without_largest_winner": (
            robustness.net_without_largest_winner_usd > 0.0
        ),
        "completed_trades_observed": partition.stress.completed_trades > 0,
        "no_nominal_or_stress_liquidations": (
            partition.nominal.liquidations + partition.stress.liquidations == 0
        ),
        "no_unresolved_data_gap_exits": not _has_data_gap(partition),
        "development_trade_paths_resolved": development_path_resolved,
        "validation_trade_paths_resolved": validation_path_resolved,
    }
    return {"advanced": all(checks.values()), "checks": checks}


def final_track_evaluation(
    validation: MuPartitionResult,
    holdout: MuPartitionResult | None,
    *,
    holdout_path_resolved: bool,
) -> dict[str, object]:
    """Evaluate one validation-frozen track once on untouched final holdout."""
    if holdout is None:
        return {"outcome": "NOT_EVALUATED_VALIDATION_REJECTED", "checks": {}}
    observed_sides = {
        trade.direction
        for partition in (validation, holdout)
        for trade in partition.stress.trades
    }
    robustness = summarize_trades(holdout.stress.trades)["all"]
    side_stress = {
        side: sum(
            trade.net_pnl_usd
            for partition in (validation, holdout)
            for trade in partition.stress.trades
            if trade.direction == side
        )
        for side in ("long", "short")
    }
    checks = {
        "holdout_nominal_positive": holdout.nominal.net_pnl_usd > 0.0,
        "holdout_stress_positive": holdout.stress.net_pnl_usd > 0.0,
        "holdout_stress_positive_without_largest_winner": (
            robustness.net_without_largest_winner_usd > 0.0
        ),
        "combined_out_of_sample_observed_both_sides": observed_sides
        == {"long", "short"},
        "combined_out_of_sample_stress_positive_each_side": all(
            value > 0.0 for value in side_stress.values()
        ),
        "no_holdout_nominal_or_stress_liquidations": (
            holdout.nominal.liquidations + holdout.stress.liquidations == 0
        ),
        "no_unresolved_data_gap_exits": not (
            _has_data_gap(validation) or _has_data_gap(holdout)
        ),
        "holdout_trade_paths_resolved": holdout_path_resolved,
    }
    return {
        "outcome": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "combined_out_of_sample_stress_net_usd_by_side": side_stress,
    }


def track_identity(track: MuArchiveTrack) -> dict[str, object]:
    """Serialize the immutable development-selected provider identity."""
    return {
        "symbol": track.symbol,
        "timeframe": track.timeframe,
        "family": track.family,
        "provider_id": track.provider_id,
        "profile_id": track.profile_id,
        "config": asdict(track.config),
    }


def proposed_runtime_contract(track: MuArchiveTrack) -> dict[str, object]:
    """Record the deployability contract required for archive/live parity."""
    return {
        **track_identity(track),
        "order_style": "taker_ioc",
        "maximum_stop_distance_bps": 80.0,
        "maximum_hold_seconds": 86_400,
        "provider_recipe_exit_policy": "honor",
        "signal_ohlc_source": "0xarchive_public_trade_ohlc_v1",
        "no_trade_bar_policy": "causal_prior_trade_close_with_segment_reset",
        "decision_pressure_source": "last_preclose_l2_snapshot",
        "live_decision_pressure_parity_status": (
            "blocked_live_collector_uses_first_postclose_snapshot"
        ),
        "live_candle_parity_status": "blocked_pending_row_for_row_test",
        "live_implementation_status": "not_implemented",
    }


def _side_assessment(
    validation: MuPartitionResult,
    holdout: MuPartitionResult,
    side: str,
) -> dict[str, object]:
    nominal = _side_trades(validation, holdout, side, stress=False)
    stress = _side_trades(validation, holdout, side, stress=True)
    nominal_summary = summarize_trades(nominal)["all"]
    stress_summary = summarize_trades(stress)["all"]
    checks = {
        "out_of_sample_observed": bool(nominal),
        "nominal_positive": nominal_summary.net_pnl_usd > 0.0,
        "stress_positive": stress_summary.net_pnl_usd > 0.0,
        "stress_positive_without_largest_winner": (
            stress_summary.net_without_largest_winner_usd > 0.0
        ),
        "no_liquidations": not any(
            trade.exit_reason == "liquidation" for trade in (*nominal, *stress)
        ),
    }
    return {
        "supportive": all(checks.values()),
        "checks": checks,
        "nominal": asdict(nominal_summary),
        "stress": asdict(stress_summary),
        "validation_trades": _side_count(validation.nominal.trades, side),
        "holdout_trades": _side_count(holdout.nominal.trades, side),
    }


def _side_trades(
    validation: MuPartitionResult,
    holdout: MuPartitionResult,
    side: str,
    *,
    stress: bool,
) -> tuple[SharedPortfolioTrade, ...]:
    reports = (
        validation.stress if stress else validation.nominal,
        holdout.stress if stress else holdout.nominal,
    )
    return tuple(
        trade
        for report in reports
        for trade in report.trades
        if trade.direction == side
    )


def _side_count(trades: tuple[SharedPortfolioTrade, ...], side: str) -> int:
    return sum(trade.direction == side for trade in trades)


def report_summary(
    report: SharedPortfolioReport,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    symbol: str | None = None,
) -> dict[str, object]:
    """Serialize metrics with overall and sliced weekly opportunity rates."""
    weeks = max((end - start).total_seconds() / _SECONDS_PER_WEEK, 1e-12)
    value = report.to_dict()
    value.pop("trades")
    value["trades_per_week"] = report.completed_trades / weeks
    value["diagnostics"] = {
        name: {**asdict(summary), "trades_per_week": summary.trades / weeks}
        for name, summary in summarize_trades(report.trades).items()
    }
    lateness = [
        max(
            (
                pd.Timestamp(trade.exit_time_utc) - pd.Timestamp(trade.entry_time_utc)
            ).total_seconds()
            - _MAXIMUM_HOLD_SECONDS,
            0.0,
        )
        for trade in report.trades
        if trade.exit_reason == "max_hold"
    ]
    value["maximum_hold_gap_censored_exits"] = sum(item > 0.0 for item in lateness)
    value["maximum_hold_lateness_seconds_max"] = max(lateness, default=0.0)
    value["data_gap_sensitivity"] = _data_gap_sensitivity(report)
    if symbol is not None:
        value["scheduled_oracle_session_diagnostics"] = (
            scheduled_session_trade_diagnostics(symbol, report.trades)
        )
    return value


def archive_coverage(
    midpoint: Hip3MidpointBars,
    audit: dict[str, object],
    timeframe: str,
) -> dict[str, object]:
    """Summarize cadence, gaps, and source density for one bar size."""
    bars = midpoint.bars
    gaps = bars["gap_before_bars"].astype(int)
    snapshots = bars["source_snapshot_count"].astype(int)
    intervals = bars["maximum_snapshot_interval_ms"].astype(float)
    unobserved = pd.concat(
        [
            intervals,
            bars["first_boundary_delay_ms"].astype(float),
            bars["end_boundary_age_ms"].astype(float),
        ],
        axis=1,
    ).max(axis=1)
    coverage = {
        "timeframe": timeframe,
        "archive_start_utc": midpoint.archive_start_utc.isoformat(),
        "archive_end_utc": midpoint.archive_end_utc.isoformat(),
        "archive_bundles": midpoint.archive_bundles,
        "book_snapshots": midpoint.archive_book_rows,
        "audit_book_snapshots": int(_number(audit.get("book_snapshots"))),
        "empty_book_windows": int(_number(audit.get("empty_book_windows", 0))),
        "empty_book_ranges_utc": audit.get("empty_book_ranges_utc", []),
        "expected_bars": midpoint.expected_bar_count,
        "observed_bars": len(bars),
        "missing_bars": midpoint.missing_bar_count,
        "gap_events": int(gaps.gt(0).sum()),
        "missing_bars_from_gaps": int(gaps.sum()),
        "maximum_gap_bars": int(gaps.max()),
        "snapshots_per_bar_min": int(snapshots.min()),
        "snapshots_per_bar_p50": float(snapshots.median()),
        "snapshots_per_bar_max": int(snapshots.max()),
        "first_boundary_delay_ms_p99": float(
            bars["first_boundary_delay_ms"].quantile(0.99)
        ),
        "end_boundary_age_ms_p99": float(bars["end_boundary_age_ms"].quantile(0.99)),
        "maximum_snapshot_interval_ms_max": float(intervals.max()),
        "maximum_snapshot_interval_ms_p99": float(intervals.quantile(0.99)),
        "bars_with_snapshot_interval_over_5000ms": int(intervals.gt(5_000).sum()),
        "bars_with_snapshot_interval_over_15000ms": int(intervals.gt(15_000).sum()),
        "bars_with_snapshot_interval_over_60000ms": int(intervals.gt(60_000).sum()),
        "maximum_unobserved_interval_ms_max": float(unobserved.max()),
        "maximum_unobserved_interval_ms_p99": float(unobserved.quantile(0.99)),
        "bars_with_unobserved_interval_over_15000ms": int(unobserved.gt(15_000).sum()),
        "single_snapshot_bars": int(snapshots.lt(2).sum()),
    }
    if "mark_path_complete" in bars:
        coverage.update(
            {
                "signal_ohlc_source": _single_text(
                    bars["signal_ohlc_source"], "signal_ohlc_source"
                ),
                "mark_complete_bars": int(
                    _strict_true_series(bars["mark_path_complete"]).sum()
                ),
                "mark_incomplete_bars": int(
                    (~_strict_true_series(bars["mark_path_complete"])).sum()
                ),
                "entry_mark_complete_bars": int(
                    _strict_true_series(bars["entry_mark_path_complete"]).sum()
                ),
                "entry_mark_incomplete_bars": int(
                    (~_strict_true_series(bars["entry_mark_path_complete"])).sum()
                ),
                "maximum_mark_interval_ms_max": float(
                    pd.to_numeric(
                        bars["maximum_mark_interval_ms"], errors="raise"
                    ).max()
                ),
                "entry_maximum_mark_interval_ms_max": float(
                    pd.to_numeric(
                        bars["entry_maximum_mark_interval_ms"], errors="raise"
                    ).max()
                ),
                "public_trade_rows_in_bars": int(
                    pd.to_numeric(bars["public_trade_count"], errors="raise").sum()
                ),
                "zero_trade_signal_bars": int(
                    _strict_true_series(bars["signal_ohlc_synthetic_no_trade"]).sum()
                ),
                "audit_public_trades": int(_number(audit.get("public_trades"))),
                "source_public_trade_rows": _single_integer(
                    bars["source_public_trade_rows"], "source_public_trade_rows"
                ),
                "canonical_public_trade_rows": _single_integer(
                    bars["canonical_public_trade_rows"],
                    "canonical_public_trade_rows",
                ),
                "duplicate_public_trade_rows": _single_integer(
                    bars["duplicate_public_trade_rows"],
                    "duplicate_public_trade_rows",
                ),
                "conflicting_duplicate_trade_ids": _single_integer(
                    bars["conflicting_duplicate_trade_ids"],
                    "conflicting_duplicate_trade_ids",
                ),
                "price_archive_mark_rows": _single_integer(
                    bars["price_archive_mark_rows"], "price_archive_mark_rows"
                ),
                "price_archive_missing_mark_rows": _single_integer(
                    bars["price_archive_missing_mark_rows"],
                    "price_archive_missing_mark_rows",
                ),
                "price_archive_empty_partitions": _single_integer(
                    bars["price_archive_empty_partitions"],
                    "price_archive_empty_partitions",
                ),
                "price_archive_maximum_observed_gap_ms": _single_integer(
                    bars["price_archive_maximum_observed_gap_ms"],
                    "price_archive_maximum_observed_gap_ms",
                ),
            }
        )
    return coverage


def _single_text(values: pd.Series, label: str) -> str:
    unique = set(values.astype(str))
    if len(unique) != 1:
        raise ValueError(f"MU {label} must have one immutable identity")
    return next(iter(unique))


def _single_integer(values: pd.Series, label: str) -> int:
    parsed = pd.to_numeric(values, errors="raise")
    unique = parsed.unique()
    if len(unique) != 1 or int(unique[0]) != unique[0] or unique[0] < 0:
        raise ValueError(f"MU {label} must have one non-negative integer")
    return int(unique[0])


def trade_path_quality(
    bars: pd.DataFrame,
    report: SharedPortfolioReport,
    *,
    timeframe: str,
    family: str,
) -> dict[str, object]:
    """Report lifecycle overlap with unresolved mark/tape risk evidence."""
    minutes = 5 if timeframe == "5m" else 15
    if family not in {"swing_ha", "breakout_pressure"}:
        raise ValueError("MU path quality requires a known candidate family")
    unobserved = (
        bars[
            [
                "first_boundary_delay_ms",
                "maximum_snapshot_interval_ms",
                "end_boundary_age_ms",
            ]
        ]
        .astype(float)
        .max(axis=1)
    )
    bad = unobserved.gt(15_000) | bars["source_snapshot_count"].astype(int).lt(2)
    resolved = _verified_risk_path_resolution(bars)
    entry_resolved = _verified_entry_risk_path_resolution(bars, resolved)
    unresolved = ~resolved
    overlap_trades = 0
    unresolved_entry_risk_trades = 0
    stale_decision_trades = 0
    stale_entry_trades = 0
    stale_exit_trades = 0
    overlap_bars: set[pd.Timestamp] = set()
    interval = pd.Timedelta(minutes=minutes)
    for trade in report.trades:
        entry = pd.Timestamp(trade.entry_time_utc)
        exit_at = pd.Timestamp(trade.exit_time_utc)
        active = bars.index.to_series().lt(exit_at) & (bars.index + interval > entry)
        affected = bars.index[active & unresolved]
        risk_unresolved = len(affected) > 0
        entry_risk_unresolved = not _evidence_at_or_before(
            entry_resolved,
            pd.Timestamp(trade.entry_time_utc),
        )
        decision_unresolved = family == "breakout_pressure" and _stale_l2_row(
            bars, pd.Timestamp(trade.signal_time_utc), "decision"
        )
        entry_unresolved = _stale_l2_row(
            bars, pd.Timestamp(trade.entry_time_utc), "entry"
        )
        exit_unresolved = _stale_exit_quote(bars, trade)
        overlap_trades += int(
            risk_unresolved
            or entry_risk_unresolved
            or decision_unresolved
            or entry_unresolved
            or exit_unresolved
        )
        unresolved_entry_risk_trades += int(entry_risk_unresolved)
        stale_decision_trades += int(decision_unresolved)
        stale_entry_trades += int(entry_unresolved)
        stale_exit_trades += int(exit_unresolved)
        overlap_bars.update(affected)
    return {
        "status": "resolved" if overlap_trades == 0 else "unresolved",
        "unresolved_lifecycle_trades": overlap_trades,
        "unresolved_lifecycle_bars": len(overlap_bars),
        "unresolved_entry_bar_risk_trades": unresolved_entry_risk_trades,
        "stale_l2_decision_trades": stale_decision_trades,
        "stale_l2_entry_trades": stale_entry_trades,
        "stale_l2_exit_trades": stale_exit_trades,
        "l2_outage_bars": int(bad.sum()),
        "verified_mark_trade_path_bars": int(resolved.sum()),
        "l2_outage_threshold_ms": 15_000,
    }


def _stale_l2_row(
    bars: pd.DataFrame,
    timestamp: pd.Timestamp,
    role: str,
) -> bool:
    """Return whether one decision/entry quote row lacks timely L2 evidence."""
    if role == "decision":
        if timestamp not in bars.index:
            return True
        row = bars.loc[timestamp]
        delay = float(row["end_boundary_age_ms"])
    else:
        candidates = bars.index[bars.index <= timestamp]
        if candidates.empty:
            return True
        row = bars.loc[candidates[-1]]
        column = "end_boundary_age_ms" if role == "close" else "first_boundary_delay_ms"
        delay = float(row[column])
    return delay > 15_000 or int(row["source_snapshot_count"]) < 2


def _stale_exit_quote(
    bars: pd.DataFrame,
    trade: SharedPortfolioTrade,
) -> bool:
    """Check the L2 boundary actually consumed by non-barrier exits."""
    open_quote_reasons = {"signal", "opposite_signal", "max_hold", "data_gap"}
    timestamp = pd.Timestamp(trade.exit_time_utc)
    if trade.exit_reason in open_quote_reasons:
        return _stale_l2_row(bars, timestamp, "entry")
    if trade.exit_reason == "end_of_data":
        return _stale_l2_row(bars, timestamp, "close")
    return False


def _verified_risk_path_resolution(bars: pd.DataFrame) -> pd.Series:
    required = {
        "risk_path_source",
        "mark_path_complete",
        "maximum_mark_interval_ms",
        "trade_bundle_complete",
    }
    if not required.issubset(bars.columns):
        return pd.Series(False, index=bars.index)
    source = (
        bars["risk_path_source"]
        .astype(str)
        .eq("0xarchive_mark_price_with_public_trade_context_v1")
    )
    mark_complete = _strict_true_series(bars["mark_path_complete"])
    trade_complete = _strict_true_series(bars["trade_bundle_complete"])
    mark_interval = pd.to_numeric(bars["maximum_mark_interval_ms"], errors="coerce")
    return (
        source
        & mark_complete
        & mark_interval.notna()
        & mark_interval.ge(0.0)
        & mark_interval.le(5_000.0)
        & trade_complete
    )


def _verified_entry_risk_path_resolution(
    bars: pd.DataFrame,
    full_path_resolved: pd.Series,
) -> pd.Series:
    required = {"entry_mark_path_complete", "entry_maximum_mark_interval_ms"}
    if not required.issubset(bars.columns):
        return pd.Series(False, index=bars.index)
    maximum_interval = pd.to_numeric(
        bars["entry_maximum_mark_interval_ms"], errors="coerce"
    )
    return (
        full_path_resolved
        & _strict_true_series(bars["entry_mark_path_complete"])
        & maximum_interval.notna()
        & maximum_interval.ge(0.0)
        & maximum_interval.le(5_000.0)
    )


def _evidence_at_or_before(
    evidence: pd.Series,
    timestamp: pd.Timestamp,
) -> bool:
    candidates = evidence.index[evidence.index <= timestamp]
    return bool(len(candidates) and evidence.loc[candidates[-1]])


def _strict_true_series(values: pd.Series) -> pd.Series:
    """Accept only an actual boolean evidence column containing true values."""
    if not is_bool_dtype(values.dtype):
        return pd.Series(False, index=values.index)
    return values.eq(True).fillna(False).astype(bool)


def partition_trade_path_quality(
    bars: pd.DataFrame,
    partition: MuPartitionResult,
    *,
    timeframe: str,
    family: str,
) -> dict[str, object]:
    """Union nominal and stress lifecycle coverage before qualification checks."""
    nominal = trade_path_quality(
        bars, partition.nominal, timeframe=timeframe, family=family
    )
    stress = trade_path_quality(
        bars, partition.stress, timeframe=timeframe, family=family
    )
    return {
        "status": (
            "resolved"
            if nominal["status"] == stress["status"] == "resolved"
            else "unresolved"
        ),
        "nominal": nominal,
        "stress": stress,
    }


def trade_frame(results: tuple[MuArchiveCandidateResult, ...]) -> pd.DataFrame:
    """Return one immutable trade sidecar across all tested timeframes."""
    rows: list[dict[str, object]] = []
    for result in results:
        rows.extend(_result_trade_rows(result))
    columns = ["timeframe", "family", "partition"]
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=columns)


def source_frame(
    bars_by_timeframe: dict[str, pd.DataFrame], funding: pd.DataFrame
) -> pd.DataFrame:
    """Return causal bar sources for both timeframes plus official funding."""
    frames: list[pd.DataFrame] = []
    for timeframe, bars in bars_by_timeframe.items():
        bar_rows = bars.reset_index(names="timestamp")
        bar_rows.insert(0, "symbol", MU_SYMBOL)
        bar_rows.insert(1, "record_type", f"hip3_l2_midpoint_{timeframe}")
        frames.append(bar_rows)
    funding_rows = funding.copy()
    funding_rows.insert(0, "symbol", MU_SYMBOL)
    funding_rows.insert(1, "record_type", "official_funding")
    return pd.concat([*frames, funding_rows], ignore_index=True, sort=False)


def partition_windows(result: MuArchiveCandidateResult) -> dict[str, object]:
    """Serialize strict positional development/validation/holdout windows."""
    value = result.windows
    return {
        "development_start_utc": value.development_start_utc.isoformat(),
        "development_end_utc": value.development_end_utc.isoformat(),
        "validation_end_utc": value.validation_end_utc.isoformat(),
        "holdout_end_utc": value.holdout_end_utc.isoformat(),
        "development_folds": [
            {"start_utc": start.isoformat(), "end_utc": end.isoformat()}
            for start, end in value.development_folds
        ],
    }


def _trial_summary(trial: object) -> dict[str, object]:
    development = getattr(trial, "development")
    folds = getattr(trial, "folds")
    return {
        "config": asdict(getattr(trial, "config")),
        "development": _compact_report(development),
        "folds": [_compact_report(report) for report in folds],
    }


def _compact_report(report: SharedPortfolioReport) -> dict[str, object]:
    directions = summarize_trades(report.trades)
    return {
        "completed_trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "net_pnl_usd": report.net_pnl_usd,
        "return_pct": report.return_pct,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "liquidations": report.liquidations,
        "long_trades": directions["long"].trades,
        "short_trades": directions["short"].trades,
    }


def _result_trade_rows(
    result: MuArchiveCandidateResult,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for family in result.families:
        for partition in family.partitions:
            scenarios = (("nominal", partition.nominal), ("stress", partition.stress))
            rows.extend(
                {
                    "timeframe": result.timeframe,
                    "family": family.family,
                    "partition": partition.name,
                    "friction_scenario": scenario,
                    "symbol": MU_SYMBOL,
                    **asdict(trade),
                }
                for scenario, report in scenarios
                for trade in report.trades
            )
    return rows


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("book_snapshots must be numeric")
    return float(value)


def _has_data_gap(partition: MuPartitionResult) -> bool:
    return any(
        trade.exit_reason == "data_gap"
        for report in (partition.nominal, partition.stress)
        for trade in report.trades
    )


def _data_gap_sensitivity(report: SharedPortfolioReport) -> dict[str, object]:
    gap_trades = tuple(
        trade for trade in report.trades if trade.exit_reason == "data_gap"
    )
    observed = sum(trade.net_pnl_usd for trade in gap_trades)
    stop_bound = sum(_gap_bound_net(trade, trade.stop_price) for trade in gap_trades)
    liquidation_bound = sum(
        _gap_bound_net(trade, trade.liquidation_price) for trade in gap_trades
    )
    return {
        "unresolved_gap_crossing_trades": len(gap_trades),
        "observed_first_recovery_quote_net_usd": observed,
        "portfolio_net_if_stop_bound_usd": report.net_pnl_usd - observed + stop_bound,
        "portfolio_net_if_liquidation_bound_usd": (
            report.net_pnl_usd - observed + liquidation_bound
        ),
        "bound_fee_note": "uses each trade's recorded total fees",
    }


def _gap_bound_net(trade: SharedPortfolioTrade, boundary_price: float | None) -> float:
    if boundary_price is None:
        return trade.net_pnl_usd
    sign = 1.0 if trade.direction == "long" else -1.0
    gross = sign * trade.quantity * (boundary_price - trade.entry_price)
    return gross - trade.fees_usd + trade.funding_cashflow_usd
