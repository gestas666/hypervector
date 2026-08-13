"""Exact report-only acceptance entry points for the inactive v33 candidate."""

from __future__ import annotations

from hypervector.research.candidate_acceptance import (
    CandidateAcceptanceBuilders,
    CandidateAcceptanceSpec,
)
from hypervector.research.v31_raw_identity import V31_SYMBOLS

V33_PROFILE_ID = "multi_asset_bidirectional_spcx_swing_retired_candidate_v33"
V33_PHASE = "candidate_v33_forward"
V33_SYMBOLS = V31_SYMBOLS

V33_ACCEPTANCE_SPEC = CandidateAcceptanceSpec(
    version_label="v33",
    profile_id=V33_PROFILE_ID,
    phase=V33_PHASE,
    symbols=V33_SYMBOLS,
    poststart_schema="v33_poststart_acceptance_v1",
    raw_ledger_schema="v33_raw_ledger_acceptance_v1",
    snapshot_schema="v33_acceptance_snapshot_v1",
    journal_revision=4,
    candidate_evidence_role="inactive_exact_delta_v33_candidate",
    executable_routes=20,
    observe_only_routes=4,
)

_BUILDERS = CandidateAcceptanceBuilders(V33_ACCEPTANCE_SPEC)
build_v33_poststart_acceptance = _BUILDERS.build_poststart
build_v33_raw_ledger_acceptance = _BUILDERS.build_raw_ledger
