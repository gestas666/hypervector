"""Parquet cache under data/cache/ — cache-first IO (SRS_HV1_CACHE)."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from hypervector.data.provenance import normalize_ohlcv

# Parquet footer key holding the writer's JSON metadata (fetch time, request).
CACHE_METADATA_KEY = b"hypervector.cache"


class ParquetCache:
    """Filesystem Parquet cache keyed by symbol/tf/lookback-ish strings."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe}.parquet"

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def load(self, key: str) -> pd.DataFrame | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        df = pd.read_parquet(path)
        return normalize_ohlcv(df)

    def load_metadata(self, key: str) -> dict[str, Any] | None:
        """Writer metadata stored in the file footer; ``None`` for legacy files."""
        path = self.path_for(key)
        if not path.is_file():
            return None
        raw = (pq.read_schema(path).metadata or {}).get(CACHE_METADATA_KEY)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def save(
        self,
        key: str,
        df: pd.DataFrame,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> Path:
        """Write atomically (temp file + rename) so readers never see a torn file."""
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        out = normalize_ohlcv(df)
        table = pa.Table.from_pandas(out, preserve_index=False)
        if metadata is not None:
            footer = dict(table.schema.metadata or {})
            footer[CACHE_METADATA_KEY] = json.dumps(
                dict(metadata), sort_keys=True, default=str
            ).encode("utf-8")
            table = table.replace_schema_metadata(footer)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            pq.write_table(table, tmp)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        return path

    def load_or_none(self, key: str) -> pd.DataFrame | None:
        return self.load(key)
