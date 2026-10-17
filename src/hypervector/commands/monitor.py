"""Read-only JSON monitoring and independent checkpoint publication."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from hypervector.commands.common import CommandRefused
from hypervector.live.cohort_accounting_rollover import load_required_accounting_epoch
from hypervector.live.cohort_checkpoint_identity import (
    require_checkpoint_accounting_epoch,
)
from hypervector.live.cohort_monitor_identity import (
    checkpoint_identity,
    checkpoint_for_identity,
    LedgerIdentityReader,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.process_signal_stop import (
    install_process_signal_stop,
    stop_aware_sleep,
)
from hypervector.research.cohort_independent_checkpoint import (
    publish_independent_checkpoint,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock


def cmd_monitor(args: argparse.Namespace) -> int:
    """Observe an exact active profile without owning or restarting its backend."""
    if not math.isfinite(args.interval_seconds) or args.interval_seconds <= 0:
        raise CommandRefused("monitor interval must be positive and finite")
    try:
        return _monitor(args)
    except (OSError, RuntimeError, ValueError) as exc:
        # Exit 2 with the shared error document (cli.main boundary).
        raise CommandRefused(f"live monitor refused: {exc}") from exc


def _monitor(args: argparse.Namespace) -> int:
    config = load_multi_asset_live_config(Path(args.config), mode="observe")
    epoch = load_required_accounting_epoch(args.accounting_epoch_bundle, config)
    stop = install_process_signal_stop() if args.follow else None
    identities = LedgerIdentityReader(config)
    while True:
        document = checkpoint_for_identity(
            Path(args.source_checkpoint),
            config,
            identities.read(),
            maximum_age_seconds=args.maximum_age_seconds,
        )
        if document is None:
            raise ValueError(
                "checkpoint is missing or stale; publish 'live checkpoint' for the exact active config"
            )
        identity = checkpoint_identity(document)
        if args.run_id and identity.run_id != args.run_id:
            raise ValueError("checkpoint differs from the requested run ID")
        if epoch is not None:
            require_checkpoint_accounting_epoch(document, epoch)
        if args.out:
            destination = Path(args.out)
            with cohort_checkpoint_runtime_lock(destination):
                document = publish_independent_checkpoint(
                    source_path=Path(args.source_checkpoint),
                    destination=destination,
                    config=config,
                    run_id=identity.run_id,
                    accounting_epoch=epoch,
                )
        print(json.dumps(document, sort_keys=True, allow_nan=False), flush=True)
        if stop is None or stop.requested:
            return 0
        stop_aware_sleep(args.interval_seconds, stop_requested=lambda: stop.requested)
