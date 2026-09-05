#!/usr/bin/env python3
"""Acquire exact missing Deribit instrument metadata without candidate signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.deribit_instrument_supplement import (
    acquire_deribit_instrument_supplement,
)


_ENDPOINT = "https://history.deribit.com/api/v2/public/get_instrument"
_AUDIT = Path(
    "docs/research-journal/"
    "v58-btc-deribit-instrument-completeness-audit-20260822-v1.json"
)
_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v4.json"
)
_OUTPUT = Path(
    "data/cache/vendor/deribit/BTC_OPTIONS/"
    "20260822T000000Z_exact_missing_instruments_v1"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the exact source-only acquisition parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completeness-audit", type=Path, default=_AUDIT)
    parser.add_argument("--preregistration", type=Path, default=_PREREGISTRATION)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--max-workers", type=int, default=8)
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Validate the amendment and acquire the bound exact-name dictionary."""
    audit = _load_mapping(args.completeness_audit)
    preregistration = _load_mapping(args.preregistration)
    _validate_inputs(audit, preregistration, args.completeness_audit)
    names = audit.get("unmatched_instrument_names")
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError("Deribit instrument completeness names are invalid")
    return acquire_deribit_instrument_supplement(
        args.output,
        names,
        _fetch_exact_instrument,
        max_workers=args.max_workers,
        context={
            "hypothesis_id": "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1",
            "execution_authority": "none",
            "live_change_authorized": False,
            "candidate_signals_computed": False,
            "candidate_outcomes_computed": False,
            "completeness_audit": {
                "path": str(args.completeness_audit.resolve()),
                **file_evidence(args.completeness_audit),
            },
            "preregistration": {
                "path": str(args.preregistration.resolve()),
                **file_evidence(args.preregistration),
            },
        },
    )


def _validate_inputs(
    audit: dict[str, object],
    preregistration: dict[str, object],
    audit_path: Path,
) -> None:
    if audit.get("status") != (
        "instrument_dictionary_gap_identified_before_candidate_signals"
    ):
        raise ValueError("Deribit instrument completeness audit identity drifted")
    if preregistration.get("schema_version") != (
        "v58_btc_deribit_option_flow_long_preregistration_v4"
    ):
        raise ValueError("Deribit instrument supplement preregistration drifted")
    revision = preregistration.get("instrument_dictionary_revision")
    if not isinstance(revision, dict):
        raise ValueError("Deribit instrument supplement revision is missing")
    evidence = revision.get("completeness_audit")
    if not isinstance(evidence, dict) or file_evidence(audit_path) != {
        "sha256": evidence.get("sha256"),
        "bytes": evidence.get("bytes"),
    }:
        raise ValueError("Deribit instrument completeness audit hash drifted")
    if preregistration.get("candidate_signal_counts_inspected") is not False:
        raise ValueError("Deribit instrument preregistration opened signals")


def _fetch_exact_instrument(name: str) -> bytes:
    response = requests.get(
        _ENDPOINT,
        params={"instrument_name": name},
        timeout=60,
    )
    response.raise_for_status()
    return response.content


def _load_mapping(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Deribit instrument input must be an object: {path}")
    return value


def main() -> int:
    """Acquire the supplement and print its immutable path."""
    print(run_command(build_parser().parse_args()).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
