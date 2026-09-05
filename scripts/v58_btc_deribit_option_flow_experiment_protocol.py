#!/usr/bin/env python3
"""Freeze exact BTC option-flow fold and bootstrap evaluation semantics."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json


_SCHEMA = "v58_btc_deribit_option_flow_long_preregistration_v3"
_HYPOTHESIS = "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1"
_INPUT = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v3.json"
)
_OUTPUT = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-experiment-protocol-20260822-v1.json"
)
_FOLDS = (
    ("2025-10-01T00:00:00Z", "2025-10-13T05:00:00Z"),
    ("2025-10-13T05:00:00Z", "2025-10-25T10:00:00Z"),
    ("2025-10-25T10:00:00Z", "2025-11-06T15:00:00Z"),
    ("2025-11-06T15:00:00Z", "2025-11-18T20:00:00Z"),
    ("2025-11-18T20:00:00Z", "2025-12-01T00:00:00Z"),
)


def build_parser() -> argparse.ArgumentParser:
    """Return the outcome-blind protocol generator parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, default=_INPUT)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--recorded-at-utc", required=True)
    return parser


def build_protocol(
    preregistration: Mapping[str, object],
    *,
    preregistration_evidence: Mapping[str, object],
    recorded_at_utc: str,
) -> dict[str, object]:
    """Build the exact fold/bootstrap protocol without opening outcomes."""
    _validate_preregistration(preregistration)
    return {
        "schema_version": "v58_btc_deribit_option_flow_experiment_protocol_v1",
        "hypothesis_id": _HYPOTHESIS,
        "recorded_at_utc": _utc_text(recorded_at_utc),
        "status": "evaluation_semantics_frozen_before_signals_or_outcomes",
        "preregistration": dict(preregistration_evidence),
        "development_folds": [
            {
                "fold_id": fold_id,
                "entry_start_utc": start,
                "entry_end_exclusive_utc": end,
            }
            for fold_id, (start, end) in enumerate(_FOLDS)
        ],
        "pooled_oos_trade_bootstrap": {
            "population": (
                "candidate nominal completed-trade net_pnl_usd pooled across "
                "validation and pseudo_holdout; each lifecycle appears once"
            ),
            "statistic": "arithmetic mean net_pnl_usd per completed trade",
            "resamples": 10_000,
            "seed": 58,
            "interval": "percentile_90pct_two_sided_quantiles_0.05_0.95",
        },
        "partition_lifecycle_rule": (
            "entry availability selects the half-open partition; the full frozen "
            "24-hour exit horizon remains observable after its entry boundary"
        ),
        "outcome_blindness": {
            "candidate_signals_computed": False,
            "candidate_signal_counts_inspected": False,
            "candidate_forward_returns_inspected": False,
            "candidate_trade_outcomes_inspected": False,
            "parameters_changed": False,
        },
        "authority": {
            "execution_authority": "none",
            "live_change_authorized": False,
            "automatic_promotion": False,
        },
    }


def run_command(args: argparse.Namespace) -> Path:
    """Validate the preregistration and publish an immutable protocol."""
    preregistration = _load_mapping(args.preregistration)
    protocol = build_protocol(
        preregistration,
        preregistration_evidence={
            "path": str(args.preregistration.resolve()),
            **file_evidence(args.preregistration),
        },
        recorded_at_utc=args.recorded_at_utc,
    )
    write_immutable_json(args.output, protocol)
    return args.output


def main() -> int:
    """Publish the protocol and print its path."""
    print(run_command(build_parser().parse_args()).resolve())
    return 0


def _validate_preregistration(value: Mapping[str, object]) -> None:
    if value.get("schema_version") != _SCHEMA:
        raise ValueError("option-flow experiment protocol preregistration drifted")
    if value.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("option-flow experiment protocol hypothesis drifted")
    if value.get("execution_authority") != "none":
        raise ValueError("option-flow preregistration gained execution authority")
    for field in (
        "candidate_signal_counts_inspected",
        "candidate_forward_returns_inspected",
        "candidate_trade_outcomes_inspected",
        "live_change_authorized",
    ):
        if value.get(field) is not False:
            raise ValueError(f"option-flow outcome-blind field drifted: {field}")
    partitions = _mapping(value, "partitions")
    expected = ["2025-10-01T00:00:00Z", "2025-12-01T00:00:00Z"]
    if partitions.get("development_entries") != expected:
        raise ValueError("option-flow development interval drifted")
    if partitions.get("development_walk_forward_folds") != len(_FOLDS):
        raise ValueError("option-flow development fold count drifted")


def _load_mapping(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"option-flow preregistration must be an object: {path}")
    return value


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"option-flow preregistration lacks object: {key}")
    return nested


def _utc_text(value: str) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("recorded_at_utc must be timezone-aware")
    return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
