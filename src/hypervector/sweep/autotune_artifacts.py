"""Durable trial boards and strict exports from successful searches."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import json
from pathlib import Path

from hypervector.sweep.autotune_models import AutotuneResult, SearchSettings


def finish_search(
    settings: SearchSettings,
    *,
    trials: list[dict[str, object]],
    role: str,
    provenance: dict[str, object],
    exporter: Callable[..., Path],
) -> AutotuneResult:
    """Preserve error evidence and refuse to call an all-failed search successful."""
    valid = [trial for trial in trials if trial["status"] == "ok"]
    valid.sort(key=lambda trial: trial["metrics"].get("net_pnl", -9999.0), reverse=True)
    best = valid[0] if valid else {"params": {}, "exit_cfg": {}, "metrics": {}}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    sampler_label = (
        "karpathy_random_adaptive" if settings.sampler == "karpathy" else "optuna_tpe"
    )
    board_path = _publish_board(settings, trials, best, stamp, sampler_label)
    if not valid:
        raise RuntimeError(
            f"Autotune produced no successful trials; inspect technical failures: {board_path}"
        )
    export_dir = (
        None
        if settings.no_export
        else exporter(
            root=settings.root,
            stamp=stamp,
            strategy_name=settings.strategy_name,
            role=role,
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            lookback_days=settings.lookback_days,
            fee_model=settings.fee_model,
            provenance=provenance,
            best_params=best["params"],
            best_exit_dict=best["exit_cfg"],
            best_metrics=best["metrics"],
        )
    )
    return _result(settings, trials, best, sampler_label, export_dir, board_path)


def _result(
    settings: SearchSettings,
    trials: list[dict[str, object]],
    best: dict[str, object],
    sampler_label: str,
    export_dir: Path | None,
    board_path: Path,
) -> AutotuneResult:
    return AutotuneResult(
        settings.strategy_name,
        settings.symbol,
        settings.timeframe,
        settings.lookback_days,
        len(trials),
        sampler_label,
        best["params"],
        best["exit_cfg"],
        best["metrics"],
        export_dir,
        board_path,
    )


def _publish_board(
    settings: SearchSettings,
    trials: list[dict[str, object]],
    best: dict[str, object],
    stamp: str,
    sampler: str,
) -> Path:
    directory = settings.root / "logs" / "research"
    directory.mkdir(parents=True, exist_ok=True)
    target = (
        directory
        / f"autotune_{settings.strategy_name}_{settings.timeframe}_{stamp}.json"
    )
    document = {
        "strategy": settings.strategy_name,
        "symbol": settings.symbol,
        "timeframe": settings.timeframe,
        "lookback_days": settings.lookback_days,
        "sampler_used": sampler,
        "fee_model": settings.fee_model,
        "n_trials": len(trials),
        "best_params": best["params"],
        "best_exit_cfg": best["exit_cfg"],
        "best_metrics": best["metrics"],
        "all_trials": trials,
    }
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2, default=str) + "\n")
    return target
