#!/usr/bin/env python3
"""Publish an immutable report-only v39 protective-stop recovery sensitivity."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.cohort_stop_recovery_sensitivity import (
    build_stop_recovery_sensitivity,
)

Record = Mapping[str, object]

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_PROFILE_ID = (
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39"
)
_PROFILE_FINGERPRINT = (
    "8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5"
)
_DEFAULT_WIDTHS = (80.0, 100.0, 125.0, 150.0, 200.0)
_GENERATOR_FILES = (
    Path(__file__).resolve(),
    Path("src/hypervector/research/cohort_stop_recovery_sensitivity.py").resolve(),
    Path("src/hypervector/research/cohort_live_audit_values.py").resolve(),
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit source and immutable output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--stop-width-bps", action="append", type=float, dest="stop_widths"
    )
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build an exact-current-run sensitivity without execution authority."""
    _validate_paths(args)
    checkpoint_raw = args.checkpoint.read_bytes()
    checkpoint = _mapping(json.loads(checkpoint_raw), "v39 checkpoint")
    audit = _mapping(checkpoint.get("audit"), "v39 checkpoint audit")
    run = _exact_v39_run(_mapping(audit.get("run"), "v39 checkpoint run"))
    reflections = _mapping(audit.get("trade_reflections"), "v39 trade reflections")
    trades = _records(reflections.get("trades"), "v39 reflected trades")
    widths = tuple(args.stop_widths or _DEFAULT_WIDTHS)
    report = build_stop_recovery_sensitivity(trades, stop_widths_bps=widths)
    generated = datetime.now(UTC).isoformat()
    report.update(
        {
            "generated_at_utc": generated,
            "source": _source(run),
            "evidence": {
                "checkpoint": _byte_record(args.checkpoint, checkpoint_raw),
                "reflected_trades": _embedded_records(trades),
            },
            "generator_identity": {"files": _generator_identity()},
        }
    )
    report["material_state_sha256"] = _digest(report)
    return report


def _exact_v39_run(run: Record) -> Record:
    if run.get("profile_id") != _PROFILE_ID:
        raise ValueError("stop recovery requires the exact v39 profile")
    if run.get("profile_fingerprint") != _PROFILE_FINGERPRINT:
        raise ValueError("stop recovery requires the exact v39 fingerprint")
    return run


def _source(run: Record) -> dict[str, object]:
    return {
        "run_id": _text(run.get("run_id"), "v39 run identity"),
        "profile_id": _PROFILE_ID,
        "profile_fingerprint": _PROFILE_FINGERPRINT,
        "scope": "exact_current_backend_process_run",
    }


def _validate_paths(args: argparse.Namespace) -> None:
    if args.out.resolve() == args.checkpoint.resolve():
        raise ValueError("stop recovery output must differ from its checkpoint")


def _require_unchanged(report: Record) -> None:
    evidence = _mapping(report.get("evidence"), "stop recovery evidence")
    expected = _mapping(evidence.get("checkpoint"), "checkpoint evidence")
    path = Path(_text(expected.get("path"), "checkpoint evidence path"))
    if _file_record(path) != expected:
        raise RuntimeError("v39 checkpoint changed during stop recovery evaluation")
    generator = _mapping(report.get("generator_identity"), "generator identity")
    if generator.get("files") != _generator_identity():
        raise RuntimeError("stop recovery generator changed during evaluation")


def _generator_identity() -> list[dict[str, object]]:
    return [_file_record(path) for path in _GENERATOR_FILES]


def _file_record(path: Path) -> dict[str, object]:
    return _byte_record(path, path.read_bytes())


def _byte_record(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _embedded_records(rows: Sequence[Record]) -> dict[str, object]:
    values = [dict(row) for row in rows]
    raw = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return {"sha256": sha256(raw).hexdigest(), "bytes": len(raw), "rows": values}


def _digest(report: Record) -> str:
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be a list of objects")
    return list(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def main(argv: Sequence[str] | None = None) -> int:
    """Build, revalidate, and publish the immutable sensitivity report."""
    args = build_parser().parse_args(argv)
    report = run_report(args)
    _require_unchanged(report)
    write_immutable_json(args.out, report)
    print(
        json.dumps(
            {
                "event": "v39_stop_recovery_sensitivity",
                "state": "published",
                "output": str(args.out),
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
