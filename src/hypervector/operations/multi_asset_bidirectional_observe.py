"""Run the production multi-asset collectors with zero execution authority."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
import sys
import time

import requests

from hypervector.data.hl import fetch_hl_ohlcv_snapshot
from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_intent_poller import (
    CohortBarFetcherProtocol,
    ConfiguredMultiAssetIntentPoller,
    MultiAssetIntentPollerError,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_observer_runner import (
    MultiAssetObserverRunner,
    MultiAssetObserverRunnerError,
)
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.live.multi_asset_public_books import MultiAssetPublicBookCollector
from hypervector.live.cohort_operator_commands import (
    CohortOperatorInbox,
    CohortOperatorInboxError,
)
from hypervector.live.cohort_profile_stage import stage_cohort_profile
from hypervector.live.cohort_profit_lock_history import profit_lock_history_limits
from hypervector.live.completed_candle_snapshot_cache import (
    CompletedCandleSnapshotCache,
)
from hypervector.live.hyperliquid_sdk_factory import (
    OfficialHyperliquidReadOnlySdkBuilder,
    HyperliquidSdkFactoryError,
)
from hypervector.live.process_signal_stop import install_process_signal_stop
from hypervector.live.perp_venue_identity import configured_perp_dexes
from hypervector.live.asset_ledger import AssetLiveLedger, AssetLiveLedgerError
from hypervector.runtime_lock import (
    RuntimeLockError,
    bidirectional_observer_runtime_lock,
)


def build_parser() -> argparse.ArgumentParser:
    """Build an observe-only command surface without live-arm flags."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, required=True, help="cohort profile TOML to observe"
    )
    parser.add_argument(
        "--ledger-root",
        type=Path,
        help="Rebind every observe-only ledger below an isolated directory.",
    )
    parser.add_argument(
        "--resume-run-id",
        help="Resume only an existing observer ledger with this exact run ID.",
    )
    parser.add_argument("--max-polls", type=int)
    return parser


def run_observer(args: argparse.Namespace) -> int:
    """Publish completed production signals without constructing venue clients."""
    config = load_multi_asset_live_config(args.config, mode="observe")
    if args.ledger_root is not None:
        config = with_observer_ledger_root(config, args.ledger_root)
    poller = _build_observer_poller(
        config,
        fetch_bars=_observer_candle_fetcher(config, fetch_hl_ohlcv_snapshot),
    )
    public_books = _build_public_books(config)
    with bidirectional_observer_runtime_lock(config.cohort_ledger):
        now = datetime.now(UTC)
        ledger = _build_observer_ledger(config, args.resume_run_id, now)
        telemetry = MultiAssetCohortTelemetry(
            config=config,
            ledger=ledger,
            now_fn=lambda: datetime.now(UTC),
        )
        stop = install_process_signal_stop()
        runner = MultiAssetObserverRunner(
            symbols=config.symbols,
            expected_provider_symbols=frozenset(
                (provider.strategy_id, symbol)
                for provider in config.providers
                for symbol in provider.symbols
            ),
            intent_poller=poller,
            book_source=public_books.collect,
            telemetry=telemetry,
            stop_file=config.stop_file,
            now_fn=lambda: datetime.now(UTC),
            sleep_fn=time.sleep,
            poll_seconds=config.poll_seconds,
            signal_stop_requested=lambda: stop.requested,
            emit_configuration_on_start=args.resume_run_id is None,
            operator_commands=CohortOperatorInbox(
                root=config.cohort_ledger.parent / "operator_commands",
                run_id=ledger.run_id,
                profile_fingerprint=config.profile_fingerprint,
                now_fn=lambda: datetime.now(UTC),
            ),
            profile_stage=lambda settings: stage_cohort_profile(
                config=config,
                settings=settings,
                output_path=config.cohort_ledger.parent / "staged_profile.toml",
            ),
        )
        return runner.run(max_polls=args.max_polls)


def _observer_candle_fetcher(
    config: MultiAssetLiveConfig,
    fetch: CohortBarFetcherProtocol,
) -> CompletedCandleSnapshotCache:
    """Cache entry candles while retaining every profit-lock candle observation."""
    lock_symbols = frozenset(profit_lock_history_limits(config.providers))
    return CompletedCandleSnapshotCache(fetch, uncached_symbols=lock_symbols)


def _build_public_books(config: MultiAssetLiveConfig) -> MultiAssetPublicBookCollector:
    info = OfficialHyperliquidReadOnlySdkBuilder().build(
        perp_dexes=configured_perp_dexes(config.symbols)
    )
    return MultiAssetPublicBookCollector(info=info, symbols=config.symbols)


def _build_observer_ledger(
    config: MultiAssetLiveConfig,
    resume_run_id: str | None,
    now: datetime,
) -> AssetLiveLedger:
    run_id = resume_run_id or f"bidirectional-observe-{int(now.timestamp() * 1_000)}"
    ledger = AssetLiveLedger(
        path=config.cohort_ledger,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=run_id,
        execution_mode="observe",
    )
    rows = ledger.read_all()
    if not rows:
        if resume_run_id is not None:
            raise AssetLiveLedgerError("observer resume requires an existing ledger")
        return ledger
    if resume_run_id is None:
        raise AssetLiveLedgerError("existing observer ledger requires explicit resume")
    _require_resume_identity(rows, config, run_id)
    return ledger


def _require_resume_identity(
    rows: list[dict[str, object]],
    config: MultiAssetLiveConfig,
    run_id: str,
) -> None:
    expected = {
        "schema_version": 1,
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "run_fingerprint": config.run_fingerprint,
    }
    if any(
        any(row.get(field) != value for field, value in expected.items())
        for row in rows
    ):
        raise AssetLiveLedgerError("observer resume identity mismatch")
    run_ids = [row.get("run_id") for row in rows]
    if run_ids[-1] != run_id:
        raise AssetLiveLedgerError("observer resume identity mismatch")
    first = run_ids.index(run_id)
    if any(value != run_id for value in run_ids[first:]):
        raise AssetLiveLedgerError("observer resume identity mismatch")


_with_observer_ledger_root = with_observer_ledger_root


def _build_observer_poller(
    config: MultiAssetLiveConfig,
    *,
    fetch_bars: CohortBarFetcherProtocol,
) -> ConfiguredMultiAssetIntentPoller:
    """Build registered providers and the canonical telemetry for core perps."""
    return ConfiguredMultiAssetIntentPoller.with_registered_collectors(
        config=config,
        fetch_bars=fetch_bars,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the observer and report bounded fail-closed errors."""
    args = build_parser().parse_args(argv)
    try:
        run_observer(args)
        return 0
    except KeyboardInterrupt:
        return 130
    except (
        FileNotFoundError,
        MultiAssetIntentPollerError,
        MultiAssetLiveConfigError,
        MultiAssetObserverRunnerError,
        requests.RequestException,
        RuntimeLockError,
        AssetLiveLedgerError,
        HyperliquidSdkFactoryError,
        CohortOperatorInboxError,
        ValueError,
    ) as exc:
        print(f"cohort observer start refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
