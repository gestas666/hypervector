#!/usr/bin/env python3
"""Capture public BTC marks and publish the exact V58 sweep lifecycle."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import json
from math import isfinite
from pathlib import Path
import sys
import time
from typing import Protocol, cast

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.data.jsonl_prefix import (
    read_jsonl_prefix,
    require_jsonl_prefix_unchanged,
)
from hypervector.data.oxa_storage import file_evidence
from hypervector.live.hyperliquid_funding_history import (
    HyperliquidFundingHistoryReader,
)
from hypervector.live.hip3_shadow_candle_storage import append_jsonl
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.live.transient_transport import transient_read_failure_reason
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
    exact_depth_funding_bounds,
)
from hypervector.research.hip3_development_provenance import require_unchanged_file
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.research.report_only_lifecycle_watch import publish_watch_status
from hypervector.research.v58_btc_sweep_lifecycle import (
    BTC_SWEEP_STRATEGY,
    build_v58_btc_sweep_resolution,
)
from hypervector.research.v58_btc_sweep_marks import parse_btc_mark_snapshot
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

Report = dict[str, object]
ReportBuilder = Callable[[argparse.Namespace], Report]
StatusPublisher = Callable[..., Report]
Sleep = Callable[[float], None]
Clock = Callable[[], int]
_CONFIG = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
_ROOT = Path("data/observe/v58_eight_asset_prospective_20260819_v1")
_LEDGER = _ROOT / "decisions.jsonl"
_MARK_LEDGER = Path("data/live/research/v58_btc_sweep_marks.jsonl")
_STATUS = Path("data/runtime/research/v58_btc_sweep_lifecycle_latest.json")
_SNAPSHOTS = Path("data/logs/research/bidirectional_cohort/v58_btc_sweep_lifecycles")
_TAKER_FEE_RATE = 0.00045
_GENERATOR_PATHS = tuple(
    Path(value)
    for value in (
        __file__,
        "src/hypervector/research/v58_btc_sweep_lifecycle.py",
        "src/hypervector/research/v58_btc_sweep_reporting.py",
        "src/hypervector/research/v58_btc_sweep_marks.py",
        "src/hypervector/research/cohort_signal_candidates.py",
        "src/hypervector/research/cohort_observer_exact_books.py",
        "src/hypervector/research/cohort_exact_depth_books.py",
        "src/hypervector/research/cohort_eligible_policy_funding.py",
        "src/hypervector/research/report_only_lifecycle_watch.py",
        "src/hypervector/research/live_ledger_snapshot.py",
        "src/hypervector/live/btc_liquidity_sweep_long_provider.py",
        "src/hypervector/live/multi_asset_live_config.py",
        "src/hypervector/live/multi_asset_observer_config.py",
        "src/hypervector/data/jsonl_prefix.py",
        "src/hypervector/live/hip3_shadow_candle_storage.py",
        "src/hypervector/runtime_lock.py",
    )
)


class PublicInfoProtocol(Protocol):
    """Unsigned public Info endpoint used for core mark snapshots."""

    def post(self, path: str, payload: dict[str, object]) -> object:
        """Return one public metadata-and-context response."""


class _LazyPublicInfo:
    """Defer SDK initialization so constructor-time throttling is retryable."""

    def __init__(self, factory: Callable[[], PublicInfoProtocol]) -> None:
        self._factory = factory
        self._client: PublicInfoProtocol | None = None

    def post(self, path: str, payload: dict[str, object]) -> object:
        """Initialize on demand and delegate one unsigned public request."""
        if self._client is None:
            self._client = self._factory()
        return self._client.post(path, payload)


class FundingReaderProtocol(Protocol):
    """Unsigned official funding-history surface used after an entry."""

    def read(
        self, symbol: str, requested_start_ms: int, requested_end_ms: int
    ) -> EligiblePolicyFundingEvidence:
        """Return one complete bounded funding interval."""


def build_parser() -> argparse.ArgumentParser:
    """Return the execution-incapable BTC sweep watcher parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--preregistration-sha256", required=True)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--ledger", type=Path, default=_LEDGER)
    parser.add_argument("--mark-ledger", type=Path, default=_MARK_LEDGER)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--status", type=Path, default=_STATUS)
    parser.add_argument("--snapshot-dir", type=Path, default=_SNAPSHOTS)
    parser.add_argument("--taker-fee-rate", type=float, default=_TAKER_FEE_RATE)
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--report-every-polls", type=int, default=20)
    parser.add_argument("--max-polls", type=int, default=0)
    return parser


def run_watcher(
    args: argparse.Namespace,
    *,
    info: PublicInfoProtocol,
    clock_ns: Clock = time.time_ns,
    report_builder: ReportBuilder | None = None,
    status_publisher: StatusPublisher = publish_watch_status,
    sleep_fn: Sleep = time.sleep,
) -> int:
    """Capture marks and periodically publish one frozen authority-none report."""
    _validate_loop(args)
    preregistration = _preregistration_evidence(args)
    frozen = _source_references(args.config)
    polls = samples = 0
    while True:
        _require_unchanged(frozen)
        polls += 1
        mark = _read_mark(info, args.run_id, clock_ns)
        if mark is not None:
            append_jsonl(args.mark_ledger, mark)
            samples += 1
        if mark is not None and (
            samples == 1 or samples % args.report_every_polls == 0
        ):
            report = report_builder(args) if report_builder else _build_report(args)
            _attach_preregistration(report, args.preregistration, preregistration)
            _require_unchanged(frozen)
            status_publisher(
                report,
                status_path=args.status,
                snapshot_dir=args.snapshot_dir,
                run_id=args.run_id,
            )
        if args.max_polls and polls >= args.max_polls:
            return 0
        sleep_fn(args.poll_seconds)


def _read_mark(
    info: PublicInfoProtocol, run_id: str, clock_ns: Clock
) -> dict[str, object] | None:
    try:
        response = info.post("/info", {"type": "metaAndAssetCtxs"})
    except (RequestException, ClientError, ServerError) as exc:
        reason = transient_read_failure_reason(exc)
        if reason is None:
            raise
        event = {"event_type": "btc_sweep_mark_poll_degraded", "reason": reason}
        print(json.dumps(event, sort_keys=True), file=sys.stderr, flush=True)
        return None
    return parse_btc_mark_snapshot(response, run_id=run_id, received_ts_ns=clock_ns())


def _build_report(
    args: argparse.Namespace,
    funding_reader: FundingReaderProtocol | None = None,
) -> Report:
    references = _source_references(args.config)
    config = with_observer_ledger_root(
        load_multi_asset_live_config(args.config, mode="observe"), args.ledger.parent
    )
    if config.cohort_ledger.resolve() != args.ledger.resolve():
        raise ValueError("BTC watcher ledger differs from observer config binding")
    start = _prospective_start(args.preregistration)
    with snapshot_decision_ledger(args.ledger, allow_incomplete_tail=True) as source:
        marks, mark_evidence = read_jsonl_prefix(args.mark_ledger, "BTC mark ledger")
        initial = _resolution(source[0], marks, config, args, start, None)
        funding = _funding(funding_reader, exact_depth_funding_bounds(initial))
        report = _resolution(source[0], marks, config, args, start, funding)
    _require_unchanged(references)
    report["source_evidence"] = {
        "observer_ledger": {"path": str(args.ledger), **source[1]},
        "mark_ledger": mark_evidence,
        "config": {"path": str(args.config), **references[args.config]},
        "generators": _generator_evidence(references, args.config),
        "funding": _funding_payload(funding),
    }
    return report


def _resolution(
    records: Sequence[Mapping[str, object]],
    marks: Sequence[Mapping[str, object]],
    config: MultiAssetLiveConfig,
    args: argparse.Namespace,
    start: int,
    funding: EligiblePolicyFundingEvidence | None,
) -> Report:
    return build_v58_btc_sweep_resolution(
        records,
        marks=marks,
        config=config,
        run_id=args.run_id,
        prospective_start_ms=start,
        funding_evidence=funding,
        taker_fee_rate=_fee_rate(args.taker_fee_rate),
    )


def _preregistration_evidence(args: argparse.Namespace) -> dict[str, object]:
    evidence = file_evidence(args.preregistration)
    if evidence.get("sha256") != args.preregistration_sha256:
        raise ValueError("BTC watcher preregistration hash does not match")
    value = _json_mapping(args.preregistration)
    expected = {
        "schema_version": "v58_btc_sweep_lifecycle_preregistration_v1",
        "strategy_id": BTC_SWEEP_STRATEGY,
        "symbol": "BTC",
        "observer_run_id": args.run_id,
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    if any(value.get(field) != target for field, target in expected.items()):
        raise ValueError("BTC watcher preregistration identity or authority is invalid")
    _require_config(value, args.config)
    prefix = _mapping(value.get("ledger_prefix"), "BTC preregistered ledger prefix")
    require_jsonl_prefix_unchanged(args.ledger, prefix, "BTC preregistered ledger")
    _nonnegative_integer(value.get("prospective_start_ms"), "prospective start")
    return evidence


def _require_config(value: Mapping[str, object], config: Path) -> None:
    frozen = _mapping(value.get("config"), "BTC preregistered config")
    expected = {"path": str(config), **file_evidence(config)}
    if dict(frozen) != expected:
        raise ValueError("BTC watcher preregistered config identity differs")


def _prospective_start(path: Path) -> int:
    value = _json_mapping(path)
    return _nonnegative_integer(value.get("prospective_start_ms"), "prospective start")


def _attach_preregistration(
    report: Report, path: Path, evidence: Mapping[str, object]
) -> None:
    sources = report.get("source_evidence", {})
    if not isinstance(sources, Mapping):
        raise ValueError("BTC watcher source evidence must be a mapping")
    report["source_evidence"] = {
        **sources,
        "preregistration": {"path": str(path), **dict(evidence)},
    }


def _funding(
    reader: FundingReaderProtocol | None, bounds: tuple[int, int] | None
) -> EligiblePolicyFundingEvidence | None:
    if bounds is None:
        return None
    source = reader or _funding_reader()
    return source.read("BTC", bounds[0], bounds[1])


def _funding_reader() -> HyperliquidFundingHistoryReader:
    from hyperliquid.info import Info  # type: ignore[import-untyped]
    from hyperliquid.utils.constants import MAINNET_API_URL  # type: ignore[import-untyped]

    if "testnet" in str(MAINNET_API_URL).lower():
        raise ValueError("BTC watcher refuses a testnet funding endpoint")
    return HyperliquidFundingHistoryReader(Info(MAINNET_API_URL, skip_ws=True))


def official_info() -> PublicInfoProtocol:
    """Return a lazy official reader whose initialization can be retried."""
    return _LazyPublicInfo(_official_info_client)


def _official_info_client() -> PublicInfoProtocol:
    """Construct only the official unsigned mainnet Info reader."""
    from hyperliquid.info import Info  # type: ignore[import-untyped]
    from hyperliquid.utils.constants import MAINNET_API_URL  # type: ignore[import-untyped]

    if "testnet" in str(MAINNET_API_URL).lower():
        raise ValueError("BTC watcher refuses a testnet mark endpoint")
    return cast(PublicInfoProtocol, Info(MAINNET_API_URL, skip_ws=True, timeout=20.0))


def _source_references(config: Path) -> dict[Path, dict[str, object]]:
    return {path: file_evidence(path) for path in (config, *_GENERATOR_PATHS)}


def _require_unchanged(references: Mapping[Path, Mapping[str, object]]) -> None:
    for path, evidence in references.items():
        require_unchanged_file(path, evidence)


def _generator_evidence(
    references: Mapping[Path, Mapping[str, object]], config: Path
) -> list[dict[str, object]]:
    return [
        {"path": str(path), **dict(evidence)}
        for path, evidence in references.items()
        if path != config and path.suffix == ".py"
    ]


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
            {"timestamp_ms": row.timestamp_ms, "funding_rate": row.funding_rate}
            for row in funding.events
        ],
    }


def _validate_loop(args: argparse.Namespace) -> None:
    if not isfinite(args.poll_seconds) or args.poll_seconds <= 0.0:
        raise ValueError("BTC watcher poll seconds must be finite and positive")
    for value, label in (
        (args.report_every_polls, "report every polls"),
        (args.max_polls, "max polls"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"BTC watcher {label} must be a nonnegative integer")
    if args.report_every_polls == 0:
        raise ValueError("BTC watcher report every polls must be positive")
    _fee_rate(args.taker_fee_rate)


def _fee_rate(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("BTC watcher taker fee rate must be numeric")
    output = float(value)
    if not isfinite(output) or not 0.0 < output < 1.0:
        raise ValueError("BTC watcher taker fee rate must be finite and positive")
    return output


def _json_mapping(path: Path) -> Mapping[str, object]:
    return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the singleton report-only watcher without a signing client."""
    args = build_parser().parse_args(argv)
    try:
        with cohort_checkpoint_runtime_lock(args.status):
            return run_watcher(args, info=official_info())
    except KeyboardInterrupt:
        return 130
    except (json.JSONDecodeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"V58 BTC sweep watcher refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
