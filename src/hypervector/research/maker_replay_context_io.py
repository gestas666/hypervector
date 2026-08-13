"""Checksum-verified replay-context loading and coverage evidence."""

from __future__ import annotations

from collections.abc import Sequence
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import verify_file_evidence
from hypervector.research.maker_replay_context import MakerReplayContext


def load_verified_replay_context(
    prices_path: Path | str,
    funding_path: Path | str,
) -> MakerReplayContext:
    """Load context only after manifest, checksum, and bound verification."""
    price_file = Path(prices_path)
    funding_file = Path(funding_path)
    price_manifest = _verified_manifest(price_file, "0xarchive_hyperliquid_prices")
    funding_manifest = _verified_manifest(funding_file, "hl_funding_history")
    _matching_bounds(price_manifest, funding_manifest)
    return MakerReplayContext.from_parquet(str(price_file), str(funding_file))


def load_verified_replay_context_parts(
    parts: Sequence[tuple[Path | str, Path | str]],
) -> MakerReplayContext:
    """Load contiguous verified context bundles as one causal chronology."""
    if not parts:
        raise ValueError("replay context parts must not be empty")
    price_frames: list[pd.DataFrame] = []
    funding_frames: list[pd.DataFrame] = []
    previous_end: pd.Timestamp | None = None
    for price_path, funding_path in parts:
        price_file = Path(price_path)
        funding_file = Path(funding_path)
        price_manifest = _verified_manifest(price_file, "0xarchive_hyperliquid_prices")
        funding_manifest = _verified_manifest(funding_file, "hl_funding_history")
        _matching_bounds(price_manifest, funding_manifest)
        start, end = _manifest_bounds(price_manifest)
        if previous_end is not None and start != previous_end:
            raise ValueError("replay context parts are not contiguous")
        context = MakerReplayContext.from_parquet(str(price_file), str(funding_file))
        price_frames.append(context.prices)
        funding_frames.append(context.funding)
        previous_end = end
    return MakerReplayContext(
        pd.concat(price_frames, ignore_index=True),
        pd.concat(funding_frames, ignore_index=True),
    )


def context_coverage_report(context: MakerReplayContext) -> dict[str, object]:
    """Return causal price/funding coverage metrics for a replay artifact."""
    prices = context.prices
    funding = context.funding
    gaps = prices["ts_ms"].diff().dropna() / 1000.0
    funding_gaps = funding["event_ts_ms"].diff().dropna() / 3_600_000.0
    gap_start, gap_end = _maximum_price_gap_bounds(prices, gaps)
    return {
        "checksums_verified": True,
        "price_rows": len(prices),
        "first_price_utc": _iso_ms(prices["ts_ms"].min()),
        "last_price_utc": _iso_ms(prices["ts_ms"].max()),
        "maximum_price_gap_seconds": float(gaps.max()) if len(gaps) else 0.0,
        "maximum_price_gap_start_utc": gap_start,
        "maximum_price_gap_end_utc": gap_end,
        "price_gaps_over_120_seconds": int((gaps > 120.0).sum()),
        "funding_rows": len(funding),
        "first_funding_utc": _iso_ms(funding["event_ts_ms"].min()),
        "last_funding_utc": _iso_ms(funding["event_ts_ms"].max()),
        "maximum_funding_gap_hours": (
            float(funding_gaps.max()) if len(funding_gaps) else 0.0
        ),
    }


def _maximum_price_gap_bounds(
    prices: pd.DataFrame,
    gaps: pd.Series,
) -> tuple[str | None, str | None]:
    if gaps.empty:
        return None, None
    end_position = int(gaps.idxmax())
    start_ms = prices.at[end_position - 1, "ts_ms"]
    end_ms = prices.at[end_position, "ts_ms"]
    return _iso_ms(start_ms), _iso_ms(end_ms)


def _verified_manifest(path: Path, expected_source: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"replay context file is missing: {path}")
    manifest_path = path.parent / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"replay context manifest is missing: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"replay context manifest must be an object: {manifest_path}")
    if payload.get("source") != expected_source or payload.get("complete") is not True:
        raise ValueError(f"replay context identity is invalid: {manifest_path}")
    files = payload.get("files")
    if not isinstance(files, dict) or path.name not in files:
        raise ValueError(f"replay context file is undeclared: {path}")
    verify_file_evidence(path.parent, files)
    return payload


def _matching_bounds(prices: dict[str, object], funding: dict[str, object]) -> None:
    for field in ("requested_start", "requested_end"):
        left, right = prices.get(field), funding.get(field)
        if not isinstance(left, str) or not isinstance(right, str):
            raise ValueError(f"replay context manifests require {field}")
        if pd.Timestamp(left) != pd.Timestamp(right):
            raise ValueError(f"replay context manifests disagree on {field}")


def _manifest_bounds(manifest: dict[str, object]) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(manifest["requested_start"])
    end = pd.Timestamp(manifest["requested_end"])
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("replay context manifest bounds are invalid")
    return start.tz_convert("UTC"), end.tz_convert("UTC")


def _iso_ms(value: object) -> str | None:
    if pd.isna(value):
        return None
    return pd.to_datetime(int(value), unit="ms", utc=True).isoformat()
