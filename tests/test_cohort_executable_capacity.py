"""Exact configured sizing and non-gating portfolio scenario regressions."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_executable_capacity import (
    CapacityScenario,
    build_executable_capacity,
)

_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86.toml"
)
_EQUITY = 4857.58724349
_FEES = {
    "BTC": 4.32,
    "ETH": 4.32,
    "SOL": 4.32,
    "HYPE": 4.32,
    "xyz:SPCX": 0.864,
    "xyz:SNDK": 0.864,
}


def test_current_capacity_uses_caps_and_excludes_observe_only_routes() -> None:
    """Seven visible assets produce six executable slots and capped margins."""
    report = build_executable_capacity(_config(), _EQUITY, _FEES)

    assert len(report["routes"]) == 6
    assert report["uncovered_assets"] == ["ZEC"]
    assert report["capacity"]["occupied_symbols"] == 6
    assert report["capacity"]["notional_usd"] == pytest.approx(7250)
    assert report["capacity"]["initial_margin_usd"] == pytest.approx(1700 / 3)
    assert report["capacity"]["long_notional_usd"] == pytest.approx(6000)
    assert report["capacity"]["short_notional_usd"] == pytest.approx(1250)
    assert report["contract"]["performance_gate"] is False
    assert report["contract"]["execution_authority"] == "none"


def test_scenarios_use_provider_stops_fees_and_explicit_friction() -> None:
    """BTC's provider stop is 60 bps even though its asset default is 80."""
    report = build_executable_capacity(
        _config(),
        _EQUITY,
        _FEES,
        scenarios=(
            CapacityScenario("fees_only", 0, 0),
            CapacityScenario("slippage_and_funding", 120, 20),
        ),
    )

    assert report["scenarios"][0]["loss_usd"] == pytest.approx(55.4)
    assert report["scenarios"][1]["loss_usd"] == pytest.approx(156.9)
    assert report["scenarios"][1]["loss_pct_equity"] == pytest.approx(
        156.9 / _EQUITY * 100
    )


def test_multiple_routes_and_sides_do_not_multiply_one_symbol_capacity() -> None:
    """Mutually exclusive BTC routes contribute only one position to a bound."""
    config = _config()
    sweep = next(row for row in config.providers if "sweep" in row.strategy_id)
    duplicate = replace(sweep, strategy_id="alternate", sides=frozenset({"short"}))
    config = replace(
        config, providers=(*config.providers, duplicate), maximum_positions=2
    )

    report = build_executable_capacity(config, _EQUITY, _FEES)

    assert report["capacity"]["occupied_symbols"] == 2
    assert report["capacity"]["notional_usd"] == pytest.approx(5000)
    assert report["capacity"]["initial_margin_usd"] == pytest.approx(375)
    assert report["scenarios"][0]["loss_usd"] == pytest.approx(39.32)


def test_directional_sizing_takes_precedence_and_low_equity_scales() -> None:
    """The report reuses the production precedence and fractional sizing."""
    config = _config()
    providers = tuple(
        replace(
            row,
            directional_sizing_overrides=(
                ("BTC", "long", CohortEntrySizing(0.01, 1000)),
            ),
        )
        if "sweep" in row.strategy_id
        else row
        for row in config.providers
    )
    report = build_executable_capacity(replace(config, providers=providers), 100, _FEES)

    btc = next(row for row in report["routes"] if row["symbol"] == "BTC")
    assert btc["notional_usd"] == pytest.approx(20)
    assert btc["initial_margin_usd"] == pytest.approx(1)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True])
def test_rejects_invalid_fees(value: float) -> None:
    """Missing or malformed costs cannot become zero-cost evidence."""
    with pytest.raises(ValueError, match="fee"):
        build_executable_capacity(_config(), _EQUITY, {**_FEES, "BTC": value})


def test_rejects_missing_fee() -> None:
    """Unknown fees must be identified rather than silently substituted."""
    with pytest.raises(ValueError, match="missing.*BTC"):
        build_executable_capacity(_config(), _EQUITY, {})


def test_structural_stop_uses_explicit_upper_sensitivity_and_asset_sizing() -> None:
    """A report-only ZEC scenario cannot claim to know an unbound ATR stop."""
    config = _config()
    providers = tuple(
        replace(row, execution_symbols=("ZEC",), sides=frozenset({"long"}))
        if "zec_" in row.strategy_id
        else row
        for row in config.providers
    )
    report = build_executable_capacity(
        replace(config, providers=providers), _EQUITY, {**_FEES, "ZEC": 4.32}
    )
    zec = next(row for row in report["routes"] if row["symbol"] == "ZEC")
    assert zec["stop_bps"] == 250
    assert zec["stop_basis"] == "structural_stop_upper_sensitivity"
    assert zec["notional_usd"] == pytest.approx(_EQUITY * 0.02 * 5)


@pytest.mark.parametrize("equity", [0, -1, float("inf"), True])
def test_rejects_invalid_equity(equity: float) -> None:
    """An invalid account-value input cannot produce an exposure report."""
    with pytest.raises(ValueError, match="equity"):
        build_executable_capacity(_config(), equity, _FEES)


def test_rejects_empty_duplicate_or_unnamed_scenarios() -> None:
    """Each report needs unambiguous labeled sensitivities."""
    with pytest.raises(ValueError, match="name"):
        CapacityScenario(" ", 0, 0)
    for scenarios in ((), (CapacityScenario("same", 0, 0),) * 2):
        with pytest.raises(ValueError, match="scenarios"):
            build_executable_capacity(_config(), _EQUITY, _FEES, scenarios=scenarios)


def test_empty_execution_scope_has_no_synthetic_exposure() -> None:
    """A wholly observational configuration has zero executable capacity."""
    config = replace(_config(), providers=())
    report = build_executable_capacity(config, _EQUITY, {})
    assert report["capacity"]["notional_usd"] == 0
    assert report["scenarios"][0]["loss_usd"] == 0
    assert len(report["uncovered_assets"]) == 7


@pytest.mark.parametrize("slippage,funding", [(-1, 0), (0, -1), (float("nan"), 0)])
def test_scenario_rejects_invalid_assumptions(slippage: float, funding: float) -> None:
    """Declared adverse scenario inputs must be finite and nonnegative."""
    with pytest.raises(ValueError):
        CapacityScenario("invalid", slippage, funding)


def _config() -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(_CONFIG, mode="observe")
