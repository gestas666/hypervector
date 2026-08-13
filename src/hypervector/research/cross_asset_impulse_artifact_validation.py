"""Independent integrity checks for frozen cross-asset impulse evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cross_asset_impulse_artifact_metrics import (
    validate_impulse_collision_diagnostics,
    validate_impulse_fold_aggregates,
)
from hypervector.research.cross_asset_impulse_models import (
    CrossAssetImpulseConfig,
    CrossAssetImpulseLabel,
    declared_impulse_folds,
    declared_impulse_pairs,
    declared_impulse_variants,
)

_SCHEMA = "cross_asset_impulse_development_v1"
_HORIZONS = (5, 15, 30)
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_PRIOR_SCHEMA = "cross_asset_residual_exit_surface_v2"
_MAX_GENERATOR_MODULES = 64
_TOLERANCE = 1e-8
_HISTORICAL_VALIDATOR_PATH = (
    "src/hypervector/research/cross_asset_impulse_artifact_validation.py"
)

Cell = dict[str, object]
CellKey = tuple[str, str, str, int]


@dataclass(frozen=True)
class ImpulseArtifactValidation:
    """Verified identities and counts for one immutable impulse artifact."""

    artifact_path: str
    artifact_sha256: str
    sidecar_path: str
    sidecar_sha256: str
    primary_cells_verified: int
    control_cells_verified: int
    event_rows_verified: int
    source_files_verified: int
    generator_modules_verified: int
    execution_authority: str
    valid: bool = True


def validate_cross_asset_impulse_artifact(
    artifact_path: Path,
    *,
    max_cells: int = 128,
    max_event_rows: int = 1_000_000,
) -> ImpulseArtifactValidation:
    """Validate an impulse report without replaying data or granting authority."""
    artifact = _read_json(artifact_path, "impulse artifact")
    _validate_frozen_contract(artifact)
    primary, controls = _validate_cells(artifact, max_cells)
    authority = _validate_authority(artifact, primary, controls)
    _validate_selection(artifact, primary, controls)
    _validate_search_accounting(artifact)
    sidecar_path, sidecar_evidence, rows = _read_sidecar(artifact, max_event_rows)
    _validate_event_rows(rows, artifact)
    validate_impulse_fold_aggregates([*primary, *controls], rows, artifact)
    validate_impulse_collision_diagnostics(artifact, rows)
    source_count = _validate_sources(artifact)
    generator_count = _validate_generators(artifact)
    _validate_prior_identity(artifact)
    artifact_evidence = file_evidence(artifact_path)
    return ImpulseArtifactValidation(
        artifact_path=str(artifact_path.resolve()),
        artifact_sha256=_text(artifact_evidence.get("sha256"), "artifact hash"),
        sidecar_path=str(sidecar_path.resolve()),
        sidecar_sha256=_text(sidecar_evidence.get("sha256"), "sidecar hash"),
        primary_cells_verified=len(primary),
        control_cells_verified=len(controls),
        event_rows_verified=len(rows),
        source_files_verified=source_count,
        generator_modules_verified=generator_count,
        execution_authority=authority,
    )


def _validate_frozen_contract(artifact: Mapping[str, object]) -> None:
    config = CrossAssetImpulseConfig()
    expected_config = asdict(config)
    for field in ("warmup_start", "development_start", "development_end"):
        expected_config[field] = getattr(config, field).isoformat()
    expected_config["horizons_minutes"] = list(config.horizons_minutes)
    if artifact.get("config") != expected_config:
        raise ValueError("impulse frozen contract config differs")
    expected_folds = [
        {
            "fold": name,
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
        }
        for name, start, end in declared_impulse_folds(config)
    ]
    if artifact.get("folds") != expected_folds:
        raise ValueError("impulse frozen contract folds differ")
    expected_identity = {
        "warmup_start_utc": config.warmup_start.isoformat(),
        "development_start_utc": config.development_start.isoformat(),
        "development_end_utc": config.development_end.isoformat(),
        "report_only": True,
        "execution_authority": "none",
    }
    if artifact.get("contract_identity") != expected_identity:
        raise ValueError("impulse frozen contract identity differs")


def _read_json(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is invalid JSON: {path}") from error
    return dict(_mapping(payload, label))


def _validate_cells(
    artifact: Mapping[str, object], max_cells: int
) -> tuple[list[Cell], list[Cell]]:
    primary = _cell_list(artifact.get("primary_cells"), "primary")
    controls = _cell_list(artifact.get("control_cells"), "control")
    if max_cells < 0 or len(primary) + len(controls) > max_cells:
        raise ValueError("impulse artifact cell bound exceeded")
    expected_primary = {
        ("primary", *pair, horizon)
        for pair in declared_impulse_pairs()
        for horizon in _HORIZONS
    }
    expected_controls = {
        (variant, *pair, horizon)
        for variant in declared_impulse_variants()[1:]
        for pair in declared_impulse_pairs()
        for horizon in _HORIZONS
    }
    _require_cell_set(primary, expected_primary, "primary")
    _require_cell_set(controls, expected_controls, "control")
    if artifact.get("searched_set_count") != len(primary):
        raise ValueError("impulse searched-set count differs from primary cells")
    return primary, controls


def _cell_list(value: object, role: str) -> list[Cell]:
    if not isinstance(value, list):
        raise ValueError(f"impulse {role} cells must be a list")
    return [dict(_mapping(cell, f"impulse {role} cell")) for cell in value]


def _require_cell_set(cells: list[Cell], expected: set[CellKey], role: str) -> None:
    keys = [_cell_key(cell) for cell in cells]
    if len(keys) != len(set(keys)):
        raise ValueError(f"impulse {role} cells contain duplicate cell identity")
    if set(keys) != expected:
        raise ValueError(f"impulse {role} cell identities differ from contract")
    selectable = role == "primary"
    for cell in cells:
        if cell.get("selectable") is not selectable:
            raise ValueError(f"impulse {role} cell selectable role differs")


def _validate_authority(
    artifact: Mapping[str, object], primary: list[Cell], controls: list[Cell]
) -> str:
    if artifact.get("schema_version") != _SCHEMA:
        raise ValueError("unsupported impulse artifact schema")
    if artifact.get("report_only") is not True:
        raise ValueError("impulse artifact must remain report-only")
    if artifact.get("execution_authority") != "none":
        raise ValueError("impulse execution authority must be none")
    config = _mapping(artifact.get("config"), "impulse config")
    contract = _mapping(artifact.get("contract_identity"), "impulse contract")
    for value in (config, contract):
        if value.get("report_only") is not True:
            raise ValueError("impulse report-only identity does not inherit true")
        if value.get("execution_authority") != "none":
            raise ValueError("impulse execution authority does not inherit none")
    if any(cell.get("execution_authority") != "none" for cell in [*primary, *controls]):
        raise ValueError("impulse cell execution authority does not inherit none")
    return "none"


def _validate_selection(
    artifact: Mapping[str, object], primary: list[Cell], controls: list[Cell]
) -> None:
    if any(cell.get("eligible_for_replay") is True for cell in controls):
        raise ValueError("impulse control cell cannot be eligible")
    if any(cell.get("selected_for_replay") is True for cell in controls):
        raise ValueError("impulse control cell cannot be selected")
    eligible = [cell for cell in primary if cell.get("eligible_for_replay") is True]
    selected = [cell for cell in primary if cell.get("selected_for_replay") is True]
    if len(selected) != min(1, len(eligible)):
        raise ValueError("impulse selected candidate count differs from eligibility")
    if selected and selected[0] not in eligible:
        raise ValueError("impulse selected candidate is not eligible")
    candidate = artifact.get("selected_candidate")
    if not selected and candidate is not None:
        raise ValueError("impulse selected candidate exists without selected cell")
    if selected and _candidate_key(candidate) != _candidate_key(selected[0]):
        raise ValueError("impulse selected candidate differs from selected cell")


def _validate_search_accounting(artifact: Mapping[str, object]) -> None:
    accounting = _mapping(artifact.get("search_accounting"), "search accounting")
    expected = {
        "within_family_selectable_cells": 15,
        "nonselectable_control_cells": 45,
        "prior_residual_selectable_cells": 90,
        "known_cumulative_selectable_cells": 105,
        "shared_development_window_disclosed": True,
        "project_trial_ledger_complete": False,
        "deflated_sharpe_ratio_computed": False,
    }
    for key, value in expected.items():
        if accounting.get(key) != value:
            raise ValueError(f"impulse search accounting differs for {key}")
    prior = _mapping(artifact.get("prior_cross_asset_search"), "prior search")
    if accounting.get("prior_residual_artifact") != prior:
        raise ValueError("impulse search accounting prior identity differs")


def _read_sidecar(
    artifact: Mapping[str, object], max_rows: int
) -> tuple[Path, dict[str, object], pd.DataFrame]:
    if max_rows < 0:
        raise ValueError("impulse event row bound exceeded")
    storage = _mapping(artifact.get("event_storage"), "impulse event storage")
    path = Path(_text(storage.get("path"), "impulse event sidecar path"))
    if not path.is_file():
        raise FileNotFoundError(f"impulse event sidecar is missing: {path}")
    evidence = file_evidence(path)
    if not _same_evidence(storage, evidence):
        raise ValueError("impulse event sidecar evidence differs")
    parquet = pq.ParquetFile(path)
    rows = int(parquet.metadata.num_rows)
    if rows != _integer(storage.get("rows"), "impulse event rows"):
        raise ValueError("impulse event sidecar row count differs")
    if rows > max_rows:
        raise ValueError("impulse event row bound exceeded")
    required = {field.name for field in fields(CrossAssetImpulseLabel)}
    missing = sorted(required.difference(parquet.schema_arrow.names))
    if missing:
        raise ValueError(f"impulse event sidecar missing columns: {missing}")
    return path, evidence, pd.read_parquet(path, columns=sorted(required))


def _validate_event_rows(rows: pd.DataFrame, artifact: Mapping[str, object]) -> None:
    if not rows["report_only"].eq(True).all():
        raise ValueError("impulse event rows must remain report-only")
    if not rows["execution_authority"].eq("none").all():
        raise ValueError("impulse event execution authority must be none")
    allowed_pairs = set(declared_impulse_pairs())
    pairs = set(zip(rows["leader_symbol"], rows["follower_symbol"], strict=True))
    if not pairs.issubset(allowed_pairs):
        raise ValueError("impulse event row contains undeclared pair")
    _validate_row_domains(rows)
    _validate_row_times(rows, artifact)
    identity = [
        "leader_symbol",
        "follower_symbol",
        "signal_variant",
        "anchor",
        "horizon_minutes",
        "decision_time_utc",
    ]
    if rows.duplicated(identity).any():
        raise ValueError("impulse event rows contain duplicate identity")


def _validate_row_domains(rows: pd.DataFrame) -> None:
    domains: dict[str, set[object]] = {
        "signal_variant": set(declared_impulse_variants()),
        "anchor": {"base", "delayed"},
        "direction": {"long", "short"},
        "horizon_minutes": set(_HORIZONS),
        "status": {
            "resolved",
            "technical_gap",
            "fold_boundary_purged",
            "right_censored",
        },
    }
    for column, allowed in domains.items():
        if not set(rows[column]).issubset(allowed):
            raise ValueError(f"impulse event row contains invalid {column}")
    resolved = rows["status"].eq("resolved")
    values = pd.to_numeric(rows.loc[resolved, "directional_gross_return_bps"])
    if not np.isfinite(values.to_numpy(float)).all():
        raise ValueError("resolved impulse rows require finite gross returns")


def _validate_row_times(rows: pd.DataFrame, artifact: Mapping[str, object]) -> None:
    if rows.empty:
        return
    decision = pd.to_datetime(rows["decision_time_utc"], utc=True, errors="raise")
    entry = pd.to_datetime(rows["entry_time_utc"], utc=True, errors="raise")
    exit_time = pd.to_datetime(rows["exit_time_utc"], utc=True, errors="raise")
    start = pd.Timestamp(_text(artifact.get("start_utc"), "development start"))
    end = pd.Timestamp(_text(artifact.get("end_utc"), "development end"))
    if not ((decision >= start) & (decision < end)).all():
        raise ValueError("impulse event decision lies outside development")
    if not ((entry >= decision) & (exit_time > entry)).all():
        raise ValueError("impulse event timestamps violate causal order")


def _validate_sources(artifact: Mapping[str, object]) -> int:
    identity = _mapping(artifact.get("source_identity"), "source identity")
    if set(identity) != set(_SYMBOLS):
        raise ValueError("impulse source identity must cover all declared symbols")
    verified = 0
    for symbol, raw in identity.items():
        source = _mapping(raw, f"{symbol} source identity")
        path = Path(_text(source.get("bars_path"), f"{symbol} bars path"))
        declared = _mapping(source.get("bars"), f"{symbol} bars evidence")
        if not path.is_file() or not _same_evidence(declared, file_evidence(path)):
            raise ValueError(f"source file evidence differs for {symbol}")
        verified += 1
        warmup = source.get("warmup_source_files", [])
        if not isinstance(warmup, list):
            raise ValueError(f"{symbol} warmup source files must be a list")
        for value in warmup:
            _validate_source_file(value, symbol)
            verified += 1
    return verified


def _validate_source_file(value: object, symbol: str) -> None:
    item = _mapping(value, f"{symbol} warmup source file")
    path = Path(_text(item.get("path"), f"{symbol} warmup source path"))
    if not path.is_file() or not _same_evidence(item, file_evidence(path)):
        raise ValueError(f"source file evidence differs for {symbol}")


def _validate_generators(artifact: Mapping[str, object]) -> int:
    identity = _mapping(artifact.get("generator_identity"), "generator identity")
    modules = _mapping(identity.get("generator_modules"), "generator modules")
    if not modules or len(modules) > _MAX_GENERATOR_MODULES:
        raise ValueError("impulse generator module count is invalid")
    for raw_path, raw_evidence in modules.items():
        path = Path(str(raw_path))
        declared = _mapping(raw_evidence, "generator module evidence")
        if str(raw_path) == _HISTORICAL_VALIDATOR_PATH:
            _validate_historical_snapshot(declared)
            continue
        if not path.is_file() or not _same_evidence(declared, file_evidence(path)):
            raise ValueError(f"generator module evidence differs: {path}")
    return len(modules)


def _validate_historical_snapshot(evidence: Mapping[str, object]) -> None:
    byte_count = evidence.get("bytes")
    digest = evidence.get("sha256")
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count <= 0
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("historical validator snapshot evidence is malformed")


def _validate_prior_identity(artifact: Mapping[str, object]) -> None:
    prior = _mapping(artifact.get("prior_cross_asset_search"), "prior search")
    if prior.get("selectable_cells") != 90 or prior.get("trial_count") != 90:
        raise ValueError("prior residual search must retain 90 selectable cells")
    if prior.get("schema_version") != _PRIOR_SCHEMA:
        raise ValueError("prior residual search schema differs")
    path = Path(_text(prior.get("artifact"), "prior residual artifact path"))
    if not path.is_file() or not _same_evidence(prior, file_evidence(path)):
        raise ValueError("prior residual evidence differs")
    payload = _read_json(path, "prior residual artifact")
    expected = {
        "schema_version": _PRIOR_SCHEMA,
        "trial_count": 90,
        "report_only": True,
        "execution_authority": "none",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("prior residual report-only contract differs")


def _cell_key(cell: Mapping[str, object]) -> CellKey:
    return (
        _text(cell.get("signal_variant"), "cell variant"),
        _text(cell.get("leader_symbol"), "cell leader"),
        _text(cell.get("follower_symbol"), "cell follower"),
        _integer(cell.get("horizon_minutes"), "cell horizon"),
    )


def _candidate_key(value: object) -> tuple[str, str, int] | None:
    if value is None:
        return None
    candidate = _mapping(value, "selected candidate")
    return (
        _text(candidate.get("leader_symbol"), "candidate leader"),
        _text(candidate.get("follower_symbol"), "candidate follower"),
        _integer(candidate.get("horizon_minutes"), "candidate horizon"),
    )


def _same_evidence(
    declared: Mapping[str, object], observed: Mapping[str, object]
) -> bool:
    return declared.get("sha256") == observed.get("sha256") and declared.get(
        "bytes"
    ) == observed.get("bytes")


def _same_value(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(right, dict):
        return left == right
    if isinstance(right, (int, float)) and not isinstance(right, bool):
        try:
            return math.isclose(float(left), float(right), abs_tol=_TOLERANCE)
        except (TypeError, ValueError):
            return False
    return left == right


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value
