#!/usr/bin/env python3
"""Publish one immutable report-only V75 Donchian/ATR asset screen."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.donchian_atr_breakout_signals import (
    build_donchian_atr_breakout_signals,
)
from hypervector.research.fixed_risk_signal_screen import (
    DEFAULT_PROFILES,
    FrictionProfile,
    add_fixed_risk_screen_arguments,
    build_fixed_risk_screen_report,
    fixed_risk_portfolio_config,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig

_VENUE_MAX_LEVERAGE = {
    "BTC": 40.0,
    "ETH": 25.0,
    "SOL": 20.0,
    "HYPE": 10.0,
    "ZEC": 10.0,
}

PROFILES = DEFAULT_PROFILES


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded execution-incapable V75 report command."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_fixed_risk_screen_arguments(parser)
    return parser


def portfolio_config(
    symbol: str,
    friction: FrictionProfile,
) -> SharedPortfolioConfig:
    """Return the exact V75 fixed-risk and all-taker lifecycle contract."""
    normalized = supported_symbol(symbol)
    return fixed_risk_portfolio_config(
        symbol=normalized,
        venue_max_leverage=_VENUE_MAX_LEVERAGE[normalized],
        friction=friction,
        margin_fraction=0.15,
    )


def run_screen(
    *,
    symbol: str,
    bars_path: Path,
    funding_paths: list[Path],
    start: datetime,
    end: datetime,
    bars_timeframe: str = "1min",
    score_start: datetime | None = None,
) -> dict[str, object]:
    """Load one exact source window and return V75 report content."""
    normalized = supported_symbol(symbol)
    return build_fixed_risk_screen_report(
        symbol=normalized,
        bars_path=bars_path,
        funding_paths=funding_paths,
        start=start,
        end=end,
        bars_timeframe=bars_timeframe,
        score_start=score_start,
        signal_builder=build_donchian_atr_breakout_signals,
        config_builder=lambda profile: portfolio_config(normalized, profile),
        mode="v75_donchian_atr_breakout_report_only",
        hypothesis_id="v75-five-crypto-donchian-atr-breakout-20260901",
        limitations=(
            "single-asset isolated screen, not shared-account concurrency",
            "bar data cannot prove private IOC fill quality or gap behavior",
            "historical support is not a profit guarantee",
        ),
    )


def supported_symbol(symbol: str) -> str:
    """Normalize and validate one V75 crypto symbol."""
    normalized = symbol.strip().upper()
    if normalized not in _VENUE_MAX_LEVERAGE:
        raise ValueError(f"unsupported V75 symbol: {symbol}")
    return normalized


def main(argv: list[str] | None = None) -> int:
    """Run one bounded asset screen and publish its immutable report."""
    args = build_parser().parse_args(argv)
    report = run_screen(
        symbol=args.symbol,
        bars_path=args.bars,
        funding_paths=args.funding,
        start=args.start,
        end=args.end,
        bars_timeframe=args.bars_timeframe,
        score_start=args.score_start,
    )
    write_immutable_json(args.output, report)
    print(json.dumps({"output": str(args.output.resolve()), "status": "published"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
