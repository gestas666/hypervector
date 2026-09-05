"""Acceptance contract for the isolated v55 SPCX opportunity increment."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.hip3_cash_open_gap_provider import (
    HIP3_SPCX_CASH_OPEN_STRATEGY,
    Hip3CashOpenGapCollector,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.live.multi_asset_strategy_evidence import strategy_evidence_payloads

_V53 = Path("configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml")
_V55 = Path("configs/multi_asset_growth_first_5000_spcx_cash_open_v55.toml")


def _load(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def test_v55_preserves_v53_and_adds_only_exact_spcx_route() -> None:
    """BTC/HYPE contracts stay fixed while one SPCX route adds both sides."""
    v53 = _load(_V53)
    v55 = _load(_V55)

    assert v55.symbols == ("BTC", "HYPE", "xyz:SPCX")
    assert v55.providers[:3] == v53.providers
    assert [asset.symbol for asset in v55.assets[:2]] == ["BTC", "HYPE"]
    for old, new in zip(v53.assets, v55.assets[:2], strict=True):
        assert old.leverage == new.leverage
        assert old.margin_fraction == new.margin_fraction
        assert old.max_notional_usd == new.max_notional_usd
        assert old.stop_bps == new.stop_bps

    spcx = v55.assets[2]
    provider = v55.providers[3]
    assert (spcx.leverage, spcx.venue_max_leverage) == (10.0, 20.0)
    assert (spcx.margin_fraction, spcx.max_notional_usd) == (0.10, 5000.0)
    assert provider.strategy_id == HIP3_SPCX_CASH_OPEN_STRATEGY
    assert provider.symbols == provider.execution_symbols == ("xyz:SPCX",)
    assert provider.sides == frozenset({"long", "short"})
    assert provider.maximum_entry_delay_seconds == 30


def test_v55_spcx_execution_and_default_collector_are_exact() -> None:
    """The staged route must bind its target, stop, exits, and source adapter."""
    config = _load(_V55)
    provider = config.providers[-1]
    execution = provider.execution

    assert execution.entry_liquidity == "taker_ioc"
    assert execution.stop_policy == "fixed_bps"
    assert execution.stop_bps == 80.0
    assert execution.target_policy == "absolute_anchor"
    assert execution.maximum_hold_seconds == 22_500
    assert execution.provider_recipe_exit_policy == "honor"
    assert isinstance(
        build_default_collector(provider, config, Path("../backtest-lab/backtest_lab")),
        Hip3CashOpenGapCollector,
    )


def test_v55_spcx_tui_evidence_discloses_development_and_path_limits() -> None:
    """The cockpit must not label the new route unreviewed or proven."""
    config = _load(_V55)

    rows = strategy_evidence_payloads(config.providers)
    spcx = next(
        row for row in rows if row["strategy_id"] == HIP3_SPCX_CASH_OPEN_STRATEGY
    )

    assert spcx["research_state"] == "development_positive_technically_unresolved"
    assert spcx["confidence"] == "low"
    assert "20 trades" in spcx["cadence"]
    assert "Eleven entry lifecycles" in spcx["summary"]
