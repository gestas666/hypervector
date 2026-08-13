"""Evidence identity checks for SOL backward temporal validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

import pandas as pd


def validate_backward_manifest(
    data_path: Path,
    expected_source: str,
    start: datetime,
    end: datetime,
    *,
    interval: str | None = None,
) -> Mapping[str, object]:
    """Validate venue, symbol, window, and checksum identity for one input."""
    manifest_path = data_path.parent / "manifest.json"
    payload = _read_object(manifest_path)
    expected = {
        "source": expected_source,
        "venue": "hyperliquid",
        "symbol": "SOL",
        "complete": True,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError(f"SOL backward manifest identity mismatch: {manifest_path}")
    if interval is not None and payload.get("interval") != interval:
        raise ValueError("SOL backward candle interval must be 1m")
    _validate_window(payload, start, end)
    files = _object_map(payload.get("files"), "manifest files")
    evidence = _object_map(files.get(data_path.name), f"manifest {data_path.name}")
    if evidence.get("sha256") != sha256(data_path):
        raise ValueError(f"SOL backward data checksum mismatch: {data_path}")
    return payload


def validate_backward_manifest_rows(
    payload: Mapping[str, object],
    observed: int,
    label: str,
) -> None:
    """Require the normalized row count to match its immutable manifest."""
    value = payload.get("row_count", payload.get("observed_hour_count"))
    if isinstance(value, bool) or not isinstance(value, int) or value != observed:
        raise ValueError(f"SOL backward {label} manifest row count mismatch")


def sha256(path: Path) -> str:
    """Return the SHA-256 identity of one evidence file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_window(
    payload: Mapping[str, object],
    start: datetime,
    end: datetime,
) -> None:
    observed_start = pd.Timestamp(payload.get("requested_start"))
    observed_end = pd.Timestamp(payload.get("requested_end"))
    if observed_start != pd.Timestamp(start) or observed_end != pd.Timestamp(end):
        raise ValueError("SOL backward manifest window mismatch")


def _read_object(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"SOL backward manifest is missing: {path}")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid SOL backward manifest: {path}") from exc
    return _object_map(payload, "manifest")


def _object_map(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"SOL backward {label} must be a string-keyed object")
    return value
