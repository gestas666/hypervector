#!/usr/bin/env python3
"""Reconcile one HYPE-native depth path with exact funding evidence."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.hl_funding_evidence import read_complete_hl_funding_evidence
from hypervector.data.oxa_price_archive import (
    OxaPriceArchive,
    OxaPriceArchiveConfig,
    load_verified_price_archive,
)
from hypervector.data.oxa_prices import OxaPriceRequest, price_output_directory
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hype_native_path_funding import (
    reconcile_hype_native_path_funding,
)

_SYMBOL = "HYPE"
_DEFAULT_ORACLE_STALENESS_MS = 120_000
_GENERATOR_PATHS = (
    Path(__file__).resolve(),
    Path("src/hypervector/research/hype_native_path_funding.py").resolve(),
    Path("src/hypervector/research/oracle_price_series.py").resolve(),
    Path("src/hypervector/data/hl_funding_evidence.py").resolve(),
    Path("src/hypervector/data/oxa_price_archive.py").resolve(),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable reconciliation command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path-report", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--price-start", type=_utc_datetime, required=True)
    parser.add_argument("--price-end", type=_utc_datetime, required=True)
    parser.add_argument(
        "--maximum-oracle-staleness-ms",
        type=int,
        default=_DEFAULT_ORACLE_STALENESS_MS,
    )
    exit_basis = parser.add_mutually_exclusive_group()
    exit_basis.add_argument("--horizon-minutes", type=int, default=480)
    exit_basis.add_argument("--resolved-path-exit", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Verify all inputs, reconcile funding, and return an immutable payload."""
    input_before = _input_evidence(args)
    generator_before = _generator_evidence()
    path = _path_report(args.path_report)
    funding = read_complete_hl_funding_evidence(args.funding, _SYMBOL)
    prices = load_verified_price_archive(_price_config(args))
    report = reconcile_hype_native_path_funding(
        path,
        funding,
        prices.frame.loc[:, ["ts_ms", "oracle_price"]],
        maximum_oracle_staleness_ms=args.maximum_oracle_staleness_ms,
        horizon_minutes=None if args.resolved_path_exit else args.horizon_minutes,
    )
    if input_before != _input_evidence(args):
        raise RuntimeError("HYPE path funding inputs changed during reconciliation")
    if generator_before != _generator_evidence():
        raise RuntimeError("HYPE path funding generator changed during reconciliation")
    report["evidence"] = input_before | {
        "funding_manifest": funding.evidence,
        "price_archive": _price_summary(prices),
        "generator_files": generator_before,
    }
    return report


def _price_config(args: argparse.Namespace) -> OxaPriceArchiveConfig:
    return OxaPriceArchiveConfig(
        symbol=_SYMBOL,
        start=args.price_start,
        end=args.price_end,
        data_root=args.data_root,
        chunk=args.price_end - args.price_start,
        maximum_gap=None,
    )


def _input_evidence(args: argparse.Namespace) -> dict[str, object]:
    price_dir = price_output_directory(
        args.data_root,
        OxaPriceRequest(_SYMBOL, args.price_start, args.price_end),
    )
    return {
        "path_report": _file_record(args.path_report),
        "funding": _file_record(args.funding),
        "funding_manifest_file": _file_record(args.funding.parent / "manifest.json"),
        "prices": _file_record(price_dir / "prices.parquet"),
        "price_manifest_file": _file_record(price_dir / "manifest.json"),
    }


def _path_report(path: Path) -> Mapping[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("HYPE path report must be a mapping")
    return raw


def _price_summary(archive: OxaPriceArchive) -> dict[str, object]:
    return {
        "partition_count": archive.partition_count,
        "row_count": archive.row_count,
        "maximum_observed_gap_ms": archive.maximum_observed_gap_ms,
        "oracle_row_count": archive.oracle_row_count,
        "missing_oracle_row_count": archive.missing_oracle_row_count,
    }


def _generator_evidence() -> list[dict[str, object]]:
    return [_file_record(path) for path in _GENERATOR_PATHS]


def _file_record(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _utc_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("timestamp must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def main(argv: Sequence[str] | None = None) -> int:
    """Publish a funded path report without constructing an exchange client."""
    args = build_parser().parse_args(argv)
    report = run(args)
    write_immutable_json(args.out, report)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "net_pnl_usd_after_funding": report["net_pnl_usd_after_funding"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
