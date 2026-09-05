#!/usr/bin/env python3
"""Publish the outcome-blind BTC option-flow candle cadence audit."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_candles import (
    OxaCandleRequest,
    read_complete_candle_evidence,
    repair_candle_cadence,
)
from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.btc_option_flow_candle_audit import (
    build_candle_source_record,
)


_HYPOTHESIS = "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1"
_BROAD_BUNDLE = Path(
    "data/cache/vendor/0xarchive/hyperliquid/BTC/"
    "20250401T000000000000Z_20260801T000000000000Z_candles_1m"
)
_REVISED_BUNDLE = Path(
    "data/cache/vendor/0xarchive/hyperliquid/BTC/"
    "20250801T000000000000Z_20260801T000000000000Z_candles_1m"
)
_OUTPUT = Path(
    "docs/research-journal/v58-btc-option-flow-candle-cadence-audit-20260822-v1.json"
)
_BROAD_START = pd.Timestamp("2025-04-01T00:00:00Z")
_REVISED_START = pd.Timestamp("2025-08-01T00:00:00Z")
_END = pd.Timestamp("2026-08-01T00:00:00Z")
_MAXIMUM_REPAIR_MINUTES = 30


def build_parser() -> argparse.ArgumentParser:
    """Return the exact source-audit command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broad-bundle", type=Path, default=_BROAD_BUNDLE)
    parser.add_argument("--revised-bundle", type=Path, default=_REVISED_BUNDLE)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--recorded-at-utc", required=True)
    return parser


def build_report(
    *,
    recorded_at_utc: str,
    broad: Mapping[str, object],
    revised: Mapping[str, object],
    revised_repair_count: int,
) -> dict[str, object]:
    """Build a source-only report that grants no economic or live authority."""
    _require_contract_result(broad, expected=False, label="original")
    _require_contract_result(revised, expected=True, label="revised")
    revised_payload = dict(revised)
    revised_payload["deterministic_gap_fill_count"] = revised_repair_count
    return {
        "schema_version": "v58_btc_option_flow_candle_cadence_audit_v1",
        "hypothesis_id": _HYPOTHESIS,
        "recorded_at_utc": _validated_recorded_at(recorded_at_utc),
        "status": "original_source_failed_revised_source_passed_before_outcomes",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "live_change_authorized": False,
        "original_source": dict(broad),
        "revised_source": revised_payload,
        "outcome_blindness": _outcome_blindness(),
        "decision": (
            "Reject the 2025-04-01 candle contract and use the outcome-blind "
            "2025-08-01 source revision without changing candidate economics."
        ),
    }


def run_command(args: argparse.Namespace) -> Path:
    """Verify both immutable bundles and publish their cadence registration."""
    broad_frame, broad_evidence = _read_source(
        args.broad_bundle, start=_BROAD_START, max_pages=100
    )
    revised_frame, revised_evidence = _read_source(
        args.revised_bundle, start=_REVISED_START, max_pages=60
    )
    broad = _record(
        broad_frame, broad_evidence, "original_2025_04_01_v1", _BROAD_START, False
    )
    revised = _record(
        revised_frame,
        revised_evidence,
        "outcome_blind_2025_08_01_v2",
        _REVISED_START,
        True,
    )
    repaired, fills = repair_candle_cadence(
        revised_frame,
        start=_REVISED_START.to_pydatetime(),
        end=_END.to_pydatetime(),
        max_gap_minutes=_MAXIMUM_REPAIR_MINUTES,
    )
    _validate_repair(repaired, fills, revised)
    report = build_report(
        recorded_at_utc=args.recorded_at_utc,
        broad=broad,
        revised=revised,
        revised_repair_count=fills,
    )
    write_immutable_json(args.output, report)
    return args.output


def main() -> int:
    """Run the audit and print the immutable report path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _read_source(
    bundle: Path,
    *,
    start: pd.Timestamp,
    max_pages: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    request = OxaCandleRequest(
        symbol="BTC",
        start=start.to_pydatetime(),
        end=_END.to_pydatetime(),
        interval="1m",
        limit=10_000,
        max_pages=max_pages,
        timeout_seconds=120.0,
    )
    return read_complete_candle_evidence(bundle, request)


def _record(
    frame: pd.DataFrame,
    evidence: Mapping[str, object],
    revision: str,
    start: pd.Timestamp,
    expected: bool,
) -> dict[str, object]:
    return build_candle_source_record(
        frame,
        source_revision=revision,
        start=start,
        end=_END,
        maximum_repair_minutes=_MAXIMUM_REPAIR_MINUTES,
        expected_contract_pass=expected,
        evidence=evidence,
    )


def _validate_repair(
    repaired: pd.DataFrame,
    fills: int,
    source: Mapping[str, object],
) -> None:
    audit = _audit(source)
    if fills != audit.get("missing_rows"):
        raise ValueError("deterministic repair count differs from cadence audit")
    expected_rows = int((_END - _REVISED_START) / pd.Timedelta(minutes=1))
    if len(repaired) != expected_rows:
        raise ValueError("deterministic repair did not restore exact minute cadence")


def _require_contract_result(
    source: Mapping[str, object], *, expected: bool, label: str
) -> None:
    audit = _audit(source)
    if source.get("expected_contract_pass") is not expected:
        raise ValueError(f"{label} source expectation drifted")
    if audit.get("contract_pass") is not expected:
        raise ValueError(f"{label} source cadence result drifted")


def _audit(source: Mapping[str, object]) -> Mapping[str, object]:
    value = source.get("audit")
    if not isinstance(value, Mapping):
        raise ValueError("candle source record lacks an audit object")
    return value


def _validated_recorded_at(value: str) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("recorded_at_utc must be timezone-aware")
    return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def _outcome_blindness() -> dict[str, bool]:
    return {
        "candidate_signal_counts_inspected": False,
        "candidate_forward_returns_inspected": False,
        "candidate_trade_outcomes_inspected": False,
        "source_timestamps_and_integrity_only": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
