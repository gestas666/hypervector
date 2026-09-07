"""Run the two frozen hourly mechanisms on exact local native inputs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.donchian_atr_breakout_signals import (
    DonchianAtrBreakoutConfig,
    build_donchian_atr_breakout_signals,
)
from hypervector.research.hip3_transfer_sources import attach_official_funding
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig
from hypervector.research.trade_activity import summarize_trade_activity

SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "xyz:SPCX", "xyz:SP500", "xyz:SNDK")
VENUE_MAX = dict(zip(SYMBOLS, (40, 25, 20, 10, 20, 50, 10), strict=True))
WINDOWS = (
    ("development", "2026-07-21T00:00Z", "2026-08-18T00:00Z"),
    ("chronological_extension", "2026-08-18T00:00Z", "2026-09-07T00:00Z"),
    ("continuous", "2026-07-21T00:00Z", "2026-09-07T00:00Z"),
)
COSTS = (("nominal", 2.5, 0.9), ("adverse", 5.5, 0.9), ("hip3_full_fee", 5.5, 9.0))
TRADE_COLUMNS = ("entry_time_utc", "exit_time_utc", "net_pnl_usd")


def execution_config(
    symbol: str, slip: float, hip3_fee: float
) -> SharedPortfolioConfig:
    """Return the preregistered capped research lifecycle and adverse costs."""
    fee = (hip3_fee if symbol.startswith("xyz:") else 4.5) / 10000
    return SharedPortfolioConfig(
        symbol=symbol,
        initial_equity=4857.58724349,
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


def run_case(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: SharedPortfolioConfig,
    window: tuple[str, str, str],
    variant: str,
    cost_name: str,
) -> dict[str, object]:
    """Retain each valid result including costs, censoring and side attribution."""
    name, first, last = window
    start, end = pd.Timestamp(first), pd.Timestamp(last)
    selected = (bars.index >= start) & (bars.index < end)
    result = evaluate_shared_bar_portfolio(
        bars.loc[selected], signals.loc[selected], config
    )
    rows = [asdict(trade) for trade in result.trades]
    trades = pd.DataFrame(rows) if rows else pd.DataFrame(columns=TRADE_COLUMNS)
    summary = summarize_trade_activity(trades, start=start, end=end)
    uncertain = {"data_gap", "end_of_data"}
    return {
        "symbol": config.symbol,
        "variant": variant,
        "cost": cost_name,
        "window": name,
        "start_utc": start.isoformat(),
        "end_exclusive_utc": end.isoformat(),
        "execution": asdict(config),
        "activity": summary,
        "by_side": _side_activity(trades, start, end),
        "signal_entries": int(
            signals.loc[selected, ["long_entry", "short_entry"]].sum().sum()
        ),
        "uncertain_exit_count": sum(
            trade.exit_reason in uncertain for trade in result.trades
        ),
        "ambiguous_exit_count": sum(
            trade.same_bar_ambiguous for trade in result.trades
        ),
        "net_excluding_uncertain_exits_usd": sum(
            trade.net_pnl_usd
            for trade in result.trades
            if trade.exit_reason not in uncertain
        ),
        "engine_result": result.to_dict(),
    }


def _side_activity(
    trades: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, object]:
    return {
        side: summarize_trade_activity(
            trades.loc[trades.direction.eq(side)] if len(trades) else trades,
            start=start,
            end=end,
        )
        for side in ("long", "short")
    }


def evaluate_symbol(directory: Path, symbol: str) -> list[dict[str, object]]:
    """Prepare one native chronology once and test the two fixed mechanisms."""
    source = directory / symbol.replace(":", "_")
    bars = pd.read_parquet(source / "bars.parquet")
    funding = pd.read_parquet(source / "funding.parquet")
    bars, evidence = attach_official_funding(bars, funding)
    if evidence.unassigned_event_count or evidence.delayed_event_count:
        raise ValueError(f"{symbol}: unexpected out-of-window funding")
    rows = []
    for entry, exit_channel in ((20, 10), (8, 4)):
        signal_config = DonchianAtrBreakoutConfig(
            entry_channel_bars=entry,
            exit_channel_bars=exit_channel,
            signal_hours=1,
        )
        signals = build_donchian_atr_breakout_signals(bars, signal_config)
        variant = f"hourly_donchian_{entry}_{exit_channel}_atr20"
        for cost, slip, hip3_fee in COSTS:
            config = execution_config(symbol, slip, hip3_fee)
            for window in WINDOWS:
                row = run_case(bars, signals, config, window, variant, cost)
                rows.append(row)
                if window[0] == "continuous":
                    print(
                        {
                            key: row[key]
                            for key in ("symbol", "variant", "cost", "activity")
                        },
                        flush=True,
                    )
    return rows


def main() -> None:
    """Publish the complete bounded screen without modifying runtime settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    cases = [
        row for symbol in SYMBOLS for row in evaluate_symbol(args.input_dir, symbol)
    ]
    sources = [
        Path(__file__),
        Path("docs/research/frequency-noncrypto-protocol-20260907.md"),
    ]
    sources.extend(sorted(args.input_dir.rglob("*.parquet")))
    sources.append(args.input_dir / "manifest.json")
    write_immutable_json(
        args.out,
        {
            "schema_version": 1,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "cases": cases,
            "evidence": {str(path.resolve()): file_evidence(path) for path in sources},
            "limitations": [
                "Previously observed chronology; exploratory partitions, not pristine OOS.",
                "Native trade candles plus adverse slippage are conditional fills, not private execution.",
                "Funding marks and liquidation paths use candle-price proxies.",
                "Each asset is screened independently; summed activity does not establish shared-account solvency.",
                "Cash-session holidays and thin external-market hours remain included and must be attributed.",
            ],
        },
    )


if __name__ == "__main__":
    main()
