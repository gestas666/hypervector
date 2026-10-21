"""Regime command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hypervector.commands.common import (
    CommandRefused,
    _load_bars,
    align_book,
    book_path_or_refuse,
)

if TYPE_CHECKING:
    import pandas as pd

EMA_FAST_DEFAULT = 12
EMA_SLOW_DEFAULT = 48
# The canonical engine classifies 1m execution bars and derives 5m/15m context.
CANONICAL_TIMEFRAME = "1m"
_TREND_LABELS = {"TREND_UP": "up", "TREND_DOWN": "down", "RANGE": "range"}


def cmd_regime(args: argparse.Namespace) -> int:
    """Classify regimes with the canonical engine (default) or the EMA crossover."""
    detector = str(getattr(args, "detector", "canonical"))
    if detector == "canonical":
        if args.fast is not None or args.slow is not None:
            raise CommandRefused("--fast/--slow apply only to --detector ema")
        if args.timeframe != CANONICAL_TIMEFRAME:
            raise CommandRefused(
                "the canonical detector classifies 1m bars (5m/15m context is "
                "derived); use --timeframe 1m or --detector ema"
            )
    fast = EMA_FAST_DEFAULT if args.fast is None else int(args.fast)
    slow = EMA_SLOW_DEFAULT if args.slow is None else int(args.slow)
    if detector == "ema" and fast >= slow:
        raise CommandRefused("--fast must be smaller than --slow")
    df, prov = _load_bars(args)
    if detector == "canonical":
        labels, metrics = _canonical_labels(df)
        settings: dict[str, Any] = {"engine": "regime.ultimate.detect_ultimate_regime"}
    else:
        from hypervector.regime.detectors import detect_regime_ema
        from hypervector.regime.metrics import regime_detection_metrics

        labels = detect_regime_ema(df["close"], fast=fast, slow=slow)
        metrics = regime_detection_metrics(labels)
        settings = {"fast": fast, "slow": slow}
    print(
        json.dumps(
            {
                "ok": True,
                "detector": detector,
                "detector_settings": settings,
                "symbol": args.symbol,
                "timeframe": args.timeframe,
                "lookback_days": args.lookback,
                "labels_sample": labels.value_counts().to_dict(),
                "metrics": metrics,
                "data_provenance": prov,
            },
            indent=2,
            default=str,
        )
    )
    return 0


def _canonical_labels(df: pd.DataFrame) -> tuple[pd.Series, dict[str, Any]]:
    """Canonical regime states plus duration metrics on the same scale as ema."""
    from hypervector.regime.metrics import regime_detection_metrics
    from hypervector.regime.ultimate import detect_ultimate_regime

    classified = detect_ultimate_regime(_datetime_indexed(df))
    labels = classified["regime_state"].astype(str)
    metrics = regime_detection_metrics(labels.map(lambda s: _TREND_LABELS.get(s, s)))
    total = max(len(labels), 1)
    metrics["pct_by_state"] = {
        str(state): float(count) / total
        for state, count in labels.value_counts().items()
    }
    return labels, metrics


def _datetime_indexed(df: pd.DataFrame) -> pd.DataFrame:
    import pandas as pd

    if isinstance(df.index, pd.DatetimeIndex):
        return df
    if "timestamp" not in df.columns:
        raise ValueError("regime bars require a DatetimeIndex or a timestamp column")
    out = df.copy()
    out.index = pd.DatetimeIndex(pd.to_datetime(out["timestamp"], utc=True))
    return out


def cmd_regime_eval(args: argparse.Namespace) -> int:
    """Evaluate forward return accuracy and predictive edge of the canonical classifier."""
    from hypervector.regime.evaluator import evaluate_regime_accuracy

    book_path = book_path_or_refuse(args)
    df_1m, provenance = _load_bars(args)
    if book_path is not None:
        df_1m = align_book(df_1m, book_path, str(args.symbol))

    rpt = evaluate_regime_accuracy(df_1m, forward_horizon=args.forward_horizon)
    out = {
        "ok": True,
        "symbol": rpt.symbol,
        "timeframe": rpt.timeframe,
        "total_bars": rpt.total_bars,
        "forward_horizon": args.forward_horizon,
        "overall_directional_accuracy_pct": rpt.overall_directional_accuracy,
        "regime_stats": rpt.regime_stats,
        "book_path": str(book_path) if book_path is not None else None,
        "data_provenance": provenance,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_regime_challengers(args: argparse.Namespace) -> int:
    """Run point-in-time statistical regimes as annotations only."""
    from hypervector.regime.challengers import evaluate_regime_challengers

    bars, provenance = _load_bars(args)
    report = evaluate_regime_challengers(
        bars,
        forward_horizon=args.forward_horizon,
        random_state=args.seed,
        n_splits=args.n_splits,
        wasserstein_window=args.wasserstein_window,
        wasserstein_sample_cap=args.wasserstein_sample_cap,
    )
    _emit({"data_provenance": provenance, **report}, args.out)
    return 0


def cmd_regime_export(args: argparse.Namespace) -> int:
    """Export real per-bar regime telemetry snapshots as JSON."""
    from hypervector.regime.snapshot_export import export_regime_snapshots

    root = Path(args.data_root)
    book_path = book_path_or_refuse(args)
    df, prov = _load_bars(args)
    if book_path is not None:
        df = align_book(df, book_path, str(args.symbol))

    out_path = args.out or (root / "exports" / "regime_snapshots.json")
    summary = export_regime_snapshots(
        df,
        out_path,
        symbol=args.symbol,
        timeframe=args.timeframe,
        data_root=root,
        max_bars=args.bars,
    )
    summary["data_provenance"] = prov
    print(json.dumps(summary, indent=2, default=str))
    return 0


def _emit(out: dict[str, Any], destination: Path | str | None) -> None:
    rendered = json.dumps(out, indent=2, default=str)
    if destination:
        output_path = Path(destination)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
