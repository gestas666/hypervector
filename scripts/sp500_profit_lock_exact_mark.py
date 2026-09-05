#!/usr/bin/env python3
"""Publish immutable SP500 profit-lock evidence from exact exchange marks."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Final, cast

from hypervector.data.oxa_price_archive import (
    OxaPriceArchive,
    OxaPriceArchiveConfig,
    load_verified_price_archive,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
)
from hypervector.research.cohort_profit_lock_exact_mark import (
    exact_mark_minute_bars,
)
from hypervector.research.cohort_profit_lock_l2_proxy import (
    ProxyMinuteBar,
    build_profit_lock_proxy_report,
)
from hypervector.research.sp500_profit_lock_evidence import (
    SP500_PROFIT_LOCK_SYMBOL,
    assess_sp500_profit_lock,
    load_sp500_profit_lock_lifecycles,
    sp500_profit_lock_selection,
)

_THRESHOLDS_MS: Final = (5_000, 10_000, 15_000, 30_000, 60_000)
_DEFAULT_TRADES = Path(
    "data/logs/research/hip3_v25_lifecycle_bar_diagnostic_20260807.trades.parquet"
)
_DEFAULT_ACQUISITION = Path(
    "docs/research-journal/v53-sp500-spcx-exact-mark-segment-acquisition-result-v1.json"
)


def parse_args() -> argparse.Namespace:
    """Parse the report-only exact-mark command surface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", type=Path, default=_DEFAULT_TRADES)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--acquisition", type=Path, default=_DEFAULT_ACQUISITION)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def run_command(args: argparse.Namespace) -> int:
    """Build one source-verified exact-mark report with no execution authority."""
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"immutable JSON output exists: {output}")
    trades_path = Path(args.trades)
    acquisition_path = Path(args.acquisition)
    source_evidence = {
        "trades": _path_evidence(trades_path),
        "acquisition": _path_evidence(acquisition_path),
    }
    acquisition = _json_object(acquisition_path)
    config = _archive_config(acquisition, Path(args.data_root))
    archive = load_verified_price_archive(config)
    _require_archive_matches(acquisition, archive)
    start_ms, end_ms = _milliseconds(config.start), _milliseconds(config.end)
    lifecycles = load_sp500_profit_lock_lifecycles(
        trades_path, start_ms=start_ms, end_ms=end_ms
    )
    bars = exact_mark_minute_bars(archive.frame)
    report = build_profit_lock_proxy_report(
        lifecycles,
        bars,
        _THRESHOLDS_MS,
        path_source="exact_exchange_mark",
    )
    report["assessment"] = assess_sp500_profit_lock(report)
    report["selection"] = sp500_profit_lock_selection(lifecycles)
    report["data_quality"] = _quality(archive, bars, start_ms, end_ms)
    report["sources"] = {
        **source_evidence,
        "price_archive": _archive_identity(config, archive, bars),
    }
    _require_unchanged(source_evidence, trades_path, acquisition_path)
    write_immutable_json(output, report)
    return 0


def _archive_config(
    acquisition: Mapping[str, object], data_root: Path
) -> OxaPriceArchiveConfig:
    _require_acquisition_contract(acquisition)
    bounds = _mapping(acquisition.get("bounds"), "acquisition bounds")
    start = _timestamp(bounds.get("start_inclusive_utc"), "archive start")
    end = _timestamp(bounds.get("end_exclusive_utc"), "archive end")
    return OxaPriceArchiveConfig(
        SP500_PROFIT_LOCK_SYMBOL,
        start,
        end,
        data_root,
        chunk=timedelta(hours=1),
        maximum_gap=None,
        market_family="hip3",
    )


def _require_acquisition_contract(acquisition: Mapping[str, object]) -> None:
    valid = (
        acquisition.get("schema_version") == 1
        and acquisition.get("status") == "accepted_for_report_only_development_replay"
        and acquisition.get("execution_authority") == "none"
    )
    if not valid:
        raise ValueError("SP500 exact-mark acquisition contract is invalid")


def _require_archive_matches(
    acquisition: Mapping[str, object], archive: OxaPriceArchive
) -> None:
    symbols = _mapping(acquisition.get("symbols"), "acquisition symbols")
    symbol = _mapping(symbols.get(SP500_PROFIT_LOCK_SYMBOL), "SP500 acquisition")
    audit = _mapping(symbol.get("price_audit"), "SP500 price audit")
    expected = {
        "partition_count": archive.partition_count,
        "row_count": archive.row_count,
        "mark_rows": archive.mark_row_count,
        "missing_mark_rows": archive.missing_mark_row_count,
        "empty_partitions": archive.empty_partition_count,
    }
    if any(_integer(audit.get(key), key) != value for key, value in expected.items()):
        raise ValueError(
            "SP500 exact-mark archive does not match its acquisition audit"
        )
    if archive.missing_mark_row_count or archive.empty_partition_count:
        raise ValueError("SP500 exact-mark archive contains incomplete partitions")


def _quality(
    archive: OxaPriceArchive,
    bars: Mapping[int, ProxyMinuteBar],
    start_ms: int,
    end_ms: int,
) -> dict[str, object]:
    return {
        "archive_start_ms": start_ms,
        "archive_end_ms_exclusive": end_ms,
        "price_rows": archive.row_count,
        "mark_rows": archive.mark_row_count,
        "minute_bars": len(bars),
        "maximum_observed_mark_gap_ms": archive.maximum_observed_gap_ms,
        "completeness_thresholds_ms": list(_THRESHOLDS_MS),
        "funding_included": False,
        "additional_exit_slippage_included": False,
    }


def _archive_identity(
    config: OxaPriceArchiveConfig,
    archive: OxaPriceArchive,
    bars: Mapping[int, ProxyMinuteBar],
) -> dict[str, object]:
    payload = [bars[key].__dict__ for key in sorted(bars)]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {
        "symbol": config.symbol,
        "requested_start_utc": config.start.isoformat(),
        "requested_end_utc": config.end.isoformat(),
        "partition_count": archive.partition_count,
        "row_count": archive.row_count,
        "mark_row_count": archive.mark_row_count,
        "selected_minute_bars": len(payload),
        "selected_bars_sha256": hashlib.sha256(encoded).hexdigest(),
        "verification": "every_partition_manifest_and_declared_file",
    }


def _require_unchanged(
    evidence: Mapping[str, object], trades: Path, acquisition: Path
) -> None:
    current = {
        "trades": _path_evidence(trades),
        "acquisition": _path_evidence(acquisition),
    }
    if current != dict(evidence):
        raise RuntimeError("SP500 exact-mark command input changed during evaluation")


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path), **file_evidence(path)}


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("SP500 exact-mark acquisition must be an object")
    return cast(dict[str, object], value)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"SP500 exact-mark {label} must be an object")
    return cast(dict[str, object], value)


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"SP500 exact-mark {label} must be a timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"SP500 exact-mark {label} must be timezone-aware")
    return result


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"SP500 exact-mark {label} must be nonnegative")
    return value


def _milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


def main() -> int:
    """Run the immutable report-only exact-mark command."""
    return run_command(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
