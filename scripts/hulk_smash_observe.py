#!/usr/bin/env python3
"""Run the execution-incapable Hulk Smash mainnet observer."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys
import time

import pandas as pd

from hypervector.data.hl import fetch_hl_ohlcv
from hypervector.live.hulk_smash_live_config import (
    HulkSmashLiveConfigError,
    load_hulk_smash_live_config,
)
from hypervector.live.hulk_smash_live_decisions import (
    HulkSmashLiveDecision,
    build_completed_hulk_decisions,
)
from hypervector.live.hulk_smash_live_ledger import (
    HulkSmashLiveLedger,
    HulkSmashLiveLedgerError,
)
from hypervector.live.hulk_smash_live_telemetry import (
    HulkSmashLiveTelemetry,
    HulkSmashLiveTelemetryError,
)
from hypervector.live.hulk_smash_observer import (
    HulkSmashObserver,
    HulkSmashObserverError,
)
from hypervector.live.hulk_smash_observer_runner import (
    HulkSmashObserverRunner,
    HulkSmashObserverRunnerError,
)
from hypervector.live.hyperliquid_btc_factory import create_read_only_btc_reader
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.runtime_env import (
    credential_presence_from_env,
    load_wallet_env_if_present,
)
from hypervector.runtime_lock import (
    RuntimeLockError,
    hulk_smash_observer_runtime_lock,
)

_CONFIG = Path("configs/hulk_smash_short_robust_v3_canary.toml")


def parser() -> argparse.ArgumentParser:
    """Build a no-submit command surface with no live-arm flags."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=_CONFIG)
    result.add_argument("--poll-seconds", type=float, default=5.0)
    result.add_argument("--max-polls", type=int)
    return result


def run(args: argparse.Namespace) -> int:
    """Construct only read-only SDK and observer components."""
    config = load_hulk_smash_live_config(args.config, mode="observe")
    presence = credential_presence_from_env()
    if not presence.wallet_configured:
        raise HulkSmashObserverError(
            "read-only Hulk observer requires a configured public wallet address"
        )
    with hulk_smash_observer_runtime_lock(config.backend_ledger):
        reader = create_read_only_btc_reader()
        now = datetime.now(UTC)
        ledger = HulkSmashLiveLedger(
            path=config.backend_ledger,
            profile_id=config.profile_id,
            profile_fingerprint=config.profile_fingerprint,
            run_fingerprint=config.run_fingerprint,
            run_id=f"hulk-observe-{int(now.timestamp() * 1_000)}",
        )
        telemetry = HulkSmashLiveTelemetry(
            config=config,
            ledger=ledger,
            armed=False,
            wallet_configured=presence.wallet_configured,
            signing_key_configured=presence.signing_key_configured,
            now_fn=lambda: datetime.now(UTC),
        )
        observer = HulkSmashObserver(
            config=config,
            reader=reader,
            telemetry=telemetry,
            now_fn=lambda: datetime.now(UTC),
        )

        def decisions(
            bars: pd.DataFrame,
            *,
            observed_at: pd.Timestamp,
            after_decision_time_ms: int | None,
        ) -> tuple[HulkSmashLiveDecision, ...]:
            return build_completed_hulk_decisions(
                bars,
                observed_at=observed_at,
                after_decision_time_ms=after_decision_time_ms,
                config=config,
            )

        runner = HulkSmashObserverRunner(
            observer=observer,
            stop_file=config.stop_file,
            fetch_bars=fetch_hl_ohlcv,
            build_decisions=decisions,
            now_fn=lambda: datetime.now(UTC),
            sleep_fn=time.sleep,
            poll_seconds=args.poll_seconds,
            lookback_days=config.lookback_days,
        )
        runner.run(max_polls=args.max_polls)
        return 0


def main() -> int:
    """Load only public wallet identity and report fail-closed errors."""
    load_wallet_env_if_present()
    try:
        return run(parser().parse_args())
    except KeyboardInterrupt:
        return 130
    except (
        HulkSmashLiveConfigError,
        HulkSmashLiveLedgerError,
        HulkSmashLiveTelemetryError,
        HulkSmashObserverError,
        HulkSmashObserverRunnerError,
        HyperliquidAdapterError,
        RuntimeLockError,
        ValueError,
    ) as exc:
        print(f"Hulk observer start refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
