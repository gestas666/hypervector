#!/usr/bin/env python3
"""Acquire preregistered BTC option-flow source evidence without outcomes."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

import requests

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.deribit_option_trade_acquisition import (
    DERIBIT_INSTRUMENTS_URL,
    DERIBIT_OPTION_TRADES_URL,
    PageFetcher,
    TradeWindow,
    acquire_deribit_option_bundle,
)


_HYPOTHESIS = "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1"
_SCHEMA = "v58_btc_deribit_option_flow_long_preregistration_v1"
_STATUS = (
    "preregistered_after_schema_preflight_before_full_source_"
    "acquisition_or_candidate_outcomes"
)
_START = "2025-04-01T00:00:00Z"
_END = "2026-08-01T00:00:00Z"
START_TIMESTAMP_MS = 1_743_465_600_000
END_TIMESTAMP_MS = 1_785_542_400_000


def build_parser() -> argparse.ArgumentParser:
    """Return the frozen source-only acquisition parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-btc-deribit-option-flow-long-preregistration-20260822-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/cache/vendor/deribit/BTC_OPTIONS/"
            "20250401T000000Z_20260801T000000Z_directional_flow_v1"
        ),
    )
    parser.add_argument("--max-requests-per-day", type=int, default=64)
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Validate preregistration and publish the source-only bundle."""
    context = _preregistration_context(args.preregistration)
    window = TradeWindow(START_TIMESTAMP_MS, END_TIMESTAMP_MS)
    fetcher: PageFetcher = _fetch_bytes
    return acquire_deribit_option_bundle(
        args.output,
        fetcher,
        window=window,
        max_requests_per_day=args.max_requests_per_day,
        context=context,
    )


def main() -> int:
    """Acquire the frozen source and print its immutable bundle path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _preregistration_context(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"BTC option-flow preregistration is missing: {resolved}"
        )
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA:
        raise ValueError("BTC option-flow preregistration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS or payload.get("status") != _STATUS:
        raise ValueError("BTC option-flow preregistration identity drifted")
    _validate_authority(payload)
    _validate_outcome_blind(payload)
    _validate_source_contract(payload)
    qualification = _qualification_evidence(resolved, payload)
    return {
        "hypothesis_id": _HYPOTHESIS,
        "execution_authority": "none",
        "live_change_authorized": False,
        "candidate_outcomes_inspected_before_acquisition": False,
        "preregistration": {"path": str(resolved), **file_evidence(resolved)},
        "source_qualification": qualification,
    }


def _validate_authority(payload: dict[str, object]) -> None:
    expected = {
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "orders_supported": False,
        "live_change_authorized": False,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("BTC option-flow preregistration gained live authority")


def _validate_outcome_blind(payload: dict[str, object]) -> None:
    fields = (
        "outcomes_inspected_before_preregistration",
        "candidate_signal_counts_inspected",
        "candidate_forward_returns_inspected",
        "candidate_trade_outcomes_inspected",
    )
    if any(payload.get(field) is not False for field in fields):
        raise ValueError("BTC option-flow preregistration is not outcome-blind")


def _validate_source_contract(payload: dict[str, object]) -> None:
    source = payload.get("source_contract")
    if not isinstance(source, dict):
        raise ValueError("BTC option-flow preregistration lacks source contract")
    _validate_trade_source(source.get("deribit_trades"))
    _validate_instrument_source(source.get("deribit_instruments"))


def _validate_trade_source(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("BTC option-flow preregistration lacks trade source")
    expected: dict[str, object] = {
        "endpoint": DERIBIT_OPTION_TRADES_URL,
        "currency": "BTC",
        "kind": "option",
        "include_old": True,
        "sorting": "asc",
        "start_utc": _START,
        "end_utc": _END,
        "maximum_count": 10_000,
    }
    if any(
        value.get(key) != expected_value for key, expected_value in expected.items()
    ):
        raise ValueError("BTC option-flow trade source drifted")


def _validate_instrument_source(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("BTC option-flow preregistration lacks instrument source")
    expected: dict[str, object] = {
        "endpoint": DERIBIT_INSTRUMENTS_URL,
        "currency": "BTC",
        "kind": "option",
        "expired": True,
    }
    if any(
        value.get(key) != expected_value for key, expected_value in expected.items()
    ):
        raise ValueError("BTC option-flow instrument source drifted")


def _qualification_evidence(
    preregistration: Path,
    payload: dict[str, object],
) -> dict[str, object]:
    value = payload.get("source_qualification")
    if not isinstance(value, dict):
        raise ValueError("BTC option-flow preregistration lacks source qualification")
    relative = value.get("path")
    if not isinstance(relative, str) or not relative:
        raise ValueError("BTC option-flow qualification path is invalid")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("BTC option-flow qualification path is unsafe")
    resolved = (preregistration.parent / candidate).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"BTC option-flow qualification is missing: {resolved}")
    observed = file_evidence(resolved)
    if observed.get("sha256") != value.get("sha256"):
        raise ValueError("BTC option-flow qualification SHA-256 drifted")
    if observed.get("bytes") != value.get("bytes"):
        raise ValueError("BTC option-flow qualification byte count drifted")
    return {"path": str(resolved), **observed}


def _fetch_bytes(
    url: str,
    parameters: Mapping[str, str | int | bool],
) -> bytes:
    response = requests.get(url, params=dict(parameters), timeout=120)
    response.raise_for_status()
    return response.content


if __name__ == "__main__":
    raise SystemExit(main())
