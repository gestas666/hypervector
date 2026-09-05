#!/usr/bin/env python3
"""Acquire preregistered official BTC DVOL history without outcomes."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

import requests

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.deribit_dvol_acquisition import (
    DERIBIT_DVOL_URL,
    PageFetcher,
    acquire_deribit_dvol_bundle,
)


_HYPOTHESIS = "V58_BTC_DVOL_VRP_CONTINUATION_LONG_V1"
_SCHEMA = "v58_btc_dvol_vrp_continuation_long_preregistration_v1"
_STATUS = "preregistered_before_source_acquisition_or_outcomes"
_START = "2025-07-28T00:00:00Z"
_END = "2026-07-28T00:00:00Z"


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed-source, report-only acquisition parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-btc-dvol-vrp-continuation-long-"
            "preregistration-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/cache/vendor/deribit/BTC_DVOL/"
            "20250728T000000Z_20260728T000000Z_hourly_v1"
        ),
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Validate preregistration and publish the source-only bundle."""
    context = _preregistration_context(args.preregistration)
    fetcher: PageFetcher = _fetch_bytes
    return acquire_deribit_dvol_bundle(args.output, fetcher, context=context)


def main() -> int:
    """Acquire the frozen source and print its immutable bundle path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _preregistration_context(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"BTC DVOL preregistration is missing: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA:
        raise ValueError("BTC DVOL preregistration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS or payload.get("status") != _STATUS:
        raise ValueError("BTC DVOL preregistration identity drifted")
    _validate_authority(payload)
    _validate_outcome_blind(payload)
    _validate_source_contract(payload)
    return {
        "hypothesis_id": _HYPOTHESIS,
        "execution_authority": "none",
        "preregistration": {"path": str(resolved), **file_evidence(resolved)},
        "candidate_results_inspected_before_acquisition": False,
    }


def _validate_authority(payload: dict[str, object]) -> None:
    if payload.get("execution_authority") != "none":
        raise ValueError("BTC DVOL preregistration gained execution authority")
    if payload.get("automatic_promotion") not in (False, None):
        raise ValueError("BTC DVOL preregistration allows automatic promotion")
    if payload.get("runtime_strategy_changed") not in (False, None):
        raise ValueError("BTC DVOL preregistration changed the runtime strategy")


def _validate_outcome_blind(payload: dict[str, object]) -> None:
    fields = (
        "outcomes_inspected_before_preregistration",
        "candidate_signal_counts_inspected",
        "candidate_forward_returns_inspected",
        "candidate_trade_outcomes_inspected",
    )
    if any(payload.get(field) is not False for field in fields):
        raise ValueError("BTC DVOL preregistration is not outcome-blind")


def _validate_source_contract(payload: dict[str, object]) -> None:
    source = payload.get("source_contract")
    if not isinstance(source, dict):
        raise ValueError("BTC DVOL preregistration lacks source contract")
    if source.get("source_acquisition_state") != (
        "not_acquired_before_preregistration"
    ):
        raise ValueError("BTC DVOL preregistration source state drifted")
    if source.get("endpoint") != DERIBIT_DVOL_URL:
        raise ValueError("BTC DVOL preregistration endpoint drifted")
    if source.get("outcome_blind_coverage_expected_inclusive") != 8_761:
        raise ValueError("BTC DVOL preregistration expected coverage drifted")
    _validate_parameters(source.get("parameters"))


def _validate_parameters(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("BTC DVOL preregistration lacks source parameters")
    expected: dict[str, object] = {
        "currency": "BTC",
        "resolution": "3600",
        "start_utc": _START,
        "end_utc": _END,
    }
    if any(
        value.get(key) != expected_value for key, expected_value in expected.items()
    ):
        raise ValueError("BTC DVOL preregistration source parameters drifted")


def _fetch_bytes(url: str, params: Mapping[str, str | int]) -> bytes:
    response = requests.get(url, params=dict(params), timeout=120)
    response.raise_for_status()
    return response.content


if __name__ == "__main__":
    raise SystemExit(main())
