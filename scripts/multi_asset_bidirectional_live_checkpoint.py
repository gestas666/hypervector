#!/usr/bin/env python3
"""Continuously publish read-only checkpoints for one live cohort ledger set."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from functools import partial
import json
from pathlib import Path
import subprocess
import sys
import time

import duckdb
from hypervector.live.cohort_accounting_rollover import (
    load_required_accounting_epoch,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.runtime_lock import (
    RuntimeLockError,
    cohort_checkpoint_runtime_lock,
)

from hypervector.research.cohort_live_checkpoint import (
    publish_live_checkpoint,
    publish_unavailable_checkpoint,
)
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch
from hypervector.research.cohort_rolling_checkpoint import (
    is_complete_live_checkpoint,
    load_cached_portfolio_archive,
    publish_rolling_checkpoint,
)
from hypervector.research.cohort_background_sync import (
    BackgroundResearchSync,
    ResearchSyncError,
)
from hypervector.research.cohort_checkpoint_accounting import (
    bind_sync_to_accounting_epoch as _bind_sync_to_accounting_epoch,
    research_worker_command as _research_worker_command,
    validated_epoch_archive as _portfolio_archive,
)
from hypervector.research.cohort_checkpoint_venue import (
    FundingFn,
    PortfolioFn,
    failure_isolated_funding_fn,
    official_funding_fn as _official_funding_fn,
    official_portfolio_fn as _official_portfolio_fn,
    portfolio_evidence as _portfolio_evidence,
)

_failure_isolated_funding_fn = failure_isolated_funding_fn

_DEFAULT_LEDGER_ROOT = Path("data/live/bidirectional_cohort")
_DEFAULT_OUTPUT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_DEFAULT_CONFIG = Path("configs/multi_asset_bidirectional_canary.toml")
_DEFAULT_OPPORTUNITY_MATRIX = Path(
    "data/runtime/bidirectional_cohort/latest_opportunity_matrix.json"
)
_DEFAULT_ASYMMETRIC_FORWARD_JOURNAL = Path(
    "docs/research-journal/cohort-asymmetric-shared-portfolio-v1.json"
)
_SNAPSHOT_ATTEMPTS = 3
_SNAPSHOT_RETRY_SECONDS = 0.1

PublishFn = Callable[..., dict[str, object]]
SyncFn = Callable[[Path, Path], Mapping[str, object]]


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable rolling checkpoint CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-root", type=Path, default=_DEFAULT_LEDGER_ROOT)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    parser.add_argument("--run-id")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--research-database", type=Path)
    parser.add_argument("--accounting-epoch-bundle", type=Path)
    parser.add_argument("--research-sync-interval-seconds", type=float, default=600.0)
    parser.add_argument("--venue-portfolio", action="store_true")
    parser.add_argument(
        "--opportunity-matrix",
        type=Path,
        default=_DEFAULT_OPPORTUNITY_MATRIX,
    )
    parser.add_argument(
        "--supplemental-opportunity-matrix",
        action="append",
        type=Path,
        default=[],
    )
    parser.add_argument(
        "--eligible-policy-forward",
        action="store_true",
        help="attach the report-only exact ETH stop/hold lifecycle journal",
    )
    parser.add_argument(
        "--asymmetric-forward-journal",
        type=Path,
        default=_DEFAULT_ASYMMETRIC_FORWARD_JOURNAL,
        help="attach the frozen report-only asymmetric portfolio observer",
    )
    parser.add_argument(
        "--disable-asymmetric-forward-observer",
        action="store_true",
        help="do not attach a profile-specific asymmetric portfolio observer",
    )
    parser.add_argument("--once", action="store_true")
    return parser


def run_checkpoint_loop(
    args: argparse.Namespace,
    *,
    publish_fn: PublishFn = publish_live_checkpoint,
    sync_fn: SyncFn | None = None,
    portfolio_fn: PortfolioFn | None = None,
    funding_fn: FundingFn | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Publish until terminated, retrying only incomplete startup evidence."""
    with cohort_checkpoint_runtime_lock(args.out):
        return _run_owned_checkpoint_loop(
            args,
            publish_fn=publish_fn,
            sync_fn=sync_fn,
            portfolio_fn=portfolio_fn,
            funding_fn=funding_fn,
            sleep_fn=sleep_fn,
        )


def _run_owned_checkpoint_loop(
    args: argparse.Namespace,
    *,
    publish_fn: PublishFn,
    sync_fn: SyncFn | None,
    portfolio_fn: PortfolioFn | None,
    funding_fn: FundingFn | None,
    sleep_fn: Callable[[float], None],
) -> int:
    """Publish while the caller exclusively owns the output artifact."""
    active_sync, active_portfolio, active_funding = _checkpoint_services(
        args, sync_fn, portfolio_fn, funding_fn
    )
    if args.once:
        return _run_once(
            args,
            active_sync,
            publish_fn,
            active_portfolio,
            active_funding,
            sleep_fn,
        )
    controller = _background_sync(args, active_sync)
    try:
        while True:
            if controller is not None:
                controller.poll(now=time.monotonic())
                _log_background_sync(controller)
            _publish_once(
                args,
                publish_fn,
                active_portfolio,
                active_funding,
                None if controller is None else controller.portfolio_archive,
                sleep_fn=sleep_fn,
            )
            sleep_fn(args.interval_seconds)
    finally:
        if controller is not None:
            controller.close()


def _checkpoint_services(
    args: argparse.Namespace,
    sync_fn: SyncFn | None,
    portfolio_fn: PortfolioFn | None,
    funding_fn: FundingFn | None,
) -> tuple[SyncFn, PortfolioFn | None, FundingFn | None]:
    """Validate arguments and build the exact report-only data sources."""
    accounting_epoch = _accounting_epoch(args)
    args.accounting_epoch = accounting_epoch
    if args.interval_seconds <= 0.0:
        raise ValueError("checkpoint interval must be positive")
    if args.research_sync_interval_seconds <= 0.0:
        raise ValueError("research sync interval must be positive")
    base_sync = sync_fn or partial(
        _sync_research_database,
        cached_checkpoint_path=args.out,
        accounting_epoch=accounting_epoch,
    )
    active_sync = _bind_sync_to_accounting_epoch(base_sync, accounting_epoch)
    active_portfolio = portfolio_fn
    if args.venue_portfolio and active_portfolio is None:
        active_portfolio = _official_portfolio_fn()
    active_funding = funding_fn
    if args.eligible_policy_forward and active_funding is None:
        active_funding = _official_funding_fn()
    return active_sync, active_portfolio, active_funding


def _run_once(
    args: argparse.Namespace,
    sync_fn: SyncFn,
    publish_fn: PublishFn,
    portfolio_fn: PortfolioFn | None,
    funding_fn: FundingFn | None,
    sleep_fn: Callable[[float], None],
) -> int:
    _, sync_ok, archive = _sync_if_due(args, sync_fn, 0.0)
    published = _publish_once(
        args,
        publish_fn,
        portfolio_fn,
        funding_fn,
        archive,
        sleep_fn=sleep_fn,
    )
    return 0 if published and sync_ok else 2


def _background_sync(
    args: argparse.Namespace,
    sync_fn: SyncFn,
) -> BackgroundResearchSync | None:
    if args.research_database is None:
        return None
    return BackgroundResearchSync(
        args.research_database,
        args.ledger_root,
        args.research_sync_interval_seconds,
        sync_fn,
        portfolio_archive=load_cached_portfolio_archive(
            args.out,
            accounting_epoch=_loaded_accounting_epoch(args),
        ),
    )


def _accounting_epoch(args: argparse.Namespace) -> CohortAccountingEpoch | None:
    bundle = args.accounting_epoch_bundle
    if bundle is not None and args.research_database is None:
        raise ValueError("--accounting-epoch-bundle requires --research-database")
    config = load_multi_asset_live_config(args.config, mode="observe")
    epoch = load_required_accounting_epoch(bundle, config)
    if epoch is not None and args.research_database is None:
        raise ValueError("--accounting-epoch-bundle requires --research-database")
    return epoch


def _loaded_accounting_epoch(
    args: argparse.Namespace,
) -> CohortAccountingEpoch | None:
    epoch = getattr(args, "accounting_epoch", None)
    if epoch is not None and not isinstance(epoch, CohortAccountingEpoch):
        raise ValueError("checkpoint accounting epoch is invalid")
    return epoch


def _log_background_sync(controller: BackgroundResearchSync) -> None:
    report = controller.pop_report()
    if report is not None:
        _emit_event(
            "cohort_research_sync",
            {"result": report},
        )
    error = controller.pop_error()
    if error is not None:
        print(f"cohort research sync failed: {error}", file=sys.stderr)


def _emit_event(event: str, fields: Mapping[str, object]) -> None:
    """Write one flushed report-only event to the shared sidecar log stream."""
    payload = {
        "event": event,
        "execution_authority": "none",
        **fields,
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)


def _publish_once(
    args: argparse.Namespace,
    publish_fn: PublishFn,
    portfolio_fn: PortfolioFn | None,
    funding_fn: FundingFn | None,
    portfolio_archive: Mapping[str, object] | None,
    *,
    sleep_fn: Callable[[float], None],
) -> bool:
    venue_portfolio = (
        _portfolio_evidence(portfolio_fn)
        if args.venue_portfolio and portfolio_fn is not None
        else None
    )
    for attempt in range(_SNAPSHOT_ATTEMPTS):
        try:
            _publish_snapshot(
                args,
                publish_fn,
                venue_portfolio,
                funding_fn,
                portfolio_archive,
            )
        except (duckdb.Error, FileNotFoundError, ValueError) as exc:
            if attempt + 1 < _SNAPSHOT_ATTEMPTS:
                sleep_fn(_SNAPSHOT_RETRY_SECONDS)
                continue
            if _has_complete_live_checkpoint(args.out):
                print(
                    "cohort checkpoint refresh unavailable; retaining last complete "
                    f"checkpoint: {exc}",
                    file=sys.stderr,
                )
                return False
            publish_unavailable_checkpoint(args.out, str(exc))
            print(f"cohort checkpoint unavailable: {exc}", file=sys.stderr)
            return False
        break
    return True


def _has_complete_live_checkpoint(path: Path) -> bool:
    """Return whether the destination contains a prior complete live projection."""
    if not path.is_file():
        return False
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError):
        return False
    return is_complete_live_checkpoint(document)


def _publish_snapshot(
    args: argparse.Namespace,
    publish_fn: PublishFn,
    venue_portfolio: Mapping[str, object] | None,
    funding_fn: FundingFn | None = None,
    portfolio_archive: Mapping[str, object] | None = None,
) -> None:
    """Publish one cross-ledger prefix with no retry or execution authority."""
    if publish_fn is publish_live_checkpoint:
        _publish_real_snapshot(
            args,
            publish_fn,
            venue_portfolio,
            funding_fn,
            portfolio_archive,
        )
        return
    publish_fn(
        args.ledger_root,
        args.out,
        run_id=args.run_id,
        config_path=args.config,
        venue_portfolio=venue_portfolio,
    )


def _publish_real_snapshot(
    args: argparse.Namespace,
    publish_fn: PublishFn,
    venue_portfolio: Mapping[str, object] | None,
    funding_fn: FundingFn | None,
    portfolio_archive: Mapping[str, object] | None,
) -> None:
    refreshed = publish_rolling_checkpoint(
        publish_fn,
        args.ledger_root,
        args.out,
        requested_run_id=args.run_id,
        config_path=args.config,
        once=args.once,
        venue_portfolio=venue_portfolio,
        opportunity_matrix_path=(
            args.opportunity_matrix if args.opportunity_matrix.is_file() else None
        ),
        supplemental_opportunity_matrix_paths=args.supplemental_opportunity_matrix,
        eligible_policy_forward=args.eligible_policy_forward,
        funding_evidence_fn=funding_fn,
        portfolio_archive=portfolio_archive,
        asymmetric_forward_journal_path=(
            None
            if args.disable_asymmetric_forward_observer
            else args.asymmetric_forward_journal
        ),
        accounting_epoch=_loaded_accounting_epoch(args),
    )
    if refreshed:
        _emit_event(
            "cohort_historical_projection_refreshed",
            {"source": "complete_ledgers"},
        )


def _sync_if_due(
    args: argparse.Namespace,
    sync_fn: SyncFn,
    next_sync_at: float,
) -> tuple[float, bool, Mapping[str, object] | None]:
    now = time.monotonic()
    if args.research_database is None or now < next_sync_at:
        return next_sync_at, True, None
    try:
        result = sync_fn(args.research_database, args.ledger_root)
        archive = _portfolio_archive(result, _loaded_accounting_epoch(args))
    except ResearchSyncError as exc:
        print(f"cohort research sync failed: {exc}", file=sys.stderr)
        return next_sync_at, False, None
    public_result = {
        key: value for key, value in result.items() if key != "portfolio_archive"
    }
    print(
        json.dumps(
            {
                "event": "cohort_research_sync",
                "execution_authority": "none",
                "result": public_result,
            },
            sort_keys=True,
        )
    )
    return now + args.research_sync_interval_seconds, True, archive


def _sync_research_database(
    database_path: Path,
    ledger_root: Path,
    *,
    cached_checkpoint_path: Path | None = None,
    accounting_epoch: CohortAccountingEpoch | None = None,
) -> dict[str, object]:
    """Persist journals in a short-lived worker and return its archive projection."""
    worker = Path(__file__).with_name("multi_asset_bidirectional_research_import.py")
    command = _research_worker_command(
        worker,
        database_path,
        ledger_root,
        cached_checkpoint_path,
        accounting_epoch,
    )
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ResearchSyncError(str(exc)) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ResearchSyncError(
            f"isolated research worker exited {completed.returncode}: {detail[-500:]}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ResearchSyncError(
            "isolated research worker returned invalid JSON"
        ) from exc
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        raise ResearchSyncError("isolated research worker did not report success")
    ingest = payload.get("ingest")
    if not isinstance(ingest, Mapping):
        raise ResearchSyncError("isolated research worker omitted its ingest report")
    result = dict(ingest)
    for key in ("archive_status", "fill_identity"):
        if key in payload:
            result[key] = payload[key]
    result["portfolio_archive"] = _portfolio_archive(payload, accounting_epoch)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Run a bounded latest-only observer with no execution authority."""
    try:
        return run_checkpoint_loop(build_parser().parse_args(argv))
    except (OSError, RuntimeLockError, ValueError) as exc:
        print(f"cohort checkpoint failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
