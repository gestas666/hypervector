#!/usr/bin/env python3
"""Publish immutable combined post-start acceptance for exact live v32."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from hypervector.research.candidate_acceptance_command import (
    CandidateAcceptanceCommand,
    CandidateAcceptanceCommandSpec,
    snapshot_acceptance_inputs,
)
from hypervector.research.v32_acceptance import (
    V32_SYMBOLS,
    build_v32_poststart_acceptance,
    build_v32_raw_ledger_acceptance,
)
from hypervector.research.v32_acceptance_snapshot import (
    build_v32_acceptance_snapshot,
)

_snapshot_inputs = partial(snapshot_acceptance_inputs, symbols=V32_SYMBOLS)

_COMMAND = CandidateAcceptanceCommand(
    spec=CandidateAcceptanceCommandSpec(
        version_label="v32",
        bundle_schema="v32_acceptance_bundle_v1",
        checkpoint=Path("data/runtime/bidirectional_cohort/latest_checkpoint.json"),
        journal=Path("docs/research-journal/hip3-route-authority-pruning-v3.json"),
        candidate_config=Path(
            "configs/multi_asset_bidirectional_commodity_swing_retired_candidate_v32.toml"
        ),
        ledger_root=Path("data/live/bidirectional_cohort"),
        output_dir=Path("data/logs/research/bidirectional_cohort"),
        output_prefix="v32_acceptance",
        journal_sha256=(
            "5630aefd980fdef8984d7a49ca9ed1b85a694370b69a7f14f1ef0c1d8e8a98f5"
        ),
        symbols=V32_SYMBOLS,
    ),
    snapshot_builder=lambda *args: build_v32_acceptance_snapshot(*args),
    poststart_builder=lambda *args, **options: build_v32_poststart_acceptance(
        *args, **options
    ),
    raw_builder=lambda *args, **options: build_v32_raw_ledger_acceptance(
        *args, **options
    ),
    snapshot_inputs=lambda *args: _snapshot_inputs(*args),
)

build_parser = _COMMAND.build_parser
run = _COMMAND.run
exit_code = _COMMAND.exit_code
command_summary = _COMMAND.command_summary


if __name__ == "__main__":
    raise SystemExit(_COMMAND.main())
