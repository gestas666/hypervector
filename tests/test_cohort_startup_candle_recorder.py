"""Observable archival failure and exact command/ledger binding without execution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

from cohort_startup_candle_support import OBSERVED, OBSERVED_MS, candle_frame
from test_multi_asset_bidirectional_live_script import _load_module
from test_multi_asset_cohort_telemetry import _telemetry
from test_multi_asset_intent_poller import _CanonicalCollector, _Collector

from hypervector.live.cohort_startup_candle_recorder import CohortStartupCandleRecorder
from hypervector.live.cohort_startup_candles import StartupCandleContext, load_startup_candles
from hypervector.live.multi_asset_intent_poller import ConfiguredMultiAssetIntentPoller
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError


def test_recorder_event_authenticates_exact_ledger_identity(tmp_path: Path) -> None:
    """A successful capture is small, replayable and bound to the emitting run."""
    telemetry, ledger = _telemetry(tmp_path)
    recorder = telemetry.startup_input_observer()
    frames = {symbol: candle_frame() for symbol in recorder.config.symbols}
    recorder(frames, OBSERVED_MS - 60_000, OBSERVED_MS)
    row, = ledger.read_all()
    payload = row["payload"]
    assert row["event_type"] == "startup_candle_inputs"
    assert payload["status"] == "captured"
    assert payload["execution_authority"] == "none"
    identity = payload["context"]
    assert identity["run_id"] == row["run_id"] == ledger.run_id
    assert identity["profile_fingerprint"] == row["profile_fingerprint"]
    context = StartupCandleContext(**{**identity, "symbols": tuple(identity["symbols"])})
    restored = load_startup_candles(Path(payload["manifest_path"]), payload["manifest_sha256"], context)
    assert ledger.path.stat().st_size < 2500
    for symbol, frame in frames.items():
        pd.testing.assert_frame_equal(frame, restored[symbol], check_exact=True)


@pytest.mark.parametrize("error", [OSError("disk full"), ImportError("missing pyarrow"), ValueError("bad frame")])
def test_capture_failure_is_explicit_and_does_not_suppress_provider_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception,
) -> None:
    """Expected archive failures retain normal decisions and an unavailable event."""
    telemetry, ledger = _telemetry(tmp_path)
    recorder = telemetry.startup_input_observer()
    collector_map = {p.strategy_id: _Collector(p.strategy_id, emit=False) for p in recorder.config.providers}

    def fail_write(*args: object, **kwargs: object) -> None:
        """Simulate one known archival failure without touching live files."""
        raise error

    monkeypatch.setattr("hypervector.live.cohort_startup_candle_recorder.write_startup_candles", fail_write)
    poller = ConfiguredMultiAssetIntentPoller(
        config=recorder.config, fetch_bars=lambda *args, **kwargs: candle_frame(),
        collectors=collector_map, canonical_regime_collector=_CanonicalCollector(),
    )
    poller.bind_startup_input_observer(recorder)
    poller.activate(OBSERVED_MS - 60_000)
    result = poller.poll(OBSERVED)
    poller.poll(OBSERVED)
    assert result.evaluations
    assert all(collector.bar_counts for collector in collector_map.values())
    row, = ledger.read_all()
    assert row["payload"]["status"] == "unavailable"
    assert row["payload"]["error_type"] == type(error).__name__
    assert row["payload"]["reason"] == str(error)
    assert "manifest_path" not in row["payload"]


def test_ledger_failure_propagates_after_capture(tmp_path: Path) -> None:
    """An unavailable authoritative ledger does not become a successful event."""
    telemetry, _ledger = _telemetry(tmp_path)

    def fail_emit(_event: str, _payload: object) -> None:
        """Represent the existing fatal durable-ledger failure boundary."""
        raise OSError("ledger unavailable")

    recorder = replace(telemetry.startup_input_observer(), emit=fail_emit)
    with pytest.raises(OSError, match="ledger unavailable"):
        recorder({s: candle_frame() for s in recorder.config.symbols}, OBSERVED_MS, OBSERVED_MS)


def test_transient_fetch_failure_captures_only_after_successful_full_cycle(tmp_path: Path) -> None:
    """Partial symbol fetches cannot publish a complete startup archive."""
    telemetry, ledger = _telemetry(tmp_path)
    recorder = telemetry.startup_input_observer()
    calls = 0

    def fetch(*args: object, **kwargs: object) -> pd.DataFrame:
        """Fail the second asset once, then return complete offline history."""
        nonlocal calls
        calls += 1
        if calls == 2:
            raise requests.Timeout("offline transient test")
        return candle_frame()

    poller = ConfiguredMultiAssetIntentPoller(
        config=recorder.config, fetch_bars=fetch,
        collectors={p.strategy_id: _Collector(p.strategy_id, emit=False) for p in recorder.config.providers},
        canonical_regime_collector=_CanonicalCollector(),
    )
    poller.bind_startup_input_observer(recorder)
    poller.activate(OBSERVED_MS - 60_000)
    with pytest.raises(TransientCohortMarketDataError):
        poller.poll(OBSERVED)
    assert ledger.read_all() == []
    poller.poll(OBSERVED)
    row, = ledger.read_all()
    assert row["payload"]["status"] == "captured"
    assert row["payload"]["rows"] == len(recorder.config.symbols) * 5001


def test_command_binds_capture_before_constructing_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real launcher wiring remains offline under fake runner/signal boundaries."""
    module = _load_module()
    config = load_multi_asset_live_config("tests/fixtures/profiles/cohort_base.toml", mode="observe")
    timeline: list[str] = []
    observer = Mock(spec=CohortStartupCandleRecorder)
    poller = Mock()
    poller.bind_startup_input_observer.side_effect = lambda value: timeline.append("bind")
    telemetry = SimpleNamespace(startup_input_observer=lambda: observer, funding_recovery_start_ms=None)
    monkeypatch.setattr(module, "install_process_signal_stop", lambda *_args: SimpleNamespace(requested=False))
    monkeypatch.setattr(module, "_create_operator_inbox", lambda *args: None)
    monkeypatch.setattr(module, "MultiAssetLiveRunner", lambda **kwargs: timeline.append("construct"))
    module._create_runner(config, {}, poller, telemetry, Mock(), "offline-run")
    poller.bind_startup_input_observer.assert_called_once_with(observer)
    assert timeline == ["bind", "construct"]
