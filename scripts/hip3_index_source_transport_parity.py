#!/usr/bin/env python3
"""Publish an exact report-only v51 index source-transport comparison."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys
from typing import NamedTuple, cast

import pandas as pd

from hypervector.data.book_align import load_l2_jsonl
from hypervector.data.hip3_public_candles import Hip3PublicCandleSource
from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    OxaArchiveBundle,
    audit_oxa_archive,
    verified_archive_bundles,
)
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.data.oxa_trades import load_trade_jsonl
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_index_source_transport_parity import (
    Hip3IndexSourceParityConfig,
    build_hip3_index_source_transport_parity,
)

Record = dict[str, object]


class _LoadedSources(NamedTuple):
    """One frozen report-only input snapshot and its recheck contract."""

    config: Hip3IndexSourceParityConfig
    trades: pd.DataFrame
    archive_books: pd.DataFrame
    venue_candles: pd.DataFrame
    rest_rows: list[Record]
    observer_rows: list[Record]
    evidence: Record
    exact_files: tuple[tuple[Path, Record], ...]
    prefixes: tuple[tuple[Path, Record], ...]


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit report-only comparison parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--archive-audit", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--observer", type=Path, required=True)
    parser.add_argument("--rest-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(args: argparse.Namespace) -> Record:
    """Reconcile exact inputs and publish one immutable authority-none report."""
    sources = _load_sources(args)
    report = build_hip3_index_source_transport_parity(
        trades=sources.trades,
        archive_books=sources.archive_books,
        venue_candles=sources.venue_candles,
        rest_book_rows=sources.rest_rows,
        observer_rows=sources.observer_rows,
        config=sources.config,
    )
    report["input_evidence"] = sources.evidence
    report["generator_identity"] = _generator_identity()
    _require_unchanged_sources(sources)
    write_immutable_json(Path(args.output), report)
    return report


def _load_sources(args: argparse.Namespace) -> _LoadedSources:
    audit_path, journal_path = Path(args.archive_audit), Path(args.journal)
    observer_path, rest_path = Path(args.observer), Path(args.rest_ledger)
    audit = _json_object(audit_path, "archive audit")
    journal = _json_object(journal_path, "research journal")
    config = _config_from_evidence(journal, audit, str(args.symbol))
    audit_config = _audit_config(audit, Path(args.data_root), config.symbol)
    current_audit = _json_safe(audit_oxa_archive(audit_config).to_dict())
    if current_audit != audit:
        raise ValueError("archive audit differs from current verified bundles")
    bundles = verified_archive_bundles(audit_config)
    books, trades = _archive_frames(bundles)
    observer_rows, observer_evidence = _read_jsonl_prefix(observer_path, "observer")
    rest_rows, rest_evidence = _read_jsonl_prefix(rest_path, "REST ledger")
    candles = _completed_candles(config)
    exact_paths = _exact_paths(audit_path, journal_path, bundles)
    exact_files = tuple((path, file_evidence(path)) for path in exact_paths)
    evidence = _input_evidence(
        exact_files, observer_evidence, rest_evidence, current_audit, candles
    )
    return _LoadedSources(
        config,
        trades,
        books,
        candles,
        rest_rows,
        observer_rows,
        evidence,
        exact_files,
        ((observer_path, observer_evidence), (rest_path, rest_evidence)),
    )


def _audit_config(
    audit: Mapping[str, object], data_root: Path, symbol: str
) -> OxaArchiveAuditConfig:
    valid = (
        audit.get("complete") is True
        and audit.get("book_only") is False
        and audit.get("market_family") == "hip3"
        and audit.get("symbol") == symbol
        and _integer(audit, "chunk_seconds") == 3_600
    )
    if not valid:
        raise ValueError("source parity requires a complete paired HIP-3 audit")
    return OxaArchiveAuditConfig(
        symbol,
        _datetime(audit, "requested_start_utc"),
        _datetime(audit, "requested_end_utc"),
        data_root,
        chunk=timedelta(hours=1),
        depth=20,
        market_family="hip3",
    )


def _config_from_evidence(
    journal: Mapping[str, object], audit: Mapping[str, object], symbol: str
) -> Hip3IndexSourceParityConfig:
    valid = (
        journal.get("schema_version") == "v51_index_source_parity_forward_v1"
        and journal.get("mode") == "report_only"
        and journal.get("execution_authority") == "none"
        and journal.get("automatic_promotion") is False
        and journal.get("runtime_strategy_changed") is False
    )
    if not valid:
        raise ValueError("v51 source parity journal contract is invalid")
    raw = _mapping(journal, "frozen_signal_contract")
    provider = _text(raw, "provider_id")
    routes = _text_list(journal.get("routes"), "routes")
    profiles = _mapping(raw, "profile_ids")
    if f"{provider}|{symbol}" not in routes or symbol not in profiles:
        raise ValueError("requested route is absent from the frozen journal")
    if raw.get("timeframe") != "15m":
        raise ValueError("v51 source parity route must use completed 15m bars")
    breakout = Hip3BreakoutPressureConfig(
        _integer(raw, "breakout_lookback_bars"),
        _integer(raw, "fast_ema"),
        _integer(raw, "slow_ema"),
        _number(raw, "minimum_abs_imbalance"),
        _number(raw, "signal_maximum_stop_bps"),
    )
    start = _datetime(audit, "requested_start_utc")
    end = _datetime(audit, "requested_end_utc")
    return Hip3IndexSourceParityConfig(
        symbol,
        provider,
        _text(profiles, symbol),
        int(start.timestamp() * 1_000),
        int(end.timestamp() * 1_000),
        breakout,
    )


def _archive_frames(
    bundles: tuple[OxaArchiveBundle, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    books = [load_l2_jsonl(bundle.book_path) for bundle in bundles if bundle.book_path]
    trades = [
        load_trade_jsonl(bundle.trade_path) for bundle in bundles if bundle.trade_path
    ]
    if not books or not trades:
        raise ValueError("source parity archive has no paired evidence")
    book_frame = pd.concat(books, ignore_index=True)[["ts_ms", "obi_10"]]
    trade_frame = pd.concat(trades, ignore_index=True)
    _require_unique(book_frame, "ts_ms", "archive books")
    _require_unique(trade_frame, "trade_id", "archive trades")
    return book_frame.sort_values("ts_ms"), trade_frame.sort_values(
        ["ts_ms", "trade_id"]
    )


def _completed_candles(config: Hip3IndexSourceParityConfig) -> pd.DataFrame:
    observed_at = config.end_ms + 15_000
    frame = Hip3PublicCandleSource().completed_candles(
        symbol=config.symbol,
        start_ms=config.start_ms,
        end_ms=config.end_ms,
        observed_at_ms=observed_at,
    )
    timestamp = pd.to_datetime(frame["timestamp"], utc=True)
    selected = frame.loc[
        timestamp.ge(pd.to_datetime(config.start_ms, unit="ms", utc=True))
        & timestamp.lt(pd.to_datetime(config.end_ms, unit="ms", utc=True)),
        ["timestamp", "open", "high", "low", "close"],
    ].copy()
    return selected.sort_values("timestamp", kind="stable").reset_index(drop=True)


def _exact_paths(
    audit: Path, journal: Path, bundles: tuple[OxaArchiveBundle, ...]
) -> tuple[Path, ...]:
    paths = [audit, journal]
    for bundle in bundles:
        for data in (bundle.book_path, bundle.trade_path):
            if data is not None:
                paths.extend((data.parent / "manifest.json", data))
    if len(paths) != len(set(paths)):
        raise ValueError("source parity exact input paths are not distinct")
    return tuple(paths)


def _input_evidence(
    exact: tuple[tuple[Path, Record], ...],
    observer: Record,
    rest: Record,
    audit: Record,
    candles: pd.DataFrame,
) -> Record:
    return {
        "archive_audit": audit,
        "exact_files": [
            {"path": str(path.resolve()), **evidence} for path, evidence in exact
        ],
        "observer_prefix": observer,
        "rest_ledger_prefix": rest,
        "venue_candles": _frame_evidence(candles),
    }


def _read_jsonl_prefix(path: Path, label: str) -> tuple[list[Record], Record]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    content = path.read_bytes()
    if not content or not content.endswith(b"\n"):
        raise ValueError(f"{label} prefix is empty or incomplete")
    rows: list[Record] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{label} row {line_number} must be an object")
        rows.append(cast(Record, value))
    return rows, {
        "path": str(path.resolve()),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "rows": len(rows),
    }


def _require_unchanged_sources(sources: _LoadedSources) -> None:
    for path, expected in sources.exact_files:
        if file_evidence(path) != expected:
            raise ValueError(f"exact source changed during comparison: {path}")
    for path, expected in sources.prefixes:
        _require_prefix_unchanged(path, expected)


def _require_prefix_unchanged(path: Path, evidence: Mapping[str, object]) -> None:
    size = _integer(evidence, "bytes")
    with path.open("rb") as handle:
        prefix = handle.read(size)
    if len(prefix) != size or hashlib.sha256(prefix).hexdigest() != evidence.get(
        "sha256"
    ):
        raise ValueError(f"consumed JSONL prefix changed during comparison: {path}")


def _frame_evidence(frame: pd.DataFrame) -> Record:
    rendered = frame.to_csv(index=False, lineterminator="\n").encode()
    return {
        "rows": len(frame),
        "bytes": len(rendered),
        "sha256": hashlib.sha256(rendered).hexdigest(),
    }


def _generator_identity() -> Record:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/hip3_index_source_transport_parity.py",
        root / "src/hypervector/research/hip3_index_rest_ledger_parity.py",
        root / "src/hypervector/research/hip3_breakout_pressure_signals.py",
        root / "src/hypervector/data/oxa_archive_audit.py",
        root / "src/hypervector/data/book_align.py",
        root / "src/hypervector/data/oxa_trades.py",
        root / "src/hypervector/data/hip3_public_candles.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _require_unique(frame: pd.DataFrame, key: str, label: str) -> None:
    if frame.empty or frame[key].duplicated().any():
        raise ValueError(f"{label} must be nonempty with unique {key}")


def _json_object(path: Path, label: str) -> Record:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(Record, value)


def _json_safe(value: Record) -> Record:
    return cast(Record, json.loads(json.dumps(value)))


def _mapping(value: Mapping[str, object], key: str) -> Record:
    selected = value.get(key)
    if not isinstance(selected, dict):
        raise ValueError(f"source parity evidence missing object {key}")
    return cast(Record, selected)


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"source parity {label} must be a nonempty array")
    output = [item for item in value if isinstance(item, str) and item.strip()]
    if len(output) != len(value) or len(set(output)) != len(output):
        raise ValueError(f"source parity {label} is invalid")
    return output


def _datetime(value: Mapping[str, object], key: str) -> datetime:
    selected = _text(value, key)
    parsed = datetime.fromisoformat(selected.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError(f"source parity {key} must include UTC offset")
    return parsed


def _integer(value: Mapping[str, object], key: str) -> int:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise ValueError(f"source parity {key} must be an integer")
    return selected


def _number(value: Mapping[str, object], key: str) -> float:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, (int, float)):
        raise ValueError(f"source parity {key} must be numeric")
    return float(selected)


def _text(value: Mapping[str, object], key: str) -> str:
    selected = value.get(key)
    if not isinstance(selected, str) or not selected.strip():
        raise ValueError(f"source parity {key} must be nonempty text")
    return selected


def main(argv: Sequence[str] | None = None) -> int:
    """Run the comparison and print only its report-only status."""
    args = build_parser().parse_args(argv)
    try:
        report = run_command(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(Path(args.output).resolve()),
                "coverage": report["coverage"],
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
