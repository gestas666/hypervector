#!/usr/bin/env python3
"""Publish causal four-asset regime-component attribution evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.regime_component_attribution import (
    AttributionSegment,
    build_component_attribution,
)

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_DEFAULT_HORIZONS = (5, 15, 30, 60)


def parse_bar_mappings(values: list[str]) -> dict[str, Path]:
    """Parse and validate exactly one candle path per supported symbol."""
    mappings: dict[str, Path] = {}
    for value in values:
        symbol, separator, raw_path = value.partition("=")
        normalized = symbol.strip().upper()
        if not separator or not normalized or not raw_path.strip():
            raise ValueError("bar mappings must use SYMBOL=/path/to/file.parquet")
        if normalized in mappings:
            raise ValueError(f"duplicate bar mapping for {normalized}")
        mappings[normalized] = Path(raw_path).expanduser()
    if set(mappings) != set(_SYMBOLS):
        raise ValueError("bar mappings must contain exactly BTC, ETH, SOL, HYPE")
    return {symbol: mappings[symbol] for symbol in _SYMBOLS}


def build_segments(
    development_start: str,
    development_end: str,
    validation_end: str,
    pseudo_holdout_end: str,
) -> tuple[AttributionSegment, ...]:
    """Build three strictly ordered half-open UTC evidence segments."""
    boundaries = tuple(
        _utc_timestamp(value)
        for value in (
            development_start,
            development_end,
            validation_end,
            pseudo_holdout_end,
        )
    )
    pairs = zip(boundaries, boundaries[1:], strict=False)
    if any(right <= left for left, right in pairs):
        raise ValueError("attribution boundaries must be strictly ordered")
    start, development, validation, holdout = boundaries
    return (
        AttributionSegment("development", start, development),
        AttributionSegment("validation", development, validation),
        AttributionSegment("pseudo_holdout", validation, holdout),
    )


def load_bars(path: Path) -> pd.DataFrame:
    """Load one complete UTC Hyperliquid minute-candle evidence file."""
    if not path.is_file():
        raise FileNotFoundError(f"Hyperliquid bar evidence is missing: {path}")
    bars = pd.read_parquet(path)
    if "timestamp" not in bars:
        raise ValueError(f"Hyperliquid bar evidence requires timestamp: {path}")
    index = pd.DatetimeIndex(pd.to_datetime(bars.pop("timestamp"), utc=True))
    bars.index = index
    required = {"open", "high", "low", "close", "volume", "source"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"Hyperliquid bar evidence missing columns: {missing}")
    sources = set(bars["source"].astype(str).unique())
    unsupported = sorted(sources.difference({"hl", "hl_gap_fill"}))
    if unsupported:
        raise ValueError(f"unsupported attribution provenance: {unsupported}")
    return bars.loc[:, ["open", "high", "low", "close", "volume", "source"]]


def generate_report(
    bar_paths: dict[str, Path],
    segments: tuple[AttributionSegment, ...],
    horizons: tuple[int, ...],
    gap_quarantine_minutes: int = 0,
) -> dict[str, object]:
    """Generate all asset reports before any artifact is published."""
    assets: dict[str, object] = {}
    for symbol in _SYMBOLS:
        path = bar_paths[symbol]
        bars = load_bars(path)
        report = build_component_attribution(
            bars,
            symbol=symbol,
            segments=segments,
            horizons_minutes=horizons,
            gap_quarantine_minutes=gap_quarantine_minutes,
        )
        assets[symbol] = {**report, "input_evidence": file_evidence(path)}
    return _artifact(assets, segments, horizons, gap_quarantine_minutes)


def run_attribution(
    bar_paths: dict[str, Path],
    segments: tuple[AttributionSegment, ...],
    horizons: tuple[int, ...],
    output: Path,
    gap_quarantine_minutes: int = 0,
) -> dict[str, object]:
    """Generate and atomically publish one immutable attribution artifact."""
    if output.exists():
        raise FileExistsError(f"immutable JSON output exists: {output}")
    report = generate_report(bar_paths, segments, horizons, gap_quarantine_minutes)
    validate_report(report, horizons=horizons)
    write_immutable_json(output, report)
    return report


def validate_report(report: dict[str, object], *, horizons: tuple[int, ...]) -> None:
    """Reject incomplete or authority-bearing attribution artifacts."""
    expected_policy = {
        "mode": "regime_component_attribution_report_only",
        "execution_authority": "none",
        "model_authority": "none",
        "thresholds_selected": False,
        "fills_assumed": False,
        "pnl_claimed": False,
    }
    observed = {key: report.get(key) for key in expected_policy}
    if observed != expected_policy:
        raise ValueError(f"attribution authority contract mismatch: {observed}")
    assets = _object_mapping(report.get("assets"), "attribution assets")
    if set(assets) != set(_SYMBOLS):
        raise ValueError("attribution report must retain all four assets")
    if _contains_key(report, "pooled_ic"):
        raise ValueError("attribution report must not contain pooled IC")
    segments = _object_mapping(report.get("segments"), "attribution segments")
    for symbol in _SYMBOLS:
        _validate_asset_report(assets[symbol], symbol, set(segments), horizons)


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only command surface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", action="append", required=True, metavar="SYMBOL=PATH")
    parser.add_argument("--development-start", required=True)
    parser.add_argument("--development-end", required=True)
    parser.add_argument("--validation-end", required=True)
    parser.add_argument("--pseudo-holdout-end", required=True)
    parser.add_argument("--horizons", default="5,15,30,60")
    parser.add_argument("--gap-quarantine-minutes", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    """Run the immutable four-asset attribution command."""
    args = build_parser().parse_args()
    paths = parse_bar_mappings(args.bars)
    segments = build_segments(
        args.development_start,
        args.development_end,
        args.validation_end,
        args.pseudo_holdout_end,
    )
    horizons = _parse_horizons(args.horizons)
    report = run_attribution(
        paths,
        segments,
        horizons,
        args.output,
        args.gap_quarantine_minutes,
    )
    print(
        f"wrote {args.output} assets={len(report['assets'])} "
        f"horizons={','.join(str(value) for value in horizons)}"
    )


def _utc_timestamp(value: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except ValueError as exc:
        raise ValueError(f"invalid attribution timestamp: {value}") from exc
    if timestamp.tz is None or timestamp.utcoffset() is None:
        raise ValueError("attribution boundaries must be UTC")
    if timestamp.utcoffset().total_seconds() != 0.0:
        raise ValueError("attribution boundaries must be UTC")
    return timestamp.tz_convert("UTC")


def _parse_horizons(value: str) -> tuple[int, ...]:
    try:
        horizons = tuple(int(item) for item in value.split(","))
    except ValueError as exc:
        raise ValueError("horizons must be comma-separated integer minutes") from exc
    if (
        not horizons
        or any(item < 1 for item in horizons)
        or len(set(horizons)) != len(horizons)
    ):
        raise ValueError("horizons must be unique positive integer minutes")
    return horizons


def _artifact(
    assets: dict[str, object],
    segments: tuple[AttributionSegment, ...],
    horizons: tuple[int, ...],
    gap_quarantine_minutes: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "regime_component_attribution_report_only",
        "execution_authority": "none",
        "model_authority": "none",
        "thresholds_selected": False,
        "fills_assumed": False,
        "pnl_claimed": False,
        "gap_quarantine_minutes": gap_quarantine_minutes,
        "horizons_minutes": list(horizons),
        "segments": {
            segment.name: {
                "start": segment.start.isoformat(),
                "end": segment.end.isoformat(),
            }
            for segment in segments
        },
        "assets": assets,
        "limitations": [
            "Historical evidence is descriptive and cannot authorize execution.",
            "Pseudo-holdout is not pristine because prior project research used this era.",
            "Daily ICs and non-overlapping counts do not prove tradable after-cost edge.",
            "Gap-filled decisions and future paths are excluded and counted explicitly.",
            "Gap-filled bars can influence causal rolling features after an excluded path.",
        ],
    }


def _validate_asset_report(
    value: object,
    symbol: str,
    segment_names: set[str],
    horizons: tuple[int, ...],
) -> None:
    asset = _object_mapping(value, f"{symbol} attribution")
    if asset.get("symbol") != symbol:
        raise ValueError(f"{symbol} attribution identity mismatch")
    segments = _object_mapping(asset.get("segments"), f"{symbol} segments")
    if set(segments) != segment_names:
        raise ValueError(f"{symbol} attribution segment coverage is incomplete")
    expected_horizons = {str(horizon) for horizon in horizons}
    for segment_name, segment_value in segments.items():
        segment = _object_mapping(segment_value, f"{symbol} {segment_name}")
        measured = _object_mapping(segment.get("horizons"), "attribution horizons")
        if set(measured) != expected_horizons:
            raise ValueError(f"{symbol} {segment_name} horizon coverage is incomplete")
        for horizon in measured.values():
            _validate_observation_counts(horizon)


def _validate_observation_counts(value: object) -> None:
    report = _object_mapping(value, "attribution horizon")
    counts = _object_mapping(report.get("observations"), "attribution observations")
    names = ("usable", "gap_decision", "gap_label_path", "right_censored")
    total = counts.get("total")
    parts = [counts.get(name) for name in names]
    parts.append(counts.get("gap_feature_quarantine", 0))
    if not isinstance(total, int) or any(not isinstance(part, int) for part in parts):
        raise ValueError("attribution observation counts must be integers")
    if total != sum(part for part in parts if isinstance(part, int)):
        raise ValueError("attribution observation counts do not reconcile")


def _object_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a string-keyed object")
    return value


def _contains_key(value: object, target: str) -> bool:
    if isinstance(value, dict):
        return target in value or any(
            _contains_key(item, target) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(item, target) for item in value)
    return False


if __name__ == "__main__":
    main()
