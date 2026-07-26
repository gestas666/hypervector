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
    assert profile.runtime_mode == "shadow"
    assert profile.strict_hl_only is True
    assert profile.metalabel_mode == "observe"
    assert profile.model_long_bundle.is_dir()
    assert profile.model_short_bundle.is_dir()
    assert profile.reentry_cooldown_bars == 1
    assert getattr(profile, "entry_ttl_seconds", None) == pytest.approx(300.0)
    assert getattr(profile, "expired_entry_rearm_policy", None) == "regime_reset"
    assert profile.orderbook_archive_enabled is True
    assert profile.orderbook_archive_depth_levels == 20


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            'max_positions_per_symbol = 1',
            'max_positions_per_symbol = 2',
            "max_positions_per_symbol must be 1",
        ),
        ('position_mode = "one_way"', 'position_mode = "hedge"', "one_way"),
        (
            "allow_reversal_while_open = false",
            "allow_reversal_while_open = true",
            "allow_reversal_while_open must be false",
        ),
        ("margin_fraction = 0.70", "margin_fraction = 0.50", "margin_fraction"),
        ('may_filter = false', 'may_filter = true', "may_filter must be false"),
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
