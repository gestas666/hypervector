"""Economic and path-risk summaries for liquidity-sweep outcomes."""

from __future__ import annotations

import numpy as np
import pandas as pd


_REQUIRED = frozenset(
    {
        "arm",
        "symbol",
        "side",
        "context_15m",
        "outcome_time_utc",
        "accepted",
        "status",
        "net_return_bps_nominal",
        "net_return_bps_stress",
        "sampled_mtm_peak_bps",
        "sampled_mtm_trough_bps",
        "sampled_mtm_maximum_drawdown_bps",
        "maximum_adverse_excursion_bps",
        "maximum_favorable_excursion_bps",
        "hold_minutes",
    }
)
_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("arm", ("arm",)),
    ("arm_symbol", ("arm", "symbol")),
    ("arm_symbol_side", ("arm", "symbol", "side")),
    ("arm_regime", ("arm", "context_15m")),
)


def summarize_liquidity_sweep_outcomes(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Return arm, asset, side, and regime economics at both friction levels."""
    missing = sorted(_REQUIRED.difference(outcomes.columns))
    if missing:
        raise ValueError(f"liquidity sweep summary missing columns: {missing}")
    accepted = outcomes.loc[outcomes["accepted"].astype(bool)].copy()
    if accepted.empty:
        return pd.DataFrame()
    records: list[dict[str, object]] = []
    for scope, dimensions in _GROUPS:
        for key, group in accepted.groupby(list(dimensions), sort=True):
            identity = _identity(dimensions, key)
            for cost in ("nominal", "stress"):
                records.append(_summary_row(scope, identity, cost, group))
    return pd.DataFrame(records)


def _identity(dimensions: tuple[str, ...], key: object) -> dict[str, object]:
    values = key if isinstance(key, tuple) else (key,)
    identity = {
        "arm": None,
        "symbol": None,
        "side": None,
        "context_15m": None,
    }
    identity.update(dict(zip(dimensions, values, strict=True)))
    return identity


def _summary_row(
    scope: str,
    identity: dict[str, object],
    cost: str,
    group: pd.DataFrame,
) -> dict[str, object]:
    values = group[f"net_return_bps_{cost}"].astype(float)
    if not np.isfinite(values).all():
        raise ValueError("accepted liquidity sweep economics must be finite")
    profits = float(values.loc[values.gt(0.0)].sum())
    losses = float(-values.loc[values.lt(0.0)].sum())
    largest = float(values.max()) if len(values) else 0.0
    return {
        "scope": scope,
        **identity,
        "cost": cost,
        "trades": len(values),
        "wins": int(values.gt(0.0).sum()),
        "losses": int(values.lt(0.0).sum()),
        "net_bps": float(values.sum()),
        "mean_bps": float(values.mean()),
        "median_bps": float(values.median()),
        "profit_factor": profits / losses if losses > 0.0 else None,
        "sampled_mtm_maximum_drawdown_bps": _sampled_mtm_drawdown(group, cost),
        "mean_mae_bps": float(group["maximum_adverse_excursion_bps"].mean()),
        "mean_mfe_bps": float(group["maximum_favorable_excursion_bps"].mean()),
        "mean_hold_minutes": float(group["hold_minutes"].mean()),
        "largest_winner_bps": largest,
        "net_ex_largest_winner_bps": float(values.sum() - max(largest, 0.0)),
        "targets": int(group["status"].eq("target").sum()),
        "stops": int(group["status"].isin(("stop", "ambiguous_stop_first")).sum()),
        "timeouts": int(group["status"].eq("timeout").sum()),
    }


def _sampled_mtm_drawdown(group: pd.DataFrame, cost: str) -> float:
    ordered = group.sort_values("outcome_time_utc")
    cumulative = 0.0
    peak = 0.0
    maximum = 0.0
    for _, row in ordered.iterrows():
        haircut = float(row["net_return_bps_nominal"] - row[f"net_return_bps_{cost}"])
        path_peak = cumulative + float(row["sampled_mtm_peak_bps"]) - haircut
        path_trough = cumulative + float(row["sampled_mtm_trough_bps"]) - haircut
        maximum = max(maximum, peak - path_trough)
        maximum = max(
            maximum,
            float(row["sampled_mtm_maximum_drawdown_bps"]),
        )
        peak = max(peak, path_peak)
        cumulative += float(row[f"net_return_bps_{cost}"])
        peak = max(peak, cumulative)
    return maximum
