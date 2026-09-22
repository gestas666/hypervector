"""Measure the proposed V90 profit lock against declared alternatives, at scale.

Report-only. execution_authority: none.

The 2026-09-21 readiness review scored the proposed 100/25/50 lock on 27 live
lifecycles, most of them from mechanisms V90 retires. This scores the SAME lock
function the live controller uses (``evaluate_profit_lock_path``) on the routes
V90 actually runs, with identical entries across arms by construction of the
signal frame, and then at mechanism scale across 26 markets.

Arms are declared here before any result. They are FAMILIES, not a tuning grid:

==================  ===========================================================
none                control: recipe exit, structural stop, 24h fallback
trail_60_15_30      the review's tighter alternative
trail_100_25_50     THE PROPOSAL
trail_150_35_75     the review's looser alternative
floor_100_25        same activation and floor, NO trail. ``stop = max(floor,
                    best * (1 - giveback))``, so a giveback larger than any
                    possible excursion leaves only the floor. A +1% winner can
                    no longer become a loser; nothing caps the run.
trail_300_100_300   wide: arms late, leaves a winner 3% of room
==================  ===========================================================

Resolution caveat. Live evaluates this lock on completed ONE-MINUTE candles;
this replay evaluates it on 15-minute bars and fills at the next bar's open. A
finer clock ratchets ``best`` sooner, so live will trigger MORE often than shown
here; the 5-minute arm below measures the direction of that bias.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import statistics as st

import pandas as pd

from hypervector.cohort_profit_lock_policy import ProfitLockPolicy
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
import v90_expansion_screen as xs

NO_TRAIL_BPS = 9_000.0  # best * 0.10 is below any floor, so only the floor binds
ARMS: dict[str, ProfitLockPolicy | None] = {
    "none": None,
    "trail_60_15_30": ProfitLockPolicy("trail_60_15_30", 60.0, 15.0, 30.0),
    "trail_100_25_50": ProfitLockPolicy("trail_100_25_50", 100.0, 25.0, 50.0),
    "trail_150_35_75": ProfitLockPolicy("trail_150_35_75", 150.0, 35.0, 75.0),
    "floor_100_25": ProfitLockPolicy("floor_100_25", 100.0, 25.0, NO_TRAIL_BPS),
    "trail_300_100_300": ProfitLockPolicy("trail_300_100_300", 300.0, 100.0, 300.0),
}


def run_arm(
    bars: pd.DataFrame, signals: pd.DataFrame, symbol: str, venue_max: float,
    cost: str, leverage: float, policy: ProfitLockPolicy | None,
) -> list[object]:
    """Evaluate one exit arm on a fixed signal frame."""
    base = xs.portfolio_config(symbol, venue_max, cost, hold_seconds=86_400)
    config = replace(
        base,
        leverage=min(leverage, venue_max),
        margin_fraction=xs.NOTIONAL / (xs.EQUITY * min(leverage, venue_max)) + 1e-9,
        completed_bar_profit_lock=policy,
    )
    return list(evaluate_shared_bar_portfolio(bars, signals, config).trades)


def describe(trades: list[object], days: float) -> dict[str, object]:
    """Summarize one arm with emphasis on the right tail."""
    pnl = sorted(float(t.net_pnl_usd) for t in trades)
    n = len(pnl)
    wins = [x for x in pnl if x > 0.0]
    losses = [x for x in pnl if x < 0.0]
    deviation = st.stdev(pnl) if n > 1 else 0.0
    reasons: dict[str, int] = {}
    for trade in trades:
        reasons[trade.exit_reason] = reasons.get(trade.exit_reason, 0) + 1
    return {
        "trades": n,
        "net_usd": round(sum(pnl), 2),
        "usd_per_day": round(sum(pnl) / days, 3),
        "win_rate": round(len(wins) / n, 4) if n else None,
        "mean_win_usd": round(st.mean(wins), 2) if wins else None,
        "mean_loss_usd": round(st.mean(losses), 2) if losses else None,
        "payoff_ratio": round(st.mean(wins) / -st.mean(losses), 3) if wins and losses else None,
        "profit_factor": round(sum(wins) / -sum(losses), 3) if losses else None,
        "t_statistic": round(st.mean(pnl) / (deviation / math.sqrt(n)), 3) if n > 2 and deviation else None,
        "largest_trade_usd": round(pnl[-1], 2) if n else None,
        "top5_sum_usd": round(sum(pnl[-5:]), 2),
        "bottom5_sum_usd": round(sum(pnl[:5]), 2),
        "trades_over_20_usd": sum(1 for x in pnl if x > 20.0),
        "liquidations": reasons.get("liquidation", 0),
        "exit_reasons": reasons,
    }


def main() -> None:
    """Publish every arm for every symbol; nothing is selected."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--venue-meta", type=Path, required=True)
    parser.add_argument("--execution-minutes", type=int, default=15)
    parser.add_argument("--leverage", type=float, default=8.0)
    parser.add_argument("--costs", nargs="+", default=["measured", "adverse"])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    meta = json.loads(args.venue_meta.read_text())["meta"]["universe"]
    venue_max = {row["name"]: float(row["maxLeverage"]) for row in meta}
    venue_max.update({"BTC": 40.0, "ETH": 25.0, "SOL": 20.0, "HYPE": 10.0})

    cells: list[dict[str, object]] = []
    for symbol in args.symbols:
        bars = xs.load_inputs(args.inputs, symbol)
        if bars is None:
            continue
        signals = xs.generic_donchian_signals(
            bars, execution_minutes=args.execution_minutes, signal_minutes=60
        )
        days = (bars.index.max() - bars.index.min()).total_seconds() / 86_400.0
        for cost in args.costs:
            for arm, policy in ARMS.items():
                trades = run_arm(
                    bars, signals, symbol, venue_max.get(symbol, 10.0), cost, args.leverage, policy
                )
                cells.append({"symbol": symbol, "cost": cost, "arm": arm, "days": round(days, 2),
                              **describe(trades, days)})
        row = {c["arm"]: c["net_usd"] for c in cells if c["symbol"] == symbol and c["cost"] == "measured"}
        print({"symbol": symbol, **row}, flush=True)
    args.out.write_text(json.dumps({
        "schema_version": 1, "execution_authority": "none", "automatic_promotion": False,
        "arms": {k: (None if v is None else [v.activation_bps, v.floor_bps, v.trailing_giveback_bps])
                 for k, v in ARMS.items()},
        "execution_minutes": args.execution_minutes, "leverage": args.leverage,
        "cells": cells,
        "limitations": [
            "The lock is evaluated on research bars, not the live one-minute candles; live will trigger more often.",
            "Lock exits fill at the next bar's open with modelled slippage; live latency is not modelled.",
            "Fixed $500 notional per trade; nothing here measures behaviour at the proposed SNDK size.",
            "Every window overlaps the 2026-09-17 to 09-19 rebound and a broadly rising tape.",
        ],
    }, indent=1))
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
