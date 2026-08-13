#!/usr/bin/env python3
"""Run full-archive, report-only bidirectional HIP-3 qualification."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.data.hl import fetch_hl_funding_history
from hypervector.data.hl_funding_evidence import read_complete_hl_funding_evidence
from hypervector.data.oxa_api import validate_market_symbol
from hypervector.data.oxa_price_archive import (
    OxaPriceArchiveConfig,
    load_verified_price_archive,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_breakout_pressure_transfer import (
    default_breakout_pressure_grid,
)
from hypervector.research.hip3_midpoint_bars import (
    Hip3MidpointBars,
    build_hip3_midpoint_bars,
)
from hypervector.research.hip3_market_sessions import oracle_session_contract
from hypervector.research.hip3_transfer_sources import attach_official_funding
from hypervector.research.hip3_venue_path_bars import (
    build_hip3_venue_path_bars,
    load_hip3_public_trades,
)
from hypervector.research.mu_hip3_archive_candidate import (
    MuArchiveCandidateResult,
    MuArchiveExecution,
    MuArchiveTrack,
    attach_hip3_track_partitions,
    canonical_mu_archive_windows,
    evaluate_hip3_archive_candidates,
    evaluate_hip3_archive_track_partition,
    select_hip3_development_track,
)
from hypervector.research.mu_hip3_artifacts import (
    publish_bundle,
    require_new_outputs,
    staged_file_reference,
    staging_paths,
)
from hypervector.research.mu_hip3_archive_reporting import (
    build_timeframe_report,
    final_track_evaluation,
    proposed_runtime_contract,
    partition_trade_path_quality,
    track_identity,
    validation_assessment_with_path_evidence,
)
from hypervector.research.hip3_archive_sidecars import (
    build_archive_source_frame,
    build_archive_trade_frame,
)
from hypervector.research.mu_hip3_archive_provenance import (
    require_unchanged_generator,
    source_tree_identity,
)
from hypervector.research.mu_hip3_candidate import MU_SYMBOL, MuPartitionResult
from hypervector.research.swing_ha_screen import base_trial_grid
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

_DEFAULT_DATABASE = Path("data/research/hip3_market.duckdb")
_DEFAULT_QUALIFICATION = Path(
    "data/logs/research/xyz_mu_qualification_20260810T093600Z.json"
)
_DEFAULT_LIQUIDITY = Path(
    "data/logs/research/xyz_mu_liquidity_profile_fee_sensitivity_20260810.json"
)
_DEFAULT_AUDIT = Path("data/logs/research/xyz_mu_l2_full_audit_20260810.json")
_DEFAULT_OUTPUT = Path(
    "data/logs/research/xyz_mu_full_archive_bidirectional_20260810_v1.json"
)
_DEFAULT_TRADES = Path(
    "data/logs/research/xyz_mu_full_archive_bidirectional_20260810_v1.trades.parquet"
)
_DEFAULT_SOURCES = Path(
    "data/logs/research/xyz_mu_full_archive_bidirectional_20260810_v1.sources.parquet"
)
_TIMEFRAME_SPECS = (("15m", 15, 96), ("5m", 5, 288))


class MidpointBuilder(Protocol):
    """Read-only full-archive midpoint materialization boundary."""

    def __call__(
        self,
        database_path: Path,
        *,
        symbol: str,
        bar_minutes: int = 15,
        start_utc: pd.Timestamp | None = None,
        end_utc: pd.Timestamp | None = None,
    ) -> Hip3MidpointBars:
        """Return audited causal midpoint bars."""
        ...


class FundingFetcher(Protocol):
    """Read-only official funding-history boundary."""

    def __call__(
        self,
        symbol: str,
        *,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp,
    ) -> pd.DataFrame:
        """Return exact official funding rows."""
        ...


class VenuePathLoader(Protocol):
    """Read-only venue mark/trade supplementation boundary."""

    def __call__(
        self,
        args: argparse.Namespace,
        midpoints: dict[str, Hip3MidpointBars],
        audit: dict[str, object],
    ) -> dict[str, Hip3MidpointBars]:
        """Return exact midpoint identities with verified risk paths attached."""
        ...


@dataclass(frozen=True)
class StagedQualification:
    """Single-track development, validation, and final evaluation state."""

    track: MuArchiveTrack
    validation: MuPartitionResult
    holdout: MuPartitionResult | None
    development_path: dict[str, object]
    validation_path: dict[str, object]
    holdout_path: dict[str, object] | None


def build_parser() -> argparse.ArgumentParser:
    """Return the execution-incapable archive research parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", type=_hip3_symbol_argument, default=MU_SYMBOL)
    parser.add_argument("--database", type=Path, default=_DEFAULT_DATABASE)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--funding", type=Path)
    parser.add_argument("--start", type=_utc_argument)
    parser.add_argument("--end", type=_utc_argument)
    parser.add_argument(
        "--qualification-report", type=Path, default=_DEFAULT_QUALIFICATION
    )
    parser.add_argument("--liquidity-report", type=Path, default=_DEFAULT_LIQUIDITY)
    parser.add_argument("--archive-audit-report", type=Path, default=_DEFAULT_AUDIT)
    parser.add_argument("--nominal-latency-bps-per-side", type=float, default=1.0)
    parser.add_argument("--stress-latency-bps-per-side", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--trades-output", type=Path, default=_DEFAULT_TRADES)
    parser.add_argument("--sources-output", type=Path, default=_DEFAULT_SOURCES)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    midpoint_builder: MidpointBuilder = build_hip3_midpoint_bars,
    funding_fetcher: FundingFetcher = fetch_hl_funding_history,
    venue_path_loader: VenuePathLoader | None = None,
    swing_configs: tuple[SwingHaSignalConfig, ...] | None = None,
    breakout_configs: tuple[Hip3BreakoutPressureConfig, ...] | None = None,
) -> dict[str, object]:
    """Evaluate complete archive evidence without granting execution authority."""
    symbol = str(args.symbol)
    _require_new(args.output, args.trades_output, args.sources_output)
    generator_identity = _generator_identity()
    qualification = _load_json(args.qualification_report)
    liquidity = _load_json(args.liquidity_report)
    audit = _load_json(args.archive_audit_report)
    _require_complete_audit(audit)
    _require_paired_trade_audit(audit)
    scope_start, scope_end = _audit_bound_scope(args, audit, symbol)
    midpoints = {
        timeframe: midpoint_builder(
            args.database,
            symbol=symbol,
            bar_minutes=bar_minutes,
            start_utc=scope_start,
            end_utc=scope_end,
        )
        for timeframe, bar_minutes, _hold_bars in _TIMEFRAME_SPECS
    }
    for midpoint in midpoints.values():
        _reconcile_archive(midpoint, audit, symbol)
    loader = venue_path_loader or _load_venue_path_midpoints
    midpoints = loader(args, midpoints, audit)
    _require_venue_path_midpoints(midpoints)
    _require_qualification_mark_start(midpoints)
    archive_start = min(item.archive_start_utc for item in midpoints.values())
    archive_end = max(item.archive_end_utc for item in midpoints.values())
    funding, funding_input = _load_funding_input(
        args,
        symbol,
        archive_start.floor("h"),
        archive_end.ceil("h"),
        funding_fetcher,
    )
    base_execution = _execution(args, qualification, liquidity, symbol)
    evaluated = _evaluate_timeframes(
        midpoints, funding, base_execution, swing_configs, breakout_configs
    )
    bars_by_timeframe, funding_evidence, executions, result_tuple, staged = evaluated
    trades = build_archive_trade_frame(result_tuple)
    sources = build_archive_source_frame(bars_by_timeframe, funding, symbol)
    stage_paths = staging_paths(args.output, args.trades_output, args.sources_output)
    report_stage, trades_stage, sources_stage = stage_paths
    try:
        write_immutable_parquet(trades_stage, trades)
        write_immutable_parquet(sources_stage, sources)
        report = _report(
            args,
            midpoints,
            audit,
            funding_evidence,
            executions,
            result_tuple,
            staged,
            generator_identity,
            symbol,
            funding_input,
        )
        report["trade_sidecar"] = staged_file_reference(
            args.trades_output, trades_stage, len(trades)
        )
        report["source_sidecar"] = staged_file_reference(
            args.sources_output, sources_stage, len(sources)
        )
        json.dumps(report, sort_keys=True)
        write_immutable_json(report_stage, report)
        _require_generator_unchanged(generator_identity)
        _require_funding_input_unchanged(args, symbol, funding_input)
        publish_bundle(
            (
                (trades_stage, args.trades_output),
                (sources_stage, args.sources_output),
                (report_stage, args.output),
            )
        )
        return report
    finally:
        for stage in stage_paths:
            stage.unlink(missing_ok=True)


def _evaluate_timeframes(
    midpoints: dict[str, Hip3MidpointBars],
    funding: pd.DataFrame,
    base_execution: MuArchiveExecution,
    swing_configs: tuple[SwingHaSignalConfig, ...] | None,
    breakout_configs: tuple[Hip3BreakoutPressureConfig, ...] | None,
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, object],
    dict[str, MuArchiveExecution],
    tuple[MuArchiveCandidateResult, ...],
    StagedQualification,
]:
    """Attach funding and evaluate 15m baseline plus 5m challenger."""
    bars_by_timeframe: dict[str, pd.DataFrame] = {}
    funding_evidence: dict[str, object] = {}
    development_results: list[MuArchiveCandidateResult] = []
    executions: dict[str, MuArchiveExecution] = {}
    common_windows = canonical_mu_archive_windows(
        max(item.archive_start_utc for item in midpoints.values()),
        min(item.archive_end_utc for item in midpoints.values()),
    )
    for timeframe, _bar_minutes, hold_bars in _TIMEFRAME_SPECS:
        bars, evidence = attach_official_funding(midpoints[timeframe].bars, funding)
        execution = replace(
            base_execution,
            maximum_hold_bars=hold_bars,
            **_risk_path_columns(bars),
        )
        bars_by_timeframe[timeframe] = bars
        funding_evidence[timeframe] = asdict(evidence)
        executions[timeframe] = execution
        development_results.append(
            evaluate_hip3_archive_candidates(
                bars,
                execution,
                timeframe=timeframe,
                partition_names=("development",),
                windows=common_windows,
                swing_configs=swing_configs or base_trial_grid(),
                breakout_configs=(breakout_configs or default_breakout_pressure_grid()),
            )
        )
    results = tuple(development_results)
    track = select_hip3_development_track(results)
    selected = next(result for result in results if result.timeframe == track.timeframe)
    selected_family = next(
        family
        for family in selected.families
        if family.proposed_provider_id == track.provider_id
    )
    development = next(
        partition
        for partition in selected_family.partitions
        if partition.name == "development"
    )
    selected_bars = bars_by_timeframe[track.timeframe]
    development_path = partition_trade_path_quality(
        selected_bars,
        development,
        timeframe=track.timeframe,
        family=track.family,
    )
    if development_path["status"] != "resolved":
        raise ValueError(
            "MU selected development path is unresolved; qualification aborts "
            "without selecting a replacement track"
        )
    validation = evaluate_hip3_archive_track_partition(
        bars_by_timeframe[track.timeframe],
        executions[track.timeframe],
        selected.windows,
        track,
        "validation",
    )
    validation_path = partition_trade_path_quality(
        selected_bars,
        validation,
        timeframe=track.timeframe,
        family=track.family,
    )
    assessment = validation_assessment_with_path_evidence(
        validation,
        development_path["status"] == "resolved",
        validation_path["status"] == "resolved",
    )
    advanced = bool(assessment["advanced"])
    holdout = (
        evaluate_hip3_archive_track_partition(
            bars_by_timeframe[track.timeframe],
            executions[track.timeframe],
            selected.windows,
            track,
            "holdout",
        )
        if advanced
        else None
    )
    holdout_path = (
        partition_trade_path_quality(
            selected_bars,
            holdout,
            timeframe=track.timeframe,
            family=track.family,
        )
        if holdout is not None
        else None
    )
    partitions = (validation,) if holdout is None else (validation, holdout)
    attached = attach_hip3_track_partitions(results, track, partitions)
    staged = StagedQualification(
        track,
        validation,
        holdout,
        development_path,
        validation_path,
        holdout_path,
    )
    return bars_by_timeframe, funding_evidence, executions, attached, staged


def _load_funding_input(
    args: argparse.Namespace,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    funding_fetcher: FundingFetcher,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load exact immutable funding when explicitly supplied, without network."""
    path = getattr(args, "funding", None)
    if path is None:
        frame = funding_fetcher(symbol, start_time=start, end_time=end)
        return frame, {
            "mode": "ephemeral_official_fetch",
            "symbol": symbol,
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
        }
    evidence = read_complete_hl_funding_evidence(Path(path), symbol)
    evidence.require_exact_window(_epoch_ms(start), _epoch_ms(end))
    return evidence.to_frame(), {
        "mode": "immutable_local_bundle",
        "symbol": symbol,
        **evidence.evidence,
    }


def _require_funding_input_unchanged(
    args: argparse.Namespace,
    symbol: str,
    expected: dict[str, object],
) -> None:
    """Reject publication if immutable local funding changed during replay."""
    path = getattr(args, "funding", None)
    if path is None:
        return
    observed = read_complete_hl_funding_evidence(Path(path), symbol).evidence
    for key in ("sha256", "manifest_sha256", "row_count"):
        if observed.get(key) != expected.get(key):
            raise ValueError(f"funding input changed during replay: {key}")


def _epoch_ms(value: pd.Timestamp) -> int:
    """Return exact UTC epoch milliseconds for one timezone-aware timestamp."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("funding bound must include a timezone")
    return int(timestamp.timestamp() * 1_000)


def _report(
    args: argparse.Namespace,
    midpoints: dict[str, Hip3MidpointBars],
    audit: dict[str, object],
    funding: dict[str, object],
    executions: dict[str, MuArchiveExecution],
    results: tuple[MuArchiveCandidateResult, ...],
    staged: StagedQualification,
    generator_identity: dict[str, object],
    symbol: str,
    funding_input: dict[str, object],
) -> dict[str, object]:
    timeframes = {
        result.timeframe: build_timeframe_report(
            midpoints[result.timeframe], audit, result
        )
        for result in results
    }
    identity = track_identity(staged.track)
    validation = validation_assessment_with_path_evidence(
        staged.validation,
        staged.development_path["status"] == "resolved",
        staged.validation_path["status"] == "resolved",
    )
    final = final_track_evaluation(
        staged.validation,
        staged.holdout,
        holdout_path_resolved=(
            staged.holdout_path is not None
            and staged.holdout_path["status"] == "resolved"
        ),
    )
    advanced_tracks = [identity] if validation["advanced"] else []
    return {
        "schema_version": (
            "mu_hip3_full_archive_bidirectional_v1"
            if symbol == MU_SYMBOL
            else "hip3_full_archive_bidirectional_v1"
        ),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "symbol": symbol,
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "place_attempted": False,
        "runtime_strategy_changed": False,
        "scheduled_oracle_session_contract": oracle_session_contract(symbol),
        "qualification_window": _qualification_window(midpoints, symbol),
        "funding_input": funding_input,
        "funding": funding,
        "execution_friction": {
            timeframe: asdict(execution) for timeframe, execution in executions.items()
        },
        "selection_design": (
            "one track selected across 5m/15m and both families on development "
            "only; validation advances/rejects once; final holdout evaluates only "
            "the frozen validation-advanced identity"
        ),
        "timeframe_selection_policy": "development_fold_robustness_before_frequency",
        "timeframes": timeframes,
        "development_selected_track": identity,
        "validation_assessment": validation,
        "validation_advanced_tracks": advanced_tracks,
        "validation_advance_verdict": (
            "ADVANCED" if validation["advanced"] else "REJECTED"
        ),
        "final_evaluation": final,
        "selected_track_path_evidence": {
            "development": staged.development_path,
            "validation": staged.validation_path,
            "holdout": staged.holdout_path,
        },
        "promotion_verdict": "NO_LIVE_PROMOTION_REPORT_ONLY",
        "research_recommendation": (
            "ELIGIBLE_FOR_SEPARATE_LIVE_IMPLEMENTATION_REVIEW"
            if final["outcome"] == "PASS"
            else "NO_PROMOTION"
        ),
        "proposed_runtime_contract": proposed_runtime_contract(staged.track),
        "live_promotion_applied": False,
        "source_evidence": _source_evidence(args),
        "generator_identity": generator_identity,
        "limitations": _limitations(),
    }


def _execution(
    args: argparse.Namespace,
    qualification: dict[str, object],
    liquidity: dict[str, object],
    symbol: str = MU_SYMBOL,
) -> MuArchiveExecution:
    max_leverage = _qualification_leverage(qualification, symbol)
    profile = _mapping(liquidity.get("profile"), "liquidity profile")
    if profile.get("symbol") != symbol:
        raise ValueError(f"liquidity evidence is not exact {symbol}")
    fees = _mapping(profile.get("fees"), "liquidity fees")
    notional = _notional(profile, 75.0)
    visible = _mapping(notional.get("round_trip_visible_cost_bps"), "visible cost")
    p90 = _number(visible.get("p90"), "visible p90")
    p99 = _number(visible.get("p99"), "visible p99")
    if p90 < 0.0 or p99 < 0.0 or p99 < p90:
        raise ValueError(
            "MU visible cost quantiles must be non-negative with p99 >= p90"
        )
    return MuArchiveExecution(
        _number(fees.get("effective_taker_rate"), "effective_taker_rate"),
        75.0,
        max_leverage,
        float(args.nominal_latency_bps_per_side),
        float(args.stress_latency_bps_per_side),
        (p99 - p90) / 2.0,
        symbol=symbol,
    )


def _load_venue_path_midpoints(
    args: argparse.Namespace,
    midpoints: dict[str, Hip3MidpointBars],
    audit: dict[str, object],
) -> dict[str, Hip3MidpointBars]:
    """Load verified 0x mark/trade paths and attach them to signal bars."""
    symbol = str(args.symbol)
    start = min(item.archive_start_utc for item in midpoints.values())
    end = max(item.archive_end_utc for item in midpoints.values())
    price_archive = load_verified_price_archive(
        OxaPriceArchiveConfig(
            symbol,
            start.to_pydatetime(),
            end.to_pydatetime(),
            args.data_root,
            chunk=timedelta(hours=1),
            maximum_gap=None,
            market_family="hip3",
        )
    )
    price_evidence = _require_complete_price_scope(price_archive)
    trades = load_hip3_public_trades(
        args.database,
        symbol=symbol,
        start_utc=start,
        end_utc=end,
    )
    reconciliation = _reconcile_loaded_trade_archive(
        trades,
        audit,
        start,
        end,
        database_path=args.database,
        symbol=symbol,
    )
    output: dict[str, Hip3MidpointBars] = {}
    for timeframe, minutes, _hold in _TIMEFRAME_SPECS:
        venue = build_hip3_venue_path_bars(
            midpoints[timeframe],
            trades,
            price_archive.frame,
            bar_minutes=minutes,
            trade_bundle_complete=True,
        )
        bars = venue.bars.assign(**reconciliation, **price_evidence)
        output[timeframe] = replace(midpoints[timeframe], bars=bars)
    return output


def _require_complete_price_scope(price_archive: object) -> dict[str, int]:
    """Reject a scope containing mark-null rows without oracle substitution."""
    mark_rows = int(getattr(price_archive, "mark_row_count"))
    missing = int(getattr(price_archive, "missing_mark_row_count"))
    empty = int(getattr(price_archive, "empty_partition_count"))
    maximum_gap = int(getattr(price_archive, "maximum_observed_gap_ms"))
    if mark_rows <= 0:
        raise ValueError("MU price scope contains no exact mark rows")
    if missing:
        raise ValueError(f"MU price scope contains {missing} missing mark rows")
    if empty:
        raise ValueError(f"MU price scope contains {empty} empty price partitions")
    if maximum_gap < 0:
        raise ValueError("MU price scope maximum mark gap is invalid")
    return {
        "price_archive_mark_rows": mark_rows,
        "price_archive_missing_mark_rows": missing,
        "price_archive_empty_partitions": empty,
        "price_archive_maximum_observed_gap_ms": maximum_gap,
    }


def _has_paired_trade_audit(audit: dict[str, object]) -> bool:
    """Return whether the archive audit explicitly includes trade bundles."""
    fields = {"public_trades", "empty_trade_windows", "empty_trade_ranges_utc"}
    present = fields.intersection(audit)
    if present and present != fields:
        raise ValueError("MU paired archive audit has incomplete trade fields")
    return present == fields


def _require_paired_trade_audit(audit: dict[str, object]) -> None:
    """Fail closed when qualification lacks checksum-complete trade evidence."""
    if not _has_paired_trade_audit(audit):
        raise ValueError(
            "MU archive qualification requires a paired trade and book audit"
        )
    _trade_bundle_complete(audit)


def _trade_bundle_complete(audit: dict[str, object]) -> bool:
    """Require checksum-complete paired bundles before marking trade evidence."""
    if not _has_paired_trade_audit(audit):
        return False
    expected = int(_number(audit.get("expected_bundles"), "expected_bundles"))
    present = int(_number(audit.get("present_bundles"), "present_bundles"))
    if audit.get("complete") is not True or expected != present or expected % 2:
        raise ValueError("MU paired archive audit is not checksum-complete")
    _number(audit.get("public_trades"), "public_trades")
    return True


def _reconcile_loaded_trade_archive(
    trades: pd.DataFrame,
    audit: dict[str, object],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    database_path: Path,
    symbol: str = MU_SYMBOL,
) -> dict[str, int]:
    """Reconcile loaded normalized prints to the immutable paired audit."""
    if not _trade_bundle_complete(audit):
        raise ValueError("MU paired trade evidence is incomplete")
    expected = int(_number(audit.get("public_trades"), "public_trades"))
    if expected > 0 and trades.empty:
        raise ValueError("loaded MU trade rows disagree with paired archive audit")
    database_evidence = _database_trade_reconciliation(
        database_path, start, end, symbol
    )
    if database_evidence["source_public_trade_rows"] != expected:
        raise ValueError("source MU trade rows disagree with paired archive audit")
    if database_evidence["canonical_public_trade_rows"] != len(trades):
        raise ValueError("loaded MU trade rows disagree with canonical database rows")
    if database_evidence["conflicting_duplicate_trade_ids"] != 0:
        raise ValueError("MU archive contains conflicting duplicate trade identities")
    timestamps = pd.to_datetime(trades["ts_exchange_ms"], unit="ms", utc=True)
    if timestamps.lt(start).any() or timestamps.ge(end).any():
        raise ValueError("loaded MU trade rows exceed paired archive bounds")
    ranges = _sequence(audit.get("empty_trade_ranges_utc", []), "empty trade ranges")
    duration_seconds = 0.0
    prior_end: pd.Timestamp | None = None
    for raw in ranges:
        pair = _sequence(raw, "empty trade range")
        if len(pair) != 2:
            raise ValueError("empty trade range requires start and end")
        left, right = pd.Timestamp(pair[0]), pd.Timestamp(pair[1])
        if left.tz is None or right.tz is None or not left < right:
            raise ValueError("empty trade range requires ordered UTC timestamps")
        left, right = left.tz_convert("UTC"), right.tz_convert("UTC")
        if left < start or right > end:
            raise ValueError("empty trade range exceeds audited archive bounds")
        if prior_end is not None and left < prior_end:
            raise ValueError("empty trade ranges must be ordered and non-overlapping")
        if (timestamps.ge(left) & timestamps.lt(right)).any():
            raise ValueError("empty trade range contains loaded public trades")
        duration_seconds += (right - left).total_seconds()
        prior_end = right
    empty_windows = int(
        _number(audit.get("empty_trade_windows", 0), "empty_trade_windows")
    )
    if duration_seconds != empty_windows * 3_600:
        raise ValueError("empty trade range duration disagrees with window count")
    return database_evidence


def _database_trade_reconciliation(
    database_path: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
    symbol: str = MU_SYMBOL,
) -> dict[str, int]:
    """Measure exact raw-to-canonical trade identity reconciliation."""
    import duckdb

    with duckdb.connect(str(database_path), read_only=True) as connection:
        row = connection.execute(
            """
            WITH scoped AS (
                SELECT * FROM public_trades
                WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
            ), grouped AS (
                SELECT trade_id, count(*) AS copies,
                       count(DISTINCT ts_exchange_ms) AS timestamps,
                       count(DISTINCT aggressor_side) AS sides,
                       count(DISTINCT price) AS prices,
                       count(DISTINCT size) AS sizes,
                       count(DISTINCT symbol) AS symbols
                FROM scoped GROUP BY trade_id
            )
            SELECT (SELECT count(*) FROM scoped), count(*),
                   coalesce(sum(copies - 1), 0),
                   count(*) FILTER (
                       WHERE timestamps != 1 OR sides != 1 OR prices != 1
                          OR sizes != 1 OR symbols != 1
                   )
            FROM grouped
            """,
            [symbol, start, end],
        ).fetchone()
    if row is None or len(row) != 4:
        raise RuntimeError("MU database trade reconciliation returned no result")
    return {
        "source_public_trade_rows": int(row[0]),
        "canonical_public_trade_rows": int(row[1]),
        "duplicate_public_trade_rows": int(row[2]),
        "conflicting_duplicate_trade_ids": int(row[3]),
    }


def _require_venue_path_midpoints(
    midpoints: dict[str, Hip3MidpointBars],
) -> None:
    """Reject partially attached venue-path evidence before evaluation."""
    required = {
        "risk_high",
        "risk_low",
        "risk_entry_high",
        "risk_entry_low",
        "risk_path_source",
        "mark_path_complete",
        "entry_mark_path_complete",
        "mark_snapshot_count",
        "entry_mark_snapshot_count",
        "entry_maximum_mark_interval_ms",
        "maximum_mark_interval_ms",
        "trade_bundle_complete",
        "signal_open",
        "signal_high",
        "signal_low",
        "signal_close",
        "signal_gap_before_bars",
        "signal_ohlc_source",
        "signal_ohlc_synthetic_no_trade",
        "signal_volume",
        "public_trade_count",
        "source_public_trade_rows",
        "canonical_public_trade_rows",
        "duplicate_public_trade_rows",
        "conflicting_duplicate_trade_ids",
        "price_archive_mark_rows",
        "price_archive_missing_mark_rows",
        "price_archive_empty_partitions",
        "price_archive_maximum_observed_gap_ms",
    }
    for timeframe, midpoint in midpoints.items():
        missing = sorted(required.difference(midpoint.bars.columns))
        if missing:
            raise ValueError(
                f"MU {timeframe} venue risk path missing columns: {missing}"
            )


def _require_qualification_mark_start(
    midpoints: dict[str, Hip3MidpointBars],
) -> None:
    """Reject a scope that begins before exact mark-risk observations."""
    common_start = max(item.archive_start_utc for item in midpoints.values())
    for timeframe, midpoint in midpoints.items():
        bars = midpoint.bars.loc[midpoint.bars.index >= common_start]
        observed_marks = bars["mark_snapshot_count"].astype(int).gt(0)
        if bars.empty or not bool(observed_marks.iloc[0]):
            observed = bars.index[observed_marks]
            first = observed[0].isoformat() if len(observed) else "unavailable"
            raise ValueError(
                "MU qualification window starts before first observed mark-risk "
                f"bar for {timeframe}; first observed={first}"
            )


def _qualification_window(
    midpoints: dict[str, Hip3MidpointBars],
    symbol: str = MU_SYMBOL,
) -> dict[str, object]:
    """Return immutable bounds and exact incomplete mark-risk ranges."""
    start = max(item.archive_start_utc for item in midpoints.values())
    end = min(item.archive_end_utc for item in midpoints.values())
    incomplete = {
        timeframe: _incomplete_mark_ranges(midpoint.bars, timeframe)
        for timeframe, midpoint in midpoints.items()
    }
    incomplete_counts = {
        timeframe: int((~midpoint.bars["mark_path_complete"].eq(True)).sum())
        for timeframe, midpoint in midpoints.items()
    }
    return {
        "scope": "exact_mark_risk_qualification",
        "window_id": (
            f"{symbol}|exact-mark-risk-v1|{start.isoformat()}|{end.isoformat()}"
        ),
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "mark_incomplete_bar_count": incomplete_counts,
        "mark_incomplete_ranges_utc": incomplete,
        "audit_bound": True,
    }


def _audit_bound_scope(
    args: argparse.Namespace,
    audit: dict[str, object],
    symbol: str = MU_SYMBOL,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Bind CLI, audit, and database readers to one exact paired window."""
    expected_identity = {
        "symbol": symbol,
        "market_family": "hip3",
        "book_only": False,
        "chunk_seconds": 3_600,
    }
    if any(audit.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("MU paired archive audit identity is invalid")
    audit_start = _utc_argument(
        str(audit.get("requested_start_utc")),
    )
    audit_end = _utc_argument(str(audit.get("requested_end_utc")))
    if audit_start >= audit_end:
        raise ValueError("MU paired archive audit bounds must be ordered")
    requested_start = args.start
    requested_end = args.end
    if (requested_start is None) != (requested_end is None):
        raise ValueError("MU --start and --end must be supplied together")
    if requested_start is not None and (
        requested_start != audit_start or requested_end != audit_end
    ):
        raise ValueError("MU CLI and paired archive audit bounds disagree")
    windows = int((audit_end - audit_start).ceil("h") / pd.Timedelta(hours=1))
    expected_bundles = int(_number(audit.get("expected_bundles"), "expected_bundles"))
    if expected_bundles != windows * 2:
        raise ValueError("MU paired archive audit cadence disagrees with bounds")
    return audit_start, audit_end


def _utc_argument(value: str) -> pd.Timestamp:
    """Parse one timezone-aware UTC CLI timestamp."""
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return timestamp.tz_convert("UTC")


def _hip3_symbol_argument(value: str) -> str:
    """Parse one exact builder-deployed market identity."""
    try:
        validate_market_symbol(value, "hip3")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return value


def _incomplete_mark_ranges(
    bars: pd.DataFrame,
    timeframe: str,
) -> list[list[str]]:
    minutes = 5 if timeframe == "5m" else 15
    interval = pd.Timedelta(minutes=minutes)
    incomplete = bars.index[~bars["mark_path_complete"].eq(True)]
    if incomplete.empty:
        return []
    ranges: list[list[str]] = []
    left = incomplete[0]
    right = left + interval
    for timestamp in incomplete[1:]:
        if timestamp == right:
            right += interval
            continue
        ranges.append([left.isoformat(), right.isoformat()])
        left, right = timestamp, timestamp + interval
    ranges.append([left.isoformat(), right.isoformat()])
    return ranges


def _risk_path_columns(bars: pd.DataFrame) -> dict[str, str]:
    """Tie simulator barrier evaluation to attached venue mark extrema."""
    columns = {
        "risk_high_column": "risk_high",
        "risk_low_column": "risk_low",
        "entry_risk_high_column": "risk_entry_high",
        "entry_risk_low_column": "risk_entry_low",
    }
    present = {key: value in bars for key, value in columns.items()}
    if any(present.values()) and not all(present.values()):
        raise ValueError("MU venue full/entry risk columns must be complete")
    return columns if all(present.values()) else {}


def _reconcile_archive(
    midpoint: Hip3MidpointBars,
    audit: dict[str, object],
    symbol: str = MU_SYMBOL,
) -> None:
    present_bundles = int(_number(audit.get("present_bundles"), "present_bundles"))
    expected_bundles = (
        present_bundles // 2 if _has_paired_trade_audit(audit) else present_bundles
    )
    if _has_paired_trade_audit(audit) and present_bundles % 2:
        raise ValueError("MU paired archive audit bundle count must be even")
    snapshots = int(_number(audit.get("book_snapshots"), "book_snapshots"))
    if midpoint.symbol != symbol:
        raise ValueError(f"midpoint archive is not exact {symbol}")
    if midpoint.archive_bundles != expected_bundles:
        raise ValueError("MU archive bundle count disagrees with audit")
    if midpoint.archive_book_rows != snapshots:
        raise ValueError("MU archive snapshot count disagrees with audit")
    _reconcile_empty_book_ranges(midpoint, audit)


def _reconcile_empty_book_ranges(
    midpoint: Hip3MidpointBars, audit: dict[str, object]
) -> None:
    ranges = _sequence(audit.get("empty_book_ranges_utc", []), "empty book ranges")
    duration_seconds = 0.0
    prior_end: pd.Timestamp | None = None
    for raw in ranges:
        pair = _sequence(raw, "empty book range")
        if len(pair) != 2:
            raise ValueError("empty book range requires start and end")
        start, end = pd.Timestamp(pair[0]), pd.Timestamp(pair[1])
        if start.tz is None or end.tz is None or not start < end:
            raise ValueError("empty book range requires ordered UTC timestamps")
        start, end = start.tz_convert("UTC"), end.tz_convert("UTC")
        if start < midpoint.archive_start_utc or end > midpoint.archive_end_utc:
            raise ValueError("empty book range exceeds audited archive bounds")
        if prior_end is not None and start < prior_end:
            raise ValueError("empty book ranges must be ordered and non-overlapping")
        observed = midpoint.bars.index.to_series().ge(
            start
        ) & midpoint.bars.index.to_series().lt(end)
        if observed.any():
            raise ValueError("empty book range contains midpoint rows")
        duration_seconds += (end - start).total_seconds()
        prior_end = end
    empty_windows = int(
        _number(audit.get("empty_book_windows", 0), "empty_book_windows")
    )
    if duration_seconds != empty_windows * 3_600:
        raise ValueError("empty book range duration disagrees with empty window count")


def _require_complete_audit(audit: dict[str, object]) -> None:
    if audit.get("complete") is not True:
        raise ValueError("MU full archive audit is incomplete")
    expected = _number(audit.get("expected_bundles"), "expected_bundles")
    present = _number(audit.get("present_bundles"), "present_bundles")
    if expected != present:
        raise ValueError("MU full archive audit has missing bundles")
    empty = _number(audit.get("empty_book_windows", 0), "empty_book_windows")
    if empty < 0.0:
        raise ValueError("MU full archive audit has invalid empty window count")


def _qualification_leverage(value: dict[str, object], symbol: str = MU_SYMBOL) -> float:
    markets = [
        _mapping(item, "qualification market")
        for item in _sequence(value.get("markets"), "qualification markets")
    ]
    matches = [row for row in markets if row.get("symbol") == symbol]
    if len(matches) != 1:
        raise ValueError(f"qualification requires exactly one {symbol} market")
    return _number(matches[0].get("max_leverage"), "max_leverage")


def _notional(profile: dict[str, object], expected: float) -> dict[str, object]:
    rows = [
        _mapping(item, "liquidity notional")
        for item in _sequence(profile.get("notionals"), "liquidity notionals")
    ]
    matches = [row for row in rows if row.get("notional_usd") == expected]
    if len(matches) != 1 or matches[0].get("both_complete_rate") != 1.0:
        raise ValueError("MU `$75` visible-depth completion evidence is incomplete")
    return matches[0]


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    return {
        "symbol": str(args.symbol),
        "database_path": str(args.database.resolve()),
        "qualification": _file_reference(args.qualification_report),
        "liquidity": _file_reference(args.liquidity_report),
        "archive_audit": _file_reference(args.archive_audit_report),
    }


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    return source_tree_identity(root, Path(__file__).resolve())


def _require_generator_unchanged(expected: dict[str, object]) -> None:
    root = Path(__file__).resolve().parents[1]
    require_unchanged_generator(expected, root, Path(__file__).resolve())


def _limitations() -> list[str]:
    return [
        "paired qualification uses public-trade OHLC for signals, L2 quotes for "
        "fills, and mark extrema for risk; live exchange-candle row parity remains "
        "a deployment blocker until tested",
        "zero-trade signal bars carry only the prior observed trade close and reset "
        "the signal segment; this policy is not assumed to match live candles",
        "visible quotes exclude queue position and post-snapshot adverse selection",
        "current account fee inputs are not historical fee-state reconstruction",
        "latency is an explicit sensitivity pending exact MU live-fill evidence",
        "unresolved gap-crossing trades fail validation/final evaluation; exact "
        "gap extrema require bounded venue trade/fill recovery",
        "the current HIP-3 live collector is hardcoded to 15m, so a selected 5m "
        "track is not deployable until timeframe-aware collection is tested",
        "current live breakout evaluation does not expose archive long_exit/short_exit; "
        "breakout deployment requires exit parity tests",
        "the proposed provider must explicitly honor recipe exits; current generic "
        "execution contracts default to ignore",
        "historical qualification does not itself grant live execution authority",
    ]


def _file_reference(path: Path, rows: int | None = None) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"MU evidence file does not exist: {path}")
    output = {"path": str(path.resolve()), **file_evidence(path)}
    if rows is not None:
        output["rows"] = rows
    return output


def _load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"MU JSON evidence does not exist: {path}")
    return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _require_new(*paths: Path) -> None:
    require_new_outputs(*paths)


def main() -> int:
    """Run once and print the immutable full-archive report path."""
    args = build_parser().parse_args()
    run_command(args)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
