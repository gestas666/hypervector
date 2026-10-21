"""Run the explicitly armed bidirectional multi-asset Hyperliquid cohort."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
import os
from pathlib import Path
import sys
import time
import traceback

import requests

from hypervector.operations.cohort_live_construction import (
    _accounting_epoch as _accounting_epoch,
    _announce_backup as _announce_backup,
    _create_operator_inbox as _create_operator_inbox,
    _create_telemetry as _create_telemetry,
    _create_transition_drain as _create_transition_drain,
    _ledger as _ledger,
    _transition_recovery as _transition_recovery,
)

from hypervector.data.hl import fetch_hl_ohlcv_snapshot
from hypervector.live import cohort_venue_start_probe as venue_probe
from hypervector.live.bidirectional_cohort_factory import (
    AssetExecutionEnvelope,
    MultiAssetCohortAdapters,
    create_armed_multi_asset_adapters,
)
from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
)
from hypervector.live.cohort_runtime_preflight import (
    build_cohort_router,
    validate_runtime_configuration,
)
from hypervector.live.cohort_prestart_backup import (
    CohortPrestartBackupError,
    CohortPrestartBackupResult as CohortPrestartBackupResult,
    create_cohort_prestart_backup,
)
from hypervector.live.cohort_profile_change_approval import (
    ProfileChangeApprovalError,
    require_approved_profile_change,
)
from hypervector.live.cohort_profile_transition_evidence import (
    require_completed_profile_transition as _require_completed_profile_transition,
)
from hypervector.live.cohort_profile_transition_venue import (
    require_profile_transition_venue_boundary as _verify_profile_transition_venue_boundary,
)
from hypervector.live.cohort_runtime_fault import runtime_fault_arguments
from hypervector.live.cohort_entry_submission import entry_delays_from_providers
from hypervector.live.cohort_implementation_sources import (
    discover_cohort_implementation_sources,
    discover_installed_cohort_sources,
    implementation_source_identity,
)
from hypervector.live.hyperliquid_perp_reader import VenueMetadataMismatchError
from hypervector.live.cohort_transition_drain import (
    CohortTransitionDrain,
    CohortTransitionDrainError,
)
from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_intent_poller import (
    CohortBarFetcherProtocol,
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.multi_asset_live_runner_support import (
    CohortDegradedBlindnessError,
    MultiAssetLiveRunnerError,
)
from hypervector.live.process_signal_stop import (
    ProcessSignalStop,
    install_process_signal_stop,
    raise_if_stop_requested,
    stop_aware_sleep,
)
from hypervector.live.asset_engine import AssetLiveEngine
from hypervector.live.asset_ledger import AssetLiveLedger
from hypervector.runtime_env import (
    CredentialPresence,
    credential_presence_from_env,
    load_dotenv_if_present,
)
from hypervector.runtime_lock import (
    RuntimeLockError,
    bidirectional_live_runtime_lock,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_MAX_READ_COALESCE_SECONDS = 10.0
_READ_COALESCE_POLL_FRACTION = 0.8
# (connect, read) for the public candle reads only. One hung read then ends
# inside the 15 s poll period instead of the research default's 30 s; account
# reads and order calls keep their own client timeouts.
_PUBLIC_CANDLE_TIMEOUT_SECONDS = (5.0, 10.0)
EXIT_RUN_FAILED = 1
EXIT_START_REFUSED = 2
# The account stayed unreconciled past the runner's wall-clock bound. The
# supervisor relaunches this without charging its crash budget: the relaunch
# waits in process for the venue before any bundle or replay. Must equal
# scripts/cohort_supervisor_restart_policy.py EXIT_DEGRADED_BLINDNESS.
EXIT_DEGRADED_BLINDNESS = 4


class CohortRunFailure(RuntimeError):
    """Mark a runtime crash separately from a technical start refusal.

    Preserve the cause for supervisor retry and degraded-blindness exit policy.
    """


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit live-only cohort command boundary."""
    parser = argparse.ArgumentParser(description=__doc__)
    # Required: the old default named a canary profile that is now a test
    # fixture; the supervised start always passes --config explicitly.
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--i-accept-live-risk", action="store_true")
    parser.add_argument("--accounting-epoch-bundle", type=Path)
    parser.add_argument(
        "--resume-transition-drain",
        action="store_true",
        help="resume only an active same-profile drain after a backend interruption",
    )
    parser.add_argument("--max-polls", type=int)
    return parser


def build_router(config: MultiAssetLiveConfig) -> BidirectionalIntentRouter:
    """Construct declared provider capabilities without performance gates."""
    return build_cohort_router(config)


def run_live(args: argparse.Namespace) -> int:
    """Validate all authority boundaries before constructing an SDK client."""
    config = load_multi_asset_live_config(
        args.config,
        mode="live",
        enabled=args.enabled,
        accepts_live_risk=args.i_accept_live_risk,
    )
    presence = credential_presence_from_env()
    credentials_present = presence.wallet_configured and presence.signing_key_configured
    config.require_live_start(credentials_present=credentials_present)
    # Everything the runner refuses at construction is knowable here, before the
    # mandatory backup, the ledger replay and any authenticated venue client.
    validate_runtime_configuration(config)
    _accounting_epoch(args, config)
    if config.stop_file.exists():
        raise MultiAssetLiveConfigError(
            f"operator stop file exists; inspect before removing: {config.stop_file}"
        )
    # Created here so the public candle reads consult the latch the run loop
    # uses. Its handlers are installed only with the runner, so a signal during
    # the start boundaries still ends the process at once, as it always has.
    signal_stop = ProcessSignalStop()
    with requests.Session() as candle_session:
        poller = ConfiguredMultiAssetIntentPoller.with_registered_collectors(
            config=config,
            fetch_bars=_live_candle_fetcher(
                candle_session,
                partial(_backend_stop_requested, config.stop_file, signal_stop),
            ),
        )
        with bidirectional_live_runtime_lock(config.cohort_ledger) as lock_path:
            return _run_locked(
                args,
                config,
                presence,
                poller,
                lock_path=lock_path,
                signal_stop=signal_stop,
            )


def _live_candle_fetcher(
    session: requests.Session,
    stop_requested: Callable[[], bool],
) -> CohortBarFetcherProtocol:
    """Return the cohort's public candle read, abandoned once a stop is requested.

    The stop is checked before every per-symbol read and every retry, and the
    retry waits end within a second of it, so a stop never waits out the ladder.
    """
    return partial(
        fetch_hl_ohlcv_snapshot,
        session=session,
        timeout=_PUBLIC_CANDLE_TIMEOUT_SECONDS,
        sleep_fn=partial(stop_aware_sleep, stop_requested=stop_requested),
        stop_check=partial(raise_if_stop_requested, stop_requested),
    )


def _backend_stop_requested(stop_file: Path, signal_stop: ProcessSignalStop) -> bool:
    """Mirror the runner's stop test: a latched signal or the operator stop file."""
    return signal_stop.requested or stop_file.exists()


def _run_locked(
    args: argparse.Namespace,
    config: MultiAssetLiveConfig,
    presence: CredentialPresence,
    poller: ConfiguredMultiAssetIntentPoller,
    lock_path: Path | None = None,
    signal_stop: ProcessSignalStop | None = None,
) -> int:
    transition_path = config.cohort_ledger.parent / "transition_drain.json"
    recovery = _transition_recovery(args, config, transition_path)
    imported = implementation_source_identity(_implementation_sources())
    _await_venue(config)
    _refresh_start_grace(lock_path)
    # Stamped after any venue wait, so the run and its bundle carry the time the
    # start actually proceeded.
    now = datetime.now(UTC)
    run_id = f"bidirectional-live-{int(now.timestamp() * 1_000)}"
    sources = _implementation_sources()
    _require_unchanged_implementation(imported, sources)
    backup = create_cohort_prestart_backup(
        config, now=now, implementation_sources=sources
    )
    _announce_backup(backup)
    _require_completed_profile_transition(config, backup)
    require_approved_profile_change(config, backup)
    transition_drain = _create_transition_drain(
        transition_path, config, run_id, recovery
    )
    adapters = _create_adapters(config)
    _verify_profile_transition_venue_boundary(config, backup, adapters)
    asset_ledgers, engines = _create_engines(config, adapters, presence, run_id)
    telemetry = _create_telemetry(
        config, asset_ledgers, run_id, backup, transition_drain
    )
    runner = _create_runner(
        config,
        engines,
        poller,
        telemetry,
        transition_drain,
        run_id,
        signal_stop=signal_stop,
    )
    return _run_started_runner(runner, telemetry, max_polls=args.max_polls)


def _run_started_runner(
    runner: MultiAssetLiveRunner,
    telemetry: MultiAssetCohortTelemetry,
    *,
    max_polls: int | None,
) -> int:
    """Distinguish runtime crashes from persistent venue start refusals."""
    try:
        return _run_guarded(runner, telemetry, max_polls=max_polls)
    except Exception as exc:
        mismatch = _venue_metadata_mismatch(exc)
        if mismatch is not None:
            # A venue contract fact survives a relaunch, so every retry would
            # fail the same way after another full backup and replay.
            raise VenueMetadataMismatchError(str(mismatch)) from exc
        raise CohortRunFailure(str(exc)) from exc


def _await_venue(config: MultiAssetLiveConfig) -> None:
    """Wait, inside the runtime lock, for a venue whose markets match the profile.

    It runs before the pre-start bundle, so an offline host neither writes a
    bundle nor crashes into a charged relaunch, and the lock names this waiting
    process so the supervisor sees a live backend rather than an absent one.
    """
    with requests.Session() as session:
        venue_probe.await_venue_start(
            {asset.symbol: int(asset.venue_max_leverage) for asset in config.assets},
            fetch_meta=venue_probe.http_meta_fetcher(session),
            stop_file=config.stop_file,
            marker=config.cohort_ledger.parent / venue_probe.VENUE_WAIT_MARKER,
            sleep_fn=time.sleep,
            requested_leverage=venue_probe.requested_market_leverage(config),
        )


def _implementation_sources() -> dict[str, Path]:
    if not (_REPOSITORY_ROOT / "src" / "hypervector").is_dir():
        return discover_installed_cohort_sources()
    return discover_cohort_implementation_sources(_REPOSITORY_ROOT)


def _require_unchanged_implementation(
    imported: dict[str, object], sources: dict[str, Path]
) -> None:
    """Refuse a start whose sources changed while this process waited for the venue.

    The modules were imported when the process started, but the bundle hashes
    the sources only after the wait, which has no upper bound. A difference
    means the bundle would fingerprint code this process is not running.
    """
    current = implementation_source_identity(sources)
    if current != imported:
        raise MultiAssetLiveConfigError(
            "implementation sources changed during the venue wait "
            f"(files {imported['file_count']} -> {current['file_count']}, "
            f"sha256 {imported['sha256']} -> {current['sha256']}); "
            "this process runs the code imported at its start, so restart the "
            "backend on the current sources"
        )


def _refresh_start_grace(lock_path: Path | None) -> None:
    """Restart the monitors' startup grace once the venue wait has returned.

    The watch agent anchors its grace on the runtime lock's age, and the lock was
    written before the wait, so after a long wait the replay still ahead read as
    a stale heartbeat. Only the lock this process holds is refreshed. The grace
    is advisory monitoring, not an execution boundary, so a failed refresh is
    reported and the start proceeds.
    """
    if lock_path is None:
        return
    try:
        os.utime(lock_path)
    except OSError as exc:
        print(f"runtime lock not refreshed after the venue wait: {type(exc).__name__}")


def _venue_metadata_mismatch(error: BaseException) -> BaseException | None:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, VenueMetadataMismatchError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def _create_runner(
    config: MultiAssetLiveConfig,
    engines: dict[str, AssetLiveEngine],
    poller: ConfiguredMultiAssetIntentPoller,
    telemetry: MultiAssetCohortTelemetry,
    transition_drain: CohortTransitionDrain,
    run_id: str,
    signal_stop: ProcessSignalStop | None = None,
) -> MultiAssetLiveRunner:
    """Construct the runtime only after every startup boundary has passed."""
    poller.bind_startup_input_observer(telemetry.startup_input_observer())
    stop = install_process_signal_stop(signal_stop)
    return MultiAssetLiveRunner(
        symbols=config.symbols,
        engines=engines,
        router=build_router(config),
        intent_poller=poller,
        telemetry=telemetry,
        stop_file=config.stop_file,
        now_fn=lambda: datetime.now(UTC),
        # The inter-poll wait re-checks the stop every second: a handled signal
        # does not end time.sleep early.
        sleep_fn=partial(
            stop_aware_sleep,
            stop_requested=partial(_backend_stop_requested, config.stop_file, stop),
        ),
        poll_seconds=config.poll_seconds,
        signal_stop_requested=lambda: stop.requested,
        funding_recovery_start_ms=telemetry.funding_recovery_start_ms,
        maximum_hold_seconds_by_symbol={
            asset.symbol: asset.maximum_hold_seconds for asset in config.assets
        },
        execution_contracts=config.provider_execution_contracts,
        maximum_entry_delay_ms_by_provider_symbol=entry_delays_from_providers(
            config.providers
        ),
        executable_provider_symbols=config.executable_provider_symbols,
        executable_provider_directions=config.executable_provider_directions,
        provider_entry_sizing=config.provider_entry_sizing,
        provider_directional_entry_sizing=(config.provider_directional_entry_sizing),
        operator_commands=_create_operator_inbox(config, run_id),
        transition_drain=transition_drain,
        venue_unreachable_reason=lambda: venue_probe.fresh_session_unreachable_reason(
            config.symbols
        ),
    )


def _run_guarded(
    runner: MultiAssetLiveRunner,
    telemetry: MultiAssetCohortTelemetry,
    *,
    max_polls: int | None,
) -> int:
    """Journal unexpected process failures and preserve fail-closed propagation."""
    try:
        return runner.run(max_polls=max_polls)
    except Exception as exc:
        telemetry.emit_runtime_fault(**runtime_fault_arguments(exc))
        raise


def _create_adapters(config: MultiAssetLiveConfig) -> MultiAssetCohortAdapters:
    requested = venue_probe.requested_market_leverage(config)
    envelopes = tuple(
        AssetExecutionEnvelope(
            asset.symbol,
            asset.max_notional_usd,
            asset.market_slippage_cap_fraction,
            asset.effective_entry_slippage_cap_fraction,
            requested_leverage=requested[asset.symbol],
        )
        for asset in config.assets
    )
    return create_armed_multi_asset_adapters(
        envelopes,
        enabled=config.enabled,
        accepts_live_risk=config.accepts_live_risk,
        read_coalesce_seconds=min(
            _MAX_READ_COALESCE_SECONDS,
            config.poll_seconds * _READ_COALESCE_POLL_FRACTION,
        ),
    )


def _create_engines(
    config: MultiAssetLiveConfig,
    adapters: MultiAssetCohortAdapters,
    presence: CredentialPresence,
    run_id: str,
) -> tuple[dict[str, AssetLiveLedger], dict[str, AssetLiveEngine]]:
    ledgers = {
        asset.symbol: _ledger(asset.live_ledger, asset, run_id)
        for asset in config.assets
    }
    credentials_present = presence.wallet_configured and presence.signing_key_configured
    engines = {
        asset.symbol: AssetLiveEngine(
            config=asset,
            adapter=adapters.by_symbol[asset.symbol],
            ledger=ledgers[asset.symbol],
            credentials_present=credentials_present,
            now_fn=lambda: datetime.now(UTC),
            reconciliation_cache_invalidator=(
                adapters.by_symbol[asset.symbol].invalidate_reconciliation_cache
            ),
        )
        for asset in config.assets
    }
    return ledgers, engines


def main() -> int:
    """Load local credentials and run the explicitly armed mainnet cohort."""
    args = build_parser().parse_args()
    if args.enabled and args.i_accept_live_risk:
        load_dotenv_if_present()
    try:
        run_live(args)
        return 0
    except CohortRunFailure as exc:
        cause = exc.__cause__ or exc
        traceback.print_exception(cause)
        if isinstance(cause, CohortDegradedBlindnessError):
            return EXIT_DEGRADED_BLINDNESS
        return EXIT_RUN_FAILED
    except (
        FileNotFoundError,
        CohortPrestartBackupError,
        ProfileChangeApprovalError,
        CohortTransitionDrainError,
        MultiAssetLiveConfigError,
        MultiAssetLiveRunnerError,
        RuntimeLockError,
        ValueError,
        VenueMetadataMismatchError,
    ) as exc:
        print(f"live start refused: {exc}", file=sys.stderr)
        return EXIT_START_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
