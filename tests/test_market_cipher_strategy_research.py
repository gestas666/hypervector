"""Frozen profile and reporting contracts for Hulk strategy research."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.market_cipher_strategy_research import (
    frame_sha256,
    market_cipher_robustness_names,
    resolve_hulk_research_profile,
    resolve_market_cipher_replay_config,
)


def test_tuned_short_profile_freezes_actual_selected_parameters() -> None:
    """The validated short challenger may not drift from the recorded surface."""
    profile = resolve_hulk_research_profile("hulk_expansion_short_tuned_v2")

    assert profile.side == "short"
    assert profile.supertrend_period == 7
    assert profile.supertrend_multiplier == 3.0
    assert profile.adx_period == 20
    assert profile.squeeze_period == 20
    assert profile.minimum_score == 8
    assert profile.pivot_bars == 8
    assert profile.adx_usable == 18.0
    assert profile.adx_trending == 25.0


def test_control_and_tuned_profiles_have_distinct_identities() -> None:
    """A tuned result cannot overwrite or masquerade as its control."""
    control = resolve_hulk_research_profile("hulk_expansion_control_v1")
    tuned = resolve_hulk_research_profile("hulk_expansion_bidirectional_tuned_v2")

    assert control.name != tuned.name
    assert control.pivot_bars != tuned.pivot_bars
    assert control.adx_period != tuned.adx_period


def test_robust_short_profile_matches_development_only_autotune_selection() -> None:
    """The forward challenger freezes the journal-ranked development identity."""
    profile = resolve_hulk_research_profile("hulk_expansion_short_robust_v3")

    assert profile.side == "short"
    assert profile.supertrend_period == 7
    assert profile.supertrend_multiplier == 3.0
    assert profile.adx_period == 20
    assert profile.squeeze_period == 20
    assert profile.minimum_score == 7
    assert profile.pivot_bars == 6
    assert profile.adx_usable == 16.0
    assert profile.adx_trending == 23.0
    assert profile.status == "forward_robustness_survivor_not_promoted"


def test_frame_hash_changes_when_one_market_value_changes() -> None:
    """Data evidence identifies values and timestamps, not only row counts."""
    index = pd.date_range("2026-01-01", periods=2, freq="30min", tz="UTC")
    frame = pd.DataFrame({"close": [100.0, 101.0]}, index=index)
    changed = frame.copy()
    changed.iloc[1, 0] = 101.01

    assert frame_sha256(frame) != frame_sha256(changed)


def test_robustness_matrix_is_frozen_and_predeclared() -> None:
    """Robustness identities cannot be invented after observing outcomes."""
    assert market_cipher_robustness_names() == (
        "nominal",
        "cost_stress",
        "entry_delay_2_bars",
        "stop_cap_60_bps",
        "stop_cap_90_bps",
        "funding_2x",
    )


def test_robustness_configs_change_only_declared_execution_dimension() -> None:
    """Each perturbation remains attributable to one execution assumption."""
    nominal = resolve_market_cipher_replay_config("nominal")
    delayed = resolve_market_cipher_replay_config("entry_delay_2_bars")
    funding = resolve_market_cipher_replay_config("funding_2x")

    assert delayed.entry_delay_bars == 2
    assert delayed.funding_rate_multiplier == nominal.funding_rate_multiplier
    assert funding.funding_rate_multiplier == 2.0
    assert funding.entry_delay_bars == nominal.entry_delay_bars


def test_unknown_robustness_identity_fails_closed() -> None:
    """An unjournaled perturbation may not silently inherit nominal settings."""
    with pytest.raises(ValueError, match="unknown Market Cipher robustness"):
        resolve_market_cipher_replay_config("post_hoc_winner")


def test_fifteen_minute_replay_preserves_nominal_maximum_hold_hours() -> None:
    """Changing the signal clock must not silently halve the hold horizon."""
    thirty = resolve_market_cipher_replay_config("nominal", bar_minutes=30)
    fifteen = resolve_market_cipher_replay_config("nominal", bar_minutes=15)

    assert thirty.maximum_hold_bars == 48
    assert fifteen.maximum_hold_bars == 96


def test_unapproved_market_cipher_timeframe_fails_closed() -> None:
    """Research clocks are explicit identities rather than arbitrary integers."""
    with pytest.raises(ValueError, match="bar_minutes must be 15 or 30"):
        resolve_market_cipher_replay_config("nominal", bar_minutes=5)
