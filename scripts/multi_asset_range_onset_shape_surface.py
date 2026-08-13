"""Exit-shape robustness for the post-hoc SOL range-onset challenger."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import product
import math
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig
from multi_asset_range_onset_risk_surface import build_range_onset_signals
from multi_asset_trend_risk_surface import TrendRiskTrial, risk_config
from shared_strategy_screen import load_causal_window

_STOP_BPS = (40.0, 60.0, 80.0, 100.0)
_MAX_HOLD_HOURS = (24, 48, 96, None)


@dataclass(frozen=True)
class OnsetShape:
    """One local stop and maximum-hold hypothesis."""

    stop_bps: float
    max_hold_hours: int | None


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit chronological shape-surface command."""
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


def onset_shape_grid() -> tuple[OnsetShape, ...]:
    """Return the complete frozen local exit neighborhood."""
    return tuple(
        OnsetShape(stop, hold) for stop, hold in product(_STOP_BPS, _MAX_HOLD_HOURS)
    )


def onset_shape_config(
    shape: OnsetShape,
    *,
    symbol: str,
) -> SharedPortfolioConfig:
    """Build the fixed low-exposure venue execution contract."""
    trial = TrendRiskTrial(
        "1h",
        10,
        30,
        None,
        shape.stop_bps,
        shape.max_hold_hours,
        0.10,
        5.0,
    )
    return risk_config(trial, symbol=symbol)


def evaluate_onset_shapes(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    symbol: str,
    shapes: tuple[OnsetShape, ...],
) -> list[dict[str, object]]:
    """Evaluate and retain every requested exit shape."""
    results: list[dict[str, object]] = []
    for shape in shapes:
        report = evaluate_shared_bar_portfolio(
            bars,
            signals,
            onset_shape_config(shape, symbol=symbol),
        )
        results.append(_trial_summary(shape, report.to_dict()))
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
    shapes: tuple[OnsetShape, ...] | None = None,
) -> dict[str, object]:
    """Evaluate one fixed shape grid on independent and continuous slices."""
    bars, evidence = load_causal_window(
        bars_path,
        funding_paths,
        development_start,
        pseudo_holdout_end,
    )
    signals = build_range_onset_signals(bars)
    surface = shapes or onset_shape_grid()
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
    shapes: tuple[OnsetShape, ...],
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    mask = (bars.index >= start) & (bars.index < end)
    results = evaluate_onset_shapes(
        bars.loc[mask],
        signals.loc[mask],
        symbol=symbol,
        shapes=shapes,
    )
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "bar_rows": int(mask.sum()),
        "trial_count": len(results),
        "trials": results,
    }


def _trial_summary(
    shape: OnsetShape,
    report: dict[str, object],
) -> dict[str, object]:
    values = dict(report)
    raw_trades = values.pop("trades")
    if not isinstance(raw_trades, tuple):
        raise ValueError("portfolio trades must be a tuple")
    limitations = values.pop("limitations")
    return {
        "trial_id": _trial_id(shape),
        "shape": asdict(shape),
        "execution_authority": "none",
        "metrics": values,
        "by_side": _trade_side_summary(raw_trades),
        "exit_reasons": dict(
            sorted(Counter(str(trade["exit_reason"]) for trade in raw_trades).items())
        ),
        "limitations": limitations,
    }


def _trade_side_summary(
    raw_trades: tuple[dict[str, object], ...],
) -> dict[str, dict[str, object]]:
    """Return after-cost results without concealing either directional leg."""
    invalid = tuple(
        trade.get("direction")
        for trade in raw_trades
        if trade.get("direction") not in {"long", "short"}
    )
    if invalid:
        raise ValueError("trade direction must be long or short")
    result: dict[str, dict[str, object]] = {}
    for side in ("long", "short"):
        trades = tuple(trade for trade in raw_trades if trade["direction"] == side)
        net = tuple(_trade_number(trade, "net_pnl_usd") for trade in trades)
        gross_profit = sum(max(value, 0.0) for value in net)
        gross_loss = -sum(min(value, 0.0) for value in net)
        result[side] = {
            "trades": len(trades),
            "wins": sum(value > 0.0 for value in net),
            "losses": sum(value <= 0.0 for value in net),
            "net_pnl_usd": sum(net),
            "profit_factor": None if gross_loss == 0.0 else gross_profit / gross_loss,
            "fees_usd": sum(_trade_number(trade, "fees_usd") for trade in trades),
            "funding_cashflow_usd": sum(
                _trade_number(trade, "funding_cashflow_usd") for trade in trades
            ),
            "exit_reasons": dict(
                sorted(Counter(str(trade["exit_reason"]) for trade in trades).items())
            ),
        }
    return result


def _trade_number(trade: dict[str, object], field: str) -> float:
    """Return one finite numeric trade field or reject malformed evidence."""
    value = trade.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"trade {field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"trade {field} must be finite")
    return number


def _trial_id(shape: OnsetShape) -> str:
    hold = "none" if shape.max_hold_hours is None else str(shape.max_hold_hours)
    return f"stop={shape.stop_bps:g}__hold={hold}"


def _artifact(
    symbol: str,
    evidence: dict[str, object],
    shapes: tuple[OnsetShape, ...],
    segments: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "multi_asset_range_onset_shape_surface_post_hoc_report_only",
        "symbol": symbol.strip().upper(),
        "execution_authority": "none",
        "model_authority": "none",
        "initial_equity": 15_000.0,
        "trial_count": len(shapes),
        "fixed_signal": "1h_10x30_sma_cross_in_5m_RANGE_or_BREAKOUT",
        "fixed_risk": {"margin_fraction": 0.10, "leverage": 5.0},
        "data_evidence": evidence,
        **segments,
        "limitations": [
            "range-onset rule was discovered after inspecting the full-year baseline",
            "exit-shape ladder is local but inherits the post-hoc signal selection",
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
    """Run the grid and publish one immutable report-only artifact."""
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
