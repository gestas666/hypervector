"""Economic summaries for accepted one-minute order-flow impulse outcomes."""

from __future__ import annotations

import numpy as np
import pandas as pd


_REQUIRED = frozenset(
    {
        "arm",
        "symbol",
        "side",
        "outcome_time_utc",
        "accepted",
        "status",
        "net_return_bps_nominal",
        "net_return_bps_stress",
    }
)
_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("arm", ("arm",)),
    ("arm_symbol", ("arm", "symbol")),
    ("arm_symbol_side", ("arm", "symbol", "side")),
)


def summarize_orderflow_outcomes(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Return arm, asset, and side economics for nominal and stress costs."""
    missing = sorted(_REQUIRED.difference(outcomes.columns))
    if missing:
        raise ValueError(f"order-flow summary missing columns: {missing}")
    accepted = outcomes.loc[outcomes["accepted"].astype(bool)].copy()
    if accepted.empty:
        return pd.DataFrame(columns=_summary_columns())
    records: list[dict[str, object]] = []
    for scope, dimensions in _GROUPS:
        for key, group in accepted.groupby(list(dimensions), sort=True):
            identity = _identity(dimensions, key)
            for cost in ("nominal", "stress"):
                values = group[f"net_return_bps_{cost}"].astype(float)
                records.append(_summary_row(scope, identity, cost, group, values))
    return pd.DataFrame(records, columns=_summary_columns())


def _identity(dimensions: tuple[str, ...], key: object) -> dict[str, object]:
    values = key if isinstance(key, tuple) else (key,)
    identity = {"arm": None, "symbol": None, "side": None}
    identity.update(dict(zip(dimensions, values, strict=True)))
    return identity


def _summary_row(
    scope: str,
    identity: dict[str, object],
    cost: str,
    group: pd.DataFrame,
    values: pd.Series,
) -> dict[str, object]:
    finite = values[np.isfinite(values)]
    if len(finite) != len(values):
        raise ValueError("accepted order-flow economics must be finite")
    profits = float(finite.loc[finite.gt(0.0)].sum())
    losses = float(-finite.loc[finite.lt(0.0)].sum())
    largest = float(finite.max()) if len(finite) else 0.0
    return {
        "scope": scope,
        **identity,
        "cost": cost,
        "trades": len(finite),
        "wins": int(finite.gt(0.0).sum()),
        "losses": int(finite.lt(0.0).sum()),
        "breakeven": int(finite.eq(0.0).sum()),
        "net_bps": float(finite.sum()),
        "mean_bps": float(finite.mean()),
        "median_bps": float(finite.median()),
        "profit_factor": profits / losses if losses > 0.0 else None,
        "maximum_drawdown_bps": _maximum_drawdown(finite),
        "largest_winner_bps": largest,
        "net_ex_largest_winner_bps": float(finite.sum() - max(largest, 0.0)),
        "targets": int(group["status"].eq("target").sum()),
        "stops": int(group["status"].isin(("stop", "ambiguous_stop_first")).sum()),
        "timeouts": int(group["status"].eq("timeout").sum()),
    }


def _maximum_drawdown(values: pd.Series) -> float:
    equity = values.cumsum().to_numpy(dtype=float)
    if not len(equity):
        return 0.0
    peaks = np.maximum.accumulate(np.concatenate(([0.0], equity)))
    path = np.concatenate(([0.0], equity))
    return float(np.max(peaks - path))


def _summary_columns() -> list[str]:
    return [
        "scope",
        "arm",
        "symbol",
        "side",
        "cost",
        "trades",
        "wins",
        "losses",
        "breakeven",
        "net_bps",
        "mean_bps",
        "median_bps",
        "profit_factor",
        "maximum_drawdown_bps",
        "largest_winner_bps",
        "net_ex_largest_winner_bps",
        "targets",
        "stops",
        "timeouts",
    ]
