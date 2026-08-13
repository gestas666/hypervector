"""Authority-boundary tests for the BTC breakout-transfer observer."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)

_PROFILE = Path("configs/observers/btc_hype_breakout_transfer_v1.toml")


def test_transfer_profile_is_btc_only_and_execution_incapable() -> None:
    """The prospective collector must not inherit any order authority."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")

    assert config.symbols == ("BTC", "HYPE")
    assert config.executable_provider_symbols == frozenset()
    assert config.cohort_ledger == Path(
        "data/observe/btc_hype_breakout_transfer/decisions.jsonl"
    )
    assert config.stop_file == Path("data/observe/btc_hype_breakout_transfer/STOP")
    assert config.poll_seconds == 60.0
    assert len(config.providers) == 1
    provider = config.providers[0]
    assert provider.strategy_id == "hype_breakout_onset_bidirectional_v1"
    assert provider.symbols == ("BTC", "HYPE")
    assert provider.execution_symbols == ()


def test_transfer_profile_cannot_be_loaded_as_live() -> None:
    """Even explicit live flags cannot arm a profile with no execution map."""
    with pytest.raises(
        MultiAssetLiveConfigError,
        match="at least one explicit provider execution symbol",
    ):
        load_multi_asset_live_config(
            _PROFILE,
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        )


def test_default_collector_factory_accepts_a_minimal_provider_set() -> None:
    """Collector construction must follow configuration, not a fixed bundle."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )

    assert isinstance(poller, ConfiguredMultiAssetIntentPoller)
