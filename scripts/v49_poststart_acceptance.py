#!/usr/bin/env python3
"""Publish immutable report-only technical acceptance for live v49."""

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
from hypervector.research.v49_poststart_acceptance import (
    build_v49_poststart_acceptance,
)

Record = Mapping[str, object]
_OUTPUT_DIR = Path("data/logs/research/bidirectional_cohort")
_SPEC = PoststartPublicationSpec(
    label="v49",
    output_prefix="v49_poststart_acceptance",
    output_dir=_OUTPUT_DIR,
    generator_files=(
        Path(__file__).resolve(),
        Path("src/hypervector/research/poststart_publication.py").resolve(),
        Path("src/hypervector/research/growth_poststart_acceptance.py").resolve(),
        Path("src/hypervector/research/v49_poststart_acceptance.py").resolve(),
        Path("src/hypervector/research/v39_poststart_acceptance.py").resolve(),
        Path("src/hypervector/research/v39_canonical_regime_acceptance.py").resolve(),
        Path("src/hypervector/research/v43_poststart_acceptance.py").resolve(),
        Path(
            "src/hypervector/research/btc_specialist_friction_acceptance.py"
        ).resolve(),
    ),
    evidence_names=("friction", "preflight"),
)


def build_parser() -> argparse.ArgumentParser:
    """Require exact v49 friction evidence and a fresh flat preflight."""
    return add_publication_arguments(
        argparse.ArgumentParser(description=__doc__),
        config=Path(
            "configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml"
        ),
        evidence_defaults={
            "friction": _OUTPUT_DIR / "v49_growth_sizing_stress_20260812_v1.json",
            "preflight": None,
        },
    )


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build v49 acceptance from exact bytes without execution authority."""
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
    return build_v49_poststart_acceptance(
        checkpoint,
        config,
        evidence["friction"],
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
