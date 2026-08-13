"""Bounded point-in-time trend-shape robustness search for Hyperliquid assets."""

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
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)
from hypervector.research.shared_strategy_signals import (
    build_registered_strategy_pair_signals,
)
from shared_strategy_screen import (
    ScreenProfile,
    load_causal_window,
    profile_config,
    resample_execution_bars,
)

_TIMEFRAMES = ("30min", "1h", "2h", "4h")
_MA_PAIRS = ((5, 20), (10, 30), (20, 50), (21, 55))
_TARGET_BPS = (None, 80.0, 150.0, 300.0)
_STOP_BPS = (None, 40.0, 60.0, 100.0)
_MAX_HOLD_HOURS = (None, 24, 48, 96)


@dataclass(frozen=True)
class TrendShape:
    """One predeclared moving-average and exit-shape hypothesis."""

    timeframe: str
    fast: int
    slow: int
    target_bps: float | None
    stop_bps: float | None
    max_hold_hours: int | None


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit chronological robustness-search command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--funding", type=Path, action="append", required=True)
    parser.add_argument("--development-start", type=_utc_datetime, required=True)
    parser.add_argument("--development-end", type=_utc_datetime, required=True)
    parser.add_argument("--validation-end", type=_utc_datetime, required=True)
    parser.add_argument("--pseudo-holdout-end", type=_utc_datetime, required=True)
    parser.add_argument("--selection-limit", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def trend_shape_grid() -> tuple[TrendShape, ...]:
    """Return the complete immutable exploration grid."""
    shapes: list[TrendShape] = []
    for timeframe, pair, target, stop, max_hold in product(
        _TIMEFRAMES,
        _MA_PAIRS,
        _TARGET_BPS,
        _STOP_BPS,
        _MAX_HOLD_HOURS,
    ):
        shapes.append(TrendShape(timeframe, pair[0], pair[1], target, stop, max_hold))
    return tuple(shapes)


def select_development_trials(
    trials: list[dict[str, object]], *, limit: int
) -> dict[str, object]:
    """Rank eligible development trials without deleting any observation."""
    if limit < 1:
        raise ValueError("selection limit must be positive")
    ranked = sorted(
        (trial for trial in trials if _selection_eligible(trial)),
        key=lambda trial: (-_selection_score(trial), _trial_id(trial)),
    )
    return {
        "searched_trial_count": len(trials),
        "eligible_trial_count": len(ranked),
        "selected_trial_ids": [_trial_id(trial) for trial in ranked[:limit]],
        "selection_rule": (
            "positive_return_profit_factor_above_one_minimum_30_trades_"
            "zero_liquidations_ranked_by_return_over_drawdown"
        ),
    }


def shape_config(shape: TrendShape, *, symbol: str) -> SharedPortfolioConfig:
    """Translate one shape into the fixed low-exposure screening contract."""
    hold_minutes = (
        shape.max_hold_hours * 60 if shape.max_hold_hours is not None else None
    )
    profile = ScreenProfile(
        "trend_shape",
        0.10,
        5.0,
        shape.target_bps,
        shape.stop_bps,
        hold_minutes,
    )
    return profile_config(
        profile,
        symbol=symbol,
        bar_minutes=_timeframe_minutes(shape.timeframe),
    )


def evaluate_shapes(
    minute_bars: pd.DataFrame,
    *,
    symbol: str,
    shapes: tuple[TrendShape, ...],
) -> list[dict[str, object]]:
    """Evaluate every requested shape and retain every resulting trial."""
    bar_cache: dict[str, pd.DataFrame] = {}
    signal_cache: dict[tuple[str, int, int], pd.DataFrame] = {}
    trials: list[dict[str, object]] = []
    for shape in shapes:
        bars = bar_cache.get(shape.timeframe)
        if bars is None:
            bars = resample_execution_bars(minute_bars, shape.timeframe)
            bar_cache[shape.timeframe] = bars
        signal_key = (shape.timeframe, shape.fast, shape.slow)
        if signal_key not in signal_cache:
            signal_cache[signal_key] = build_registered_strategy_pair_signals(
                bars,
                long_strategy_name="ma_cross_long",
                short_strategy_name="ma_cross_short",
                long_params={"fast": shape.fast, "slow": shape.slow},
                short_params={"fast": shape.fast, "slow": shape.slow},
            )
        report = evaluate_shared_bar_portfolio(
            bars,
            signal_cache[signal_key],
            shape_config(shape, symbol=symbol),
        )
        trials.append(_trial_summary(shape, report))
    return trials


def run_robustness(
    *,
    symbol: str,
    bars_path: Path,
    funding_paths: list[Path],
    development_start: datetime,
    development_end: datetime,
    validation_end: datetime,
    pseudo_holdout_end: datetime,
    shapes: tuple[TrendShape, ...] | None = None,
    selection_limit: int = 12,
) -> dict[str, object]:
    """Search development and evaluate selected shapes on later windows."""
    search_shapes = shapes or trend_shape_grid()
    development = _evaluate_window(
        symbol,
        bars_path,
        funding_paths,
        development_start,
        development_end,
        search_shapes,
    )
    trials = _trials(development)
    selection = select_development_trials(trials, limit=selection_limit)
    selected = _selected_shapes(search_shapes, selection)
    validation = _evaluate_window(
        symbol,
        bars_path,
        funding_paths,
        development_end,
        validation_end,
        selected,
    )
    pseudo_holdout = _evaluate_window(
        symbol,
        bars_path,
        funding_paths,
        validation_end,
        pseudo_holdout_end,
        selected,
    )
    return _artifact(symbol, development, selection, validation, pseudo_holdout)


def _evaluate_window(
    symbol: str,
    bars_path: Path,
    funding_paths: list[Path],
    start: datetime,
    end: datetime,
    shapes: tuple[TrendShape, ...],
) -> dict[str, object]:
    bars, evidence = load_causal_window(bars_path, funding_paths, start, end)
    trials = evaluate_shapes(bars, symbol=symbol, shapes=shapes)
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "trial_count": len(trials),
        "data_evidence": evidence,
        "trials": trials,
    }


def _selected_shapes(
    shapes: tuple[TrendShape, ...], selection: dict[str, object]
) -> tuple[TrendShape, ...]:
    raw_ids = selection.get("selected_trial_ids")
    if not isinstance(raw_ids, list) or not all(
        isinstance(value, str) for value in raw_ids
    ):
        raise ValueError("selection must contain string trial IDs")
    by_id = {_shape_id(shape): shape for shape in shapes}
    return tuple(by_id[trial_id] for trial_id in raw_ids)


def _artifact(
    symbol: str,
    development: dict[str, object],
    selection: dict[str, object],
    validation: dict[str, object],
    pseudo_holdout: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "multi_asset_trend_shape_robustness_report_only",
        "symbol": symbol.upper(),
        "execution_authority": "none",
        "model_authority": "none",
        "initial_equity": 15_000.0,
        "development": development,
        "selection": selection,
        "validation": validation,
        "pseudo_holdout": pseudo_holdout,
        "limitations": [
            "bar simulation cannot establish maker queue rank or market impact",
            "pseudo-holdout follows prior broad screening and is not pristine",
            "risk scaling is fixed at 10% margin and 5x in this shape search",
            "no result changes runtime strategy, model, or execution authority",
        ],
    }


def _trials(segment: dict[str, object]) -> list[dict[str, object]]:
    value = segment.get("trials")
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError("segment trials must be a list of objects")
    return value


def _trial_summary(
    shape: TrendShape, report: SharedPortfolioReport
) -> dict[str, object]:
    values = report.to_dict()
    trades = report.trades
    values.pop("trades")
    limitations = values.pop("limitations")
    return {
        "trial_id": _shape_id(shape),
        "shape": asdict(shape),
        "execution_authority": "none",
        "metrics": values,
        "exit_reasons": dict(
            sorted(Counter(trade.exit_reason for trade in trades).items())
        ),
        "limitations": limitations,
    }


def _shape_id(shape: TrendShape) -> str:
    target = _optional_token(shape.target_bps)
    stop = _optional_token(shape.stop_bps)
    hold = "none" if shape.max_hold_hours is None else str(shape.max_hold_hours)
    return (
        f"tf={shape.timeframe}__ma={shape.fast}x{shape.slow}__"
        f"target={target}__stop={stop}__hold={hold}"
    )


def _optional_token(value: float | None) -> str:
    return "none" if value is None else f"{value:g}"


def _timeframe_minutes(timeframe: str) -> int:
    delta = pd.Timedelta(timeframe)
    minute = pd.Timedelta(minutes=1)
    if delta < minute or delta % minute != pd.Timedelta(0):
        raise ValueError("timeframe must be whole positive minutes")
    return int(delta / minute)


def _selection_eligible(trial: dict[str, object]) -> bool:
    metrics = _metrics(trial)
    profit_factor = _number(metrics, "profit_factor")
    return (
        _number(metrics, "return_pct") > 0.0
        and profit_factor > 1.0
        and _integer(metrics, "completed_trades") >= 30
        and _integer(metrics, "liquidations") == 0
        and metrics.get("insolvent") is False
    )


def _selection_score(trial: dict[str, object]) -> float:
    metrics = _metrics(trial)
    drawdown = abs(_number(metrics, "maximum_drawdown_pct"))
    return _number(metrics, "return_pct") / max(drawdown, 0.01)


def _metrics(trial: dict[str, object]) -> dict[str, object]:
    value = trial.get("metrics")
    if not isinstance(value, dict):
        raise ValueError("trial metrics must be an object")
    return value


def _trial_id(trial: dict[str, object]) -> str:
    value = trial.get("trial_id")
    if not isinstance(value, str) or not value:
        raise ValueError("trial_id must be a non-empty string")
    return value


def _number(values: dict[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _integer(values: dict[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != pd.Timedelta(0):
        raise argparse.ArgumentTypeError("timestamps must be UTC")
    return parsed.astimezone(UTC)


def main() -> int:
    """Run the search and publish one immutable report-only artifact."""
    args = build_parser().parse_args()
    report = run_robustness(
        symbol=args.symbol,
        bars_path=args.bars,
        funding_paths=args.funding,
        development_start=args.development_start,
        development_end=args.development_end,
        validation_end=args.validation_end,
        pseudo_holdout_end=args.pseudo_holdout_end,
        selection_limit=args.selection_limit,
    )
    write_immutable_json(args.output, report)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
