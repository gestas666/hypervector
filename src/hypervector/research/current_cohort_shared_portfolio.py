"""Exact-cap chronological replay helpers for the current live cohort."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import math
from pathlib import Path

from hypervector.research.hype_breakout_exit_models import HypeExitTrade
from hypervector.research.shared_trade_portfolio import (
    ScaledSharedTrade,
    SharedTradeOutcome,
    SharedTradeReplayConfig,
    replay_shared_trade_outcomes,
)

_SOL_RANGE_ARTIFACT_NAMES = (
    "multi_asset_range_onset_event_replay_SOL_20251126_20260110_v2_capacity_posthoc.json",
    "multi_asset_range_onset_event_replay_SOL_20260124T0100_20260226_v3_capacity_posthoc.json",
    "multi_asset_range_onset_event_replay_SOL_20260226_20260501_v2_capacity_posthoc.json",
    "multi_asset_range_onset_event_replay_SOL_20260501_20260507T20_v1_clean_capacity_posthoc.json",
    "multi_asset_range_onset_event_replay_SOL_20260523T08_20260527T21_v1_clean_capacity_posthoc.json",
    "multi_asset_range_onset_event_replay_SOL_20260528T05_20260602_v1_clean_capacity_posthoc.json",
    "multi_asset_range_onset_event_replay_SOL_20260614T10_20260625_v1_clean_capacity_posthoc.json",
    "multi_asset_range_onset_event_replay_SOL_20260625_20260710_v1_clean_capacity_posthoc.json",
    "multi_asset_range_onset_event_replay_SOL_20260710_20260718T01_v1_clean_capacity_posthoc.json",
    "multi_asset_range_onset_event_replay_SOL_20260718T01_20260721T23_v1_clean_capacity_posthoc.json",
    "multi_asset_range_onset_event_replay_SOL_20260721T23_20260725_v1_clean_capacity_posthoc.json",
    "multi_asset_range_onset_event_replay_SOL_20260727T21_20260730T07_v2_resolved_capacity_posthoc.json",
)


@dataclass(frozen=True)
class CohortTradeSpec:
    """One provider-symbol live sizing and entry-fee contract."""

    strategy_id: str
    symbol: str
    notional_usd: float
    leverage: float
    entry_fee_bps: float
    reference_equity_usd: float = 500.0

    def __post_init__(self) -> None:
        """Reject incomplete identities and impossible fixed-cap sizing."""
        if not self.strategy_id.strip() or not self.symbol.strip():
            raise ValueError("cohort strategy_id and symbol must be non-empty")
        _positive(self.notional_usd, "notional_usd")
        _positive(self.leverage, "leverage")
        _nonnegative(self.entry_fee_bps, "entry_fee_bps")
        _positive(self.reference_equity_usd, "reference_equity_usd")
        if self.margin_fraction > 1.0:
            raise ValueError(
                "cohort fixed notional requires more than full equity margin"
            )

    @property
    def margin_fraction(self) -> float:
        """Return effective reference-equity margin after the notional cap."""
        return self.notional_usd / self.leverage / self.reference_equity_usd


@dataclass(frozen=True)
class CohortOutcome:
    """One normalized lifecycle plus immutable strategy attribution."""

    strategy_id: str
    side: str
    outcome: SharedTradeOutcome

    @property
    def trade_id(self) -> str:
        """Expose the underlying unique lifecycle identity."""
        return self.outcome.trade_id


def default_sol_range_artifact_paths() -> tuple[Path, ...]:
    """Return the shared immutable SOL range-onset evidence block paths."""
    root = Path("data/logs/research")
    return tuple(root / name for name in _SOL_RANGE_ARTIFACT_NAMES)


def adapt_hulk_payloads(
    payloads: tuple[dict[str, object], ...],
    spec: CohortTradeSpec,
) -> tuple[CohortOutcome, ...]:
    """Normalize exact Hulk artifact lifecycles to the current fixed cap."""
    adapted: list[CohortOutcome] = []
    for payload_index, payload in enumerate(payloads):
        _validate_hulk_payload(payload, spec)
        replay = _mapping(payload, "replay")
        for trade_index, trade in enumerate(_mapping_rows(replay, "trades")):
            if _text(trade, "symbol").upper() != spec.symbol.upper():
                continue
            adapted.append(_adapt_hulk_trade(trade, spec, payload_index, trade_index))
    if not adapted:
        raise ValueError(f"Hulk artifacts contain no {spec.symbol} trades")
    return tuple(adapted)


def adapt_breakout_trades(
    trades: tuple[HypeExitTrade, ...],
    spec: CohortTradeSpec,
) -> tuple[CohortOutcome, ...]:
    """Normalize unit-notional breakout trades to an exact live notional cap."""
    return tuple(
        _adapt_breakout_trade(trade, spec, index) for index, trade in enumerate(trades)
    )


def adapt_range_event_payloads(
    payloads: tuple[dict[str, object], ...],
    spec: CohortTradeSpec,
    *,
    effective_exposure: float = 0.15,
) -> tuple[CohortOutcome, ...]:
    """Normalize completed range-onset event lifecycles to one live cap."""
    _positive(effective_exposure, "effective_exposure")
    adapted: list[CohortOutcome] = []
    for payload_index, payload in enumerate(payloads):
        _validate_range_payload(payload, spec)
        continuous = _mapping(payload, "continuous")
        trials = tuple(
            trial
            for trial in _mapping_rows(continuous, "trials")
            if math.isclose(
                _number(trial, "effective_exposure"),
                effective_exposure,
                abs_tol=1e-12,
            )
        )
        if len(trials) != 1:
            raise ValueError("range artifact must contain one exact exposure trial")
        replay = _mapping(trials[0], "event_replay")
        if _text(replay, "status") != "complete" or replay.get("failure") is not None:
            raise ValueError("range event replay must be complete without failure")
        for trade_index, trade in enumerate(_mapping_rows(replay, "trades")):
            adapted.append(
                _adapt_range_event_trade(trade, spec, payload_index, trade_index)
            )
    if not adapted:
        raise ValueError(f"range artifacts contain no {spec.symbol} trades")
    return tuple(adapted)


def partition_cohort_outcomes(
    trades: tuple[CohortOutcome, ...],
    *,
    development_end_utc: str,
    holdout_start_utc: str,
    holdout_end_utc: str,
) -> dict[str, tuple[CohortOutcome, ...]]:
    """Partition by entry time using one common purge and final-block boundary."""
    development_end = _timestamp_ms(development_end_utc)
    holdout_start = _timestamp_ms(holdout_start_utc)
    holdout_end = _timestamp_ms(holdout_end_utc)
    if not development_end < holdout_start < holdout_end:
        raise ValueError("cohort partition boundaries must be strictly increasing")
    development = tuple(
        trade for trade in trades if trade.outcome.entry_time_ms < development_end
    )
    holdout = tuple(
        trade
        for trade in trades
        if holdout_start <= trade.outcome.entry_time_ms < holdout_end
    )
    selected = {trade.trade_id for trade in development + holdout}
    purged = tuple(trade for trade in trades if trade.trade_id not in selected)
    return {
        "development": development,
        "opened_final_60d": holdout,
        "purged": purged,
    }


def replay_cohort_outcomes(
    trades: tuple[CohortOutcome, ...],
    *,
    initial_equity_usd: float,
) -> dict[str, object]:
    """Replay one shared account and expose strategy, side, and month attribution."""
    if not trades:
        raise ValueError("cohort shared replay requires completed outcomes")
    outcomes = tuple(trade.outcome for trade in trades)
    metadata = {trade.trade_id: trade for trade in trades}
    if len(metadata) != len(trades):
        raise ValueError("cohort trade identities must be unique")
    caps = _source_equity_caps(outcomes)
    config = SharedTradeReplayConfig(initial_equity_usd, caps, True)
    replay = replay_shared_trade_outcomes(outcomes, config)
    return {
        "performance": _performance(replay.trades, initial_equity_usd),
        "capacity": {
            "maximum_concurrent_positions": replay.maximum_concurrent_positions,
            "peak_reserved_margin_usd": replay.peak_reserved_margin_usd,
        },
        "by_strategy": _grouped_performance(replay.trades, metadata, "strategy"),
        "by_strategy_side": _grouped_performance(
            replay.trades, metadata, "strategy_side"
        ),
        "by_exit_month": _monthly_performance(replay.trades),
        "trades": [trade.__dict__ for trade in replay.trades],
        "execution_authority": "none",
        "report_only": True,
    }


def _adapt_hulk_trade(
    trade: Mapping[str, object],
    spec: CohortTradeSpec,
    payload_index: int,
    trade_index: int,
) -> CohortOutcome:
    side = _side(_text(trade, "direction"))
    entry_time = _text(trade, "entry_time_utc")
    exit_time = _text(trade, "exit_time_utc")
    entry_notional = _number(trade, "entry_price") * _number(trade, "initial_quantity")
    _positive(entry_notional, "Hulk entry notional")
    normalized_net = _number(trade, "net_pnl_usd") / entry_notional
    trade_id = _trade_id(spec, entry_time, payload_index, trade_index)
    outcome = _shared_outcome(
        spec,
        trade_id,
        entry_time,
        exit_time,
        normalized_net * spec.notional_usd,
        _text(trade, "exit_reason"),
    )
    return CohortOutcome(spec.strategy_id, side, outcome)


def _adapt_breakout_trade(
    trade: HypeExitTrade,
    spec: CohortTradeSpec,
    index: int,
) -> CohortOutcome:
    trade_id = _trade_id(spec, trade.entry_time_utc, 0, index)
    net_pnl = trade.net_return_bps / 10_000.0 * spec.notional_usd
    outcome = _shared_outcome(
        spec,
        trade_id,
        trade.entry_time_utc,
        trade.exit_time_utc,
        net_pnl,
        trade.exit_reason,
    )
    return CohortOutcome(spec.strategy_id, trade.side, outcome)


def _adapt_range_event_trade(
    trade: Mapping[str, object],
    spec: CohortTradeSpec,
    payload_index: int,
    trade_index: int,
) -> CohortOutcome:
    side = _side(_text(trade, "direction"))
    entry_ms = _integer(trade, "entry_snapshot_time_ms")
    exit_ms = _integer(trade, "exit_snapshot_time_ms")
    entry_notional = _number(trade, "entry_price") * abs(_number(trade, "quantity"))
    _positive(entry_notional, "range entry notional")
    normalized_net = _number(trade, "net_pnl_usd") / entry_notional
    trade_id = (
        f"{spec.strategy_id}|{spec.symbol}|{entry_ms}|"
        f"{payload_index:02d}|{trade_index:05d}"
    )
    outcome = SharedTradeOutcome(
        trade_id=trade_id,
        symbol=spec.symbol.upper(),
        entry_time_ms=entry_ms,
        exit_time_ms=exit_ms,
        source_equity_usd=spec.reference_equity_usd,
        margin_fraction=spec.margin_fraction,
        entry_fee_usd=spec.notional_usd * spec.entry_fee_bps / 10_000.0,
        net_pnl_usd=normalized_net * spec.notional_usd,
        outcome=_text(trade, "exit_reason"),
    )
    return CohortOutcome(spec.strategy_id, side, outcome)


def _validate_range_payload(
    payload: Mapping[str, object], spec: CohortTradeSpec
) -> None:
    if _text(payload, "execution_authority") != "none":
        raise ValueError("range artifact must have no execution authority")
    if _text(payload, "model_authority") != "none":
        raise ValueError("range artifact must have no model authority")
    if _text(payload, "symbol").upper() != spec.symbol.upper():
        raise ValueError("range artifact symbol does not match live strategy")


def _shared_outcome(
    spec: CohortTradeSpec,
    trade_id: str,
    entry_time_utc: str,
    exit_time_utc: str,
    net_pnl_usd: float,
    outcome: str,
) -> SharedTradeOutcome:
    entry_fee = spec.notional_usd * spec.entry_fee_bps / 10_000.0
    entry_time_ms = _timestamp_ms(entry_time_utc)
    exit_time_ms = _causal_exit_ms(entry_time_ms, _timestamp_ms(exit_time_utc))
    return SharedTradeOutcome(
        trade_id=trade_id,
        symbol=spec.symbol.upper(),
        entry_time_ms=entry_time_ms,
        exit_time_ms=exit_time_ms,
        source_equity_usd=spec.reference_equity_usd,
        margin_fraction=spec.margin_fraction,
        entry_fee_usd=entry_fee,
        net_pnl_usd=net_pnl_usd,
        outcome=outcome,
    )


def _validate_hulk_payload(
    payload: Mapping[str, object], spec: CohortTradeSpec
) -> None:
    if _text(payload, "execution_authority") != "none":
        raise ValueError("Hulk artifact must have no execution authority")
    profile = _mapping(payload, "profile")
    if _text(profile, "name") != spec.strategy_id:
        raise ValueError("Hulk artifact profile identity does not match live strategy")


def _source_equity_caps(
    outcomes: tuple[SharedTradeOutcome, ...],
) -> dict[str, float]:
    caps: dict[str, float] = {}
    for outcome in outcomes:
        existing = caps.setdefault(outcome.symbol, outcome.source_equity_usd)
        if not math.isclose(existing, outcome.source_equity_usd, abs_tol=1e-9):
            raise ValueError(f"inconsistent source equity cap for {outcome.symbol}")
    return caps


def _performance(
    trades: tuple[ScaledSharedTrade, ...], initial_equity_usd: float
) -> dict[str, object]:
    values = [trade.net_pnl_usd for trade in trades]
    net = sum(values)
    equity = initial_equity_usd
    peak = equity
    maximum_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        maximum_drawdown = max(maximum_drawdown, (peak - equity) / peak * 100.0)
    return _summary(values) | {
        "initial_equity_usd": initial_equity_usd,
        "final_equity_usd": initial_equity_usd + net,
        "return_pct": net / initial_equity_usd * 100.0,
        "maximum_realized_drawdown_pct": maximum_drawdown,
    }


def _grouped_performance(
    trades: tuple[ScaledSharedTrade, ...],
    metadata: Mapping[str, CohortOutcome],
    grouping: str,
) -> dict[str, dict[str, object]]:
    values: dict[str, list[float]] = {}
    for trade in trades:
        source = metadata[trade.trade_id]
        key = source.strategy_id
        if grouping == "strategy_side":
            key = f"{key}|{source.side}"
        values.setdefault(key, []).append(trade.net_pnl_usd)
    return {key: _summary(group) for key, group in sorted(values.items())}


def _monthly_performance(
    trades: tuple[ScaledSharedTrade, ...],
) -> dict[str, dict[str, object]]:
    values: dict[str, list[float]] = {}
    for trade in trades:
        month = datetime.fromtimestamp(
            trade.exit_time_ms / 1_000.0,
            tz=UTC,
        ).strftime("%Y-%m")
        values.setdefault(month, []).append(trade.net_pnl_usd)
    return {month: _summary(group) for month, group in sorted(values.items())}


def _summary(values: list[float]) -> dict[str, object]:
    profits = [value for value in values if value > 0.0]
    losses = [-value for value in values if value < 0.0]
    net = sum(values)
    return {
        "completed_trades": len(values),
        "wins": len(profits),
        "losses": len(losses),
        "breakeven": len(values) - len(profits) - len(losses),
        "win_rate_pct": len(profits) / len(values) * 100.0 if values else None,
        "net_pnl_usd": net,
        "average_pnl_usd": net / len(values) if values else None,
        "profit_factor": sum(profits) / sum(losses) if losses else None,
    }


def _trade_id(spec: CohortTradeSpec, entry_time: str, group: int, index: int) -> str:
    stamp = _timestamp_ms(entry_time)
    return f"{spec.strategy_id}|{spec.symbol}|{stamp}|{group:02d}|{index:05d}"


def _timestamp_ms(value: str) -> int:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid aware cohort timestamp: {value}") from error
    if timestamp.tzinfo is None:
        raise ValueError(f"cohort timestamp must be timezone-aware: {value}")
    return int(timestamp.timestamp() * 1_000.0)


def _causal_exit_ms(entry_time_ms: int, exit_time_ms: int) -> int:
    if exit_time_ms < entry_time_ms:
        raise ValueError("cohort exit timestamp precedes entry timestamp")
    return entry_time_ms + 1 if exit_time_ms == entry_time_ms else exit_time_ms


def _mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _mapping_rows(
    payload: Mapping[str, object], key: str
) -> tuple[Mapping[str, object], ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{key} must be an object list")
    return tuple(value)


def _number(payload: Mapping[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    return number


def _integer(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a nonnegative integer")
    return value


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _side(value: str) -> str:
    side = value.lower()
    if side not in {"long", "short"}:
        raise ValueError(f"unsupported cohort trade side: {value}")
    return side


def _positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive")


def _nonnegative(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
