"""Ultimate Regime Accuracy & Forward Return Evaluator.

Measures classification precision, forward return edge, Sharpe ratio,
directional win rate, and regime persistence across market states.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from hypervector.regime.ultimate import detect_ultimate_regime


@dataclass
class RegimeAccuracyReport:
    symbol: str
    timeframe: str
    total_bars: int
    regime_stats: dict[str, dict[str, Any]]
    overall_directional_accuracy: float


def evaluate_regime_accuracy(
    df_1m: pd.DataFrame,
    df_5m: pd.DataFrame | None = None,
    df_15m: pd.DataFrame | None = None,
    forward_horizon: int = 15,  # 15 bars forward
) -> RegimeAccuracyReport:
    """Evaluate forward return accuracy and predictive edge of Ultimate Regime Classifier."""
    df_regime = detect_ultimate_regime(df_1m, df_5m, df_15m)
    c = df_1m["close"].astype(float)

    # Calculate forward returns (bps)
    fwd_ret_bps = ((c.shift(-forward_horizon) - c) / c * 10_000.0).fillna(0.0)

    combined = pd.DataFrame(
        {
            "regime": df_regime["regime_state"],
            "long_w": df_regime["long_weight"],
            "short_w": df_regime["short_weight"],
            "fwd_ret": fwd_ret_bps,
        },
        index=df_1m.index,
    )

    stats: dict[str, dict[str, Any]] = {}
    correct_count = 0
    eval_count = 0

    for state, group in combined.groupby("regime"):
        rets = group["fwd_ret"].to_numpy()
        n_bars = len(rets)
        if n_bars == 0:
            continue

        mean_ret = float(np.mean(rets))
        std_ret = float(np.std(rets)) if len(rets) > 1 else 1.0
        sharpe = (
            (mean_ret / std_ret * np.sqrt(365 * 24 * 60 / forward_horizon))
            if std_ret > 0
            else 0.0
        )

        if state == "BULL_MOMENTUM_EXPANSION":
            wins = int((rets > 0).sum())
            win_pct = (wins / n_bars * 100.0) if n_bars else 0.0
            correct_count += wins
            eval_count += n_bars
        elif state == "BEAR_MOMENTUM_EXPANSION":
            wins = int((rets < 0).sum())
            win_pct = (wins / n_bars * 100.0) if n_bars else 0.0
            correct_count += wins
            eval_count += n_bars
        elif state == "FUNDING_CARRY_REVERSAL":
            # Evaluates if long_w == 2.0 has positive return or short_w == 2.0 has negative return
            bull_sub = group[group["long_w"] > 1.0]["fwd_ret"]
            bear_sub = group[group["short_w"] > 1.0]["fwd_ret"]
            wins = int((bull_sub > 0).sum() + (bear_sub < 0).sum())
            tot = len(bull_sub) + len(bear_sub)
            win_pct = (wins / tot * 100.0) if tot else 0.0
            correct_count += wins
            eval_count += tot
        else:
            wins = int((np.abs(rets) < 10.0).sum())
            win_pct = (wins / n_bars * 100.0) if n_bars else 0.0

        stats[str(state)] = {
            "bar_count": n_bars,
            "allocation_pct": round(n_bars / len(combined) * 100.0, 2),
            "mean_fwd_ret_bps": round(mean_ret, 2),
            "win_pct": round(win_pct, 2),
            "sharpe_annualized": round(sharpe, 2),
        }

    overall_acc = (correct_count / eval_count * 100.0) if eval_count > 0 else 0.0

    symbol = str(df_1m.attrs.get("symbol", "BTC"))
    timeframe = str(df_1m.attrs.get("timeframe", "1m"))

    return RegimeAccuracyReport(
        symbol=symbol,
        timeframe=timeframe,
        total_bars=len(df_1m),
        regime_stats=stats,
        overall_directional_accuracy=round(overall_acc, 2),
    )
