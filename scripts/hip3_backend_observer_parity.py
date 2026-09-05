#!/usr/bin/env python3
"""Publish immutable active-backend versus HIP-3 observer decision parity."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_backend_observer_parity import (
    build_hip3_backend_observer_parity,
)

Record = dict[str, object]
_CHUNK_BYTES = 1024 * 1024
_GENERATOR_FILES = (
    Path(__file__).resolve(),
    Path("src/hypervector/research/hip3_backend_observer_parity.py").resolve(),
    Path("src/hypervector/data/oxa_storage.py").resolve(),
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit immutable parity-report arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--cohort-ledger", type=Path, required=True)
    parser.add_argument("--observer", action="append", required=True)
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> Record:
    """Snapshot source prefixes and build one authority-none parity report."""
    checkpoint_path = Path(args.checkpoint)
    cohort_path = Path(args.cohort_ledger)
    output = Path(args.output)
    observer_paths = _observer_paths(args.observer)
    _require_distinct_paths(checkpoint_path, cohort_path, observer_paths, output)
    checkpoint, checkpoint_evidence = _json_snapshot(checkpoint_path)
    scope = _runtime_scope(checkpoint, str(args.provider_id))
    cohort_rows, cohort_evidence = _cohort_prefix(
        checkpoint, cohort_path, str(args.provider_id)
    )
    observer_rows, observer_evidence = _observer_prefixes(observer_paths)
    report = build_hip3_backend_observer_parity(
        cohort_rows=cohort_rows,
        observer_rows_by_symbol=observer_rows,
        **scope,
    )
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "input_evidence": {
                "checkpoint": checkpoint_evidence,
                "cohort_prefix": cohort_evidence,
                "observer_prefixes": observer_evidence,
            },
            "generator_identity": {"files": _generator_identity()},
        }
    )
    report["material_state_sha256"] = _digest(report)
    return report


def publish_report(path: Path, report: Mapping[str, object]) -> None:
    """Publish one immutable backend-observer parity artifact."""
    write_immutable_json(path, report)


def _runtime_scope(checkpoint: Record, provider_id: str) -> Record:
    _require_checkpoint_contract(_mapping(checkpoint, "checkpoint_contract"))
    generation = _mapping(checkpoint, "configuration_generation")
    run = _mapping(_mapping(checkpoint, "audit"), "run")
    fingerprint = _text(run, "profile_fingerprint")
    valid_generation = (
        generation.get("state") == "current_runtime_configuration"
        and generation.get("matches_runtime") is True
        and generation.get("current_profile_fingerprint") == fingerprint
        and generation.get("runtime_profile_fingerprint") == fingerprint
    )
    if not valid_generation:
        raise ValueError("parity checkpoint does not match the running profile")
    scopes = _mapping(generation, "current_provider_execution_scopes")
    symbols = tuple(_text_list(scopes, provider_id))
    executable = set(_text_list(run, "executable_provider_symbols"))
    expected = {f"{provider_id}|{symbol}" for symbol in symbols}
    if not symbols or not expected.issubset(executable):
        raise ValueError("parity provider is not executable for every symbol")
    return {
        "run_id": _text(run, "run_id"),
        "profile_id": _text(run, "profile_id"),
        "profile_fingerprint": fingerprint,
        "provider_id": provider_id,
        "symbols": symbols,
        "run_started_at_ms": _utc_ms(_text(run, "first_observed_at_utc")),
    }


def _cohort_prefix(
    checkpoint: Record, path: Path, provider_id: str
) -> tuple[list[Record], Record]:
    evidence = _mapping(_mapping(checkpoint, "evidence"), "cohort")
    if Path(_text(evidence, "path")).resolve() != path.resolve():
        raise ValueError("checkpoint cohort evidence path is inconsistent")
    start, end, scope = _cohort_bounds(evidence)
    expected_hash = _text(evidence, "sha256")
    rows, digest = _read_jsonl_range(path, start, end, provider_id.encode())
    if digest != expected_hash:
        raise RuntimeError("cohort ledger prefix differs from checkpoint evidence")
    return rows, {
        "path": str(path.resolve()),
        "bytes": end - start,
        "source_start_offset": start,
        "stable_bytes": end,
        "snapshot_scope": scope,
        "selected_rows": len(rows),
        "sha256": digest,
    }


def _cohort_bounds(evidence: Record) -> tuple[int, int, str]:
    end = _integer(evidence, "stable_bytes")
    raw_start = evidence.get("source_start_offset", 0)
    if isinstance(raw_start, bool) or not isinstance(raw_start, int) or raw_start < 0:
        raise ValueError("parity source_start_offset must be a nonnegative integer")
    if raw_start >= end:
        raise ValueError("parity cohort evidence range must be nonempty")
    if _integer(evidence, "bytes") != end - raw_start:
        raise ValueError("parity cohort evidence byte range is inconsistent")
    scope = evidence.get("snapshot_scope", "full_ledger_prefix")
    allowed = {"full_ledger_prefix", "compatible_execution_history"}
    if scope not in allowed or (raw_start and scope != "compatible_execution_history"):
        raise ValueError("parity cohort snapshot scope is inconsistent")
    return raw_start, end, str(scope)


def _observer_prefixes(
    paths: Mapping[str, Path],
) -> tuple[dict[str, tuple[Record, ...]], dict[str, Record]]:
    rows: dict[str, tuple[Record, ...]] = {}
    evidence: dict[str, Record] = {}
    for symbol, path in paths.items():
        length = path.stat().st_size
        selected, digest = _read_jsonl_prefix(path, length, b"")
        rows[symbol] = tuple(selected)
        evidence[symbol] = {
            "path": str(path.resolve()),
            "bytes": length,
            "rows": len(selected),
            "sha256": digest,
        }
    return rows, evidence


def _read_jsonl_prefix(
    path: Path, length: int, token: bytes
) -> tuple[list[Record], str]:
    return _read_jsonl_range(path, 0, length, token)


def _read_jsonl_range(
    path: Path, start: int, end: int, token: bytes
) -> tuple[list[Record], str]:
    if start < 0 or end <= start or not path.is_file():
        raise ValueError(f"parity JSONL prefix is unavailable: {path}")
    output: list[Record] = []
    digest = sha256()
    remaining, carry = end - start, b""
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining:
            chunk = handle.read(min(_CHUNK_BYTES, remaining))
            if not chunk:
                raise RuntimeError(f"parity JSONL prefix shortened: {path}")
            digest.update(chunk)
            remaining -= len(chunk)
            parts = (carry + chunk).split(b"\n")
            carry = parts.pop()
            output.extend(_selected_rows(parts, token))
    if carry:
        raise ValueError(f"parity JSONL prefix ends with an incomplete row: {path}")
    return output, digest.hexdigest()


def _selected_rows(lines: Sequence[bytes], token: bytes) -> list[Record]:
    output: list[Record] = []
    for line in lines:
        if not line or (token and token not in line):
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("parity JSONL row must be an object")
        output.append(value)
    return output


def _observer_paths(values: Sequence[str]) -> dict[str, Path]:
    output: dict[str, Path] = {}
    for value in values:
        symbol, separator, raw_path = value.partition("=")
        if not separator or not symbol.strip() or not raw_path.strip():
            raise ValueError("observer must use SYMBOL=PATH")
        if symbol in output:
            raise ValueError(f"duplicate observer symbol: {symbol}")
        output[symbol] = Path(raw_path)
    return output


def _json_snapshot(path: Path) -> tuple[Record, Record]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("parity checkpoint must be an object")
    return value, {
        "path": str(path.resolve()),
        "bytes": len(raw),
        "sha256": sha256(raw).hexdigest(),
    }


def _require_checkpoint_contract(contract: Record) -> None:
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
        or contract.get("runtime_strategy_changed") is not False
    ):
        raise ValueError("parity checkpoint contract is not report-only")


def _require_distinct_paths(
    checkpoint: Path,
    cohort: Path,
    observers: Mapping[str, Path],
    output: Path,
) -> None:
    resolved = [
        path.resolve() for path in (checkpoint, cohort, *observers.values(), output)
    ]
    if len(resolved) != len(set(resolved)):
        raise ValueError("parity inputs and output paths must be distinct")


def _generator_identity() -> list[Record]:
    return [{"path": str(path), **file_evidence(path)} for path in _GENERATOR_FILES]


def _digest(report: Mapping[str, object]) -> str:
    raw = json.dumps(report, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode()).hexdigest()


def _mapping(row: Mapping[str, object], key: str) -> Record:
    value = row.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"parity {key} must be an object")
    return value


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"parity {key} must be text")
    return value


def _integer(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"parity {key} must be a positive integer")
    return value


def _text_list(row: Mapping[str, object], key: str) -> list[str]:
    value = row.get(key)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"parity {key} must be a text list")
    return list(value)


def _utc_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("parity run start must be timezone-aware")
    return int(parsed.timestamp() * 1_000)


def main(argv: Sequence[str] | None = None) -> int:
    """Build, publish, and summarize one immutable parity report."""
    args = build_parser().parse_args(argv)
    report = run_report(args)
    publish_report(Path(args.output), report)
    print(
        json.dumps(
            {
                "event": "hip3_backend_observer_parity",
                "output": str(args.output),
                "technical_assessment": report["technical_assessment"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
