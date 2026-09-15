"""Immutable exact retained-candle inputs for offline startup replay."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
from importlib.metadata import version
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import tempfile

import pandas as pd

_SCHEMA_VERSION = 1
_MINUTES_PER_DAY = 1440
_CONTRACT = "merged_retained_1m_before_resampling_including_incomplete_candles"


@dataclass(frozen=True)
class StartupCandleContext:
    """Bind source inputs to one profile, run and causal observation boundary."""

    profile_id: str
    profile_fingerprint: str
    run_fingerprint: str
    run_id: str
    symbols: tuple[str, ...]
    activation_time_ms: int
    observed_at_ms: int
    requested_lookback_days: float

    def __post_init__(self) -> None:
        """Reject ambiguous identities and invalid retention boundaries."""
        if not self.profile_id.strip() or not self.run_id.strip():
            raise ValueError("startup candle profile_id and run_id are required")
        for digest in (self.profile_fingerprint, self.run_fingerprint):
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError("startup candle fingerprints must be SHA256 values")
        if not self.symbols or len(set(self.symbols)) != len(self.symbols):
            raise ValueError("startup candle symbols must be nonempty and unique")
        if any(not symbol.strip() for symbol in self.symbols):
            raise ValueError("startup candle symbol must not be blank")
        for value in (self.activation_time_ms, self.observed_at_ms):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("startup candle clocks must be nonnegative integers")
        if self.observed_at_ms < self.activation_time_ms:
            raise ValueError("startup candle observation predates activation")
        if (isinstance(self.requested_lookback_days, bool)
                or not math.isfinite(self.requested_lookback_days)
                or self.requested_lookback_days <= 0):
            raise ValueError("startup candle lookback must be finite and positive")

    def as_payload(self) -> dict[str, object]:
        """Return JSON-compatible identity without losing configured symbol order."""
        payload = asdict(self)
        payload["symbols"] = list(self.symbols)
        return payload


@dataclass(frozen=True)
class StartupCandleReceipt:
    """Externally record the manifest hash needed to authenticate replay."""

    manifest_path: Path
    manifest_sha256: str
    rows: int
    bytes: int

    def as_payload(self) -> dict[str, object]:
        """Return a small ledger reference instead of embedding candle history."""
        return {**asdict(self), "manifest_path": str(self.manifest_path)}


def write_startup_candles(
    root: Path,
    context: StartupCandleContext,
    frames: Mapping[str, pd.DataFrame],
) -> StartupCandleReceipt:
    """Publish one immutable run bundle; refuse conflicting prior evidence."""
    if set(frames) != set(context.symbols):
        raise ValueError("startup candle frames must match configured symbols")
    root.mkdir(parents=True, exist_ok=True)
    final = root / hashlib.sha256(context.run_id.encode()).hexdigest()
    if final.exists():
        raise FileExistsError(f"startup candle bundle already exists: {final}")
    with tempfile.TemporaryDirectory(prefix=".startup-", dir=root) as raw:
        staging = Path(raw)
        records = [
            _write_frame(staging, symbol, index, frames[symbol], context)
            for index, symbol in enumerate(context.symbols)
        ]
        manifest = {
            "schema_version": _SCHEMA_VERSION,
            "source_contract": _CONTRACT,
            "context": context.as_payload(),
            "libraries": {"pandas": pd.__version__, "pyarrow": version("pyarrow")},
            "files": records,
        }
        encoded = json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False).encode()
        manifest_path = staging / "manifest.json"
        with manifest_path.open("xb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        _sync_directory(staging)
        staging.rename(final)
        _sync_directory(root)
    return StartupCandleReceipt(
        final / "manifest.json", hashlib.sha256(encoded).hexdigest(),
        sum(len(frame) for frame in frames.values()),
        len(encoded) + sum((final / _filename(i)).stat().st_size for i in range(len(records))),
    )


def load_startup_candles(
    manifest_path: Path,
    manifest_sha256: str,
    context: StartupCandleContext,
) -> dict[str, pd.DataFrame]:
    """Authenticate externally bound metadata and every exact frame before replay."""
    encoded = manifest_path.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != manifest_sha256:
        raise ValueError("startup candle manifest SHA256 mismatch")
    manifest = json.loads(encoded)
    if not isinstance(manifest, dict) or (
        manifest.get("schema_version") != _SCHEMA_VERSION
        or manifest.get("source_contract") != _CONTRACT
        or manifest.get("context") != context.as_payload()
    ):
        raise ValueError("startup candle manifest context or schema mismatch")
    records = manifest.get("files")
    if not isinstance(records, list) or len(records) != len(context.symbols):
        raise ValueError("startup candle manifest file coverage mismatch")
    return {
        symbol: _read_frame(manifest_path.parent, record, symbol, index, context)
        for index, (symbol, record) in enumerate(zip(context.symbols, records, strict=True))
    }


def _filename(index: int) -> str:
    return f"candles-{index:03d}.parquet"


def _frame_metadata(frame: pd.DataFrame, context: StartupCandleContext) -> dict[str, object]:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not frame.columns.is_unique or not all(isinstance(c, str) for c in frame.columns):
        raise ValueError("startup candle columns must be unique strings")
    if not required.issubset(frame.columns):
        raise ValueError("startup candle frame lacks required OHLCV columns")
    timestamps = frame["timestamp"]
    if not isinstance(timestamps.dtype, pd.DatetimeTZDtype):
        raise ValueError("startup candle timestamps must be timezone-aware")
    if (timestamps.isna().any() or not timestamps.is_unique
            or not timestamps.is_monotonic_increasing):
        raise ValueError("startup candle timestamps must be unique and increasing")
    row_limit = math.ceil(context.requested_lookback_days * _MINUTES_PER_DAY) + 1
    if len(frame) > row_limit:
        raise ValueError("startup candle frame exceeds configured retention bound")
    return {
        "rows": len(frame),
        "columns": list(frame.columns),
        "dtypes": [str(dtype) for dtype in frame.dtypes],
        "index_class": type(frame.index).__name__,
        "index_dtype": str(frame.index.dtype),
        "first_open_utc": None if frame.empty else timestamps.iloc[0].isoformat(),
        "last_open_utc": None if frame.empty else timestamps.iloc[-1].isoformat(),
    }


def _write_frame(
    root: Path, symbol: str, index: int, frame: pd.DataFrame, context: StartupCandleContext,
) -> dict[str, object]:
    metadata = _frame_metadata(frame, context)
    path = root / _filename(index)
    with path.open("xb") as output:
        frame.to_parquet(output, engine="pyarrow", compression="zstd")
        output.flush()
        os.fsync(output.fileno())
    encoded = path.read_bytes()
    return {
        "symbol": symbol, "path": path.name, "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(), **metadata,
    }


def _read_frame(
    root: Path, record: object, symbol: str, index: int, context: StartupCandleContext,
) -> pd.DataFrame:
    if not isinstance(record, dict) or record.get("path") != _filename(index):
        raise ValueError("startup candle manifest has an invalid file path")
    path = root / _filename(index)
    if path.is_symlink():
        raise ValueError("startup candle payload must not be a symlink")
    encoded = path.read_bytes()
    if (record.get("symbol") != symbol or record.get("bytes") != len(encoded)
            or record.get("sha256") != hashlib.sha256(encoded).hexdigest()):
        raise ValueError("startup candle payload identity, size or SHA256 mismatch")
    frame = pd.read_parquet(BytesIO(encoded), engine="pyarrow")
    expected = {
        "symbol": symbol, "path": path.name, "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(), **_frame_metadata(frame, context),
    }
    if record != expected:
        raise ValueError("startup candle payload metadata mismatch")
    return frame


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
