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
from hypervector.research.cohort_checkpoint_refresh import (
    RefreshFailureMemory as RefreshFailureMemory,
    has_complete_live_checkpoint as _has_complete_live_checkpoint,
)
from hypervector.operations.cohort_checkpoint_options import (
    build_parser as build_parser,
)
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
    load_cached_portfolio_archive,
    publish_rolling_checkpoint,
)
from hypervector.research.cohort_background_sync import (
    BackgroundResearchSync,
    ResearchSyncError,
)
from hypervector.research.cohort_checkpoint_logging import (
    emit_event as _emit_event,
    log_background_sync as _log_background_sync,
)
from hypervector.research.cohort_research_import_gate import ResearchImportGate
from hypervector.research.cohort_research_sync_telemetry import ResearchSyncTelemetry
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

_SNAPSHOT_ATTEMPTS = 3
_SNAPSHOT_RETRY_SECONDS = 0.1

PublishFn = Callable[..., dict[str, object]]
SyncFn = Callable[[Path, Path], Mapping[str, object]]
LedgerState = tuple[tuple[str, int, int, int], ...]


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
    failures = RefreshFailureMemory()
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
                current_run_only=(
                    args.current_run_only
                    or (controller is not None and controller.portfolio_archive is None)
                ),
                sleep_fn=sleep_fn,
                research_sync=(
                    ResearchSyncTelemetry(enabled=False).snapshot()
                    if controller is None
                    else controller.telemetry.snapshot()
                ),
                failures=failures,
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
    if args.research_sync_min_pending_bytes < 0:
        raise ValueError("research sync minimum pending bytes cannot be negative")
    if not args.research_sync_max_age_seconds > 0.0:
        raise ValueError("research sync maximum age must be positive")
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
    telemetry = ResearchSyncTelemetry(enabled=args.research_database is not None)
    _, sync_ok, archive = _sync_if_due(args, sync_fn, 0.0, telemetry=telemetry)
    published = _publish_once(
        args,
        publish_fn,
        portfolio_fn,
        funding_fn,
        archive,
        current_run_only=args.current_run_only,
        sleep_fn=sleep_fn,
        research_sync=telemetry.snapshot(),
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
        import_gate=ResearchImportGate(
            args.ledger_root,
            minimum_pending_bytes=args.research_sync_min_pending_bytes,
            maximum_age_seconds=args.research_sync_max_age_seconds,
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


def _publish_once(
    args: argparse.Namespace,
    publish_fn: PublishFn,
    portfolio_fn: PortfolioFn | None,
    funding_fn: FundingFn | None,
    portfolio_archive: Mapping[str, object] | None,
    *,
    current_run_only: bool = False,
    sleep_fn: Callable[[float], None],
    research_sync: Mapping[str, object] | None = None,
    failures: RefreshFailureMemory | None = None,
) -> bool:
    if failures is None:
        failures = RefreshFailureMemory()
    venue_portfolio = (
        _portfolio_evidence(portfolio_fn)
        if args.venue_portfolio and portfolio_fn is not None
        else None
    )
    for attempt in range(_SNAPSHOT_ATTEMPTS):
        ledgers = _ledger_state(args.ledger_root)
        try:
            _publish_snapshot(
                args,
                publish_fn,
                venue_portfolio,
                funding_fn,
                portfolio_archive,
                current_run_only,
                research_sync,
            )
        except (duckdb.Error, FileNotFoundError, ValueError) as exc:
            retry = attempt + 1 < _SNAPSHOT_ATTEMPTS and _retryable(
                exc, args.ledger_root, ledgers, failures.message
            )
            failures.message = str(exc)
            if retry:
                sleep_fn(_SNAPSHOT_RETRY_SECONDS)
                continue
            _report_unavailable_refresh(args.out, exc)
            return False
        break
    failures.message = None
    return True


def _report_unavailable_refresh(output: Path, error: Exception) -> None:
    """Retain a complete checkpoint or publish an explicit unavailable result."""
    if _has_complete_live_checkpoint(output):
        print(
            "cohort checkpoint refresh unavailable; retaining last complete "
            f"checkpoint: {error}",
            file=sys.stderr,
        )
        return
    publish_unavailable_checkpoint(output, str(error))
    print(f"cohort checkpoint unavailable: {error}", file=sys.stderr)


def _ledger_state(ledger_root: Path) -> LedgerState | None:
    """Identify the append state of every ledger a snapshot attempt may read."""
    try:
        return tuple(
            (path.name, stat.st_ino, stat.st_size, stat.st_mtime_ns)
            for path in sorted(ledger_root.glob("*.jsonl"))
            for stat in (path.stat(),)
        )
    except OSError:
        return None


def _retryable(
    exc: Exception,
    ledger_root: Path,
    before: LedgerState | None,
    previous_failure: str | None,
) -> bool:
    """Retry startup gaps and cross-ledger append races, not deterministic errors.

    A ValueError is deterministic when no ledger changed during the failed attempt
    or when it repeats the previous failure; re-copying the snapshot cannot clear it.
    """
    if not isinstance(exc, ValueError):
        return True
    if str(exc) == previous_failure:
        return False
    return before is None or _ledger_state(ledger_root) != before


def _publish_snapshot(
    args: argparse.Namespace,
    publish_fn: PublishFn,
    venue_portfolio: Mapping[str, object] | None,
    funding_fn: FundingFn | None = None,
    portfolio_archive: Mapping[str, object] | None = None,
    current_run_only: bool = False,
    research_sync: Mapping[str, object] | None = None,
) -> None:
    if publish_fn is publish_live_checkpoint:
        _publish_real_snapshot(
            args,
            publish_fn,
            venue_portfolio,
            funding_fn,
            portfolio_archive,
            current_run_only,
            research_sync,
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
    current_run_only: bool = False,
    research_sync: Mapping[str, object] | None = None,
) -> None:
    refreshed = publish_rolling_checkpoint(
        publish_fn,
        args.ledger_root,
        args.out,
        requested_run_id=args.run_id,
        follow_latest_run=getattr(args, "follow_latest_run", False),
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
        current_run_only=current_run_only,
        # No journal (the default) means no asymmetric observer, exactly like
        # --disable-asymmetric-forward-observer.
        asymmetric_forward_journal_path=(
            None
            if args.disable_asymmetric_forward_observer
            or args.asymmetric_forward_journal is None
            else args.asymmetric_forward_journal
        ),
        accounting_epoch=_loaded_accounting_epoch(args),
        research_sync=research_sync,
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
    *,
    telemetry: ResearchSyncTelemetry | None = None,
) -> tuple[float, bool, Mapping[str, object] | None]:
    now = time.monotonic()
    if args.research_database is None or now < next_sync_at:
        return next_sync_at, True, None
    if telemetry is not None:
        telemetry.begin_attempt()
    try:
        result = sync_fn(args.research_database, args.ledger_root)
        archive = _portfolio_archive(result, _loaded_accounting_epoch(args))
    except ResearchSyncError as exc:
        if telemetry is not None:
            telemetry.failed(str(exc))
        print(f"cohort research sync failed: {exc}", file=sys.stderr)
        return next_sync_at, False, None
    public_result = {
        key: value for key, value in result.items() if key != "portfolio_archive"
    }
    if telemetry is not None:
        telemetry.succeeded(public_result)
    _emit_event("cohort_research_sync", {"result": public_result}, stream=sys.stdout)
    return now + args.research_sync_interval_seconds, True, archive


def _sync_research_database(
    database_path: Path,
    ledger_root: Path,
    *,
    cached_checkpoint_path: Path | None = None,
    accounting_epoch: CohortAccountingEpoch | None = None,
) -> dict[str, object]:
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
            stdin=subprocess.DEVNULL,
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
