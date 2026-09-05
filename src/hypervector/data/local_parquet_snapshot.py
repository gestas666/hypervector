"""Immutable local parquet file-set snapshots for report-only research."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence

Record = dict[str, object]


@dataclass(frozen=True)
class LocalParquetSnapshot:
    """One frozen parquet file set with an exact publication recheck."""

    root: Path
    files: tuple[tuple[Path, Record], ...]
    evidence: Record

    @classmethod
    def from_directory(cls, root: Path, directory: Path) -> LocalParquetSnapshot:
        """Freeze every parquet part beneath one explicit local directory."""
        paths = tuple(sorted(directory.glob("*.parquet")))
        if not paths:
            raise FileNotFoundError(f"local parquet parts are missing: {directory}")
        exact = tuple((path, file_evidence(path)) for path in paths)
        entries = [_entry(root, path, evidence) for path, evidence in exact]
        rendered = json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()
        summary: Record = {
            "file_count": len(entries),
            "total_bytes": sum(_integer(row, "bytes") for row in entries),
            "manifest_sha256": hashlib.sha256(rendered).hexdigest(),
            "files": entries,
        }
        return cls(root.resolve(), exact, summary)

    def load(self, columns: list[str]) -> pd.DataFrame:
        """Read only declared columns from the frozen file set."""
        return pd.read_parquet(
            [str(path) for path, _evidence in self.files], columns=columns
        )

    def require_unchanged(self) -> None:
        """Fail if any consumed file changed before report publication."""
        for path, expected in self.files:
            if file_evidence(path) != expected:
                raise ValueError(
                    f"local parquet source changed during analysis: {path}"
                )


def _entry(root: Path, path: Path, evidence: Record) -> Record:
    relative = path.resolve().relative_to(root.resolve())
    return {"path": str(relative), **evidence}


def _integer(value: Record, key: str) -> int:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise ValueError(f"local parquet evidence {key} must be an integer")
    return selected
