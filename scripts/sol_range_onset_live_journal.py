"""Write one immutable read-only attribution snapshot of the SOL live ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence, cast

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.sol_range_onset_live_journal import build_live_journal


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable live-journal command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Read one ledger and write one immutable attribution artifact."""
    args = build_parser().parse_args(argv)
    try:
        records, evidence = _read_snapshot(args.ledger)
        report = build_live_journal(records)
        report["source_evidence"] = evidence
        write_immutable_json(args.out, report)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"ok": True, "out": str(args.out), "evidence": file_evidence(args.out)},
            sort_keys=True,
        )
    )
    return 0


def _read_snapshot(
    path: Path,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Read and hash the same immutable-in-memory ledger byte snapshot."""
    if not path.is_file():
        raise ValueError(f"live ledger does not exist: {path}")
    raw = path.read_bytes()
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        value: object = json.loads(line)
        if not isinstance(value, dict) or not all(
            isinstance(key, str) for key in value
        ):
            raise ValueError(f"live ledger line {line_number} must be an object")
        records.append(cast(dict[str, object], value))
    evidence: dict[str, object] = {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "record_count": len(records),
    }
    return records, evidence


if __name__ == "__main__":
    raise SystemExit(main())
