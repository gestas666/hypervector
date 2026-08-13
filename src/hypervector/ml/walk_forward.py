"""Walk-forward metalabel retrain orchestrated from a Phase-1.5 export."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hypervector.data.pipeline import load_research_history
from hypervector.ml.feature_matrix import FEATURE_NAMES, build_feature_matrix
from hypervector.ml.labels import build_strategy_labels
from hypervector.ml.purged_cv import walk_forward_windows
from hypervector.ml.train_bundle import DEFAULT_LGBM_PARAMS, train_metalabel_bundle
from hypervector.nautilus.load_export import load_strategy_loadout
from hypervector.strategies import register_all_strategies
from hypervector.strategies.registry import get_strategy
from hypervector.sweep.exits import ExitConfig


@dataclass
class FoldScore:
    fold: int
    n_train: int
    n_test: int
    log_loss: float | None
    brier: float | None
    auc: float | None
    baseline_log_loss: float | None
    pos_rate_test: float | None


@dataclass
class WalkForwardResult:
    labels_path: Path
    bundle_dir: Path
    n_labels: int
    class_balance: float
    folds: list[FoldScore]
    oos_log_loss_mean: float | None
    oos_auc_mean: float | None
    beat_baseline: bool | None
    strategy: str
    export_dir: str
    report: dict[str, Any]


def _exit_cfg_from_loadout(loadout: Any) -> ExitConfig:
    ex = getattr(loadout, "exits", None) or {}
    if not isinstance(ex, dict):
        ex = {}
    mode = ex.get("mode") or getattr(loadout, "exit_mode", None) or "atr"
    return ExitConfig(
        mode=mode,  # type: ignore[arg-type]
        sl_pct=float(ex.get("sl_pct", 0.01)),
        rr=float(ex.get("rr", 2.0)),
        atr_length=int(ex.get("atr_length", 14)),
        sl_atr_mult=float(ex.get("sl_atr_mult", 1.5)),
        trail_atr_mult=float(ex.get("trail_atr_mult", 2.0)),
    )


def _direction_from_role(role: str) -> str:
    if role in ("uptrend", "long"):
        return "long"
    if role in ("downtrend", "short"):
        return "short"
    return "long"


def run_walk_forward_metalabel(
    *,
    export_dir: Path | str,
    data_root: Path | str,
    out_dir: Path | str | None = None,
    lookback_days: int | None = None,
    train_days: int = 45,
    test_days: int = 15,
    step_days: int | None = None,
    embargo_minutes: int = 60,
    max_hold_bars: int = 120,
    n_cv_splits: int = 5,
    ohlcv: pd.DataFrame | None = None,
) -> WalkForwardResult:
    """Label strategy entries → walk-forward OOS scores → final metalabel bundle."""
    try:
        import lightgbm as lgb
        from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
    except ImportError as exc:
        raise ImportError(
            "walk-forward metalabel requires lightgbm + scikit-learn (uv sync --extra ml)"
        ) from exc

    export_path = Path(export_dir)
    root = Path(data_root)
    register_all_strategies()
    loadout = load_strategy_loadout(export_path, strict=True)
    strategy = get_strategy(loadout.strategy_name)
    direction = _direction_from_role(strategy.role)
    exit_cfg = _exit_cfg_from_loadout(loadout)

    lb = lookback_days
    if lb is None:
        meta_lb = (loadout.meta or {}).get("lookback_days")
        lb = int(meta_lb) if meta_lb is not None else 90

    if ohlcv is not None:
        df = ohlcv
        prov: dict[str, Any] = {"injected": True}
    else:
        df, prov = load_research_history(
            root,
            symbol=loadout.symbol,
            timeframe=loadout.timeframe,
            lookback_days=int(lb),
        )

    # Strategy params from export (drop non-signal keys)
    params = {
        k: v
        for k, v in (loadout.params or {}).items()
        if k
        not in {
            "strategy",
            "role",
            "exit_mode",
            "tp_sl_mode",
            "sl_pct",
            "rr",
            "atr_length",
            "sl_atr_mult",
            "trail_atr_mult",
        }
    }
    entries, _exits, _dir = strategy.build_signals(df, **params)
    feats = build_feature_matrix(df)
    labels = build_strategy_labels(
        df,
        entries,
        direction=direction,
        exit_cfg=exit_cfg,
        max_hold_bars=int(max_hold_bars),
        feature_matrix=feats,
    )
    if len(labels) < 25:
        raise RuntimeError(
            f"too few labeled samples for walk-forward: {len(labels)} "
            f"(need ≥25; strategy may not fire enough on this window)"
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (
        Path(out_dir)
        if out_dir
        else root / "models" / "metalabel" / f"wf_{loadout.strategy_name}_{stamp}"
    )
    out.mkdir(parents=True, exist_ok=True)
    labels_path = out / "labels.csv"
    labels.to_csv(labels_path, index=False)

    entry_ts = labels["entry_ts_ms"].to_numpy(dtype=np.int64)
    X = labels[FEATURE_NAMES].astype(float)
    y = labels["label"].astype(int).to_numpy()
    train_ms = int(train_days) * 86_400_000
    test_ms = int(test_days) * 86_400_000
    step_ms = int(step_days if step_days is not None else test_days) * 86_400_000

    windows = walk_forward_windows(
        entry_ts,
        train_ms=train_ms,
        test_ms=test_ms,
        step_ms=step_ms,
        min_train_samples=max(15, min(40, len(labels) // 3)),
        min_test_samples=max(5, min(8, len(labels) // 8)),
    )

    fold_scores: list[FoldScore] = []
    params_lgb = dict(DEFAULT_LGBM_PARAMS)

    for fi, (tr, te) in enumerate(windows):
        if len(np.unique(y[tr])) < 2:
            fold_scores.append(
                FoldScore(
                    fold=fi,
                    n_train=int(len(tr)),
                    n_test=int(len(te)),
                    log_loss=None,
                    brier=None,
                    auc=None,
                    baseline_log_loss=None,
                    pos_rate_test=float(y[te].mean()) if len(te) else None,
                )
            )
            continue
        dtr = lgb.Dataset(X.iloc[tr], label=y[tr])
        booster = lgb.train(params_lgb, dtr, num_boost_round=200)
        preds = np.clip(booster.predict(X.iloc[te]), 1e-6, 1 - 1e-6)
        base = float(y[te].mean()) if len(te) else 0.5
        base = min(max(base, 1e-6), 1 - 1e-6)
        try:
            ll = float(log_loss(y[te], preds, labels=[0, 1]))
            br = float(brier_score_loss(y[te], preds))
            bl = float(log_loss(y[te], np.full(len(te), base), labels=[0, 1]))
        except ValueError:
            ll = br = bl = None  # type: ignore[assignment]
        try:
            auc = float(roc_auc_score(y[te], preds))
        except ValueError:
            auc = None
        fold_scores.append(
            FoldScore(
                fold=fi,
                n_train=int(len(tr)),
                n_test=int(len(te)),
                log_loss=ll,
                brier=br,
                auc=auc,
                baseline_log_loss=bl,
                pos_rate_test=float(y[te].mean()),
            )
        )

    lls = [f.log_loss for f in fold_scores if f.log_loss is not None]
    aucs = [f.auc for f in fold_scores if f.auc is not None]
    bls = [f.baseline_log_loss for f in fold_scores if f.baseline_log_loss is not None]
    oos_ll = float(np.mean(lls)) if lls else None
    oos_auc = float(np.mean(aucs)) if aucs else None
    oos_bl = float(np.mean(bls)) if bls else None
    beat = (oos_ll < oos_bl) if (oos_ll is not None and oos_bl is not None) else None

    # Final bundle: purged CV on full labels
    train_res = train_metalabel_bundle(
        labels,
        out,
        n_splits=n_cv_splits,
        embargo_minutes=embargo_minutes,
        extra_meta={
            "pipeline": "walk_forward_metalabel",
            "export_dir": str(export_path.resolve()),
            "strategy": loadout.strategy_name,
            "role": strategy.role,
            "direction": direction,
            "lookback_days": int(lb),
            "train_days": train_days,
            "test_days": test_days,
            "max_hold_bars": max_hold_bars,
            "exit_cfg": exit_cfg.to_dict(),
            "params": params,
            "data_provenance": prov,
            "walk_forward_folds": [asdict(f) for f in fold_scores],
            "oos_log_loss_mean": oos_ll,
            "oos_auc_mean": oos_auc,
            "beat_baseline": beat,
        },
    )

    report = {
        "ok": True,
        "strategy": loadout.strategy_name,
        "export_dir": str(export_path.resolve()),
        "n_labels": int(len(labels)),
        "class_balance": float(y.mean()),
        "n_wf_folds": len(fold_scores),
        "oos_log_loss_mean": oos_ll,
        "oos_auc_mean": oos_auc,
        "oos_baseline_log_loss_mean": oos_bl,
        "beat_baseline": beat,
        "bundle_dir": str(train_res.out_dir),
        "labels_path": str(labels_path.resolve()),
        "cv": train_res.cv,
        "folds": [asdict(f) for f in fold_scores],
        "promote_hint": (
            "Set HYPERVECTOR_METALABEL_ROOT to bundle_dir; paper-run --metalabel"
            if beat
            else "OOS did not beat baseline — inspect folds before promoting"
        ),
    }
    (out / "walk_forward_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    return WalkForwardResult(
        labels_path=labels_path.resolve(),
        bundle_dir=train_res.out_dir,
        n_labels=int(len(labels)),
        class_balance=float(y.mean()),
        folds=fold_scores,
        oos_log_loss_mean=oos_ll,
        oos_auc_mean=oos_auc,
        beat_baseline=beat,
        strategy=loadout.strategy_name,
        export_dir=str(export_path.resolve()),
        report=report,
    )
