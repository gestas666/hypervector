"""Causal report-only feasibility screen for OI-conditioned deleveraging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd


_MINUTE: Final = pd.Timedelta(minutes=1)
_REQUIRED_COLUMNS: Final = frozenset(
    {
        "minute",
        "close",
        "trade_imbalance",
        "book_imbalance",
        "open_interest",
        "first_bid",
        "first_ask",
        "first_quote_at",
    }
)


@dataclass(frozen=True)
class OiDeleveragingConfig:
    """Frozen causal event and execution parameters."""

    warmup_bars: int = 288
    minimum_shock_bps: float = 13.0
    minimum_oi_contraction_pct: float = -0.0005
    price_quantile: float = 0.9
    oi_quantile: float = 0.1
    primary_horizon_minutes: int = 15
    maximum_quote_delay_seconds: int = 15

    def __post_init__(self) -> None:
        if self.warmup_bars <= 0 or self.primary_horizon_minutes <= 0:
            raise ValueError("warmup and primary horizon must be positive")
        if not 0.0 < self.price_quantile < 1.0:
            raise ValueError("price_quantile must be between zero and one")
        if not 0.0 < self.oi_quantile < 1.0:
            raise ValueError("oi_quantile must be between zero and one")
        if self.minimum_shock_bps <= 0.0:
            raise ValueError("minimum_shock_bps must be positive")
        if self.minimum_oi_contraction_pct >= 0.0:
            raise ValueError("minimum OI contraction must be negative")
        if self.maximum_quote_delay_seconds <= 0:
            raise ValueError("maximum quote delay must be positive")


@dataclass(frozen=True)
class OiDeleveragingTrade:
    """One executable fixed-horizon event outcome."""

    symbol: str
    decision_at: pd.Timestamp
    side: str
    exhausted: bool
    entry_price: float
    exit_price: float
    gross_bps: float
    net_bps: float


@dataclass(frozen=True)
class OiDeleveragingRejection:
    """One technically unresolved event that cannot enter the result."""

    symbol: str
    decision_at: pd.Timestamp
    reason: str


@dataclass(frozen=True)
class OiDeleveragingReplay:
    """Immutable in-memory replay result."""

    trades: tuple[OiDeleveragingTrade, ...]
    rejections: tuple[OiDeleveragingRejection, ...]


def build_signals(
    minutes: pd.DataFrame,
    symbol: str,
    config: OiDeleveragingConfig,
) -> pd.DataFrame:
    """Build prior-only forced-deleveraging signals from complete minutes."""
    rows = _validated_minutes(minutes)
    bars = _five_minute_bars(rows)
    featured = _with_causal_thresholds(bars, config)
    eligible = featured.loc[_eligible_mask(featured, config)].copy()
    eligible["symbol"] = symbol
    eligible["primary_horizon_minutes"] = config.primary_horizon_minutes
    eligible["shock_side"] = eligible["shock_sign"].map({-1: "down", 1: "up"})
    eligible["terminal_trade_exhaustion"] = (
        eligible["shock_sign"] * eligible["trade_imbalance"] < 0.0
    )
    eligible["terminal_book_replenishment"] = (
        eligible["shock_sign"] * eligible["book_imbalance"] < 0.0
    )
    eligible["exhausted"] = (
        eligible["terminal_trade_exhaustion"] & eligible["terminal_book_replenishment"]
    )
    return _suppress_overlaps(eligible, config.primary_horizon_minutes)


def replay_signals(
    minutes: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    round_trip_cost_bps: float,
    maximum_quote_delay_seconds: int = 15,
) -> OiDeleveragingReplay:
    """Replay signals against first causal bid/ask quotes at entry and exit."""
    if round_trip_cost_bps < 0.0:
        raise ValueError("round-trip cost must be nonnegative")
    rows = _validated_minutes(minutes).set_index("minute", drop=False)
    trades: list[OiDeleveragingTrade] = []
    rejected: list[OiDeleveragingRejection] = []
    for signal in signals.to_dict("records"):
        result = _replay_one(
            rows, signal, round_trip_cost_bps, maximum_quote_delay_seconds
        )
        if isinstance(result, OiDeleveragingTrade):
            trades.append(result)
        else:
            rejected.append(result)
    return OiDeleveragingReplay(tuple(trades), tuple(rejected))


def assess_development(
    replay: OiDeleveragingReplay,
    *,
    symbols: tuple[str, ...],
) -> dict[str, object]:
    """Apply the preregistered feasibility criterion without tuning."""
    trades = pd.DataFrame([trade.__dict__ for trade in replay.trades])
    failures: list[str] = []
    if len(trades) < 20:
        failures.append("minimum_total_events")
    counts = _symbol_counts(trades, symbols)
    if any(counts[symbol] < 5 for symbol in symbols):
        failures.append("minimum_events_per_symbol")
    exhausted = _exhausted_trades(trades)
    if exhausted.empty or exhausted["gross_bps"].mean() < 26.0:
        failures.append("exhausted_mean_gross")
    if exhausted.empty or exhausted["gross_bps"].median() < 26.0:
        failures.append("exhausted_median_gross")
    if any(_symbol_mean(trades, symbol) <= 0.0 for symbol in symbols):
        failures.append("symbol_consistency")
    if _largest_winner_share(exhausted) > 50.0:
        failures.append("largest_winner_share")
    if replay.rejections:
        failures.append("technical_rejections")
    passed = not failures
    return {
        "passed": passed,
        "confirmation_authorized": passed,
        "failures": failures,
        "events": len(trades),
        "events_by_symbol": counts,
        "technical_rejections": len(replay.rejections),
    }


def _validated_minutes(minutes: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_REQUIRED_COLUMNS.difference(minutes.columns))
    if missing:
        raise ValueError(f"OI deleveraging minutes missing columns: {missing}")
    rows = minutes.copy()
    rows["minute"] = pd.to_datetime(rows["minute"], utc=True)
    rows["first_quote_at"] = pd.to_datetime(rows["first_quote_at"], utc=True)
    rows = rows.sort_values("minute").reset_index(drop=True)
    if rows["minute"].duplicated().any():
        raise ValueError("OI deleveraging minutes contain duplicate timestamps")
    numeric = _REQUIRED_COLUMNS.difference({"minute", "first_quote_at"})
    if rows[list(numeric)].isna().any().any():
        raise ValueError("OI deleveraging minutes contain null values")
    return rows


def _five_minute_bars(rows: pd.DataFrame) -> pd.DataFrame:
    rows = rows.copy()
    rows["segment"] = rows["minute"].diff().ne(_MINUTE).cumsum()
    rows["bar_open"] = rows["minute"].dt.floor("5min")
    bars: list[dict[str, object]] = []
    for (segment, bar_open), group in rows.groupby(["segment", "bar_open"]):
        if len(group) != 5 or not _is_contiguous(group["minute"]):
            continue
        terminal = group.iloc[-1]
        bars.append(
            {
                "segment": int(segment),
                "bar_open": bar_open,
                "decision_at": terminal["minute"] + _MINUTE,
                "close": float(terminal["close"]),
                "open_interest": float(terminal["open_interest"]),
                "trade_imbalance": float(terminal["trade_imbalance"]),
                "book_imbalance": float(terminal["book_imbalance"]),
            }
        )
    return pd.DataFrame.from_records(bars)


def _with_causal_thresholds(
    bars: pd.DataFrame, config: OiDeleveragingConfig
) -> pd.DataFrame:
    if bars.empty:
        return bars.assign(
            shock_bps=pd.Series(dtype=float),
            oi_change_pct=pd.Series(dtype=float),
            shock_threshold_bps=pd.Series(dtype=float),
            oi_threshold_pct=pd.Series(dtype=float),
            shock_sign=pd.Series(dtype=int),
        )
    result = bars.copy()
    grouped = result.groupby("segment", sort=False)
    result["shock_bps"] = grouped["close"].pct_change() * 10_000.0
    result["oi_change_pct"] = grouped["open_interest"].pct_change()
    result["shock_threshold_bps"] = grouped["shock_bps"].transform(
        lambda values: values.abs()
        .shift(1)
        .rolling(config.warmup_bars, min_periods=config.warmup_bars)
        .quantile(config.price_quantile)
    )
    result["oi_threshold_pct"] = grouped["oi_change_pct"].transform(
        lambda values: values.shift(1)
        .rolling(config.warmup_bars, min_periods=config.warmup_bars)
        .quantile(config.oi_quantile)
    )
    result["shock_sign"] = result["shock_bps"].map(lambda value: 1 if value > 0 else -1)
    return result


def _eligible_mask(rows: pd.DataFrame, config: OiDeleveragingConfig) -> pd.Series:
    return (
        rows["shock_threshold_bps"].notna()
        & rows["oi_threshold_pct"].notna()
        & rows["shock_bps"].abs().ge(config.minimum_shock_bps)
        & rows["shock_bps"].abs().ge(rows["shock_threshold_bps"])
        & rows["oi_change_pct"].le(config.minimum_oi_contraction_pct)
        & rows["oi_change_pct"].le(rows["oi_threshold_pct"])
    )


def _suppress_overlaps(signals: pd.DataFrame, horizon_minutes: int) -> pd.DataFrame:
    retained: list[int] = []
    unavailable_until: pd.Timestamp | None = None
    for index, row in signals.sort_values("decision_at").iterrows():
        decision = pd.Timestamp(row["decision_at"])
        if unavailable_until is not None and decision <= unavailable_until:
            continue
        retained.append(index)
        unavailable_until = decision + pd.Timedelta(minutes=horizon_minutes)
    return signals.loc[retained].sort_values("decision_at").reset_index(drop=True)


def _replay_one(
    rows: pd.DataFrame,
    signal: dict[str, object],
    cost_bps: float,
    maximum_delay_seconds: int,
) -> OiDeleveragingTrade | OiDeleveragingRejection:
    decision = pd.Timestamp(signal["decision_at"])
    exit_time = decision + pd.Timedelta(minutes=int(signal["primary_horizon_minutes"]))
    entry, reason = _quote(rows, decision, maximum_delay_seconds, "entry")
    if reason is not None:
        return OiDeleveragingRejection(str(signal["symbol"]), decision, reason)
    exit_row, reason = _quote(rows, exit_time, maximum_delay_seconds, "exit")
    if reason is not None:
        return OiDeleveragingRejection(str(signal["symbol"]), decision, reason)
    assert entry is not None and exit_row is not None
    return _trade(signal, decision, entry, exit_row, cost_bps)


def _quote(
    rows: pd.DataFrame,
    minute: pd.Timestamp,
    maximum_delay_seconds: int,
    role: str,
) -> tuple[pd.Series | None, str | None]:
    if minute not in rows.index:
        return None, f"missing_{role}_quote"
    row = rows.loc[minute]
    delay = (pd.Timestamp(row["first_quote_at"]) - minute).total_seconds()
    if delay < 0.0 or delay > maximum_delay_seconds:
        return None, f"stale_{role}_quote"
    if float(row["first_bid"]) >= float(row["first_ask"]):
        return None, f"crossed_{role}_book"
    return row, None


def _trade(
    signal: dict[str, object],
    decision: pd.Timestamp,
    entry: pd.Series,
    exit_row: pd.Series,
    cost_bps: float,
) -> OiDeleveragingTrade:
    side = "long" if str(signal["shock_side"]) == "down" else "short"
    if side == "long":
        entry_price, exit_price = (
            float(entry["first_ask"]),
            float(exit_row["first_bid"]),
        )
        gross = (exit_price / entry_price - 1.0) * 10_000.0
    else:
        entry_price, exit_price = (
            float(entry["first_bid"]),
            float(exit_row["first_ask"]),
        )
        gross = (entry_price / exit_price - 1.0) * 10_000.0
    return OiDeleveragingTrade(
        str(signal["symbol"]),
        decision,
        side,
        bool(signal["exhausted"]),
        entry_price,
        exit_price,
        gross,
        gross - cost_bps,
    )


def _is_contiguous(minutes: pd.Series) -> bool:
    return bool(minutes.diff().dropna().eq(_MINUTE).all())


def _symbol_counts(trades: pd.DataFrame, symbols: tuple[str, ...]) -> dict[str, int]:
    return {
        symbol: int(trades.get("symbol", pd.Series(dtype=str)).eq(symbol).sum())
        for symbol in symbols
    }


def _exhausted_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if "exhausted" not in trades:
        return trades.iloc[0:0]
    return trades.loc[trades["exhausted"].eq(True)]


def _symbol_mean(trades: pd.DataFrame, symbol: str) -> float:
    selected = trades.loc[trades.get("symbol", pd.Series(dtype=str)).eq(symbol)]
    return float(selected["gross_bps"].mean()) if not selected.empty else float("-inf")


def _largest_winner_share(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 100.0
    positive = trades.loc[trades["gross_bps"].gt(0.0), "gross_bps"]
    if positive.empty:
        return 100.0
    return float(positive.max() / positive.sum() * 100.0)
