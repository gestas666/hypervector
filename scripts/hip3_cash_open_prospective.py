#!/usr/bin/env python3
"""Publish exact report-only SPCX cash-open prospective signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, cast

from hypervector.data.event_archive import EventArchive
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_cash_open_prospective import (
    Hip3CashOpenProspectiveSpec,
    build_hip3_cash_open_prospective_report,
)

_SYMBOL = "xyz:SPCX"
_PROVIDER_ID = "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_research_v1"
_PROFILE_ID = "spcx_cash_open_gap_reversal_15m_development_v1"


def build_parser() -> argparse.ArgumentParser:
    """Return the explicit immutable report parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path-audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Bind the frozen audit prefix and publish zero-authority signals."""
    audit_path = Path(args.path_audit)
    audit_evidence = file_evidence(audit_path)
    generator = _generator_identity()
    audit = _json_object(audit_path, "prospective path audit")
    start_ms, end_ms, observed_at_ms = _audit_bounds(audit)
    archive = EventArchive(
        data_root=Path(args.data_root), symbol=_SYMBOL, batch_size=2_000
    )
    report = build_hip3_cash_open_prospective_report(
        trades=archive.replay_trades(),
        start_ms=start_ms,
        end_ms=end_ms,
        observed_at_ms=observed_at_ms,
        spec=Hip3CashOpenProspectiveSpec(_SYMBOL, _PROVIDER_ID, _PROFILE_ID),
    )
    _reconcile_audit(report, audit)
    _require_unchanged(audit_path, audit_evidence, generator)
    report["path_audit"] = {
        "path": str(audit_path),
        **audit_evidence,
    }
    report["generator_identity"] = generator
    write_immutable_json(Path(args.output), report)
    return report


def _audit_bounds(audit: Mapping[str, object]) -> tuple[int, int, int]:
    source = _mapping(audit.get("source"), "audit source")
    coverage = _mapping(audit.get("coverage"), "audit coverage")
    if source.get("symbol") != _SYMBOL:
        raise ValueError("prospective path audit symbol differs from frozen SPCX")
    if coverage.get("timeframe_minutes") != 15:
        raise ValueError("prospective path audit must use completed 15m bars")
    return (
        _integer(coverage.get("first_full_bar_open_ms"), "audit start"),
        _integer(coverage.get("completed_bar_end_ms"), "audit end"),
        _integer(source.get("observed_at_ms"), "audit observed_at"),
    )


def _reconcile_audit(report: Mapping[str, object], audit: Mapping[str, object]) -> None:
    """Require the exact raw trade prefix already frozen by the path audit."""
    source = _mapping(report.get("source"), "prospective report source")
    identity = _mapping(audit.get("evidence_identity"), "audit identity")
    trades = _mapping(identity.get("completed_bar_trades"), "audit trades")
    actual = (source.get("raw_trade_rows"), source.get("raw_trade_sha256"))
    expected = (trades.get("rows"), trades.get("sha256"))
    if actual != expected:
        raise ValueError("prospective cash-open trade prefix differs from path audit")


def _require_unchanged(
    audit_path: Path,
    audit_evidence: Mapping[str, object],
    generator: Mapping[str, object],
) -> None:
    if file_evidence(audit_path) != audit_evidence:
        raise ValueError("prospective path audit changed during reconstruction")
    if _generator_identity() != generator:
        raise ValueError("prospective generator changed during reconstruction")


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/data/event_archive.py",
        root / "src/hypervector/data/hl_events.py",
        root / "src/hypervector/research/hip3_cash_open_gap_reversal_signals.py",
        root / "src/hypervector/research/hip3_cash_open_prospective.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _json_object(path: Path, label: str) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def main() -> int:
    """Run the immutable local-only reconstruction."""
    args = build_parser().parse_args()
    report = run_command(args)
    print(json.dumps({"output": str(args.output), "signals": report["signals"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
