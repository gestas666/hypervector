"""Public candle connection ownership at the guarded command boundary."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import ModuleType, TracebackType

import pandas as pd
import pytest
import requests

from test_multi_asset_bidirectional_live_script import _args, _load_module

from hypervector.live.multi_asset_intent_poller import CohortBarFetcherProtocol
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
)
from hypervector.runtime_env import CredentialPresence

PROFILE = Path("tests/fixtures/profiles/mixed_crypto_hip3.toml")
REQUESTS = tuple(
    (symbol, "1m", 5 / 1440, cutoff)
    for cutoff in (1000, 2000)
    for symbol in ("BTC", "xyz:CCC")
)


class _Session:
    """Observe ownership without creating any network resource."""

    def __init__(self) -> None:
        """Start with an unused, open fake public session."""
        self.enters = 0
        self.closes = 0
        self.constructions = 0

    def __enter__(self) -> _Session:
        """Record entry into the owning command scope."""
        self.enters += 1
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Record closure on both success and failure without suppressing errors."""
        self.closes += 1


def _boundary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[ModuleType, _Session]:
    """Mock account/execution boundaries while preserving actual command validation."""
    module = _load_module()
    session = _Session()
    load_config = module.load_multi_asset_live_config

    def isolated_config(path: Path, **kwargs: object) -> MultiAssetLiveConfig:
        return replace(load_config(path, **kwargs), stop_file=tmp_path / "STOP",
                       cohort_ledger=tmp_path / "decisions.jsonl")

    monkeypatch.setattr(module, "load_multi_asset_live_config", isolated_config)


    def construct() -> _Session:
        """Observe session creation separately from entering its context."""
        session.constructions += 1
        return session

    monkeypatch.setattr(requests, "Session", construct)
    monkeypatch.setattr(
        module,
        "credential_presence_from_env",
        lambda: module.CredentialPresence(True, True),
    )
    monkeypatch.setattr(module, "_accounting_epoch", lambda *_args: None)
    monkeypatch.setattr(
        module, "bidirectional_live_runtime_lock", lambda _path: nullcontext()
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        """Protect this offline test from accidental execution-client construction."""
        raise AssertionError("The candle-session test must not construct execution")

    monkeypatch.setattr(module, "create_armed_multi_asset_adapters", forbidden)
    return module, session


def _retain_fetcher(
    *,
    config: MultiAssetLiveConfig,
    fetch_bars: CohortBarFetcherProtocol,
) -> CohortBarFetcherProtocol:
    """Retain the actual wired callable for the simulated runner."""
    return fetch_bars


def test_one_candle_session_survives_multiple_assets_and_cycles_then_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every public fetch uses one owned session and preserves its request values."""
    module, session = _boundary(monkeypatch, tmp_path)
    observed: list[tuple[str, str, float, int | None, object]] = []
    timeouts: list[object] = []

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
        session: object = None,
        timeout: object = None,
        **_stop_policy: object,
    ) -> pd.DataFrame:
        """Capture the request boundary without calling the network."""
        observed.append((symbol, timeframe, lookback_days, end_ms, session))
        timeouts.append(timeout)
        return pd.DataFrame()

    monkeypatch.setattr(module, "fetch_hl_ohlcv_snapshot", fetch)

    def run(
        args: argparse.Namespace,
        config: MultiAssetLiveConfig,
        presence: CredentialPresence,
        fetch_bars: CohortBarFetcherProtocol,
        lock_path: Path | None = None,
        signal_stop: object = None,
    ) -> int:
        """Exercise two assets at two cutoffs while the command owns its session."""
        assert session.closes == 0
        for symbol, timeframe, lookback, cutoff in REQUESTS:
            fetch_bars(symbol, timeframe, lookback, end_ms=cutoff)
        return 17

    monkeypatch.setattr(
        module.ConfiguredMultiAssetIntentPoller,
        "with_registered_collectors",
        _retain_fetcher,
    )
    monkeypatch.setattr(module, "_run_locked", run)
    result = module.run_live(
        _args(config=PROFILE, enabled=True, i_accept_live_risk=True)
    )
    assert result == 17
    assert observed == [(*request, session) for request in REQUESTS]
    assert timeouts == [(5.0, 10.0)] * len(REQUESTS)
    assert session.constructions == session.enters == session.closes == 1


@pytest.mark.parametrize("stage", ["collector", "runtime"])
def test_candle_session_closes_when_startup_or_runtime_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    """The owning context closes the session and preserves the original error."""
    module, session = _boundary(monkeypatch, tmp_path)

    def fail(*args: object, **kwargs: object) -> None:
        """Represent a collector or runtime failure without any remote operation."""
        raise requests.Timeout("bounded test failure")

    builder = fail if stage == "collector" else lambda **kwargs: object()
    monkeypatch.setattr(
        module.ConfiguredMultiAssetIntentPoller, "with_registered_collectors", builder
    )
    monkeypatch.setattr(module, "_run_locked", fail)
    with pytest.raises(requests.Timeout, match="bounded test failure"):
        module.run_live(_args(config=PROFILE, enabled=True, i_accept_live_risk=True))
    assert session.constructions == session.enters == session.closes == 1


def test_disarmed_command_does_not_construct_a_candle_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resource creation remains after the existing explicit live authority checks."""
    module, session = _boundary(monkeypatch, tmp_path)
    with pytest.raises(MultiAssetLiveConfigError, match="--enabled"):
        module.run_live(_args(config=PROFILE, i_accept_live_risk=True))
    assert session.constructions == session.enters == session.closes == 0


def test_stop_marker_refuses_before_public_session_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A user stop marker cannot cause even the public transport to start."""
    module, session = _boundary(monkeypatch, tmp_path)
    config = module.load_multi_asset_live_config(
        PROFILE, mode="live", enabled=True, accepts_live_risk=True
    )
    marker = tmp_path / "STOP"
    marker.write_text("stop\n")
    config = replace(config, stop_file=marker)
    monkeypatch.setattr(
        module, "load_multi_asset_live_config", lambda *args, **kwargs: config
    )
    with pytest.raises(MultiAssetLiveConfigError, match="operator stop"):
        module.run_live(_args(config=PROFILE, enabled=True, i_accept_live_risk=True))
    assert session.constructions == session.enters == session.closes == 0
