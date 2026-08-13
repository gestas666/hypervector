"""Append-only authoritative ledger for the BTC source-follow live canary."""

from pathlib import Path

from hypervector.live.sol_range_onset_ledger import (
    SOL_LIVE_EVENT_TYPES,
    SolLiveLedger,
    SolLiveLedgerError,
)

SOURCE_FOLLOW_LIVE_EVENT_TYPES = SOL_LIVE_EVENT_TYPES | frozenset(
    {"regime_history", "target_order"}
)
SourceFollowLiveLedgerError = SolLiveLedgerError


class SourceFollowLiveLedger(SolLiveLedger):
    """Reuse the durable event schema in a strictly separate BTC ledger domain."""

    event_types = SOURCE_FOLLOW_LIVE_EVENT_TYPES

    def _validate_path(self, path: Path) -> None:
        parts = path.parts
        valid_domain = any(
            parts[index : index + 2] == ("live", "hypervelocity_source_follow")
            for index in range(max(0, len(parts) - 1))
        )
        if not valid_domain or path.name != "decisions.jsonl":
            raise SolLiveLedgerError(
                "source-follow ledger path must end with "
                "live/hypervelocity_source_follow/decisions.jsonl"
            )
