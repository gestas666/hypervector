#!/usr/bin/env python3
"""Freeze the outcome-blind post-entry execution-horizon revision."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json


_V2_SCHEMA = "v58_btc_deribit_option_flow_long_preregistration_v2"
_V3_SCHEMA = "v58_btc_deribit_option_flow_long_preregistration_v3"
_HYPOTHESIS = "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1"
_ENTRY_END = "2026-08-01T00:00:00Z"
_EXECUTION_END = "2026-08-02T00:00:00Z"
_V2 = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v2.json"
)
_AUDIT = Path(
    "docs/research-journal/v58-btc-option-flow-execution-horizon-audit-20260822-v1.json"
)
_OUTPUT = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v3.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the execution-horizon preregistration parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revised-preregistration", type=Path, default=_V2)
    parser.add_argument("--horizon-audit", type=Path, default=_AUDIT)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--recorded-at-utc", required=True)
    return parser


def build_revision(
    prior: Mapping[str, object],
    audit: Mapping[str, object],
    *,
    recorded_at_utc: str,
    audit_evidence: Mapping[str, object],
) -> dict[str, object]:
    """Add only the lifecycle-resolution horizon to the frozen v2 contract."""
    _validate_prior(prior)
    _validate_audit(audit)
    revised = deepcopy(dict(prior))
    revised["schema_version"] = _V3_SCHEMA
    revised["recorded_at_utc"] = _validated_recorded_at(recorded_at_utc)
    revised["status"] = (
        "execution_horizon_revision_preregistered_before_candidate_outcomes"
    )
    revised["execution_horizon_revision"] = {
        "revision_id": "post_entry_24h_execution_horizon_v3",
        "candidate_outcomes_opened": False,
        "candidate_signals_opened": False,
        "candidate_parameters_changed": False,
        "within_family_trial_number_changed": False,
        "audit": dict(audit_evidence),
    }
    _revise_market_horizons(revised, audit)
    revised["single_highest_value_next_investigation"] = (
        "Register the completed immutable Deribit source and run the exact frozen "
        "candidate with full 24-hour post-entry market evidence."
    )
    return revised


def run_command(args: argparse.Namespace) -> Path:
    """Validate the horizon evidence and publish immutable v3."""
    prior = _load_mapping(args.revised_preregistration)
    audit = _load_mapping(args.horizon_audit)
    revised = build_revision(
        prior,
        audit,
        recorded_at_utc=args.recorded_at_utc,
        audit_evidence={
            "path": args.horizon_audit.name,
            **file_evidence(args.horizon_audit),
        },
    )
    write_immutable_json(args.output, revised)
    return args.output


def main() -> int:
    """Publish v3 and print its immutable path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _validate_prior(value: Mapping[str, object]) -> None:
    if value.get("schema_version") != _V2_SCHEMA:
        raise ValueError("v2 option-flow preregistration schema drifted")
    if value.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("v2 option-flow hypothesis identity drifted")
    false_fields = (
        "automatic_promotion",
        "runtime_strategy_changed",
        "orders_supported",
        "live_change_authorized",
        "outcomes_inspected_before_preregistration",
        "candidate_signal_counts_inspected",
        "candidate_forward_returns_inspected",
        "candidate_trade_outcomes_inspected",
    )
    if value.get("execution_authority") != "none" or any(
        value.get(field) is not False for field in false_fields
    ):
        raise ValueError("v2 option-flow preregistration is not outcome-blind")


def _validate_audit(value: Mapping[str, object]) -> None:
    expected = (
        "required_post_entry_execution_horizon_qualified_before_candidate_outcomes"
    )
    if value.get("status") != expected:
        raise ValueError("option-flow execution-horizon audit status drifted")
    if value.get("entry_source_end_utc") != _ENTRY_END:
        raise ValueError("option-flow entry-source boundary drifted")
    if value.get("required_execution_end_utc") != _EXECUTION_END:
        raise ValueError("option-flow execution-horizon boundary drifted")
    blindness = _mapping(value, "outcome_blindness")
    if blindness.get("candidate_trade_outcomes_inspected") is not False:
        raise ValueError("execution-horizon audit opened candidate outcomes")


def _revise_market_horizons(
    revised: dict[str, object], audit: Mapping[str, object]
) -> None:
    sources = _mapping(revised, "source_contract")
    candles = _mapping(sources, "hyperliquid_btc_minutes")
    funding = _mapping(sources, "hyperliquid_funding")
    if candles.get("end_utc") != _ENTRY_END or funding.get("end_utc") != _ENTRY_END:
        raise ValueError("v2 market source end boundary drifted")
    candles["entry_source_end_utc"] = _ENTRY_END
    candles["execution_end_utc"] = _EXECUTION_END
    candles["execution_horizon_source"] = deepcopy(
        _mapping(audit, "candle_horizon_source")
    )
    funding["entry_source_end_utc"] = _ENTRY_END
    funding["execution_end_utc"] = _EXECUTION_END
    funding["execution_horizon_source"] = deepcopy(
        _mapping(audit, "funding_horizon_source")
    )


def _load_mapping(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"option-flow horizon evidence is missing: {path}")
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"option-flow horizon evidence must be an object: {path}")
    return value


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"option-flow horizon evidence lacks object: {key}")
    return nested


def _validated_recorded_at(value: str) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("recorded_at_utc must be timezone-aware")
    return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
