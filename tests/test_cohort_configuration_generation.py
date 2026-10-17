"""Runtime-configuration generation and restart-readiness evidence."""

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.research.cohort_configuration_generation import (
    ConfigurationGenerationExpectation,
    configuration_generation_evidence,
    load_configuration_expectation,
)
from hypervector.research.cohort_configuration_exit_policy import (
    ProviderExitExpectation,
)

_FIXTURE_PROFILES = Path("tests/fixtures/profiles")
_V95 = Path("configs/multi_asset_growth_first_5000_review_fixes_v95.toml")

_EXPECTATION = ConfigurationGenerationExpectation(
    source_path="configs/cohort.toml",
    source_modified_at_utc="2026-08-03T11:16:04+00:00",
    profile_fingerprint="current-profile",
    entry_context_overrides=(
        (
            "range_onset_bidirectional_v1",
            "ETH",
            "dual_mtf_not_opposed",
        ),
    ),
)


def test_current_profile_exposes_the_explicit_eth_entry_context_rule() -> None:
    """The disk identity carries the exact pending rule without runtime authority."""
    expectation = load_configuration_expectation(
        Path("tests/fixtures/profiles/multi_asset_bidirectional_canary.toml")
    )

    assert expectation.entry_context_overrides == (
        (
            "range_onset_bidirectional_v1",
            "ETH",
            "dual_mtf_not_opposed",
        ),
    )


def test_load_expectation_retains_provider_symbol_sizing() -> None:
    """Disk identity retains an explicit provider override without activating it."""
    expectation = load_configuration_expectation(
        Path("tests/fixtures/profiles/multi_asset_bidirectional_canary.toml")
    )

    assert expectation.provider_sizing_overrides == (
        ("hulk_expansion_bidirectional_tuned_v2", "SOL", 0.03, 25.0),
        ("range_onset_bidirectional_v1", "SOL", 0.10, 75.0),
    )


def test_v36_expectation_retains_exact_provider_membership_and_routes() -> None:
    """The pending generation exposes its complete execution roster."""
    expectation = load_configuration_expectation(
        _FIXTURE_PROFILES / "multi_asset_bidirectional_evidence_roster_canary_v36.toml"
    )

    scopes = dict(expectation.provider_execution_scopes)
    assert len(scopes) == 7
    assert sum(len(symbols) for symbols in scopes.values()) == 16
    assert scopes["range_onset_bidirectional_v1"] == ("SOL",)
    assert "hip3_swing_ha_sp500_spcx_bidirectional_v2" not in scopes
    assert "hip3_swing_ha_sndk_gold_brent_bidirectional_v1" not in scopes
    active = load_configuration_expectation(
        _FIXTURE_PROFILES / "multi_asset_bidirectional_all_live_canary_v35.toml"
    )
    active_routes = {
        (provider, symbol)
        for provider, symbols in active.provider_execution_scopes
        for symbol in symbols
    }
    staged_routes = {
        (provider, symbol)
        for provider, symbols in expectation.provider_execution_scopes
        for symbol in symbols
    }
    assert active_routes - staged_routes == {
        ("range_onset_bidirectional_v1", "BTC"),
        ("range_onset_bidirectional_v1", "ETH"),
        ("range_onset_bidirectional_v1", "HYPE"),
        ("hip3_swing_ha_sp500_spcx_bidirectional_v2", "xyz:SP500"),
        ("hip3_swing_ha_sp500_spcx_bidirectional_v2", "xyz:SPCX"),
        ("hip3_swing_ha_sndk_gold_brent_bidirectional_v1", "xyz:SNDK"),
        ("hip3_swing_ha_sndk_gold_brent_bidirectional_v1", "xyz:GOLD"),
        ("hip3_swing_ha_sndk_gold_brent_bidirectional_v1", "xyz:BRENTOIL"),
    }
    assert staged_routes - active_routes == set()


def test_v43_expectation_retains_exact_side_specialist_directions() -> None:
    """Staged evidence reports aggregate BTC coverage without name inference."""
    expectation = load_configuration_expectation(
        _FIXTURE_PROFILES / "multi_asset_bidirectional_btc_specialists_candidate_v43.toml"
    )

    directions = {
        (strategy, symbol): sides
        for strategy, symbol, sides in expectation.provider_execution_directions
    }
    assert directions[("hulk_expansion_short_robust_v3", "BTC")] == ("short",)
    assert directions[("liquidity_sweep_long_1h_stop60_v1", "BTC")] == ("long",)
    assert directions[
        ("hype_breakout_compression_pullback_bidirectional_v1", "HYPE")
    ] == ("long", "short")
    assert directions[
        ("hip3_breakout_pressure_sp500_spcx_bidirectional_v1", "xyz:SP500")
    ] == ("long", "short")
    evidence = configuration_generation_evidence(
        "runtime-profile",
        expectation,
        {
            "BTC": {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            }
        },
    )
    assert evidence["current_provider_execution_directions"][
        "hulk_expansion_short_robust_v3|BTC"
    ] == ["short"]
    assert evidence["current_provider_execution_directions"][
        "liquidity_sweep_long_1h_stop60_v1|BTC"
    ] == ["long"]


def test_v44_expectation_exposes_corrected_long_identity_and_six_sides() -> None:
    """The staged cockpit sees the corrected route rather than its v43 alias."""
    expectation = load_configuration_expectation(
        _FIXTURE_PROFILES
        / "multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml"
    )
    directions = {
        (strategy, symbol): sides
        for strategy, symbol, sides in expectation.provider_execution_directions
    }

    assert len(expectation.provider_execution_scopes) == 4
    assert sum(len(sides) for sides in directions.values()) == 6
    assert directions[("liquidity_sweep_long_1h_stop60_target60_v2", "BTC")] == (
        "long",
    )
    assert ("liquidity_sweep_long_1h_stop60_v1", "BTC") not in directions


def test_v95_expectation_exposes_exact_live_routes_without_authority() -> None:
    """The retained live profile publishes its six route-sides as report-only."""
    expectation = load_configuration_expectation(_V95)

    assert dict(expectation.provider_execution_scopes) == {
        "eth_range_onset_long_dual_mtf_v2": ("ETH",),
        "hourly_donchian_20_10_atr20_strong_short_v1": (
            "SOL",
            "xyz:BRENTOIL",
            "xyz:SNDK",
            "xyz:TSLA",
        ),
        "liquidity_sweep_long_1h_stop60_target60_v2": ("BTC",),
    }
    directions = {
        (strategy, symbol): sides
        for strategy, symbol, sides in expectation.provider_execution_directions
    }
    assert directions[("liquidity_sweep_long_1h_stop60_target60_v2", "BTC")] == (
        "long",
    )
    assert directions[("eth_range_onset_long_dual_mtf_v2", "ETH")] == ("long",)
    assert {
        symbol
        for (strategy, symbol), sides in directions.items()
        if strategy == "hourly_donchian_20_10_atr20_strong_short_v1"
        and sides == ("long", "short")
    } == {"SOL", "xyz:BRENTOIL", "xyz:SNDK", "xyz:TSLA"}
    assert len(directions) == 6
    assert all(symbol not in {"HYPE", "xyz:SPCX"} for _, symbol in directions)

    evidence = configuration_generation_evidence(
        "runtime-profile",
        expectation,
        {
            "BTC": {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            },
            "xyz:SNDK": {
                "final_state": "OPEN",
                "position_size_signed": -1.5,
                "open_order_ids": [1],
            },
        },
    )
    assert evidence["current_profile_fingerprint"] == expectation.profile_fingerprint
    assert evidence["restart_state"] == "wait_for_flat_and_no_orders"
    assert evidence["blocking_assets"] == ["xyz:SNDK"]
    assert evidence["execution_authority"] == "none"
    assert evidence["automatic_restart"] is False


def test_load_expectation_retains_provider_directional_sizing(
    tmp_path: Path,
) -> None:
    """Disk identity keeps distinct long and short policies for one route."""
    source = Path("tests/fixtures/profiles/multi_asset_bidirectional_canary.toml").read_text()
    directional = (
        "directional_sizing_overrides = { SOL = { "
        "long = { margin_fraction = 0.03, max_notional_usd = 60.0 }, "
        "short = { margin_fraction = 0.03, max_notional_usd = 15.0 } } }\n"
    )
    profile = tmp_path / "directional-sizing.toml"
    profile.write_text(
        source.replace(
            'symbols = ["BTC", "ETH", "SOL", "HYPE"]\n',
            directional + 'symbols = ["BTC", "ETH", "SOL", "HYPE"]\n',
            1,
        )
    )

    expectation = load_configuration_expectation(profile)

    assert expectation.provider_directional_sizing_overrides == (
        ("hulk_expansion_bidirectional_tuned_v2", "SOL", "long", 0.03, 60.0),
        ("hulk_expansion_bidirectional_tuned_v2", "SOL", "short", 0.03, 15.0),
    )


def test_load_expectation_retains_exact_pending_asset_sizing() -> None:
    """The selected profile exposes every asset cap without activating it."""
    expectation = load_configuration_expectation(
        _FIXTURE_PROFILES / "multi_asset_bidirectional_range_retired_hype75_candidate.toml"
    )

    assert expectation.asset_sizing == (
        ("BTC", 5.0, 0.03, 25.0),
        ("ETH", 5.0, 0.03, 25.0),
        ("HYPE", 5.0, 0.03, 75.0),
        ("SOL", 5.0, 0.03, 75.0),
    )


def test_generation_exposes_preserved_provider_exit_policy_without_authority() -> None:
    """The operator can verify the HYPE extension remains unchanged."""
    expectation = load_configuration_expectation(
        _FIXTURE_PROFILES / "multi_asset_bidirectional_range_retired_hype75_candidate.toml"
    )
    evidence = configuration_generation_evidence(
        "runtime-profile",
        expectation,
        {
            "HYPE": {
                "final_state": "OPEN",
                "position_size_signed": 0.45,
                "open_order_ids": [510231986579],
            }
        },
    )

    hype = evidence["current_provider_exit_policies"][
        "hype_breakout_onset_bidirectional_v1"
    ]
    assert hype == {
        "maximum_hold_seconds": 28_800,
        "maximum_hold_policy": "extend_while_regime_supported",
        "hard_maximum_hold_seconds": 86_400,
        "maximum_hold_evidence_maximum_age_seconds": None,
        "provider_recipe_exit_policy": "ignore",
        "profit_lock_policy": "none",
        "profit_lock_activation_bps": None,
        "profit_lock_floor_bps": None,
        "profit_lock_giveback_bps": None,
    }
    assert evidence["execution_authority"] == "none"
    assert evidence["automatic_restart"] is False


def test_generation_publishes_pending_asset_sizing_without_authority() -> None:
    """Asset sizing is auditable configuration evidence, not a hot mutation."""
    expectation = replace(
        _EXPECTATION,
        asset_sizing=(("HYPE", 5.0, 0.03, 75.0),),
    )

    evidence = configuration_generation_evidence(
        "runtime-profile",
        expectation,
        {
            "HYPE": {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            }
        },
    )

    assert evidence["current_asset_sizing"] == {
        "HYPE": {
            "leverage": 5.0,
            "margin_fraction": 0.03,
            "max_notional_usd": 75.0,
        }
    }
    assert evidence["execution_authority"] == "none"
    assert evidence["automatic_restart"] is False


def test_generation_publishes_provider_routes_without_authority() -> None:
    """A staged route roster is report-only and machine-comparable."""
    expectation = replace(
        _EXPECTATION,
        provider_execution_scopes=(
            ("range_onset_bidirectional_v1", ("SOL",)),
            ("hip3_breakout_pressure_v1", ("xyz:GOLD", "xyz:SNDK")),
        ),
    )

    evidence = configuration_generation_evidence(
        "runtime-profile",
        expectation,
        {
            "xyz:GOLD": {
                "final_state": "OPEN",
                "position_size_signed": 0.0171,
                "open_order_ids": [123],
            }
        },
    )

    assert evidence["current_provider_execution_scopes"] == {
        "hip3_breakout_pressure_v1": ["xyz:GOLD", "xyz:SNDK"],
        "range_onset_bidirectional_v1": ["SOL"],
    }
    assert evidence["blocking_assets"] == ["xyz:GOLD"]
    assert evidence["execution_authority"] == "none"
    assert evidence["automatic_restart"] is False


def test_stale_generation_waits_for_every_position_and_order_to_clear() -> None:
    """Any observed exposure keeps restart readiness explicitly blocked."""
    evidence = configuration_generation_evidence(
        "runtime-profile",
        _EXPECTATION,
        {
            "BTC": {
                "final_state": "OPEN",
                "position_size_signed": 0.00039,
                "open_order_ids": [509104867159],
            },
            "HYPE": {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            },
        },
    )

    assert evidence["restart_state"] == "wait_for_flat_and_no_orders"
    assert evidence["blocking_assets"] == ["BTC"]
    assert evidence["current_entry_context_overrides"] == {
        "range_onset_bidirectional_v1|ETH": "dual_mtf_not_opposed"
    }


def test_generation_exposes_pending_provider_sizing_without_authority() -> None:
    """Pending sizing is explicit evidence, not an execution or balance gate."""
    expectation = replace(
        _EXPECTATION,
        provider_sizing_overrides=(
            ("range_onset_bidirectional_v1", "SOL", 0.10, 20.0),
        ),
    )

    evidence = configuration_generation_evidence(
        "runtime-profile",
        expectation,
        {
            "SOL": {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            }
        },
    )

    assert evidence["current_provider_sizing_overrides"] == {
        "range_onset_bidirectional_v1|SOL": {
            "margin_fraction": 0.10,
            "max_notional_usd": 20.0,
        }
    }
    assert evidence["execution_authority"] == "none"
    assert evidence["automatic_restart"] is False


def test_generation_exposes_directional_sizing_without_hiding_either_side() -> None:
    """Route-side sizing stays explicit, bidirectional, and report-only."""
    expectation = replace(
        _EXPECTATION,
        provider_directional_sizing_overrides=(
            ("hype_breakout_onset_bidirectional_v1", "HYPE", "long", 0.03, 75.0),
            ("hype_breakout_onset_bidirectional_v1", "HYPE", "short", 0.03, 25.0),
        ),
    )

    evidence = configuration_generation_evidence(
        "runtime-profile",
        expectation,
        {
            "HYPE": {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            }
        },
    )

    assert evidence["current_provider_directional_sizing_overrides"] == {
        "hype_breakout_onset_bidirectional_v1|HYPE|long": {
            "margin_fraction": 0.03,
            "max_notional_usd": 75.0,
        },
        "hype_breakout_onset_bidirectional_v1|HYPE|short": {
            "margin_fraction": 0.03,
            "max_notional_usd": 25.0,
        },
    }
    assert evidence["execution_authority"] == "none"
    assert evidence["automatic_restart"] is False


def test_stale_generation_marks_flat_order_free_prefix_as_candidate() -> None:
    """Flat/order-free evidence permits verification, never automatic restart."""
    evidence = configuration_generation_evidence(
        "runtime-profile",
        _EXPECTATION,
        {
            "BTC": {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            }
        },
    )

    assert evidence["restart_state"] == "candidate_flat_no_orders"
    assert evidence["blocking_assets"] == []
    assert evidence["automatic_restart"] is False


def test_stale_generation_marks_stopped_order_free_prefix_as_candidate() -> None:
    """A normally stopped zero-exposure ledger is a candidate restart boundary."""
    evidence = configuration_generation_evidence(
        "runtime-profile",
        _EXPECTATION,
        {
            "BTC": {
                "final_state": "STOPPED",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            }
        },
    )

    assert evidence["restart_state"] == "candidate_flat_no_orders"
    assert evidence["blocking_assets"] == []
    assert evidence["automatic_restart"] is False


def test_stopped_generation_blocks_when_exposure_or_orders_remain() -> None:
    """STOPPED is not safe when the ledger retains exposure or owned orders."""
    evidence = configuration_generation_evidence(
        "runtime-profile",
        _EXPECTATION,
        {
            "BTC": {
                "final_state": "STOPPED",
                "position_size_signed": 0.00039,
                "open_order_ids": [509104867159],
            }
        },
    )

    assert evidence["restart_state"] == "wait_for_flat_and_no_orders"
    assert evidence["blocking_assets"] == ["BTC"]


def test_matching_generation_requires_no_restart() -> None:
    """A matching runtime identity does not invent restart work."""
    evidence = configuration_generation_evidence(
        "current-profile",
        _EXPECTATION,
        {
            "BTC": {
                "final_state": "OPEN",
                "position_size_signed": 0.00039,
                "open_order_ids": [1],
            }
        },
    )

    assert evidence["restart_state"] == "not_required_current_configuration"
    assert evidence["blocking_assets"] == []


def test_generation_rejects_unknown_provider_recipe_exit_policy() -> None:
    """Pending profiles cannot disguise an unsupported recipe-exit action."""
    expectation = replace(
        _EXPECTATION,
        provider_exit_policies=(
            ProviderExitExpectation(
                strategy_id="provider",
                maximum_hold_seconds=28_800,
                maximum_hold_policy="fixed",
                hard_maximum_hold_seconds=None,
                maximum_hold_evidence_maximum_age_seconds=None,
                provider_recipe_exit_policy="sometimes",
                profit_lock_policy="none",
            ),
        ),
    )

    with pytest.raises(ValueError, match="provider exit policy is invalid"):
        configuration_generation_evidence(
            "current-profile",
            expectation,
            {
                "BTC": {
                    "final_state": "FLAT",
                    "position_size_signed": 0.0,
                    "open_order_ids": [],
                }
            },
        )


def test_generation_exposes_enabled_profit_lock_without_authority() -> None:
    """A pending completed-bar lock is visible but cannot hot-mutate runtime."""
    expectation = replace(
        _EXPECTATION,
        provider_exit_policies=(
            ProviderExitExpectation(
                "provider",
                28_800,
                "fixed",
                None,
                None,
                "ignore",
                "completed_bar_trailing",
                25.0,
                15.0,
                10.0,
            ),
        ),
    )

    evidence = configuration_generation_evidence(
        "runtime-profile",
        expectation,
        {
            "BTC": {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            }
        },
    )

    assert evidence["current_provider_exit_policies"]["provider"] == {
        "maximum_hold_seconds": 28_800,
        "maximum_hold_policy": "fixed",
        "hard_maximum_hold_seconds": None,
        "maximum_hold_evidence_maximum_age_seconds": None,
        "provider_recipe_exit_policy": "ignore",
        "profit_lock_policy": "completed_bar_trailing",
        "profit_lock_activation_bps": 25.0,
        "profit_lock_floor_bps": 15.0,
        "profit_lock_giveback_bps": 10.0,
    }
    assert evidence["execution_authority"] == "none"
    assert evidence["automatic_restart"] is False


def test_v60_generation_exposes_btc_component_floor_without_authority() -> None:
    """The checkpoint accepts only the exact staged BTC specialized policy."""
    expectation = load_configuration_expectation(
        _FIXTURE_PROFILES
        / "multi_asset_growth_first_5000_eight_asset_btc_hulk_smart_exit_candidate_v60.toml"
    )

    evidence = configuration_generation_evidence(
        "runtime-profile",
        expectation,
        {
            "BTC": {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            }
        },
    )

    policy = evidence["current_provider_exit_policies"][
        "hulk_expansion_short_robust_v3"
    ]
    assert policy["profit_lock_policy"] == "btc_hulk_delayed_component_floor_v1"
    assert policy["profit_lock_activation_bps"] is None
    assert policy["profit_lock_floor_bps"] is None
    assert policy["profit_lock_giveback_bps"] is None
    assert evidence["execution_authority"] == "none"


def test_generation_exposes_directional_profit_lock_without_collapsing_scope(
    tmp_path: Path,
) -> None:
    """Checkpoint evidence preserves strategy, symbol, and side identity."""
    source = _FIXTURE_PROFILES / "multi_asset_growth_first_5000_repaired_candidate_v49.toml"
    text = source.read_text(encoding="utf-8")
    anchor = 'execution_symbols = ["HYPE"]\n'
    override = (
        "profit_lock_overrides = { HYPE = { long = { policy = "
        '"completed_bar_trailing", activation_bps = 25.0, floor_bps = 8.0, '
        'giveback_bps = 6.0 }, short = { policy = "none" } } }\n'
    )
    profile = tmp_path / "directional-lock.toml"
    profile.write_text(text.replace(anchor, anchor + override, 1), encoding="utf-8")

    expectation = load_configuration_expectation(profile)
    evidence = configuration_generation_evidence(
        "runtime-profile",
        expectation,
        {
            "HYPE": {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            }
        },
    )

    directional = evidence["current_provider_directional_exit_policies"]
    long = directional["hype_breakout_compression_pullback_bidirectional_v1|HYPE|long"]
    short = directional[
        "hype_breakout_compression_pullback_bidirectional_v1|HYPE|short"
    ]
    assert long["profit_lock_policy"] == "completed_bar_trailing"
    assert long["profit_lock_activation_bps"] == pytest.approx(25.0)
    assert long["profit_lock_floor_bps"] == pytest.approx(8.0)
    assert long["profit_lock_giveback_bps"] == pytest.approx(6.0)
    assert short["profit_lock_policy"] == "none"
    assert evidence["execution_authority"] == "none"
