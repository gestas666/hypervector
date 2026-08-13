"""Exact report-only acceptance entry points for the inactive v32 candidate."""

from __future__ import annotations

from hypervector.research.candidate_acceptance import (
    CandidateAcceptanceBuilders,
    CandidateAcceptanceSpec,
)
from hypervector.research.v31_raw_identity import V31_SYMBOLS

V32_PROFILE_ID = "multi_asset_bidirectional_commodity_swing_retired_candidate_v32"
V32_PHASE = "candidate_v32_forward"
V32_SYMBOLS = V31_SYMBOLS

V32_ACCEPTANCE_SPEC = CandidateAcceptanceSpec(
    version_label="v32",
    profile_id=V32_PROFILE_ID,
    phase=V32_PHASE,
    symbols=V32_SYMBOLS,
    poststart_schema="v32_poststart_acceptance_v1",
    raw_ledger_schema="v32_raw_ledger_acceptance_v1",
    snapshot_schema="v32_acceptance_snapshot_v1",
    journal_revision=3,
    candidate_evidence_role="inactive_exact_delta_v32_candidate",
    executable_routes=21,
    observe_only_routes=3,
)

_BUILDERS = CandidateAcceptanceBuilders(V32_ACCEPTANCE_SPEC)
build_v32_poststart_acceptance = _BUILDERS.build_poststart
build_v32_raw_ledger_acceptance = _BUILDERS.build_raw_ledger
