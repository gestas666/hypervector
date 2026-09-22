"""Score the v89 roster and V90 candidates on strictly post-selection tape.

Report-only. execution_authority: none. No credentials, no order client, no
live path is touched.

The frozen selection screen (`frequency_repair_*_20260907_v1`) ends at
2026-09-06T23:45Z. Every bar used here opens at or after 2026-09-07T00:00Z, so
no cell in this file could have influenced the roster that is running.

Entries are byte-identical across the LEVERAGE arms. They are NOT identical
across the max_hold arms: a longer hold keeps a position open through later
signals, so raising max_hold_seconds removes entries (D20/10 goes 86 -> 71 -> 70
trades at 24h/48h/72h). The hold sweep is therefore not a clean exit-geometry
contrast and must not be read as one.

KNOWN DEFECT IN THE SIGNAL BUILDER (research-only, does not affect live):
`build_donchian_atr_breakout_signals` has no finite-ATR gate, unlike
`build_hourly_band_reentry_signals` (hourly_band_reentry.py:82,
`warmed = adjacent & np.isfinite(atr)`). When entry_channel_bars < atr_period
(i.e. the 8/4 variant), entries fire during ATR(20) warmup with
`stop_price = NaN`, and `evaluate_shared_bar_portfolio` then runs them with no
stop and no target. Nine such signals occur in this window, all on 8/4, all in
the first 24 hours; 20/10 and band20 emit none. The LIVE path is unaffected:
`hourly_price_provider._evaluation` sets `eligible = side is not None and ready
and stop is not None`, and `_intent` raises on a non-finite stop, so the live
engine refuses exactly these decisions. The published frozen 2026-09-07 screen
is also unaffected, because its scored windows start 2026-07-21 while its bars
start 2026-07-19, so the warmup falls outside every scored cell.
Effect on this file: the D8/4 aggregate is -$24.28 as published and -$3.49 when
scoring starts after a 24h warmup buffer. D20/10 (+$107.58) and band20
(-$322.55) are unchanged, having zero NaN-stop entries.
"""

from __future__ import annotations

import argparse
import statistics as st
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.donchian_atr_breakout_signals import (
    DonchianAtrBreakoutConfig,
    build_donchian_atr_breakout_signals,
)
from hypervector.research.hip3_transfer_sources import attach_official_funding
from hypervector.research.hourly_band_reentry import build_hourly_band_reentry_signals
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig

SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SPCX",
    "xyz:SP500",
    "xyz:SNDK",
    "xyz:BRENTOIL",
)
VENUE_MAX = {
    "BTC": 40,
    "ETH": 25,
    "SOL": 20,
    "HYPE": 10,
    "xyz:SPCX": 20,
    "xyz:SP500": 50,
    "xyz:SNDK": 10,
    "xyz:BRENTOIL": 20,
}
# (slippage bps per side, HIP-3 fee bps per side). Crypto fee is fixed at 4.5.
COSTS = (("nominal", 2.5, 0.9), ("adverse", 5.5, 0.9), ("hip3_full_fee", 5.5, 9.0))
MECHANISMS = (
    ("hourly_donchian_20_10_atr20_bidirectional_v1", (20, 10)),
    ("hourly_donchian_8_4_atr20_bidirectional_v1", (8, 4)),
    ("hourly_band20_reentry_atr20_bidirectional_v1", None),
)
# The equity basis the frozen screen used, retained so cells are comparable.
SCREEN_EQUITY = 4857.58724349

_bars: dict[str, pd.DataFrame] = {}
_signals: dict[tuple[str, tuple[int, int] | None], pd.DataFrame] = {}


def bars_for(inputs: Path, symbol: str) -> pd.DataFrame:
    """Return funding-attached execution bars for one symbol, cached."""
    if symbol in _bars:
        return _bars[symbol]
    source = inputs / symbol.replace(":", "_")
    frame, evidence = attach_official_funding(
        pd.read_parquet(source / "bars.parquet"),
        pd.read_parquet(source / "funding.parquet"),
    )
    if evidence.unassigned_event_count or evidence.delayed_event_count:
        raise ValueError(f"{symbol}: incomplete native funding assignment")
    _bars[symbol] = frame
    return frame


def signals_for(
    inputs: Path, symbol: str, variant: tuple[int, int] | None
) -> pd.DataFrame:
    """Return completed-hour signals for one mechanism, cached."""
    key = (symbol, variant)
    if key in _signals:
        return _signals[key]
    frame = bars_for(inputs, symbol)
    if variant is None:
        built = build_hourly_band_reentry_signals(frame)
    else:
        entry, exit_channel = variant
        built = build_donchian_atr_breakout_signals(
            frame,
            DonchianAtrBreakoutConfig(
                entry_channel_bars=entry,
                exit_channel_bars=exit_channel,
                signal_hours=1,
            ),
        )
    _signals[key] = built
    return built


def screen_config(symbol: str, slip: float, hip3_fee: float) -> SharedPortfolioConfig:
    """Return the frozen screen's per-asset research lifecycle and costs."""
    fee = (hip3_fee if symbol.startswith("xyz:") else 4.5) / 10000
    return SharedPortfolioConfig(
        symbol=symbol,
        initial_equity=SCREEN_EQUITY,
        leverage=10.0,
        venue_max_leverage=VENUE_MAX[symbol],
        margin_fraction=0.02,
        maximum_notional_usd=500.0,
        minimum_stop_distance_bps=20.0,
        maximum_stop_distance_bps=250.0,
        max_hold_seconds=86400,
        reentry_cooldown_bars=0,
        close_on_opposite_signal=False,
        entry_fee_rate=fee,
        target_fee_rate=fee,
        market_exit_fee_rate=fee,
        liquidation_fee_rate=fee,
        entry_slippage_bps=slip,
        market_exit_slippage_bps=slip,
        target_slippage_bps=slip,
    )


def describe(trades: list[object]) -> dict[str, object]:
    """Summarize one arm without discarding losing, sparse or censored results."""
    pnl = [float(t.net_pnl_usd) for t in trades]
    n = len(pnl)
    gross_profit = sum(x for x in pnl if x > 0.0)
    gross_loss = -sum(x for x in pnl if x < 0.0)
    exits: dict[str, int] = {}
    for trade in trades:
        exits[trade.exit_reason] = exits.get(trade.exit_reason, 0) + 1
    ordered = sorted(pnl)
    stdev = st.stdev(pnl) if n > 1 else 0.0
    return {
        "trades": n,
        "net_usd": round(sum(pnl), 6),
        "wins": sum(1 for x in pnl if x > 0.0),
        "profit_factor": (
            round(gross_profit / gross_loss, 6) if gross_loss > 0.0 else None
        ),
        "net_excluding_top_1_usd": round(sum(ordered[:-1]), 6) if n >= 1 else None,
        "net_excluding_top_3_usd": round(sum(ordered[:-3]), 6) if n >= 3 else None,
        "mean_usd": round(st.mean(pnl), 6) if n else None,
        "stdev_usd": round(stdev, 6) if n > 1 else None,
        "t_statistic": (
            round(st.mean(pnl) / (stdev / n**0.5), 6) if n > 2 and stdev > 0.0 else None
        ),
        "liquidations": exits.get("liquidation", 0),
        "exit_reasons": exits,
    }


def run_arm(
    inputs: Path,
    symbol: str,
    variant: tuple[int, int] | None,
    config: SharedPortfolioConfig,
) -> tuple[dict[str, object], list[object]]:
    """Evaluate one symbol/mechanism/config arm over the whole OOS window."""
    frame = bars_for(inputs, symbol)
    signals = signals_for(inputs, symbol, variant)
    result = evaluate_shared_bar_portfolio(frame, signals, config)
    return describe(list(result.trades)), list(result.trades)


def main() -> None:
    """Publish every arm, including negative and sparse ones, with no selection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    inputs = args.input_dir.resolve()

    cells: list[dict[str, object]] = []
    trade_rows: list[dict[str, object]] = []
    for strategy_id, variant in MECHANISMS:
        for symbol in SYMBOLS:
            for cost_name, slip, hip3_fee in COSTS:
                config = screen_config(symbol, slip, hip3_fee)
                summary, trades = run_arm(inputs, symbol, variant, config)
                cells.append(
                    {
                        "strategy_id": strategy_id,
                        "symbol": symbol,
                        "cost": cost_name,
                        "arm": "screen_contract",
                        **summary,
                    }
                )
                if cost_name == "adverse":
                    for trade in trades:
                        row = asdict(trade)
                        row["strategy_id"] = strategy_id
                        row["symbol"] = symbol
                        trade_rows.append(row)
                print(
                    {
                        "strategy": strategy_id.split("_atr20")[0],
                        "symbol": symbol,
                        "cost": cost_name,
                        "n": summary["trades"],
                        "net": summary["net_usd"],
                    },
                    flush=True,
                )

    # Geometry sweeps on the adverse basis: identical entries, varied exit clock
    # and varied leverage. Only the deployed Donchian 20/10 mechanism is swept
    # across every symbol; this is the contested lever from the V90 review.
    sweeps: list[dict[str, object]] = []
    for strategy_id, variant in MECHANISMS:
        for symbol in SYMBOLS:
            base = screen_config(symbol, 5.5, 0.9)
            for hold in (86400, 172800, 259200):
                summary, _ = run_arm(
                    inputs, symbol, variant, replace(base, max_hold_seconds=hold)
                )
                sweeps.append(
                    {
                        "sweep": "max_hold_seconds",
                        "strategy_id": strategy_id,
                        "symbol": symbol,
                        "value": hold,
                        **summary,
                    }
                )
            for leverage in (6.0, 8.0, 10.0):
                summary, _ = run_arm(
                    inputs, symbol, variant, replace(base, leverage=leverage)
                )
                sweeps.append(
                    {
                        "sweep": "leverage",
                        "strategy_id": strategy_id,
                        "symbol": symbol,
                        "value": leverage,
                        **summary,
                    }
                )

    paths = [
        Path(__file__),
        inputs / "manifest.json",
        Path("src/hypervector/research/donchian_atr_breakout_signals.py"),
        Path("src/hypervector/research/hourly_band_reentry.py"),
        Path("src/hypervector/research/shared_bar_portfolio.py"),
    ]
    paths.extend(sorted(inputs.rglob("*.parquet")))
    write_immutable_json(
        args.out,
        {
            "schema_version": 1,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "window_start_utc": "2026-09-07T00:00:00+00:00",
            "window_end_exclusive_utc": "2026-09-20T00:00:00+00:00",
            "selection_screen_end_exclusive_utc": "2026-09-07T00:00:00+00:00",
            "cells": cells,
            "sweeps": sweeps,
            "adverse_trades": trade_rows,
            "evidence": {str(path.resolve()): file_evidence(path) for path in paths},
            "limitations": [
                "Thirteen calendar days. Per-cell trade counts are small and no"
                " cell here can establish forward expectancy.",
                "The operator has already observed the LIVE outcome of three of"
                " these routes in this same interval, so the window is"
                " out-of-sample with respect to roster SELECTION only.",
                "Native candle OHLC conditional fills; no queue position, depth"
                " constraint, receipt or private fill reconstruction.",
                "Each asset is screened independently at the frozen $500/10x"
                " contract; summed activity does not establish shared-account"
                " solvency.",
                "Same-bar paths order liquidation, then stop, then target.",
                "Tape corroboration is PARTIAL: the independently recorded 1m"
                " tape covers 2026-09-08 to 2026-09-13T11:59 on 7 of 8 symbols"
                " (no xyz:SP500), i.e. roughly 36% of the OOS bars. Over the"
                " overlap, 3,588 of 3,635 resampled 15m bars are byte-exact."
                " Of the 47 differences most are in OPEN, but HIGH and LOW also"
                " differ on a handful of xyz:SNDK and xyz:SPCX bars; the largest"
                " single deviation is about 7.4 bps on an xyz:SNDK open.",
                "max_hold arms do not share entries (see module docstring), and"
                " the D20/10 hold curve has an interior maximum at 48h"
                " (+107.58 / +153.32 / +134.74), the canonical shape of a"
                " fitted parameter rather than a discovered one.",
                "liquidation_slippage_bps is left at its 0.0 default while every"
                " other exit pays 5.5 bps, so the single liquidation observed in"
                " 357 trades is priced at the liquidation price exactly.",
                "Leverage does not vary position size here: margin_fraction 0.02"
                " on $4,857.59 gives $583/$777/$972 of formula notional at"
                " 6x/8x/10x, all above the $500 cap, so every published trade has"
                " notional_usd exactly 500.0.",
            ],
        },
    )
    print(f"\nwrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
