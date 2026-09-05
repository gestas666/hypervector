"""Causal, report-only ETH exit after persistent component opposition."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from hypervector.regime.component_telemetry import build_regime_component_frame
from hypervector.research.cohort_regime_assessment import build_regime_assessment
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
    HypeExitTrade,
    HypeSide,
)
from hypervector.research.hype_breakout_exit_replay import replay_hype_breakout_exits
from hypervector.research.hype_breakout_profit_research import (
    freeze_hype_entry_cohort,
)

_COMPONENT_COLUMNS = (
    "ema_21_55_direction",
    "sma_100_200_direction",
    "cipher_a_direction",
    "harsi_direction",
    "mtf_5m_bias",
    "mtf_15m_bias",
    "trend_slope_bps",
)
_COMPONENT_WEIGHT = 9.0


@dataclass(frozen=True)
class EthComponentDecaySpec:
    """One frozen component-decay hypothesis with no execution authority."""

    activation_mfe_bps: float = 300.0
    alignment_threshold: float = -0.5
    persistence_completed_bars: int = 5
    stop_bps: float = 60.0
    maximum_hold_minutes: int = 720
    fee_bps_per_side: float = 4.5
    slippage_bps_per_side: float = 2.0

    def __post_init__(self) -> None:
        """Reject malformed or economically unsupported candidate settings."""
        _positive(self.activation_mfe_bps, "activation MFE")
        if not -1.0 <= self.alignment_threshold < 0.0:
            raise ValueError("component alignment threshold must be within [-1, 0)")
        if self.persistence_completed_bars < 1:
            raise ValueError("component persistence must be positive")
        _positive(self.stop_bps, "stop bps")
        if self.maximum_hold_minutes < 1:
            raise ValueError("maximum hold must be positive")
        _nonnegative(self.fee_bps_per_side, "fee bps")
        _nonnegative(self.slippage_bps_per_side, "slippage bps")


@dataclass(frozen=True)
class EthComponentDecayTrigger:
    """One completed-bar decision that can schedule a following-open exit."""

    decision_time_utc: str
    side: HypeSide
    maximum_favorable_excursion_bps: float
    component_alignment_score: float
    persistence_completed_bars: int


@dataclass(frozen=True)
class EthComponentDecayReplay:
    """Fixed-entry candidate replay plus technical path diagnostics."""

    report: HypeExitReplayReport
    triggers: tuple[EthComponentDecayTrigger, ...]
    unavailable_component_rows: tuple[str, ...]
    technical_status: str
    execution_authority: str = "none"


def replay_eth_component_decay_exit(
    market: pd.DataFrame,
    control_trades: tuple[HypeExitTrade, ...],
    spec: EthComponentDecaySpec | None = None,
) -> EthComponentDecayReplay:
    """Replay the frozen ETH entries with a causal component-decay close."""
    candidate = spec or EthComponentDecaySpec()
    fixed_market = freeze_hype_entry_cohort(market, control_trades)
    components = build_regime_component_frame(market)
    _validate_component_frame(market, components)
    triggers, unavailable = _lifecycle_triggers(
        market,
        components,
        control_trades,
        candidate,
    )
    replay_market = fixed_market.copy()
    replay_market["structural_direction"] = "neutral"
    if not unavailable:
        _apply_trigger_directions(replay_market, triggers)
    report = replay_hype_breakout_exits(
        replay_market,
        HypeExitPolicy("eth_r5_component_decay_p5", exit_on_reversal=True),
        _replay_config(candidate),
    )
    _require_entry_parity(control_trades, report.trades)
    return EthComponentDecayReplay(
        report=report,
        triggers=() if unavailable else triggers,
        unavailable_component_rows=unavailable,
        technical_status=(
            "resolved" if not unavailable else "unresolved_component_path"
        ),
    )


def _lifecycle_triggers(
    market: pd.DataFrame,
    components: pd.DataFrame,
    trades: tuple[HypeExitTrade, ...],
    spec: EthComponentDecaySpec,
) -> tuple[tuple[EthComponentDecayTrigger, ...], tuple[str, ...]]:
    triggers: list[EthComponentDecayTrigger] = []
    unavailable: set[pd.Timestamp] = set()
    for trade in trades:
        trigger, missing = _trade_trigger(market, components, trade, spec)
        unavailable.update(missing)
        if trigger is not None:
            triggers.append(trigger)
    missing_rows = tuple(timestamp.isoformat() for timestamp in sorted(unavailable))
    return tuple(triggers), missing_rows


def _trade_trigger(
    market: pd.DataFrame,
    components: pd.DataFrame,
    trade: HypeExitTrade,
    spec: EthComponentDecaySpec,
) -> tuple[EthComponentDecayTrigger | None, tuple[pd.Timestamp, ...]]:
    entry = pd.Timestamp(trade.entry_time_utc)
    end = pd.Timestamp(trade.exit_time_utc)
    if end < entry:
        raise ValueError("ETH component-decay lifecycle exits before entry")
    if end == entry and trade.exit_reason == "protective_stop":
        return None, ()
    path = market.loc[(market.index >= entry) & (market.index < end)]
    if path.empty:
        raise ValueError("ETH component-decay lifecycle path is empty")
    maximum_favorable = 0.0
    streak = 0
    unavailable: list[pd.Timestamp] = []
    for timestamp, row in path.iterrows():
        maximum_favorable = max(maximum_favorable, _favorable_bps(row, trade))
        score = _component_score(components.loc[timestamp], trade.side)
        if score is None:
            unavailable.append(timestamp)
            streak = 0
            continue
        active = maximum_favorable >= spec.activation_mfe_bps
        streak = streak + 1 if active and score <= spec.alignment_threshold else 0
        if streak >= spec.persistence_completed_bars:
            return _trigger(timestamp, trade, maximum_favorable, score, spec), tuple(
                unavailable
            )
    return None, tuple(unavailable)


def _component_score(row: pd.Series, side: HypeSide) -> float | None:
    metrics = {name: _finite_or_none(row[name]) for name in _COMPONENT_COLUMNS}
    context = {
        "signal_provider": {"status": "observed", "primary_regime": "RANGE"},
        "canonical_regime": {
            "status": "observed",
            "primary_regime": "RANGE",
            "readiness": {"metrics": metrics},
        },
    }
    assessment = build_regime_assessment(side, context)
    if assessment["component_weight_observed"] != _COMPONENT_WEIGHT:
        return None
    value = assessment["component_alignment_score"]
    return float(value) if value is not None else None


def _favorable_bps(row: pd.Series, trade: HypeExitTrade) -> float:
    if trade.side == "long":
        return max((float(row["high"]) / trade.entry_price - 1.0) * 10_000.0, 0.0)
    return max((1.0 - float(row["low"]) / trade.entry_price) * 10_000.0, 0.0)


def _trigger(
    timestamp: pd.Timestamp,
    trade: HypeExitTrade,
    maximum_favorable: float,
    score: float,
    spec: EthComponentDecaySpec,
) -> EthComponentDecayTrigger:
    return EthComponentDecayTrigger(
        decision_time_utc=timestamp.isoformat(),
        side=trade.side,
        maximum_favorable_excursion_bps=maximum_favorable,
        component_alignment_score=score,
        persistence_completed_bars=spec.persistence_completed_bars,
    )


def _apply_trigger_directions(
    market: pd.DataFrame,
    triggers: tuple[EthComponentDecayTrigger, ...],
) -> None:
    for trigger in triggers:
        timestamp = pd.Timestamp(trigger.decision_time_utc)
        market.at[timestamp, "structural_direction"] = (
            "short" if trigger.side == "long" else "long"
        )


def _replay_config(spec: EthComponentDecaySpec) -> HypeExitReplayConfig:
    return HypeExitReplayConfig(
        stop_bps=spec.stop_bps,
        maximum_hold_minutes=spec.maximum_hold_minutes,
        fee_bps_per_side=spec.fee_bps_per_side,
        slippage_bps_per_side=spec.slippage_bps_per_side,
    )


def _require_entry_parity(
    control: tuple[HypeExitTrade, ...],
    candidate: tuple[HypeExitTrade, ...],
) -> None:
    control_entries = [_entry_identity(trade) for trade in control]
    candidate_entries = [_entry_identity(trade) for trade in candidate]
    if control_entries != candidate_entries:
        raise ValueError("ETH component-decay replay changed the fixed entry cohort")


def _entry_identity(trade: HypeExitTrade) -> tuple[str, str, HypeSide]:
    return trade.signal_time_utc, trade.entry_time_utc, trade.side


def _validate_component_frame(
    market: pd.DataFrame,
    components: pd.DataFrame,
) -> None:
    if not components.index.equals(market.index):
        raise ValueError("ETH component evidence must share the market index")
    missing = sorted(set(_COMPONENT_COLUMNS).difference(components.columns))
    if missing:
        raise ValueError(f"ETH component evidence missing columns: {missing}")


def _finite_or_none(value: object) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def _positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"ETH component-decay {label} must be finite and positive")


def _nonnegative(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
        raise ValueError(f"ETH component-decay {label} must be finite and nonnegative")
