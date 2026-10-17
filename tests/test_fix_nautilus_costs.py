"""Nautilus runs use the export cost model (fees + slippage + funding) and conviction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.nautilus.costs import (
    resolve_phase2_conviction,
    resolve_phase2_costs,
)
from hypervector.nautilus.load_export import load_strategy_loadout
from hypervector.nautilus.runner import run_phase2_backtest
from nautilus_fix_support import (
    FIXTEST_ENTER_AT,
    capture_engine,
    register_fix_strategies,
    synth_ohlcv,
    write_export,
)

# Entry at bar 20 (05:00, after the 14-bar ATR warm-up), exit signal at bar 40
# (10:00): 20 bars x 15m = 5h.
_ENTRY_ROW, _EXIT_ROW = 20, 40
_ROUND_TRIP = {
    "entry_ts": "2026-01-01T05:00:00+00:00",
    "exit_ts": "2026-01-01T10:00:00+00:00",
    "direction": "long",
}
# Trail far away so only the strategy exit closes the position.
_WIDE_TRAIL = {"trail_atr_mult": 50.0}


@pytest.fixture(autouse=True)
def _strategies() -> None:
    register_fix_strategies()


def _round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **export_kw):
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params=_ROUND_TRIP,
        exit_mode="trail",
        exits=_WIDE_TRAIL,
        **export_kw,
    )
    captured = capture_engine(monkeypatch)
    df = synth_ohlcv(60)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    summary = json.loads(result.report_path.read_text())
    return result, summary, captured, df


def test_fees_are_taker_plus_slippage_per_side(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, summary, captured, df = _round_trip(tmp_path, monkeypatch)
    per_side = 0.00035 + 2.0 / 10_000  # export taker_fee + slippage_bps
    instrument = captured["instrument"]
    assert float(instrument.taker_fee) == pytest.approx(per_side)
    assert float(instrument.maker_fee) == pytest.approx(per_side)

    fills = captured["fills"]
    assert len(fills) == 2  # one entry, one signal exit
    entry, exit_ = fills
    # Market fills at the bar close (slippage is folded into the fee, not the price).
    assert entry["avg_px"] == pytest.approx(float(df["close"].iloc[_ENTRY_ROW]))
    assert exit_["avg_px"] == pytest.approx(float(df["close"].iloc[_EXIT_ROW]))
    notional = sum(f["avg_px"] * f["filled_qty"] for f in fills)
    assert result.commissions_total == pytest.approx(notional * per_side, rel=1e-6)
    cm = summary["cost_model"]
    assert cm["source"] == "export_costs"
    assert cm["taker_fee"] == pytest.approx(0.00035)
    assert cm["slippage_frac"] == pytest.approx(0.0002)
    assert cm["slippage_model"] == "folded_into_per_side_fee"


def test_funding_is_charged_hourly_on_entry_notional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, summary, captured, _df = _round_trip(tmp_path, monkeypatch)
    entry = captured["fills"][0]
    entry_notional = entry["avg_px"] * entry["filled_qty"]
    hourly = 0.0001 / 8.0  # funding_rate_8h -> hourly; legacy 480-minute period ignored
    expected = entry_notional * hourly * 5.0  # held 5 hours
    assert result.funding_cost == pytest.approx(expected, rel=1e-9)
    assert summary["cost_model"]["funding_rate_hourly"] == pytest.approx(hourly)
    # Headline PnL is mark-to-market net of fees and funding.
    assert result.pnl == pytest.approx(
        result.pnl_realized + result.pnl_unrealized - result.funding_cost
    )
    assert summary["pnl_before_funding"] == pytest.approx(
        result.pnl_realized + result.pnl_unrealized
    )


def test_realized_pnl_matches_hand_computed_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _summary, captured, _df = _round_trip(tmp_path, monkeypatch)
    entry, exit_ = captured["fills"]
    qty = entry["filled_qty"]
    gross = (exit_["avg_px"] - entry["avg_px"]) * qty
    assert result.pnl_realized == pytest.approx(
        gross - result.commissions_total, abs=1e-6
    )


def test_apply_costs_false_runs_frictionless(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, summary, captured, _df = _round_trip(
        tmp_path, monkeypatch, extra_meta={"apply_costs": False}
    )
    assert float(captured["instrument"].taker_fee) == 0.0
    assert result.commissions_total == 0.0
    assert result.funding_cost == 0.0
    assert summary["cost_model"]["source"] == "apply_costs_false"


def test_resolve_costs_variants(tmp_path: Path) -> None:
    modern = load_strategy_loadout(
        write_export(
            tmp_path / "modern",
            costs={
                "taker_fee": 0.00045,
                "maker_fee": 0.00015,
                "slippage_bps": 2.0,
                "funding_rate_1h": 0.0000125,
                "funding_rate_8h": None,
                "minutes_per_funding": 60.0,
                "slippage_frac": 0.0002,
            },
        )
    )
    costs = resolve_phase2_costs(modern)
    assert costs.instrument_taker_fee == pytest.approx(0.00065)
    assert costs.instrument_maker_fee == pytest.approx(
        0.00065
    )  # VectorBT bills taker+slip
    assert costs.funding_rate_hourly == pytest.approx(0.0000125)
    assert costs.funding_cost(10_000.0, 120.0) == pytest.approx(
        10_000.0 * 0.0000125 * 2
    )


def test_conviction_defaults_to_export_values(tmp_path: Path) -> None:
    with_meta = load_strategy_loadout(
        write_export(tmp_path / "a", extra_meta={"conviction": 0.9})
    )
    assert resolve_phase2_conviction(with_meta, None) == (0.9, "export_meta")
    assert resolve_phase2_conviction(with_meta, 0.2) == (0.2, "explicit")
    risk_only = load_strategy_loadout(
        write_export(
            tmp_path / "b",
            risk={
                "risk_pct_min": 0.01,
                "risk_pct_max": 0.05,
                "default_conviction": 0.75,
                "max_size_frac": 1.0,
            },
        )
    )
    assert resolve_phase2_conviction(risk_only, None) == (0.75, "export_risk_default")


def test_run_sizes_with_export_conviction_when_not_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    low = write_export(
        tmp_path / "low",
        strategy=FIXTEST_ENTER_AT,
        params=_ROUND_TRIP,
        exit_mode="trail",
        exits=_WIDE_TRAIL,
        extra_meta={"conviction": 0.0},
    )
    high = write_export(
        tmp_path / "high",
        strategy=FIXTEST_ENTER_AT,
        params=_ROUND_TRIP,
        exit_mode="trail",
        exits=_WIDE_TRAIL,
        extra_meta={"conviction": 1.0},
    )
    df = synth_ohlcv(60)
    qty = {}
    for name, export_dir in (("low", low), ("high", high)):
        captured = capture_engine(monkeypatch)
        result = run_phase2_backtest(
            export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
        )
        summary = json.loads(result.report_path.read_text())
        assert summary["conviction_source"] == "export_meta"
        qty[name] = captured["fills"][0]["filled_qty"]
    # risk 1% at conviction 0 vs 5% at conviction 1 -> 5x the entry size, up to
    # the 0.001 BTC size increment on each quantity.
    assert qty["low"] > 0
    assert abs(qty["high"] - 5 * qty["low"]) <= 6 * 0.0005 + 1e-12
