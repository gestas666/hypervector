"""V90 expansion screen: breadth and sub-hourly clocks at real venue costs.

Report-only. execution_authority: none. No credentials, no order client.

Two questions, both aimed at MORE TRADES rather than bigger ones:

1. BREADTH. The hourly Donchian 20/10 is the only mechanism in the repository
   whose unselected aggregate is non-negative in-sample and out-of-sample. Which
   other liquid, growth-mode HIP-3 markets does it transfer to?
2. SCALPING. Every sub-hourly family this repository rejected was scored against
   a 13 bps crypto friction hurdle. HIP-3 growth-mode markets cost about 1.7 bps
   in fees per round trip. Does the SAME mechanism on a 15-minute or 5-minute
   signal clock clear that much lower hurdle? This was never measured.

Discipline carried over from the 2026-09-20 out-of-sample review:

* The mechanism grid is declared here, before any result, and is tiny: one
  channel pair (20/10), three clocks. No parameter is tuned.
* The signal path reuses the repository's own validated Donchian internals, and
  ``parity`` proves the generic builder reproduces the frozen hourly builder.
* Entries whose ATR stop is not finite are refused, exactly as the live provider
  refuses them (``hourly_price_provider._evaluation``). The frozen research
  builder does not, which is a known research/live parity defect.
* Every cell reports buy-and-hold and an exposure-matched always-long benchmark.
  A trending-window result without those two columns is not evidence of skill.
* Every cell reports three contiguous equal blocks, so no boundary is chosen.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics as st
import time

import numpy as np
import pandas as pd
import requests

from hypervector.data.hl import bars_from_hl_payload, funding_from_hl_payload
from hypervector.research import donchian_atr_breakout_signals as donchian
from hypervector.research.completed_bar_indicators import (
    OHLC_COLUMNS,
    contiguous_segment_ids,
    raw_true_range,
    segmented_wilder_rma,
    validated_ohlc_bars,
)
from hypervector.research.completed_signal_projection import empty_directional_signals
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig

INFO_URL = "https://api.hyperliquid.xyz/info"
NOTIONAL = 500.0
EQUITY = 4857.58724349
ENTRY_BARS, EXIT_BARS, ATR_PERIOD, ATR_MULTIPLE = 20, 10, 20, 2.0

# clock id -> (execution minutes, signal minutes). Hold cap = 24 signal bars.
# H4 was added AFTER M15 and M5 were seen to be monotonically worse than H1, to
# complete the edge-versus-clock curve. It is the repository's own V75 default
# signal clock, not a new parameter, but it is not part of the original grid.
CLOCKS = {"H4": (15, 240), "H1": (15, 60), "M15": (15, 15), "M5": (5, 5)}

# cost id -> (entry slip bps, exit slip bps, HIP-3 fee bps/side, crypto fee bps/side)
# "measured" uses the live means: 0.864 / 4.32 bps fees on 60 fills, and
# 0.773 / 1.485 bps entry / exit slippage from audit.execution.friction_parity.
COSTS = {
    "measured": (0.8, 1.5, 0.864, 4.32),
    "adverse": (5.5, 5.5, 0.9, 4.5),
    "hip3_full_fee": (5.5, 5.5, 9.0, 4.5),
}


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #


def _post(session: requests.Session, payload: dict[str, object], pace: float) -> object:
    """One paced public read. The live backend shares this IP's request budget."""
    time.sleep(pace)
    response = session.post(INFO_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_symbol(
    session: requests.Session, symbol: str, interval: str, directory: Path, pace: float
) -> dict[str, object]:
    """Capture the venue's retained candles (at most 5,000) and hourly funding."""
    target = directory / symbol.replace(":", "_")
    target.mkdir(parents=True, exist_ok=False)
    end = pd.Timestamp.now(tz="UTC").floor("h")
    minutes = int(interval.removesuffix("m"))
    start = end - pd.Timedelta(minutes=minutes * 4_990)
    raw = _post(
        session,
        {
            "type": "candleSnapshot",
            "req": {
                "coin": symbol,
                "interval": interval,
                "startTime": int(start.timestamp() * 1000),
                "endTime": int(end.timestamp() * 1000),
            },
        },
        pace,
    )
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{symbol}: empty candle response")
    bars = bars_from_hl_payload(raw).set_index("timestamp").sort_index()
    bars = bars.loc[bars.index < end]
    rows: list[dict[str, object]] = []
    cursor = int(bars.index.min().timestamp() * 1000)
    final = int(end.timestamp() * 1000)
    while cursor < final:
        page = _post(
            session,
            {"type": "fundingHistory", "coin": symbol, "startTime": cursor, "endTime": final},
            pace,
        )
        if not isinstance(page, list) or not page:
            break
        rows.extend(page)
        latest = max(int(item["time"]) for item in page)
        if latest <= cursor or len(page) < 500:
            break
        cursor = latest + 1
    funding = funding_from_hl_payload(rows)
    bars.to_parquet(target / "bars.parquet")
    funding.to_parquet(target / "funding.parquet", index=False)
    summary = {
        "symbol": symbol,
        "interval": interval,
        "bars": len(bars),
        "first": str(bars.index.min()),
        "last": str(bars.index.max()),
        "funding_rows": len(funding),
    }
    print(summary, flush=True)
    return summary


def attach_funding(bars: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    """Assign each hourly settlement to the first bar at or after it.

    Tolerates listing gaps that ``attach_official_funding`` rejects. Funding is a
    second-order term here (at most $1.43 per cell over 48 days in the frozen
    screen), so a missing settlement is left at zero and never imputed.
    """
    output = bars.copy()
    output["funding_rate"] = 0.0
    if funding.empty:
        return output
    events = funding.drop_duplicates("timestamp").set_index("timestamp")["funding_rate"]
    events = events.loc[(events.index >= output.index.min()) & (events.index <= output.index.max())]
    positions = output.index.searchsorted(events.index, side="left")
    column = output.columns.get_loc("funding_rate")
    for position, rate in zip(positions, events.to_numpy(), strict=True):
        if position < len(output):
            output.iat[int(position), column] += float(rate)
    return output


def load_inputs(directory: Path, symbol: str) -> pd.DataFrame | None:
    """Return funding-attached bars for one symbol, or ``None`` when absent."""
    source = directory / symbol.replace(":", "_")
    if not (source / "bars.parquet").exists():
        return None
    bars = pd.read_parquet(source / "bars.parquet").sort_index()
    bars = bars.loc[~bars.index.duplicated()]
    funding = pd.read_parquet(source / "funding.parquet")
    return attach_funding(bars, funding)


# --------------------------------------------------------------------------- #
# generic-clock Donchian, built from the repository's validated internals
# --------------------------------------------------------------------------- #


def complete_resample(frame: pd.DataFrame, source_minutes: int, target_minutes: int) -> pd.DataFrame:
    """Aggregate only complete, boundary-aligned bars (minutes-generic)."""
    if target_minutes == source_minutes:
        return frame.loc[:, list(OHLC_COLUMNS)]
    expected = target_minutes // source_minutes
    interval = pd.Timedelta(minutes=source_minutes)
    rule = f"{target_minutes}min"
    grouped = frame.resample(rule, origin="epoch", label="left", closed="left")
    aggregate = grouped.agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), count=("close", "count"),
    )
    bounds = (
        frame.index.to_series()
        .resample(rule, origin="epoch", label="left", closed="left")
        .agg(["min", "max"])
    )
    complete = (
        aggregate["count"].eq(expected)
        & bounds["min"].eq(aggregate.index)
        & bounds["max"].eq(aggregate.index + interval * (expected - 1))
    )
    return aggregate.loc[complete, list(OHLC_COLUMNS)]


def generic_donchian_signals(
    execution_bars: pd.DataFrame, *, execution_minutes: int, signal_minutes: int
) -> pd.DataFrame:
    """Completed-bar Donchian 20/10 with ATR(20)x2 stops on any signal clock."""
    frame = validated_ohlc_bars(execution_bars, label="generic Donchian")
    signal_bars = complete_resample(frame, execution_minutes, signal_minutes)
    segments = contiguous_segment_ids(signal_bars.index, pd.Timedelta(minutes=signal_minutes))
    close = signal_bars["close"].to_numpy(dtype=np.float64)
    high = signal_bars["high"].to_numpy(dtype=np.float64)
    low = signal_bars["low"].to_numpy(dtype=np.float64)
    entry_high = donchian._prior_extreme(high, segments, ENTRY_BARS, "max")
    entry_low = donchian._prior_extreme(low, segments, ENTRY_BARS, "min")
    exit_high = donchian._prior_extreme(high, segments, EXIT_BARS, "max")
    exit_low = donchian._prior_extreme(low, segments, EXIT_BARS, "min")
    long_entry = donchian._fresh_onset(close > entry_high, segments)
    short_entry = donchian._fresh_onset(close < entry_low, segments)
    atr = segmented_wilder_rma(raw_true_range(signal_bars, segments), segments, ATR_PERIOD)
    stop = donchian._entry_stops(close, atr, long_entry, short_entry, ATR_MULTIPLE)
    # Live parity: the live provider refuses an entry whose stop is not finite.
    finite = np.isfinite(stop)
    long_entry, short_entry = long_entry & finite, short_entry & finite

    output = empty_directional_signals(
        frame.index,
        signal_name=f"completed_{signal_minutes}m_donchian_{ENTRY_BARS}_{EXIT_BARS}_atr{ATR_PERIOD}",
        source_time_column="donchian_signal_bar_open",
    )
    offset = pd.Timedelta(minutes=signal_minutes - execution_minutes)
    decision = signal_bars.index + offset
    present = decision.isin(frame.index)
    for flags, direction in ((long_entry, "long"), (short_entry, "short")):
        rows = decision[flags & present]
        output.loc[rows, "entry_direction"] = direction
        output.loc[rows, f"{direction}_entry"] = True
        output.loc[rows, "short_exit" if direction == "long" else "long_exit"] = True
        output.loc[rows, "stop_price"] = stop[flags & present]
    output.loc[decision[(close < exit_low) & present], "long_exit"] = True
    output.loc[decision[(close > exit_high) & present], "short_exit"] = True
    return output


def parity(frozen_inputs: Path, symbols: tuple[str, ...]) -> dict[str, object]:
    """Prove the generic builder reproduces the frozen hourly builder.

    The only permitted difference is entries the frozen builder emits with a
    non-finite stop, which this builder refuses by design.
    """
    checked, identical, refused = 0, 0, 0
    for symbol in symbols:
        bars = load_inputs(frozen_inputs, symbol)
        if bars is None:
            continue
        reference = donchian.build_donchian_atr_breakout_signals(
            bars,
            donchian.DonchianAtrBreakoutConfig(
                entry_channel_bars=ENTRY_BARS, exit_channel_bars=EXIT_BARS, signal_hours=1
            ),
        )
        mine = generic_donchian_signals(bars, execution_minutes=15, signal_minutes=60)
        nan_stop = (reference["long_entry"] | reference["short_entry"]) & reference["stop_price"].isna()
        refused += int(nan_stop.sum())
        keep = ~nan_stop
        same = True
        for column in ("long_entry", "short_entry", "long_exit", "short_exit"):
            same &= bool((reference.loc[keep, column] == mine.loc[keep, column]).all())
        same &= bool(
            np.allclose(
                reference.loc[keep, "stop_price"].to_numpy(dtype=float),
                mine.loc[keep, "stop_price"].to_numpy(dtype=float),
                equal_nan=True,
            )
        )
        checked += 1
        identical += int(same)
    return {"symbols_checked": checked, "identical": identical, "nan_stop_entries_refused": refused}


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #


def portfolio_config(symbol: str, venue_max: float, cost: str, hold_seconds: int) -> SharedPortfolioConfig:
    """The frozen $500 / 10x screen contract with a per-clock hold cap."""
    entry_slip, exit_slip, hip3_fee, crypto_fee = COSTS[cost]
    fee = (hip3_fee if symbol.startswith("xyz:") else crypto_fee) / 10_000.0
    return SharedPortfolioConfig(
        symbol=symbol, initial_equity=EQUITY, leverage=min(10.0, venue_max),
        venue_max_leverage=venue_max, margin_fraction=0.02, maximum_notional_usd=NOTIONAL,
        minimum_stop_distance_bps=20.0, maximum_stop_distance_bps=250.0,
        max_hold_seconds=hold_seconds, reentry_cooldown_bars=0, close_on_opposite_signal=False,
        entry_fee_rate=fee, target_fee_rate=fee, market_exit_fee_rate=fee,
        liquidation_fee_rate=fee, entry_slippage_bps=entry_slip,
        market_exit_slippage_bps=exit_slip, target_slippage_bps=exit_slip,
        liquidation_slippage_bps=exit_slip,
    )


def buy_and_hold(bars: pd.DataFrame, symbol: str, cost: str) -> float:
    """Always-long at the same notional, the same costs and the real funding."""
    entry_slip, exit_slip, hip3_fee, crypto_fee = COSTS[cost]
    fee = hip3_fee if symbol.startswith("xyz:") else crypto_fee
    entry = float(bars["open"].iloc[0]) * (1.0 + entry_slip / 10_000.0)
    exit_price = float(bars["close"].iloc[-1]) * (1.0 - exit_slip / 10_000.0)
    gross = NOTIONAL * (exit_price / entry - 1.0)
    fees = NOTIONAL * 2.0 * fee / 10_000.0
    funding = -NOTIONAL * float(bars["funding_rate"].sum())
    return gross - fees + funding


def exposure_matched_long(trades: list[object], cost: str) -> float:
    """An always-long position held over exactly each trade's own window.

    A long trade is its own benchmark. A short is mirrored: gross and funding
    flip sign, fees are unchanged, and the slippage the short received on both
    legs is charged again in the long's direction.
    """
    entry_slip, exit_slip, _hip3, _crypto = COSTS[cost]
    total = 0.0
    for trade in trades:
        if trade.direction == "long":
            total += float(trade.net_pnl_usd)
            continue
        mirrored = -float(trade.gross_pnl_usd) - float(trade.funding_cashflow_usd)
        reslip = float(trade.notional_usd) * 2.0 * (entry_slip + exit_slip) / 10_000.0
        total += mirrored - float(trade.fees_usd) - reslip
    return total


def score(trades: list[object], bars: pd.DataFrame, symbol: str, cost: str) -> dict[str, object]:
    """Summarize one cell, including its benchmarks and three equal blocks."""
    pnl = [float(trade.net_pnl_usd) for trade in trades]
    n = len(pnl)
    days = (bars.index.max() - bars.index.min()).total_seconds() / 86_400.0
    gains = sum(x for x in pnl if x > 0.0)
    losses = -sum(x for x in pnl if x < 0.0)
    deviation = st.stdev(pnl) if n > 1 else 0.0
    edges = pd.date_range(bars.index.min(), bars.index.max(), periods=4)
    blocks = [
        round(sum(float(t.net_pnl_usd) for t in trades
                  if edges[i] <= pd.Timestamp(t.entry_time_utc) < edges[i + 1] or
                  (i == 2 and pd.Timestamp(t.entry_time_utc) == edges[3])), 4)
        for i in range(3)
    ]
    hold = buy_and_hold(bars, symbol, cost)
    matched = exposure_matched_long(trades, cost)
    net = sum(pnl)
    held_seconds = sum(
        (pd.Timestamp(t.exit_time_utc) - pd.Timestamp(t.entry_time_utc)).total_seconds()
        for t in trades
    )
    in_market = held_seconds / (days * 86_400.0) if days else 0.0
    return {
        "trades": n,
        "days": round(days, 3),
        "trades_per_day": round(n / days, 4) if days else None,
        "net_usd": round(net, 4),
        "usd_per_day": round(net / days, 4) if days else None,
        "mean_usd": round(st.mean(pnl), 4) if n else None,
        "t_statistic": round(st.mean(pnl) / (deviation / math.sqrt(n)), 4) if n > 2 and deviation else None,
        "profit_factor": round(gains / losses, 4) if losses else None,
        "win_rate": round(sum(1 for x in pnl if x > 0.0) / n, 4) if n else None,
        "liquidations": sum(1 for t in trades if t.exit_reason == "liquidation"),
        "longs_net_usd": round(sum(float(t.net_pnl_usd) for t in trades if t.direction == "long"), 4),
        "shorts_net_usd": round(sum(float(t.net_pnl_usd) for t in trades if t.direction == "short"), 4),
        "block_nets_usd": blocks,
        "blocks_positive": sum(1 for value in blocks if value > 0.0),
        "time_in_market_fraction": round(in_market, 4),
        "buy_and_hold_usd": round(hold, 4),
        "beta_scaled_buy_and_hold_usd": round(hold * in_market, 4),
        "net_minus_beta_scaled_usd": round(net - hold * in_market, 4),
        "net_minus_buy_and_hold_usd": round(net - hold, 4),
        "exposure_matched_long_usd": round(matched, 4),
        "alpha_vs_exposure_matched_usd": round(net - matched, 4),
    }


def run_cell(bars: pd.DataFrame, symbol: str, venue_max: float, clock: str, cost: str) -> dict[str, object]:
    """Evaluate one symbol on one clock under one cost profile."""
    execution_minutes, signal_minutes = CLOCKS[clock]
    signals = generic_donchian_signals(
        bars, execution_minutes=execution_minutes, signal_minutes=signal_minutes
    )
    config = portfolio_config(symbol, venue_max, cost, hold_seconds=signal_minutes * 60 * 24)
    result = evaluate_shared_bar_portfolio(bars, signals, config)
    trades = list(result.trades)
    return {"symbol": symbol, "clock": clock, "cost": cost, **score(trades, bars, symbol, cost)}


# --------------------------------------------------------------------------- #
# command line
# --------------------------------------------------------------------------- #


def main() -> None:
    """Fetch paced public inputs, prove parity, or publish every screened cell."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch")
    fetch.add_argument("--interval", choices=("15m", "5m"), required=True)
    fetch.add_argument("--symbols", nargs="+", required=True)
    fetch.add_argument("--out", type=Path, required=True)
    fetch.add_argument("--pace-seconds", type=float, default=12.0)
    check = commands.add_parser("parity")
    check.add_argument("--inputs", type=Path, required=True)
    check.add_argument("--symbols", nargs="+", required=True)
    screen = commands.add_parser("screen")
    screen.add_argument("--inputs", type=Path, required=True)
    screen.add_argument("--clocks", nargs="+", choices=tuple(CLOCKS), required=True)
    screen.add_argument("--symbols", nargs="+", required=True)
    screen.add_argument("--venue-meta", type=Path, required=True)
    screen.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "fetch":
        args.out.mkdir(parents=True, exist_ok=True)
        rows = []
        with requests.Session() as session:
            for symbol in args.symbols:
                try:
                    rows.append(fetch_symbol(session, symbol, args.interval, args.out, args.pace_seconds))
                except Exception as exc:  # noqa: BLE001 - every failure is a retained result
                    rows.append({"symbol": symbol, "error": type(exc).__name__})
                    print({"symbol": symbol, "error": type(exc).__name__}, flush=True)
        (args.out / "manifest.json").write_text(json.dumps(rows, indent=1))
        return

    if args.command == "parity":
        print(json.dumps(parity(args.inputs, tuple(args.symbols)), indent=1))
        return

    meta = json.loads(args.venue_meta.read_text())["meta"]["universe"]
    venue_max = {row["name"]: float(row["maxLeverage"]) for row in meta}
    venue_max.update({"BTC": 40.0, "ETH": 25.0, "SOL": 20.0, "HYPE": 10.0})
    if args.out.exists():
        raise FileExistsError(args.out)
    cells: list[dict[str, object]] = []
    for symbol in args.symbols:
        bars = load_inputs(args.inputs, symbol)
        if bars is None or len(bars) < 500:
            print({"symbol": symbol, "skipped": "no_or_short_inputs"}, flush=True)
            continue
        for clock in args.clocks:
            for cost in COSTS:
                try:
                    cell = run_cell(bars, symbol, venue_max.get(symbol, 10.0), clock, cost)
                except Exception as exc:  # noqa: BLE001 - a failed cell is a reported result
                    cell = {"symbol": symbol, "clock": clock, "cost": cost, "error": f"{type(exc).__name__}: {exc}"}
                cells.append(cell)
                if cost == "measured":
                    print({k: cell.get(k) for k in ("symbol", "clock", "trades", "net_usd", "t_statistic",
                                                   "buy_and_hold_usd", "alpha_vs_exposure_matched_usd")}, flush=True)
    args.out.write_text(
        json.dumps(
            {
                "schema_version": 1, "execution_authority": "none", "automatic_promotion": False,
                "runtime_strategy_changed": False,
                "declared_grid": {"channel": [ENTRY_BARS, EXIT_BARS], "atr": [ATR_PERIOD, ATR_MULTIPLE],
                                  "clocks": CLOCKS, "costs": COSTS, "hold_cap_signal_bars": 24,
                                  "notional_usd": NOTIONAL, "leverage": 10.0, "stop_clamp_bps": [20.0, 250.0]},
                "cells": cells,
                "limitations": [
                    "Candle OHLC conditional fills; no queue position, depth or private fill reconstruction.",
                    "Each asset is screened independently at $500; nothing here measures shared-account solvency or behaviour at larger size.",
                    "The venue retains at most 5,000 candles per interval, so the 5-minute window is about 17 days and new 15-minute symbols about 52 days.",
                    "Every window here overlaps the 2026-09-17 to 09-19 rebound. Read net only beside buy-and-hold and the exposure-matched benchmark.",
                    "This is a screen over many cells. The best cell of N is expected to look good under a zero-edge null; nothing here is a promotion.",
                ],
            },
            indent=1,
        )
    )
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
