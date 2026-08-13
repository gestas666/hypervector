#!/usr/bin/env python3
"""Repair prospective HIP-3 recorder gaps with exact 0xArchive paths."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
from typing import NamedTuple, cast

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    audit_oxa_archive,
    verified_archive_bundles,
)
from hypervector.data.oxa_price_archive import (
    OxaPriceArchiveConfig,
    load_verified_price_archive,
)
from hypervector.data.oxa_prices import OxaPriceRequest, price_output_directory
from hypervector.data.oxa_storage import (
    file_evidence,
    open_text_reader,
    write_immutable_json,
)
from hypervector.research.hip3_prospective_path_repair import (
    Hip3ProspectivePathRepairConfig,
    build_hip3_prospective_path_repair,
)


class SupplementalPathEvidence(NamedTuple):
    """Verified replacement timestamps and files protected during publication."""

    mark_timestamps_ms: tuple[int, ...]
    l2_timestamps_ms: tuple[int, ...]
    evidence: dict[str, object]
    protected_files: tuple[Path, ...]


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit report-only repair command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--path-audit", type=Path, required=True)
    parser.add_argument("--archive-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    supplemental: SupplementalPathEvidence | None = None,
) -> dict[str, object]:
    """Publish one immutable repair while guarding every consumed file."""
    base_path = Path(args.path_audit)
    archive_path = Path(args.archive_audit)
    base = _load_json(base_path, "prospective path audit")
    archive = _load_json(archive_path, "0xArchive audit")
    config = _repair_config(str(args.symbol), archive)
    _require_archive_covers_unresolved(base, config)
    path = supplemental or _load_verified_supplemental(
        data_root=Path(args.data_root),
        archive_path=archive_path,
        archive=archive,
        config=config,
    )
    protected = _distinct_paths((base_path, *path.protected_files))
    expected = tuple(file_evidence(value) for value in protected)
    report = build_hip3_prospective_path_repair(
        base_audit=base,
        mark_timestamps_ms=path.mark_timestamps_ms,
        l2_timestamps_ms=path.l2_timestamps_ms,
        archive_evidence=path.evidence,
        config=config,
    )
    report["base_path_audit_evidence"] = _path_evidence(base_path)
    report["generator_identity"] = _generator_identity()
    _require_unchanged_files(protected, expected)
    write_immutable_json(Path(args.output), report)
    return report


def _load_verified_supplemental(
    *,
    data_root: Path,
    archive_path: Path,
    archive: Mapping[str, object],
    config: Hip3ProspectivePathRepairConfig,
) -> SupplementalPathEvidence:
    audit_config = _audit_config(data_root, archive, config.symbol)
    current = _json_safe(audit_oxa_archive(audit_config).to_dict())
    if current != dict(archive):
        raise ValueError("0xArchive audit does not match current verified bundles")
    bundles = verified_archive_bundles(audit_config)
    book_paths = tuple(bundle.book_path for bundle in bundles if bundle.book_path)
    l2_timestamps = _load_book_timestamps(book_paths, config)
    price_config = OxaPriceArchiveConfig(
        config.symbol,
        audit_config.start,
        audit_config.end,
        data_root,
        chunk=audit_config.chunk,
        maximum_gap=None,
        market_family="hip3",
    )
    prices = load_verified_price_archive(price_config)
    marks = tuple(
        int(value)
        for value in prices.frame.loc[prices.frame["mark_price"].notna(), "ts_ms"]
    )
    price_files = _price_files(price_config)
    protected = (archive_path, *book_paths, *price_files)
    evidence = _supplemental_evidence(archive_path, archive, prices, protected)
    return SupplementalPathEvidence(marks, l2_timestamps, evidence, protected)


def _audit_config(
    data_root: Path, archive: Mapping[str, object], symbol: str
) -> OxaArchiveAuditConfig:
    if archive.get("complete") is not True or archive.get("book_only") is not False:
        raise ValueError("supplemental 0xArchive audit must be complete and paired")
    if archive.get("symbol") != symbol or archive.get("market_family") != "hip3":
        raise ValueError("supplemental 0xArchive audit identity is invalid")
    chunk_seconds = _integer(archive, "chunk_seconds")
    return OxaArchiveAuditConfig(
        symbol,
        _datetime(archive, "requested_start_utc"),
        _datetime(archive, "requested_end_utc"),
        data_root,
        chunk=timedelta(seconds=chunk_seconds),
        market_family="hip3",
    )


def _repair_config(
    symbol: str, archive: Mapping[str, object]
) -> Hip3ProspectivePathRepairConfig:
    start = _datetime(archive, "requested_start_utc")
    end = _datetime(archive, "requested_end_utc")
    return Hip3ProspectivePathRepairConfig(
        symbol=symbol,
        start_ms=int(start.timestamp() * 1_000),
        end_ms=int(end.timestamp() * 1_000),
    )


def _require_archive_covers_unresolved(
    base: Mapping[str, object], config: Hip3ProspectivePathRepairConfig
) -> None:
    rows = base.get("bar_diagnostics")
    if not isinstance(rows, list):
        raise ValueError("base path audit bar diagnostics are invalid")
    for row in rows:
        if not isinstance(row, dict) or row.get("resolved") is True:
            continue
        start = _integer(row, "bar_open_ms")
        end = _integer(row, "bar_close_ms")
        if start < config.start_ms or end > config.end_ms:
            raise ValueError("supplemental archive does not cover unresolved bars")


def _load_book_timestamps(
    paths: Sequence[Path], config: Hip3ProspectivePathRepairConfig
) -> tuple[int, ...]:
    timestamps: list[int] = []
    for path in paths:
        with open_text_reader(path) as handle:
            for line in handle:
                row = json.loads(line)
                timestamp = _validated_book_timestamp(row, config)
                if timestamp is not None:
                    timestamps.append(timestamp)
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("supplemental L2 archive contains duplicate timestamps")
    return tuple(sorted(timestamps))


def _validated_book_timestamp(
    row: object, config: Hip3ProspectivePathRepairConfig
) -> int | None:
    if not isinstance(row, dict):
        raise ValueError("supplemental L2 row must be an object")
    if row.get("symbol") != config.symbol:
        raise ValueError("supplemental L2 row symbol is inconsistent")
    if row.get("source") != "0xarchive_hyperliquid_hip3_l2":
        raise ValueError("supplemental L2 row source is invalid")
    timestamp = _integer(row, "ts_exchange_ms")
    if timestamp == config.end_ms:
        return None
    if timestamp < config.start_ms or timestamp > config.end_ms:
        raise ValueError("supplemental L2 row exceeds repair bounds")
    return timestamp


def _price_files(config: OxaPriceArchiveConfig) -> tuple[Path, ...]:
    output: list[Path] = []
    start = config.start
    while start < config.end:
        end = min(start + config.chunk, config.end)
        directory = price_output_directory(
            config.data_root,
            OxaPriceRequest(config.symbol, start, end, market_family="hip3"),
        )
        output.extend((directory / "manifest.json", directory / "prices.parquet"))
        start = end
    return tuple(output)


def _supplemental_evidence(
    archive_path: Path,
    archive: Mapping[str, object],
    prices: object,
    files: Sequence[Path],
) -> dict[str, object]:
    return {
        "complete": True,
        "market_family": "hip3",
        "symbol": archive["symbol"],
        "archive_audit": _path_evidence(archive_path),
        "book_trade_summary": dict(archive),
        "price_rows": int(getattr(prices, "row_count")),
        "mark_rows": int(getattr(prices, "mark_row_count")),
        "missing_mark_rows": int(getattr(prices, "missing_mark_row_count")),
        "protected_files": [_path_evidence(path) for path in files],
    }


def _load_json(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _require_unchanged_files(
    paths: tuple[Path, ...], expected: tuple[dict[str, object], ...]
) -> None:
    observed = tuple(file_evidence(path) for path in paths)
    if observed != expected:
        raise ValueError("path-repair evidence changed during path repair")


def _distinct_paths(paths: Sequence[Path]) -> tuple[Path, ...]:
    resolved = tuple(path.resolve() for path in paths)
    if len(set(resolved)) != len(resolved):
        raise ValueError("path-repair protected files contain duplicates")
    return resolved


def _datetime(value: Mapping[str, object], key: str) -> datetime:
    selected = value.get(key)
    if not isinstance(selected, str):
        raise ValueError(f"path-repair archive {key} must be a timestamp")
    parsed = datetime.fromisoformat(selected.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError(f"path-repair archive {key} must include a UTC offset")
    return parsed


def _integer(value: Mapping[str, object], key: str) -> int:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise ValueError(f"path-repair evidence {key} must be an integer")
    return selected


def _json_safe(value: object) -> object:
    return json.loads(json.dumps(value))


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/hip3_prospective_path_repair.py",
        root / "src/hypervector/research/hip3_prospective_path_audit.py",
        root / "src/hypervector/data/oxa_archive_audit.py",
        root / "src/hypervector/data/oxa_price_archive.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the repair and print a compact authority-free status."""
    args = build_parser().parse_args(argv)
    try:
        report = run_command(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(Path(args.output).resolve()),
                "technical_assessment": report["technical_assessment"],
                "execution_authority": "none",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
