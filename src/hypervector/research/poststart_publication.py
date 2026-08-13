"""Shared immutable publication boundary for cohort post-start acceptance."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

Record = Mapping[str, object]
AcceptanceBuilder = Callable[
    [Record, MultiAssetLiveConfig, Mapping[str, Record], datetime, float, float],
    dict[str, object],
]


@dataclass(frozen=True)
class PoststartPublicationSpec:
    """Immutable inputs and names for one post-start report generation."""

    label: str
    output_prefix: str
    output_dir: Path
    generator_files: tuple[Path, ...]
    evidence_names: tuple[str, ...]


def add_publication_arguments(
    parser: argparse.ArgumentParser,
    *,
    config: Path,
    evidence_defaults: Mapping[str, Path | None],
) -> argparse.ArgumentParser:
    """Add the common immutable post-start publication arguments."""
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("data/runtime/bidirectional_cohort/latest_checkpoint.json"),
    )
    parser.add_argument("--config", type=Path, default=config)
    for name, default in evidence_defaults.items():
        parser.add_argument(
            f"--{name}", type=Path, default=default, required=default is None
        )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--maximum-checkpoint-age-seconds", type=float, default=90.0)
    parser.add_argument("--maximum-pressure-age-seconds", type=float, default=30.0)
    return parser


def publish_acceptance(
    args: argparse.Namespace,
    spec: PoststartPublicationSpec,
    builder: AcceptanceBuilder,
) -> int:
    """Build, revalidate, publish, and summarize one acceptance report."""
    report = build_publication_report(args, spec, builder)
    require_unchanged_publication(report, spec)
    write_immutable_json(args.out, report)
    print(publication_summary(report, args.out))
    return accepted_exit_code(report, spec.label)


def build_publication_report(
    args: argparse.Namespace,
    spec: PoststartPublicationSpec,
    builder: AcceptanceBuilder,
) -> dict[str, object]:
    """Build a source-bound report without granting execution authority."""
    paths = input_paths(args, spec)
    output = args.out or timestamped_output(datetime.now(UTC), spec)
    validate_paths(paths, output, spec.label)
    raw = {name: path.read_bytes() for name, path in paths.items()}
    generated = datetime.now(UTC)
    evidence = {name: json_record(raw[name], name) for name in spec.evidence_names}
    report = builder(
        json_record(raw["checkpoint"], "checkpoint"),
        load_bound_config(raw["config"], spec.label),
        evidence,
        generated,
        float(args.maximum_checkpoint_age_seconds),
        float(args.maximum_pressure_age_seconds),
    )
    report.update(publication_identity(paths, raw, generated, spec))
    report["material_state_sha256"] = digest(report)
    args.out = output
    return report


def require_unchanged_publication(
    report: Record, spec: PoststartPublicationSpec
) -> None:
    """Abort when an input or generator changes after evaluation."""
    evidence = record(report.get("evidence"), "acceptance evidence")
    for value in evidence.values():
        expected = record(value, "acceptance input")
        path = Path(text(expected.get("path"), "acceptance path"))
        if file_record(path) != dict(expected):
            raise RuntimeError(f"{spec.label} post-start input changed: {path}")
    current = [file_record(path) for path in spec.generator_files]
    if report.get("generator_identity") != current:
        raise RuntimeError(
            f"{spec.label} post-start generator changed during evaluation"
        )


def input_paths(
    args: argparse.Namespace, spec: PoststartPublicationSpec
) -> dict[str, Path]:
    """Resolve the common and generation-specific evidence paths."""
    paths = {
        "checkpoint": Path(args.checkpoint).resolve(),
        "config": Path(args.config).resolve(),
    }
    paths.update(
        {name: Path(getattr(args, name)).resolve() for name in spec.evidence_names}
    )
    return paths


def validate_paths(paths: Record, output: Path, label: str) -> None:
    """Reject aliased inputs or destructive output paths."""
    resolved = [Path(text(value, "input path")).resolve() for value in paths.values()]
    if len(set(resolved)) != len(resolved):
        raise ValueError(f"{label} post-start inputs must be distinct")
    if output.resolve() in set(resolved):
        raise ValueError(f"{label} post-start output must differ from every input")


def accepted_exit_code(report: Record, label: str) -> int:
    """Return zero only for an explicit boolean technical acceptance."""
    accepted = report.get("accepted")
    if not isinstance(accepted, bool):
        raise ValueError(f"{label} acceptance result must be boolean")
    return 0 if accepted else 2


def publication_summary(report: Record, output: Path) -> str:
    """Serialize the bounded operator summary without secret material."""
    return json.dumps(
        {
            "accepted": report.get("accepted"),
            "decision": report.get("decision"),
            "reasons": report.get("reasons"),
            "out": str(output),
            "execution_authority": "none",
        },
        sort_keys=True,
    )


def publication_identity(
    paths: Mapping[str, Path],
    raw: Mapping[str, bytes],
    generated: datetime,
    spec: PoststartPublicationSpec,
) -> dict[str, object]:
    """Return exact input and generator evidence for immutable publication."""
    return {
        "generated_at_utc": generated.isoformat(),
        "evidence": {
            name: byte_record(path, raw[name]) for name, path in paths.items()
        },
        "generator_identity": [file_record(path) for path in spec.generator_files],
    }


def load_bound_config(raw: bytes, label: str) -> MultiAssetLiveConfig:
    """Parse exactly the bytes whose hash will be published."""
    with TemporaryDirectory(prefix=f"hypervector-{label}-poststart-") as directory:
        path = Path(directory) / "bound-config.toml"
        path.write_bytes(raw)
        return load_multi_asset_live_config(path, mode="observe")


def json_record(raw: bytes, label: str) -> Record:
    """Decode one required JSON object."""
    return record(json.loads(raw), label)


def file_record(path: Path) -> dict[str, object]:
    """Hash one on-disk input or generator file."""
    evidence = file_evidence(path)
    return {"path": str(path.resolve()), **evidence}


def byte_record(path: Path, raw: bytes) -> dict[str, object]:
    """Hash the exact bytes read at evaluation start."""
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def digest(report: Record) -> str:
    """Hash the report material state before publication."""
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def timestamped_output(generated: datetime, spec: PoststartPublicationSpec) -> Path:
    """Return a collision-resistant generation-specific output path."""
    stamp = generated.strftime("%Y%m%dT%H%M%SZ")
    return spec.output_dir / f"{spec.output_prefix}_{stamp}.json"


def record(value: object, label: str) -> Record:
    """Require a JSON object."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def text(value: object, label: str) -> str:
    """Require a path-like value."""
    if not isinstance(value, str | Path):
        raise ValueError(f"{label} must be a path")
    return str(value)
