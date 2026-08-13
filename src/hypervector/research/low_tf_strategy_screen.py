"""Friction-aware report-only screening for low-timeframe predictions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import math
import pandas as pd

from hypervector.ml.low_tf_directional_challenger import CANDIDATE_NAMES


FIXED_THRESHOLDS: tuple[float, ...] = (0.55, 0.60, 0.65, 0.70)
_REQUIRED_COLUMNS = frozenset(
    {
        "signal_ts_ms",
        "outcome_ts_ms",
        "side",
        "candidate",
        "prediction",
        "status",
        "gross_return_bps",
        "ambiguous",
    }
)


@dataclass(frozen=True)
class LowTimeframeScreenConfig:
    """Frozen candidate, threshold, and unit-notional friction contract."""

    thresholds: tuple[float, ...] = FIXED_THRESHOLDS
    candidates: tuple[str, ...] = CANDIDATE_NAMES
    maker_entry_fee_bps: float = 1.5
    taker_exit_fee_bps: float = 4.5

    def __post_init__(self) -> None:
        if not self.candidates or len(set(self.candidates)) != len(self.candidates):
            raise ValueError("screen candidates must be non-empty and unique")
        if not self.thresholds or len(set(self.thresholds)) != len(self.thresholds):
            raise ValueError("screen thresholds must be non-empty and unique")
        if not all(0.0 < value < 1.0 for value in self.thresholds):
            raise ValueError("screen thresholds must be between zero and one")
        fees = (self.maker_entry_fee_bps, self.taker_exit_fee_bps)
        if not all(math.isfinite(value) and value >= 0.0 for value in fees):
            raise ValueError("screen fees must be finite and non-negative")

    @property
    def round_trip_fee_bps(self) -> float:
        """Return the frozen entry plus exit fee in basis points."""
        return self.maker_entry_fee_bps + self.taker_exit_fee_bps


@dataclass(frozen=True)
class LowTimeframeScreenTrade:
    """One serialized, unit-notional post-fee screening outcome."""

    signal_ts_ms: int
    outcome_ts_ms: int
    side: str
    prediction: float
    status: str
    gross_return_bps: float
    fee_bps: float
    net_return_bps: float
    ambiguous: bool


@dataclass(frozen=True)
class LowTimeframeScreenTrial:
    """Economic summary for one fixed model and probability threshold."""

    candidate: str
    threshold: float
    trades: tuple[LowTimeframeScreenTrade, ...]
    trade_count: int
    wins: int
    losses: int
    breakeven: int
    net_pnl_bps: float
    gross_profit_bps: float
    gross_loss_bps: float
    profit_factor: float | None
    max_drawdown_bps: float
    total_fee_bps: float
    expired_occupied_signals: int
    probability_ties: int
    censored_signals: int
    timeout_trades: int
    ambiguous_trades: int
    monthly_net_bps: dict[str, float]


@dataclass(frozen=True)
class LowTimeframeScreenReport:
    """All frozen trials with an explicit denial of execution authority."""

    trials: tuple[LowTimeframeScreenTrial, ...]
    report_only: bool = True
    execution_authority: str = "none"
    place_attempted: bool = False


def screen_low_tf_strategies(
    rows: pd.DataFrame,
    config: LowTimeframeScreenConfig | None = None,
) -> LowTimeframeScreenReport:
    """Screen every configured model and threshold on one serialized stream."""
    resolved = config or LowTimeframeScreenConfig()
    _validate_rows(rows, resolved)
    trials = tuple(
        _screen_trial(rows, candidate, threshold, resolved)
        for candidate in resolved.candidates
        for threshold in resolved.thresholds
    )
    return LowTimeframeScreenReport(trials=trials)


def _validate_rows(rows: pd.DataFrame, config: LowTimeframeScreenConfig) -> None:
    missing = sorted(_REQUIRED_COLUMNS.difference(rows.columns))
    if missing:
        raise ValueError(f"screen rows missing columns: {missing}")
    if rows.empty:
        raise ValueError("screen rows must be non-empty")
    observed = set(rows["candidate"].astype(str))
    if observed != set(config.candidates):
        raise ValueError("screen rows must match the configured candidate set")
    predictions = rows["prediction"].astype(float)
    if not predictions.map(math.isfinite).all() or not predictions.between(0, 1).all():
        raise ValueError("screen probabilities must be finite and bounded")
    if (rows["outcome_ts_ms"] <= rows["signal_ts_ms"]).any():
        raise ValueError("screen outcomes must follow their signals")
    for identity, group in rows.groupby(["candidate", "signal_ts_ms"]):
        sides = group["side"].astype(str).tolist()
        if len(sides) != 2 or set(sides) != {"long", "short"}:
            raise ValueError(
                f"candidate signal {identity} must contain exactly one long and short"
            )


def _screen_trial(
    rows: pd.DataFrame,
    candidate: str,
    threshold: float,
    config: LowTimeframeScreenConfig,
) -> LowTimeframeScreenTrial:
    selected = rows.loc[rows["candidate"].eq(candidate)].sort_values(
        ["signal_ts_ms", "side"]
    )
    trades: list[LowTimeframeScreenTrade] = []
    occupied_until = -1
    expired = ties = censored = 0
    for _, group in selected.groupby("signal_ts_ms", sort=True):
        chosen, tied = _choose_side(group, threshold)
        ties += int(tied)
        if chosen is None:
            continue
        if int(chosen["signal_ts_ms"]) < occupied_until:
            expired += 1
            continue
        trade = _trade(chosen, config.round_trip_fee_bps)
        if trade is None:
            censored += 1
            continue
        trades.append(trade)
        occupied_until = trade.outcome_ts_ms
    return _summarize(candidate, threshold, trades, expired, ties, censored)


def _choose_side(
    group: pd.DataFrame,
    threshold: float,
) -> tuple[pd.Series | None, bool]:
    ranked = group.sort_values("prediction", ascending=False)
    highest = float(ranked.iloc[0]["prediction"])
    second = float(ranked.iloc[1]["prediction"])
    if highest < threshold:
        return None, False
    if math.isclose(highest, second, rel_tol=0.0, abs_tol=1e-12):
        return None, True
    return ranked.iloc[0], False


def _trade(row: pd.Series, fee_bps: float) -> LowTimeframeScreenTrade | None:
    gross_value = row["gross_return_bps"]
    if pd.isna(gross_value) or str(row["status"]) == "truncated":
        return None
    gross = float(gross_value)
    if not math.isfinite(gross):
        raise ValueError("screen gross return must be finite")
    return LowTimeframeScreenTrade(
        signal_ts_ms=int(row["signal_ts_ms"]),
        outcome_ts_ms=int(row["outcome_ts_ms"]),
        side=str(row["side"]),
        prediction=float(row["prediction"]),
        status=str(row["status"]),
        gross_return_bps=gross,
        fee_bps=fee_bps,
        net_return_bps=gross - fee_bps,
        ambiguous=bool(row["ambiguous"]),
    )


def _summarize(
    candidate: str,
    threshold: float,
    trades: list[LowTimeframeScreenTrade],
    expired: int,
    ties: int,
    censored: int,
) -> LowTimeframeScreenTrial:
    net = [trade.net_return_bps for trade in trades]
    profits = sum(value for value in net if value > 0.0)
    losses = -sum(value for value in net if value < 0.0)
    return LowTimeframeScreenTrial(
        candidate=candidate,
        threshold=threshold,
        trades=tuple(trades),
        trade_count=len(trades),
        wins=sum(value > 0.0 for value in net),
        losses=sum(value < 0.0 for value in net),
        breakeven=sum(value == 0.0 for value in net),
        net_pnl_bps=sum(net),
        gross_profit_bps=profits,
        gross_loss_bps=losses,
        profit_factor=profits / losses if losses > 0.0 else None,
        max_drawdown_bps=_max_drawdown(net),
        total_fee_bps=len(trades) * (trades[0].fee_bps if trades else 0.0),
        expired_occupied_signals=expired,
        probability_ties=ties,
        censored_signals=censored,
        timeout_trades=sum(trade.status == "timeout" for trade in trades),
        ambiguous_trades=sum(trade.ambiguous for trade in trades),
        monthly_net_bps=_monthly_net(trades),
    )


def _max_drawdown(net_returns: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in net_returns:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _monthly_net(trades: list[LowTimeframeScreenTrade]) -> dict[str, float]:
    output: dict[str, float] = {}
    for trade in trades:
        stamp = datetime.fromtimestamp(trade.outcome_ts_ms / 1_000.0, tz=UTC)
        month = stamp.strftime("%Y-%m")
        output[month] = output.get(month, 0.0) + trade.net_return_bps
    return output
