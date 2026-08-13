"""Run the explicitly armed SOL range-onset canary on Hyperliquid mainnet."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys
import time

from hypervector.data.hl import fetch_hl_ohlcv
from hypervector.live.hyperliquid_sol_factory import (
    SolSdkFactoryError,
    create_armed_sol_adapter,
)
from hypervector.live.sol_range_onset_config import (
    SolCanaryConfigError,
    SolRangeOnsetConfig,
    load_sol_range_onset_config,
)
from hypervector.live.sol_range_onset_controller import SolRangeOnsetLiveController
from hypervector.live.sol_range_onset_decision_source import (
    build_completed_live_decisions,
)
from hypervector.live.sol_range_onset_engine import SolRangeOnsetLiveEngine
from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.live.sol_range_onset_runner import SolRangeOnsetLiveRunner
from hypervector.runtime_env import credential_presence_from_env, load_dotenv_if_present
from hypervector.runtime_lock import sol_live_runtime_lock

_DEFAULT_CONFIG = Path("configs/sol_range_onset_canary.toml")


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit live-only command boundary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--i-accept-live-risk", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--lookback-days", type=int, default=5)
    parser.add_argument("--max-polls", type=int)
    return parser


def run_live(args: argparse.Namespace) -> int:
    """Construct the armed adapter only after every independent gate passes."""
    config = load_sol_range_onset_config(
        args.config,
        mode="live",
        enabled=args.enabled,
        accepts_live_risk=args.i_accept_live_risk,
    )
    presence = credential_presence_from_env()
    credentials_present = presence.wallet_configured and presence.signing_key_configured
    config.require_live_start(credentials_present=credentials_present)
    with sol_live_runtime_lock(config.live_ledger):
        return _run_locked_live(args, config, credentials_present)


def _run_locked_live(
    args: argparse.Namespace,
    config: SolRangeOnsetConfig,
    credentials_present: bool,
) -> int:
    """Construct and run venue authority while holding singleton ownership."""
    adapter = create_armed_sol_adapter(config)
    now = datetime.now(UTC)
    ledger = SolLiveLedger(
        path=config.live_ledger,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=f"sol-live-{int(now.timestamp() * 1_000)}",
    )
    engine = SolRangeOnsetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=credentials_present,
        now_fn=lambda: datetime.now(UTC),
    )
    controller = SolRangeOnsetLiveController(engine=engine, config=config)
    runner = SolRangeOnsetLiveRunner(
        engine=engine,
        controller=controller,
        stop_file=config.authoritative_stop_file,
        fetch_bars=fetch_hl_ohlcv,
        build_decisions=build_completed_live_decisions,
        now_fn=lambda: datetime.now(UTC),
        sleep_fn=time.sleep,
        poll_seconds=args.poll_seconds,
        lookback_days=args.lookback_days,
    )
    return runner.run(max_polls=args.max_polls)


def main() -> int:
    """Load environment presence and run until stop or interrupt."""
    load_dotenv_if_present()
    try:
        return run_live(build_parser().parse_args())
    except KeyboardInterrupt:
        return 130
    except (SolCanaryConfigError, SolSdkFactoryError) as exc:
        print(f"live start refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
