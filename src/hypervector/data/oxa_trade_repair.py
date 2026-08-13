"""Recoverable taker-only renormalization for stored 0xArchive trade bundles."""

from __future__ import annotations

import gzip
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from hypervector.data.oxa_storage import (
    file_evidence,
    verify_file_evidence,
    write_json,
)
from hypervector.data.oxa_trades import (
    OxaTradeFetch,
    OxaTradePage,
    OxaTradeRequest,
    TRADE_NORMALIZATION_VERSION,
    normalize_trade_pages,
    parse_trade_page,
    write_trade_jsonl,
)

_BACKUP_SUFFIX = ".pre_taker_only_v2"


@dataclass(frozen=True)
class TradeBundleRepair:
    """Measured outcome of previewing or applying one bundle repair."""

    directory: Path
    backup_directory: Path
    previous_trade_count: int
    repaired_trade_count: int
    raw_fill_count: int
    applied: bool


def repair_trade_bundle(
    directory: Path,
    *,
    apply: bool = False,
) -> TradeBundleRepair:
    """Preview or apply a recoverable taker-only bundle renormalization."""
    manifest = _load_manifest(directory)
    previous_count = _integer(manifest, "trade_count")
    raw_count = _integer(manifest, "raw_fill_count")
    backup = directory.with_name(directory.name + _BACKUP_SUFFIX)
    if manifest.get("normalization_version") == TRADE_NORMALIZATION_VERSION:
        return TradeBundleRepair(
            directory, backup, previous_count, previous_count, raw_count, False
        )
    verify_file_evidence(directory, manifest.get("files"))
    request = _request_from_manifest(manifest)
    result = normalize_trade_pages(_load_pages(directory, manifest, request))
    _validate_result(result, manifest)
    report = TradeBundleRepair(
        directory, backup, previous_count, len(result.trades), raw_count, apply
    )
    if apply:
        _publish_repair(directory, backup, manifest, result)
    return report


def _load_manifest(directory: Path) -> dict[str, object]:
    if not directory.is_dir() or not directory.name.endswith("_trades"):
        raise ValueError(f"trade repair target is not a bundle: {directory}")
    path = directory / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"trade bundle manifest is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"trade bundle manifest must be an object: {path}")
    if value.get("source") != "0xarchive_hyperliquid_public_trades":
        raise ValueError(f"trade bundle source is invalid: {directory}")
    return value


def _request_from_manifest(manifest: dict[str, object]) -> OxaTradeRequest:
    symbol = _text(manifest, "symbol")
    start = datetime.fromisoformat(_text(manifest, "requested_start"))
    end = datetime.fromisoformat(_text(manifest, "requested_end"))
    limit = _integer(manifest, "page_limit")
    max_pages = _integer(manifest, "max_pages")
    return OxaTradeRequest(symbol, start, end, limit, max_pages)


def _load_pages(
    directory: Path,
    manifest: dict[str, object],
    request: OxaTradeRequest,
) -> tuple[OxaTradePage, ...]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"trade bundle has invalid file evidence: {directory}")
    names = sorted(
        name for name in files if isinstance(name, str) and name.startswith("raw/page-")
    )
    if len(names) != _integer(manifest, "page_count"):
        raise ValueError(f"trade bundle raw page count mismatch: {directory}")
    return tuple(_read_page(directory / name, request) for name in names)


def _read_page(path: Path, request: OxaTradeRequest) -> OxaTradePage:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    return parse_trade_page(payload, request)


def _validate_result(
    result: OxaTradeFetch,
    manifest: dict[str, object],
) -> None:
    if not result.complete:
        raise ValueError("stored trade pages retain an unresolved continuation cursor")
    if result.unresolved_fill_groups:
        raise ValueError("stored trade pages retain unresolved participant groups")
    if len(result.pages) != _integer(manifest, "page_count"):
        raise ValueError("stored trade page count changed during repair")


def _publish_repair(
    directory: Path,
    backup: Path,
    manifest: dict[str, object],
    result: OxaTradeFetch,
) -> None:
    if backup.exists():
        raise FileExistsError(f"trade repair backup already exists: {backup}")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{directory.name}.repair.", dir=directory.parent)
    )
    try:
        repaired_manifest = _write_staging(staging, directory, manifest, result)
        verify_file_evidence(staging, repaired_manifest["files"])
        directory.rename(backup)
        try:
            staging.rename(directory)
        except OSError:
            backup.rename(directory)
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _write_staging(
    staging: Path,
    source: Path,
    manifest: dict[str, object],
    result: OxaTradeFetch,
) -> dict[str, object]:
    files = _link_raw_evidence(staging, source, manifest)
    trades_path = staging / "trades.jsonl.gz"
    write_trade_jsonl(trades_path, result.trades)
    files["trades.jsonl.gz"] = file_evidence(trades_path)
    repaired = dict(manifest)
    repaired.update(_repaired_fields(manifest, result, files))
    write_json(staging / "manifest.json", repaired)
    return repaired


def _link_raw_evidence(
    staging: Path,
    source: Path,
    manifest: dict[str, object],
) -> dict[str, object]:
    value = manifest.get("files")
    if not isinstance(value, dict):
        raise ValueError(f"trade bundle has invalid file evidence: {source}")
    files: dict[str, object] = {}
    for name, evidence in value.items():
        if name == "trades.jsonl.gz":
            continue
        if not isinstance(name, str):
            raise ValueError(f"trade bundle has invalid file path: {source}")
        target = staging / name
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(source / name, target)
        files[name] = evidence
    return files


def _repaired_fields(
    previous: dict[str, object],
    result: OxaTradeFetch,
    files: dict[str, object],
) -> dict[str, object]:
    first = result.trades[0].timestamp if result.trades else None
    last = result.trades[-1].timestamp if result.trades else None
    surrogate_count = sum(
        trade.trade_id_source == "derived_null_id_v1" for trade in result.trades
    )
    return {
        "files": files,
        "normalization_version": TRADE_NORMALIZATION_VERSION,
        "observed_start": first,
        "observed_end": last,
        "surrogate_trade_id_count": surrogate_count,
        "trade_count": len(result.trades),
        "unresolved_fill_groups": result.unresolved_fill_groups,
        "repair": {
            "method": "crossed_true_taker_rows_only",
            "previous_normalization_version": previous.get("normalization_version"),
            "previous_trade_count": _integer(previous, "trade_count"),
        },
    }


def _text(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"trade bundle {key} must be a non-empty string")
    return value


def _integer(values: dict[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"trade bundle {key} must be a non-negative integer")
    return value
