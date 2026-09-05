#!/usr/bin/env python3
"""Publish immutable report-only technical acceptance for live v56."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.poststart_publication import (
    PoststartPublicationSpec,
    add_publication_arguments,
    build_publication_report,
    publish_acceptance,
    require_unchanged_publication,
)
from hypervector.research.v56_poststart_acceptance import (
    build_v56_poststart_acceptance,
)

Record = Mapping[str, object]
_SPEC = PoststartPublicationSpec(
    label="v56",
    output_prefix="v56_poststart_acceptance",
    output_dir=Path("data/logs/research/bidirectional_cohort"),
    generator_files=(
        Path(__file__).resolve(),
        Path("src/hypervector/research/poststart_publication.py").resolve(),
        Path("src/hypervector/research/v56_poststart_acceptance.py").resolve(),
        Path("src/hypervector/research/v51_poststart_acceptance.py").resolve(),
        Path("src/hypervector/research/v43_poststart_acceptance.py").resolve(),
        Path("src/hypervector/research/v39_poststart_acceptance.py").resolve(),
        Path("src/hypervector/live/btc_hulk_robust_short_provider.py").resolve(),
        Path("src/hypervector/live/cohort_execution_plan.py").resolve(),
    ),
    evidence_names=("preflight",),
)


def build_parser() -> argparse.ArgumentParser:
    """Require the exact v56 configuration and transition preflight."""
    return add_publication_arguments(
        argparse.ArgumentParser(description=__doc__),
        config=Path(
            "configs/multi_asset_growth_first_5000_btc_tuned_v2_increment_v56.toml"
        ),
        evidence_defaults={"preflight": None},
    )


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build v56 acceptance from exact bytes without execution authority."""
    return build_publication_report(args, _SPEC, _build_acceptance)


def require_unchanged_inputs(report: Record) -> None:
    """Abort if an input or generator changes after evaluation."""
    require_unchanged_publication(report, _SPEC)


def _build_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    evidence: Mapping[str, Record],
    generated: datetime,
    checkpoint_age: float,
    pressure_age: float,
) -> dict[str, object]:
    return build_v56_poststart_acceptance(
        checkpoint,
        config,
        evidence["preflight"],
        now_utc=generated,
        maximum_checkpoint_age_seconds=checkpoint_age,
        maximum_pressure_age_seconds=pressure_age,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Persist technical evidence without importing an order client."""
    return publish_acceptance(build_parser().parse_args(argv), _SPEC, _build_acceptance)


if __name__ == "__main__":
    raise SystemExit(main())
