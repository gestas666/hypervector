"""Publish an immutable report-only p99-normalized growth allocation."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import tempfile

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_risk_normalized_allocation import (
    build_risk_normalized_allocation,
)
from hypervector.research.mu_hip3_archive_provenance import (
    require_unchanged_generator,
    source_tree_identity,
)

Record = Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build explicit source and immutable output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build one source-bound allocation report without execution authority."""
    project_root = Path(__file__).resolve().parents[1]
    generator = source_tree_identity(project_root, Path(__file__).resolve())
    source = _load_json(args.source)
    report = build_risk_normalized_allocation(source)
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "source_evidence": _path_evidence(args.source),
            "generator_identity": generator,
        }
    )
    return report


def write_immutable_report(path: Path, report: Record) -> None:
    """Publish a new JSON artifact without a replacement race."""
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise FileExistsError(f"allocation output already exists: {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _load_json(path: Path) -> Record:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"growth stress source is unreadable: {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("growth stress source must be an object")
    return value


def _path_evidence(path: Path) -> dict[str, object]:
    evidence = file_evidence(path)
    evidence["path"] = str(path)
    return evidence


def main() -> int:
    """Publish the report after a source-tree stability recheck."""
    args = build_parser().parse_args()
    report = run_report(args)
    generator = report.get("generator_identity")
    if not isinstance(generator, Mapping):
        raise ValueError("generator identity is missing")
    require_unchanged_generator(
        dict(generator),
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve(),
    )
    write_immutable_report(args.out, report)
    print(
        json.dumps(
            {
                "output": str(args.out),
                "execution_authority": "none",
                "status": report["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
