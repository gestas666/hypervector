#!/usr/bin/env python3
"""Publish immutable combined post-start acceptance for exact live v33."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from hypervector.research.candidate_acceptance_command import (
    CandidateAcceptanceCommand,
    CandidateAcceptanceCommandSpec,
    snapshot_acceptance_inputs,
)
from hypervector.research.v33_acceptance import (
    V33_SYMBOLS,
    build_v33_poststart_acceptance,
    build_v33_raw_ledger_acceptance,
)
from hypervector.research.v33_acceptance_snapshot import (
    build_v33_acceptance_snapshot,
)

_snapshot_inputs = partial(snapshot_acceptance_inputs, symbols=V33_SYMBOLS)

_COMMAND = CandidateAcceptanceCommand(
    spec=CandidateAcceptanceCommandSpec(
        version_label="v33",
        bundle_schema="v33_acceptance_bundle_v1",
        checkpoint=Path("data/runtime/bidirectional_cohort/latest_checkpoint.json"),
        journal=Path("docs/research-journal/hip3-route-authority-pruning-v4.json"),
        candidate_config=Path(
            "configs/multi_asset_bidirectional_spcx_swing_retired_candidate_v33.toml"
        ),
        ledger_root=Path("data/live/bidirectional_cohort"),
        output_dir=Path("data/logs/research/bidirectional_cohort"),
        output_prefix="v33_acceptance",
        journal_sha256=(
            "1aab492f9914f699e1d1ba1462dd394472018c848825cb66dde1146c62869a8c"
        ),
        symbols=V33_SYMBOLS,
    ),
    snapshot_builder=lambda *args: build_v33_acceptance_snapshot(*args),
    poststart_builder=lambda *args, **options: build_v33_poststart_acceptance(
        *args, **options
    ),
    raw_builder=lambda *args, **options: build_v33_raw_ledger_acceptance(
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
