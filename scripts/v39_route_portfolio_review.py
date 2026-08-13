#!/usr/bin/env python3
"""Publish one immutable, exact-v39 route and portfolio evidence review."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from tempfile import TemporaryDirectory

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.v39_forward_evidence import build_v39_forward_evidence
from hypervector.research.v39_route_portfolio_review import (
    build_v39_route_portfolio_review,
)

Record = Mapping[str, object]

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_CONFIG = Path(
    "configs/"
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
_GENERATOR_FILES = (
    Path(__file__).resolve(),
    Path("src/hypervector/research/v39_route_portfolio_review.py").resolve(),
    Path("src/hypervector/research/v39_causal_challenger_program.py").resolve(),
    Path("src/hypervector/research/v39_forward_evidence.py").resolve(),
    Path("src/hypervector/research/v39_forward_evidence_contract.py").resolve(),
    Path("src/hypervector/research/v39_forward_evidence_lifecycles.py").resolve(),
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit exact sources and immutable output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build a source-bound report without changing execution state."""
    _validate_paths(args)
    checkpoint_raw = args.checkpoint.read_bytes()
    config_raw = args.config.read_bytes()
    checkpoint = _mapping(json.loads(checkpoint_raw), "v39 checkpoint")
    config = _load_bound_config(config_raw)
    generated = datetime.now(UTC)
    forward = build_v39_forward_evidence(checkpoint, config, observed_at=generated)
    report = build_v39_route_portfolio_review(forward, checkpoint)
    report.update(
        {
            "generated_at_utc": generated.isoformat(),
            "evidence": {
                "checkpoint": _byte_record(args.checkpoint, checkpoint_raw),
                "config": _byte_record(args.config, config_raw),
            },
            "generator_identity": {"files": _generator_identity()},
        }
    )
    report["material_state_sha256"] = _digest(report)
    return report


def write_immutable_report(path: Path, report: Record) -> None:
    """Publish a complete JSON artifact without replacement races."""
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
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
        raise FileExistsError(f"v39 route review already exists: {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _validate_paths(args: argparse.Namespace) -> None:
    output = args.out.resolve()
    if output in {args.checkpoint.resolve(), args.config.resolve()}:
        raise ValueError("v39 route review output must differ from every input")


def _load_bound_config(raw: bytes) -> object:
    with TemporaryDirectory(prefix="hypervector-v39-review-") as directory:
        path = Path(directory) / "bound-config.toml"
        path.write_bytes(raw)
        return load_multi_asset_live_config(
            path,
            mode="observe",
            enabled=False,
            accepts_live_risk=False,
        )


def _generator_identity() -> list[dict[str, object]]:
    return [_file_record(path) for path in _GENERATOR_FILES]


def _require_unchanged_generator(expected: Record) -> None:
    files = expected.get("files")
    if not isinstance(files, list):
        raise ValueError("v39 route review generator identity is missing")
    if files != _generator_identity():
        raise RuntimeError("v39 route review generator changed during evaluation")


def _file_record(path: Path) -> dict[str, object]:
    return _byte_record(path, path.read_bytes())


def _byte_record(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _digest(report: Record) -> str:
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Build, revalidate, and publish the immutable route review."""
    args = build_parser().parse_args(argv)
    report = run_report(args)
    _require_unchanged_generator(
        _mapping(report.get("generator_identity"), "generator identity")
    )
    write_immutable_report(args.out, report)
    print(
        json.dumps(
            {
                "event": "v39_route_portfolio_review",
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
