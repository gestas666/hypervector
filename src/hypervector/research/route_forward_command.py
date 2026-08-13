"""Shared operator command for versioned report-only route tracking."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.v31_route_forward import build_v31_route_forward_snapshot
from hypervector.research.v32_route_forward import build_v32_route_forward_snapshot
from hypervector.research.v33_route_forward import build_v33_route_forward_snapshot

Record = Mapping[str, object]
SnapshotBuilder = Callable[[Record, Record, Path, Path], dict[str, object]]


@dataclass(frozen=True)
class RouteForwardCommandSpec:
    """Bind one tracker command to exact files and a snapshot builder."""

    label: str
    checkpoint: Path
    journal: Path
    source_config: Path
    candidate_config: Path
    output: Path
    builder: SnapshotBuilder


_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_SOURCE = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")

V31_ROUTE_COMMAND_SPEC = RouteForwardCommandSpec(
    label="v31 route-forward",
    checkpoint=_CHECKPOINT,
    journal=Path("docs/research-journal/hip3-route-authority-pruning-v1.json"),
    source_config=_SOURCE,
    candidate_config=Path(
        "configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml"
    ),
    output=Path("data/runtime/bidirectional_cohort/latest_v31_route_forward.json"),
    builder=build_v31_route_forward_snapshot,
)

V32_ROUTE_COMMAND_SPEC = RouteForwardCommandSpec(
    label="v32 route-forward",
    checkpoint=_CHECKPOINT,
    journal=Path("docs/research-journal/hip3-route-authority-pruning-v3.json"),
    source_config=_SOURCE,
    candidate_config=Path(
        "configs/multi_asset_bidirectional_commodity_swing_retired_candidate_v32.toml"
    ),
    output=Path("data/runtime/bidirectional_cohort/latest_v32_route_forward.json"),
    builder=build_v32_route_forward_snapshot,
)

V33_ROUTE_COMMAND_SPEC = RouteForwardCommandSpec(
    label="v33 route-forward",
    checkpoint=_CHECKPOINT,
    journal=Path("docs/research-journal/hip3-route-authority-pruning-v4.json"),
    source_config=_SOURCE,
    candidate_config=Path(
        "configs/multi_asset_bidirectional_spcx_swing_retired_candidate_v33.toml"
    ),
    output=Path("data/runtime/bidirectional_cohort/latest_v33_route_forward.json"),
    builder=build_v33_route_forward_snapshot,
)


def build_route_forward_parser(
    spec: RouteForwardCommandSpec,
) -> argparse.ArgumentParser:
    """Build a parser with exact versioned defaults."""
    parser = argparse.ArgumentParser(description=f"Publish {spec.label} telemetry")
    parser.add_argument("--checkpoint", type=Path, default=spec.checkpoint)
    parser.add_argument("--journal", type=Path, default=spec.journal)
    parser.add_argument("--source-config", type=Path, default=spec.source_config)
    parser.add_argument("--candidate-config", type=Path, default=spec.candidate_config)
    parser.add_argument("--out", type=Path, default=spec.output)
    parser.add_argument(
        "--immutable",
        action="store_true",
        help="refuse an existing output instead of replacing the bounded snapshot",
    )
    return parser


def run_route_forward(
    spec: RouteForwardCommandSpec, args: argparse.Namespace
) -> dict[str, object]:
    """Validate and atomically publish one versioned route snapshot."""
    if args.immutable and args.out.exists():
        raise FileExistsError(f"{spec.label} output already exists: {args.out}")
    checkpoint = _load_json(args.checkpoint, "checkpoint", spec.label)
    journal = _load_json(args.journal, "journal", spec.label)
    report = spec.builder(
        checkpoint, journal, args.source_config, args.candidate_config
    )
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["evidence"] = {
        "checkpoint": _path_evidence(args.checkpoint),
        "journal": _path_evidence(args.journal),
        "source_config": _path_evidence(args.source_config),
        "candidate_config": _path_evidence(args.candidate_config),
    }
    write_atomic_json(args.out, report)
    return report


def route_forward_summary(report: Record) -> dict[str, object]:
    """Return bounded operator telemetry without route expansion."""
    assessment = report.get("assessment")
    if not isinstance(assessment, Mapping):
        raise ValueError("route-forward assessment must be an object")
    return {
        "phase": report.get("phase"),
        "tracking_state": report.get("tracking_state"),
        "current_open_positions": assessment.get("current_open_positions"),
        "removed_route_eligible_signals": assessment.get(
            "removed_route_eligible_signals"
        ),
        "execution_authority": "none",
    }


def route_forward_main(
    spec: RouteForwardCommandSpec, argv: Sequence[str] | None = None
) -> int:
    """Run one versioned tracker without importing a venue order client."""
    args = build_route_forward_parser(spec).parse_args(argv)
    report = run_route_forward(spec, args)
    print(
        json.dumps({"ok": True, "out": str(args.out), **route_forward_summary(report)})
    )
    return 0


def _load_json(path: Path, label: str, command_label: str) -> Record:
    if not path.is_file():
        raise FileNotFoundError(f"{command_label} {label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{command_label} {label} must be an object")
    return value


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}
