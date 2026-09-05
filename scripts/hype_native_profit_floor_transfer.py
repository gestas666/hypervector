#!/usr/bin/env python3
"""Publish the bounded native-HYPE mature-profit-floor transfer snapshot."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sys

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.hype_native_profit_floor_sources import (
    PreparedNativeFloorInput,
    prepare_closed_native_floor_input,
    prepare_prospective_native_floor_input,
)
from hypervector.research.hype_native_profit_floor_transfer import (
    build_hype_native_profit_floor_transfer,
)

Record = Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only profit-floor snapshot parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closed-path", type=Path, action="append", required=True)
    parser.add_argument("--closed-funded", type=Path, action="append", required=True)
    parser.add_argument("--lifecycle-status", type=Path, required=True)
    parser.add_argument("--resolution", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--immutable", action="store_true")
    return parser


def run_command(args: argparse.Namespace) -> int:
    """Reconcile exact source prefixes and atomically publish one snapshot."""
    paths = tuple(Path(value) for value in args.closed_path)
    funded = tuple(Path(value) for value in args.closed_funded)
    if len(paths) != len(funded):
        raise ValueError("closed HYPE path and funded artifact counts differ")
    prepared, closed_sources = _closed_inputs(paths, funded)
    status, status_evidence = _read_mapping_with_evidence(Path(args.lifecycle_status))
    resolution, resolution_evidence = _optional_resolution(args.resolution)
    records, ledger_evidence = _prospective_records(status)
    prepared.append(
        prepare_prospective_native_floor_input(status, records, resolution=resolution)
    )
    report = _report(prepared)
    report.update(
        {
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "source_evidence": {
                "closed": closed_sources,
                "prospective_status": status_evidence,
                "prospective_ledger": ledger_evidence,
                "prospective_resolution": resolution_evidence,
                "generator": _generator_evidence(),
            },
        }
    )
    if args.immutable:
        write_immutable_json(Path(args.output), report)
    else:
        write_atomic_json(Path(args.output), report)
    return 0


def _closed_inputs(
    paths: Sequence[Path], funded_paths: Sequence[Path]
) -> tuple[list[PreparedNativeFloorInput], list[dict[str, object]]]:
    prepared: list[PreparedNativeFloorInput] = []
    sources: list[dict[str, object]] = []
    for path_file, funded_file in zip(paths, funded_paths, strict=True):
        path, path_evidence = _read_mapping_with_evidence(path_file)
        funded, funded_evidence = _read_mapping_with_evidence(funded_file)
        evidence = _mapping(path.get("evidence"), "closed path evidence")
        asset, asset_evidence = _slice_records(
            _mapping(evidence.get("asset_ledger"), "asset ledger evidence")
        )
        cohort, cohort_evidence = _slice_records(
            _mapping(evidence.get("cohort_ledger"), "cohort ledger evidence")
        )
        entry = _mapping(path.get("execution_path"), "execution path").get(
            "entry_book_time_ms"
        )
        prepared.append(
            prepare_closed_native_floor_input(
                path,
                funded,
                asset,
                cohort,
                lifecycle_id=f"HYPE:native:{entry}",
            )
        )
        sources.append(
            {
                "path_report": path_evidence,
                "funded_report": funded_evidence,
                "asset_ledger": asset_evidence,
                "cohort_ledger": cohort_evidence,
            }
        )
    return prepared, sources


def _prospective_records(
    status: Record,
) -> tuple[tuple[Record, ...], dict[str, object]]:
    evidence = _mapping(status.get("evidence"), "prospective evidence")
    ledger = _mapping(evidence.get("decision_ledger"), "decision ledger evidence")
    return _prefix_records(ledger)


def _slice_records(evidence: Record) -> tuple[tuple[Record, ...], dict[str, object]]:
    path = Path(_text(evidence.get("path"), "ledger path"))
    start = _integer(evidence.get("source_start_offset"), "ledger start offset")
    length = _integer(evidence.get("bytes"), "ledger bytes")
    expected = _text(evidence.get("sha256"), "ledger sha256")
    with path.open("rb") as stream:
        stream.seek(start)
        raw = stream.read(length)
    observed = _digest(raw)
    if len(raw) != length or observed != expected:
        raise RuntimeError(f"HYPE floor ledger slice changed: {path}")
    return _jsonl_records(raw), {
        "path": str(path),
        "source_start_offset": start,
        "bytes": length,
        "sha256": observed,
    }


def _prefix_records(evidence: Record) -> tuple[tuple[Record, ...], dict[str, object]]:
    values = dict(evidence)
    values["source_start_offset"] = 0
    return _slice_records(values)


def _jsonl_records(raw: bytes) -> tuple[Record, ...]:
    if raw and not raw.endswith(b"\n"):
        raise ValueError("HYPE floor ledger prefix ends with an incomplete row")
    rows: list[Record] = []
    for line in raw.splitlines():
        value = json.loads(line)
        rows.append(_mapping(value, "ledger row"))
    return tuple(rows)


def _optional_resolution(
    value: Path | None,
) -> tuple[Record | None, dict[str, object] | None]:
    if value is None:
        return None, None
    return _read_mapping_with_evidence(Path(value))


def _report(prepared: Sequence[PreparedNativeFloorInput]) -> dict[str, object]:
    return build_hype_native_profit_floor_transfer(
        tuple(value.lifecycle for value in prepared),
        {value.lifecycle.lifecycle_id: value.bars for value in prepared},
        {value.lifecycle.lifecycle_id: value.books for value in prepared},
    )


def _read_mapping_with_evidence(
    path: Path,
) -> tuple[Record, dict[str, object]]:
    raw = path.read_bytes()
    value = _mapping(json.loads(raw), f"artifact {path}")
    return value, {"path": str(path), "bytes": len(raw), "sha256": _digest(raw)}


def _generator_evidence() -> list[dict[str, object]]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/hype_native_profit_floor_sources.py",
        root / "src/hypervector/research/hype_native_profit_floor_transfer.py",
        root / "src/hypervector/cohort_profit_lock_policy.py",
        root / "src/hypervector/research/cohort_exact_depth_books.py",
    )
    return [file_evidence(path) for path in paths]


def _digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"HYPE floor {label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"HYPE floor {label} must be non-empty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"HYPE floor {label} must be a nonnegative integer")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only HYPE-native profit-floor snapshot command."""
    args = build_parser().parse_args(argv)
    try:
        run_command(args)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
