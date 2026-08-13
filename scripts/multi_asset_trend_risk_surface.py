"""Chronological risk surface for surviving multi-asset trend shapes."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig
from hypervector.research.shared_strategy_signals import (
    build_registered_strategy_pair_on_timeframe,
)
from shared_strategy_screen import (
    ScreenProfile,
    load_causal_window,
    profile_config,
)

_SURVIVING_SHAPES = (
    ("1h", 10, 30, None, 60.0, 96),
    ("1h", 10, 30, None, 60.0, None),
    ("1h", 10, 30, None, 60.0, 48),
    ("1h", 10, 30, None, 40.0, 96),
)
_MARGIN_FRACTIONS = (0.10, 0.20, 0.35, 0.50, 0.70, 1.00)
_LEVERAGES = (5.0, 10.0, 15.0, 20.0)


@dataclass(frozen=True)
class TrendRiskTrial:
    """One fixed trend shape and isolated exposure hypothesis."""

    timeframe: str
    fast: int
    slow: int
    target_bps: float | None
    stop_bps: float | None
    max_hold_hours: int | None
    margin_fraction: float
    leverage: float


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit chronological risk-surface command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--funding", type=Path, action="append", required=True)
    parser.add_argument("--development-start", type=_utc_datetime, required=True)
    parser.add_argument("--development-end", type=_utc_datetime, required=True)
    parser.add_argument("--validation-end", type=_utc_datetime, required=True)
    parser.add_argument("--pseudo-holdout-end", type=_utc_datetime, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def risk_trial_grid() -> tuple[TrendRiskTrial, ...]:
    """Return every predeclared shape, margin, and leverage combination."""
    return tuple(
        TrendRiskTrial(*shape, margin, leverage)
        for shape, margin, leverage in product(
            _SURVIVING_SHAPES,
            _MARGIN_FRACTIONS,
            _LEVERAGES,
        )
    )


def risk_config(trial: TrendRiskTrial, *, symbol: str) -> SharedPortfolioConfig:
    """Build an asset-specific contract while preserving price-space barriers."""
    hold_minutes = (
        trial.max_hold_hours * 60 if trial.max_hold_hours is not None else None
    )
    profile = ScreenProfile(
        "trend_risk",
        trial.margin_fraction,
        trial.leverage,
        trial.target_bps,
        trial.stop_bps,
        hold_minutes,
    )
    return profile_config(
        profile,
        symbol=symbol,
        bar_minutes=1,
    )


def evaluate_risk_trials(
    minute_bars: pd.DataFrame,
    *,
    symbol: str,
    trials: tuple[TrendRiskTrial, ...],
) -> list[dict[str, object]]:
    """Evaluate and retain every requested risk trial."""
    signal_cache: dict[tuple[str, int, int], pd.DataFrame] = {}
    results: list[dict[str, object]] = []
    for trial in trials:
        key = (trial.timeframe, trial.fast, trial.slow)
        signals = _cached_signals(minute_bars, trial, key, signal_cache)
        report = evaluate_shared_bar_portfolio(
            minute_bars,
            signals,
            risk_config(trial, symbol=symbol),
        )
        results.append(_result_summary(trial, report.to_dict()))
    return results


def run_surface(
    *,
    symbol: str,
    bars_path: Path,
    funding_paths: list[Path],
    development_start: datetime,
    development_end: datetime,
    validation_end: datetime,
    pseudo_holdout_end: datetime,
    trials: tuple[TrendRiskTrial, ...] | None = None,
) -> dict[str, object]:
    """Evaluate one fixed risk grid on independent and continuous intervals."""
    search_trials = trials or risk_trial_grid()
    boundaries = (
        ("development", development_start, development_end),
        ("validation", development_end, validation_end),
        ("pseudo_holdout", validation_end, pseudo_holdout_end),
        ("continuous", development_start, pseudo_holdout_end),
    )
    segments = {
        name: _evaluate_window(
            symbol,
            bars_path,
            funding_paths,
            start,
            end,
            search_trials,
        )
        for name, start, end in boundaries
    }
    return _artifact(symbol, search_trials, segments)


def _cached_signals(
    minute_bars: pd.DataFrame,
    trial: TrendRiskTrial,
    key: tuple[str, int, int],
    cache: dict[tuple[str, int, int], pd.DataFrame],
) -> pd.DataFrame:
    signals = cache.get(key)
    if signals is None:
        signals = build_registered_strategy_pair_on_timeframe(
            minute_bars,
            timeframe=trial.timeframe,
            long_strategy_name="ma_cross_long",
            short_strategy_name="ma_cross_short",
            long_params={"fast": trial.fast, "slow": trial.slow},
            short_params={"fast": trial.fast, "slow": trial.slow},
        )
        cache[key] = signals
    return signals


def _evaluate_window(
    symbol: str,
    bars_path: Path,
    funding_paths: list[Path],
    start: datetime,
    end: datetime,
    trials: tuple[TrendRiskTrial, ...],
) -> dict[str, object]:
    bars, evidence = load_causal_window(bars_path, funding_paths, start, end)
    results = evaluate_risk_trials(bars, symbol=symbol, trials=trials)
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "trial_count": len(results),
        "data_evidence": evidence,
        "trials": results,
    }


def _result_summary(
    trial: TrendRiskTrial, report: dict[str, object]
) -> dict[str, object]:
    values = dict(report)
    raw_trades = values.pop("trades")
    if not isinstance(raw_trades, tuple):
        raise ValueError("portfolio trades must be a tuple")
    limitations = values.pop("limitations")
    exit_reasons = Counter(str(trade["exit_reason"]) for trade in raw_trades)
    return {
        "trial_id": _trial_id(trial),
        "shape": _shape_dict(trial),
        "risk": {
            "margin_fraction": trial.margin_fraction,
            "leverage": trial.leverage,
        },
        "execution_authority": "none",
        "metrics": values,
        "exit_reasons": dict(sorted(exit_reasons.items())),
        "limitations": limitations,
    }


def _shape_dict(trial: TrendRiskTrial) -> dict[str, object]:
    values = asdict(trial)
    values.pop("margin_fraction")
    values.pop("leverage")
    return values


def _artifact(
    symbol: str,
    trials: tuple[TrendRiskTrial, ...],
    segments: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "multi_asset_trend_risk_surface_report_only",
        "symbol": symbol.strip().upper(),
        "execution_authority": "none",
        "model_authority": "none",
        "initial_equity": 15_000.0,
        "trial_count": len(trials),
        "risk_dimensions": {
            "margin_fractions": list(_MARGIN_FRACTIONS),
            "leverages": list(_LEVERAGES),
        },
        **segments,
        "limitations": [
            "bar simulation cannot establish maker queue rank or market impact",
            "pseudo-holdout was observed during the preceding shape search",
            "the surface reports every risk trial and grants no execution authority",
            "promotion requires venue-event replay and fresh forward shadow evidence",
        ],
    }


def _trial_id(trial: TrendRiskTrial) -> str:
    target = _optional_token(trial.target_bps)
    stop = _optional_token(trial.stop_bps)
    hold = _optional_token(trial.max_hold_hours)
    return (
        f"tf={trial.timeframe}__ma={trial.fast}x{trial.slow}__target={target}__"
        f"stop={stop}__hold={hold}__margin={trial.margin_fraction:g}__"
        f"lev={trial.leverage:g}"
    )


def _optional_token(value: float | int | None) -> str:
    return "none" if value is None else f"{value:g}"


def _timeframe_minutes(timeframe: str) -> int:
    delta = pd.Timedelta(timeframe)
    minute = pd.Timedelta(minutes=1)
    if delta < minute or delta % minute != pd.Timedelta(0):
        raise ValueError("timeframe must be whole positive minutes")
    return int(delta / minute)


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != pd.Timedelta(0):
        raise argparse.ArgumentTypeError("timestamps must be UTC")
    return parsed.astimezone(UTC)


def main() -> int:
    """Run the surface and publish one immutable report-only artifact."""
    args = build_parser().parse_args()
    report = run_surface(
        symbol=args.symbol,
        bars_path=args.bars,
        funding_paths=args.funding,
        development_start=args.development_start,
        development_end=args.development_end,
        validation_end=args.validation_end,
        pseudo_holdout_end=args.pseudo_holdout_end,
    )
    write_immutable_json(args.output, report)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
