#!/usr/bin/env python3
"""Publish one immutable, report-only v41 successor-readiness artifact."""

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
from hypervector.research.v41_successor_readiness import (
    build_v41_successor_readiness,
)

Record = Mapping[str, object]

_CONFIG = Path(
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41.toml"
)
_DEFAULTS = {
    "preflight": Path(
        "data/runtime/bidirectional_cohort/"
        "growth_5000_v41_preflight_20260811T1718Z.json"
    ),
    "reprice": Path(
        "data/logs/research/bidirectional_cohort/"
        "v40_p99_risk_normalized_exact_reprice_20260811T0226Z_v1.json"
    ),
    "concentration": Path(
        "data/logs/research/bidirectional_cohort/"
        "v41_provider_family_concentration_20260811T0535Z_v1.json"
    ),
    "return_panel": Path(
        "data/logs/research/bidirectional_cohort/"
        "v41_return_panel_coverage_20260811T0558Z_v1.json"
    ),
    "v39_review": Path(
        "data/logs/research/bidirectional_cohort/"
        "v39_route_portfolio_review_20260811T1715Z_v2.json"
    ),
}
_GENERATOR_FILES = (
    Path(__file__).resolve(),
    Path("src/hypervector/research/v41_successor_readiness.py").resolve(),
    Path("src/hypervector/live/multi_asset_live_config.py").resolve(),
    Path("src/hypervector/live/multi_asset_live_identity.py").resolve(),
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit evidence and immutable output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    for name, default in _DEFAULTS.items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, default=default)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build a source-bound readiness report without live authority."""
    paths = _input_paths(args)
    _validate_paths(paths, args.out)
    raw = {name: path.read_bytes() for name, path in paths.items()}
    parsed = {
        name: _mapping(json.loads(payload), name)
        for name, payload in raw.items()
        if name != "config"
    }
    config = _load_bound_config(raw["config"])
    report = build_v41_successor_readiness(
        config=config,
        config_source_sha256=sha256(raw["config"]).hexdigest(),
        **parsed,
    )
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "evidence": {
                name: _byte_record(paths[name], payload)
                for name, payload in raw.items()
            },
            "generator_identity": {"files": _generator_identity()},
        }
    )
    report["material_state_sha256"] = _digest(report)
    return report


def require_unchanged_inputs(report: Record) -> None:
    """Abort if evidence or generator bytes changed after assessment."""
    evidence = _mapping(report.get("evidence"), "report evidence")
    for value in evidence.values():
        expected = _mapping(value, "evidence file")
        path = Path(_text(expected.get("path"), "evidence path"))
        if _file_record(path) != dict(expected):
            raise RuntimeError(f"v41 readiness input changed: {path}")
    generator = _mapping(report.get("generator_identity"), "generator identity")
    if generator.get("files") != _generator_identity():
        raise RuntimeError("v41 readiness generator changed during evaluation")


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
        raise FileExistsError(f"v41 readiness report already exists: {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _input_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "config": args.config.resolve(),
        **{name: getattr(args, name).resolve() for name in _DEFAULTS},
    }


def _validate_paths(paths: Record, output: Path) -> None:
    resolved = [Path(_text(value, "input path")).resolve() for value in paths.values()]
    if len(set(resolved)) != len(resolved):
        raise ValueError("v41 readiness inputs must be distinct")
    if output.resolve() in set(resolved):
        raise ValueError("v41 readiness output must differ from every input")


def _load_bound_config(raw: bytes) -> object:
    with TemporaryDirectory(prefix="hypervector-v41-readiness-") as directory:
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
    """Build, revalidate, and publish the immutable readiness report."""
    args = build_parser().parse_args(argv)
    report = run_report(args)
    require_unchanged_inputs(report)
    write_immutable_report(args.out, report)
    print(
        json.dumps(
            {
                "event": "v41_successor_readiness",
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
