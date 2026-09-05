#!/usr/bin/env python3
"""Freeze the outcome-blind BTC option-flow source-window revision."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json


_V1_SCHEMA = "v58_btc_deribit_option_flow_long_preregistration_v1"
_V2_SCHEMA = "v58_btc_deribit_option_flow_long_preregistration_v2"
_HYPOTHESIS = "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1"
_ANALYSIS_START = "2025-08-01T00:00:00Z"
_DEVELOPMENT_START = "2025-10-01T00:00:00Z"
_END = "2026-08-01T00:00:00Z"
_V1 = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v1.json"
)
_AUDIT = Path(
    "docs/research-journal/v58-btc-option-flow-candle-cadence-audit-20260822-v1.json"
)
_FUNDING = Path(
    "data/cache/vendor/hyperliquid/BTC/"
    "20250801T000000000000Z_20260801T000000000000Z_funding"
)
_OUTPUT = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v2.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the source-revision preregistration parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, default=_V1)
    parser.add_argument("--cadence-audit", type=Path, default=_AUDIT)
    parser.add_argument("--funding-bundle", type=Path, default=_FUNDING)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--recorded-at-utc", required=True)
    return parser


def build_revision(
    original: Mapping[str, object],
    cadence_audit: Mapping[str, object],
    *,
    recorded_at_utc: str,
    audit_evidence: Mapping[str, object],
    funding_evidence: Mapping[str, object],
) -> dict[str, object]:
    """Create v2 while preserving all candidate-defining economics."""
    _validate_original(original)
    _validate_audit(cadence_audit)
    revised = deepcopy(dict(original))
    revised["schema_version"] = _V2_SCHEMA
    revised["recorded_at_utc"] = _validated_recorded_at(recorded_at_utc)
    revised["status"] = "source_revision_preregistered_before_candidate_outcomes"
    revised["source_revision"] = _source_revision(audit_evidence)
    _revise_sources(revised, cadence_audit, funding_evidence)
    _revise_partitions(revised)
    revised["single_highest_value_next_investigation"] = (
        "Register the completed immutable Deribit source, then execute the exact "
        "frozen feature and replay without parameter changes."
    )
    return revised


def run_command(args: argparse.Namespace) -> Path:
    """Verify all evidence and publish one immutable preregistration revision."""
    original = _load_mapping(args.original)
    cadence = _load_mapping(args.cadence_audit)
    funding = _funding_evidence(args.funding_bundle)
    revised = build_revision(
        original,
        cadence,
        recorded_at_utc=args.recorded_at_utc,
        audit_evidence={
            "path": args.cadence_audit.name,
            **file_evidence(args.cadence_audit),
        },
        funding_evidence=funding,
    )
    write_immutable_json(args.output, revised)
    return args.output


def main() -> int:
    """Publish v2 and print its immutable path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _validate_original(value: Mapping[str, object]) -> None:
    if value.get("schema_version") != _V1_SCHEMA:
        raise ValueError("original option-flow preregistration schema drifted")
    if value.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("original option-flow hypothesis identity drifted")
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
        raise ValueError("original preregistration is not outcome-blind report-only")


def _validate_audit(value: Mapping[str, object]) -> None:
    expected = "original_source_failed_revised_source_passed_before_outcomes"
    if value.get("status") != expected:
        raise ValueError("candle cadence audit status drifted")
    if _audit_pass(value, "original_source") is not False:
        raise ValueError("original candle source unexpectedly passed")
    if _audit_pass(value, "revised_source") is not True:
        raise ValueError("revised candle source did not pass")
    blindness = _mapping(value, "outcome_blindness")
    if blindness.get("candidate_trade_outcomes_inspected") is not False:
        raise ValueError("candle cadence audit opened candidate outcomes")


def _revise_sources(
    revised: dict[str, object],
    cadence: Mapping[str, object],
    funding: Mapping[str, object],
) -> None:
    sources = _mapping(revised, "source_contract")
    trades = _mapping(sources, "deribit_trades")
    original_start = trades.get("start_utc")
    if original_start != "2025-04-01T00:00:00Z":
        raise ValueError("Deribit acquisition start drifted")
    trades["acquisition_start_utc"] = original_start
    trades["start_utc"] = _ANALYSIS_START
    trades["analysis_filter"] = "event timestamp inside the half-open analysis window"
    minutes = _mapping(sources, "hyperliquid_btc_minutes")
    minutes["start_utc"] = _ANALYSIS_START
    minutes["registered_source"] = deepcopy(
        _mapping(_mapping(cadence, "revised_source"), "evidence")
    )
    funding_source = _mapping(sources, "hyperliquid_funding")
    funding_source["start_utc"] = _ANALYSIS_START
    funding_source["registered_source"] = dict(funding)


def _revise_partitions(revised: dict[str, object]) -> None:
    partitions = _mapping(revised, "partitions")
    partitions["source_warmup"] = [_ANALYSIS_START, _DEVELOPMENT_START]
    partitions["development_entries"] = [_DEVELOPMENT_START, "2025-12-01T00:00:00Z"]


def _source_revision(audit_evidence: Mapping[str, object]) -> dict[str, object]:
    return {
        "revision_id": "outcome_blind_2025_08_01_source_v2",
        "reason": (
            "The original candle window has gaps above the frozen 30-minute "
            "repair bound; the later source window has only bounded internal gaps."
        ),
        "candidate_outcomes_opened": False,
        "candidate_parameters_changed": False,
        "within_family_trial_number_changed": False,
        "candle_cadence_audit": dict(audit_evidence),
    }


def _funding_evidence(bundle: Path) -> dict[str, object]:
    manifest = bundle / "manifest.json"
    funding = bundle / "funding.parquet"
    if not manifest.is_file() or not funding.is_file():
        raise FileNotFoundError(f"registered funding bundle is incomplete: {bundle}")
    payload = _load_mapping(manifest)
    if (
        payload.get("missing_hour_count") != 0
        or payload.get("observed_hour_count") != 8760
    ):
        raise ValueError("registered funding bundle does not cover every expected hour")
    return {
        "bundle": str(bundle.resolve()),
        "manifest": file_evidence(manifest),
        "funding": file_evidence(funding),
        "observed_hour_count": 8760,
        "missing_hour_count": 0,
    }


def _load_mapping(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"required source revision evidence is missing: {path}")
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"required JSON evidence must be an object: {path}")
    return value


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"required object is missing: {key}")
    return nested


def _audit_pass(value: Mapping[str, object], key: str) -> object:
    return _mapping(_mapping(value, key), "audit").get("contract_pass")


def _validated_recorded_at(value: str) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("recorded_at_utc must be timezone-aware")
    return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
