"""Protected V90 routes retain entry parity and explicit restart-safe exits."""

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.hourly_price_provider import (
    DONCHIAN20_STRATEGY,
    PROTECTED_DONCHIAN20_SYMBOLS,
    HourlyPriceCollector,
    build_hourly_price_signals,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    load_multi_asset_live_config,
    validate_multi_asset_live_config,
)
from hypervector.live.multi_asset_polling_contract import SOURCE_TIMEFRAMES
from hypervector.live.multi_asset_strategy_evidence import strategy_research_evidence
from test_hourly_price_provider import _bars
from test_cohort_profit_lock_controller import _Engine, _Telemetry
from hypervector.live.cohort_profit_lock_controller import CohortProfitLockController
from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState

PROFILE = Path(
    "configs/multi_asset_growth_first_5000_bankroll_builder_candidate_v90.toml"
)
PROTECTED = "hourly_donchian_20_10_atr20_profit_lock_bidirectional_v2"
BASELINE = Path("configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml")
HOURLY_ROUTES = {"SOL", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA"}


def _hourly(config):
    return next(p for p in config.providers if "donchian" in p.strategy_id)


def _protected_config():
    """Derive the protected variant from the committed option-B profile.

    The V90 candidate deliberately runs the UNLOCKED identity (option B of
    docs/reviews/2026-09-21-v90-profit-lock-exit-review.md). The protected
    identity stays in source as a frozen alternative, so its contract is
    exercised here on a derived configuration rather than on the live profile.
    """
    config = load_multi_asset_live_config(PROFILE, mode="observe")
    hourly = _hourly(config)
    evidenced = tuple(s for s in hourly.symbols if s in PROTECTED_DONCHIAN20_SYMBOLS)
    protected = replace(
        hourly,
        strategy_id=PROTECTED,
        symbols=evidenced,
        execution_symbols=evidenced,
        execution=replace(
            hourly.execution,
            profit_lock_policy="completed_bar_trailing",
            profit_lock_activation_bps=100.0,
            profit_lock_floor_bps=25.0,
            profit_lock_giveback_bps=50.0,
        ),
    )
    dropped = set(hourly.symbols) - set(evidenced)
    config = replace(
        config,
        assets=tuple(a for a in config.assets if a.symbol not in dropped),
        providers=tuple(protected if p == hourly else p for p in config.providers),
    )
    validate_multi_asset_live_config(config)
    return config


def test_candidate_runs_every_hourly_route_unlocked_on_the_v1_identity() -> None:
    """Option B: no profit lock on any route; TSLA joins the screened contract."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")
    hourly = _hourly(config)
    assert hourly.strategy_id == DONCHIAN20_STRATEGY
    assert set(hourly.symbols) == set(hourly.execution_symbols) == HOURLY_ROUTES
    contract = hourly.execution
    assert contract.profit_lock_policy == "none"
    assert contract.profit_lock_activation_bps is None
    assert contract.provider_recipe_exit_policy == "honor"
    assert contract.maximum_hold_seconds == 86400
    assert contract.maximum_hold_policy == "fixed"
    assert (contract.minimum_stop_bps, contract.maximum_stop_bps) == (20.0, 250.0)
    assert isinstance(
        build_default_collector(hourly, config, Path("unused")), HourlyPriceCollector
    )
    assert SOURCE_TIMEFRAMES[DONCHIAN20_STRATEGY] == "15m"
    btc = next(p for p in config.providers if p.execution_symbols == ("BTC",))
    assert btc.execution.target_bps == btc.execution.stop_bps == 60
    assert {symbol for _, symbol in config.executable_provider_symbols} == {
        "BTC",
        *HOURLY_ROUTES,
    }
    for symbol in HOURLY_ROUTES:
        plan = hourly.execution_for(symbol, "long")
        assert plan.profit_lock_policy == "none"
    tsla = next(a for a in config.assets if a.symbol == "xyz:TSLA")
    assert (tsla.leverage, tsla.venue_max_leverage, tsla.max_notional_usd) == (
        8.0,
        20.0,
        700.0,
    )
    assert config.maximum_positions == 8


def test_unlocked_identity_refuses_profit_lock_keys() -> None:
    """The lock cannot be smuggled onto the v1 identity by a configuration edit."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")
    hourly = _hourly(config)
    locked = replace(
        hourly.execution,
        profit_lock_policy="completed_bar_trailing",
        profit_lock_activation_bps=100.0,
        profit_lock_floor_bps=25.0,
        profit_lock_giveback_bps=50.0,
    )
    with pytest.raises(ValueError, match="hourly price"):
        validate_multi_asset_live_config(
            replace(
                config,
                providers=tuple(
                    replace(p, execution=locked) if p == hourly else p
                    for p in config.providers
                ),
            )
        )


def test_protected_variant_is_derivable_and_binds_the_frozen_lock() -> None:
    """The protected identity remains a valid, frozen alternative in source."""
    config = _protected_config()
    hourly = _hourly(config)
    assert hourly.strategy_id == PROTECTED
    assert (
        hourly.execution.profit_lock_activation_bps,
        hourly.execution.profit_lock_floor_bps,
        hourly.execution.profit_lock_giveback_bps,
    ) == (100.0, 25.0, 50.0)
    assert SOURCE_TIMEFRAMES[PROTECTED] == "15m"


@pytest.mark.parametrize(
    "field,value",
    [
        ("profit_lock_activation_bps", 99.0),
        ("profit_lock_floor_bps", 24.0),
        ("profit_lock_giveback_bps", 51.0),
        ("maximum_stop_bps", 251.0),
        ("provider_recipe_exit_policy", "ignore"),
    ],
)
def test_protected_identity_rejects_parameter_drift(field: str, value: object) -> None:
    """A labelled protected strategy cannot silently use different exit mechanics."""
    config = _protected_config()
    hourly = _hourly(config)
    invalid = replace(hourly, execution=replace(hourly.execution, **{field: value}))
    with pytest.raises(ValueError, match="hourly price"):
        validate_multi_asset_live_config(
            replace(
                config,
                providers=tuple(
                    invalid if p == hourly else p for p in config.providers
                ),
            )
        )


def test_original_provider_cannot_silently_inherit_protected_exit() -> None:
    """V89 remains unchanged and its legacy identity still requires no lock."""
    config = _protected_config()
    hourly = _hourly(config)
    with pytest.raises(ValueError, match="hourly price"):
        validate_multi_asset_live_config(
            replace(
                config,
                providers=tuple(
                    replace(p, strategy_id=DONCHIAN20_STRATEGY) if p == hourly else p
                    for p in config.providers
                ),
            )
        )


def test_protected_provider_cannot_disable_the_lock() -> None:
    """A protected identity fails closed if its bound exit protection is removed."""
    config = _protected_config()
    hourly = _hourly(config)
    disabled = replace(
        hourly.execution,
        profit_lock_policy="none",
        profit_lock_activation_bps=None,
        profit_lock_floor_bps=None,
        profit_lock_giveback_bps=None,
    )
    with pytest.raises(ValueError, match="hourly price"):
        validate_multi_asset_live_config(
            replace(
                config,
                providers=tuple(
                    replace(p, execution=disabled) if p == hourly else p
                    for p in config.providers
                ),
            )
        )


def test_protected_identity_refuses_a_symbol_without_protected_evidence() -> None:
    """The lock contract pins its researched symbol set, not only its parameters."""
    config = _protected_config()
    hourly = _hourly(config)
    tsla = next(
        a
        for a in load_multi_asset_live_config(PROFILE, mode="observe").assets
        if a.symbol == "xyz:TSLA"
    )
    widened = replace(
        hourly,
        symbols=(*hourly.symbols, "xyz:TSLA"),
        execution_symbols=(*hourly.execution_symbols, "xyz:TSLA"),
    )
    # The asset is present and enabled, so the only remaining objection is the
    # identity-bound contract's symbol pin.
    with pytest.raises(ValueError, match="hourly price"):
        validate_multi_asset_live_config(
            replace(
                config,
                assets=(*config.assets, tsla),
                providers=tuple(
                    widened if p == hourly else p for p in config.providers
                ),
            )
        )
    for symbol in hourly.symbols:
        assert strategy_research_evidence(PROTECTED, symbol).research_state == (
            "profit_protection_candidate_unconfirmed"
        )


def test_v89_profile_fingerprint_is_unchanged() -> None:
    """Adding a provider must not alter the running baseline's immutable settings."""
    baseline = load_multi_asset_live_config(BASELINE, mode="observe")
    assert (
        baseline.profile_fingerprint
        == "39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a"
    )


def test_protected_signals_are_identical_but_have_distinct_evidence() -> None:
    """A changed exit does not silently change entry or hourly recipe signals."""
    bars = _bars().set_index("timestamp")
    pd.testing.assert_frame_equal(
        build_hourly_price_signals(bars, PROTECTED),
        build_hourly_price_signals(bars, DONCHIAN20_STRATEGY),
    )
    evidence = strategy_research_evidence(PROTECTED, "xyz:SNDK")
    assert evidence.research_state == "profit_protection_candidate_unconfirmed"
    assert evidence.confidence == "low"


@pytest.mark.parametrize("side", ["long", "short"])
def test_protected_exit_journals_before_close_and_replays_after_restart(
    side: str,
) -> None:
    """A committed crossing survives lost bars and uses the current exit mark."""
    config = _protected_config()
    contract = next(
        p.execution for p in config.providers if "donchian" in p.strategy_id
    )
    assert contract.profit_lock_policy == "completed_bar_trailing"
    plan = contract.bind(
        strategy_id=PROTECTED, stop_anchor=98 if side == "long" else 102
    )
    plan = BoundExecutionPlan.from_payload(plan.as_payload())
    snapshot = SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=7,
        stop_oid=8,
        position_size_signed=1 if side == "long" else -1,
        opened_at_ms=10_000,
        execution_plan=plan,
    )
    sink = _Telemetry()
    for observed_ms, bars, mark in (
        (
            180_000,
            (
                CohortMarketBar("SOL", 60_000, 100, 102, 98, 100, 1),
                CohortMarketBar("SOL", 120_000, 100, 101, 99, 100, 1),
            ),
            100.1,
        ),
        (195_000, (), 99.9),
    ):
        controller = CohortProfitLockController(
            symbols=("SOL",), engines={"SOL": _Engine(snapshot)}, telemetry=sink
        )
        closing, actions = controller.actions(
            observed_ms=observed_ms,
            reference_prices={"SOL": mark},
            entry_prices={"SOL": 100},
            market_bars={"SOL": bars},
            excluded_symbols=set(),
        )
        assert closing == {"SOL"}
        assert actions[0].reference_price == mark
        assert actions[0].decision_time_ms == 180_000
        assert actions[0].exit_reason == "completed_bar_profit_lock"
    assert len(sink.decisions) == 1
