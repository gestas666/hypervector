"""Regime command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
import pandas as pd
from hypervector.export.phase2 import export_candidate
from hypervector.regime.detectors import detect_regime_ema
from hypervector.regime.metrics import regime_detection_metrics
from hypervector.commands.common import _load_bars


def cmd_regime(args: argparse.Namespace) -> int:
    df, prov = _load_bars(args)
    labels = detect_regime_ema(df["close"], fast=args.fast, slow=args.slow)
    metrics = regime_detection_metrics(labels)
    print(
        json.dumps(
            {
                "labels_sample": labels.value_counts().to_dict(),
                "metrics": metrics,
                "data_provenance": prov,
            },
            indent=2,
            default=str,
        )
    )
    if args.export:
        export_candidate(
            Path(args.data_root) / "exports",
            run_id=str(uuid.uuid4())[:8],
            meta={
                "track": "regime",
                "symbol": args.symbol,
                "timeframe": args.timeframe,
                "data_provenance": prov,
            },
            params={
                "strategy": "regime_ema",
                "fast": args.fast,
                "slow": args.slow,
            },
            metrics=metrics,
            regime_labels=labels,
            candidate_id=f"regime_{args.symbol}",
        )
    return 0


def cmd_regime_eval(args: argparse.Namespace) -> int:
    """Evaluate forward return accuracy and predictive edge of Ultimate Regime Classifier."""
    from hypervector.regime.evaluator import evaluate_regime_accuracy

    df_1m, _ = _load_bars(args)

    book_path = getattr(args, "book_path", None)
    if book_path and Path(book_path).is_file():
        from hypervector.data.book_align import align_orderbook_to_ohlcv, load_l2_jsonl

        df_book = load_l2_jsonl(book_path)
        df_1m = align_orderbook_to_ohlcv(df_1m, df_book)

    rpt = evaluate_regime_accuracy(df_1m, forward_horizon=args.forward_horizon)
    out = {
        "ok": True,
        "symbol": rpt.symbol,
        "timeframe": rpt.timeframe,
        "total_bars": rpt.total_bars,
        "forward_horizon": args.forward_horizon,
        "overall_directional_accuracy_pct": rpt.overall_directional_accuracy,
        "regime_stats": rpt.regime_stats,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_hypervelocity_regime_eval(args: argparse.Namespace) -> int:
    """Report Hypervelocity regime fidelity without gating the experiment."""
    from hypervector.regime.hypervelocity_eval import evaluate_hypervelocity_regimes

    df, provenance = _load_bars(args)
    positions_path = Path(args.positions)
    if not positions_path.is_file():
        raise FileNotFoundError(f"positions file not found: {positions_path}")
    positions = pd.read_csv(positions_path)
    report = evaluate_hypervelocity_regimes(
        df,
        positions,
        forward_horizon=args.forward_horizon,
    )
    out = {
        "ok": True,
        "report_only": True,
        "data_provenance": provenance,
        **report.to_dict(),
    }
    rendered = json.dumps(out, indent=2, default=str)
    if args.out:
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def cmd_hypervelocity_regime_autotune(args: argparse.Namespace) -> int:
    """Tune causal regime parameters and retain every trial result."""
    from hypervector.regime.tuning import (
        autotune_regime_candidates,
        generate_candidate_parameters,
    )

    df, provenance = _load_bars(args)
    positions_path = Path(args.positions)
    if not positions_path.is_file():
        raise FileNotFoundError(f"positions file not found: {positions_path}")
    positions = pd.read_csv(positions_path)
    candidates = generate_candidate_parameters(n_trials=args.n_trials, seed=args.seed)
    board = autotune_regime_candidates(
        df,
        positions,
        candidates,
        train_fraction=args.train_fraction,
        forward_horizon=args.forward_horizon,
    )
    out = {
        "ok": True,
        "report_only": True,
        "data_provenance": provenance,
        "tuning_board": board.to_dict(),
    }
    rendered = json.dumps(out, indent=2, default=str)
    if args.out:
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def cmd_hypervelocity_regime_challengers(args: argparse.Namespace) -> int:
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
    output = {"data_provenance": provenance, **report}
    rendered = json.dumps(output, indent=2, default=str)
    if args.out:
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def cmd_regime_export(args: argparse.Namespace) -> int:
    """Export real per-bar regime telemetry snapshots for the TUI cockpit."""
    from hypervector.regime.snapshot_export import export_regime_snapshots

    root = Path(args.data_root)
    df, prov = _load_bars(args)

    book_path = getattr(args, "book_path", None)
    if book_path and Path(book_path).is_file():
        from hypervector.data.book_align import align_orderbook_to_ohlcv, load_l2_jsonl

        df_book = load_l2_jsonl(book_path)
        df = align_orderbook_to_ohlcv(df, df_book)

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
