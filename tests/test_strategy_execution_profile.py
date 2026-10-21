"""Declared strategy execution options and the strategy-family registration point.

Each option must reach the behavior a strategy-name switch used to select:
fixed sizing, strategy-managed exits, post-only entries, declared leverage and
a declared fee model. A plain strategy keeps the standard path.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

from hypervector.cli import main
from hypervector.data.sources import fixture_ohlcv
from hypervector.strategies import register_all_strategies
from hypervector.strategies import STRATEGY_FAMILY_MODULES
from hypervector.strategies.registry import (
    STANDARD_EXECUTION,
    STRATEGY_MANAGED_EXIT_MODE,
    ExecutionProfile,
    StrategySpec,
    UnknownStrategy,
    execution_profile,
    get_strategy,
    register,
)
from synthetic_strategies import (
    MANAGED_EXECUTION,
    MANAGED_LONG,
    SYNTHETIC_LONG,
    sma_cross_long,
)


# --- the profile ----------------------------------------------------------------------


def test_standard_profile_is_the_default_for_every_spec() -> None:
    spec = StrategySpec("plain", "uptrend", {}, sma_cross_long)
    assert spec.execution == STANDARD_EXECUTION
    assert spec.execution.standard
    assert spec.execution.fixed_notional_fraction is None
    assert spec.execution.exit_dict() is None
    assert execution_profile("not_registered_anywhere") is STANDARD_EXECUTION
    assert execution_profile(None) is STANDARD_EXECUTION


def test_declared_profile_reports_its_fixed_allocation() -> None:
    assert MANAGED_EXECUTION.fixed_sizing
    assert MANAGED_EXECUTION.fixed_notional_fraction == pytest.approx(5.0)
    assert MANAGED_EXECUTION.exit_dict() == {
        "mode": STRATEGY_MANAGED_EXIT_MODE,
        "stop": None,
    }
    assert execution_profile(MANAGED_LONG) == MANAGED_EXECUTION
    payload = MANAGED_EXECUTION.to_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert payload["fixed_notional_fraction"] == pytest.approx(5.0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"fixed_margin_fraction": 0.5}, "requires a declared leverage"),
        ({"fixed_margin_fraction": 1.5, "leverage": 2.0}, "<= 1"),
        ({"fixed_margin_fraction": 0.0, "leverage": 2.0}, "> 0"),
        ({"leverage": float("nan")}, "finite"),
        ({"leverage": True}, "number"),
        ({"entry_ttl_seconds": 0.0}, "> 0"),
        ({"strategy_managed_exits": True}, "requires fixed sizing"),
        ({"post_only_entries": 1}, "bool"),
        ({"fee_model": " "}, "fee_model"),
    ],
)
def test_invalid_declarations_are_refused(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ExecutionProfile(**kwargs)


def test_register_requires_an_execution_profile() -> None:
    spec = StrategySpec("bad", "uptrend", {}, sma_cross_long)
    spec.execution = {"post_only_entries": True}  # type: ignore[assignment]
    with pytest.raises(TypeError, match="ExecutionProfile"):
        register(spec)


# --- registration point -------------------------------------------------------------------


def test_no_strategy_family_is_built_in() -> None:
    assert STRATEGY_FAMILY_MODULES == ()


def test_register_all_strategies_imports_each_listed_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    family = types.ModuleType("fake_strategy_family")
    calls: list[str] = []

    def register_family() -> None:
        calls.append("registered")
        register(StrategySpec("family_long", "uptrend", {}, sma_cross_long))

    family.register_family = register_family  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_strategy_family", family)
    monkeypatch.setattr(
        "hypervector.strategies.STRATEGY_FAMILY_MODULES", ("fake_strategy_family",)
    )

    register_all_strategies()
    register_all_strategies()

    assert calls == ["registered", "registered"]
    assert get_strategy("family_long").role == "uptrend"


def test_a_family_without_register_family_is_a_technical_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "empty_family", types.ModuleType("empty_family"))
    monkeypatch.setattr("hypervector.strategies.STRATEGY_FAMILY_MODULES", ("empty_family",))
    with pytest.raises(TypeError, match="register_family"):
        register_all_strategies()


def test_unknown_strategy_names_the_registered_ones_and_the_registration_point() -> None:
    with pytest.raises(UnknownStrategy) as excinfo:
        get_strategy("no_such_strategy")
    text = str(excinfo.value)
    assert "unknown strategy: no_such_strategy" in text
    assert SYNTHETIC_LONG in text
    assert "STRATEGY_FAMILY_MODULES" in text


@pytest.mark.parametrize(
    "command",
    [
        ["backtest", "run"],
        ["backtest", "sweep", "--track", "uptrend"],
        ["tune", "strategy"],
    ],
)
@pytest.mark.parametrize("strategy", [None, "no_such_strategy"])
def test_research_commands_refuse_a_missing_or_unknown_strategy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
    strategy: str | None,
) -> None:
    monkeypatch.setattr(
        "hypervector.data.pipeline.load_research_history",
        lambda *_a, **_k: pytest.fail("history loaded before the strategy check"),
    )
    argv = ["--data-root", str(tmp_path / "data"), *command]
    if strategy is not None:
        argv += ["--strategy", strategy]
    assert main(argv) == 2
    error = json.loads(capsys.readouterr().err)["error"]
    assert "STRATEGY_FAMILY_MODULES" in error
    assert ("no strategy given" in error) is (strategy is None)


# --- research engines read the declared options -------------------------------------


def _managed_metrics(name: str) -> dict[str, object]:
    from hypervector.sweep.search import run_grid_search

    df = fixture_ohlcv(n_bars=600, drift=3.0, wave_period=40)
    [best, *_] = run_grid_search(
        df, get_strategy(name), param_grid={"fast": [5], "slow": [20]}
    )
    assert best.status == "ok", best.error
    return best.metrics


def test_grid_search_applies_fixed_sizing_and_strategy_managed_exits() -> None:
    managed = _managed_metrics(MANAGED_LONG)
    standard = _managed_metrics(SYNTHETIC_LONG)

    assert managed["strategy_managed_exits"] is True
    assert managed["position_notional_fraction"] == pytest.approx(5.0)
    assert standard["strategy_managed_exits"] is False
    assert standard["position_notional_fraction"] is None


def test_backtest_run_applies_the_declared_options(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, object]] = []
    bars = fixture_ohlcv(n_bars=200, drift=3.0, wave_period=40)
    monkeypatch.setattr(
        "hypervector.commands.backtest._load_bars", lambda _args: (bars, {})
    )

    from hypervector.sweep import metrics

    real = metrics.compute_trial_metrics

    def spy(*args: object, **kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(metrics, "compute_trial_metrics", spy)
    for strategy in (MANAGED_LONG, SYNTHETIC_LONG):
        argv = ["--data-root", str(tmp_path), "backtest", "run", "--strategy", strategy]
        assert main(argv) == 0
    capsys.readouterr()

    managed, standard = seen
    assert managed["fixed_notional_fraction"] == pytest.approx(5.0)
    assert managed["fixed_margin_fraction"] == pytest.approx(0.5)
    assert managed["strategy_managed_exits"] is True
    assert standard["fixed_notional_fraction"] is None
    assert standard["strategy_managed_exits"] is False


# --- bundles, Nautilus and order intents ------------------------------------------------


def _bundle(root: Path, strategy: str, *, mode: str) -> Path:
    from hypervector.export.phase2 import export_candidate

    exits = (
        {"mode": mode, "stop": None}
        if mode == STRATEGY_MANAGED_EXIT_MODE
        else {
            "mode": mode,
            "sl_pct": 0.01,
            "rr": 2.0,
            "atr_length": 14,
            "sl_atr_mult": 1.5,
            "trail_atr_mult": 2.0,
        }
    )
    return export_candidate(
        root / "exports",
        run_id="declared",
        meta={
            "symbol": "BTC",
            "timeframe": "1m",
            "track": "uptrend",
            "lookback_days": 30,
            "init_cash": 10_000.0,
            "tp_sl_mode": mode,
            "exits": exits,
            "costs": {"taker_fee": 0.00045, "slippage_bps": 1.0},
            "risk": {"risk_pct_min": 0.5, "risk_pct_max": 0.5, "max_size_frac": 5.0},
        },
        params={"strategy": strategy, "role": "uptrend", "exit_mode": mode},
        metrics={"net_pnl": 1.0, "total_return_pct": 0.01, "sharpe": 0.1, "trade_count": 1},
        candidate_id=f"cand_{strategy}",
        strict=True,
    )


def test_strategy_managed_bundles_are_valid_only_for_declaring_strategies(
    tmp_path: Path,
) -> None:
    from hypervector.export.schema import (
        STRATEGY_MANAGED,
        ExportSchemaError,
        validate_export_dir,
    )

    assert STRATEGY_MANAGED == STRATEGY_MANAGED_EXIT_MODE
    managed = _bundle(tmp_path / "a", MANAGED_LONG, mode=STRATEGY_MANAGED)
    assert validate_export_dir(managed, strict=True)["tp_sl_mode"] == STRATEGY_MANAGED
    with pytest.raises(ExportSchemaError, match="declares strategy-managed exits"):
        _bundle(tmp_path / "b", SYNTHETIC_LONG, mode=STRATEGY_MANAGED)


def test_nautilus_actor_skips_brackets_and_trail_for_strategy_managed_exits() -> None:
    from hypervector.nautilus.actor import _uses_strategy_exits_only

    assert _uses_strategy_exits_only(MANAGED_LONG) is True
    assert _uses_strategy_exits_only(SYNTHETIC_LONG) is False


def test_shadow_intents_follow_the_declared_entry_order_type() -> None:
    from hypervector.paper.order_intent import shadow_order_intent

    def intent(strategy: str, action: str) -> dict[str, object]:
        return shadow_order_intent(
            symbol="BTC",
            strategy_name=strategy,
            side="buy",
            qty=1.0,
            mark_px=100.0,
            action=action,
        )

    for action in ("enter_long", "submit_entry", "cancel_entry"):
        declared = intent(MANAGED_LONG, action)
        assert (declared["order_type"], declared["time_in_force"]) == (
            "limit",
            "post_only",
        )
        assert declared["limit_px"] == 100.0
    close = intent(MANAGED_LONG, "close")
    assert (close["order_type"], close["time_in_force"], close["reduce_only"]) == (
        "market",
        "ioc",
        True,
    )
    standard = intent(SYNTHETIC_LONG, "enter_long")
    assert (standard["order_type"], standard["time_in_force"]) == ("market", "ioc")
    assert standard["limit_px"] is None


def test_canonical_regime_output_carries_no_execution_policy() -> None:
    from hypervector.regime.ultimate import detect_ultimate_regime

    bars = fixture_ohlcv(n_bars=400, drift=2.0, wave_period=40)
    bars.index = pd.DatetimeIndex(pd.to_datetime(bars["timestamp"], utc=True))
    result = detect_ultimate_regime(bars)
    assert {"max_leverage", "dynamic_leverage", "allow_taker"}.isdisjoint(result.columns)
    assert {"long_weight", "short_weight", "regime_state"} <= set(result.columns)
