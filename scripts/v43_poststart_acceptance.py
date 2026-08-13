#!/usr/bin/env python3
"""Publish immutable report-only technical acceptance for live v43."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.poststart_publication import (
    PoststartPublicationSpec,
    accepted_exit_code,
    build_publication_report,
    publication_summary,
    require_unchanged_publication,
)
from hypervector.research.v43_poststart_acceptance import (
    build_v43_poststart_acceptance,
)

Record = Mapping[str, object]

_OUTPUT_DIR = Path("data/logs/research/bidirectional_cohort")
_SPEC = PoststartPublicationSpec(
    label="v43",
    output_prefix="v43_poststart_acceptance",
    output_dir=_OUTPUT_DIR,
    generator_files=(
        Path(__file__).resolve(),
        Path("src/hypervector/research/poststart_publication.py").resolve(),
        Path("src/hypervector/research/v43_poststart_acceptance.py").resolve(),
        Path("src/hypervector/research/v39_poststart_acceptance.py").resolve(),
        Path("src/hypervector/research/v39_canonical_regime_acceptance.py").resolve(),
    ),
    evidence_names=("risk", "preflight"),
)


def build_parser() -> argparse.ArgumentParser:
    """Require exact final-boundary preflight evidence explicitly."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("data/runtime/bidirectional_cohort/latest_checkpoint.json"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            "configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml"
        ),
    )
    parser.add_argument(
        "--risk",
        type=Path,
        default=_OUTPUT_DIR / "v43_btc_specialist_successor_risk_20260811_v1.json",
    )
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--maximum-checkpoint-age-seconds", type=float, default=90.0)
    parser.add_argument("--maximum-pressure-age-seconds", type=float, default=30.0)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build v43 acceptance from exact bytes without execution authority."""
    return build_publication_report(args, _SPEC, _build_acceptance)


def require_unchanged_inputs(report: Record) -> None:
    """Abort if an input or generator changes after evaluation."""
    require_unchanged_publication(report, _SPEC)


def exit_code(report: Record) -> int:
    """Return zero only for explicit technical acceptance."""
    return accepted_exit_code(report, "v43")


def _build_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    evidence: Mapping[str, Record],
    generated: datetime,
    checkpoint_age: float,
    pressure_age: float,
) -> dict[str, object]:
    return build_v43_poststart_acceptance(
        checkpoint,
        config,
        evidence["risk"],
        evidence["preflight"],
        now_utc=generated,
        maximum_checkpoint_age_seconds=checkpoint_age,
        maximum_pressure_age_seconds=pressure_age,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Persist technical evidence without importing an order client."""
    args = build_parser().parse_args(argv)
    report = run_report(args)
    require_unchanged_inputs(report)
    write_immutable_json(args.out, report)
    print(publication_summary(report, args.out))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
