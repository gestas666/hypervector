#!/usr/bin/env python3
"""Run the explicitly armed Apex MM measurement canary on mainnet."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import signal
import sys
import time
from types import FrameType

from hypervector.live.apex_mm_live_config import (
    ApexMMLiveConfig,
    ApexMMLiveConfigError,
    load_apex_mm_live_config,
)
from hypervector.live.apex_mm_live_engine import ApexMMLiveEngine, ApexMMLiveEngineError
from hypervector.live.apex_mm_live_factory import create_armed_apex_mm_adapter
from hypervector.live.apex_mm_live_ledger import (
    ApexMMLiveLedger,
    ApexMMLiveLedgerError,
)
from hypervector.live.apex_mm_live_runner import ApexMMLiveRunner, ApexMMLiveRunnerError
from hypervector.live.apex_mm_live_telemetry import ApexMMLiveTelemetry
from hypervector.live.hyperliquid_sol_factory import SolSdkFactoryError
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.live.sol_order_identity import new_client_order_id
from hypervector.live.sol_range_onset_live_telemetry import SolLiveTelemetryError
from hypervector.runtime_env import credential_presence_from_env, load_dotenv_if_present
from hypervector.runtime_lock import RuntimeLockError, apex_mm_live_runtime_lock

_CONFIG = Path("configs/apex_regime_mm_canary.toml")


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit live-only command boundary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--i-accept-live-risk", action="store_true")
    parser.add_argument("--max-polls", type=int)
    return parser


def run_live(args: argparse.Namespace) -> int:
    """Construct authenticated authority only after every live gate passes."""
    config = load_apex_mm_live_config(
        args.config,
        enabled=args.enabled,
        accepts_live_risk=args.i_accept_live_risk,
    )
    presence = credential_presence_from_env()
    credentials = presence.wallet_configured and presence.signing_key_configured
    config.require_live_start(credentials_present=credentials)
    with apex_mm_live_runtime_lock(config.backend_ledger):
        return _run_locked_live(config, credentials, args.max_polls)


def _run_locked_live(
    config: ApexMMLiveConfig,
    credentials_present: bool,
    max_polls: int | None,
) -> int:
    """Build and run venue authority while holding account ownership."""
    adapter = create_armed_apex_mm_adapter(config)
    now = datetime.now(UTC)
    ledger = ApexMMLiveLedger(
        path=config.backend_ledger,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=f"apex-mm-live-{int(now.timestamp() * 1_000)}",
    )
    telemetry = ApexMMLiveTelemetry(
        config=config,
        ledger=ledger,
        now_fn=lambda: datetime.now(UTC),
    )
    engine = ApexMMLiveEngine(
        config=config,
        adapter=adapter,
        telemetry=telemetry,
        credentials_present=credentials_present,
        now_fn=lambda: datetime.now(UTC),
        client_order_id_fn=new_client_order_id,
    )
    runner = ApexMMLiveRunner(
        engine=engine,
        stop_file=config.stop_file,
        sleep_fn=time.sleep,
        poll_seconds=config.quote_refresh_ms / 1_000.0,
    )
    try:
        return runner.run(max_polls=max_polls)
    finally:
        adapter.close()


def main() -> int:
    """Load local environment presence and fail closed on invalid startup."""
    load_dotenv_if_present()
    previous_sigterm = signal.signal(signal.SIGTERM, _request_verified_cleanup)
    try:
        try:
            run_live(build_parser().parse_args())
            return 0
        except KeyboardInterrupt:
            return 130
        except (
            ApexMMLiveConfigError,
            ApexMMLiveEngineError,
            ApexMMLiveLedgerError,
            ApexMMLiveRunnerError,
            HyperliquidAdapterError,
            RuntimeLockError,
            SolSdkFactoryError,
            SolLiveTelemetryError,
        ) as exc:
            print(f"live start refused: {exc}", file=sys.stderr)
            return 2
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)


def _request_verified_cleanup(_signum: int, _frame: FrameType | None) -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    raise SystemExit(main())
