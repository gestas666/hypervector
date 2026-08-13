"""Audit fixed causal context challengers for the range-onset entry rule."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import math
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.regime.component_telemetry import build_regime_component_frame
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.range_onset_context_challenger import (
    build_context_signal_variants,
)
from hypervector.research.range_onset_signals import build_range_onset_signals
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from multi_asset_range_onset_shape_surface import (
    OnsetShape,
    _trade_side_summary,
    onset_shape_config,
)
from shared_strategy_screen import load_causal_window

_FIXED_SHAPE = OnsetShape(60.0, 48)


def build_parser() -> argparse.ArgumentParser:
    """Build the command with explicit point-in-time evidence boundaries."""
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
    """Evaluate all fixed challengers on three slices and the continuous window."""
    bars, evidence = load_causal_window(
        bars_path,
        funding_paths,
        development_start,
        pseudo_holdout_end,
    )
    baseline = build_range_onset_signals(bars)
    regimes = classify_multitimeframe(bars)
    components = build_regime_component_frame(bars)
    variants = build_context_signal_variants(baseline, regimes, components)
    boundaries = (
        ("development", development_start, development_end),
        ("validation", development_end, validation_end),
        ("pseudo_holdout", validation_end, pseudo_holdout_end),
        ("continuous", development_start, pseudo_holdout_end),
    )
    segments = {
        name: _segment(bars, variants, symbol, start, end)
        for name, start, end in boundaries
    }
    return _artifact(symbol, evidence, segments)


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
    candidates = [
        _candidate_summary(
            candidate,
            evaluate_shared_bar_portfolio(
                window,
                signals.loc[mask],
                config,
            ).to_dict(),
        )
        for candidate, signals in variants.items()
    ]
    baseline = candidates[0]
    for candidate in candidates:
        candidate["baseline_trade_retention"] = _retention_summary(baseline, candidate)
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "bar_rows": int(mask.sum()),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _candidate_summary(candidate: str, report: dict[str, object]) -> dict[str, object]:
    values = dict(report)
    raw_trades = values.pop("trades")
    if not isinstance(raw_trades, tuple):
        raise ValueError("context candidate trades must be a tuple")
    limitations = values.pop("limitations", ())
    trades = [dict(trade) for trade in raw_trades]
    return {
        "candidate_id": candidate,
        "execution_authority": "none",
        "metrics": values,
        "by_side": _trade_side_summary(raw_trades),
        "exit_reasons": dict(
            sorted(Counter(str(trade["exit_reason"]) for trade in trades).items())
        ),
        "trades": trades,
        "limitations": list(limitations),
    }


def _retention_summary(
    baseline: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    baseline_trades = _trade_map(baseline.get("trades"), "baseline")
    candidate_trades = _trade_map(candidate.get("trades"), "candidate")
    baseline_keys = set(baseline_trades)
    candidate_keys = set(candidate_trades)
    winners = {
        key: trade for key, trade in baseline_trades.items() if _trade_pnl(trade) > 0.0
    }
    losses = {
        key: trade for key, trade in baseline_trades.items() if _trade_pnl(trade) <= 0.0
    }
    retained_winners = winners.keys() & candidate_keys
    excluded_winners = winners.keys() - candidate_keys
    retained_losses = losses.keys() & candidate_keys
    excluded_losses = losses.keys() - candidate_keys
    gross_profit = sum(_trade_pnl(trade) for trade in winners.values())
    gross_loss = -sum(_trade_pnl(trade) for trade in losses.values())
    retained_profit = sum(_trade_pnl(winners[key]) for key in retained_winners)
    excluded_loss = -sum(_trade_pnl(losses[key]) for key in excluded_losses)
    return {
        "baseline_trades": len(baseline_trades),
        "retained_baseline_trades": len(baseline_keys & candidate_keys),
        "excluded_baseline_trades": len(baseline_keys - candidate_keys),
        "candidate_entries_not_in_baseline": len(candidate_keys - baseline_keys),
        "baseline_winners": len(winners),
        "retained_baseline_winners": len(retained_winners),
        "excluded_baseline_winners": len(excluded_winners),
        "baseline_losses": len(losses),
        "retained_baseline_losses": len(retained_losses),
        "excluded_baseline_losses": len(excluded_losses),
        "retained_baseline_gross_profit_pct": _percentage(
            retained_profit, gross_profit
        ),
        "excluded_baseline_gross_loss_pct": _percentage(excluded_loss, gross_loss),
    }


def _trade_map(value: object, label: str) -> dict[tuple[str, str], dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} retention trades must be a list")
    output: dict[tuple[str, str], dict[str, object]] = {}
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError(f"{label} retention trade must be an object")
        side = raw.get("direction")
        signal_time = raw.get("signal_time_utc")
        if side not in {"long", "short"} or not isinstance(signal_time, str):
            raise ValueError(f"{label} retention trade identity is invalid")
        key = (side, signal_time)
        if key in output:
            raise ValueError(f"{label} retention trade identity is duplicated")
        _trade_pnl(raw)
        output[key] = raw
    return output


def _trade_pnl(trade: dict[str, object]) -> float:
    value = trade.get("net_pnl_usd")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("retention trade net_pnl_usd must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("retention trade net_pnl_usd must be finite")
    return number


def _percentage(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0.0 else numerator / denominator * 100.0


def _artifact(
    symbol: str,
    evidence: dict[str, object],
    segments: dict[str, object],
) -> dict[str, object]:
    definitions = {
        "current_contract": "hourly SMA10/30 cross in completed 5m RANGE or BREAKOUT",
        "component_alignment_gte_neg05": (
            "current contract and weighted component alignment score >= -0.5"
        ),
        "dual_mtf_not_opposed": (
            "current contract unless completed 5m and 15m candle biases both oppose"
        ),
        "state_1m_not_opposed": (
            "current contract unless canonical completed 1m trend opposes"
        ),
    }
    return {
        "schema_version": 1,
        "mode": "range_onset_context_challenger_report_only",
        "symbol": symbol.strip().upper(),
        "execution_authority": "none",
        "model_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_execution_gate": False,
        "balance_gate": False,
        "candidate_count": len(definitions),
        "candidate_definitions": definitions,
        "fixed_signal": "1h_10x30_sma_cross_in_5m_RANGE_or_BREAKOUT",
        "fixed_risk": {
            "stop_bps": _FIXED_SHAPE.stop_bps,
            "maximum_hold_hours": _FIXED_SHAPE.max_hold_hours,
            "margin_fraction": 0.10,
            "leverage": 5.0,
        },
        "data_evidence": evidence,
        **segments,
        "limitations": [
            "challengers were specified after one opposed ETH live loss",
            "the original range-onset signal was selected post hoc",
            "bar simulation cannot establish queue rank or depth impact",
            "candidate results cannot filter, size, route, close, or promote live trades",
            "rare trend winners can dominate profit factor and must be inspected directly",
        ],
    }


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != pd.Timedelta(0):
        raise argparse.ArgumentTypeError("timestamps must be UTC")
    return parsed.astimezone(UTC)


def main() -> int:
    """Run the immutable report-only challenger audit."""
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
