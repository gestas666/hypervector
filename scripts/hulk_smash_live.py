#!/usr/bin/env python3
"""Run the explicitly armed Hulk Smash BTC canary on mainnet."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import signal
import sys
from threading import Event
import time
from types import FrameType

import pandas as pd

from hypervector.data.hl import fetch_hl_ohlcv
from hypervector.live.hulk_smash_live_config import HulkSmashLiveConfig
from hypervector.live.hulk_smash_live_config import (
    HulkSmashLiveConfigError,
    load_hulk_smash_live_config,
)
from hypervector.live.hulk_smash_live_decisions import (
    HulkSmashLiveDecision,
    build_completed_hulk_decisions,
)
from hypervector.live.hulk_smash_live_engine import (
    HulkSmashLiveEngine,
    HulkSmashLiveEngineError,
)
from hypervector.live.hulk_smash_live_ledger import (
    HulkSmashLiveLedger,
    HulkSmashLiveLedgerError,
)
from hypervector.live.hulk_smash_live_runner import (
    HulkSmashLiveRunner,
    HulkSmashLiveRunnerError,
)
from hypervector.live.hulk_smash_live_telemetry import HulkSmashLiveTelemetryError
from hypervector.live.hulk_smash_observer import (
    HulkSmashObserverError,
    validate_hulk_signal_source,
)
from hypervector.live.hyperliquid_btc_factory import create_armed_hulk_btc_adapter
from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.hyperliquid_sol_factory import SolSdkFactoryError
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.live.sol_order_identity import new_client_order_id
from hypervector.runtime_env import credential_presence_from_env, load_dotenv_if_present
from hypervector.runtime_lock import RuntimeLockError, hulk_smash_live_runtime_lock

_CONFIG = Path("configs/hulk_smash_short_robust_v3_canary.toml")
_STOP_REQUESTED = Event()


def parser() -> argparse.ArgumentParser:
    """Build the explicit live-only command boundary."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=_CONFIG)
    result.add_argument("--enabled", action="store_true")
    result.add_argument("--i-accept-live-risk", action="store_true")
    result.add_argument("--poll-seconds", type=float, default=5.0)
    result.add_argument("--max-polls", type=int)
    return result


def run(args: argparse.Namespace) -> int:
    """Construct authenticated authority only after every fail-closed gate."""
    config = load_hulk_smash_live_config(
        args.config,
        mode="live",
        enabled=args.enabled,
        accepts_live_risk=args.i_accept_live_risk,
    )
    presence = credential_presence_from_env()
    credentials = presence.wallet_configured and presence.signing_key_configured
    config.require_live_start(credentials_present=credentials)
    validate_hulk_signal_source(config)
    with hulk_smash_live_runtime_lock(config.backend_ledger):
        adapter = create_armed_hulk_btc_adapter(config)
        ledger = HulkSmashLiveLedger(
            path=config.backend_ledger,
            profile_id=config.profile_id,
            profile_fingerprint=config.profile_fingerprint,
            run_fingerprint=config.run_fingerprint,
            run_id=f"hulk-live-{int(datetime.now(UTC).timestamp() * 1_000)}",
        )
        runner = _build_runner(
            config,
            adapter,
            ledger,
            credentials_present=credentials,
            poll_seconds=args.poll_seconds,
        )
        return runner.run(max_polls=args.max_polls)


def _build_runner(
    config: HulkSmashLiveConfig,
    adapter: BtcHyperliquidAdapter,
    ledger: HulkSmashLiveLedger,
    *,
    credentials_present: bool,
    poll_seconds: float,
) -> HulkSmashLiveRunner:
    engine = HulkSmashLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=credentials_present,
        now_fn=lambda: datetime.now(UTC),
        client_order_id_fn=new_client_order_id,
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

    return HulkSmashLiveRunner(
        engine=engine,
        stop_file=config.stop_file,
        fetch_bars=fetch_hl_ohlcv,
        build_decisions=decisions,
        now_fn=lambda: datetime.now(UTC),
        sleep_fn=time.sleep,
        poll_seconds=poll_seconds,
        lookback_days=config.lookback_days,
        maximum_entry_delay_seconds=config.maximum_entry_delay_seconds,
        signal_stop_requested=_STOP_REQUESTED.is_set,
    )


def main() -> int:
    """Load local secrets and report fail-closed startup errors."""
    load_dotenv_if_present()
    _STOP_REQUESTED.clear()
    previous_sigterm = signal.signal(signal.SIGTERM, _request_verified_stop)
    previous_sigint = signal.signal(signal.SIGINT, _request_verified_stop)
    try:
        try:
            run(parser().parse_args())
            return 0
        except KeyboardInterrupt:
            return 130
        except (
            HulkSmashLiveConfigError,
            HulkSmashLiveEngineError,
            HulkSmashLiveLedgerError,
            HulkSmashLiveRunnerError,
            HulkSmashLiveTelemetryError,
            HulkSmashObserverError,
            HyperliquidAdapterError,
            SolSdkFactoryError,
            RuntimeLockError,
            ValueError,
        ) as exc:
            print(f"Hulk live start refused: {exc}", file=sys.stderr)
            return 2
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)


def _request_verified_stop(_signum: int, _frame: FrameType | None) -> None:
    _STOP_REQUESTED.set()


if __name__ == "__main__":
    raise SystemExit(main())
