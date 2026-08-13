#!/usr/bin/env python3
"""Publish immutable report-only technical acceptance for live v44."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.poststart_publication import (
    PoststartPublicationSpec,
    add_publication_arguments,
    accepted_exit_code,
    build_publication_report,
    publish_acceptance,
    require_unchanged_publication,
)
from hypervector.research.v44_poststart_acceptance import (
    build_v44_poststart_acceptance,
)

Record = Mapping[str, object]

_OUTPUT_DIR = Path("data/logs/research/bidirectional_cohort")
_SPEC = PoststartPublicationSpec(
    label="v44",
    output_prefix="v44_poststart_acceptance",
    output_dir=_OUTPUT_DIR,
    generator_files=(
        Path(__file__).resolve(),
        Path("src/hypervector/research/poststart_publication.py").resolve(),
        Path("src/hypervector/research/v44_poststart_acceptance.py").resolve(),
        Path("src/hypervector/research/v43_poststart_acceptance.py").resolve(),
        Path("src/hypervector/research/v39_poststart_acceptance.py").resolve(),
        Path("src/hypervector/research/v39_canonical_regime_acceptance.py").resolve(),
    ),
    evidence_names=("risk", "friction", "preflight"),
)


def build_parser() -> argparse.ArgumentParser:
    """Require exact final-boundary preflight evidence explicitly."""
    parser = argparse.ArgumentParser(description=__doc__)
    return add_publication_arguments(
        parser,
        config=Path(
            "configs/multi_asset_bidirectional_btc_specialists_corrected_"
            "candidate_v44.toml"
        ),
        evidence_defaults={
            "risk": _OUTPUT_DIR / "v44_btc_specialist_successor_risk_20260811_v1.json",
            "friction": _OUTPUT_DIR / "v44_portfolio_friction_stress_20260811_v1.json",
            "preflight": None,
        },
    )


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build v44 acceptance from exact bytes without execution authority."""
    return build_publication_report(args, _SPEC, _build_acceptance)


def require_unchanged_inputs(report: Record) -> None:
    """Abort if an input or generator changes after evaluation."""
    require_unchanged_publication(report, _SPEC)


def exit_code(report: Record) -> int:
    """Return zero only for explicit technical acceptance."""
    return accepted_exit_code(report, "v44")


def _build_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    evidence: Mapping[str, Record],
    generated: datetime,
    checkpoint_age: float,
    pressure_age: float,
) -> dict[str, object]:
    return build_v44_poststart_acceptance(
        checkpoint,
        config,
        evidence["risk"],
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
