#!/usr/bin/env python3
"""Write one immutable, report-only Market Cipher/Hulk strategy artifact."""

from __future__ import annotations

import argparse
import json
import math
from numbers import Integral, Real
from pathlib import Path
from typing import Sequence

import pandas as pd

from hypervector.research.cipher_suite_duckdb import CIPHER_RESEARCH_SYMBOLS
from hypervector.research.market_cipher_strategy_research import (
    hulk_research_profile_names,
    market_cipher_robustness_names,
    run_market_cipher_strategy_research,
)


def _parser() -> argparse.ArgumentParser:
    """Build the explicit non-executable research command contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backtest-lab-root", required=True, type=Path)
    parser.add_argument("--mc-scalper-root", required=True, type=Path)
    parser.add_argument("--market-cipher-cli-root", required=True, type=Path)
    parser.add_argument(
        "--symbol",
        action="append",
        required=True,
        choices=CIPHER_RESEARCH_SYMBOLS,
    )
    parser.add_argument("--funding", action="append", required=True)
    parser.add_argument("--candle-bundle", action="append", default=[])
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--segment",
        required=True,
        choices=(
            "development",
            "validation",
            "pseudo_holdout",
            "backward_check",
            "robustness",
        ),
    )
    parser.add_argument(
        "--profile", required=True, choices=hulk_research_profile_names()
    )
    parser.add_argument(
        "--robustness", default="nominal", choices=market_cipher_robustness_names()
    )
    parser.add_argument("--bar-minutes", type=int, choices=(15, 30), default=30)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute and persist one immutable Hulk research run."""
    args = _parser().parse_args(argv)
    output = Path(args.out)
    signals_path = output.with_suffix(".signals.parquet")
    trades_path = output.with_suffix(".trades.parquet")
    _ensure_available(output, signals_path, trades_path)
    run = run_market_cipher_strategy_research(
        database_path=Path(args.database),
        backtest_lab_root=Path(args.backtest_lab_root),
        mc_scalper_root=Path(args.mc_scalper_root),
        market_cipher_cli_root=Path(args.market_cipher_cli_root),
        funding_by_symbol=_funding_map(args.funding),
        symbols=tuple(args.symbol),
        start_utc=_timestamp(args.start),
        end_utc=_timestamp(args.end),
        segment=str(args.segment),
        profile_name=str(args.profile),
        robustness_name=str(args.robustness),
        bar_minutes=int(args.bar_minutes),
        candle_bundles_by_symbol=_bundle_map(args.candle_bundle),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    run.signals.to_parquet(signals_path, index=False)
    run.trades.to_parquet(trades_path, index=False)
    output.write_text(
        json.dumps(_json_safe(run.report), indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote report-only Market Cipher strategy artifact: {output}")
    return 0


def _ensure_available(output: Path, *sidecars: Path) -> None:
    existing = [path for path in (output, *sidecars) if path.exists()]
    if existing:
        raise FileExistsError(
            "Market Cipher strategy output exists: "
            + ", ".join(str(path) for path in existing)
        )


def _funding_map(values: list[str]) -> dict[str, tuple[Path, ...]]:
    grouped: dict[str, list[Path]] = {}
    for value in values:
        symbol, separator, path = value.partition("=")
        normalized = symbol.strip().upper()
        if (
            not separator
            or normalized not in CIPHER_RESEARCH_SYMBOLS
            or not path.strip()
        ):
            supported = ", ".join(CIPHER_RESEARCH_SYMBOLS)
            raise ValueError(f"funding must use SYMBOL=PATH for: {supported}")
        grouped.setdefault(normalized, []).append(Path(path.strip()))
    return {symbol: tuple(paths) for symbol, paths in grouped.items()}


def _bundle_map(values: list[str]) -> dict[str, Path]:
    bundles: dict[str, Path] = {}
    for value in values:
        symbol, separator, path = value.partition("=")
        normalized = symbol.strip().upper()
        if (
            not separator
            or normalized not in CIPHER_RESEARCH_SYMBOLS
            or not path.strip()
            or normalized in bundles
        ):
            raise ValueError("candle bundle must uniquely use SYMBOL=PATH")
        bundles[normalized] = Path(path.strip())
    return bundles


def _timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError("Market Cipher timestamps must include a timezone")
    return timestamp.tz_convert("UTC")


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Market Cipher report contains non-finite numeric output")
        return number
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
