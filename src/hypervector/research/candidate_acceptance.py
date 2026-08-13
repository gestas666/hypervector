"""Versioned identity bindings for exact candidate acceptance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.v31_poststart_acceptance import (
    build_candidate_poststart_acceptance,
)
from hypervector.research.v31_raw_ledger_acceptance import (
    build_candidate_raw_ledger_acceptance,
)

Record = Mapping[str, object]
AssetRecords = Mapping[str, Sequence[Record]]


@dataclass(frozen=True)
class CandidateAcceptanceSpec:
    """Bind acceptance schemas and authority counts to one candidate."""

    version_label: str
    profile_id: str
    phase: str
    symbols: tuple[str, ...]
    poststart_schema: str
    raw_ledger_schema: str
    snapshot_schema: str
    journal_revision: int
    candidate_evidence_role: str
    executable_routes: int
    observe_only_routes: int


@dataclass(frozen=True)
class CandidateAcceptanceBuilders:
    """Expose exact aggregate and raw acceptance for one version."""

    spec: CandidateAcceptanceSpec

    def build_poststart(
        self,
        checkpoint: Record,
        route_snapshot: Record,
        *,
        maximum_pressure_age_seconds: float = 30.0,
    ) -> dict[str, object]:
        """Return technical acceptance bound to this exact identity."""
        return build_candidate_poststart_acceptance(
            checkpoint,
            route_snapshot,
            expected_profile_id=self.spec.profile_id,
            expected_phase=self.spec.phase,
            schema_version=self.spec.poststart_schema,
            maximum_pressure_age_seconds=maximum_pressure_age_seconds,
        )

    def build_raw_ledger(
        self,
        checkpoint: Record,
        aggregate_acceptance: Record,
        cohort_records: Sequence[Record],
        asset_records: AssetRecords,
        *,
        maximum_pressure_age_seconds: float = 30.0,
    ) -> dict[str, object]:
        """Return raw-ledger acceptance bound to this exact identity."""
        return build_candidate_raw_ledger_acceptance(
            checkpoint,
            aggregate_acceptance,
            cohort_records,
            asset_records,
            expected_profile_id=self.spec.profile_id,
            symbols=self.spec.symbols,
            schema_version=self.spec.raw_ledger_schema,
            maximum_pressure_age_seconds=maximum_pressure_age_seconds,
        )
