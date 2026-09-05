#!/usr/bin/env python3
"""Publish immutable report-only post-v51 exposure evidence."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.v51_successor_exposure_ladder import (
    build_v51_successor_exposure_ladder,
)

_PROFILE_ID = "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51"
_DISPOSITION = Path("docs/research-journal/v51-successor-route-disposition-v1.json")
_FEE_PREFLIGHT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v51_final_flat_preflight_pre_observer_restart_20260813T2030Z.json"
)
_OUTPUT = Path("docs/research-journal/v51-successor-exposure-ladder-v2.json")
_GENERATOR = Path("scripts/v51_successor_exposure_ladder.py")
_BUILDER = Path("src/hypervector/research/v51_successor_exposure_ladder.py")

Record = Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build a mutation-incapable report command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disposition", type=Path, default=_DISPOSITION)
    parser.add_argument("--fee-preflight", type=Path, default=_FEE_PREFLIGHT)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--account-equity-usd", type=float, default=5_000.0)
    parser.add_argument("--slippage-stress-bps-per-side", type=float, default=2.0)
    return parser


def run(args: argparse.Namespace) -> int:
    """Build and atomically publish one source-bound advisory ladder."""
    evidence = _evidence(args.disposition, args.fee_preflight)
    disposition = _load(args.disposition, "successor disposition")
    preflight = _load(args.fee_preflight, "fee preflight")
    core_fee, hip3_fee = _fees(preflight)
    report = build_v51_successor_exposure_ladder(
        disposition,
        account_equity_usd=args.account_equity_usd,
        core_taker_fee_bps_per_side=core_fee,
        hip3_taker_fee_bps_per_side=hip3_fee,
        slippage_stress_bps_per_side=args.slippage_stress_bps_per_side,
    )
    report["evidence"] = evidence
    _require_unchanged(evidence)
    write_immutable_json(args.output, report)
    return 0


def _evidence(disposition: Path, preflight: Path) -> dict[str, object]:
    return {
        "disposition": {"path": str(disposition), **file_evidence(disposition)},
        "fee_preflight": {"path": str(preflight), **file_evidence(preflight)},
        "generator": {"path": str(_GENERATOR), **file_evidence(_GENERATOR)},
        "builder": {"path": str(_BUILDER), **file_evidence(_BUILDER)},
    }


def _require_unchanged(evidence: Record) -> None:
    for value in evidence.values():
        row = _mapping(value, "evidence row")
        path = Path(_text(row.get("path"), "evidence path"))
        observed = file_evidence(path)
        if any(observed.get(key) != row.get(key) for key in ("sha256", "bytes")):
            raise RuntimeError(f"exposure ladder input changed during build: {path}")


def _fees(preflight: Record) -> tuple[float, float]:
    identity = _mapping(preflight.get("identity"), "preflight identity")
    if identity.get("candidate_profile_id") != _PROFILE_ID:
        raise ValueError("fee preflight does not identify the exact v51 profile")
    assets = preflight.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("fee preflight assets must be a non-empty list")
    rows = [_mapping(value, "fee preflight asset") for value in assets]
    return _fee_for_class(rows, hip3=False), _fee_for_class(rows, hip3=True)


def _fee_for_class(rows: list[Record], *, hip3: bool) -> float:
    fees = {
        _nonnegative(
            _mapping(row.get("venue"), "venue").get("one_way_taker_fee_bps"),
            "one-way taker fee",
        )
        for row in rows
        if _text(row.get("symbol"), "symbol").startswith("xyz:") is hip3
    }
    if len(fees) != 1:
        label = "HIP-3" if hip3 else "core"
        raise ValueError(f"fee preflight requires one exact {label} taker fee")
    return fees.pop()


def _load(path: Path, label: str) -> Record:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(value, label)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if number < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return number


def main(argv: Sequence[str] | None = None) -> int:
    """Return bounded errors without exposing live execution authority."""
    try:
        return run(build_parser().parse_args(argv))
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"v51 successor exposure evidence failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
