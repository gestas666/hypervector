"""Independent integrity and causal-rebuild checks for breadth evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cross_asset_breadth_data import (
    load_breadth_development_inputs,
)
from hypervector.research.cross_asset_breadth_models import (
    CrossAssetBreadthConfig,
    declared_breadth_folds,
)
from hypervector.research.cross_asset_breadth_screen import (
    build_breadth_development,
)

_SCHEMA = "cross_asset_breadth_development_v1"
_SELF_PATH = "src/hypervector/research/cross_asset_breadth_artifact_validation.py"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")


@dataclass(frozen=True)
class BreadthArtifactValidation:
    """Verified identities and counts for one immutable breadth artifact."""

    artifact_path: str
    artifact_sha256: str
    sidecar_path: str
    sidecar_sha256: str
    primary_cells_verified: int
    control_cells_verified: int
    event_rows_verified: int
    source_symbols_verified: int
    generator_modules_verified: int
    execution_authority: str
    valid: bool = True


def validate_cross_asset_breadth_artifact(
    artifact_path: Path,
    *,
    max_event_rows: int = 1_000_000,
) -> BreadthArtifactValidation:
    """Rebuild the report from bound sources without granting authority."""
    artifact = _read_json(artifact_path)
    config = _validate_contract(artifact)
    _validate_authority(artifact)
    sidecar_path, rows, sidecar_evidence = _read_sidecar(artifact, max_event_rows)
    _validate_event_authority(rows)
    prior = _mapping(artifact.get("prior_cross_asset_search"), "prior search")
    data_root = _data_root(artifact)
    inputs = load_breadth_development_inputs(data_root, config)
    rebuilt, expected_rows = build_breadth_development(
        closes_15m=inputs.closes_15m,
        validity_15m=inputs.validity_15m,
        btc_minute_frame=inputs.minute_frames["BTC"],
        config=config,
        run_id=_text(artifact.get("run_id"), "run ID"),
        source_identity=inputs.source_identity,
        prior_search_identity=dict(prior),
    )
    _compare_rebuilt_artifact(artifact, rebuilt)
    _compare_event_rows(rows, expected_rows)
    generator_count = _validate_generators(artifact)
    artifact_evidence = file_evidence(artifact_path)
    return BreadthArtifactValidation(
        artifact_path=str(artifact_path.resolve()),
        artifact_sha256=_text(artifact_evidence.get("sha256"), "artifact hash"),
        sidecar_path=str(sidecar_path.resolve()),
        sidecar_sha256=_text(sidecar_evidence.get("sha256"), "sidecar hash"),
        primary_cells_verified=1,
        control_cells_verified=2,
        event_rows_verified=len(rows),
        source_symbols_verified=len(inputs.source_identity),
        generator_modules_verified=generator_count,
        execution_authority="none",
    )


def _validate_contract(artifact: Mapping[str, object]) -> CrossAssetBreadthConfig:
    if artifact.get("schema_version") != _SCHEMA:
        raise ValueError("unsupported breadth artifact schema")
    config = CrossAssetBreadthConfig()
    expected = asdict(config)
    for field in ("warmup_start", "development_start", "development_end"):
        expected[field] = getattr(config, field).isoformat()
    expected["symbols"] = list(config.symbols)
    if artifact.get("config") != expected:
        raise ValueError("breadth frozen contract config differs")
    folds = [
        {"fold": name, "start_utc": start.isoformat(), "end_utc": end.isoformat()}
        for name, start, end in declared_breadth_folds(config)
    ]
    if artifact.get("folds") != folds:
        raise ValueError("breadth frozen folds differ")
    expected_identity = {
        "warmup_start_utc": config.warmup_start.isoformat(),
        "development_start_utc": config.development_start.isoformat(),
        "development_end_utc": config.development_end.isoformat(),
        "report_only": True,
        "execution_authority": "none",
    }
    if artifact.get("contract_identity") != expected_identity:
        raise ValueError("breadth contract identity differs")
    return config


def _validate_authority(artifact: Mapping[str, object]) -> None:
    if (
        artifact.get("report_only") is not True
        or artifact.get("execution_authority") != "none"
    ):
        raise ValueError("breadth artifact has execution authority")
    primary = _mapping(artifact.get("primary_cell"), "primary cell")
    controls = artifact.get("control_cells")
    if not isinstance(controls, list) or len(controls) != 2:
        raise ValueError("breadth artifact must retain two controls")
    cells = [primary, *[_mapping(cell, "control cell") for cell in controls]]
    if any(cell.get("execution_authority") != "none" for cell in cells):
        raise ValueError("breadth cell has execution authority")
    if artifact.get("searched_set_count") != 1:
        raise ValueError("breadth searched-set count must equal one")


def _read_sidecar(
    artifact: Mapping[str, object],
    max_event_rows: int,
) -> tuple[Path, pd.DataFrame, dict[str, object]]:
    storage = _mapping(artifact.get("event_storage"), "event storage")
    path = Path(_text(storage.get("path"), "event sidecar path"))
    if not path.is_file():
        raise FileNotFoundError(f"breadth event sidecar is missing: {path}")
    evidence = file_evidence(path)
    for field in ("sha256", "bytes"):
        if storage.get(field) != evidence.get(field):
            raise ValueError(f"breadth event sidecar {field} differs")
    parquet = pq.ParquetFile(path)
    row_count = int(parquet.metadata.num_rows)
    if row_count != storage.get("rows") or row_count > max_event_rows:
        raise ValueError("breadth event sidecar row count differs or exceeds bound")
    return path, pd.read_parquet(path), evidence


def _compare_rebuilt_artifact(
    artifact: Mapping[str, object],
    rebuilt: Mapping[str, object],
) -> None:
    fields = (
        "source_identity",
        "primary_cell",
        "control_cells",
        "searched_set_count",
        "selected_candidate",
        "search_accounting",
    )
    for field in fields:
        if artifact.get(field) != rebuilt.get(field):
            raise ValueError(f"breadth rebuilt artifact differs for {field}")


def _compare_event_rows(actual: pd.DataFrame, expected: pd.DataFrame) -> None:
    try:
        pd.testing.assert_frame_equal(
            actual.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_dtype=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )
    except AssertionError as error:
        raise ValueError("breadth event sidecar differs from causal rebuild") from error


def _validate_event_authority(rows: pd.DataFrame) -> None:
    required = {"report_only", "execution_authority"}
    if not required.issubset(rows.columns):
        raise ValueError("breadth event rows are missing authority columns")
    if (
        not rows["report_only"].eq(True).all()
        or not rows["execution_authority"].eq("none").all()
    ):
        raise ValueError("breadth event rows contain execution authority")


def _validate_generators(artifact: Mapping[str, object]) -> int:
    identity = _mapping(artifact.get("generator_identity"), "generator identity")
    modules = _mapping(identity.get("generator_modules"), "generator modules")
    root = Path(__file__).resolve().parents[3]
    if _SELF_PATH not in modules:
        raise ValueError("breadth generator identity omits its validator")
    for relative, stored in modules.items():
        evidence = _mapping(stored, f"generator {relative}")
        if not isinstance(evidence.get("sha256"), str) or not isinstance(
            evidence.get("bytes"), int
        ):
            raise ValueError(f"breadth generator evidence is malformed: {relative}")
        if relative != _SELF_PATH and evidence != file_evidence(root / relative):
            raise ValueError(f"breadth generator module differs: {relative}")
    return len(modules)


def _data_root(artifact: Mapping[str, object]) -> Path:
    sources = _mapping(artifact.get("source_identity"), "source identity")
    if set(sources) != set(_SYMBOLS) or len(sources) != len(_SYMBOLS):
        raise ValueError("breadth source identity differs from the frozen universe")
    btc = _mapping(sources["BTC"], "BTC source identity")
    bars_path = Path(_text(btc.get("bars_path"), "BTC bars path"))
    if bars_path.parent.name != "cache":
        raise ValueError("breadth BTC bars path does not identify a data root")
    return bars_path.parent.parent


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"breadth artifact is missing: {path}")
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    return dict(_mapping(payload, "breadth artifact"))


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return dict(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value
