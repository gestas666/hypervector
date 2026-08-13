#!/usr/bin/env python3
"""Publish exact, immutable, report-only technical acceptance for live v41."""

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
from hypervector.research.v41_poststart_acceptance import (
    build_v41_poststart_acceptance,
)

Record = Mapping[str, object]

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_CONFIG = Path(
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41.toml"
)
_OUTPUT_DIR = Path("data/logs/research/bidirectional_cohort")
_GENERATOR_FILES = (
    Path(__file__).resolve(),
    Path("src/hypervector/research/v41_poststart_acceptance.py").resolve(),
    Path("src/hypervector/research/v39_poststart_acceptance.py").resolve(),
    Path("src/hypervector/research/v39_canonical_regime_acceptance.py").resolve(),
    Path("src/hypervector/live/multi_asset_live_config.py").resolve(),
)


def build_parser() -> argparse.ArgumentParser:
    """Require the final flat-boundary readiness artifact explicitly."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--maximum-checkpoint-age-seconds", type=float, default=90.0)
    parser.add_argument("--maximum-pressure-age-seconds", type=float, default=30.0)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build acceptance from frozen bytes without execution authority."""
    paths = _input_paths(args)
    output = args.out or _timestamped_output(datetime.now(UTC))
    _validate_paths(paths, output)
    raw = {name: path.read_bytes() for name, path in paths.items()}
    checkpoint = _mapping(json.loads(raw["checkpoint"]), "checkpoint")
    readiness = _mapping(json.loads(raw["readiness"]), "readiness")
    config = _load_bound_config(raw["config"])
    generated = datetime.now(UTC)
    report = build_v41_poststart_acceptance(
        checkpoint,
        config,
        readiness,
        now_utc=generated,
        maximum_checkpoint_age_seconds=args.maximum_checkpoint_age_seconds,
        maximum_pressure_age_seconds=args.maximum_pressure_age_seconds,
    )
    report.update(
        {
            "generated_at_utc": generated.isoformat(),
            "evidence": {
                name: _byte_record(path, raw[name]) for name, path in paths.items()
            },
            "generator_identity": {"files": _generator_identity()},
        }
    )
    report["material_state_sha256"] = _digest(report)
    args.out = output
    return report


def require_unchanged_inputs(report: Record) -> None:
    """Abort if any exact input or generator changed after evaluation."""
    evidence = _mapping(report.get("evidence"), "acceptance evidence")
    for value in evidence.values():
        expected = _mapping(value, "acceptance input")
        path = Path(_text(expected.get("path"), "acceptance path"))
        if _file_record(path) != dict(expected):
            raise RuntimeError(f"v41 post-start input changed: {path}")
    generator = _mapping(report.get("generator_identity"), "generator identity")
    if generator.get("files") != _generator_identity():
        raise RuntimeError("v41 post-start generator changed during evaluation")


def write_immutable_report(path: Path, report: Record) -> None:
    """Publish complete JSON without replacing an existing artifact."""
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
        raise FileExistsError(f"v41 post-start report already exists: {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def exit_code(report: Record) -> int:
    """Return zero only for explicit technical acceptance."""
    accepted = report.get("accepted")
    if not isinstance(accepted, bool):
        raise ValueError("v41 acceptance result must be boolean")
    return 0 if accepted else 2


def _input_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "checkpoint": args.checkpoint.resolve(),
        "config": args.config.resolve(),
        "readiness": args.readiness.resolve(),
    }


def _validate_paths(paths: Record, output: Path) -> None:
    resolved = [Path(_text(value, "input path")).resolve() for value in paths.values()]
    if len(set(resolved)) != len(resolved):
        raise ValueError("v41 post-start inputs must be distinct")
    if output.resolve() in set(resolved):
        raise ValueError("v41 post-start output must differ from every input")


def _load_bound_config(raw: bytes) -> object:
    with TemporaryDirectory(prefix="hypervector-v41-poststart-") as directory:
        path = Path(directory) / "bound-config.toml"
        path.write_bytes(raw)
        return load_multi_asset_live_config(path, mode="observe")


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


def _digest(report: Record) -> str:
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str | Path):
        raise ValueError(f"{label} must be a path")
    return str(value)


def _timestamped_output(generated: datetime) -> Path:
    stamp = generated.strftime("%Y%m%dT%H%M%SZ")
    return _OUTPUT_DIR / f"v41_poststart_acceptance_{stamp}.json"


def main(argv: Sequence[str] | None = None) -> int:
    """Persist technical evidence without importing an order client."""
    args = build_parser().parse_args(argv)
    report = run_report(args)
    require_unchanged_inputs(report)
    write_immutable_report(args.out, report)
    print(
        json.dumps(
            {
                "accepted": report.get("accepted"),
                "decision": report.get("decision"),
                "reasons": report.get("reasons"),
                "out": str(args.out),
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
