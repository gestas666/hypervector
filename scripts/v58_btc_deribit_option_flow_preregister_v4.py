#!/usr/bin/env python3
"""Freeze the exact-name instrument-dictionary supplement before signals."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json


_V3 = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v3.json"
)
_AUDIT = Path(
    "docs/research-journal/"
    "v58-btc-deribit-instrument-completeness-audit-20260822-v1.json"
)
_OUTPUT = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v4.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the source-amendment parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, default=_V3)
    parser.add_argument("--completeness-audit", type=Path, default=_AUDIT)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--recorded-at-utc", required=True)
    return parser


def build_revision(
    prior: Mapping[str, object],
    audit: Mapping[str, object],
    *,
    audit_evidence: Mapping[str, object],
    recorded_at_utc: str,
) -> dict[str, object]:
    """Add only exact official metadata recovery for anti-join names."""
    _validate_prior(prior)
    _validate_audit(audit)
    revised = deepcopy(dict(prior))
    revised["schema_version"] = "v58_btc_deribit_option_flow_long_preregistration_v4"
    revised["status"] = (
        "instrument_dictionary_revision_preregistered_before_candidate_signals"
    )
    revised["recorded_at_utc"] = _utc_text(recorded_at_utc)
    source = _mapping(revised, "source_contract")
    instruments = _mapping(source, "deribit_instruments")
    instruments["missing_name_supplement"] = {
        "endpoint": "https://history.deribit.com/api/v2/public/get_instrument",
        "selection": "exact left-anti-join names from bound completeness audit",
        "required_exact_name_match": True,
        "inference_permitted": False,
        "expected_instrument_count": audit.get("unmatched_instrument_count"),
        "completeness_audit": dict(audit_evidence),
    }
    revised["instrument_dictionary_revision"] = {
        "revision_id": "exact_missing_name_metadata_supplement_v4",
        "reason": (
            "The bulk expired-instrument snapshot omitted names present in the "
            "immutable trade source; exact official name lookups are required."
        ),
        "candidate_signals_opened": False,
        "candidate_outcomes_opened": False,
        "candidate_parameters_changed": False,
        "within_family_trial_number_changed": False,
        "completeness_audit": dict(audit_evidence),
    }
    revised["single_highest_value_next_investigation"] = (
        "Acquire and reproduce the exact missing-name instrument supplement, then "
        "re-run source registration before computing candidate signals."
    )
    return revised


def run_command(args: argparse.Namespace) -> Path:
    """Validate inputs and immutably publish v4."""
    prior = _load_mapping(args.preregistration)
    audit = _load_mapping(args.completeness_audit)
    revision = build_revision(
        prior,
        audit,
        audit_evidence={
            "path": str(args.completeness_audit.resolve()),
            **file_evidence(args.completeness_audit),
        },
        recorded_at_utc=args.recorded_at_utc,
    )
    write_immutable_json(args.output, revision)
    return args.output


def _validate_prior(value: Mapping[str, object]) -> None:
    if value.get("schema_version") != (
        "v58_btc_deribit_option_flow_long_preregistration_v3"
    ):
        raise ValueError("option-flow v3 preregistration drifted")
    false_fields = (
        "candidate_signal_counts_inspected",
        "candidate_forward_returns_inspected",
        "candidate_trade_outcomes_inspected",
        "live_change_authorized",
    )
    if value.get("execution_authority") != "none" or any(
        value.get(field) is not False for field in false_fields
    ):
        raise ValueError("option-flow v3 is not outcome-blind")


def _validate_audit(value: Mapping[str, object]) -> None:
    expected = "instrument_dictionary_gap_identified_before_candidate_signals"
    if value.get("status") != expected:
        raise ValueError("instrument completeness audit status drifted")
    count = value.get("unmatched_instrument_count")
    names = value.get("unmatched_instrument_names")
    if not isinstance(count, int) or not isinstance(names, list) or len(names) != count:
        raise ValueError("instrument completeness audit names drifted")
    blindness = _mapping(value, "outcome_blindness")
    if any(item is not False for item in blindness.values()):
        raise ValueError("instrument completeness audit opened candidate evidence")


def _load_mapping(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"option-flow source amendment must be an object: {path}")
    return value


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"option-flow source amendment lacks object: {key}")
    return nested


def _utc_text(value: str) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("recorded_at_utc must be timezone-aware")
    return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def main() -> int:
    """Publish v4 and print its path."""
    print(run_command(build_parser().parse_args()).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
