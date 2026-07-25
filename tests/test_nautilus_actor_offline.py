"""Offline tests for HypervectorStrategy config + buffer/intent helpers.

No BacktestEngine.run / network — pure config construction and decision helpers.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from hypervector.export.phase2 import export_candidate
from hypervector.nautilus.actor import (
    DEFAULT_MAX_LOOKBACK,
    HypervectorStrategy,
    HypervectorStrategyConfig,
    _action_from_intent,
    _append_bar_record,
    _bar_ohlcv_record,
    _bars_to_ohlcv_df,
    _stop_tp_fracs,
    _uses_strategy_exits_only,
    config_from_loadout,
)
from hypervector.nautilus.load_export import StrategyLoadout, load_strategy_loadout
from hypervector.nautilus.signals import SignalIntent
from hypervector.strategies import register_all_strategies


def _write_strict_export(root: Path) -> Path:
    return export_candidate(
        root / "exports",
        run_id="act01",
        meta={
            "symbol": "BTC",
            "timeframe": "1m",
            "track": "uptrend",
            "lookback_days": 30,
            "init_cash": 10_000.0,
            "tp_sl_mode": "fixed_rr",
            "exits": {
                "mode": "fixed_rr",
                "sl_pct": 0.01,
                "rr": 2.0,
                "atr_length": 14,
                "sl_atr_mult": 1.5,
                "trail_atr_mult": 2.0,
            },
            "costs": {
                "taker_fee": 0.00035,
                "slippage_bps": 2.0,
                "funding_rate_8h": 0.0001,
                "minutes_per_funding": 480,
            },
            "risk": {
                "risk_pct_min": 0.01,
                "risk_pct_max": 0.05,
                "default_conviction": 0.5,
                "max_size_frac": 1.0,
            },
            "data_provenance": {"sources": {"fixture": 200}},
        },
        params={
            "strategy": "crown_stack_long",
            "bbwp_lookback": 100,
            "bbwp_threshold": 20.0,
            "exit_mode": "fixed_rr",
        },
        metrics={
            "net_pnl": 100.0,
            "total_return_pct": 1.0,
            "sharpe": 0.5,
            "trade_count": 5,
        },
        candidate_id="actor_crown",
        strict=True,
    )


def _synthetic_bar(
    *,
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 1.0,
    ts_ns: int = 1_000_000_000,
    bar_type: str = "BTC-PERP.HYPERLIQUID-1-MINUTE-LAST-EXTERNAL",
) -> Bar:
    return Bar(
        bar_type=BarType.from_str(bar_type),
        open=Price.from_str(f"{open_:.1f}"),
        high=Price.from_str(f"{high:.1f}"),
        low=Price.from_str(f"{low:.1f}"),
        close=Price.from_str(f"{close:.1f}"),
        volume=Quantity.from_str(f"{volume:.3f}"),
        ts_event=ts_ns,
        ts_init=ts_ns,
    )


def test_strategy_config_from_loadout(tmp_path: Path):
    export_dir = _write_strict_export(tmp_path)
    loadout = load_strategy_loadout(export_dir, strict=True)
    bar_type = "BTC-PERP.HYPERLIQUID-1-MINUTE-LAST-EXTERNAL"
    cfg = config_from_loadout(loadout, bar_type=bar_type)

    assert isinstance(cfg, HypervectorStrategyConfig)
    assert cfg.strategy_name == loadout.strategy_name
    assert cfg.exits["mode"] == loadout.exit_mode
    assert cfg.bar_type == bar_type
    assert cfg.instrument_id == "BTC-PERP.HYPERLIQUID"
    assert cfg.params["bbwp_lookback"] == 100
    assert cfg.risk is not None
    assert cfg.risk["risk_pct_min"] == 0.01
    assert cfg.costs is not None
    assert cfg.costs["taker_fee"] == 0.00035
    assert cfg.conviction == 0.5
    assert cfg.loadout_summary["strategy_name"] == "crown_stack_long"
    assert cfg.loadout_summary["exit_mode"] == "fixed_rr"


def test_config_from_loadout_overrides_instrument_and_conviction():
    loadout = StrategyLoadout(
        strategy_name="crown_stack_short",
        role="downtrend",
        params={"bbwp_lookback": 50},
        meta={},
        costs=None,
        risk={"risk_pct_min": 0.02, "risk_pct_max": 0.04},
        exit_mode="atr",
        exits={"mode": "atr", "sl_atr_mult": 1.75, "rr": 2.5},
        export_dir=Path("/tmp"),
    )
    cfg = config_from_loadout(
        loadout,
        bar_type="ETH-PERP.SIM-5-MINUTE-LAST-EXTERNAL",
        instrument_id="ETH-PERP.SIM",
        conviction=0.9,
    )
    assert cfg.instrument_id == "ETH-PERP.SIM"
    assert cfg.conviction == 0.9
    assert cfg.exits["mode"] == "atr"
    assert cfg.exits["sl_atr_mult"] == 1.75


def test_config_fills_exits_mode_from_exit_mode_when_exits_sparse():
    loadout = StrategyLoadout(
        strategy_name="crown_stack_long",
        role=None,
        params={},
        meta={},
        costs=None,
        risk=None,
        exit_mode="fixed_rr",
        exits={"sl_pct": 0.02, "rr": 3.0},
        export_dir=Path("/tmp"),
    )
    cfg = config_from_loadout(
        loadout, bar_type="BTC-PERP.HYPERLIQUID-1-MINUTE-LAST-EXTERNAL"
    )
    assert cfg.exits["mode"] == "fixed_rr"
    assert cfg.exits["sl_pct"] == 0.02


def test_hypervelocity_uses_only_strategy_emitted_tp_exit() -> None:
    assert _uses_strategy_exits_only("hypervelocity_1m_scalper_long") is True
    assert _uses_strategy_exits_only("crown_stack_long") is False


def test_bar_ohlcv_record_and_buffer_to_df():
    bar = _synthetic_bar(
        open_=123.0,
        high=124.0,
        low=122.0,
        close=123.4,
        ts_ns=2_000_000_000,
    )
    rec = _bar_ohlcv_record(bar)
    assert rec["close"] == pytest.approx(123.4)
    assert rec["open"] == pytest.approx(123.0)
    assert isinstance(rec["timestamp"], pd.Timestamp)

    buf: list[dict] = []
    for i in range(3):
        px = 100.0 + i
        b = _synthetic_bar(
            open_=px,
            high=px + 1.0,
            low=px - 1.0,
            close=px,
            ts_ns=(i + 1) * 60_000_000_000,
        )
        _append_bar_record(buf, _bar_ohlcv_record(b), max_lookback=DEFAULT_MAX_LOOKBACK)
    assert len(buf) == 3

    df = _bars_to_ohlcv_df(buf)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert df["close"].iloc[-1] == pytest.approx(102.0)


def test_append_bar_record_rolls_at_max_lookback():
    buf: list[dict] = []
    for i in range(5):
        rec = {
            "timestamp": pd.Timestamp(i, unit="s", tz="UTC"),
            "open": float(i),
            "high": float(i),
            "low": float(i),
            "close": float(i),
            "volume": 1.0,
        }
        _append_bar_record(buf, rec, max_lookback=3)
    assert len(buf) == 3
    assert [r["close"] for r in buf] == [2.0, 3.0, 4.0]


def test_action_from_intent_enter_when_flat():
    intent = SignalIntent(direction="long", enter=True, exit=False, bar_index=0)
    assert _action_from_intent(intent, is_flat=True, position_side=None) == "enter_long"

    intent_s = SignalIntent(direction="short", enter=True, exit=False, bar_index=0)
    assert (
        _action_from_intent(intent_s, is_flat=True, position_side=None) == "enter_short"
    )


def test_action_from_intent_hold_when_flat_no_enter():
    intent = SignalIntent(direction="long", enter=False, exit=False, bar_index=0)
    assert _action_from_intent(intent, is_flat=True, position_side=None) == "hold"


def test_action_from_intent_close_on_exit_or_opposite():
    exit_intent = SignalIntent(direction="long", enter=False, exit=True, bar_index=1)
    assert (
        _action_from_intent(exit_intent, is_flat=False, position_side="long") == "close"
    )

    opposite = SignalIntent(direction="short", enter=True, exit=False, bar_index=2)
    assert _action_from_intent(opposite, is_flat=False, position_side="long") == "close"

    same = SignalIntent(direction="long", enter=True, exit=False, bar_index=3)
    assert _action_from_intent(same, is_flat=False, position_side="long") == "hold"


def test_stop_tp_fracs_fixed_rr():
    exits = {"mode": "fixed_rr", "sl_pct": 0.01, "rr": 2.0}
    df = pd.DataFrame(
        {
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.0],
            "volume": [1.0],
        }
    )
    stop_frac, tp_frac = _stop_tp_fracs(df, exits)
    assert stop_frac == pytest.approx(0.01)
    assert tp_frac == pytest.approx(0.02)


def test_strategy_instantiates_and_does_not_touch_signals_parquet(tmp_path: Path):
    """Strategy constructs offline; decision path never opens signals.parquet."""
    export_dir = _write_strict_export(tmp_path)
    # Deliberately no signals.parquet written by export_candidate unless provided.
    assert not (export_dir / "signals.parquet").exists()

    loadout = load_strategy_loadout(export_dir, strict=True)
    cfg = config_from_loadout(
        loadout,
        bar_type="BTC-PERP.HYPERLIQUID-1-MINUTE-LAST-EXTERNAL",
    )
    strategy = HypervectorStrategy(config=cfg)
    assert strategy.config.strategy_name == "crown_stack_long"
    assert strategy.execution_mode == "phase2_historical"
    assert strategy.max_lookback == DEFAULT_MAX_LOOKBACK


def test_buffer_intent_path_uses_registry_not_parquet(tmp_path: Path):
    """last_bar_intent on rolling buffer works without any signal file."""
    register_all_strategies()
    export_dir = _write_strict_export(tmp_path)
    loadout = load_strategy_loadout(export_dir, strict=True)
    cfg = config_from_loadout(
        loadout,
        bar_type="BTC-PERP.HYPERLIQUID-1-MINUTE-LAST-EXTERNAL",
    )
    strategy = HypervectorStrategy(config=cfg)

    # Build enough synthetic bars for crown_stack lookbacks (bbwp_lookback=100).
    for i in range(250):
        px = 100.0 + (i % 20) * 0.5
        bar = _synthetic_bar(
            open_=px,
            high=px + 1.0,
            low=px - 1.0,
            close=px + 0.2,
            ts_ns=(i + 1) * 60_000_000_000,
        )
        strategy._append_bar(bar)

    assert len(strategy._bar_buffer) == 250
    intent = strategy._intent_from_buffer()
    assert intent.direction in ("long", "short", "flat")
    assert isinstance(intent.enter, bool)
    assert isinstance(intent.exit, bool)
    # Still no signals file involved
    assert not (export_dir / "signals.parquet").exists()
