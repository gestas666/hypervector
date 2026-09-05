#!/usr/bin/env python3
"""Wait for a closed HYPE-native path and publish exact research resolution."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from hypervector.data.hl_funding_archive import (
    HlFundingRequest,
    acquire_and_store_hl_funding,
    funding_output_directory,
)
from hypervector.data.oxa_api import OxaHistoryError
from hypervector.data.oxa_prices import (
    OxaPriceRequest,
    acquire_and_store_prices,
    price_output_directory,
)
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

_CLOSED_STATE = "resolved_proxy_lifecycle_evidence_available"
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only finalizer parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lifecycle-status", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--resolution-out", type=Path, required=True)
    parser.add_argument("--finalizer-status", type=Path, required=True)
    parser.add_argument("--decision-journal", type=Path, required=True)
    parser.add_argument("--decision-out", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--maximum-oracle-staleness-ms", type=int, default=120_000)
    parser.add_argument("--maximum-mark-gap-ms", type=int, default=120_000)
    return parser


def finalize_once(args: argparse.Namespace) -> bool:
    """Acquire and resolve once closed, or publish an explicit waiting state."""
    status = _json_object(args.lifecycle_status, "HYPE lifecycle status")
    if status.get("watch_state") != _CLOSED_STATE:
        _publish_status(args, "waiting_for_closed_lifecycle")
        return False
    snapshot = Path(_text(status.get("snapshot"), "closed snapshot path"))
    report = _json_object(snapshot, "HYPE closed snapshot")
    entry_ms, exit_ms = _lifecycle_bounds(report)
    funding_request, price_request = _evidence_requests(entry_ms, exit_ms)
    funding_path = _ensure_funding(funding_request, args.data_root)
    _ensure_prices(price_request, args.data_root)
    _run_resolution(snapshot, funding_path, price_request, args)
    _run_decision(args.resolution_out, args.decision_journal, args.decision_out)
    _publish_status(
        args,
        "resolved_exact_evidence_and_decision_published",
        snapshot=str(snapshot.resolve()),
        resolution=str(args.resolution_out.resolve()),
        decision=str(args.decision_out.resolve()),
    )
    return True


def run_loop(
    args: argparse.Namespace,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Poll until resolved while retrying only explicit evidence-boundary failures."""
    _validate_loop(args)
    cycles = 0
    while True:
        cycles += 1
        try:
            if finalize_once(args):
                return 0
        except (OxaHistoryError, RuntimeError, ValueError, OSError) as error:
            _publish_status(
                args,
                "exact_evidence_temporarily_unavailable",
                error_type=type(error).__name__,
                error=str(error),
            )
        if args.max_cycles and cycles >= args.max_cycles:
            return 0
        sleep_fn(args.poll_seconds)


def _evidence_requests(
    entry_ms: int, exit_ms: int
) -> tuple[HlFundingRequest, OxaPriceRequest]:
    entry = datetime.fromtimestamp(entry_ms / 1_000.0, tz=UTC)
    exit_time = datetime.fromtimestamp(exit_ms / 1_000.0, tz=UTC)
    funding_start = entry.replace(minute=0, second=0, microsecond=0)
    funding_end = exit_time.replace(minute=0, second=0, microsecond=0) + timedelta(
        hours=1
    )
    return (
        HlFundingRequest("HYPE", funding_start, funding_end),
        OxaPriceRequest("HYPE", entry, exit_time + timedelta(milliseconds=1)),
    )


def _ensure_funding(request: HlFundingRequest, data_root: Path) -> Path:
    directory = funding_output_directory(data_root, request)
    existing = directory / "funding.parquet"
    if existing.is_file() and (directory / "manifest.json").is_file():
        return existing
    report = acquire_and_store_hl_funding(data_root=data_root, request=request)
    return Path(_text(report.get("funding_path"), "funding result path"))


def _ensure_prices(request: OxaPriceRequest, data_root: Path) -> Path:
    directory = price_output_directory(data_root, request)
    existing = directory / "prices.parquet"
    if existing.is_file() and (directory / "manifest.json").is_file():
        return existing
    api_key = os.environ.get("OXA_API_KEY", "")
    if not api_key:
        raise RuntimeError("OXA_API_KEY is required for HYPE price resolution")
    report = acquire_and_store_prices(
        data_root=data_root,
        api_key=api_key,
        request=request,
    )
    return Path(_text(report.get("prices_path"), "price result path"))


def _run_resolution(
    snapshot: Path,
    funding: Path,
    price_request: OxaPriceRequest,
    args: argparse.Namespace,
) -> None:
    if args.resolution_out.exists():
        if _matching_resolution(args.resolution_out, snapshot):
            return
        raise FileExistsError(f"HYPE resolution output exists: {args.resolution_out}")
    command = _resolution_command(snapshot, funding, price_request, args)
    result = subprocess.run(
        command,
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[:2_000]
        raise RuntimeError(f"HYPE exact resolution failed: {detail}")
    if not args.resolution_out.is_file():
        raise RuntimeError("HYPE exact resolution published no output")


def _matching_resolution(output: Path, snapshot: Path) -> bool:
    report = _json_object(output, "HYPE existing resolution")
    contract = report.get("contract")
    evidence = report.get("evidence")
    if not isinstance(contract, Mapping) or not isinstance(evidence, Mapping):
        return False
    source = evidence.get("lifecycle_status")
    expected = file_evidence(snapshot)["sha256"]
    return (
        report.get("mode") == "hype_native_v54_exact_post_close_resolution_report_only"
        and contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and isinstance(source, Mapping)
        and source.get("sha256") == expected
    )


def _run_decision(resolution: Path, journal: Path, output: Path) -> None:
    if output.exists():
        if _matching_decision(output, resolution, journal):
            return
        raise FileExistsError(f"HYPE decision output exists: {output}")
    command = [
        sys.executable,
        "scripts/hype_native_third_forward_decision.py",
        "--resolution",
        str(resolution),
        "--preregistered-journal",
        str(journal),
        "--out",
        str(output),
    ]
    result = subprocess.run(
        command, cwd=_PROJECT_ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode or not output.is_file():
        detail = (result.stderr or result.stdout).strip()[:2_000]
        raise RuntimeError(f"HYPE third-forward decision failed: {detail}")


def _matching_decision(output: Path, resolution: Path, journal: Path) -> bool:
    report = _json_object(output, "HYPE existing decision")
    contract = report.get("contract")
    evidence = report.get("evidence")
    if not isinstance(contract, Mapping) or not isinstance(evidence, Mapping):
        return False
    source = evidence.get("resolution")
    preregistered = evidence.get("preregistered_journal")
    return (
        report.get("mode") == "hype_native_v54_third_forward_decision_report_only"
        and contract.get("execution_authority") == "none"
        and isinstance(source, Mapping)
        and source.get("sha256") == file_evidence(resolution)["sha256"]
        and isinstance(preregistered, Mapping)
        and preregistered.get("sha256") == file_evidence(journal)["sha256"]
    )


def _resolution_command(
    snapshot: Path,
    funding: Path,
    prices: OxaPriceRequest,
    args: argparse.Namespace,
) -> list[str]:
    return [
        sys.executable,
        "scripts/hype_native_prospective_resolution.py",
        "--lifecycle-status",
        str(snapshot),
        "--funding",
        str(funding),
        "--data-root",
        str(args.data_root),
        "--price-start",
        prices.start.isoformat(),
        "--price-end",
        prices.end.isoformat(),
        "--maximum-oracle-staleness-ms",
        str(args.maximum_oracle_staleness_ms),
        "--maximum-mark-gap-ms",
        str(args.maximum_mark_gap_ms),
        "--out",
        str(args.resolution_out),
    ]


def _lifecycle_bounds(report: Mapping[str, object]) -> tuple[int, int]:
    raw = report.get("lifecycles")
    if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], Mapping):
        raise ValueError("HYPE finalizer requires exactly one lifecycle")
    lifecycle = raw[0]
    if lifecycle.get("technical_path_resolved") is not True:
        raise ValueError("HYPE finalizer lifecycle is technically unresolved")
    entry = _integer(lifecycle.get("entry_book_time_ms"), "entry time")
    exit_time = _integer(lifecycle.get("exit_book_time_ms"), "exit time")
    if exit_time <= entry:
        raise ValueError("HYPE finalizer exit must follow entry")
    return entry, exit_time


def _publish_status(args: argparse.Namespace, state: str, **extra: object) -> None:
    write_atomic_json(
        args.finalizer_status,
        {
            "schema_version": 1,
            "mode": "hype_native_v54_prospective_finalizer_report_only",
            "state": state,
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "execution_authority": "none",
            "report_only": True,
            **extra,
        },
    )


def _json_object(path: Path, label: str) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _validate_loop(args: argparse.Namespace) -> None:
    if not math.isfinite(args.poll_seconds) or args.poll_seconds <= 0.0:
        raise ValueError("HYPE finalizer poll seconds must be positive and finite")
    if isinstance(args.max_cycles, bool) or args.max_cycles < 0:
        raise ValueError("HYPE finalizer max cycles must be nonnegative")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the singleton report-only finalizer."""
    args = build_parser().parse_args(argv)
    with cohort_checkpoint_runtime_lock(args.finalizer_status):
        return run_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
