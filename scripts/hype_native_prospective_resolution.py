#!/usr/bin/env python3
"""Resolve closed HYPE-native v54 lifecycles with exact mark and funding data."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd

from hypervector.data.hl_funding_evidence import read_complete_hl_funding_evidence
from hypervector.data.oxa_price_archive import (
    OxaPriceArchive,
    OxaPriceArchiveConfig,
    load_verified_price_archive,
)
from hypervector.data.oxa_prices import OxaPriceRequest, price_output_directory
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hype_native_prospective_resolution import (
    HypeProxyExitUnconfirmedError,
    resolve_hype_native_prospective_lifecycles,
)
from hypervector.research.hip3_shadow_lifecycle_sources import (
    FrozenHip3MarkArchive,
    FrozenHyperliquidL2Archive,
    Hip3MarkSourceProtocol,
    HyperliquidL2SourceProtocol,
)

_SYMBOL = "HYPE"
_GENERATOR_PATHS = tuple(
    Path(value).resolve()
    for value in (
        __file__,
        "src/hypervector/research/hype_native_prospective_resolution.py",
        "src/hypervector/research/hype_funding_events.py",
        "src/hypervector/research/oracle_price_series.py",
        "src/hypervector/data/hl_funding_evidence.py",
        "src/hypervector/data/oxa_price_archive.py",
        "src/hypervector/data/oxa_storage.py",
        "src/hypervector/research/hip3_shadow_lifecycle_sources.py",
        "src/hypervector/data/event_archive.py",
    )
)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded, execution-incapable resolution parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lifecycle-status", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--price-start", type=_utc_datetime, required=True)
    parser.add_argument("--price-end", type=_utc_datetime, required=True)
    parser.add_argument("--maximum-oracle-staleness-ms", type=int, default=120_000)
    parser.add_argument("--maximum-mark-gap-ms", type=int, default=120_000)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run(
    args: argparse.Namespace,
    *,
    mark_source: Hip3MarkSourceProtocol | None = None,
    l2_source: HyperliquidL2SourceProtocol | None = None,
) -> dict[str, object]:
    """Reconcile exact frozen inputs and return an immutable report payload."""
    inputs = _input_evidence(args)
    generator = _generator_evidence()
    status = _status_report(args.lifecycle_status)
    funding = read_complete_hl_funding_evidence(args.funding, _SYMBOL)
    prices = load_verified_price_archive(_price_config(args))
    source = mark_source or FrozenHip3MarkArchive()
    entry_ms, exit_ms = _lifecycle_window(status)
    mark_rows, mark_evidence = source.load(
        data_root=Path(args.data_root),
        symbol=_SYMBOL,
        start_ms=entry_ms,
        end_ms=exit_ms,
    )
    depth_source = l2_source or FrozenHyperliquidL2Archive()
    stop_books, l2_evidence = depth_source.load(
        data_root=Path(args.data_root),
        symbol=_SYMBOL,
        start_ms=entry_ms,
        end_ms=exit_ms,
    )
    marks = _mark_frame(mark_rows)
    try:
        report = resolve_hype_native_prospective_lifecycles(
            status,
            funding,
            prices.frame,
            mark_prices=marks,
            stop_books=stop_books,
            maximum_oracle_staleness_ms=args.maximum_oracle_staleness_ms,
            maximum_mark_gap_ms=args.maximum_mark_gap_ms,
        )
    except HypeProxyExitUnconfirmedError as error:
        report = _technical_rejection_report(status, error)
    if inputs != _input_evidence(args):
        raise RuntimeError("HYPE prospective resolution inputs changed")
    source.require_unchanged(mark_evidence)
    depth_source.require_unchanged(l2_evidence)
    if generator != _generator_evidence():
        raise RuntimeError("HYPE prospective resolution generator changed")
    report["evidence"] = _resolution_evidence(
        inputs, funding.evidence, prices, mark_evidence, l2_evidence, generator
    )
    return report


def _resolution_evidence(
    inputs: Mapping[str, object],
    funding: Mapping[str, object],
    prices: OxaPriceArchive,
    marks: Mapping[str, object],
    books: Mapping[str, object],
    generator: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Return immutable provenance for every resolution input."""
    return dict(inputs) | {
        "funding_bundle": dict(funding),
        "price_archive": _price_summary(prices),
        "local_mark_archive": dict(marks),
        "local_l2_archive": dict(books),
        "generator_files": [dict(row) for row in generator],
    }


def _lifecycle_window(status: Mapping[str, object]) -> tuple[int, int]:
    rows = status.get("lifecycles")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise ValueError("HYPE local marks require exactly one lifecycle")
    entry = rows[0].get("entry_book_time_ms")
    exit_time = rows[0].get("exit_book_time_ms")
    if (
        isinstance(entry, bool)
        or not isinstance(entry, int)
        or isinstance(exit_time, bool)
        or not isinstance(exit_time, int)
        or exit_time <= entry
    ):
        raise ValueError("HYPE local mark lifecycle window is invalid")
    return entry, exit_time


def _mark_frame(rows: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    values = pd.DataFrame(rows)
    required = {"received_ts_ns", "mark_price"}
    missing = required.difference(values.columns)
    if missing:
        raise ValueError(f"HYPE local marks are missing columns: {sorted(missing)}")
    values["ts_ms"] = values["received_ts_ns"].astype("int64") // 1_000_000
    return values.loc[:, ["ts_ms", "received_ts_ns", "mark_price"]].sort_values(
        "received_ts_ns"
    )


def _technical_rejection_report(
    status: Mapping[str, object], error: HypeProxyExitUnconfirmedError
) -> dict[str, object]:
    """Serialize a terminal mark mismatch without claiming resolved economics."""
    identity = status.get("identity")
    rows = status.get("lifecycles")
    if not isinstance(identity, Mapping):
        raise ValueError("HYPE rejection identity must be an object")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise ValueError("HYPE rejection requires exactly one lifecycle")
    lifecycle = rows[0]
    rejected = {
        "decision_time_ms": lifecycle.get("decision_time_ms"),
        "side": lifecycle.get("side"),
        "entry_book_time_ms": lifecycle.get("entry_book_time_ms"),
        "exit_book_time_ms": lifecycle.get("exit_book_time_ms"),
        "exit_reason": lifecycle.get("exit_reason"),
        "net_pnl_usd_after_funding": None,
        "technical_evidence_status": "rejected",
        "technical_rejection_reason": "bbo_proxy_exit_not_confirmed_by_mark",
        **error.mark_evidence,
    }
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_exact_post_close_resolution_report_only",
        "resolution_status": "technical_evidence_rejected",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "funding_source": "hl_funding_history",
            "mark_and_oracle_source": "0xarchive_hyperliquid_prices",
        },
        "identity": dict(identity),
        "lifecycles": [rejected],
        "summary": {"resolved_trades": 0, "technically_rejected_lifecycles": 1},
    }


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
    directory = price_output_directory(
        args.data_root,
        OxaPriceRequest(_SYMBOL, args.price_start, args.price_end),
    )
    return {
        "lifecycle_status": _file_record(args.lifecycle_status),
        "funding": _file_record(args.funding),
        "funding_manifest": _file_record(args.funding.parent / "manifest.json"),
        "prices": _file_record(directory / "prices.parquet"),
        "price_manifest": _file_record(directory / "manifest.json"),
    }


def _status_report(path: Path) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("HYPE lifecycle status must be an object")
    return value


def _price_summary(archive: OxaPriceArchive) -> dict[str, object]:
    return {
        "partition_count": archive.partition_count,
        "row_count": archive.row_count,
        "maximum_observed_gap_ms": archive.maximum_observed_gap_ms,
        "mark_row_count": archive.mark_row_count,
        "missing_mark_row_count": archive.missing_mark_row_count,
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
    """Publish one report-only resolution without creating venue authority."""
    args = build_parser().parse_args(argv)
    report = run(args)
    write_immutable_json(args.out, report)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "execution_authority": "none",
                "summary": report["summary"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
