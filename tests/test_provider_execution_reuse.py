"""A new profile reuses a registered provider with its own execution values.

Provider registrations refuse only what a provider's signal cannot compute or
bind: the symbols it evaluates, its signal clock, the sides it emits, the
position interaction it implements, the anchors its intents carry, and
observer-only scope. Stops, targets, holds, entry delays, execution scope and
exit-policy combinations are the profile's own choice (SRS_HV1_NO_GATES); the
generic loader and the runtime validator still bound them.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

import hypervector.operations.cohort_runtime_validation_check as check
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.research_pending_market_observer import (
    RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY,
)

PROFILE_B = Path("tests/fixtures/cohort_chain/profile_b.toml")
_BOTH = ["long", "short"]
_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _execution(**values: object) -> dict[str, object]:
    return {"entry_liquidity": "taker_ioc", **values}


def _fixed(stop_bps: float, hold: int, **values: object) -> dict[str, object]:
    return _execution(
        stop_policy="fixed_bps",
        stop_bps=stop_bps,
        maximum_hold_seconds=hold,
        **{"target_policy": "none", **values},
    )


def _structural(low: float, high: float, hold: int, **values: object) -> dict:
    return _execution(
        stop_policy="structural_clamped_bps",
        minimum_stop_bps=low,
        maximum_stop_bps=high,
        maximum_hold_seconds=hold,
        **{"target_policy": "none", **values},
    )


def _provider(
    strategy_id: str,
    symbols: list[str],
    sides: list[str],
    timeframe: str,
    execution: dict[str, object],
    **extra: object,
) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbols": symbols,
        "sides": sides,
        "timeframe": timeframe,
        "maximum_entry_delay_seconds": 75,
        "execution_symbols": symbols,
        "position_policy": "enter_and_close",
        **extra,
        "execution": execution,
    }


# Registered providers configured with deliberately varied execution values:
# stops, targets, holds, entry delays, side and execution scope, exit-policy
# combinations and overrides.
_REUSED = {
    "fixed_target_long": _provider(
        "test_long_stop_1m",
        ["BTC"],
        ["long"],
        "1m",
        _fixed(90.0, 7_200, target_policy="fixed_bps", target_bps=150.0),
        maximum_entry_delay_seconds=45,
    ),
    "reward_risk_with_profit_lock": _provider(
        "test_long_target_1m",
        ["BTC"],
        _BOTH,
        "1m",
        _fixed(
            45.0,
            3_600,
            target_policy="reward_risk",
            target_r_multiple=2.5,
            provider_recipe_exit_policy="honor",
            profit_lock_policy="completed_bar_trailing",
            profit_lock_activation_bps=40.0,
            profit_lock_floor_bps=10.0,
            profit_lock_giveback_bps=20.0,
        ),
        maximum_entry_delay_seconds=120,
    ),
    "safety_overlay": _provider(
        "test_channel_long_15m",
        ["LTC"],
        ["long"],
        "15m",
        _fixed(150.0, 604_800, safety_stop_overlay=True),
    ),
    "fixed_target_two_markets": _provider(
        "test_channel_15m",
        ["ETH", "xyz:AAA"],
        _BOTH,
        "15m",
        _fixed(120.0, 43_200, target_policy="fixed_bps", target_bps=240.0),
        maximum_entry_delay_seconds=300,
    ),
    "structural_with_profit_lock": _provider(
        "test_channel_fast_15m",
        ["BTC", "HYPE"],
        _BOTH,
        "15m",
        _structural(
            30.0,
            200.0,
            172_800,
            profit_lock_policy="completed_bar_trailing",
            profit_lock_activation_bps=80.0,
            profit_lock_floor_bps=20.0,
            profit_lock_giveback_bps=40.0,
        ),
    ),
    "side_and_stop_overrides": _provider(
        "test_channel_short_15m",
        ["xyz:FFF"],
        _BOTH,
        "15m",
        _fixed(200.0, 21_600, provider_recipe_exit_policy="honor"),
        execution_side_overrides={"xyz:FFF": ["short"]},
        stop_bps_overrides={"xyz:FFF": 150.0},
    ),
    "recipe_exit_ignored": _provider(
        "test_fade_1m",
        ["ETH"],
        ["long"],
        "1m",
        _fixed(90.0, 3_600, provider_recipe_exit_policy="ignore"),
    ),
    "short_hold_fixed_target": _provider(
        "test_breakout_1m",
        ["ETH", "SOL"],
        _BOTH,
        "1m",
        _fixed(45.0, 7_200, target_policy="fixed_bps", target_bps=90.0),
        maximum_entry_delay_seconds=30,
    ),
    "structural_reward_risk_short": _provider(
        "test_short_trend_5m",
        ["BTC"],
        ["short"],
        "5m",
        _structural(
            30.0,
            120.0,
            43_200,
            target_policy="reward_risk",
            target_r_multiple=2.0,
            provider_recipe_exit_policy="honor",
        ),
    ),
    "execution_side_override": _provider(
        "test_squeeze_1m",
        ["HYPE"],
        _BOTH,
        "1m",
        _fixed(100.0, 14_400, provider_recipe_exit_policy="ignore"),
        execution_side_overrides={"HYPE": ["short"]},
    ),
    "extended_hold": _provider(
        "test_alignment_1m",
        ["HYPE"],
        _BOTH,
        "1m",
        _fixed(
            100.0,
            3_600,
            maximum_hold_policy="extend_while_regime_supported",
            hard_maximum_hold_seconds=7_200,
            maximum_hold_evidence_maximum_age_seconds=120,
            provider_recipe_exit_policy="honor",
        ),
    ),
    "reward_risk": _provider(
        "test_continuation_1m",
        ["ETH"],
        _BOTH,
        "1m",
        _fixed(45.0, 3_600, target_policy="reward_risk", target_r_multiple=3.0),
    ),
    "observed_absolute_target": _provider(
        "test_anchor_target_15m",
        ["xyz:BBB"],
        _BOTH,
        "15m",
        _fixed(120.0, 7_200, target_policy="absolute_anchor"),
        execution_symbols=[],
    ),
    "single_side_fixed_target": _provider(
        "test_btc_long_only_15m",
        ["BTC"],
        ["long"],
        "15m",
        _fixed(90.0, 7_200, target_policy="fixed_bps", target_bps=150.0),
    ),
    "hip3_profit_lock": _provider(
        "test_session_a_15m",
        ["xyz:DDD"],
        _BOTH,
        "15m",
        _fixed(
            120.0,
            43_200,
            profit_lock_policy="completed_bar_trailing",
            profit_lock_activation_bps=100.0,
            profit_lock_floor_bps=30.0,
            profit_lock_giveback_bps=60.0,
        ),
    ),
    "research_observer": _provider(
        RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY,
        ["xyz:FFF"],
        ["long"],
        "15m",
        _fixed(200.0, 3_600),
        execution_symbols=[],
    ),
}


def _toml(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml(item) for item in value) + "]"
    if isinstance(value, dict):
        rows = ", ".join(f"{_key(key)} = {_toml(item)}" for key, item in value.items())
        return "{ " + rows + " }"
    raise TypeError(f"unsupported TOML value: {value!r}")


def _key(key: str) -> str:
    return key if _BARE_KEY.match(key) else json.dumps(key)


def _companion(provider: dict[str, object]) -> dict[str, object]:
    """A second executable market, since a live cohort needs two assets."""
    candidates = (
        _provider("test_mirror_1m", ["BTC"], ["long"], "1m", _fixed(60.0, 3_600)),
        _provider("test_pullback_1m", ["ETH"], _BOTH, "1m", _fixed(60.0, 3_600)),
    )
    return next(
        candidate
        for candidate in candidates
        if candidate["strategy_id"] != provider["strategy_id"]
        and not set(candidate["symbols"]) & set(provider["symbols"])
    )


def _write_profile(path: Path, providers: list[dict[str, object]]) -> Path:
    symbols = list(
        dict.fromkeys(symbol for provider in providers for symbol in provider["symbols"])
    )
    lines = [
        'profile = "fixture_provider_reuse"',
        'network = "mainnet"',
        'margin_mode = "isolated"',
        f"maximum_positions = {len(symbols)}",
        "",
        "[runtime]",
        'cohort_ledger = "data/live/bidirectional_cohort/decisions.jsonl"',
        'stop_file = "data/live/bidirectional_cohort/STOP"',
        "poll_seconds = 15.0",
        "lookback_days = 14",
    ]
    for symbol in symbols:
        lines += [
            "",
            "[[assets]]",
            f"symbol = {_toml(symbol)}",
            'sides = ["long", "short"]',
            "leverage = 3.0",
            "venue_max_leverage = 10.0",
            "margin_fraction = 0.02",
            "max_notional_usd = 200.0",
            "market_slippage_cap_fraction = 0.01",
            "stop_bps = 100.0",
            "maximum_hold_seconds = 86400",
        ]
    for priority, provider in enumerate(providers, start=1):
        lines += ["", "[[providers]]", f"priority = {priority * 10}"]
        lines += [f"{_key(key)} = {_toml(value)}" for key, value in provider.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _load_live(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        path, mode="live", enabled=True, accepts_live_risk=True
    )


@pytest.mark.parametrize("case", sorted(_REUSED))
def test_a_reused_provider_loads_with_its_own_execution_values(
    tmp_path: Path, case: str
) -> None:
    provider = _REUSED[case]
    profile = _write_profile(tmp_path / "profile.toml", [provider, _companion(provider)])

    config = _load_live(profile)

    loaded = next(
        row for row in config.providers if row.strategy_id == provider["strategy_id"]
    )
    for key, value in provider["execution"].items():
        assert getattr(loaded.execution, key) == value, key
    assert loaded.maximum_entry_delay_seconds == provider["maximum_entry_delay_seconds"]
    assert loaded.execution_symbols == tuple(provider["execution_symbols"])
    assert check.check(profile, mode="observe") == []


def test_profile_b_reusing_providers_with_new_exits_passes_live_validate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The armed-start gate accepts reused providers with different exits."""
    text = PROFILE_B.read_text(encoding="utf-8")
    target_old = (
        "maximum_entry_delay_seconds = 30\n"
        'execution_symbols = ["BTC"]\n'
        'position_policy = "enter_and_close"\n'
        'execution = { entry_liquidity = "taker_ioc", stop_policy = "fixed_bps", '
        'target_policy = "fixed_bps", maximum_hold_seconds = 86400, stop_bps = 60.0, '
        "target_bps = 60.0,"
    )
    target_new = (
        "maximum_entry_delay_seconds = 90\n"
        'execution_symbols = ["BTC"]\n'
        'position_policy = "enter_and_close"\n'
        'execution = { entry_liquidity = "taker_ioc", stop_policy = "fixed_bps", '
        'target_policy = "fixed_bps", maximum_hold_seconds = 21600, stop_bps = 95.0, '
        "target_bps = 210.0,"
    )
    channel_old = (
        'stop_policy = "structural_clamped_bps", target_policy = "none", '
        "maximum_hold_seconds = 86400, minimum_stop_bps = 20.0, "
        "maximum_stop_bps = 250.0,"
    )
    channel_new = (
        'stop_policy = "fixed_bps", target_policy = "fixed_bps", '
        "maximum_hold_seconds = 259200, stop_bps = 140.0, target_bps = 420.0,"
    )
    bias_old = (
        'target_policy = "none", maximum_hold_seconds = 172800, stop_bps = 60.0, '
        'safety_stop_overlay = false, maximum_hold_policy = "fixed", '
        'provider_recipe_exit_policy = "honor"'
    )
    bias_new = (
        'target_policy = "none", maximum_hold_seconds = 28800, stop_bps = 85.0, '
        'safety_stop_overlay = false, maximum_hold_policy = "fixed", '
        'provider_recipe_exit_policy = "ignore"'
    )
    for old, new in (
        (target_old, target_new),
        (channel_old, channel_new),
        (bias_old, bias_new),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    profile = tmp_path / "reused_providers.toml"
    profile.write_text(text, encoding="utf-8")

    providers = {row.strategy_id: row for row in _load_live(profile).providers}
    target = providers["test_long_target_1m"]
    assert (target.execution.stop_bps, target.execution.target_bps) == (95.0, 210.0)
    assert target.execution.maximum_hold_seconds == 21_600
    assert target.maximum_entry_delay_seconds == 90
    channel = providers["test_channel_short_15m"]
    assert channel.execution.stop_policy == "fixed_bps"
    assert channel.execution.maximum_hold_seconds == 259_200
    assert check.check(profile, mode="live") == []

    exit_code = check.main(
        ["--config", str(profile), "--mode", "live", "--equity", "5000"]
    )

    report = json.loads(capsys.readouterr().out)
    assert (exit_code, report["verdict"]) == (0, "accepted")
    assert report["book"]["problems"] == []


def _refused(case: str, **changes: object) -> dict[str, object]:
    provider = dict(_REUSED[case])
    execution = changes.pop("execution", None)
    provider.update(changes)
    if execution is not None:
        provider["execution"] = execution
    if "symbols" in changes:
        provider["execution_symbols"] = changes.get(
            "execution_symbols", changes["symbols"]
        )
    return provider


# What a provider's signal cannot compute or bind stays a refusal.
_REFUSED = {
    "a market the signal does not compute": (
        _refused("single_side_fixed_target", symbols=["SOL"]),
        "evaluates only",
    ),
    "a side the signal does not emit": (
        _refused("single_side_fixed_target", sides=_BOTH),
        "emits only",
    ),
    "a position interaction the signal does not implement": (
        _refused("single_side_fixed_target", position_policy="flat_entry_only"),
        "implements position policies",
    ),
    "a structural stop without a stop anchor": (
        _refused("fixed_target_long", execution=_structural(20.0, 80.0, 3_600)),
        "anchors its intents do not carry",
    ),
    "a mislabeled signal clock": (
        _refused("fixed_target_long", timeframe="15m"),
        "reads the 1m signal clock",
    ),
    "an absolute target without a target anchor": (
        _refused(
            "recipe_exit_ignored",
            execution=_fixed(90.0, 3_600, target_policy="absolute_anchor"),
        ),
        "anchors its intents do not carry",
    ),
    "a target anchor without its absolute target": (
        _refused("observed_absolute_target", execution=_fixed(120.0, 7_200)),
        "anchors its intents do not carry",
    ),
    "an observer with execution authority": (
        _refused("research_observer", execution_symbols=["xyz:FFF"]),
        "observe-only",
    ),
    "an unregistered strategy id": (
        _refused("fixed_target_long", strategy_id="test_unregistered_1m"),
        "not registered",
    ),
}


@pytest.mark.parametrize("case", sorted(_REFUSED))
def test_a_technical_provider_constraint_is_still_refused(
    tmp_path: Path, case: str
) -> None:
    provider, message = _REFUSED[case]
    profile = _write_profile(tmp_path / "profile.toml", [provider, _companion(provider)])

    with pytest.raises(MultiAssetLiveConfigError, match=message):
        _load_live(profile)
