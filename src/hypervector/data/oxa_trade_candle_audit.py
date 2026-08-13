"""Venue-candle parity audit for normalized 0xArchive public trade tapes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    OxaArchiveBundle,
    verified_archive_bundles,
)
from hypervector.data.oxa_trade_bars import (
    empty_trade_bars,
    trade_rows_to_minute_bars,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_json,
)
from hypervector.data.oxa_trades import (
    OxaTradeRequest,
    load_trade_jsonl,
    trade_output_directory,
)

PRICE_TOLERANCE = 1e-9
VOLUME_TOLERANCE = 1e-8


@dataclass(frozen=True)
class TradeCandleParityReport:
    """Measured completeness and ordering parity for one archive window."""

    symbol: str
    window_start_utc: str
    window_end_utc: str
    candle_minutes: int
    trade_minutes: int
    overlap_minutes: int
    exact_bar_minutes: int
    execution_complete_minutes: int
    ordering_only_minutes_utc: tuple[str, ...]
    degraded_execution_minutes_utc: tuple[str, ...]
    missing_trade_minutes: int
    missing_candle_minutes: int
    max_volume_delta: float
    max_trade_count_delta: int
    candle_path: str
    candle_sha256: str
    trade_manifest_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe values with explicit completeness ratios."""
        values = asdict(self)
        denominator = self.candle_minutes
        values["exact_bar_ratio"] = _ratio(self.exact_bar_minutes, denominator)
        values["execution_complete_ratio"] = _ratio(
            self.execution_complete_minutes, denominator
        )
        return values


@dataclass(frozen=True)
class TradeCandleReconstructionReport:
    """Provenance counts for one continuous venue-derived candle stream."""

    symbol: str
    window_start_utc: str
    window_end_utc: str
    native_minutes: int
    trade_reconstructed_minutes: int
    verified_no_trade_minutes: int
    native_trade_overlap_minutes: int
    minute_price_extrema_difference_minutes: int
    complete_five_minute_overlap_bars: int
    five_minute_price_extrema_difference_bars: int
    maximum_minute_high_difference: float
    maximum_minute_low_difference: float
    execution_undercoverage_minutes: int
    maximum_volume_undercoverage: float
    maximum_trade_count_undercoverage: int
    candle_path: str
    candle_sha256: str
    trade_manifest_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe reconstruction provenance."""
        return asdict(self)


@dataclass(frozen=True)
class _ReconstructionPriceParity:
    minute_differences: int
    complete_five_minute_bars: int
    five_minute_differences: int
    maximum_minute_high_difference: float
    maximum_minute_low_difference: float


def audit_trade_candle_parity(
    config: OxaArchiveAuditConfig,
    candles_path: Path,
) -> TradeCandleParityReport:
    """Compare verified normalized trades with independent one-minute candles."""
    bundles = verified_archive_bundles(config)
    candles = _load_candles(candles_path, config)
    trades = _load_trade_bars(bundles)
    joined = trades.join(candles, how="outer")
    flags = _parity_flags(joined)
    return _build_report(
        config,
        candles_path,
        bundles,
        joined,
        flags,
    )


def reconstruct_trade_candle_continuity(
    config: OxaArchiveAuditConfig,
    candles_path: Path,
) -> tuple[pd.DataFrame, TradeCandleReconstructionReport]:
    """Repair missing native candles using only verified public-trade evidence."""
    bundles = verified_archive_bundles(config)
    candles = _load_candles(candles_path, config)
    trades = _load_trade_bars(bundles)
    joined = trades.join(candles, how="outer")
    price_parity = _validate_reconstruction_overlap(joined)
    expected = pd.date_range(config.start, config.end, freq="1min", inclusive="left")
    reconstructed = _reconstruct_minutes(expected, candles, trades)
    source_counts = reconstructed["source"].value_counts()
    overlap = joined["trade_open"].notna() & joined["candle_open"].notna()
    volume_undercoverage = (
        (joined["candle_volume"] - joined["trade_volume"])
        .where(overlap)
        .clip(lower=0.0)
    )
    volume_undercoverage = volume_undercoverage.mask(
        volume_undercoverage <= VOLUME_TOLERANCE,
        0.0,
    )
    count_undercoverage = (
        (joined["candle_trade_count"] - joined["trade_trade_count"])
        .where(overlap)
        .clip(lower=0)
    )
    undercoverage = overlap & (
        (volume_undercoverage > VOLUME_TOLERANCE) | (count_undercoverage > 0)
    )
    report = TradeCandleReconstructionReport(
        symbol=config.symbol,
        window_start_utc=config.start.isoformat(),
        window_end_utc=config.end.isoformat(),
        native_minutes=int(source_counts.get("hl_native_candle", 0)),
        trade_reconstructed_minutes=int(
            source_counts.get("hl_trade_reconstruction", 0)
        ),
        verified_no_trade_minutes=int(source_counts.get("hl_verified_no_trade", 0)),
        native_trade_overlap_minutes=int(overlap.sum()),
        minute_price_extrema_difference_minutes=price_parity.minute_differences,
        complete_five_minute_overlap_bars=price_parity.complete_five_minute_bars,
        five_minute_price_extrema_difference_bars=(
            price_parity.five_minute_differences
        ),
        maximum_minute_high_difference=price_parity.maximum_minute_high_difference,
        maximum_minute_low_difference=price_parity.maximum_minute_low_difference,
        execution_undercoverage_minutes=int(undercoverage.sum()),
        maximum_volume_undercoverage=_max_float(volume_undercoverage),
        maximum_trade_count_undercoverage=_max_int(count_undercoverage),
        candle_path=str(candles_path.resolve()),
        candle_sha256=_sha256(candles_path),
        trade_manifest_fingerprint=_manifest_fingerprint(config, bundles),
    )
    return reconstructed, report


def store_reconstructed_trade_candles(
    config: OxaArchiveAuditConfig,
    candles_path: Path,
    output_directory: Path,
) -> tuple[Path, TradeCandleReconstructionReport]:
    """Publish one immutable, source-bound reconstructed candle bundle."""
    frame, report = reconstruct_trade_candle_continuity(config, candles_path)

    def write_bundle(staging: Path) -> None:
        output = staging / "candles.parquet"
        frame.to_parquet(output, index=False)
        manifest = {
            "schema": "hyperliquid_trade_candle_reconstruction_v1",
            "complete": True,
            "execution_authority": "none",
            "symbol": config.symbol,
            "window_start_utc": config.start.isoformat(),
            "window_end_utc": config.end.isoformat(),
            "input_candle": file_evidence(candles_path),
            "trade_manifest_fingerprint": report.trade_manifest_fingerprint,
            "reconstruction": report.to_dict(),
            "files": {"candles.parquet": file_evidence(output)},
        }
        write_json(staging / "manifest.json", manifest)

    publish_immutable_directory(output_directory, write_bundle)
    return output_directory / "candles.parquet", report


def _validate_reconstruction_overlap(
    joined: pd.DataFrame,
) -> _ReconstructionPriceParity:
    parity, first_five_minute_difference = _reconstruction_price_parity(joined)
    if first_five_minute_difference is not None:
        raise ValueError(
            f"trade/candle 5m price-extrema mismatch at {first_five_minute_difference}"
        )
    _validate_traded_candle_coverage(joined)
    return parity


def _reconstruction_price_parity(
    joined: pd.DataFrame,
) -> tuple[_ReconstructionPriceParity, str | None]:
    flags = _parity_flags(joined)
    high_difference = (joined["trade_high"] - joined["candle_high"]).abs()
    low_difference = (joined["trade_low"] - joined["candle_low"]).abs()
    minute_difference = flags["both"] & ~(flags["high"] & flags["low"])
    overlap = joined.loc[flags["both"]].copy()
    overlap["overlap_minute"] = 1
    grouped = overlap.resample("5min").agg(
        overlap_minutes=("overlap_minute", "sum"),
        trade_high=("trade_high", "max"),
        trade_low=("trade_low", "min"),
        candle_high=("candle_high", "max"),
        candle_low=("candle_low", "min"),
    )
    complete = grouped["overlap_minutes"].eq(5)
    five_difference = complete & (
        (grouped["trade_high"] - grouped["candle_high"]).abs().gt(PRICE_TOLERANCE)
        | (grouped["trade_low"] - grouped["candle_low"]).abs().gt(PRICE_TOLERANCE)
    )
    first = (
        None
        if not five_difference.any()
        else pd.Timestamp(grouped.index[five_difference][0]).isoformat()
    )
    return (
        _ReconstructionPriceParity(
            minute_differences=int(minute_difference.sum()),
            complete_five_minute_bars=int(complete.sum()),
            five_minute_differences=int(five_difference.sum()),
            maximum_minute_high_difference=_max_float(high_difference),
            maximum_minute_low_difference=_max_float(low_difference),
        ),
        first,
    )


def _validate_traded_candle_coverage(joined: pd.DataFrame) -> None:
    candle_without_trade = joined["candle_open"].notna() & joined["trade_open"].isna()
    traded_candle = (joined["candle_volume"].fillna(0.0) > VOLUME_TOLERANCE) | (
        joined["candle_trade_count"].fillna(0) > 0
    )
    missing = candle_without_trade & traded_candle
    if missing.any():
        first = pd.Timestamp(joined.index[missing][0]).isoformat()
        raise ValueError(f"trade archive is incomplete at candle minute {first}")


def _reconstruct_minutes(
    expected: pd.DatetimeIndex,
    candles: pd.DataFrame,
    trades: pd.DataFrame,
) -> pd.DataFrame:
    native = candles.reindex(expected)
    tape = trades.reindex(expected)
    native_present = native["candle_open"].notna()
    trade_present = tape["trade_open"].notna()
    output = pd.DataFrame(index=expected)
    for name in ("open", "high", "low", "close"):
        output[name] = native[f"candle_{name}"].combine_first(tape[f"trade_{name}"])
    carry = output["close"].ffill()
    no_observation = ~native_present & ~trade_present
    for name in ("open", "high", "low", "close"):
        output.loc[no_observation, name] = carry.loc[no_observation]
    if output[["open", "high", "low", "close"]].isna().any(axis=None):
        raise ValueError("cannot reconstruct a leading minute without venue evidence")
    output["volume"] = native["candle_volume"].combine_first(tape["trade_volume"])
    output["trade_count"] = native["candle_trade_count"].combine_first(
        tape["trade_trade_count"]
    )
    output.loc[no_observation, ["volume", "trade_count"]] = 0.0
    output["source"] = "hl_verified_no_trade"
    output.loc[trade_present & ~native_present, "source"] = "hl_trade_reconstruction"
    output.loc[native_present, "source"] = "hl_native_candle"
    output.index.name = "timestamp"
    return output.reset_index()


def _load_candles(
    path: Path,
    config: OxaArchiveAuditConfig,
) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"candle evidence is missing: {path}")
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume", "trade_count"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"candle evidence missing columns: {sorted(missing)}")
    index = pd.DatetimeIndex(pd.to_datetime(frame.pop("timestamp"), utc=True))
    frame.index = index
    frame = frame[(frame.index >= config.start) & (frame.index < config.end)]
    if frame.empty or not frame.index.is_unique:
        raise ValueError("candle evidence is empty or has duplicate minutes")
    selected = frame[["open", "high", "low", "close", "volume", "trade_count"]]
    return selected.sort_index().add_prefix("candle_")


def _load_trade_bars(
    bundles: tuple[OxaArchiveBundle, ...],
) -> pd.DataFrame:
    evidence = [
        _bundle_trade_evidence(bundle.trade_path)
        for bundle in bundles
        if bundle.trade_path is not None
    ]
    if not evidence:
        return empty_trade_bars()
    bars = pd.concat([item[0] for item in evidence]).sort_index()
    if bars.index.is_unique:
        return bars
    boundaries = pd.concat([item[1] for item in evidence], ignore_index=True)
    return _merge_partition_minutes(bars, boundaries)


def _bundle_trade_evidence(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return minute bars plus raw rows capable of crossing an hourly edge."""
    trades = load_trade_jsonl(path)
    minute = pd.to_datetime(trades["ts_ms"], unit="ms", utc=True).dt.floor("min")
    boundary_minutes = {minute.min(), minute.max()}
    boundary_rows = trades.loc[minute.isin(boundary_minutes)]
    return trade_rows_to_minute_bars(trades), boundary_rows


def _merge_partition_minutes(
    bars: pd.DataFrame,
    boundary_rows: pd.DataFrame,
) -> pd.DataFrame:
    """Rebuild minutes spanning adjacent bundles from deduplicated raw prints."""
    duplicate_minutes = bars.index[bars.index.duplicated(keep=False)].unique()
    boundary_minute = pd.to_datetime(
        boundary_rows["ts_ms"], unit="ms", utc=True
    ).dt.floor("min")
    selected = boundary_rows.loc[boundary_minute.isin(duplicate_minutes)]
    replacement = trade_rows_to_minute_bars(_deduplicate_trade_rows(selected))
    if set(replacement.index) != set(duplicate_minutes):
        raise ValueError("trade bundle overlap is not confined to partition boundaries")
    unique = bars.loc[~bars.index.isin(duplicate_minutes)]
    return pd.concat([unique, replacement]).sort_index()


def _deduplicate_trade_rows(trades: pd.DataFrame) -> pd.DataFrame:
    """Collapse identical cross-partition prints and reject ID conflicts."""
    repeated = trades.loc[trades.duplicated("trade_id", keep=False)]
    if repeated.empty:
        return trades
    signature = ["ts_ms", "aggressor_side", "price", "size"]
    disagreements = (
        repeated.groupby("trade_id", sort=False)[signature]
        .nunique(dropna=False)
        .gt(1)
        .any(axis=1)
    )
    if disagreements.any():
        first = disagreements.index[disagreements][0]
        raise ValueError(f"trade ID {first} has inconsistent cross-partition rows")
    return trades.drop_duplicates("trade_id", keep="first")


def _parity_flags(joined: pd.DataFrame) -> dict[str, pd.Series]:
    both = joined["trade_open"].notna() & joined["candle_open"].notna()
    flags = {
        name: both
        & ((joined[f"trade_{name}"] - joined[f"candle_{name}"]).abs() <= tolerance)
        for name, tolerance in (
            ("open", PRICE_TOLERANCE),
            ("high", PRICE_TOLERANCE),
            ("low", PRICE_TOLERANCE),
            ("close", PRICE_TOLERANCE),
            ("volume", VOLUME_TOLERANCE),
        )
    }
    flags["count"] = both & (
        joined["trade_trade_count"] == joined["candle_trade_count"]
    )
    flags["both"] = both
    return flags


def _build_report(
    config: OxaArchiveAuditConfig,
    candles_path: Path,
    bundles: tuple[OxaArchiveBundle, ...],
    joined: pd.DataFrame,
    flags: dict[str, pd.Series],
) -> TradeCandleParityReport:
    execution = _all(flags, ("high", "low", "volume", "count"))
    exact = execution & flags["open"] & flags["close"]
    ordering = execution & ~(flags["open"] & flags["close"])
    candle_present = joined["candle_open"].notna()
    trade_present = joined["trade_open"].notna()
    degraded = candle_present & ~execution
    volume_delta = (joined["trade_volume"] - joined["candle_volume"]).abs()
    count_delta = (joined["trade_trade_count"] - joined["candle_trade_count"]).abs()
    candle_sha = _sha256(candles_path)
    return TradeCandleParityReport(
        config.symbol,
        config.start.isoformat(),
        config.end.isoformat(),
        int(candle_present.sum()),
        int(trade_present.sum()),
        int(flags["both"].sum()),
        int(exact.sum()),
        int(execution.sum()),
        _timestamps(joined.index[ordering]),
        _timestamps(joined.index[degraded]),
        int((candle_present & ~trade_present).sum()),
        int((trade_present & ~candle_present).sum()),
        _max_float(volume_delta),
        _max_int(count_delta),
        str(candles_path.resolve()),
        candle_sha,
        _manifest_fingerprint(config, bundles),
    )


def _all(flags: dict[str, pd.Series], names: tuple[str, ...]) -> pd.Series:
    result = flags[names[0]].copy()
    for name in names[1:]:
        result &= flags[name]
    return result


def _timestamps(index: pd.DatetimeIndex) -> tuple[str, ...]:
    return tuple(timestamp.isoformat() for timestamp in index)


def _max_float(values: pd.Series) -> float:
    observed = values.dropna()
    return float(observed.max()) if not observed.empty else 0.0


def _max_int(values: pd.Series) -> int:
    observed = values.dropna()
    return int(observed.max()) if not observed.empty else 0


def _sha256(path: Path) -> str:
    value = file_evidence(path).get("sha256")
    if not isinstance(value, str):
        raise ValueError(f"file evidence has invalid SHA-256: {path}")
    return value


def _manifest_fingerprint(
    config: OxaArchiveAuditConfig,
    bundles: tuple[OxaArchiveBundle, ...],
) -> str:
    digests = [_sha256(_trade_manifest_path(config, bundle)) for bundle in bundles]
    encoded = json.dumps(digests, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _trade_manifest_path(
    config: OxaArchiveAuditConfig,
    bundle: OxaArchiveBundle,
) -> Path:
    request = OxaTradeRequest(
        config.symbol,
        bundle.start,
        bundle.end,
        1000,
        500,
        30.0,
    )
    return trade_output_directory(config.data_root, request) / "manifest.json"


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
