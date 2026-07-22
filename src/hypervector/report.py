"""Per-track ranking boards (SRS_HV1_RANK_PRIMARY, SRS_HV1_METRICS)."""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

METRIC_COLUMNS = [
    "strategy",
    "params",
    "net_pnl",
    "total_return_pct",
    "sharpe",
    "trade_count",
    "wins",
    "losses",
    "win_pct",
    "max_drawdown",
    "status",
]


def rank_trials(
    rows: Sequence[dict[str, Any]],
    *,
    primary: str = "net_pnl",
    secondary: str = "total_return_pct",
) -> pd.DataFrame:
    """Order trials primarily by net PnL / total return; no risk filtering."""
    if not rows:
        return pd.DataFrame(columns=METRIC_COLUMNS)
    df = pd.DataFrame(list(rows))
    for col in METRIC_COLUMNS:
        if col not in df.columns:
            df[col] = None
    # Technical failures last; healthy trials ranked by primary then secondary
    df["_ok"] = (df["status"].fillna("ok") == "ok").astype(int)
    df = df.sort_values(
        by=["_ok", primary, secondary],
        ascending=[False, False, False],
        kind="mergesort",
    ).drop(columns=["_ok"])
    return df.reset_index(drop=True)
