"""Parquet cache under data/cache/ — cache-first IO (SRS_HV1_CACHE)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hypervector.data.provenance import OHLCV_COLUMNS, normalize_ohlcv


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

    def save(self, key: str, df: pd.DataFrame) -> Path:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        out = normalize_ohlcv(df)
        # pyarrow via pandas
        out.to_parquet(path, index=False)
        return path

    def load_or_none(self, key: str) -> pd.DataFrame | None:
        return self.load(key)
