"""Mechanical risk ladder for the post-hoc SOL range-onset challenger."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.range_onset_signals import (
    build_range_onset_signals as _build_range_onset_signals,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig
from multi_asset_trend_risk_surface import TrendRiskTrial, risk_config
from shared_strategy_screen import load_causal_window

_EXPOSURES = (
    (0.10, 5.0),
    (0.10, 10.0),
    (0.10, 15.0),
    (0.10, 20.0),
    (0.20, 15.0),
    (0.35, 10.0),
    (0.20, 20.0),
    (0.50, 10.0),
    (0.35, 20.0),
    (0.50, 20.0),
)


@dataclass(frozen=True)
class OnsetRiskTrial:
    """One isolated margin and leverage hypothesis for the onset signal."""

    margin_fraction: float
    leverage: float

    @property
    def effective_exposure(self) -> float:
        """Return notional as a multiple of total portfolio equity."""
        return self.margin_fraction * self.leverage


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit chronological onset-risk command."""
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


def onset_risk_grid() -> tuple[OnsetRiskTrial, ...]:
    """Return the frozen effective-exposure ladder."""
    return tuple(OnsetRiskTrial(margin, leverage) for margin, leverage in _EXPOSURES)


def onset_risk_config(
    trial: OnsetRiskTrial,
    *,
    symbol: str,
) -> SharedPortfolioConfig:
    """Build the venue-specific 60-bps-stop execution contract."""
    shape = TrendRiskTrial(
        "1h",
        10,
        30,
        None,
        60.0,
        48,
        trial.margin_fraction,
        trial.leverage,
    )
    return risk_config(shape, symbol=symbol)


def build_range_onset_signals(bars: pd.DataFrame) -> pd.DataFrame:
    """Retain one-hour crosses occurring in a 5-minute range or breakout."""
    return _build_range_onset_signals(bars)


def evaluate_onset_risk(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    symbol: str,
    trials: tuple[OnsetRiskTrial, ...],
) -> list[dict[str, object]]:
    """Evaluate and retain every requested exposure trial."""
    results: list[dict[str, object]] = []
    for trial in trials:
        report = evaluate_shared_bar_portfolio(
            bars,
            signals,
            onset_risk_config(trial, symbol=symbol),
        )
        results.append(_trial_summary(trial, report.to_dict()))
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
    trials: tuple[OnsetRiskTrial, ...] | None = None,
) -> dict[str, object]:
    """Evaluate one fixed exposure ladder on independent and continuous slices."""
    bars, evidence = load_causal_window(
        bars_path,
        funding_paths,
        development_start,
        pseudo_holdout_end,
    )
    signals = build_range_onset_signals(bars)
    surface = trials or onset_risk_grid()
    boundaries = (
        ("development", development_start, development_end),
        ("validation", development_end, validation_end),
        ("pseudo_holdout", validation_end, pseudo_holdout_end),
        ("continuous", development_start, pseudo_holdout_end),
    )
    segments = {
        name: _segment(bars, signals, symbol, surface, start, end)
        for name, start, end in boundaries
    }
    return _artifact(symbol, evidence, surface, segments)


def _segment(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    symbol: str,
    trials: tuple[OnsetRiskTrial, ...],
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    mask = (bars.index >= start) & (bars.index < end)
    results = evaluate_onset_risk(
        bars.loc[mask],
        signals.loc[mask],
        symbol=symbol,
        trials=trials,
    )
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "bar_rows": int(mask.sum()),
        "trial_count": len(results),
        "trials": results,
    }


def _trial_summary(
    trial: OnsetRiskTrial,
    report: dict[str, object],
) -> dict[str, object]:
    values = dict(report)
    raw_trades = values.pop("trades")
    if not isinstance(raw_trades, tuple):
        raise ValueError("portfolio trades must be a tuple")
    limitations = values.pop("limitations")
    return {
        "trial_id": _trial_id(trial),
        "margin_fraction": trial.margin_fraction,
        "leverage": trial.leverage,
        "effective_exposure": trial.effective_exposure,
        "execution_authority": "none",
        "metrics": values,
        "exit_reasons": dict(
            sorted(Counter(str(trade["exit_reason"]) for trade in raw_trades).items())
        ),
        "limitations": limitations,
    }


def _trial_id(trial: OnsetRiskTrial) -> str:
    return f"margin={trial.margin_fraction:g}__lev={trial.leverage:g}"


def _artifact(
    symbol: str,
    evidence: dict[str, object],
    trials: tuple[OnsetRiskTrial, ...],
    segments: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "multi_asset_range_onset_risk_surface_post_hoc_report_only",
        "symbol": symbol.strip().upper(),
        "execution_authority": "none",
        "model_authority": "none",
        "initial_equity": 15_000.0,
        "trial_count": len(trials),
        "signal_contract": {
            "timeframe": "1h",
            "moving_average": "10x30_sma_cross",
            "entry_regime": "5m_RANGE_or_BREAKOUT",
            "target_bps": None,
            "stop_bps": 60.0,
            "max_hold_hours": 48,
        },
        "data_evidence": evidence,
        **segments,
        "limitations": [
            "range-onset rule was discovered after inspecting the full-year baseline",
            "risk scaling is mechanical but inherits the post-hoc signal selection",
            "bar simulation cannot establish queue rank or depth-constrained impact",
            "promotion requires venue-event replay and fresh forward evidence",
        ],
    }


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != pd.Timedelta(0):
        raise argparse.ArgumentTypeError("timestamps must be UTC")
    return parsed.astimezone(UTC)


def main() -> int:
    """Run the ladder and publish one immutable report-only artifact."""
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
