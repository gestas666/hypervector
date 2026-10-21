"""Source-checkout native runner assembly with signing-incapable shared SDK ports."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from itertools import count
from pathlib import Path

from hypervector.live.cohort_runtime_preflight import build_cohort_router as build_router

from hypervector.live.cohort_entry_submission import entry_delays_from_providers
from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_directional_adapter import MultiAssetDirectionalAdapter
from hypervector.live.multi_asset_intent_poller import (
    CohortBarFetcherProtocol,
    CohortIntentPoll,
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import AssetLiveConfig, MultiAssetLiveConfig
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.sol_range_onset_engine import SolRangeOnsetLiveEngine
from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.research.native_replay_origins import NativeReplayOrigins
from hypervector.research.native_replay_sdk import ReplaySdk

OFFLINE_ADDRESS = "0x" + "0" * 40
OFFLINE_RUN_ID = "offline-native-account-replay"


@dataclass(frozen=True)
class NativeReplayRunner:
    """The actual runtime and its separate, native-shaped research telemetry writers."""

    runner: MultiAssetLiveRunner
    engines: dict[str, SolRangeOnsetLiveEngine]
    ledgers: dict[str, SolLiveLedger]
    cohort_ledger: SolLiveLedger


class ReplayConfiguredPoller:
    """Retain native acquisition/strategy behavior with an explicit optional elapsed profile."""

    def __init__(
        self, poller: ConfiguredMultiAssetIntentPoller, finish_poll: Callable[[], None] | None
    ) -> None:
        """Bind the original poller and a declared post-processing clock adjustment."""
        self.poller, self.finish_poll = poller, finish_poll

    def activate(self, activation_time_ms: int) -> None:
        """Keep the native no-retroactive-entry activation boundary."""
        self.poller.activate(activation_time_ms)

    def poll(self, observed_at: datetime) -> CohortIntentPoll:
        """Return the native provider output after its declared acquisition/CPU timing."""
        result = self.poller.poll(observed_at)
        if self.finish_poll is not None:
            self.finish_poll()
        return result


def build_native_replay_runner(
    *,
    config: MultiAssetLiveConfig,
    replay: ReplaySdk,
    fetch_bars: CohortBarFetcherProtocol,
    output_root: Path,
    finish_poll: Callable[[], None] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> NativeReplayRunner:
    """Build all configured real engines/runner without invoking any live-client factory."""
    if not isinstance(replay, ReplaySdk) or replay.symbols != config.symbols:
        raise ValueError(
            "native replay requires offline SDK ports for the exact configured universe"
        )
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / "OFFLINE_REPLAY").write_text(
        "Native-shaped simulation ledgers; no live SDK clients or transactions.\n"
    )
    ledgers = {asset.symbol: _ledger(asset, output_root, asset.symbol) for asset in config.assets}
    replay.decision_time = NativeReplayOrigins(replay.clock, ledgers)
    identities = count(1)
    wait = sleep_fn or replay.runtime_clock.sleep
    engines = {
        asset.symbol: _engine(
            replay,
            asset,
            ledgers[asset.symbol],
            wait,
            lambda: f"0x{next(identities):032x}",
        )
        for asset in config.assets
    }
    cohort = _ledger(config, output_root, "cohort")
    telemetry = MultiAssetCohortTelemetry(
        config=config,
        ledger=cohort,
        now_fn=replay.clock.now,
        asset_ledgers=ledgers,
    )
    runner = _runner(
        config,
        replay,
        engines,
        _poller(config, fetch_bars, finish_poll),
        telemetry,
        output_root / "STOP",
        wait,
    )
    return NativeReplayRunner(runner, engines, ledgers, cohort)


def _poller(
    config: MultiAssetLiveConfig,
    fetch_bars: CohortBarFetcherProtocol,
    finish_poll: Callable[[], None] | None,
) -> ReplayConfiguredPoller:
    poller = ConfiguredMultiAssetIntentPoller.with_registered_collectors(
        config=config,
        fetch_bars=fetch_bars,
    )
    return ReplayConfiguredPoller(poller, finish_poll)


def _ledger(config: MultiAssetLiveConfig | AssetLiveConfig, root: Path, name: str) -> SolLiveLedger:
    return SolLiveLedger(
        path=root / "live/bidirectional_cohort" / f"{name}.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=OFFLINE_RUN_ID,
    )


def _engine(
    replay: ReplaySdk,
    asset: AssetLiveConfig,
    ledger: SolLiveLedger,
    sleep_fn: Callable[[float], None],
    client_id: Callable[[], str],
) -> SolRangeOnsetLiveEngine:
    asset = replace(asset, live_ledger=ledger.path)
    adapter = MultiAssetDirectionalAdapter(
        BtcHyperliquidAdapter(
            info=replay.info,
            exchange=replay.exchange,
            account_address=OFFLINE_ADDRESS,
            max_notional_usd=asset.max_notional_usd,
            slippage_fraction=asset.market_slippage_cap_fraction,
            entry_slippage_fraction=asset.entry_slippage_cap_fraction,
            symbol=asset.symbol,
            perp_dex=replay.markets[asset.symbol].perp_dex,
        )
    )
    return SolRangeOnsetLiveEngine(
        config=asset,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=replay.clock.now,
        sleep_fn=sleep_fn,
        client_order_id_fn=client_id,
    )


def _runner(
    config: MultiAssetLiveConfig,
    replay: ReplaySdk,
    engines: dict[str, SolRangeOnsetLiveEngine],
    poller: ReplayConfiguredPoller,
    telemetry: MultiAssetCohortTelemetry,
    stop_file: Path,
    sleep_fn: Callable[[float], None],
) -> MultiAssetLiveRunner:
    return MultiAssetLiveRunner(
        symbols=config.symbols,
        engines=engines,
        router=build_router(config),
        intent_poller=poller,
        telemetry=telemetry,
        stop_file=stop_file,
        now_fn=replay.clock.now,
        sleep_fn=sleep_fn,
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
