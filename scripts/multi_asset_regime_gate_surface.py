"""Point-in-time regime-gate surface for the SOL trend challenger."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_strategy_signals import (
    build_registered_strategy_pair_on_timeframe,
)
from multi_asset_trend_risk_surface import TrendRiskTrial, risk_config
from shared_strategy_screen import load_causal_window

_GATE_NAMES = (
    "baseline",
    "exclude_5m_range",
    "five_min_structural",
    "fifteen_min_non_opposed",
    "fifteen_min_strict",
    "five_structural_fifteen_non_opposed",
    "five_structural_fifteen_strict",
    "composite_entry_direction",
    "confidence_60",
    "five_structural_confidence_60",
)
_RANGE_ONSET_GATE_NAMES = (
    "baseline",
    "only_5m_range",
    "five_min_range_or_transition",
    "five_min_range_or_breakout",
    "not_five_min_structural",
    "five_min_range_fifteen_non_opposed",
    "five_min_range_fifteen_strict",
)
_ALL_GATE_NAMES = frozenset((*_GATE_NAMES, *_RANGE_ONSET_GATE_NAMES))
_TREND_UP = "TREND_UP"
_TREND_DOWN = "TREND_DOWN"


@dataclass(frozen=True)
class RegimeGate:
    """One named, predeclared entry-policy counterfactual."""

    name: str

    def __post_init__(self) -> None:
        """Reject undeclared gate names."""
        if self.name not in _ALL_GATE_NAMES:
            raise ValueError(f"unknown regime gate: {self.name}")


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit chronological regime-surface command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--funding", type=Path, action="append", required=True)
    parser.add_argument("--development-start", type=_utc_datetime, required=True)
    parser.add_argument("--development-end", type=_utc_datetime, required=True)
    parser.add_argument("--validation-end", type=_utc_datetime, required=True)
    parser.add_argument("--pseudo-holdout-end", type=_utc_datetime, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--surface",
        choices=("canonical", "range-onset"),
        default="canonical",
    )
    return parser


def regime_gate_grid() -> tuple[RegimeGate, ...]:
    """Return the complete frozen regime-policy grid."""
    return tuple(RegimeGate(name) for name in _GATE_NAMES)


def range_onset_gate_grid() -> tuple[RegimeGate, ...]:
    """Return the explicitly post-hoc range-to-trend onset grid."""
    return tuple(RegimeGate(name) for name in _RANGE_ONSET_GATE_NAMES)


def build_trend_signals(bars: pd.DataFrame) -> pd.DataFrame:
    """Build causal 10/30 SMA-cross decisions on completed one-hour bars."""
    return build_registered_strategy_pair_on_timeframe(
        bars,
        timeframe="1h",
        long_strategy_name="ma_cross_long",
        short_strategy_name="ma_cross_short",
        long_params={"fast": 10, "slow": 30},
        short_params={"fast": 10, "slow": 30},
    )


def classify_regimes(bars: pd.DataFrame) -> pd.DataFrame:
    """Classify the canonical completed 1m/5m/15m state without future data."""
    return classify_multitimeframe(bars)


def apply_regime_gate(
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
    gate: RegimeGate,
) -> pd.DataFrame:
    """Suppress only disallowed entries while preserving every exit signal."""
    if not signals.index.equals(regimes.index):
        raise ValueError("signals and regimes must share the same index")
    long_allowed, short_allowed = _gate_masks(regimes, gate.name)
    result = signals.copy()
    result["long_entry"] = signals["long_entry"].astype(bool) & long_allowed
    result["short_entry"] = signals["short_entry"].astype(bool) & short_allowed
    return result


def evaluate_gates(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
    *,
    symbol: str,
    gates: tuple[RegimeGate, ...],
) -> list[dict[str, object]]:
    """Evaluate and retain every requested gate on one independent interval."""
    config = risk_config(_baseline_trial(), symbol=symbol)
    results: list[dict[str, object]] = []
    for gate in gates:
        gated = apply_regime_gate(signals, regimes, gate)
        report = evaluate_shared_bar_portfolio(bars, gated, config)
        results.append(_gate_summary(gate, signals, gated, report.to_dict()))
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
    gates: tuple[RegimeGate, ...] | None = None,
    surface_name: str = "canonical",
) -> dict[str, object]:
    """Compute features once, then evaluate gates on frozen chronological slices."""
    bars, evidence = load_causal_window(
        bars_path,
        funding_paths,
        development_start,
        pseudo_holdout_end,
    )
    signals = build_trend_signals(bars)
    regimes = classify_regimes(bars)
    surface = gates or regime_gate_grid()
    boundaries = (
        ("development", development_start, development_end),
        ("validation", development_end, validation_end),
        ("pseudo_holdout", validation_end, pseudo_holdout_end),
        ("continuous", development_start, pseudo_holdout_end),
    )
    segments = {
        name: _segment(bars, signals, regimes, symbol, surface, start, end)
        for name, start, end in boundaries
    }
    return _artifact(symbol, evidence, regimes, surface, segments, surface_name)


def _gate_masks(
    regimes: pd.DataFrame,
    name: str,
) -> tuple[pd.Series, pd.Series]:
    all_rows = pd.Series(True, index=regimes.index)
    state_5m = regimes["state_5m"]
    context = regimes["context_15m"]
    structural = regimes["structural_direction"]
    composite = regimes["entry_direction"]
    confident = regimes["confidence"].astype(float).ge(0.60)
    five_long, five_short = structural.eq("long"), structural.eq("short")
    non_opposed_long = ~context.eq(_TREND_DOWN)
    non_opposed_short = ~context.eq(_TREND_UP)
    strict_long, strict_short = context.eq(_TREND_UP), context.eq(_TREND_DOWN)
    in_range = state_5m.eq("RANGE")
    masks = {
        "baseline": (all_rows, all_rows),
        "exclude_5m_range": (
            ~state_5m.isin(["RANGE", "UNKNOWN"]),
            ~state_5m.isin(["RANGE", "UNKNOWN"]),
        ),
        "five_min_structural": (five_long, five_short),
        "fifteen_min_non_opposed": (non_opposed_long, non_opposed_short),
        "fifteen_min_strict": (strict_long, strict_short),
        "five_structural_fifteen_non_opposed": (
            five_long & non_opposed_long,
            five_short & non_opposed_short,
        ),
        "five_structural_fifteen_strict": (
            five_long & strict_long,
            five_short & strict_short,
        ),
        "composite_entry_direction": (
            composite.eq("long"),
            composite.eq("short"),
        ),
        "confidence_60": (confident, confident),
        "five_structural_confidence_60": (
            five_long & confident,
            five_short & confident,
        ),
        "only_5m_range": (in_range, in_range),
        "five_min_range_or_transition": (
            state_5m.isin(["RANGE", "TRANSITION"]),
            state_5m.isin(["RANGE", "TRANSITION"]),
        ),
        "five_min_range_or_breakout": (
            state_5m.isin(["RANGE", "BREAKOUT"]),
            state_5m.isin(["RANGE", "BREAKOUT"]),
        ),
        "not_five_min_structural": (~five_long, ~five_short),
        "five_min_range_fifteen_non_opposed": (
            in_range & non_opposed_long,
            in_range & non_opposed_short,
        ),
        "five_min_range_fifteen_strict": (
            in_range & strict_long,
            in_range & strict_short,
        ),
    }
    return masks[name]


def _segment(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
    symbol: str,
    gates: tuple[RegimeGate, ...],
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    mask = (bars.index >= start) & (bars.index < end)
    segment_bars = bars.loc[mask]
    results = evaluate_gates(
        segment_bars,
        signals.loc[mask],
        regimes.loc[mask],
        symbol=symbol,
        gates=gates,
    )
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "bar_rows": len(segment_bars),
        "trial_count": len(results),
        "trials": results,
    }


def _gate_summary(
    gate: RegimeGate,
    raw_signals: pd.DataFrame,
    gated: pd.DataFrame,
    report: dict[str, object],
) -> dict[str, object]:
    values = dict(report)
    raw_trades = values.pop("trades")
    if not isinstance(raw_trades, tuple):
        raise ValueError("portfolio trades must be a tuple")
    limitations = values.pop("limitations")
    return {
        "trial_id": gate.name,
        "gate": gate.name,
        "execution_authority": "none",
        "raw_entries": _entry_counts(raw_signals),
        "retained_entries": _entry_counts(gated),
        "metrics": values,
        "exit_reasons": dict(
            sorted(Counter(str(trade["exit_reason"]) for trade in raw_trades).items())
        ),
        "limitations": limitations,
    }


def _entry_counts(signals: pd.DataFrame) -> dict[str, int]:
    return {
        "long": int(signals["long_entry"].astype(bool).sum()),
        "short": int(signals["short_entry"].astype(bool).sum()),
    }


def _baseline_trial() -> TrendRiskTrial:
    return TrendRiskTrial("1h", 10, 30, None, 60.0, 48, 0.10, 5.0)


def _artifact(
    symbol: str,
    evidence: dict[str, object],
    regimes: pd.DataFrame,
    gates: tuple[RegimeGate, ...],
    segments: dict[str, dict[str, object]],
    surface_name: str,
) -> dict[str, object]:
    if surface_name not in {"canonical", "range-onset"}:
        raise ValueError("surface_name must be canonical|range-onset")
    post_hoc = surface_name == "range-onset"
    return {
        "schema_version": 1,
        "mode": f"multi_asset_regime_{surface_name.replace('-', '_')}_report_only",
        "symbol": symbol.strip().upper(),
        "execution_authority": "none",
        "model_authority": "none",
        "initial_equity": 15_000.0,
        "trial_count": len(gates),
        "fixed_strategy": {
            "timeframe": "1h",
            "moving_average": "10x30_sma_cross",
            "target_bps": None,
            "stop_bps": 60.0,
            "max_hold_hours": 48,
            "margin_fraction": 0.10,
            "leverage": 5.0,
        },
        "data_evidence": evidence,
        "regime_state_distribution": _regime_distribution(regimes),
        "post_hoc_after_canonical_surface": post_hoc,
        **segments,
        "limitations": [
            "regime policies are report-only and do not change runtime execution",
            (
                "range-onset hypotheses were declared after inspecting full-year "
                "canonical gate attribution"
                if post_hoc
                else "canonical gate policies were frozen before result inspection"
            ),
            "pseudo-holdout has been observed during prior strategy searches",
            "bar simulation cannot establish maker queue rank or market impact",
            "promotion requires venue-event replay and fresh forward evidence",
        ],
    }


def _regime_distribution(regimes: pd.DataFrame) -> dict[str, int]:
    counts = regimes["primary_regime"].value_counts()
    return {str(name): int(count) for name, count in counts.sort_index().items()}


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != pd.Timedelta(0):
        raise argparse.ArgumentTypeError("timestamps must be UTC")
    return parsed.astimezone(UTC)


def main() -> int:
    """Run the surface and publish one immutable report-only artifact."""
    args = build_parser().parse_args()
    gates = (
        regime_gate_grid() if args.surface == "canonical" else range_onset_gate_grid()
    )
    report = run_surface(
        symbol=args.symbol,
        bars_path=args.bars,
        funding_paths=args.funding,
        development_start=args.development_start,
        development_end=args.development_end,
        validation_end=args.validation_end,
        pseudo_holdout_end=args.pseudo_holdout_end,
        gates=gates,
        surface_name=args.surface,
    )
    write_immutable_json(args.output, report)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
