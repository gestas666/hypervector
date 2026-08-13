"""Bounded deterministic experiment for five-minute liquidity sweeps."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Mapping

import pandas as pd

from hypervector.research.liquidity_sweep_contract import LiquiditySweepConfig
from hypervector.research.liquidity_sweep_features import (
    build_liquidity_sweep_events,
    build_liquidity_sweep_feature_rows,
)
from hypervector.research.liquidity_sweep_labels import (
    label_liquidity_sweep_events,
    serialize_liquidity_sweep_outcomes,
)
from hypervector.research.liquidity_sweep_reporting import (
    summarize_liquidity_sweep_outcomes,
)
from hypervector.research.market_cipher_data import load_verified_hourly_funding
from hypervector.research.orderflow_impulse_data import (
    audit_orderflow_coverage,
    load_orderflow_impulse_inputs,
)


@dataclass(frozen=True)
class LiquiditySweepExperimentResult:
    """Immutable report payload and complete lifecycle sidecar."""

    report: dict[str, object]
    outcomes: pd.DataFrame


@dataclass(frozen=True)
class DevelopmentFold:
    """One non-adjacent chronological development interval."""

    fold_id: int
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp


def run_liquidity_sweep_experiment(
    database_path: Path,
    start_utc: datetime,
    end_utc: datetime,
    funding_paths: Mapping[str, Path],
    config: LiquiditySweepConfig,
) -> LiquiditySweepExperimentResult:
    """Run the fixed BTC/SOL five-minute family without execution authority."""
    _validate_funding_paths(funding_paths, config)
    folds = build_development_folds(start_utc, end_utc)
    outcomes: list[pd.DataFrame] = []
    identities: dict[str, object] = {}
    counts: dict[str, object] = {}
    for symbol in config.symbols:
        result, identity, row_counts = _run_symbol(
            database_path,
            symbol,
            start_utc,
            end_utc,
            funding_paths[symbol],
            folds,
            config,
        )
        outcomes.append(result)
        identities[symbol] = identity
        counts[symbol] = row_counts
    combined = pd.concat(outcomes, ignore_index=True)
    report = _report(
        database_path,
        start_utc,
        end_utc,
        config,
        folds,
        combined,
        identities,
        counts,
    )
    return LiquiditySweepExperimentResult(report, combined)


def build_development_folds(
    start_utc: datetime, end_utc: datetime
) -> tuple[DevelopmentFold, ...]:
    """Create three chronological folds separated by one-day purge windows."""
    start = pd.Timestamp(start_utc)
    end = pd.Timestamp(end_utc)
    if start.tz is None or end.tz is None or start >= end:
        raise ValueError("development fold bounds must be ordered and aware")
    duration = end - start
    if duration < pd.Timedelta(days=9):
        raise ValueError("development interval must span at least nine days")
    boundary_one = start + duration / 3
    boundary_two = start + 2 * duration / 3
    purge = pd.Timedelta(days=1)
    return (
        DevelopmentFold(0, start, boundary_one),
        DevelopmentFold(1, boundary_one + purge, boundary_two),
        DevelopmentFold(2, boundary_two + purge, end),
    )


def assign_development_folds(
    outcomes: pd.DataFrame, folds: tuple[DevelopmentFold, ...]
) -> pd.DataFrame:
    """Assign entry-time folds and reject lifecycles crossing fold boundaries."""
    output = outcomes.copy()
    output["fold_id"] = pd.Series(pd.NA, index=output.index, dtype="Int64")
    output["fold_eligible"] = False
    entries = pd.to_datetime(output["entry_time_utc"], utc=True)
    exits = pd.to_datetime(output["outcome_time_utc"], utc=True)
    for fold in folds:
        selected = entries.ge(fold.start_utc) & entries.lt(fold.end_utc)
        output.loc[selected, "fold_id"] = fold.fold_id
        output.loc[selected, "fold_eligible"] = exits.loc[selected].le(fold.end_utc)
    rejected = output["accepted"] & ~output["fold_eligible"]
    output.loc[rejected, "accepted"] = False
    output.loc[rejected, "displacement_reason"] = "purge_or_fold_boundary"
    return output


def _run_symbol(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    funding_path: Path,
    folds: tuple[DevelopmentFold, ...],
    config: LiquiditySweepConfig,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, object]]:
    inputs = load_orderflow_impulse_inputs(
        database_path,
        symbol,
        start_utc,
        end_utc,
        warmup_minutes=config.warmup_minutes,
        horizon_minutes=config.maximum_hold_minutes + config.bar_minutes,
    )
    features = build_liquidity_sweep_feature_rows(
        inputs.bars, inputs.trades, inputs.books, config
    )
    scored = features.loc[
        features["bar_open_at"].ge(start_utc) & features["bar_open_at"].lt(end_utc)
    ].reset_index(drop=True)
    events, event_audit = build_liquidity_sweep_events(
        scored, symbol=symbol, config=config
    )
    funding = _funding_frame(funding_path, start_utc, end_utc, config)
    labeled = label_liquidity_sweep_events(features, events, funding, config)
    serialized = serialize_liquidity_sweep_outcomes(labeled)
    outcomes = assign_development_folds(serialized, folds)
    identity = _input_identity(inputs.bars, inputs.trades, inputs.books, funding_path)
    counts: dict[str, object] = {
        "minute_price_rows": len(inputs.bars),
        "five_minute_rows": len(features),
        "scored_five_minute_rows": len(scored),
        "event_rows": len(events),
        "event_audit": event_audit,
        "accepted_rows": int(outcomes["accepted"].sum()),
    }
    return outcomes, identity, counts


def _funding_frame(
    path: Path,
    start_utc: datetime,
    end_utc: datetime,
    config: LiquiditySweepConfig,
) -> pd.DataFrame:
    extended_end = pd.Timestamp(end_utc) + pd.Timedelta(
        minutes=config.maximum_hold_minutes + config.bar_minutes
    )
    series = load_verified_hourly_funding([path], pd.Timestamp(start_utc), extended_end)
    return series.rename_axis("timestamp").reset_index()


def _report(
    database_path: Path,
    start_utc: datetime,
    end_utc: datetime,
    config: LiquiditySweepConfig,
    folds: tuple[DevelopmentFold, ...],
    outcomes: pd.DataFrame,
    identities: dict[str, object],
    counts: dict[str, object],
) -> dict[str, object]:
    coverage = audit_orderflow_coverage(database_path, ("BTC", "ETH", "SOL", "HYPE"))
    return {
        "schema_version": "liquidity_sweep_development_v1",
        "start_utc": pd.Timestamp(start_utc).isoformat(),
        "end_utc": pd.Timestamp(end_utc).isoformat(),
        "report_only": config.report_only,
        "execution_authority": config.execution_authority,
        "place_attempted": False,
        "config": asdict(config),
        "database_path": str(database_path),
        "input_identity": identities,
        "row_counts": counts,
        "folds": [_fold_record(fold) for fold in folds],
        "archive_coverage": _records(coverage),
        "deterministic_summary": _records(summarize_liquidity_sweep_outcomes(outcomes)),
        "fold_summary": _fold_summary(outcomes),
        "accepted_rows": int(outcomes["accepted"].sum()),
        "displaced_rows": int((~outcomes["accepted"]).sum()),
        "ml_status": "not_run_deterministic_contract_first",
    }


def _fold_summary(outcomes: pd.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    eligible = outcomes.loc[outcomes["fold_id"].notna()]
    for fold_id, rows in eligible.groupby("fold_id", sort=True):
        summary = summarize_liquidity_sweep_outcomes(rows)
        selected = summary.loc[summary["scope"].eq("arm")].copy()
        selected.insert(0, "fold_id", int(fold_id))
        records.extend(_records(selected))
    return records


def _fold_record(fold: DevelopmentFold) -> dict[str, object]:
    return {
        "fold_id": fold.fold_id,
        "start_utc": fold.start_utc.isoformat(),
        "end_utc": fold.end_utc.isoformat(),
    }


def _input_identity(
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    books: pd.DataFrame,
    funding_path: Path,
) -> dict[str, str]:
    return {
        "bars_sha256": _frame_sha256(bars),
        "trades_sha256": _frame_sha256(trades),
        "books_sha256": _frame_sha256(books),
        "funding_sha256": _file_sha256(funding_path),
    }


def _validate_funding_paths(
    funding_paths: Mapping[str, Path], config: LiquiditySweepConfig
) -> None:
    if set(funding_paths) != set(config.symbols):
        raise ValueError("funding paths must exactly match configured symbols")
    missing = [str(path) for path in funding_paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"funding paths do not exist: {missing}")


def _frame_sha256(frame: pd.DataFrame) -> str:
    digest = sha256()
    digest.update("\x1f".join(map(str, frame.columns)).encode())
    values = pd.util.hash_pandas_object(frame, index=False, categorize=True)
    digest.update(values.to_numpy().tobytes())
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
