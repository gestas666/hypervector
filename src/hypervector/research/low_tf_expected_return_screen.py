"""Serialized expected-return screening under explicit round-trip friction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import math
import pandas as pd

from hypervector.ml.low_tf_directional_challenger import RETURN_CANDIDATE_NAMES


_REQUIRED_COLUMNS = frozenset(
    {
        "signal_ts_ms",
        "outcome_ts_ms",
        "side",
        "candidate",
        "predicted_gross_return_bps",
        "gross_return_bps",
        "status",
        "ambiguous",
    }
)


@dataclass(frozen=True)
class ExpectedReturnScreenConfig:
    """Frozen candidates and nominal/stress round-trip cost surfaces."""

    candidates: tuple[str, ...] = RETURN_CANDIDATE_NAMES
    round_trip_costs_bps: tuple[float, ...] = (13.0, 20.0)

    def __post_init__(self) -> None:
        if not self.candidates or len(set(self.candidates)) != len(self.candidates):
            raise ValueError("expected-return candidates must be non-empty and unique")
        costs = self.round_trip_costs_bps
        if not costs or len(set(costs)) != len(costs):
            raise ValueError("round-trip costs must be non-empty and unique")
        if not all(math.isfinite(value) and value > 0.0 for value in costs):
            raise ValueError("round-trip costs must be finite and positive")


@dataclass(frozen=True)
class ExpectedReturnScreenTrade:
    """One realized unit-notional trade selected by an OOS return forecast."""

    signal_ts_ms: int
    outcome_ts_ms: int
    side: str
    predicted_gross_return_bps: float
    gross_return_bps: float
    round_trip_cost_bps: float
    net_return_bps: float
    status: str
    ambiguous: bool


@dataclass(frozen=True)
class ExpectedReturnScreenTrial:
    """One candidate and cost surface on a serialized position stream."""

    candidate: str
    round_trip_cost_bps: float
    trades: tuple[ExpectedReturnScreenTrade, ...]
    trade_count: int
    long_trades: int
    short_trades: int
    wins: int
    losses: int
    net_pnl_bps: float
    profit_factor: float | None
    max_drawdown_bps: float
    total_cost_bps: float
    expired_occupied_signals: int
    below_hurdle_signals: int
    prediction_ties: int
    monthly_net_bps: dict[str, float]


@dataclass(frozen=True)
class ExpectedReturnScreenReport:
    """All return screens with an explicit denial of execution authority."""

    trials: tuple[ExpectedReturnScreenTrial, ...]
    report_only: bool = True
    execution_authority: str = "none"
    place_attempted: bool = False


def screen_low_tf_expected_returns(
    rows: pd.DataFrame,
    config: ExpectedReturnScreenConfig | None = None,
) -> ExpectedReturnScreenReport:
    """Select the higher side only when expected gross return clears cost."""
    resolved = config or ExpectedReturnScreenConfig()
    _validate_rows(rows, resolved)
    trials = tuple(
        _screen_trial(rows, candidate, cost)
        for candidate in resolved.candidates
        for cost in resolved.round_trip_costs_bps
    )
    return ExpectedReturnScreenReport(trials)


def _validate_rows(rows: pd.DataFrame, config: ExpectedReturnScreenConfig) -> None:
    missing = sorted(_REQUIRED_COLUMNS.difference(rows.columns))
    if missing:
        raise ValueError(f"expected-return screen rows missing: {missing}")
    if rows.empty or set(rows["candidate"].astype(str)) != set(config.candidates):
        raise ValueError("screen rows must match configured return candidates")
    numeric = rows[["predicted_gross_return_bps", "gross_return_bps"]]
    if not numeric.map(lambda value: math.isfinite(float(value))).all().all():
        raise ValueError("expected and realized returns must be finite")
    if (rows["outcome_ts_ms"] <= rows["signal_ts_ms"]).any():
        raise ValueError("expected-return outcomes must follow their signals")
    for identity, group in rows.groupby(["candidate", "signal_ts_ms"]):
        sides = group["side"].astype(str).tolist()
        if len(sides) != 2 or set(sides) != {"long", "short"}:
            raise ValueError(f"return signal {identity} requires a side pair")


def _screen_trial(
    rows: pd.DataFrame,
    candidate: str,
    cost_bps: float,
) -> ExpectedReturnScreenTrial:
    selected = rows.loc[rows["candidate"].eq(candidate)].sort_values(
        ["signal_ts_ms", "side"]
    )
    trades: list[ExpectedReturnScreenTrade] = []
    occupied_until = -1
    expired = below = ties = 0
    for _, group in selected.groupby("signal_ts_ms", sort=True):
        chosen, reason = _choose_side(group, cost_bps)
        below += int(reason == "below_hurdle")
        ties += int(reason == "tie")
        if chosen is None:
            continue
        if int(chosen["signal_ts_ms"]) < occupied_until:
            expired += 1
            continue
        trade = _trade(chosen, cost_bps)
        trades.append(trade)
        occupied_until = trade.outcome_ts_ms
    return _summarize(candidate, cost_bps, trades, expired, below, ties)


def _choose_side(
    group: pd.DataFrame,
    hurdle_bps: float,
) -> tuple[pd.Series | None, str | None]:
    ranked = group.sort_values("predicted_gross_return_bps", ascending=False)
    highest = float(ranked.iloc[0]["predicted_gross_return_bps"])
    second = float(ranked.iloc[1]["predicted_gross_return_bps"])
    if highest < hurdle_bps:
        return None, "below_hurdle"
    if math.isclose(highest, second, rel_tol=0.0, abs_tol=1e-12):
        return None, "tie"
    return ranked.iloc[0], None


def _trade(row: pd.Series, cost_bps: float) -> ExpectedReturnScreenTrade:
    gross = float(row["gross_return_bps"])
    return ExpectedReturnScreenTrade(
        signal_ts_ms=int(row["signal_ts_ms"]),
        outcome_ts_ms=int(row["outcome_ts_ms"]),
        side=str(row["side"]),
        predicted_gross_return_bps=float(row["predicted_gross_return_bps"]),
        gross_return_bps=gross,
        round_trip_cost_bps=cost_bps,
        net_return_bps=gross - cost_bps,
        status=str(row["status"]),
        ambiguous=bool(row["ambiguous"]),
    )


def _summarize(
    candidate: str,
    cost_bps: float,
    trades: list[ExpectedReturnScreenTrade],
    expired: int,
    below: int,
    ties: int,
) -> ExpectedReturnScreenTrial:
    net = [trade.net_return_bps for trade in trades]
    profits = sum(value for value in net if value > 0.0)
    losses = -sum(value for value in net if value < 0.0)
    return ExpectedReturnScreenTrial(
        candidate=candidate,
        round_trip_cost_bps=cost_bps,
        trades=tuple(trades),
        trade_count=len(trades),
        long_trades=sum(trade.side == "long" for trade in trades),
        short_trades=sum(trade.side == "short" for trade in trades),
        wins=sum(value > 0.0 for value in net),
        losses=sum(value < 0.0 for value in net),
        net_pnl_bps=sum(net),
        profit_factor=profits / losses if losses > 0.0 else None,
        max_drawdown_bps=_max_drawdown(net),
        total_cost_bps=len(trades) * cost_bps,
        expired_occupied_signals=expired,
        below_hurdle_signals=below,
        prediction_ties=ties,
        monthly_net_bps=_monthly_net(trades),
    )


def _max_drawdown(net_returns: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in net_returns:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _monthly_net(trades: list[ExpectedReturnScreenTrade]) -> dict[str, float]:
    output: dict[str, float] = {}
    for trade in trades:
        stamp = datetime.fromtimestamp(trade.outcome_ts_ms / 1_000.0, tz=UTC)
        month = stamp.strftime("%Y-%m")
        output[month] = output.get(month, 0.0) + trade.net_return_bps
    return output
