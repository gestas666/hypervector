"""Shared immutable report projection for candidate raw-ledger acceptance."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json

from hypervector.research.cohort_live_audit_values import nonnegative_int, text
from hypervector.research.v31_raw_identity import (
    raw_acceptance_contract,
    raw_acceptance_limitations,
)

Record = Mapping[str, object]


def build_raw_acceptance_report(
    checkpoint: Record,
    aggregate: Record,
    identity: Mapping[str, str],
    routing: Record,
    books: Record,
    funding: Record,
    payments: Record,
    reasons: list[str],
    *,
    schema_version: str,
) -> dict[str, object]:
    """Return an execution-incapable raw-ledger acceptance report."""
    accepted = not reasons
    return {
        "schema_version": schema_version,
        "contract": raw_acceptance_contract(),
        "accepted": accepted,
        "decision": "accepted" if accepted else "rejected",
        "reasons": reasons,
        "source_checkpoint_generated_at_utc": text(
            checkpoint.get("generated_at_utc"), "checkpoint generation time"
        ),
        "run": dict(identity),
        "target_routing_sequence": nonnegative_int(
            routing.get("sequence"), "target routing sequence"
        ),
        "checks": {
            "aggregate_acceptance": {
                "passed": aggregate.get("accepted") is True,
                "sha256": _payload_sha256(aggregate),
            },
            "causal_pressure_books": dict(books),
            "funding_cursor_continuity": dict(funding),
            "funding_payment_uniqueness": dict(payments),
        },
        "limitations": raw_acceptance_limitations(),
    }


def _payload_sha256(payload: Record) -> str:
    encoded = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
