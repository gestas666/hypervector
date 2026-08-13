"""Append-only authoritative ledger domain for the Apex MM live canary."""

from pathlib import Path

from hypervector.live.sol_range_onset_ledger import (
    SOL_LIVE_EVENT_TYPES,
    SolLiveLedger,
    SolLiveLedgerError,
)


APEX_MM_LIVE_EVENT_TYPES = SOL_LIVE_EVENT_TYPES | frozenset(
    {"execution_quality", "fill_markout", "liquidation_distance"}
)
ApexMMLiveLedgerError = SolLiveLedgerError


class ApexMMLiveLedger(SolLiveLedger):
    """Persist MM lifecycle facts in a strictly separate live domain."""

    event_types = APEX_MM_LIVE_EVENT_TYPES

    def _validate_path(self, path: Path) -> None:
        parts = path.parts
        valid_domain = any(
            parts[index : index + 2] == ("live", "apex_regime_mm")
            for index in range(max(0, len(parts) - 1))
        )
        if not valid_domain or path.name != "decisions.jsonl":
            raise SolLiveLedgerError(
                "Apex MM ledger path must end with live/apex_regime_mm/decisions.jsonl"
            )
