"""Compare fixed causal range-onset timeframes without runtime authority."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import math
from pathlib import Path
from statistics import median

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.range_onset_signals import build_range_onset_signals
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from multi_asset_range_onset_shape_surface import (
    OnsetShape,
    _trade_side_summary,
    onset_shape_config,
)
from shared_strategy_screen import load_causal_window

_TIMEFRAMES = ("5min", "15min", "30min", "1h")
_FIXED_SHAPE = OnsetShape(60.0, 48)


def candidate_timeframes() -> tuple[str, ...]:
    """Return the predeclared timeframe candidates in evaluation order."""
    return _TIMEFRAMES


def build_parser() -> argparse.ArgumentParser:
    """Build the command with explicit chronological evidence boundaries."""
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


def run_report(
    *,
    symbol: str,
    bars_path: Path,
    funding_paths: list[Path],
    development_start: datetime,
    development_end: datetime,
    validation_end: datetime,
    pseudo_holdout_end: datetime,
) -> dict[str, object]:
    """Evaluate every fixed timeframe on three slices and the full window."""
    bars, evidence = load_causal_window(
        bars_path,
        funding_paths,
        development_start,
        pseudo_holdout_end,
    )
    regimes = classify_multitimeframe(bars)
    variants = {
        timeframe: build_range_onset_signals(
            bars,
            timeframe=timeframe,
            regimes=regimes,
        )
        for timeframe in candidate_timeframes()
    }
    boundaries = _boundaries(
        development_start,
        development_end,
        validation_end,
        pseudo_holdout_end,
    )
    segments = {
        name: _segment(bars, variants, symbol, start, end)
        for name, start, end in boundaries
    }
    return _artifact(symbol, evidence, segments)


def _boundaries(
    start: datetime,
    development_end: datetime,
    validation_end: datetime,
    holdout_end: datetime,
) -> tuple[tuple[str, datetime, datetime], ...]:
    return (
        ("development", start, development_end),
        ("validation", development_end, validation_end),
        ("pseudo_holdout", validation_end, holdout_end),
        ("continuous", start, holdout_end),
    )


def _segment(
    bars: pd.DataFrame,
    variants: dict[str, pd.DataFrame],
    symbol: str,
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    mask = (bars.index >= start) & (bars.index < end)
    window = bars.loc[mask]
    config = onset_shape_config(_FIXED_SHAPE, symbol=symbol)
    window_days = (end - start).total_seconds() / 86_400.0
    candidates = []
    for timeframe, signals in variants.items():
        summary = _candidate_summary(
            timeframe,
            evaluate_shared_bar_portfolio(
                window,
                signals.loc[mask],
                config,
            ).to_dict(),
            window_days,
        )
        summary["signal_events"] = _signal_events(signals.loc[mask])
        trades = summary["trades"]
        if not isinstance(trades, list):
            raise ValueError("timeframe summary trades must be a list")
        summary["gap_path_attribution"] = _gap_path_attribution(trades, window)
        candidates.append(summary)
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "bar_rows": int(mask.sum()),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _candidate_summary(
    timeframe: str,
    report: dict[str, object],
    window_days: float,
) -> dict[str, object]:
    values = dict(report)
    raw_trades = values.pop("trades")
    if not isinstance(raw_trades, tuple):
        raise ValueError("timeframe candidate trades must be a tuple")
    limitations = values.pop("limitations", ())
    trades = [dict(trade) for trade in raw_trades]
    return {
        "candidate_id": f"sma10x30@{timeframe}",
        "source_timeframe": timeframe,
        "execution_authority": "none",
        "metrics": values,
        "cadence": _cadence(trades, window_days),
        "by_side": _trade_side_summary(raw_trades),
        "exit_reasons": dict(
            sorted(Counter(str(trade["exit_reason"]) for trade in trades).items())
        ),
        "trades": trades,
        "limitations": list(limitations),
    }


def _cadence(trades: list[dict[str, object]], window_days: float) -> dict[str, object]:
    if not math.isfinite(window_days) or window_days <= 0.0:
        raise ValueError("cadence window_days must be positive and finite")
    timestamps = sorted(_trade_timestamp(trade) for trade in trades)
    gaps = [
        (current - previous).total_seconds() / 3_600.0
        for previous, current in zip(timestamps, timestamps[1:], strict=False)
    ]
    return {
        "trades_per_30_days": len(trades) / window_days * 30.0,
        "median_intertrade_hours": median(gaps) if gaps else None,
    }


def _trade_timestamp(trade: dict[str, object]) -> datetime:
    return _trade_time(trade, "signal_time_utc")


def _trade_time(trade: dict[str, object], field: str) -> datetime:
    value = trade.get(field)
    if not isinstance(value, str):
        raise ValueError(f"trade {field} must be text")
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError(f"trade {field} must be timezone-aware")
    return timestamp


def _signal_events(signals: pd.DataFrame) -> dict[str, int]:
    return {
        "admitted_long": int(signals["long_entry"].astype(bool).sum()),
        "admitted_short": int(signals["short_entry"].astype(bool).sum()),
        "raw_long_cross": int(signals["raw_long_cross"].astype(bool).sum()),
        "raw_short_cross": int(signals["raw_short_cross"].astype(bool).sum()),
    }


def _gap_path_attribution(
    trades: list[dict[str, object]],
    bars: pd.DataFrame,
) -> dict[str, object]:
    if "source" not in bars:
        raise ValueError("gap attribution requires bar source provenance")
    gaps = bars.index[bars["source"].astype(str).eq("hl_gap_fill")]
    touched_pnl: list[float] = []
    for trade in trades:
        start = _trade_time(trade, "signal_time_utc")
        end = _trade_time(trade, "exit_time_utc")
        if ((gaps >= start) & (gaps <= end)).any():
            value = trade.get("net_pnl_usd")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("trade net_pnl_usd must be numeric")
            touched_pnl.append(float(value))
    return {
        "gap_fill_rows": len(gaps),
        "trades_touching_gap_fill": len(touched_pnl),
        "gap_touched_net_pnl_usd": sum(touched_pnl),
        "clean_path_trade_count": len(trades) - len(touched_pnl),
    }


def _artifact(
    symbol: str,
    evidence: dict[str, object],
    segments: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "range_onset_timeframe_challenger_report_only",
        "symbol": symbol.strip().upper(),
        "execution_authority": "none",
        "model_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_execution_gate": False,
        "candidate_timeframes": list(candidate_timeframes()),
        "fixed_entry_logic": "SMA10/30 cross in completed 5m RANGE or BREAKOUT",
        "fixed_risk": {
            "stop_bps": _FIXED_SHAPE.stop_bps,
            "maximum_hold_hours": _FIXED_SHAPE.max_hold_hours,
            "margin_fraction": 0.10,
            "leverage": 5.0,
        },
        "data_evidence": evidence,
        **segments,
        "limitations": [
            "timeframe candidates were specified after sparse live cadence was observed",
            "the original range-onset rule was selected post hoc",
            "bar simulation cannot establish queue rank or depth-constrained impact",
            "candidate results cannot filter, size, route, close, or promote live trades",
            "pseudo-holdout remains reuse-contaminated by prior project research",
        ],
    }


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != pd.Timedelta(0):
        raise argparse.ArgumentTypeError("timestamps must be UTC")
    return parsed.astimezone(UTC)


def main() -> int:
    """Run the immutable report-only timeframe audit."""
    args = build_parser().parse_args()
    report = run_report(
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
