"""Friction stress for the post-hoc SOL range-onset challenger."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig
from multi_asset_range_onset_risk_surface import build_range_onset_signals
from multi_asset_trend_risk_surface import TrendRiskTrial, risk_config
from shared_strategy_screen import load_causal_window

_STOP_BPS = (60.0, 80.0)
_EXPOSURES = ((0.10, 5.0), (0.20, 15.0))
_SLIPPAGE_BPS_PER_SIDE = (2.0, 5.0, 10.0, 20.0)
_MAX_HOLD_HOURS = 48


@dataclass(frozen=True)
class OnsetFrictionTrial:
    """One stop, portfolio exposure, and adverse-slippage hypothesis."""

    stop_bps: float
    margin_fraction: float
    leverage: float
    slippage_bps: float

    @property
    def effective_exposure(self) -> float:
        """Return notional as a multiple of total portfolio equity."""
        return self.margin_fraction * self.leverage


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit chronological friction-stress command."""
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


def friction_grid() -> tuple[OnsetFrictionTrial, ...]:
    """Return the frozen local shape, exposure, and friction cross-product."""
    return tuple(
        OnsetFrictionTrial(stop, margin, leverage, slippage)
        for stop, (margin, leverage), slippage in product(
            _STOP_BPS,
            _EXPOSURES,
            _SLIPPAGE_BPS_PER_SIDE,
        )
    )


def friction_config(
    trial: OnsetFrictionTrial,
    *,
    symbol: str,
) -> SharedPortfolioConfig:
    """Build a venue contract with symmetric adverse market-fill stress."""
    shape = TrendRiskTrial(
        "1h",
        10,
        30,
        None,
        trial.stop_bps,
        _MAX_HOLD_HOURS,
        trial.margin_fraction,
        trial.leverage,
    )
    base = risk_config(shape, symbol=symbol)
    return replace(
        base,
        entry_slippage_bps=trial.slippage_bps,
        market_exit_slippage_bps=trial.slippage_bps,
        liquidation_slippage_bps=trial.slippage_bps,
    )


def evaluate_friction_trials(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    symbol: str,
    trials: tuple[OnsetFrictionTrial, ...],
) -> list[dict[str, object]]:
    """Evaluate and retain every requested friction observation."""
    results: list[dict[str, object]] = []
    for trial in trials:
        report = evaluate_shared_bar_portfolio(
            bars,
            signals,
            friction_config(trial, symbol=symbol),
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
    trials: tuple[OnsetFrictionTrial, ...] | None = None,
) -> dict[str, object]:
    """Evaluate one fixed friction grid on independent chronological slices."""
    bars, evidence = load_causal_window(
        bars_path,
        funding_paths,
        development_start,
        pseudo_holdout_end,
    )
    signals = build_range_onset_signals(bars)
    surface = trials or friction_grid()
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
    trials: tuple[OnsetFrictionTrial, ...],
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    mask = (bars.index >= start) & (bars.index < end)
    results = evaluate_friction_trials(
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
    trial: OnsetFrictionTrial,
    report: dict[str, object],
) -> dict[str, object]:
    values = dict(report)
    raw_trades = values.pop("trades")
    if not isinstance(raw_trades, tuple):
        raise ValueError("portfolio trades must be a tuple")
    limitations = values.pop("limitations")
    return {
        "trial_id": _trial_id(trial),
        "trial": asdict(trial),
        "effective_exposure": trial.effective_exposure,
        "slippage_bps_per_side": trial.slippage_bps,
        "execution_authority": "none",
        "metrics": values,
        "exit_reasons": dict(
            sorted(Counter(str(trade["exit_reason"]) for trade in raw_trades).items())
        ),
        "limitations": limitations,
    }


def _trial_id(trial: OnsetFrictionTrial) -> str:
    return (
        f"stop={trial.stop_bps:g}__exposure={trial.effective_exposure:g}__"
        f"slip={trial.slippage_bps:g}"
    )


def _artifact(
    symbol: str,
    evidence: dict[str, object],
    trials: tuple[OnsetFrictionTrial, ...],
    segments: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "multi_asset_range_onset_friction_surface_post_hoc_report_only",
        "symbol": symbol.strip().upper(),
        "execution_authority": "none",
        "model_authority": "none",
        "initial_equity": 15_000.0,
        "trial_count": len(trials),
        "fixed_signal": "1h_10x30_sma_cross_in_5m_RANGE_or_BREAKOUT",
        "stress_dimensions": {
            "stop_bps": list(_STOP_BPS),
            "effective_exposure": [0.5, 3.0],
            "slippage_bps_per_side": list(_SLIPPAGE_BPS_PER_SIDE),
        },
        "data_evidence": evidence,
        **segments,
        "limitations": [
            "range-onset rule was discovered after inspecting the full-year baseline",
            "fixed slippage is a stress proxy rather than observed depth impact",
            "bar simulation cannot establish event ordering within each minute",
            "promotion requires venue-event replay and fresh forward evidence",
        ],
    }


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != pd.Timedelta(0):
        raise argparse.ArgumentTypeError("timestamps must be UTC")
    return parsed.astimezone(UTC)


def main() -> int:
    """Run the stress grid and publish one immutable report-only artifact."""
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
