#!/usr/bin/env python3
"""Acquire preregistered official IBIT history without candidate outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.blackrock_ibit_acquisition import (
    BLACKROCK_IBIT_HISTORY_URL,
    acquire_blackrock_ibit_history_bundle,
)


_HYPOTHESIS = "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1"
_SCHEMA = "v58_btc_ibit_creation_persistence_long_preregistration_v1"
_STATUS = "preregistered_before_blackrock_source_acquisition_or_candidate_results"
_ADDENDUM_SCHEMA = "v58_btc_ibit_creation_persistence_long_source_integrity_addendum_v1"
_ADDENDUM_STATUS = (
    "frozen_after_failed_technical_acquisition_before_candidate_signal_or_"
    "return_results"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed-source, report-only acquisition parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-btc-ibit-creation-persistence-long-"
            "preregistration-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--source-integrity-addendum",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-btc-ibit-creation-persistence-long-source-integrity-"
            "addendum-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/cache/vendor/blackrock/IBIT/20240105_20260820_history_v1"),
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Validate preregistration and publish the source-only bundle."""
    context = _preregistration_context(
        args.preregistration,
        args.source_integrity_addendum,
    )
    return acquire_blackrock_ibit_history_bundle(
        args.output,
        _fetch_bytes,
        context=context,
    )


def main() -> int:
    """Acquire the frozen source and print its immutable bundle path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _preregistration_context(
    path: Path,
    addendum_path: Path,
) -> dict[str, object]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"BTC IBIT preregistration is missing: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA:
        raise ValueError("BTC IBIT preregistration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS or payload.get("status") != _STATUS:
        raise ValueError("BTC IBIT preregistration identity drifted")
    _validate_authority(payload)
    _validate_unacquired_source(payload)
    return {
        "hypothesis_id": _HYPOTHESIS,
        "execution_authority": "none",
        "preregistration": {"path": str(resolved), **file_evidence(resolved)},
        "source_integrity_addendum": _validated_addendum(addendum_path),
        "candidate_results_inspected_before_acquisition": False,
    }


def _validated_addendum(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"BTC IBIT source addendum is missing: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        _ADDENDUM_SCHEMA
    ):
        raise ValueError("BTC IBIT source addendum schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BTC IBIT source addendum identity drifted")
    if payload.get("status") != _ADDENDUM_STATUS:
        raise ValueError("BTC IBIT source addendum status drifted")
    _validate_addendum_authority(payload)
    _validate_addendum_rule(payload)
    return {"path": str(resolved), **file_evidence(resolved)}


def _validate_addendum_authority(payload: dict[str, object]) -> None:
    authority = payload.get("authority")
    if not isinstance(authority, dict) or authority.get("report_only") is not True:
        raise ValueError("BTC IBIT source addendum is not report-only")
    if authority.get("execution_authority") != "none":
        raise ValueError("BTC IBIT source addendum acquired execution authority")
    trigger = payload.get("trigger")
    if not isinstance(trigger, dict) or any(
        trigger.get(key) is not False
        for key in (
            "candidate_signal_count_inspected",
            "candidate_returns_inspected",
            "candidate_pnl_inspected",
        )
    ):
        raise ValueError("BTC IBIT source addendum is not outcome-blind")


def _validate_addendum_rule(payload: dict[str, object]) -> None:
    rule = payload.get("frozen_normalization_rule")
    if not isinstance(rule, dict):
        raise ValueError("BTC IBIT source addendum lacks normalization rule")
    if rule.get("frozen_market_start") != "2025-07-28T00:00:00Z":
        raise ValueError("BTC IBIT source addendum market start drifted")
    if rule.get("allowed_placeholder_token") != "--":
        raise ValueError("BTC IBIT source addendum placeholder token drifted")


def _validate_authority(payload: dict[str, object]) -> None:
    authority = payload.get("authority")
    if not isinstance(authority, dict):
        raise ValueError("BTC IBIT preregistration lacks authority contract")
    if authority.get("report_only") is not True:
        raise ValueError("BTC IBIT preregistration is not report-only")
    if authority.get("execution_authority") != "none":
        raise ValueError("BTC IBIT preregistration acquired execution authority")


def _validate_unacquired_source(payload: dict[str, object]) -> None:
    sources = payload.get("source_evidence")
    if not isinstance(sources, dict):
        raise ValueError("BTC IBIT preregistration lacks source evidence")
    source = sources.get("blackrock_ibit_history")
    if not isinstance(source, dict) or source.get("state") != (
        "not_acquired_before_preregistration"
    ):
        raise ValueError("BTC IBIT source was not outcome-blind at preregistration")
    if source.get("source_url") != BLACKROCK_IBIT_HISTORY_URL:
        raise ValueError("BTC IBIT preregistration source URL drifted")
    if any(source.get(key) is not None for key in ("path", "bytes", "sha256")):
        raise ValueError("BTC IBIT preregistration already binds source results")


def _fetch_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


if __name__ == "__main__":
    raise SystemExit(main())
