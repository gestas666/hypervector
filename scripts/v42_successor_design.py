#!/usr/bin/env python3
"""Publish one immutable, report-only focused v42 successor design."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.v42_successor_design import build_v42_successor_design

Record = Mapping[str, object]

_CONFIG = Path(
    "configs/multi_asset_bidirectional_focused_growth_5000_candidate_v42.toml"
)
_DEFAULTS = {
    "v41_readiness": Path(
        "data/logs/research/bidirectional_cohort/"
        "v41_successor_readiness_20260811T1730Z_v1.json"
    ),
    "current_checkpoint": Path(
        "data/runtime/bidirectional_cohort/latest_checkpoint.json"
    ),
    "hype_exit_evidence": Path(
        "data/logs/research/hype_compression_breakout_challenger_20260811_v4/"
        "report.json"
    ),
}
_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    """Build explicit source and immutable output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    for name, default in _DEFAULTS.items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, default=default)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build the v42 design from one byte-frozen evidence prefix."""
    paths = _input_paths(args)
    _validate_paths(paths, args.out)
    raw = {name: path.read_bytes() for name, path in paths.items()}
    parsed = {
        name: _mapping(json.loads(payload), name)
        for name, payload in raw.items()
        if name != "config"
    }
    report = build_v42_successor_design(
        config=_load_bound_config(raw["config"]),
        v41_readiness=parsed["v41_readiness"],
        current_checkpoint=parsed["current_checkpoint"],
        hype_exit_evidence=parsed["hype_exit_evidence"],
    )
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["evidence"] = {
        name: _byte_record(paths[name], payload) for name, payload in raw.items()
    }
    report["generator_identity"] = {"files": _generator_identity()}
    report["material_state_sha256"] = _digest(report)
    return report


def require_unchanged_inputs(report: Record) -> None:
    """Abort if any evidence or generator file changed before publication."""
    evidence = _mapping(report.get("evidence"), "report evidence")
    for value in evidence.values():
        expected = _mapping(value, "evidence file")
        path = Path(_text(expected.get("path"), "evidence path"))
        if _file_record(path) != dict(expected):
            raise RuntimeError(f"v42 successor input changed: {path}")
    generator = _mapping(report.get("generator_identity"), "generator identity")
    if generator.get("files") != _generator_identity():
        raise RuntimeError("v42 successor generator changed during evaluation")


def _input_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "config": args.config.resolve(),
        **{name: getattr(args, name).resolve() for name in _DEFAULTS},
    }


def _validate_paths(paths: Record, output: Path) -> None:
    inputs = [Path(_text(value, "input path")).resolve() for value in paths.values()]
    if len(set(inputs)) != len(inputs):
        raise ValueError("v42 successor inputs must be distinct")
    if output.resolve() in set(inputs):
        raise ValueError("v42 successor output must differ from its inputs")


def _load_bound_config(raw: bytes) -> MultiAssetLiveConfig:
    with TemporaryDirectory(prefix="hypervector-v42-design-") as directory:
        path = Path(directory) / "bound-config.toml"
        path.write_bytes(raw)
        return load_multi_asset_live_config(
            path,
            mode="observe",
            enabled=False,
            accepts_live_risk=False,
        )


def _generator_identity() -> list[dict[str, object]]:
    paths = [
        Path(__file__).resolve(),
        (_ROOT / "src/hypervector/research/v42_successor_design.py").resolve(),
        *sorted((_ROOT / "src/hypervector/live").glob("multi_asset_live_config*.py")),
        (_ROOT / "src/hypervector/live/multi_asset_live_identity.py").resolve(),
        (_ROOT / "src/hypervector/live/cohort_execution_plan.py").resolve(),
    ]
    return [_file_record(path) for path in paths]


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


def main(argv: Sequence[str] | None = None) -> int:
    """Build, revalidate, and publish the immutable v42 design."""
    args = build_parser().parse_args(argv)
    report = run_report(args)
    require_unchanged_inputs(report)
    write_immutable_json(args.out, report)
    print(
        json.dumps(
            {
                "event": "v42_successor_design",
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
