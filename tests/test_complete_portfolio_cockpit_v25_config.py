"""Complete nine-asset portfolio and setup contract for cohort v25."""

import pytest

from pathlib import Path
import tomllib

import pandas as pd

from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.perp_venue_identity import configured_perp_dexes

PROFILE = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
STAGED_PROFILE = Path(
    "configs/multi_asset_bidirectional_complete_portfolio_canary_v26.toml"
)
CORE_ASSETS = ("BTC", "ETH", "SOL", "HYPE")
HIP3_ASSETS = (
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:GOLD",
    "xyz:BRENTOIL",
)

HULK = "hulk_expansion_bidirectional_tuned_v2"
RANGE = "range_onset_bidirectional_v1"
SOURCE = "hypervelocity_source_follow_bidirectional_5m_v1"
BREAKOUT = "hype_breakout_onset_bidirectional_v1"
ETH_PULLBACK = "eth_breakout_precompression_pullback_bidirectional_v1"
HIP3_SWING_INDEX = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
HIP3_BREAKOUT_INDEX = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"
HIP3_SWING_COMMODITY = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
HIP3_BREAKOUT_COMMODITY = "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1"


def test_v25_declares_every_asset_and_setup_as_explicit_live_canary_authority() -> None:
    """The complete cockpit must not silently omit assets or provider routes."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")

    expected_core = {
        *((HULK, symbol) for symbol in CORE_ASSETS),
        *((RANGE, symbol) for symbol in CORE_ASSETS),
        (SOURCE, "BTC"),
        *((BREAKOUT, symbol) for symbol in CORE_ASSETS),
        (ETH_PULLBACK, "ETH"),
    }
    expected_hip3 = {
        *((HIP3_SWING_INDEX, symbol) for symbol in HIP3_ASSETS[:2]),
        *((HIP3_BREAKOUT_INDEX, symbol) for symbol in HIP3_ASSETS[:2]),
        *((HIP3_SWING_COMMODITY, symbol) for symbol in HIP3_ASSETS[2:]),
        *((HIP3_BREAKOUT_COMMODITY, symbol) for symbol in HIP3_ASSETS[2:]),
    }
    expected = expected_core | expected_hip3

    assert config.profile_id == (
        "multi_asset_bidirectional_complete_portfolio_canary_v25"
    )
    assert config.symbols == CORE_ASSETS + HIP3_ASSETS
    assert config.maximum_positions == len(config.symbols)
    assert config.executable_provider_symbols == expected
    assert len(expected_core) == 14
    assert len(expected_hip3) == 10
    assert len(expected) == 24
    assert all(provider.sides == {"long", "short"} for provider in config.providers)
    assert config.executable_provider_directions == {
        (strategy, symbol, side)
        for strategy, symbol in expected
        for side in ("long", "short")
    }


def test_v25_uses_one_position_slot_per_asset_and_exact_venue_limits() -> None:
    """Position capacity and venue leverage ceilings must cover the full roster."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")

    venue_limits = {asset.symbol: asset.venue_max_leverage for asset in config.assets}
    assert venue_limits == {
        "BTC": 40.0,
        "ETH": 25.0,
        "SOL": 20.0,
        "HYPE": 10.0,
        "xyz:SP500": 50.0,
        "xyz:SPCX": 20.0,
        "xyz:SNDK": 10.0,
        "xyz:GOLD": 25.0,
        "xyz:BRENTOIL": 20.0,
    }
    assert all(asset.max_positions_per_symbol == 1 for asset in config.assets)
    assert all(asset.leverage == 5.0 for asset in config.assets)
    assert configured_perp_dexes(config.symbols) == ("", "xyz")


@pytest.mark.integration
def test_v25_constructs_all_default_collectors_and_fifteen_minute_sources() -> None:
    """Every declared setup must have a concrete runtime implementation."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda *_args, **_kwargs: pd.DataFrame(),
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )

    assert poller is not None


@pytest.mark.integration
def test_v25_initial_poll_publishes_all_twenty_four_setup_rows() -> None:
    """Startup must populate every setup with evidence or explicit blockers."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")
    timestamps = pd.date_range("2026-08-04T00:00:00Z", periods=3_200, freq="1min")

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        offset = float(config.symbols.index(symbol) * 100)
        closes = pd.Series(range(len(timestamps)), dtype=float) / 100.0 + 100.0 + offset
        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": closes,
                "high": closes + 0.2,
                "low": closes - 0.2,
                "close": closes,
                "volume": [10.0] * len(timestamps),
            }
        )

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=fetch,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )
    observed = timestamps[-1] + pd.Timedelta(minutes=1)
    poller.activate(int(observed.timestamp() * 1_000))

    result = poller.poll(observed.to_pydatetime())

    pairs = {(row.strategy_id, row.symbol) for row in result.evaluations}
    expected = {
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    }
    assert pairs == expected
    assert len(result.evaluations) == 24
    assert set(result.reference_prices) == set(config.symbols)
    assert set(result.market_bars) == set(config.symbols)


def test_v26_stages_new_generation_identity_without_parameter_drift() -> None:
    """The causal L2 repair must not smuggle in a strategy or risk change."""
    current = load_multi_asset_live_config(PROFILE, mode="observe")
    staged = load_multi_asset_live_config(STAGED_PROFILE, mode="observe")

    assert staged.profile_id == (
        "multi_asset_bidirectional_complete_portfolio_canary_v26"
    )
    assert staged.profile_fingerprint != current.profile_fingerprint
    current_raw = tomllib.loads(PROFILE.read_text(encoding="utf-8"))
    staged_raw = tomllib.loads(STAGED_PROFILE.read_text(encoding="utf-8"))
    current_raw.pop("profile")
    staged_raw.pop("profile")
    assert staged_raw == current_raw
