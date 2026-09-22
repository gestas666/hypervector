"""Frozen V92 entry/failure comparisons; offline, with no execution authority."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

import pandas as pd

from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.v92_entry_candidates import build_v92_signals
from hypervector.research.v92_failure_replay import (
    FailureReplay,
    replay_failed_followthrough,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioTrade
from v90_expansion_screen import load_inputs, portfolio_config, buy_and_hold

SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
    "xyz:TSLA",
)
VENUE_MAX = dict(zip(SYMBOLS, (40, 25, 20, 10, 20, 10, 20, 20), strict=True))
CANDIDATES = ("donchian", "donchian_bounded", "trend", "trend_long")
COSTS = ("measured", "adverse")


def main() -> int:
    """Write immutable summaries and trade rows for every predeclared variant."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--supplemental-inputs", type=Path)
    parser.add_argument("--symbols", nargs="+", choices=SYMBOLS, default=SYMBOLS)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cells: list[dict[str, object]] = []
    inputs: dict[str, object] = {}
    sources = _sources(args.inputs, args.supplemental_inputs, tuple(args.symbols))
    for symbol in args.symbols:
        bars = load_inputs(sources[symbol], symbol)
        if bars is None:
            raise ValueError(f"missing preregistered symbol: {symbol}")
        gaps = (
            bars.index.to_series().diff().div(pd.Timedelta(minutes=15)).sub(1).fillna(0)
        )
        bars["gap_before_bars"] = gaps.clip(lower=0).astype(int)
        inputs[symbol] = _input_manifest(sources[symbol], symbol, bars)
        for candidate in CANDIDATES:
            signals = build_v92_signals(
                bars, "trend" if candidate == "trend_long" else candidate
            )
            if candidate == "trend_long":
                signals.loc[signals.short_entry, "entry_direction"] = None
                signals["short_entry"] = False
            for cost in COSTS:
                cell = _evaluate(symbol, candidate, cost, bars, signals, args.output)
                cells.append(cell)
                _progress(cell)
    _write(
        args.output / "report.json",
        {
            "execution_authority": "none",
            "inputs": inputs,
            "cells": cells,
            "limitations": [
                "Previously examined history, not an untouched holdout",
                "Mechanism comparison, not full V91 replay",
                "Fixed-entry failure overlay omits new freed-capital entries",
                "15-minute OHLC lacks tick ordering and historical orderbook; native barrier ordering is conservative",
                "Per-symbol drawdowns cannot be added to obtain portfolio drawdown",
            ],
        },
    )
    return 0


def _sources(
    primary: Path, supplemental: Path | None, symbols: tuple[str, ...]
) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for symbol in symbols:
        directory = symbol.replace(":", "_")
        root = primary
        if (
            not (root / directory / "bars.parquet").exists()
            and supplemental is not None
        ):
            root = supplemental
        if not all(
            (root / directory / name).is_file()
            for name in ("bars.parquet", "funding.parquet")
        ):
            raise ValueError(
                f"missing preregistered symbol: {symbol}; supply --supplemental-inputs"
            )
        result[symbol] = root
    return result


def _input_manifest(root: Path, symbol: str, bars: pd.DataFrame) -> dict[str, object]:
    directory = root / symbol.replace(":", "_")
    return {
        "source": str(directory),
        "first": str(bars.index[0]),
        "last": str(bars.index[-1]),
        "rows": len(bars),
        "missing_bars": int(bars.gap_before_bars.sum()),
        "hashes": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("bars.parquet", "funding.parquet")
        },
    }


def _evaluate(
    symbol: str,
    candidate: str,
    cost: str,
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    output: Path,
) -> dict[str, object]:
    config = replace(
        portfolio_config(symbol, VENUE_MAX[symbol], cost, 86400),
        same_direction_reentry_requires_reset=False,
    )
    report = evaluate_shared_bar_portfolio(bars, signals, config)
    overlay = [replay_failed_followthrough(bars, t, config) for t in report.trades]
    blocks, failure_blocks = _blocks(bars, report.trades, overlay)
    name = f"{symbol.replace(':', '_')}_{candidate}_{cost}.json"
    _write(
        output / name,
        {
            "config": asdict(config),
            "trades": [asdict(t) for t in report.trades],
            "failure_overlay": [asdict(f) for f in overlay],
        },
    )
    return {
        "symbol": symbol,
        "candidate": candidate,
        "cost": cost,
        "trades": report.completed_trades,
        "net_usd": report.net_pnl_usd,
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "worst_trade_usd": min((t.net_pnl_usd for t in report.trades), default=None),
        "profit_factor": report.profit_factor,
        "blocks_net_usd": blocks,
        "buy_hold_net_usd": buy_and_hold(bars, symbol, cost),
        "refused_extended_signals": int(signals.entry_rejected_extension.sum()),
        "failure_net_usd": sum(f.counterfactual_net_usd for f in overlay),
        "failure_blocks_net_usd": failure_blocks,
        "failure_changed": sum(f.changed for f in overlay),
        "failure_cut_winners": sum(
            f.changed
            and f.original_net_usd > 0
            and f.counterfactual_net_usd < f.original_net_usd
            for f in overlay
        ),
        "exit_reasons": dict(Counter(t.exit_reason for t in report.trades)),
        "trades_file": name,
    }


def _blocks(
    bars: pd.DataFrame,
    trades: tuple[SharedPortfolioTrade, ...],
    overlay: list[FailureReplay],
) -> tuple[list[float], list[float]]:
    edges = pd.date_range(
        bars.index[0], bars.index[-1] + pd.Timedelta(minutes=15), periods=4
    )
    blocks = [
        sum(
            t.net_pnl_usd
            for t in trades
            if edges[i] <= pd.Timestamp(t.entry_time_utc) < edges[i + 1]
        )
        for i in range(3)
    ]
    failure_blocks = [
        sum(
            f.counterfactual_net_usd
            for t, f in zip(trades, overlay, strict=True)
            if edges[i] <= pd.Timestamp(t.entry_time_utc) < edges[i + 1]
        )
        for i in range(3)
    ]
    return blocks, failure_blocks


def _progress(cell: dict[str, object]) -> None:
    fields = ("symbol", "candidate", "cost", "trades", "net_usd", "failure_net_usd")
    print(json.dumps({key: cell[key] for key in fields}), flush=True)


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
