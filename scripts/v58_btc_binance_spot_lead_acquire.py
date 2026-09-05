#!/usr/bin/env python3
"""Acquire the preregistered Binance BTCUSDT spot source without outcomes."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

import requests

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.binance_spot_archive_acquisition import (
    acquire_binance_spot_kline_bundle,
)


_HYPOTHESIS = "V58_BTC_BINANCE_SPOT_LEAD_HL_PERP_CATCHUP_LONG_V1"
_SCHEMA = "v58_btc_binance_spot_lead_hl_perp_catchup_preregistration_v1"
_STATUS = "preregistered_before_external_spot_data_acquisition_or_candidate_results"
_START = datetime(2025, 7, 28, tzinfo=UTC)
_END = datetime(2026, 7, 28, tzinfo=UTC)


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed-window, report-only acquisition parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-btc-binance-spot-lead-hl-perp-catchup-"
            "preregistration-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/cache/vendor/binance/BTCUSDT/"
            "20250728T000000Z_20260728T000000Z_spot_1m_v58_lead_v1"
        ),
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Validate the preregistration and publish the vendor source bundle."""
    context = _preregistration_context(args.preregistration)
    return acquire_binance_spot_kline_bundle(
        args.output,
        _START,
        _END,
        _fetch_bytes,
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
        raise FileNotFoundError(f"BTC spot-lead preregistration is missing: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA:
        raise ValueError("BTC spot-lead preregistration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS or payload.get("status") != _STATUS:
        raise ValueError("BTC spot-lead preregistration identity drifted")
    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("execution_authority") != "none"
    ):
        raise ValueError("BTC spot-lead preregistration acquired execution authority")
    _validate_unacquired_source(payload)
    return {
        "hypothesis_id": _HYPOTHESIS,
        "preregistration": {"path": str(resolved), **file_evidence(resolved)},
        "candidate_results_inspected_before_acquisition": False,
    }


def _validate_unacquired_source(payload: dict[str, object]) -> None:
    sources = payload.get("source_evidence")
    if not isinstance(sources, dict):
        raise ValueError("BTC spot-lead preregistration lacks source evidence")
    spot = sources.get("binance_spot_bars")
    if not isinstance(spot, dict) or spot.get("state") != (
        "not_acquired_before_preregistration"
    ):
        raise ValueError(
            "BTC spot-lead source was not outcome-blind at preregistration"
        )
    if any(spot.get(key) is not None for key in ("path", "bytes", "sha256")):
        raise ValueError("BTC spot-lead preregistration already binds spot results")


def _fetch_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


if __name__ == "__main__":
    raise SystemExit(main())
