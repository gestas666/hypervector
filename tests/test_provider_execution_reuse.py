"""A new profile reuses a live strategy provider with its own execution values.

Provider validators refuse only what a provider's signal cannot compute or
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
from hypervector.live.btc_hulk_robust_short_provider import (
    HULK_ROBUST_SHORT_STRATEGY,
    HULK_TUNED_SHORT_STRATEGY,
)
from hypervector.live.btc_liquidity_sweep_long_provider import (
    LIQUIDITY_SWEEP_LONG_STRATEGY,
    LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY,
)
from hypervector.live.directional_range_onset_provider import (
    ETH_RANGE_LONG_STRATEGY,
    SOL_RANGE_SHORT_STRATEGY,
)
from hypervector.live.eth_breakout_transfer_provider import (
    ETH_BREAKOUT_TRANSFER_STRATEGY,
)
from hypervector.live.hip3_cash_open_gap_provider import HIP3_BBB_CASH_OPEN_STRATEGY
from hypervector.live.hip3_cohort_providers import (
    HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
)
from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
    HIP3_CCC_FRESH15_V4_STRATEGY,
)
from hypervector.live.hourly_price_provider import (
    DONCHIAN8_STRATEGY,
    DONCHIAN20_STRATEGY,
    PROTECTED_DONCHIAN20_STRATEGY,
)
from hypervector.live.hype_breakout_compression_provider import (
    HYPE_COMPRESSION_BREAKOUT_STRATEGY,
)
from hypervector.live.hype_compression_alignment_provider import (
    HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
)
from hypervector.live.hype_native_breakout_provider import (
    HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
    HYPE_NATIVE_BREAKOUT_STRATEGY,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_route_contract_validation import (
    HULK_BIDIRECTIONAL_STRATEGY,
)
from hypervector.live.research_pending_market_observer import (
    RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY,
)
from hypervector.live.bbb_cash_session_breakout_provider import (
    BBB_CASH_SESSION_LONG_STRATEGY,
)
from hypervector.live.ltc_donchian_provider import LTC_DONCHIAN_LONG_STRATEGY

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


# Every provider with a dedicated validator, configured with values that none of
# the removed profiles used: different stops, targets, holds, entry delays,
# side and execution scope, exit-policy combinations and overrides.
_REUSED = {
    "liquidity_sweep": _provider(
        LIQUIDITY_SWEEP_LONG_STRATEGY,
        ["BTC"],
        ["long"],
        "1h",
        _fixed(90.0, 7_200, target_policy="fixed_bps", target_bps=150.0),
        maximum_entry_delay_seconds=45,
    ),
    "liquidity_sweep_target60": _provider(
        LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY,
        ["BTC"],
        _BOTH,
        "1h",
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
    "ltc_donchian": _provider(
        LTC_DONCHIAN_LONG_STRATEGY,
        ["LTC"],
        ["long"],
        "15m",
        _fixed(150.0, 604_800, safety_stop_overlay=True),
    ),
    "hourly_donchian": _provider(
        DONCHIAN20_STRATEGY,
        ["ETH", "xyz:AAA"],
        _BOTH,
        "15m",
        _fixed(120.0, 43_200, target_policy="fixed_bps", target_bps=240.0),
        maximum_entry_delay_seconds=300,
    ),
    "hourly_donchian_protected": _provider(
        PROTECTED_DONCHIAN20_STRATEGY,
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
    "hourly_donchian_overrides": _provider(
        DONCHIAN8_STRATEGY,
        ["xyz:FFF"],
        _BOTH,
        "15m",
        _fixed(200.0, 21_600, provider_recipe_exit_policy="honor"),
        execution_side_overrides={"xyz:FFF": ["short"]},
        stop_bps_overrides={"xyz:FFF": 150.0},
    ),
    "eth_range_long": _provider(
        ETH_RANGE_LONG_STRATEGY,
        ["ETH"],
        ["long"],
        "1m",
        _fixed(90.0, 3_600, provider_recipe_exit_policy="ignore"),
    ),
    "sol_range_short": _provider(
        SOL_RANGE_SHORT_STRATEGY,
        ["SOL"],
        _BOTH,
        "1m",
        _fixed(70.0, 14_400, target_policy="fixed_bps", target_bps=140.0),
    ),
    "range_onset": _provider(
        "test_breakout_1m",
        ["ETH", "SOL"],
        _BOTH,
        "1m",
        _fixed(45.0, 7_200, target_policy="fixed_bps", target_bps=90.0),
        maximum_entry_delay_seconds=30,
    ),
    "hulk_bidirectional": _provider(
        HULK_BIDIRECTIONAL_STRATEGY,
        ["ETH", "SOL"],
        _BOTH,
        "30m",
        _fixed(50.0, 3_600, target_policy="fixed_bps", target_bps=100.0),
    ),
    "hulk_robust_short": _provider(
        HULK_ROBUST_SHORT_STRATEGY,
        ["BTC"],
        ["short"],
        "30m",
        _structural(
            30.0,
            120.0,
            43_200,
            target_policy="reward_risk",
            target_r_multiple=2.0,
            provider_recipe_exit_policy="honor",
            profit_lock_policy="btc_hulk_delayed_component_exit_v2",
        ),
    ),
    "hulk_tuned_short": _provider(
        HULK_TUNED_SHORT_STRATEGY,
        ["BTC"],
        _BOTH,
        "30m",
        _fixed(80.0, 7_200),
    ),
    "hype_native": _provider(
        HYPE_NATIVE_BREAKOUT_STRATEGY,
        ["HYPE"],
        ["long"],
        "1m",
        _fixed(60.0, 3_600, target_policy="fixed_bps", target_bps=120.0),
    ),
    "hype_native_long": _provider(
        HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
        ["HYPE"],
        _BOTH,
        "1m",
        _fixed(100.0, 14_400, provider_recipe_exit_policy="ignore"),
        execution_side_overrides={"HYPE": ["short"]},
    ),
    "hype_compression": _provider(
        HYPE_COMPRESSION_BREAKOUT_STRATEGY,
        ["HYPE"],
        _BOTH,
        "1m",
        _fixed(60.0, 7_200),
    ),
    "hype_alignment": _provider(
        HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
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
    "eth_transfer": _provider(
        ETH_BREAKOUT_TRANSFER_STRATEGY,
        ["ETH"],
        _BOTH,
        "1m",
        _fixed(45.0, 3_600, target_policy="reward_risk", target_r_multiple=3.0),
    ),
    "bbb_cash_open_observed": _provider(
        HIP3_BBB_CASH_OPEN_STRATEGY,
        ["xyz:BBB"],
        _BOTH,
        "15m",
        _fixed(120.0, 7_200, target_policy="absolute_anchor"),
        execution_symbols=[],
    ),
    "bbb_cash_session": _provider(
        BBB_CASH_SESSION_LONG_STRATEGY,
        ["xyz:BBB"],
        ["long"],
        "15m",
        _fixed(90.0, 7_200, target_policy="fixed_bps", target_bps=150.0),
    ),
    "fresh15_commodity": _provider(
        HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
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
    "fresh15_index": _provider(
        HIP3_INDEX_FRESH15_V3_STRATEGY,
        ["xyz:AAA"],
        _BOTH,
        "15m",
        _fixed(
            60.0,
            21_600,
            profit_lock_policy="completed_bar_trailing",
            profit_lock_activation_bps=80.0,
            profit_lock_floor_bps=20.0,
            profit_lock_giveback_bps=40.0,
        ),
    ),
    "fresh15_ccc_both_sides": _provider(
        HIP3_CCC_FRESH15_V4_STRATEGY,
        ["xyz:CCC"],
        _BOTH,
        "15m",
        _fixed(100.0, 43_200),
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
        _provider(
            LIQUIDITY_SWEEP_LONG_STRATEGY, ["BTC"], ["long"], "1h", _fixed(60.0, 3_600)
        ),
        _provider(
            ETH_BREAKOUT_TRANSFER_STRATEGY, ["ETH"], _BOTH, "1m", _fixed(60.0, 3_600)
        ),
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


def test_profile_b_reusing_sweep_and_donchian_with_new_exits_passes_live_validate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The armed-start gate accepts reused providers with different exits."""
    text = PROFILE_B.read_text(encoding="utf-8")
    sweep_old = (
        "maximum_entry_delay_seconds = 30\n"
        'execution_symbols = ["BTC"]\n'
        'position_policy = "enter_and_close"\n'
        'execution = { entry_liquidity = "taker_ioc", stop_policy = "fixed_bps", '
        'target_policy = "fixed_bps", maximum_hold_seconds = 86400, stop_bps = 60.0, '
        "target_bps = 60.0,"
    )
    sweep_new = (
        "maximum_entry_delay_seconds = 90\n"
        'execution_symbols = ["BTC"]\n'
        'position_policy = "enter_and_close"\n'
        'execution = { entry_liquidity = "taker_ioc", stop_policy = "fixed_bps", '
        'target_policy = "fixed_bps", maximum_hold_seconds = 21600, stop_bps = 95.0, '
        "target_bps = 210.0,"
    )
    donchian_old = (
        'stop_policy = "structural_clamped_bps", target_policy = "none", '
        "maximum_hold_seconds = 86400, minimum_stop_bps = 20.0, "
        "maximum_stop_bps = 250.0,"
    )
    donchian_new = (
        'stop_policy = "fixed_bps", target_policy = "fixed_bps", '
        "maximum_hold_seconds = 259200, stop_bps = 140.0, target_bps = 420.0,"
    )
    range_old = (
        'target_policy = "none", maximum_hold_seconds = 172800, stop_bps = 60.0, '
        'safety_stop_overlay = false, maximum_hold_policy = "fixed", '
        'provider_recipe_exit_policy = "honor"'
    )
    range_new = (
        'target_policy = "none", maximum_hold_seconds = 28800, stop_bps = 85.0, '
        'safety_stop_overlay = false, maximum_hold_policy = "fixed", '
        'provider_recipe_exit_policy = "ignore"'
    )
    for old, new in (
        (sweep_old, sweep_new),
        (donchian_old, donchian_new),
        (range_old, range_new),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    profile = tmp_path / "reused_providers.toml"
    profile.write_text(text, encoding="utf-8")

    providers = {row.strategy_id: row for row in _load_live(profile).providers}
    sweep = providers[LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY]
    assert (sweep.execution.stop_bps, sweep.execution.target_bps) == (95.0, 210.0)
    assert sweep.execution.maximum_hold_seconds == 21_600
    assert sweep.maximum_entry_delay_seconds == 90
    donchian = providers["test_channel_short_15m"]
    assert donchian.execution.stop_policy == "fixed_bps"
    assert donchian.execution.maximum_hold_seconds == 259_200
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
    "sweep on a market it does not compute": (
        _refused("liquidity_sweep", symbols=["SOL"]),
        "BTC-only",
    ),
    "sweep without the long side it emits": (
        _refused("liquidity_sweep", sides=["short"]),
        "emitted long",
    ),
    "sweep with a structural stop it has no anchor for": (
        _refused("liquidity_sweep", execution=_structural(20.0, 80.0, 3_600)),
        "fixed stop",
    ),
    "sweep on a mislabeled signal clock": (
        _refused("liquidity_sweep", timeframe="15m"),
        "1h",
    ),
    "sweep without opposite-entry close": (
        _refused("liquidity_sweep", position_policy="flat_entry_only"),
        "opposite-entry close",
    ),
    "hourly Donchian without a side it emits": (
        _refused("hourly_donchian", sides=["long"]),
        "both emitted sides",
    ),
    "hourly Donchian on an uncomputed market": (
        _refused("hourly_donchian", symbols=["xyz:DDD"]),
        "qualified symbols",
    ),
    "LTC Donchian on another market": (
        _refused("ltc_donchian", symbols=["SOL"]),
        "LTC-only",
    ),
    "directional range with an absolute target": (
        _refused(
            "eth_range_long",
            execution=_fixed(90.0, 3_600, target_policy="absolute_anchor"),
        ),
        "no absolute target",
    ),
    "BBB cash-open without its target anchor": (
        _refused("bbb_cash_open_observed", execution=_fixed(120.0, 7_200)),
        "absolute target anchor",
    ),
    "research observer with execution authority": (
        _refused("research_observer", execution_symbols=["xyz:FFF"]),
        "execution-disabled",
    ),
    "CCC fresh15 on a journal it does not have": (
        _refused("fresh15_ccc_both_sides", symbols=["xyz:AAA"]),
        "symbols within",
    ),
    "HYPE native on another market": (
        _refused("hype_native", symbols=["SOL"]),
        "HYPE-only",
    ),
    "ETH transfer without a side it emits": (
        _refused("eth_transfer", sides=["long"]),
        "both emitted sides",
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
