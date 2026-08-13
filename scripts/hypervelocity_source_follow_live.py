#!/usr/bin/env python3
"""Run the explicitly armed BTC 5m source-follow canary on mainnet."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys
import time

from hypervector.data.hl import fetch_hl_ohlcv
from hypervector.live.hyperliquid_btc_factory import create_armed_btc_adapter
from hypervector.live.hyperliquid_sol_factory import SolSdkFactoryError
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.live.source_follow_live_config import (
    SourceFollowLiveConfigError,
    load_source_follow_live_config,
)
from hypervector.live.source_follow_live_engine import (
    SourceFollowLiveEngine,
    SourceFollowLiveEngineError,
)
from hypervector.live.source_follow_live_ledger import (
    SourceFollowLiveLedger,
    SourceFollowLiveLedgerError,
)
from hypervector.live.source_follow_live_runner import (
    SourceFollowLiveRunner,
    SourceFollowLiveRunnerError,
)
from hypervector.regime.pinned_hypertrader import PinnedHypertraderClassifier
from hypervector.regime.source_follow_runtime import SourceFollowRuntime
from hypervector.runtime_env import credential_presence_from_env, load_dotenv_if_present
from hypervector.runtime_lock import RuntimeLockError, source_follow_live_runtime_lock

_CONFIG = Path("configs/hypervelocity_source_follow_minrange12_alloc35_canary.toml")


def parser() -> argparse.ArgumentParser:
    """Build the explicit live-only command boundary."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=_CONFIG)
    result.add_argument("--enabled", action="store_true")
    result.add_argument("--i-accept-live-risk", action="store_true")
    result.add_argument("--poll-seconds", type=float, default=5.0)
    result.add_argument("--lookback-days", type=int, default=30)
    result.add_argument("--max-polls", type=int)
    return result


def run(args: argparse.Namespace) -> int:
    """Construct authenticated authority only after both risk flags pass."""
    config = load_source_follow_live_config(
        args.config,
        enabled=args.enabled,
        accepts_live_risk=args.i_accept_live_risk,
    )
    presence = credential_presence_from_env()
    credentials = presence.wallet_configured and presence.signing_key_configured
    config.require_live_start(credentials_present=credentials)
    with source_follow_live_runtime_lock(config.backend_ledger):
        adapter = create_armed_btc_adapter(config)
        now = datetime.now(UTC)
        ledger = SourceFollowLiveLedger(
            path=config.backend_ledger,
            profile_id=config.profile_id,
            profile_fingerprint=config.profile_fingerprint,
            run_fingerprint=config.run_fingerprint,
            run_id=f"btc-source-live-{int(now.timestamp() * 1_000)}",
        )
        engine = SourceFollowLiveEngine(
            config=config,
            adapter=adapter,
            ledger=ledger,
            credentials_present=credentials,
            now_fn=lambda: datetime.now(UTC),
            client_order_id_fn=_client_order_id,
        )
        profile = config.profile
        runtime = SourceFollowRuntime(
            PinnedHypertraderClassifier(profile.source_backend_root),
            minimum_confidence=profile.minimum_confidence,
            minimum_range_bps=profile.minimum_range_bps,
            maximum_range_bps=profile.maximum_range_bps,
            maximum_hold_seconds=profile.maximum_hold_seconds,
            entry_pulse_seconds=profile.entry_pulse_seconds,
            direction_mode=config.runtime_direction_mode,
        )
        runner = SourceFollowLiveRunner(
            engine=engine,
            runtime=runtime,
            fetch_bars=fetch_hl_ohlcv,
            stop_file=config.stop_file,
            now_fn=lambda: datetime.now(UTC),
            sleep_fn=time.sleep,
            poll_seconds=args.poll_seconds,
            lookback_days=args.lookback_days,
            entry_pulse_seconds=profile.entry_pulse_seconds,
        )
        return runner.run(max_polls=args.max_polls)


def _client_order_id() -> str:
    from hypervector.live.sol_order_identity import new_client_order_id

    return new_client_order_id()


def main() -> int:
    """Load local environment presence and fail closed on invalid startup."""
    load_dotenv_if_present()
    try:
        return run(parser().parse_args())
    except KeyboardInterrupt:
        return 130
    except (
        HyperliquidAdapterError,
        SolSdkFactoryError,
        SourceFollowLiveConfigError,
        SourceFollowLiveEngineError,
        SourceFollowLiveLedgerError,
        SourceFollowLiveRunnerError,
        RuntimeLockError,
    ) as exc:
        print(f"live start refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
