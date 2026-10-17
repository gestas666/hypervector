"""Final-review regressions for the Nautilus historical replay (offline, tmp_path).

* the trail stop covers the whole position when thin bars split the entry;
* entries are sized on ``init_cash`` (VectorBT's non-compounding basis);
* a bracket TP filled on a bar that also reached the SL is reported;
* USDT/USD/PERP aliases resolve to the venue coin the exporter writes;
* ``nautilus catalog`` defaults to the instrument id ``nautilus run`` uses.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from hypervector.cli import main
from hypervector.export.venue_meta import (
    VENUE_META_DIR,
    cached_instrument_meta,
    venue_coin,
    with_instrument_meta,
)
from hypervector.nautilus.actor import HypervectorStrategy
from hypervector.nautilus.runner import run_phase2_backtest
from hypervector.nautilus.venue_spec import (
    coin_for_symbol,
    research_symbol_to_instrument,
    resolve_venue_spec,
    venue_coin_name,
)
from nautilus_fix_support import (
    FIXTEST_ENTER_AT,
    FIXTEST_ENTER_EACH,
    capture_engine,
    register_fix_strategies,
    synth_ohlcv,
    write_export,
)

_ENTRY_TS = "2026-01-01T05:00:00+00:00"  # bar 20 of synth_ohlcv (15m)
_ZERO_COSTS = {
    "taker_fee": 0.0,
    "slippage_bps": 0.0,
    "funding_rate_8h": 0.0,
    "minutes_per_funding": 480,
}


@pytest.fixture(autouse=True)
def _strategies() -> None:
    register_fix_strategies()


def _frame(rows: list[tuple[float, float, float, float]], volume: float = 50.0):
    o, h, lo, c = (np.asarray(col, dtype=float) for col in zip(*rows))
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-01-01", periods=len(rows), freq="15min", tz="UTC"
            ),
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": volume,
        }
    )


def _entries(captured: dict) -> list[dict]:
    return [o for o in captured["orders"] if o["type"] == "MARKET" and not o["reduce_only"]]


# -- trail stop vs. thin bars ------------------------------------------------


@pytest.mark.parametrize("direction", ["long", "short"])
@pytest.mark.parametrize("volume", [0.2, 0.0])
def test_trail_stop_covers_the_whole_position_on_thin_bars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direction: str, volume: float
) -> None:
    """A bar offers volume/4 per level, so a 0.164 BTC entry fills in pieces;
    the stop must still protect (and close) the whole position."""
    df = synth_ohlcv(400, seed=11)
    df["volume"] = volume
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params={"entry_ts": _ENTRY_TS, "direction": direction},
        exit_mode="trail",
    )
    captured = capture_engine(monkeypatch)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    summary = json.loads(result.report_path.read_text())

    (entry,) = _entries(captured)
    stops = [o for o in captured["orders"] if o["type"] == "STOP_MARKET"]
    assert len(stops) == 1 and stops[0]["reduce_only"]
    assert stops[0]["quantity"] == pytest.approx(entry["filled_qty"])
    assert stops[0]["filled_qty"] == pytest.approx(entry["filled_qty"])
    assert summary["trail_exits"] == 1
    assert result.trade_count == 1
    assert result.open_positions_at_end == 0
    # The split entry and stop are reported as volume-capped fills.
    capped = summary["volume_capped_fills"]
    assert capped["orders"] >= 2
    assert capped["extra_cost"] > 0


def test_trail_stop_is_resized_on_the_entry_bar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The later entry piece resizes the stop at once (on_position_changed),
    not only when a later bar ratchets it."""
    monkeypatch.setattr(
        HypervectorStrategy, "_ratchet_trail", lambda self, bar, iid: None
    )
    df = synth_ohlcv(400, seed=11)
    df["volume"] = 0.2
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params={"entry_ts": _ENTRY_TS, "direction": "long"},
        exit_mode="trail",
    )
    captured = capture_engine(monkeypatch)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    (entry,) = _entries(captured)
    (stop,) = [o for o in captured["orders"] if o["type"] == "STOP_MARKET"]
    assert stop["quantity"] == pytest.approx(entry["filled_qty"])
    assert stop["filled_qty"] == pytest.approx(entry["filled_qty"])
    assert result.open_positions_at_end == 0
    assert not [o for o in captured["orders"] if o["type"] == "MARKET" and o["reduce_only"]]


def test_volume_capped_fills_are_zero_when_bars_have_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    df = synth_ohlcv(400, seed=11)
    df["volume"] = 50.0
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params={"entry_ts": _ENTRY_TS, "direction": "long"},
        exit_mode="trail",
    )
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    summary = json.loads(result.report_path.read_text())
    assert summary["volume_capped_fills"]["orders"] == 0
    assert summary["volume_capped_fills"]["extra_cost"] == 0.0


def test_trail_fill_smaller_than_the_position_flattens_the_remainder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defence in depth: if the stop ever covers less than the position, its
    fill closes the remainder at once (VectorBT exits the whole position)."""
    monkeypatch.setattr(
        HypervectorStrategy, "_trail_quantity", lambda self, order, iid: None
    )
    df = synth_ohlcv(400, seed=11)
    df["volume"] = 0.2
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params={"entry_ts": _ENTRY_TS, "direction": "long"},
        exit_mode="trail",
    )
    captured = capture_engine(monkeypatch)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    summary = json.loads(result.report_path.read_text())
    (stop,) = [o for o in captured["orders"] if o["type"] == "STOP_MARKET"]
    (entry,) = _entries(captured)
    assert stop["quantity"] < entry["filled_qty"]  # undersized without the resize
    assert summary["trail_exits"] == 1
    assert result.open_positions_at_end == 0
    closes = [
        o for o in captured["orders"] if o["type"] == "MARKET" and o["reduce_only"]
    ]
    assert len(closes) == 1
    assert closes[0]["filled_qty"] == pytest.approx(
        entry["filled_qty"] - stop["filled_qty"]
    )


# -- sizing basis --------------------------------------------------------------


def test_entries_are_sized_on_init_cash_after_a_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VectorBT notional is size x init_cash; a loss must not shrink the next entry."""
    flat = (60_000.0, 60_050.0, 59_950.0, 60_000.0)
    rows = [flat] * 31
    rows.append((60_000.0, 60_050.0, 59_000.0, 59_200.0))  # SL 59400 fills
    rows += [(59_200.0, 59_250.0, 59_150.0, 59_200.0)] * 8
    df = _frame(rows)
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_EACH,
        params={
            "entry_ts": ",".join(
                df["timestamp"].iloc[r].isoformat() for r in (30, 36)
            ),
            "direction": "long",
        },
        exit_mode="fixed_rr",
    )
    captured = capture_engine(monkeypatch)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    summary = json.loads(result.report_path.read_text())

    first, second = sorted(_entries(captured), key=lambda o: o["ts_init"])
    assert result.pnl_realized < 0  # the first trade lost
    assert first["filled_qty"] == pytest.approx(round(10_000.0 / 60_000.0, 3))
    assert second["filled_qty"] == pytest.approx(round(10_000.0 / 59_200.0, 3))
    assert summary["sizing_basis"] == "init_cash"
    assert summary["parity"]["sizing_basis"] == "init_cash"


# -- bracket same-bar SL/TP ----------------------------------------------------


@pytest.mark.parametrize(
    ("direction", "bar", "exit_type", "exit_px", "ambiguous"),
    [
        # Long: SL 59400 / TP 61200, both inside the bar; Nautilus walks
        # open->high first and fills the TP while VectorBT takes the SL.
        ("long", (60_000.0, 61_500.0, 59_100.0, 60_000.0), "LIMIT", 61_200.0, 1),
        # Short: SL 60600 / TP 58800; the high comes first, so the SL fills.
        ("short", (60_000.0, 60_900.0, 58_500.0, 60_000.0), "STOP_MARKET", 60_600.0, 0),
    ],
)
def test_bracket_same_bar_sl_tp_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    direction: str,
    bar: tuple[float, float, float, float],
    exit_type: str,
    exit_px: float,
    ambiguous: int,
) -> None:
    rows = [(60_000.0, 60_000.0, 60_000.0, 60_000.0)] * 31 + [bar]
    rows += [(60_000.0, 60_010.0, 59_990.0, 60_000.0)] * 4
    df = _frame(rows)
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params={"entry_ts": df["timestamp"].iloc[30].isoformat(), "direction": direction},
        exit_mode="fixed_rr",
        costs=_ZERO_COSTS,
    )
    captured = capture_engine(monkeypatch)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    summary = json.loads(result.report_path.read_text())

    exits = [o for o in captured["fills"] if o["reduce_only"] or o["type"] != "MARKET"]
    assert [o["type"] for o in exits] == [exit_type]
    assert exits[0]["avg_px"] == pytest.approx(exit_px)
    assert "bracket_same_bar_sl_tp_ohlc_order" in summary["event_venue_model_gaps"]
    assert summary["bracket_same_bar_tp_fills"] == ambiguous


def test_trail_runs_do_not_report_the_bracket_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params={"entry_ts": _ENTRY_TS, "direction": "long"},
        exit_mode="trail",
    )
    result = run_phase2_backtest(
        export_dir=export_dir,
        data_root=tmp_path / "data",
        ohlcv=synth_ohlcv(200, seed=11),
    )
    summary = json.loads(result.report_path.read_text())
    assert "bracket_same_bar_sl_tp_ohlc_order" not in summary["event_venue_model_gaps"]
    assert summary["bracket_same_bar_tp_fills"] is None


# -- symbol aliases --------------------------------------------------------------


@pytest.mark.parametrize(
    ("symbol", "coin", "instrument"),
    [
        ("ETHUSDT", "ETH", "ETH-PERP"),
        ("ETH-USD", "ETH", "ETH-PERP"),
        ("SOLUSDT", "SOL", "SOL-PERP"),
        ("BTCUSDT", "BTC", "BTC-PERP"),
        ("BTC-PERP", "BTC", "BTC-PERP"),
        ("BTCPERP", "BTC", "BTC-PERP"),
        ("DOGEUSDT", "DOGE", "DOGE-PERP"),
        ("kPEPE-PERP", "kPEPE", "KPEPE-PERP"),
        ("SUSDE", "SUSDE", "SUSDE-PERP"),  # never a substring strip
        ("xyz:SNDK", "xyz:SNDK", "XYZ:SNDK-PERP"),
    ],
)
def test_one_coin_key_for_exporter_and_resolver(
    symbol: str, coin: str, instrument: str
) -> None:
    assert venue_coin_name(symbol) == coin
    assert venue_coin(symbol) == coin
    assert research_symbol_to_instrument(symbol) == instrument
    assert coin_for_symbol(symbol) == coin.upper()


def test_hip3_perp_suffix_is_not_doubled() -> None:
    assert research_symbol_to_instrument("xyz:SNDK-PERP") == "XYZ:SNDK-PERP"
    assert research_symbol_to_instrument("xyz:SNDK") == "XYZ:SNDK-PERP"


@pytest.mark.parametrize(("symbol", "coin"), [("ETHUSDT", "ETH"), ("SOLUSDT", "SOL")])
def test_alias_of_a_builtin_major_uses_the_builtin_spec(symbol: str, coin: str) -> None:
    spec = resolve_venue_spec(symbol)
    assert spec.coin == coin
    assert spec.instrument_symbol == f"{coin}-PERP"
    assert spec.source == "builtin_venue_spec"


def test_btc_aliases_keep_the_stub_geometry() -> None:
    for symbol in ("BTC", "BTCUSD", "BTCUSDT", "BTC-USD", "BTC-PERP", "BTCPERP"):
        spec = resolve_venue_spec(symbol)
        assert spec.source == "builtin_btc_stub"
        assert spec.instrument_symbol == "BTC-PERP"


def _write_universe(root: Path) -> None:
    path = root / VENUE_META_DIR / "meta.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "universe": [
                    {"name": "ETH", "szDecimals": 4, "maxLeverage": 25},
                    {"name": "DOGE", "szDecimals": 0, "maxLeverage": 10},
                ]
            }
        )
    )


@pytest.mark.parametrize("symbol", ["DOGEUSDT", "DOGE-PERP", "DOGE"])
def test_exported_alias_meta_resolves(tmp_path: Path, symbol: str) -> None:
    _write_universe(tmp_path)
    meta = with_instrument_meta({"symbol": symbol}, tmp_path)
    assert meta["instrument"]["name"] == "DOGE"
    spec = resolve_venue_spec(symbol, meta)
    assert spec.coin == "DOGE" and spec.source == "export_meta"
    assert spec.instrument_symbol == "DOGE-PERP"


def test_cached_meta_lookup_uses_the_normalized_coin(tmp_path: Path) -> None:
    _write_universe(tmp_path)
    instrument, reason = cached_instrument_meta(tmp_path, "ETHUSDT")
    assert reason == "" and instrument is not None and instrument["name"] == "ETH"
    assert resolve_venue_spec("ETHUSDT", {"instrument": instrument}).coin == "ETH"


def test_alias_export_runs_on_the_venue_instrument(tmp_path: Path) -> None:
    export_dir = write_export(tmp_path, symbol="ETHUSDT")
    df = synth_ohlcv(200, base=3_000.0, decimals=2)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    summary = json.loads(result.report_path.read_text())
    assert summary["instrument_id"] == "ETH-PERP.HYPERLIQUID"
    assert summary["instrument"]["source"] == "builtin_venue_spec"


# -- catalog instrument id ------------------------------------------------------


@pytest.mark.parametrize(
    ("symbol", "instrument_id"),
    [
        ("BTC", "BTC-PERP.HYPERLIQUID"),
        ("kPEPE", "KPEPE-PERP.HYPERLIQUID"),
        ("xyz:SNDK", "XYZ:SNDK-PERP.HYPERLIQUID"),
    ],
)
def test_catalog_default_instrument_id_matches_nautilus_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    symbol: str,
    instrument_id: str,
) -> None:
    captured: dict[str, object] = {}

    def fake_write(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            book_delta_count=0,
            quote_count=0,
            trade_count=0,
            gap_count=0,
            gap_provenance_path=Path(str(kwargs["catalog_path"])) / "gaps.json",
        )

    monkeypatch.setattr(
        "hypervector.nautilus.hl_catalog.write_hyperliquid_catalog", fake_write
    )
    data = tmp_path / "data"
    (data / "cache" / "events" / "hyperliquid" / symbol).mkdir(parents=True)
    argv = ["--data-root", str(data), "nautilus", "catalog", "--symbol", symbol]
    assert main([*argv, "--price-precision", "1", "--size-precision", "3"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["instrument_id"] == instrument_id
    assert captured["instrument_id"] == instrument_id
    # The run builds the same id for this coin.
    assert f"{research_symbol_to_instrument(symbol)}.HYPERLIQUID" == instrument_id
    # The archive keeps the venue's exact case.
    assert out["symbol"] == symbol
