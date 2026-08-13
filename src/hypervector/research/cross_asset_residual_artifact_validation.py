"""Bounded integrity validation for cross-asset residual research artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from hypervector.data.oxa_storage import file_evidence

_SCHEMAS = {
    "cross_asset_residual_development_v1": "config",
    "cross_asset_residual_exit_surface_v1": "signal_contract",
    "cross_asset_residual_development_v2": "config",
    "cross_asset_residual_exit_surface_v2": "signal_contract",
}
_SOURCE_SYMBOLS = {"BTC", "ETH", "SOL", "HYPE"}
_TRADE_COLUMNS = (
    "left_symbol",
    "right_symbol",
    "signal_time_utc",
    "entry_time_utc",
    "exit_time_utc",
    "gross_pnl_usd",
    "fees_usd",
    "funding_cashflow_usd",
    "liquidation_penalty_usd",
    "net_pnl_usd",
    "equity_before_usd",
    "equity_after_usd",
    "exit_reason",
)
_FLOAT_TOLERANCE = 1e-7
_MAX_GENERATOR_MODULES = 64

CellKey = tuple[str, ...]


@dataclass(frozen=True)
class ResidualArtifactValidation:
    """Verified identities and counts for one immutable residual artifact."""

    artifact_path: str
    artifact_sha256: str
    sidecar_path: str
    sidecar_sha256: str
    cells_verified: int
    trades_verified: int
    source_files_verified: int
    generator_modules_verified: int
    execution_authority: str
    valid: bool = True


def validate_cross_asset_residual_artifact(
    artifact_path: Path,
    *,
    generator_manifest_path: Path | None = None,
    max_cells: int = 512,
    max_trade_rows: int = 100_000,
) -> ResidualArtifactValidation:
    """Verify a residual report without replaying market data or granting authority."""
    artifact = _read_json_mapping(artifact_path, "residual artifact")
    cells = _validated_cells(artifact, max_cells)
    authority = _validate_authority(artifact, cells)
    sidecar_path, sidecar_evidence, trade_rows = _validated_sidecar(
        artifact,
        max_trade_rows,
    )
    frame = _read_trade_columns(sidecar_path, cells)
    _validate_trade_cells(cells, frame)
    source_count = _validate_source_files(artifact)
    generator_count = _validate_embedded_generator_identity(artifact)
    generator_count += _validate_generator_manifest(generator_manifest_path)
    artifact_evidence = file_evidence(artifact_path)
    return ResidualArtifactValidation(
        artifact_path=str(artifact_path.resolve()),
        artifact_sha256=_string(artifact_evidence.get("sha256"), "artifact sha256"),
        sidecar_path=str(sidecar_path.resolve()),
        sidecar_sha256=_string(sidecar_evidence.get("sha256"), "sidecar sha256"),
        cells_verified=len(cells),
        trades_verified=trade_rows,
        source_files_verified=source_count,
        generator_modules_verified=generator_count,
        execution_authority=authority,
    )


def _read_json_mapping(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    return dict(_mapping(value, label))


def _validated_cells(
    artifact: Mapping[str, object],
    max_cells: int,
) -> list[dict[str, object]]:
    if max_cells < 0:
        raise ValueError("maximum cell bound must be non-negative")
    raw = artifact.get("cells")
    if not isinstance(raw, list):
        raise ValueError("residual artifact cells must be a list")
    if len(raw) > max_cells:
        raise ValueError(
            f"residual artifact cell bound exceeded: {len(raw)} > {max_cells}"
        )
    cells = [dict(_mapping(value, "residual cell")) for value in raw]
    if artifact.get("trial_count") != len(cells):
        raise ValueError("residual artifact trial_count differs from cell count")
    if len({_cell_key(cell, _surface_cells(cells)) for cell in cells}) != len(cells):
        raise ValueError("residual artifact contains duplicate cell identity")
    return cells


def _validate_authority(
    artifact: Mapping[str, object],
    cells: list[dict[str, object]],
) -> str:
    if artifact.get("report_only") is not True:
        raise ValueError("residual artifact must remain report-only")
    authority = artifact.get("execution_authority")
    if authority != "none":
        raise ValueError("residual execution authority must be none")
    schema = _string(artifact.get("schema_version"), "residual schema version")
    contract_key = _SCHEMAS.get(schema)
    if contract_key is None:
        raise ValueError(f"unsupported residual artifact schema: {schema}")
    contract = _mapping(artifact.get(contract_key), f"residual {contract_key}")
    if contract.get("execution_authority") != authority:
        raise ValueError("residual contract execution authority does not inherit none")
    if any(cell.get("execution_authority") != authority for cell in cells):
        raise ValueError("residual cell execution authority does not inherit none")
    return authority


def _validated_sidecar(
    artifact: Mapping[str, object],
    max_trade_rows: int,
) -> tuple[Path, dict[str, object], int]:
    if max_trade_rows < 0:
        raise ValueError("maximum trade row bound must be non-negative")
    storage = _mapping(artifact.get("trade_storage"), "residual trade storage")
    path = _declared_path(storage.get("path"), "trade sidecar")
    if not path.is_file():
        raise FileNotFoundError(f"residual trade sidecar is missing: {path}")
    observed = file_evidence(path)
    if not _same_evidence(storage, observed):
        raise ValueError(f"residual trade sidecar evidence differs: {path}")
    metadata_rows = int(pq.ParquetFile(path).metadata.num_rows)
    declared_rows = _integer(storage.get("rows"), "trade sidecar rows")
    if declared_rows != metadata_rows:
        raise ValueError("residual trade sidecar row count differs")
    if metadata_rows > max_trade_rows:
        raise ValueError(
            f"residual trade row bound exceeded: {metadata_rows} > {max_trade_rows}"
        )
    return path, observed, metadata_rows


def _read_trade_columns(
    path: Path,
    cells: list[dict[str, object]],
) -> pd.DataFrame:
    surface = _surface_cells(cells)
    prefix = ("trial_id",) if surface else ()
    columns = [*prefix, *_TRADE_COLUMNS]
    available = set(pq.ParquetFile(path).schema_arrow.names)
    missing = sorted(set(columns).difference(available))
    if missing:
        raise ValueError(f"residual trade sidecar missing columns: {missing}")
    frame = pd.read_parquet(path, columns=columns)
    if "execution_authority" in available:
        authorities = pd.read_parquet(path, columns=["execution_authority"])
        if not authorities["execution_authority"].eq("none").all():
            raise ValueError("residual trade execution authority does not inherit none")
    _validate_trade_lifecycle_identity(frame, surface)
    return frame


def _validate_trade_lifecycle_identity(frame: pd.DataFrame, surface: bool) -> None:
    prefix = ("trial_id",) if surface else ()
    identity = [*prefix, "left_symbol", "right_symbol"]
    lifecycle = [*identity, "signal_time_utc", "entry_time_utc", "exit_time_utc"]
    if frame[lifecycle].isna().any().any():
        raise ValueError("residual trade lifecycle identity contains null values")
    if frame.duplicated(lifecycle).any():
        raise ValueError("residual trade sidecar contains duplicate lifecycle identity")


def _validate_trade_cells(
    cells: list[dict[str, object]],
    frame: pd.DataFrame,
) -> None:
    surface = _surface_cells(cells)
    cell_map = {_cell_key(cell, surface): cell for cell in cells}
    groups = _trade_groups(frame, surface)
    unexpected = sorted(set(groups).difference(cell_map))
    if unexpected:
        raise ValueError(
            f"residual trade sidecar has undeclared cell identity: {unexpected}"
        )
    for key, cell in cell_map.items():
        group = groups.get(key, frame.iloc[0:0])
        _validate_equity_chain(key, group)
        _validate_cell_aggregates(key, cell, group)


def _trade_groups(frame: pd.DataFrame, surface: bool) -> dict[CellKey, pd.DataFrame]:
    prefix = ("trial_id",) if surface else ()
    fields = [*prefix, "left_symbol", "right_symbol"]
    groups: dict[CellKey, pd.DataFrame] = {}
    for values, group in frame.groupby(fields, sort=False, dropna=False):
        raw = values if isinstance(values, tuple) else (values,)
        key = tuple(_string(value, "trade cell identity") for value in raw)
        groups[key] = group.reset_index(drop=True)
    return groups


def _validate_equity_chain(key: CellKey, frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    before = frame["equity_before_usd"].astype(float)
    after = frame["equity_after_usd"].astype(float)
    net = frame["net_pnl_usd"].astype(float)
    if not _series_close(after, before + net):
        raise ValueError(f"residual trade equity identity differs for cell {key}")
    if len(frame) > 1 and not _series_close(before.iloc[1:], after.iloc[:-1]):
        raise ValueError(f"residual trade equity chain differs for cell {key}")


def _validate_cell_aggregates(
    key: CellKey,
    cell: Mapping[str, object],
    frame: pd.DataFrame,
) -> None:
    net = frame["net_pnl_usd"].astype(float)
    aggregates: dict[str, int | float | None] = {
        "completed_trades": len(frame),
        "wins": int(net.gt(0.0).sum()),
        "losses": int(net.le(0.0).sum()),
        "gross_pnl_usd": float(frame["gross_pnl_usd"].astype(float).sum()),
        "fees_usd": float(frame["fees_usd"].astype(float).sum()),
        "funding_cashflow_usd": float(
            frame["funding_cashflow_usd"].astype(float).sum()
        ),
        "liquidation_penalties_usd": float(
            frame["liquidation_penalty_usd"].astype(float).sum()
        ),
        "net_pnl_usd": float(net.sum()),
        "liquidations": int(frame["exit_reason"].eq("liquidation").sum()),
        "profit_factor": _profit_factor(net),
    }
    _add_equity_aggregates(aggregates, cell, frame)
    for field, observed in aggregates.items():
        if not _same_number(cell.get(field), observed):
            raise ValueError(f"residual cell {field} differs for identity {key}")


def _add_equity_aggregates(
    aggregates: dict[str, int | float | None],
    cell: Mapping[str, object],
    frame: pd.DataFrame,
) -> None:
    if frame.empty:
        initial = _number(cell.get("initial_equity"), "cell initial_equity")
        aggregates["initial_equity"] = initial
        aggregates["final_equity"] = initial
        return
    aggregates["initial_equity"] = float(frame.iloc[0]["equity_before_usd"])
    aggregates["final_equity"] = float(frame.iloc[-1]["equity_after_usd"])


def _profit_factor(net: pd.Series) -> float | None:
    gains = float(net[net > 0.0].sum())
    losses = -float(net[net < 0.0].sum())
    if losses > 0.0:
        return gains / losses
    return math.inf if gains > 0.0 else None


def _validate_source_files(artifact: Mapping[str, object]) -> int:
    identity = _mapping(artifact.get("source_identity"), "residual source identity")
    if set(identity) != _SOURCE_SYMBOLS:
        raise ValueError("residual source identity must cover BTC/ETH/SOL/HYPE")
    verified = 0
    for symbol in sorted(_SOURCE_SYMBOLS):
        source = _mapping(identity.get(symbol), f"{symbol} source identity")
        for kind in ("bars", "funding"):
            path = _declared_path(source.get(f"{kind}_path"), f"{symbol} {kind}")
            declared = _mapping(source.get(kind), f"{symbol} {kind} evidence")
            if not path.is_file():
                raise FileNotFoundError(f"residual source file is missing: {path}")
            if not _same_evidence(declared, file_evidence(path)):
                raise ValueError(
                    f"residual source file evidence differs: {symbol} {kind}"
                )
            verified += 1
    return verified


def _validate_generator_manifest(path: Path | None) -> int:
    if path is None:
        return 0
    manifest = _read_json_mapping(path, "residual generator manifest")
    modules = _mapping(manifest.get("generator_modules"), "generator modules")
    return _validate_generator_modules(modules)


def _validate_embedded_generator_identity(
    artifact: Mapping[str, object],
) -> int:
    schema = _string(artifact.get("schema_version"), "residual schema version")
    raw = artifact.get("generator_identity")
    if raw is None and schema.endswith("_v1"):
        return 0
    identity = _mapping(raw, "residual generator identity")
    modules = _mapping(identity.get("generator_modules"), "generator modules")
    if not modules:
        raise ValueError("residual generator identity must contain modules")
    return _validate_generator_modules(modules)


def _validate_generator_modules(modules: Mapping[str, object]) -> int:
    if len(modules) > _MAX_GENERATOR_MODULES:
        raise ValueError("residual generator module bound exceeded")
    for name, value in modules.items():
        module = _declared_path(name, "generator module")
        declared = _mapping(value, f"generator module evidence {name}")
        if not module.is_file():
            raise FileNotFoundError(f"residual generator module is missing: {module}")
        if not _same_evidence(declared, file_evidence(module)):
            raise ValueError(f"residual generator module evidence differs: {module}")
    return len(modules)


def _surface_cells(cells: list[dict[str, object]]) -> bool:
    flags = {"trial_id" in cell for cell in cells}
    if len(flags) > 1:
        raise ValueError("residual cells mix development and surface identity")
    return True in flags


def _cell_key(cell: Mapping[str, object], surface: bool) -> CellKey:
    prefix = ("trial_id",) if surface else ()
    fields = [*prefix, "left_symbol", "right_symbol"]
    return tuple(_string(cell.get(field), f"cell {field}") for field in fields)


def _declared_path(value: object, label: str) -> Path:
    text = _string(value, f"{label} path")
    path = Path(text).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def _same_evidence(
    declared: Mapping[str, object],
    observed: Mapping[str, object],
) -> bool:
    return declared.get("bytes") == observed.get("bytes") and declared.get(
        "sha256"
    ) == observed.get("sha256")


def _same_number(declared: object, observed: int | float | None) -> bool:
    if observed is None:
        return declared is None
    if isinstance(declared, bool) or not isinstance(declared, (int, float)):
        return False
    return math.isclose(
        float(declared),
        float(observed),
        rel_tol=1e-9,
        abs_tol=_FLOAT_TOLERANCE,
    )


def _series_close(left: pd.Series, right: pd.Series) -> bool:
    if len(left) != len(right):
        return False
    return all(
        math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=_FLOAT_TOLERANCE)
        for a, b in zip(left, right, strict=True)
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} keys must be strings")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result
