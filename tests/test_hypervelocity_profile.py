"""Validated runtime profile for one-way bidirectional Hypervelocity."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile


PROFILE = Path("configs/hypervelocity_faithful.toml")


def test_faithful_profile_enforces_one_way_bidirectional_runtime() -> None:
    profile = load_hypervelocity_profile(PROFILE)

    assert profile.strategy_id == "hypervelocity_1m_scalper"
    assert profile.position_mode == "one_way"
    assert profile.max_positions_per_symbol == 1
    assert profile.direction_mode == "regime_bidirectional"
    assert profile.allow_reversal_while_open is False
    assert profile.switch_after_exit is True
    assert profile.open_position_range_policy == "hold_until_target"
    assert profile.margin_fraction == pytest.approx(0.70)
    assert profile.leverage == pytest.approx(40.0)
    assert profile.target_margin_pct == pytest.approx(8.0)
    assert profile.fee_tier == 0
    assert profile.maker_fee_rate == pytest.approx(0.00015)
    assert profile.taker_fee_rate == pytest.approx(0.00045)
    assert profile.slippage_bps == 0.0
    assert profile.funding_refresh_seconds == 60.0
    assert profile.size_decimals == 5
    assert profile.venue_max_leverage >= profile.leverage
    assert profile.margin_mode == "isolated"
    assert profile.live_canary_max_notional_usd == pytest.approx(3_360.0)
    assert profile.runtime_mode == "shadow"
    assert profile.shadow_execution_model == "nautilus_event_v1"
    assert profile.execution_submit_latency_ms == 50
    assert profile.execution_cancel_latency_ms == 50
    assert profile.execution_update_latency_ms == 50
    assert profile.execution_max_event_age_ms == 3_000
    assert profile.restart_queue_policy == "requeue_behind_displayed_liquidity"
    assert profile.strict_hl_only is True
    assert profile.metalabel_mode == "observe"
    assert profile.model_long_bundle.is_dir()
    assert profile.model_short_bundle.is_dir()
    assert profile.reentry_cooldown_bars == 1
    assert getattr(profile, "entry_ttl_seconds", None) == pytest.approx(300.0)
    assert getattr(profile, "expired_entry_rearm_policy", None) == "regime_reset"
    assert profile.same_direction_reentry_policy == "regime_reset"
    assert profile.orderbook_archive_enabled is True
    assert profile.orderbook_archive_depth_levels == 20


def _venue_profile_text(
    *,
    margin_mode: str | None,
    max_notional: str | None,
) -> str:
    """Return profile text with controlled venue-friction fields."""
    lines = [
        line
        for line in PROFILE.read_text(encoding="utf-8").splitlines()
        if not line.startswith(("margin_mode =", "live_canary_max_notional_usd ="))
    ]
    additions = [line for line in (margin_mode, max_notional) if line is not None]
    marker = 'network = "mainnet"'
    index = lines.index(marker) + 1
    lines[index:index] = additions
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    "margin_mode",
    [None, 'margin_mode = "cross"', 'margin_mode = "portfolio"'],
)
def test_profile_requires_isolated_margin(
    tmp_path: Path,
    margin_mode: str | None,
) -> None:
    path = tmp_path / "invalid-margin.toml"
    path.write_text(
        _venue_profile_text(
            margin_mode=margin_mode,
            max_notional="live_canary_max_notional_usd = 3360.0",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="margin_mode must be 'isolated'"):
        load_hypervelocity_profile(path)


@pytest.mark.parametrize("value", ["0.0", "-1.0", "nan"])
def test_profile_requires_positive_finite_live_canary_notional(
    tmp_path: Path,
    value: str,
) -> None:
    path = tmp_path / "invalid-canary-cap.toml"
    path.write_text(
        _venue_profile_text(
            margin_mode='margin_mode = "isolated"',
            max_notional=f"live_canary_max_notional_usd = {value}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="live_canary_max_notional_usd"):
        load_hypervelocity_profile(path)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "max_positions_per_symbol = 1",
            "max_positions_per_symbol = 2",
            "max_positions_per_symbol must be 1",
        ),
        ('position_mode = "one_way"', 'position_mode = "hedge"', "one_way"),
        (
            "allow_reversal_while_open = false",
            "allow_reversal_while_open = true",
            "allow_reversal_while_open must be false",
        ),
        ("margin_fraction = 0.70", "margin_fraction = 0.50", "margin_fraction"),
        ("may_filter = false", "may_filter = true", "may_filter must be false"),
        (
            'same_direction_reentry_policy = "regime_reset"',
            'same_direction_reentry_policy = "immediate"',
            "same_direction_reentry_policy",
        ),
        (
            'shadow_execution_model = "nautilus_event_v1"',
            'shadow_execution_model = "legacy_bar_through_v1"',
            "shadow_execution_model",
        ),
        (
            'fill_model = "nautilus_event_v1"',
            'fill_model = "post_only_limit_through_v1"',
            "fill_model",
        ),
        (
            'restart_queue_policy = "requeue_behind_displayed_liquidity"',
            'restart_queue_policy = "preserve_unknown_queue"',
            "restart_queue_policy",
        ),
    ],
)
def test_profile_rejects_unfaithful_runtime_values(
    tmp_path: Path,
    old: str,
    new: str,
    message: str,
) -> None:
    text = PROFILE.read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / "invalid.toml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_hypervelocity_profile(path)
