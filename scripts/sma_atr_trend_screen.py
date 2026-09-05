#!/usr/bin/env python3
"""Publish one immutable report-only V73 SMA/ATR asset screen."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.fixed_risk_signal_screen import (
    DEFAULT_PROFILES,
    FrictionProfile,
    add_fixed_risk_screen_arguments,
    build_fixed_risk_screen_report,
    evaluate_asset_profiles,
    fixed_risk_portfolio_config,
    scored_inputs as scored_inputs,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
)
from hypervector.research.sma_atr_trend_signals import (
    build_sma_atr_trend_signals,
)

_VENUE_MAX_LEVERAGE = {
    "BTC": 40.0,
    "ETH": 25.0,
    "SOL": 20.0,
    "HYPE": 10.0,
    "ZEC": 10.0,
    "xyz:SP500": 50.0,
    "xyz:SPCX": 20.0,
    "xyz:SNDK": 10.0,
    "xyz:BRENTOIL": 20.0,
}


PROFILES = DEFAULT_PROFILES


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded execution-incapable report command."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_fixed_risk_screen_arguments(parser)
    return parser


def portfolio_config(
    symbol: str,
    friction: FrictionProfile,
) -> SharedPortfolioConfig:
    """Return the exact V73 fixed-risk and all-taker lifecycle contract."""
    normalized = _supported_symbol(symbol)
    return fixed_risk_portfolio_config(
        symbol=normalized,
        venue_max_leverage=_VENUE_MAX_LEVERAGE[normalized],
        friction=friction,
        margin_fraction=0.20,
    )


def evaluate_asset(
    symbol: str,
    bars: pd.DataFrame,
    score_start: datetime | None = None,
) -> dict[str, object]:
    """Evaluate the frozen signal once under nominal and stress friction."""
    normalized = _supported_symbol(symbol)
    return evaluate_asset_profiles(
        symbol=normalized,
        bars=bars,
        signal_builder=build_sma_atr_trend_signals,
        config_builder=lambda profile: portfolio_config(normalized, profile),
        score_start=score_start,
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
    """Load one exact source-bar window and return immutable-report content."""
    normalized = _supported_symbol(symbol)
    mode, hypothesis_id = report_identity(symbol)
    return build_fixed_risk_screen_report(
        symbol=normalized,
        bars_path=bars_path,
        funding_paths=funding_paths,
        start=start,
        end=end,
        bars_timeframe=bars_timeframe,
        score_start=score_start,
        signal_builder=build_sma_atr_trend_signals,
        config_builder=lambda profile: portfolio_config(normalized, profile),
        mode=mode,
        hypothesis_id=hypothesis_id,
        limitations=(
            "single-asset isolated screen, not shared-account concurrency",
            "bar data cannot prove private IOC fill quality or gap behavior",
            "historical support is not a profit guarantee",
        ),
    )


def report_identity(symbol: str) -> tuple[str, str]:
    """Return the immutable experiment identity for one supported asset."""
    normalized = _supported_symbol(symbol)
    if normalized == "ZEC":
        return (
            "v74_zec_sma_atr_extension_report_only",
            "v74-seven-asset-zec-sma-atr-extension-20260901",
        )
    return (
        "v73_sma_atr_trend_report_only",
        "v73-eight-asset-sma-atr-trend-20260901",
    )


def _supported_symbol(symbol: str) -> str:
    value = symbol.strip()
    normalized = value if value.startswith("xyz:") else value.upper()
    if normalized not in _VENUE_MAX_LEVERAGE:
        raise ValueError(f"unsupported SMA/ATR trend symbol: {symbol}")
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
