"""Outcome-blind Binance BTCUSDT spot archive normalization."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_immutable_parquet,
    write_json,
)
from hypervector.research.binance_spot_archive_acquisition import _vendor_checksum


_SOURCE_SCHEMA = "binance_spot_kline_archive_bundle_v1"
_OUTPUT_SCHEMA = "normalized_binance_spot_1m_bundle_v1"
_CSV_COLUMNS = (
    "open_time_us",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time_us",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
)
_OUTPUT_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
)
_MINUTE_US = 60_000_000


@dataclass(frozen=True)
class NormalizedBinanceSpotInput:
    """Hold verified spot bars and outcome-blind technical coverage."""

    bars: pd.DataFrame
    coverage: dict[str, object]
    source_manifest_evidence: dict[str, object]


def load_verified_binance_spot_klines(bundle: Path) -> NormalizedBinanceSpotInput:
    """Verify a vendor bundle and return exact sparse UTC minute bars."""
    manifest_path = bundle / "manifest.json"
    manifest = _load_manifest(manifest_path)
    archives = manifest.get("archives")
    if not isinstance(archives, dict) or not archives:
        raise ValueError("Binance spot source manifest has no archives")
    frames = [_load_archive(bundle, name, record) for name, record in archives.items()]
    bars = pd.concat(frames) if frames else _empty_bars()
    bars = _validated_bars(bars, manifest)
    coverage = _coverage(bars)
    return NormalizedBinanceSpotInput(
        bars=bars,
        coverage=coverage,
        source_manifest_evidence={
            "path": str(manifest_path.resolve()),
            **file_evidence(manifest_path),
        },
    )


def publish_normalized_binance_spot_bundle(source: Path, output: Path) -> Path:
    """Atomically publish verified bars without calculating candidate fields."""
    result = load_verified_binance_spot_klines(source)
    if output.exists():
        raise FileExistsError(
            f"normalized Binance spot bundle already exists: {output}"
        )

    def writer(staging: Path) -> None:
        bars_path = staging / "spot_1m.parquet"
        frame = result.bars.reset_index(names="timestamp")
        write_immutable_parquet(bars_path, frame)
        manifest = {
            "schema_version": _OUTPUT_SCHEMA,
            "execution_authority": "none",
            "report_only": True,
            "candidate_outcomes_computed": False,
            "source_manifest": result.source_manifest_evidence,
            "coverage": result.coverage,
            "files": {"spot_1m.parquet": file_evidence(bars_path)},
        }
        write_json(staging / "manifest.json", manifest)

    publish_immutable_directory(output, writer)
    return output


def _load_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Binance spot source manifest is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != _SOURCE_SCHEMA:
        raise ValueError("Binance spot source manifest schema drifted")
    if payload.get("execution_authority") != "none":
        raise ValueError("Binance spot source manifest acquired execution authority")
    if payload.get("candidate_outcomes_computed") is not False:
        raise ValueError("Binance spot source manifest contains candidate outcomes")
    return payload


def _load_archive(bundle: Path, name: object, record: object) -> pd.DataFrame:
    if not isinstance(name, str) or not isinstance(record, dict):
        raise ValueError("Binance spot archive record is malformed")
    archive_path = _bound_path(bundle, record.get("archive_file"))
    checksum_path = _bound_path(bundle, record.get("checksum_file"))
    observed = _require_evidence(archive_path, record.get("archive_evidence"))
    _require_evidence(checksum_path, record.get("checksum_evidence"))
    vendor_sha = record.get("vendor_sha256")
    if vendor_sha != observed["sha256"]:
        raise ValueError(f"Binance spot archive vendor hash drifted: {name}")
    expected = _vendor_checksum(checksum_path.read_bytes(), name)
    if expected != vendor_sha:
        raise ValueError(f"Binance spot checksum binding drifted: {name}")
    return _read_archive_csv(archive_path, name)


def _read_archive_csv(path: Path, archive_name: str) -> pd.DataFrame:
    expected_member = f"{Path(archive_name).stem}.csv"
    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        if members != [expected_member]:
            raise ValueError(f"Binance spot ZIP members are unexpected: {archive_name}")
        with archive.open(expected_member) as handle:
            if archive.getinfo(expected_member).file_size == 0:
                return _empty_raw_frame()
            frame = pd.read_csv(handle, header=None, names=_CSV_COLUMNS)
    frame["source_archive"] = archive_name
    return frame


def _validated_bars(frame: pd.DataFrame, manifest: dict[str, object]) -> pd.DataFrame:
    if frame.empty:
        raise ValueError("Binance spot source has no rows")
    numeric = frame.loc[:, _CSV_COLUMNS].apply(pd.to_numeric, errors="raise")
    open_us = numeric["open_time_us"].to_numpy(dtype=np.int64)
    close_us = numeric["close_time_us"].to_numpy(dtype=np.int64)
    if (open_us < 1_000_000_000_000_000).any():
        raise ValueError("Binance spot open timestamps must be microseconds")
    if (open_us % _MINUTE_US != 0).any() or not np.array_equal(
        close_us, open_us + _MINUTE_US - 1
    ):
        raise ValueError("Binance spot timestamps violate exact minute boundaries")
    bars = numeric.loc[:, _OUTPUT_COLUMNS].copy()
    bars.index = pd.to_datetime(open_us, unit="us", utc=True)
    bars.index.name = "timestamp"
    bars["source"] = "binance_spot_data_vision"
    bars["source_archive"] = frame["source_archive"].to_numpy()
    bars = _slice_and_validate_market(bars, manifest)
    gaps = bars.index.to_series().diff().div(pd.Timedelta(minutes=1)).sub(1)
    bars["gap_before_bars"] = gaps.fillna(0).astype(int)
    return bars


def _slice_and_validate_market(
    bars: pd.DataFrame,
    manifest: dict[str, object],
) -> pd.DataFrame:
    if not bars.index.is_unique:
        raise ValueError("Binance spot source has duplicate open timestamps")
    if not bars.index.is_monotonic_increasing:
        raise ValueError("Binance spot source timestamps are not increasing")
    start = pd.Timestamp(str(manifest.get("start_utc")))
    end = pd.Timestamp(str(manifest.get("end_utc")))
    if start.tz is None or end.tz is None or end <= start:
        raise ValueError("Binance spot source interval is invalid")
    selected = bars.loc[(bars.index >= start) & (bars.index < end)].copy()
    if selected.empty:
        raise ValueError("Binance spot source has no rows inside its interval")
    _validate_prices_and_volume(selected)
    return selected


def _validate_prices_and_volume(bars: pd.DataFrame) -> None:
    ohlc = bars.loc[:, ["open", "high", "low", "close"]]
    if not np.isfinite(ohlc.to_numpy()).all() or (ohlc <= 0.0).any().any():
        raise ValueError("Binance spot OHLC must be finite and positive")
    if (ohlc["high"] < ohlc.max(axis=1)).any():
        raise ValueError("Binance spot high is internally inconsistent")
    if (ohlc["low"] > ohlc.min(axis=1)).any():
        raise ValueError("Binance spot low is internally inconsistent")
    nonnegative = bars.loc[
        :, [column for column in _OUTPUT_COLUMNS if column not in ohlc]
    ]
    if not np.isfinite(nonnegative.to_numpy()).all() or (nonnegative < 0.0).any().any():
        raise ValueError("Binance spot activity fields must be finite and non-negative")


def _coverage(bars: pd.DataFrame) -> dict[str, object]:
    gaps = bars["gap_before_bars"]
    return {
        "rows": len(bars),
        "first_timestamp_utc": bars.index[0].isoformat(),
        "last_timestamp_utc": bars.index[-1].isoformat(),
        "gap_boundaries": int(gaps.gt(0).sum()),
        "missing_minutes": int(gaps.sum()),
        "duplicate_minutes": 0,
        "candidate_outcomes_computed": False,
    }


def _bound_path(bundle: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("Binance spot manifest has an invalid file path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Binance spot manifest file path is unsafe: {value}")
    path = bundle / relative
    if not path.is_file():
        raise ValueError(f"Binance spot manifest file is missing: {path}")
    return path


def _require_evidence(path: Path, expected: object) -> dict[str, object]:
    if not isinstance(expected, dict):
        raise ValueError(f"Binance spot manifest evidence is invalid: {path}")
    observed = file_evidence(path)
    if observed != expected:
        raise ValueError(f"Binance spot manifest evidence drifted: {path}")
    return observed


def _empty_raw_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=(*_CSV_COLUMNS, "source_archive"))


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=(*_OUTPUT_COLUMNS, "source", "source_archive"))
