"""Append-only authoritative ledger for the Hulk Smash BTC canary."""

from pathlib import Path

from hypervector.live.sol_range_onset_ledger import (
    SOL_LIVE_EVENT_TYPES,
    SolLiveLedger,
    SolLiveLedgerError,
)

HULK_LIVE_EVENT_TYPES = SOL_LIVE_EVENT_TYPES | frozenset(
    {
        "regime_history",
        "protective_stop_plan",
        "target_order",
        "execution_quality",
        "fill_markout",
        "liquidation_distance",
    }
)
HulkSmashLiveLedgerError = SolLiveLedgerError


class HulkSmashLiveLedger(SolLiveLedger):
    """Durably record disarmed observations or explicitly armed BTC events."""

    event_types = HULK_LIVE_EVENT_TYPES

    def _validate_path(self, path: Path) -> None:
        parts = path.parts
        valid_domain = any(
            parts[index : index + 2] == ("live", "hulk_smash")
            for index in range(max(0, len(parts) - 1))
        )
        if not valid_domain or path.name != "decisions.jsonl":
            raise SolLiveLedgerError(
                "Hulk ledger path must end with live/hulk_smash/decisions.jsonl"
            )
