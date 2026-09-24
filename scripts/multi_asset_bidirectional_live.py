"""Run the explicitly armed bidirectional multi-asset Hyperliquid cohort."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
import sys
import time
import traceback

import requests

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
    CohortPrestartBackupResult,
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
from hypervector.live.cohort_accounting_rollover import (
    load_required_accounting_epoch,
)
from hypervector.live.cohort_entry_submission import entry_delays_from_providers
from hypervector.live.cohort_implementation_sources import (
    discover_cohort_implementation_sources,
)
from hypervector.live.hyperliquid_perp_reader import VenueMetadataMismatchError
from hypervector.live.cohort_transition_drain import (
    CohortTransitionDrain,
    CohortTransitionDrainError,
    CohortTransitionDrainSnapshot,
    ensure_transition_drain_startable,
    load_transition_drain_snapshot,
)
from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_intent_poller import ConfiguredMultiAssetIntentPoller
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.multi_asset_live_runner_support import (
    CohortDegradedBlindnessError,
    MultiAssetLiveRunnerError,
)
from hypervector.live.cohort_operator_commands import (
    CohortOperatorInbox,
    operator_command_maximum_age_seconds,
)
from hypervector.live.process_signal_stop import install_process_signal_stop
from hypervector.live.sol_range_onset_engine import SolRangeOnsetLiveEngine
from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.runtime_env import (
    CredentialPresence,
    credential_presence_from_env,
    load_dotenv_if_present,
)
from hypervector.runtime_lock import (
    RuntimeLockError,
    bidirectional_live_runtime_lock,
)
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

_CONFIG_NAME = "multi_asset_bidirectional_complete_portfolio_canary_v25.toml"
_DEFAULT_CONFIG = Path("configs") / _CONFIG_NAME
_DEFAULT_BACKTEST_LAB = Path("../backtest-lab/backtest_lab")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_MAX_READ_COALESCE_SECONDS = 10.0
_READ_COALESCE_POLL_FRACTION = 0.8
EXIT_RUN_FAILED = 1
EXIT_START_REFUSED = 2
# The account stayed unreconciled past the runner's wall-clock bound. The
# supervisor relaunches this without charging its crash budget: the relaunch
# waits in process for the venue before any bundle or replay. Must equal
# scripts/cohort_supervisor_restart_policy.py EXIT_DEGRADED_BLINDNESS.
EXIT_DEGRADED_BLINDNESS = 4


class CohortRunFailure(RuntimeError):
    """A failure raised after the runner was built, never a start refusal.

    ``ValueError`` and ``MultiAssetLiveRunnerError`` can both be raised while the
    start boundaries are still being checked and long after the first poll. The
    supervisor holds on ``EXIT_START_REFUSED`` and relaunches on any other nonzero
    code, so the two phases must stay distinguishable: a refusal a human has to
    resolve must not be retried, and a crash a bounded restart would clear must
    not park the backend. ``_run_guarded`` keeps re-raising the original fault so
    its stage classification stays exact; this marker is applied one level up, at
    the phase boundary itself.
    """


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit live-only cohort command boundary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    parser.add_argument(
        "--backtest-lab-root",
        type=Path,
        default=_DEFAULT_BACKTEST_LAB,
    )
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
    with requests.Session() as candle_session:
        poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
            config=config,
            fetch_bars=partial(fetch_hl_ohlcv_snapshot, session=candle_session),
            backtest_lab_root=args.backtest_lab_root.resolve(),
        )
        with bidirectional_live_runtime_lock(config.cohort_ledger):
            return _run_locked(args, config, presence, poller)


def _run_locked(
    args: argparse.Namespace,
    config: MultiAssetLiveConfig,
    presence: CredentialPresence,
    poller: ConfiguredMultiAssetIntentPoller,
) -> int:
    transition_path = config.cohort_ledger.parent / "transition_drain.json"
    recovery = _transition_recovery(args, config, transition_path)
    _await_venue(config)
    # Stamped after any venue wait, so the run and its bundle carry the time the
    # start actually proceeded.
    now = datetime.now(UTC)
    run_id = f"bidirectional-live-{int(now.timestamp() * 1_000)}"
    sources = discover_cohort_implementation_sources(
        _REPOSITORY_ROOT,
        args.backtest_lab_root.resolve(),
    )
    backup = create_cohort_prestart_backup(
        config,
        now=now,
        implementation_sources=sources,
    )
    _announce_backup(backup)
    _require_completed_profile_transition(config, backup)
    require_approved_profile_change(config, backup)
    transition_drain = _create_transition_drain(
        transition_path,
        config,
        run_id,
        recovery,
    )
    adapters = _create_adapters(config)
    _verify_profile_transition_venue_boundary(config, backup, adapters)
    asset_ledgers, engines = _create_engines(config, adapters, presence, run_id)
    telemetry = _create_telemetry(
        config,
        asset_ledgers,
        run_id,
        backup,
        transition_drain,
    )
    runner = _create_runner(
        config, engines, poller, telemetry, transition_drain, run_id
    )
    try:
        return _run_guarded(runner, telemetry, max_polls=args.max_polls)
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
        )


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
    engines: dict[str, SolRangeOnsetLiveEngine],
    poller: ConfiguredMultiAssetIntentPoller,
    telemetry: MultiAssetCohortTelemetry,
    transition_drain: CohortTransitionDrain,
    run_id: str,
) -> MultiAssetLiveRunner:
    """Construct the runtime only after every startup boundary has passed."""
    poller.bind_startup_input_observer(telemetry.startup_input_observer())
    stop = install_process_signal_stop()
    return MultiAssetLiveRunner(
        symbols=config.symbols,
        engines=engines,
        router=build_router(config),
        intent_poller=poller,
        telemetry=telemetry,
        stop_file=config.stop_file,
        now_fn=lambda: datetime.now(UTC),
        sleep_fn=time.sleep,
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


def _accounting_epoch(
    args: argparse.Namespace,
    config: MultiAssetLiveConfig,
) -> CohortAccountingEpoch | None:
    """Verify any profile-required reporting epoch before live construction."""
    bundle = getattr(args, "accounting_epoch_bundle", None)
    return load_required_accounting_epoch(bundle, config)


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


def _transition_recovery(
    args: argparse.Namespace,
    config: MultiAssetLiveConfig,
    path: Path,
) -> CohortTransitionDrainSnapshot | None:
    if not args.resume_transition_drain:
        ensure_transition_drain_startable(path)
        return None
    snapshot = load_transition_drain_snapshot(path)
    if snapshot.status != "active":
        raise CohortTransitionDrainError("recovery requires an active drain")
    if snapshot.profile_fingerprint != config.profile_fingerprint:
        raise CohortTransitionDrainError(
            "transition drain recovery profile identity differs"
        )
    return snapshot


def _create_transition_drain(
    path: Path,
    config: MultiAssetLiveConfig,
    run_id: str,
    recovery: CohortTransitionDrainSnapshot | None,
) -> CohortTransitionDrain:
    current_run = run_id if recovery is None else recovery.run_id
    drain = CohortTransitionDrain(
        path=path,
        run_id=current_run,
        profile_fingerprint=config.profile_fingerprint,
        now_fn=lambda: datetime.now(UTC),
    )
    if recovery is not None:
        drain.resume_for_run(run_id)
    return drain


def _announce_backup(backup: CohortPrestartBackupResult) -> None:
    """Emit non-secret evidence that the mandatory pre-start backup passed."""
    changed = "yes" if backup.strategy_changed else "no"
    print(
        "pre-start backup verified: "
        f"path={backup.path} manifest_sha256={backup.manifest_sha256} "
        f"implementation_files={backup.implementation_file_count} "
        f"implementation_sha256={backup.implementation_sha256} "
        f"strategy_changed={changed}"
    )


def _create_adapters(config: MultiAssetLiveConfig) -> MultiAssetCohortAdapters:
    envelopes = tuple(
        AssetExecutionEnvelope(
            asset.symbol,
            asset.max_notional_usd,
            asset.market_slippage_cap_fraction,
            asset.effective_entry_slippage_cap_fraction,
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


def _create_operator_inbox(
    config: MultiAssetLiveConfig,
    run_id: str,
) -> CohortOperatorInbox:
    return CohortOperatorInbox(
        root=config.cohort_ledger.parent / "operator_commands",
        run_id=run_id,
        profile_fingerprint=config.profile_fingerprint,
        now_fn=lambda: datetime.now(UTC),
        maximum_age_seconds=operator_command_maximum_age_seconds(
            poll_seconds=config.poll_seconds,
            symbol_count=len(config.symbols),
        ),
    )


def _create_engines(
    config: MultiAssetLiveConfig,
    adapters: MultiAssetCohortAdapters,
    presence: CredentialPresence,
    run_id: str,
) -> tuple[dict[str, SolLiveLedger], dict[str, SolRangeOnsetLiveEngine]]:
    ledgers = {
        asset.symbol: _ledger(asset.live_ledger, asset, run_id)
        for asset in config.assets
    }
    credentials_present = presence.wallet_configured and presence.signing_key_configured
    engines = {
        asset.symbol: SolRangeOnsetLiveEngine(
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


def _create_telemetry(
    config: MultiAssetLiveConfig,
    asset_ledgers: dict[str, SolLiveLedger],
    run_id: str,
    backup: CohortPrestartBackupResult,
    transition_drain: CohortTransitionDrain,
) -> MultiAssetCohortTelemetry:
    cohort_ledger = SolLiveLedger(
        path=config.cohort_ledger,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=run_id,
    )
    return MultiAssetCohortTelemetry(
        config=config,
        ledger=cohort_ledger,
        now_fn=lambda: datetime.now(UTC),
        asset_ledgers=asset_ledgers,
        prestart_backup=backup,
        transition_drain=transition_drain,
    )


def _ledger(path: Path, config: AssetLiveConfig, run_id: str) -> SolLiveLedger:
    return SolLiveLedger(
        path=path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=run_id,
    )


def main() -> int:
    """Load local credentials and run the explicitly armed mainnet cohort."""
    load_dotenv_if_present()
    try:
        run_live(build_parser().parse_args())
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
