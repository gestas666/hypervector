#!/usr/bin/env python3
"""Publish one immutable exact-depth ETH pullback forward resolution."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
import json
from math import isfinite
from pathlib import Path
import sys
from typing import Protocol

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.hyperliquid_funding_history import (
    HyperliquidFundingHistoryReader,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
)
from hypervector.research.eth_pullback_forward_resolution import (
    build_eth_pullback_forward_resolution,
    eth_pullback_funding_bounds,
)
from hypervector.research.hip3_development_provenance import (
    require_unchanged_file,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

_CONFIG = Path("configs/research/multi_asset_eth_pullback_forward_observer_v1.toml")
_LEDGER = Path("data/observe/eth_pullback_forward_observer/decisions.jsonl")
_MODULE = Path("src/hypervector/research/eth_pullback_forward_resolution.py")
_REPLAY_MODULES = tuple(
    Path("src/hypervector/research") / name
    for name in (
        "cohort_eligible_exact_depth_forward.py",
        "cohort_eligible_exact_depth_reporting.py",
        "cohort_eligible_opposite_exit.py",
        "cohort_exact_depth_books.py",
        "cohort_signal_candidates.py",
        "cohort_eligible_policy_funding.py",
        "cohort_observer_exact_books.py",
        "cohort_prospective_records.py",
        "cohort_live_audit_values.py",
        "market_depth_fill.py",
    )
)
_TAKER_FEE_RATE = 0.00045


class FundingReaderProtocol(Protocol):
    """Unsigned official funding-history surface used by the publisher."""

    def read(
        self, symbol: str, requested_start_ms: int, requested_end_ms: int
    ) -> EligiblePolicyFundingEvidence:
        """Return one complete bounded funding window."""


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only publisher CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--ledger", type=Path, default=_LEDGER)
    parser.add_argument("--observer-ledger-root", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--taker-fee-rate", type=float, default=_TAKER_FEE_RATE)
    return parser


def publish_report(
    args: argparse.Namespace,
    *,
    funding_reader: FundingReaderProtocol | None = None,
) -> dict[str, object]:
    """Freeze one observer prefix and publish its exact virtual lifecycle."""
    report = build_report(args, funding_reader=funding_reader)
    write_immutable_json(args.out, report)
    return report


def build_report(
    args: argparse.Namespace,
    *,
    funding_reader: FundingReaderProtocol | None = None,
    prospective_start_ms: int = 0,
) -> dict[str, object]:
    """Build one exact source-bound report without publishing an artifact."""
    fee_rate = _fee_rate(args.taker_fee_rate)
    references = _source_references(args.config)
    config = _observer_config(
        load_multi_asset_live_config(args.config, mode="observe"), args
    )
    with snapshot_decision_ledger(args.ledger, allow_incomplete_tail=True) as (
        records,
        ledger_evidence,
    ):
        initial = build_eth_pullback_forward_resolution(
            records,
            config=config,
            run_id=args.run_id,
            prospective_start_ms=prospective_start_ms,
            funding_evidence=None,
            taker_fee_rate=fee_rate,
        )
        bounds = eth_pullback_funding_bounds(initial)
        funding = _funding(funding_reader, bounds)
        report = build_eth_pullback_forward_resolution(
            records,
            config=config,
            run_id=args.run_id,
            prospective_start_ms=prospective_start_ms,
            funding_evidence=funding,
            taker_fee_rate=fee_rate,
        )
    _require_unchanged(references)
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["source_evidence"] = {
        "ledger": {"path": str(args.ledger), **ledger_evidence},
        "config": {"path": str(args.config), **references[args.config]},
        "generators": _generator_evidence(references),
        "funding": _funding_payload(funding),
    }
    return report


def _observer_config(
    config: MultiAssetLiveConfig, args: argparse.Namespace
) -> MultiAssetLiveConfig:
    root = args.observer_ledger_root
    if root is None:
        return config
    isolated = with_observer_ledger_root(config, root)
    if args.ledger.resolve() != isolated.cohort_ledger.resolve():
        raise ValueError(
            "observer ledger must equal rebound ledger root decisions.jsonl"
        )
    return isolated


def _funding(
    reader: FundingReaderProtocol | None,
    bounds: tuple[int, int] | None,
) -> EligiblePolicyFundingEvidence | None:
    if bounds is None:
        return None
    source = reader or _funding_reader()
    return source.read("ETH", bounds[0], bounds[1])


def _funding_reader() -> HyperliquidFundingHistoryReader:
    from hyperliquid.info import Info  # type: ignore[import-untyped]
    from hyperliquid.utils import constants  # type: ignore[import-untyped]

    endpoint = str(constants.MAINNET_API_URL)
    if "testnet" in endpoint.lower():
        raise ValueError("ETH forward resolution refuses a testnet endpoint")
    return HyperliquidFundingHistoryReader(Info(endpoint, skip_ws=True))


def _funding_payload(
    funding: EligiblePolicyFundingEvidence | None,
) -> dict[str, object]:
    if funding is None:
        return {"status": "not_requested_no_entered_lifecycle"}
    return {
        "status": "covered",
        "source": "hl_funding_history",
        "symbol": funding.symbol,
        "requested_start_ms": funding.requested_start_ms,
        "requested_end_ms": funding.requested_end_ms,
        "events": [
            {
                "timestamp_ms": event.timestamp_ms,
                "funding_rate": event.funding_rate,
            }
            for event in funding.events
        ],
    }


def _source_references(config: Path) -> dict[Path, dict[str, object]]:
    references = (config, Path(__file__), _MODULE, *_REPLAY_MODULES)
    return {path: file_evidence(path) for path in references}


def _require_unchanged(
    references: dict[Path, dict[str, object]],
) -> None:
    for path, evidence in references.items():
        require_unchanged_file(path, evidence)


def _generator_evidence(
    references: dict[Path, dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {"path": str(_project_relative(path)), **evidence}
        for path, evidence in references.items()
        if path != _CONFIG and path.suffix == ".py"
    ]


def _project_relative(path: Path) -> Path:
    try:
        return path.resolve().relative_to(Path.cwd().resolve())
    except ValueError as exc:
        raise ValueError(f"generator is outside the project root: {path}") from exc


def _fee_rate(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("taker fee rate must be numeric")
    rate = float(value)
    if not isfinite(rate) or rate <= 0.0 or rate >= 1.0:
        raise ValueError("taker fee rate must be finite and between zero and one")
    return rate


def main(argv: Sequence[str] | None = None) -> int:
    """Run the immutable report-only publisher."""
    args = build_parser().parse_args(argv)
    try:
        report = publish_report(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"ETH pullback forward resolution failed: {exc}", file=sys.stderr)
        return 2
    summary = report.get("summary")
    print(json.dumps({"out": str(args.out), "summary": summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
