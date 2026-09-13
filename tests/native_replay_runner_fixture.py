"""Actual configured poller, runner and telemetry around explicitly offline engine ports."""

from datetime import datetime

from native_replay_protective_fixture import ProtectiveEngineFixture
from scripts.multi_asset_bidirectional_live import build_router

from hypervector.live.cohort_entry_submission import entry_delays_from_providers
from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_intent_poller import (
    CohortIntentPoll,
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.research.native_runner_recorded_fetch import RecordedRunnerFetch


class ClockedConfiguredPoller:
    """Retain native provider output while applying the declared profiler-time model."""

    def __init__(
        self, poller: ConfiguredMultiAssetIntentPoller, fetch: RecordedRunnerFetch
    ) -> None:
        """Bind the actual configured poller to the shared recorded transport clock."""
        self.poller, self.fetch = poller, fetch

    def activate(self, activation_time_ms: int) -> None:
        """Use the native no-retro-entry activation boundary unchanged."""
        self.poller.activate(activation_time_ms)

    def poll(self, observed_at: datetime) -> CohortIntentPoll:
        """Run native acquisition/providers before applying remaining profiled CPU duration."""
        result = self.poller.poll(observed_at)
        self.fetch.finish_poll()
        return result


def configured_recorded_runner(
    replay: ProtectiveEngineFixture, fetch: RecordedRunnerFetch
) -> tuple[MultiAssetLiveRunner, SolLiveLedger]:
    """Assemble the actual seven-asset runtime without calling its live-client factory."""
    config = replay.config
    replay.engines = {asset.symbol: replay.engine(asset) for asset in config.assets}
    ledger = SolLiveLedger(
        path=replay.root / "live/bidirectional_cohort/cohort.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="offline-native-account",
    )
    telemetry = MultiAssetCohortTelemetry(
        config=config,
        ledger=ledger,
        now_fn=replay.clock.now,
        asset_ledgers={symbol: engine._ledger for symbol, engine in replay.engines.items()},
    )
    native = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=fetch,
        backtest_lab_root=config.source_path.resolve().parents[2] / "backtest-lab",
    )
    poller = ClockedConfiguredPoller(native, fetch)
    return _runner(replay, poller, telemetry), ledger


def _runner(
    replay: ProtectiveEngineFixture,
    poller: ClockedConfiguredPoller,
    telemetry: MultiAssetCohortTelemetry,
) -> MultiAssetLiveRunner:
    config = replay.config
    return MultiAssetLiveRunner(
        symbols=config.symbols,
        engines=replay.engines,
        router=build_router(config),
        intent_poller=poller,
        telemetry=telemetry,
        stop_file=replay.root / "STOP",
        now_fn=replay.clock.now,
        sleep_fn=replay.clock.sleep,
        monotonic_fn=replay.clock.monotonic,
        poll_seconds=config.poll_seconds,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={a.symbol: a.maximum_hold_seconds for a in config.assets},
        execution_contracts=config.provider_execution_contracts,
        maximum_entry_delay_ms_by_provider_symbol=entry_delays_from_providers(config.providers),
        executable_provider_symbols=config.executable_provider_symbols,
        executable_provider_directions=config.executable_provider_directions,
        provider_entry_sizing=config.provider_entry_sizing,
        provider_directional_entry_sizing=config.provider_directional_entry_sizing,
    )
