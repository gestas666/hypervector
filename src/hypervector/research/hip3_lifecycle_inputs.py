"""Verified shared inputs for report-only HIP-3 lifecycle experiments."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
    build_breakout_pressure_signals,
)
from hypervector.research.hip3_midpoint_bars import (
    Hip3MidpointBars,
    build_hip3_midpoint_bars,
)
from hypervector.research.hip3_swing_signals import (
    build_gap_aware_swing_ha_signals,
)
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
    Hip3TransferWindows,
)
from hypervector.research.hip3_transfer_sources import attach_official_funding
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

Record = Mapping[str, object]
Recipe = SwingHaSignalConfig | Hip3BreakoutPressureConfig


@dataclass(frozen=True)
class Hip3LifecycleCaseInputs:
    """Verified paths and source report for one production recipe."""

    strategy_id: str
    report_path: Path
    report: Record
    database_path: Path
    sidecar_path: Path
    qualification_path: Path


def load_hip3_lifecycle_case_inputs(
    strategy_id: str,
    report_path: Path,
) -> Hip3LifecycleCaseInputs:
    """Load a source report and validate every referenced file identity."""
    if not report_path.is_file():
        raise FileNotFoundError(f"HIP-3 source report does not exist: {report_path}")
    report = _load_json(report_path)
    database, sidecar, qualification = _source_paths(report)
    if not database.is_file():
        raise FileNotFoundError(f"HIP-3 database does not exist: {database}")
    return Hip3LifecycleCaseInputs(
        strategy_id,
        report_path,
        report,
        database,
        sidecar,
        qualification,
    )


def load_hip3_lifecycle_assets(
    inputs: Hip3LifecycleCaseInputs,
) -> tuple[tuple[Hip3TransferAsset, Hip3ExecutionFriction], ...]:
    """Build funded pre-holdout assets with verified friction evidence."""
    symbols = hip3_lifecycle_symbols(inputs.report)
    windows = hip3_lifecycle_windows(inputs.report)
    qualification = _load_json(inputs.qualification_path)
    leverages = _leverages(qualification, symbols)
    sidecar = pd.read_parquet(inputs.sidecar_path)
    return tuple(
        _asset_and_friction(
            inputs,
            symbol,
            leverages[symbol],
            sidecar,
            windows,
        )
        for symbol in symbols
    )


def build_hip3_lifecycle_signals(
    bars: pd.DataFrame,
    recipe: Recipe,
) -> pd.DataFrame:
    """Build the exact provider recipe signals over verified bars."""
    if isinstance(recipe, SwingHaSignalConfig):
        return build_gap_aware_swing_ha_signals(bars, recipe)
    return build_breakout_pressure_signals(bars, recipe)


def hip3_lifecycle_windows(report: Record) -> Hip3TransferWindows:
    """Parse the source report's development, validation, and sealed windows."""
    value = _mapping(report.get("windows"), "source windows")
    folds = tuple(
        (
            _timestamp(row.get("start_utc"), "fold start"),
            _timestamp(row.get("end_utc"), "fold end"),
        )
        for item in _sequence(value.get("development_folds"), "development_folds")
        for row in [_mapping(item, "development fold")]
    )
    return Hip3TransferWindows(
        _timestamp(value.get("development_start_utc"), "development start"),
        _timestamp(value.get("development_end_utc"), "development end"),
        _timestamp(value.get("validation_end_utc"), "validation end"),
        _timestamp(value.get("holdout_end_utc"), "holdout end"),
        folds,
    )


def hip3_lifecycle_symbols(report: Record) -> tuple[str, ...]:
    """Return the exact non-empty symbol scope declared by a source report."""
    values = report.get("symbols")
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ValueError("source symbols must be non-empty strings")
    return tuple(values)


def hip3_file_reference(path: Path) -> dict[str, object]:
    """Return an absolute content-addressed evidence reference."""
    return {"path": str(path.resolve()), **file_evidence(path)}


def _source_paths(report: Record) -> tuple[Path, Path, Path]:
    source = report.get("source_evidence")
    if isinstance(source, list):
        database = _path(report.get("database_path"), "database_path")
        sidecar = _verified_reference(report.get("source_sidecar"), "source_sidecar")
        qualification = _verified_reference(
            report.get("qualification_report"), "qualification_report"
        )
        return database, sidecar, qualification
    nested = _mapping(source, "source_evidence")
    database = _path(nested.get("database_path"), "database_path")
    sidecar = _verified_reference(nested.get("source_sidecar"), "source_sidecar")
    qualification = _verified_reference(
        nested.get("qualification_report"), "qualification_report"
    )
    return database, sidecar, qualification


def _asset_and_friction(
    inputs: Hip3LifecycleCaseInputs,
    symbol: str,
    venue_max_leverage: float,
    sidecar: pd.DataFrame,
    windows: Hip3TransferWindows,
) -> tuple[Hip3TransferAsset, Hip3ExecutionFriction]:
    midpoint = build_hip3_midpoint_bars(inputs.database_path, symbol=symbol)
    evidence = _symbol_source_evidence(inputs.report, symbol)
    _verify_archive(midpoint, evidence)
    before_holdout = midpoint.bars.index.to_series().lt(windows.validation_end_utc)
    research = midpoint.bars.loc[before_holdout].copy()
    bars, _ = attach_official_funding(research, _funding_rows(sidecar, symbol))
    asset = Hip3TransferAsset(symbol, venue_max_leverage, bars)
    friction = Hip3ExecutionFriction(
        **dict(_mapping(evidence.get("friction"), f"{symbol} friction"))
    )
    return asset, friction


def _symbol_source_evidence(report: Record, symbol: str) -> Record:
    source = report.get("source_evidence")
    if isinstance(source, list):
        rows = [_mapping(row, "source evidence row") for row in source]
        matches = [row for row in rows if row.get("symbol") == symbol]
    else:
        assets = _mapping(_mapping(source, "source_evidence").get("assets"), "assets")
        attachment = _mapping(assets.get(symbol), f"{symbol} attachment")
        inherited = _mapping(
            attachment.get("inherited_verified_evidence"),
            f"{symbol} inherited evidence",
        )
        matches = [inherited]
    if len(matches) != 1:
        raise ValueError(f"source report lacks exact evidence for {symbol}")
    return matches[0]


def _verify_archive(midpoint: Hip3MidpointBars, evidence: Record) -> None:
    archive = _mapping(evidence.get("archive"), "archive evidence")
    expected = (
        _integer(archive.get("bundles"), "archive bundles"),
        _integer(archive.get("book_rows"), "archive book_rows"),
        _integer(archive.get("observed_15m_bars"), "archive observed bars"),
    )
    observed = (
        midpoint.archive_bundles,
        midpoint.archive_book_rows,
        len(midpoint.bars),
    )
    if observed != expected:
        raise ValueError(f"HIP-3 archive identity changed: {observed} != {expected}")


def _funding_rows(sidecar: pd.DataFrame, symbol: str) -> pd.DataFrame:
    required = {"symbol", "record_type", "timestamp", "funding_rate", "source"}
    missing = sorted(required.difference(sidecar.columns))
    if missing:
        raise ValueError(f"source sidecar missing columns: {missing}")
    selected = sidecar["symbol"].eq(symbol) & sidecar["record_type"].eq(
        "official_funding"
    )
    output = sidecar.loc[selected, ["timestamp", "funding_rate", "source"]].copy()
    if output.empty:
        raise ValueError(f"source sidecar has no official funding for {symbol}")
    return output


def _leverages(report: Record, symbols: tuple[str, ...]) -> dict[str, float]:
    rows = _sequence(report.get("markets"), "qualification markets")
    values = {
        str(row["symbol"]): float(row["max_leverage"])
        for item in rows
        for row in [_mapping(item, "qualification market")]
        if row.get("symbol") in symbols
    }
    if set(values) != set(symbols):
        raise ValueError("qualification leverage scope differs from source symbols")
    return values


def _verified_reference(value: object, label: str) -> Path:
    row = _mapping(value, label)
    path = _path(row.get("path"), f"{label} path")
    observed = file_evidence(path)
    for field in ("bytes", "sha256"):
        if row.get(field) != observed[field]:
            raise ValueError(f"{label} {field} no longer matches")
    return path


def _load_json(path: Path) -> Record:
    return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty path")
    return Path(value)


def _timestamp(value: object, label: str) -> pd.Timestamp:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO timestamp")
    result = pd.Timestamp(value)
    if result.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return result.tz_convert("UTC")


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value
