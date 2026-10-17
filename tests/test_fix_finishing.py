"""Engine follow-ups from the integration review, one regression test (or more) each.

1. ``tune strategy`` honours ``--pin-cache`` / ``--max-cache-age-hours`` like
   every other history-loading command.
2. Trade direction comes from the builder's tag through ``normalize_direction``
   (autotune, Nautilus signal adapter), never a ``"short"`` substring rule.
3. Exporters write ``meta.conviction`` and, for symbols outside the Nautilus
   built-in table, ``meta.instrument`` from cached venue metadata (or a note).
4. Autotune sampling uses the single venue-cap table in ``sweep.sizing``.
5. 0xArchive symbol validation accepts ``kPEPE`` and HIP-3 ``dex:ASSET``.
6. Autotune boards and results record the requested and the used fee model.
7. Nautilus precompute no longer computes or probes an unused trail distance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.cli import main
from hypervector.data.provenance import summarize_provenance
from hypervector.data.sources import fixture_ohlcv
from hypervector.strategies import register_all_strategies
from hypervector.strategies.registry import _REGISTRY, StrategySpec
from hypervector.sweep import autotune

_STUB_METRICS = {
    "trade_count": 1,
    "sharpe": 0.5,
    "net_pnl": 1.0,
    "total_return_pct": 0.01,
    "max_drawdown": -0.01,
}


class HistoryBoundary(Exception):
    """Stop a command once the history request has been observed."""


def _bars(n_bars: int = 180) -> pd.DataFrame:
    return fixture_ohlcv(n_bars=n_bars, drift=5.0, wave_period=30, source="hl")


def _offline_history(monkeypatch: pytest.MonkeyPatch, bars: pd.DataFrame) -> list[dict]:
    calls: list[dict] = []

    def fake_load(_root: object, **kwargs: object):
        calls.append(kwargs)
        return bars, summarize_provenance(bars)

    monkeypatch.setattr(autotune, "load_research_history", fake_load)
    return calls


def _recording_metrics(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    seen: list[dict] = []

    def calculate(*_args: object, **kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return dict(_STUB_METRICS)

    monkeypatch.setattr(autotune, "compute_trial_metrics", calculate)
    return seen


# --- 1. tune strategy cache flags --------------------------------------------------------------


def test_tune_strategy_cache_flags_reach_the_history_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []

    def capture(_root: object, **kwargs: object) -> None:
        calls.append(kwargs)
        raise HistoryBoundary

    monkeypatch.setattr("hypervector.sweep.autotune.load_research_history", capture)
    base = ["--data-root", str(tmp_path), "tune", "strategy", "--n-trials", "2"]
    with pytest.raises(HistoryBoundary):
        main(base)
    assert "max_cache_age" not in calls[-1]  # neither flag: the loader default
    with pytest.raises(HistoryBoundary):
        main([*base, "--pin-cache"])
    assert calls[-1]["max_cache_age"] is None
    with pytest.raises(HistoryBoundary):
        main([*base, "--max-cache-age-hours", "6"])
    assert calls[-1]["max_cache_age"] == pd.Timedelta(hours=6)

    loads = len(calls)
    assert main([*base, "--pin-cache", "--max-cache-age-hours", "6"]) == 2
    assert main([*base, "--pin-cache", "--refresh"]) == 2
    with pytest.raises(SystemExit) as refused:  # argparse type check
        main([*base, "--max-cache-age-hours", "0"])
    assert refused.value.code == 2
    assert len(calls) == loads  # refused before any load


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pin_cache": True, "max_cache_age_hours": 6.0},
        {"pin_cache": True, "force_refresh": True},
        {"max_cache_age_hours": 0.0},
        {"max_cache_age_hours": float("nan")},
    ],
)
def test_run_autotune_refuses_contradictory_cache_policy_before_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kwargs: dict
) -> None:
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_a, **_k: pytest.fail("history read before cache policy check"),
    )
    with pytest.raises(ValueError, match="pin_cache|max_cache_age_hours"):
        autotune.run_autotune(data_root=tmp_path, **kwargs)


def test_board_records_the_cache_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _offline_history(monkeypatch, _bars())
    _recording_metrics(monkeypatch)
    result = autotune.run_autotune(
        data_root=tmp_path, n_trials=2, no_export=True, pin_cache=True
    )
    assert calls[-1]["max_cache_age"] is None
    board = json.loads(result.board_path.read_text())
    assert board["cache_policy"] == {
        "mode": "pinned",
        "pin_cache": True,
        "max_cache_age_hours": None,
        "force_refresh": False,
    }


# --- 2. direction via normalize_direction ------------------------------------------------------


def _register(monkeypatch: pytest.MonkeyPatch, name: str, tag: str) -> None:
    register_all_strategies()

    def build(df: pd.DataFrame, **_kwargs: object):
        flags = pd.Series(False, index=df.index)
        flags.iloc[::20] = True
        return flags, flags.shift(5, fill_value=False), tag

    monkeypatch.setitem(_REGISTRY, name, StrategySpec(name, "uptrend", {}, build))


def test_autotune_uses_the_builder_tag_not_a_name_substring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """'shortcut_breakout_long' trades long; impulse-style tags are normalised."""
    _offline_history(monkeypatch, _bars())
    seen = _recording_metrics(monkeypatch)
    _register(monkeypatch, "shortcut_breakout_long", "long")
    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name="shortcut_breakout_long",
        n_trials=2,
        no_export=True,
    )
    assert {call["direction"] for call in seen} == {"long"}
    assert json.loads(result.board_path.read_text())["direction"] == "long"

    seen.clear()
    _register(monkeypatch, "fix_impulse_tagged", "impulse_1m_short")
    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name="fix_impulse_tagged",
        n_trials=2,
        no_export=True,
    )
    assert {call["direction"] for call in seen} == {"short"}
    assert json.loads(result.board_path.read_text())["direction"] == "short"


def test_autotune_unknown_direction_tag_is_a_technical_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offline_history(monkeypatch, _bars())
    seen = _recording_metrics(monkeypatch)
    _register(monkeypatch, "fix_bidirectional", "bidirectional")
    with pytest.raises(RuntimeError, match="no successful trials"):
        autotune.run_autotune(
            data_root=tmp_path,
            strategy_name="fix_bidirectional",
            n_trials=2,
            no_export=True,
        )
    assert seen == []  # never measured as a guessed 'long'


def test_trial_evaluator_refuses_a_tag_that_contradicts_the_expected_direction() -> (
    None
):
    from hypervector.sweep.autotune_evaluation import TrialEvaluator
    from hypervector.sweep.costs import resolve_cost_model

    bars = _bars(60)
    flags = pd.Series(False, index=bars.index)
    spec = StrategySpec(
        "fake", "uptrend", {}, lambda df, **_k: (flags, flags, "impulse_1m_short")
    )
    evaluator = TrialEvaluator(
        bars,
        spec,
        "long",
        resolve_cost_model("hl_base_taker"),
        False,
        lambda *a, **k: {},
    )
    evaluator.evaluate({}, {"mode": "atr", "leverage": 2.0}, 0)
    assert evaluator.trials[-1]["status"] == "error"
    assert "expected 'long'" in str(evaluator.trials[-1]["error"])


@pytest.mark.parametrize(
    ("strategy", "expected"),
    [("impulse_1m_long", "long"), ("impulse_1m_range_short", "short")],
)
def test_nautilus_signal_adapter_normalises_impulse_tags(
    strategy: str, expected: str
) -> None:
    """The actor/paper/live intent only acts on long|short; raw tags never traded."""
    from hypervector.nautilus.actor import _action_from_intent
    from hypervector.nautilus.precompute import precompute_intents
    from hypervector.nautilus.signals import (
        SignalIntent,
        last_bar_intent,
        signals_from_ohlcv,
    )

    frame = _bars(400).set_index("timestamp")[
        ["open", "high", "low", "close", "volume"]
    ]
    _, _, direction = signals_from_ohlcv(frame, strategy, {})
    assert direction == expected
    assert last_bar_intent(frame, strategy, {}).direction == expected
    exits = {"mode": "fixed_rr", "sl_pct": 0.01, "rr": 2.0, "atr_length": 14}
    assert precompute_intents(frame, strategy, {}, exits).direction == expected
    intent = SignalIntent(direction=direction, enter=True, exit=False, bar_index=0)
    assert (
        _action_from_intent(intent, is_flat=True, position_side=None)
        == f"enter_{expected}"
    )


def test_nautilus_signal_adapter_refuses_an_unknown_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hypervector.nautilus.signals import signals_from_ohlcv

    _register(monkeypatch, "fix_sideways", "sideways")
    frame = _bars(60).set_index("timestamp")
    with pytest.raises(ValueError, match="long\\|short"):
        signals_from_ohlcv(frame, "fix_sideways", {})


# --- 3. exporters: conviction and instrument metadata -------------------------------------------


def _meta(symbol: str, **extra: object) -> dict[str, object]:
    return {
        "symbol": symbol,
        "timeframe": "1m",
        "init_cash": 10_000.0,
        "tp_sl_mode": "fixed_rr",
        "exits": {
            "mode": "fixed_rr",
            "sl_pct": 0.01,
            "rr": 2.0,
            "atr_length": 14,
            "sl_atr_mult": 2.0,
            "trail_atr_mult": 2.0,
        },
        "costs": {"taker_fee": 0.00045, "slippage_bps": 1.0},
        "risk": {"risk_pct_min": 0.01, "risk_pct_max": 0.05},
        **extra,
    }


def _export(root: Path, symbol: str, **extra: object) -> dict[str, object]:
    from hypervector.export.phase2 import export_candidate

    path = export_candidate(
        root / "exports",
        run_id="fin01",
        meta=_meta(symbol, **extra),
        params={"strategy": "ma_cross_long", "fast": 5, "slow": 20},
        metrics={"net_pnl": 0.0},
        candidate_id=f"fin_{symbol.replace(':', '_')}",
        strict=True,
    )
    return json.loads((path / "meta.json").read_text())


def _cache_meta(root: Path, name: str, payload: object) -> Path:
    path = root / "cache" / "venue" / "hyperliquid" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


_UNIVERSE = {
    "universe": [
        {"name": "BTC", "szDecimals": 5, "maxLeverage": 40},
        {"name": "kPEPE", "szDecimals": 0, "maxLeverage": 10},
        {"name": "DOGE", "szDecimals": 0, "maxLeverage": 20, "price_decimals": 5},
    ]
}


def test_export_copies_cached_venue_metadata_for_a_case_sensitive_coin(
    tmp_path: Path,
) -> None:
    from hypervector.nautilus.venue_spec import resolve_venue_spec

    _cache_meta(tmp_path, "meta.json", _UNIVERSE)
    meta = _export(tmp_path, "kPEPE")
    assert meta["instrument"] == {
        "name": "kPEPE",
        "szDecimals": 0,
        "maxLeverage": 10,
        "source": "data_root:cache/venue/hyperliquid/meta.json",
    }
    assert "instrument_note" not in meta
    spec = resolve_venue_spec("kPEPE", meta)
    assert (spec.source, spec.size_decimals, spec.price_decimals) == (
        "export_meta",
        0,
        6,
    )
    assert spec.venue_max_leverage == 10.0

    doge = _export(tmp_path, "DOGE")
    assert doge["instrument"]["price_decimals"] == 5
    assert resolve_venue_spec("DOGE", doge).price_decimals == 5


def test_export_venue_lookup_prefers_the_exact_name_over_the_alias(
    tmp_path: Path,
) -> None:
    """hl_coin strips any 'USD' substring; an exact cached name must win first."""
    _cache_meta(
        tmp_path,
        "meta.json",
        {
            "universe": [
                {"name": "SUSDE", "szDecimals": 1, "maxLeverage": 5},
                {"name": "kPEPE", "szDecimals": 0, "maxLeverage": 10},
            ]
        },
    )
    assert _export(tmp_path, "SUSDE")["instrument"]["name"] == "SUSDE"
    assert _export(tmp_path, "kPEPE-PERP")["instrument"]["name"] == "kPEPE"


def test_export_reads_hip3_dex_meta_and_the_meta_and_asset_ctxs_shape(
    tmp_path: Path,
) -> None:
    from hypervector.nautilus.venue_spec import resolve_venue_spec

    _cache_meta(
        tmp_path,
        "meta_xyz.json",
        [{"universe": [{"name": "TSLA", "szDecimals": 3, "maxLeverage": 10}]}, [{}]],
    )
    meta = _export(tmp_path, "xyz:TSLA")
    assert meta["instrument"]["name"] == "xyz:TSLA"
    assert meta["instrument"]["source"].endswith("meta_xyz.json")
    spec = resolve_venue_spec("xyz:TSLA", meta)
    assert (spec.size_decimals, spec.venue_max_leverage) == (3, 10.0)


def test_export_without_cached_metadata_explains_how_to_supply_it(
    tmp_path: Path,
) -> None:
    from hypervector.nautilus.errors import UnsupportedNautilusSymbol
    from hypervector.nautilus.venue_spec import resolve_venue_spec

    meta = _export(tmp_path, "kPEPE")
    assert "instrument" not in meta
    note = str(meta["instrument_note"])
    assert "meta.instrument" in note and "szDecimals" in note and "kPEPE" in note
    assert str(tmp_path / "cache" / "venue" / "hyperliquid" / "meta.json") in note
    with pytest.raises(UnsupportedNautilusSymbol):
        resolve_venue_spec("kPEPE", meta)

    _cache_meta(
        tmp_path, "meta.json", {"universe": [{"name": "KPEPE", "szDecimals": 0}]}
    )
    meta = _export(tmp_path, "kPEPE")  # exact names only; no case folding
    assert "instrument" not in meta and "no universe entry named 'kPEPE'" in str(
        meta["instrument_note"]
    )


def test_export_leaves_builtin_symbols_and_caller_instrument_alone(
    tmp_path: Path,
) -> None:
    _cache_meta(tmp_path, "meta.json", _UNIVERSE)
    for symbol in ("BTC", "ETH", "SOL", "HYPE"):
        meta = _export(tmp_path, symbol)
        assert "instrument" not in meta and "instrument_note" not in meta
    own = {"szDecimals": 2, "maxLeverage": 5}
    assert _export(tmp_path, "kPEPE", instrument=own)["instrument"] == own


def test_autotune_export_writes_conviction_fee_models_and_instrument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cache_meta(tmp_path, "meta.json", _UNIVERSE)
    _offline_history(monkeypatch, _bars())
    seen = _recording_metrics(monkeypatch)
    result = autotune.run_autotune(
        data_root=tmp_path, symbol="kPEPE", strategy_name="ma_cross_long", n_trials=2
    )
    assert result.export_dir is not None
    meta = json.loads((Path(result.export_dir) / "meta.json").read_text())
    # The conviction the trials were sized with (risk contract default).
    measured = {call["risk_cfg"].default_conviction for call in seen}
    assert measured == {meta["conviction"]} == {meta["risk"]["default_conviction"]}
    assert meta["fee_model"] == meta["fee_model_requested"] == "hl_base_taker"
    assert meta["instrument"]["name"] == "kPEPE"


# --- 4. single venue-cap table ------------------------------------------------------------------


def test_autotune_sampling_has_no_private_venue_cap_table() -> None:
    from hypervector.sweep import autotune_sampling, sizing

    assert not hasattr(autotune_sampling, "_VENUE_LEVERAGE_CAPS")
    assert not hasattr(autotune_sampling, "_DEFAULT_ALT_LEVERAGE_CAP")
    assert autotune_sampling.venue_leverage_cap is sizing.venue_leverage_cap
    assert autotune.venue_leverage_cap is sizing.venue_leverage_cap
    clamp = autotune_sampling._clamp_strategy_leverage
    # sizing's symbol normalisation applies (the private table missed it).
    assert clamp({"leverage": 50.0}, "BTC-PERP")["leverage"] == 40.0
    assert (
        clamp({"leverage": 50.0}, "HYPE")["leverage"]
        == sizing.VENUE_LEVERAGE_CAPS["HYPE"]
    )
    assert (
        clamp({"leverage": 50.0}, "kPEPE")["leverage"]
        == sizing.DEFAULT_ALT_LEVERAGE_CAP
    )


# --- 5. 0xArchive symbol syntax -----------------------------------------------------------------


@pytest.mark.parametrize(
    "symbol", ["BTC", "kPEPE", "kSHIB", "1000PEPE", "KAS", "xyz:TSLA", "km:US500"]
)
def test_oxa_symbol_accepts_hl_venue_identities(symbol: str) -> None:
    from hypervector.data.oxa_api import validate_symbol

    validate_symbol(symbol)


@pytest.mark.parametrize(
    "symbol",
    [
        "kpepe",
        "Kpepe",
        "kPEPe",
        "btc",
        "BtC",
        "k",
        "kk",
        "k-PEPE",
        "XYZ:TSLA",
        "xyz:tsla",
        "xyz:",
        ":TSLA",
        "a:b:C",
        "BTC ",
        " BTC",
        "../BTC",
        "BTC/USD",
        "",
    ],
)
def test_oxa_symbol_rejects_everything_else(symbol: str) -> None:
    from hypervector.data.oxa_api import validate_symbol

    with pytest.raises(ValueError):
        validate_symbol(symbol)


def test_oxa_market_family_still_matches_symbol_syntax() -> None:
    from hypervector.data.oxa_api import validate_market_symbol

    validate_market_symbol("kPEPE", "core")
    validate_market_symbol("xyz:TSLA", "hip3")
    with pytest.raises(ValueError, match="uppercase Hyperliquid asset"):
        validate_market_symbol("xyz:TSLA", "core")
    with pytest.raises(ValueError):
        validate_market_symbol("kPEPE", "hip3")


# --- 6. fee model requested vs used -------------------------------------------------------------


def test_board_and_result_record_a_fee_model_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offline_history(monkeypatch, _bars())
    _recording_metrics(monkeypatch)
    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name="hypervelocity_1m_scalper_long",
        fee_model="hl_base_taker",
        n_trials=1,
    )
    assert (result.fee_model_requested, result.fee_model_used) == (
        "hl_base_taker",
        "hl_maker",
    )
    board = json.loads(result.board_path.read_text())
    assert board["fee_model_requested"] == "hl_base_taker"
    assert board["fee_model_used"] == board["fee_model"] == "hl_maker"
    assert board["fee_model_overridden"] is True
    assert any("hl_base_taker" in w and "hl_maker" in w for w in board["warnings"])
    meta = json.loads((Path(result.export_dir) / "meta.json").read_text())
    assert (meta["fee_model_requested"], meta["fee_model"]) == (
        "hl_base_taker",
        "hl_maker",
    )


def test_board_records_the_fee_model_without_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offline_history(monkeypatch, _bars())
    _recording_metrics(monkeypatch)
    result = autotune.run_autotune(
        data_root=tmp_path, fee_model="hl_maker", n_trials=1, no_export=True
    )
    board = json.loads(result.board_path.read_text())
    assert board["fee_model_requested"] == board["fee_model_used"] == "hl_maker"
    assert board["fee_model_overridden"] is False
    assert not any("strategy contract override" in w for w in board["warnings"])
    assert (result.fee_model_requested, result.fee_model_used) == (
        "hl_maker",
        "hl_maker",
    )


def test_tune_strategy_cli_reports_both_fee_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _offline_history(monkeypatch, _bars())
    _recording_metrics(monkeypatch)
    argv = [
        "--data-root",
        str(tmp_path),
        "tune",
        "strategy",
        "--strategy",
        "hypervelocity_1m_scalper_long",
        "--n-trials",
        "1",
        "--no-export",
    ]
    assert main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["fee_model_requested"], out["fee_model_used"]) == (
        "hl_base_taker",
        "hl_maker",
    )


# --- 7. precompute: no unused trail distance ----------------------------------------------------


def test_precompute_has_no_trail_distance_and_still_probes_trail_stops() -> None:
    import dataclasses

    from hypervector.nautilus import precompute

    fields = {field.name for field in dataclasses.fields(precompute.PrecomputedIntents)}
    assert "trail_dist" not in fields
    assert not hasattr(precompute, "atr_indicator")

    frame = _bars(400).set_index("timestamp")[
        ["open", "high", "low", "close", "volume"]
    ]
    exits = {"mode": "trail", "sl_pct": 0.01, "trail_atr_mult": 2.0, "atr_length": 14}
    intents = precompute.precompute_intents(
        frame, "ma_cross_long", {"fast": 5, "slow": 20}, exits
    )
    params = {"fast": 5, "slow": 20}
    probe = precompute.probe_precomputed(
        intents, frame, "ma_cross_long", params, exits, max_lookback=1_000
    )
    assert probe["sampled"] > 0 and probe["mismatches"] == 0
    stop, tp = intents.stop_tp(len(intents) - 1)
    assert tp is None and stop > 0.0  # trail distance lives in the stop fraction
    # A window too short for the ATR warmup still shows up, as a stop mismatch.
    short = precompute.probe_precomputed(
        intents, frame, "ma_cross_long", params, exits, max_lookback=200
    )
    assert short["mismatches"] > 0
    assert all(
        problem.startswith("stop/tp") for problem in short["first_mismatch"]["problems"]
    )
