"""Causal, annotation-only memory for rebuilt Hulk Smash signals."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import pandas as pd

from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayReport,
)

BrainAnnotation = Literal["insufficient_support", "positive", "neutral", "negative"]

_SIGNAL_COLUMNS = {
    "signal_time_utc",
    "symbol",
    "candidate",
    "side",
    "trigger",
    "evidence",
}
_OUTCOME_COLUMNS = _SIGNAL_COLUMNS | {"exit_time_utc", "net_return_r"}
_OUTCOME_ORDER = (
    "signal_time_utc",
    "exit_time_utc",
    "symbol",
    "candidate",
    "side",
    "trigger",
    "evidence",
    "net_return_r",
)


@dataclass(frozen=True)
class HulkBrainConfig:
    """Frozen causal pooling, decay, and uncertainty parameters."""

    half_life_days: float = 30.0
    neutral_prior_weight: float = 4.0
    return_clip_r: float = 3.0
    minimum_similarity: float = 0.35
    minimum_support: int = 5
    annotation_threshold: float = 0.05
    wilson_z: float = 1.96

    def __post_init__(self) -> None:
        """Reject parameters that could create incoherent annotations."""
        positive = {
            "half_life_days": self.half_life_days,
            "neutral_prior_weight": self.neutral_prior_weight,
            "return_clip_r": self.return_clip_r,
            "wilson_z": self.wilson_z,
        }
        if any(not math.isfinite(value) or value <= 0.0 for value in positive.values()):
            raise ValueError(
                f"Hulk Brain values must be positive and finite: {positive}"
            )
        if not 0.0 <= self.minimum_similarity <= 1.0:
            raise ValueError("Hulk Brain minimum_similarity must be within [0, 1]")
        if self.minimum_support < 1:
            raise ValueError("Hulk Brain minimum_support must be positive")
        if not 0.0 <= self.annotation_threshold <= 1.0:
            raise ValueError("Hulk Brain annotation_threshold must be within [0, 1]")


@dataclass(frozen=True)
class HulkBrainSizingConfig:
    """Bounded research-only mapping from Brain score to risk multiplier."""

    score_gain: float = 2.0
    minimum_risk_multiplier: float = 0.5
    maximum_risk_multiplier: float = 1.5

    def __post_init__(self) -> None:
        """Reject non-finite or inverted sizing bounds."""
        values = (
            self.score_gain,
            self.minimum_risk_multiplier,
            self.maximum_risk_multiplier,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("Hulk Brain sizing values must be positive and finite")
        if self.minimum_risk_multiplier > 1.0:
            raise ValueError("Hulk Brain minimum multiplier must not exceed neutral")
        if self.maximum_risk_multiplier < 1.0:
            raise ValueError("Hulk Brain maximum multiplier must include neutral")


@dataclass(frozen=True)
class _Context:
    symbol: str
    candidate: str
    archetype: str
    side: str
    trigger: str
    evidence: frozenset[str]


@dataclass(frozen=True)
class _Memory:
    context: _Context
    exit_time: pd.Timestamp
    net_return_r: float


@dataclass(frozen=True)
class _Pool:
    raw_support: int
    exact_support: int
    effective_support: float
    score: float
    mean_return_r: float
    wins: int


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Return the two-sided Wilson interval for a Bernoulli proportion."""
    if total < 0 or successes < 0 or successes > total:
        raise ValueError("Wilson counts must satisfy 0 <= successes <= total")
    if not math.isfinite(z) or z <= 0.0:
        raise ValueError("Wilson z must be positive and finite")
    if total == 0:
        return 0.0, 1.0
    probability = successes / total
    z_squared = z * z
    denominator = 1.0 + z_squared / total
    centre = probability + z_squared / (2.0 * total)
    variance = probability * (1.0 - probability) + z_squared / (4.0 * total)
    spread = z * math.sqrt(variance / total)
    return max(0.0, (centre - spread) / denominator), min(
        1.0, (centre + spread) / denominator
    )


def annotate_hulk_signals(
    signals: pd.DataFrame,
    outcomes: pd.DataFrame,
    config: HulkBrainConfig | None = None,
) -> pd.DataFrame:
    """Append point-in-time Brain telemetry without changing signal authority."""
    cfg = config or HulkBrainConfig()
    signal_times = _validated_times(signals, _SIGNAL_COLUMNS, "signal_time_utc")
    outcome_times = _validated_times(outcomes, _OUTCOME_COLUMNS, "exit_time_utc")
    memories = _memories(outcomes, outcome_times, cfg)
    annotations: list[dict[str, object]] = []
    for position, (_, row) in enumerate(signals.iterrows()):
        context = _context(row)
        pool = _pool(memories, context, signal_times.iloc[position], cfg)
        annotations.append(_annotation(pool, cfg))
    result = signals.copy(deep=True)
    for column in _annotation_columns():
        result[column] = [row[column] for row in annotations]
    return result


def apply_hulk_brain_risk_scaling(
    annotated: pd.DataFrame,
    config: HulkBrainSizingConfig | None = None,
) -> pd.DataFrame:
    """Attach bounded continuous risk multipliers without filtering signals."""
    required = {"brain_score", "brain_supported", "eligible"}
    missing = sorted(required.difference(annotated.columns))
    if missing:
        raise ValueError(f"Hulk Brain sizing input missing columns: {missing}")
    cfg = config or HulkBrainSizingConfig()
    multipliers: list[float] = []
    for score, supported in zip(
        annotated["brain_score"],
        annotated["brain_supported"],
        strict=True,
    ):
        value = float(score)
        if not math.isfinite(value):
            raise ValueError("Hulk Brain score must be finite for sizing")
        raw = 1.0 + cfg.score_gain * value if bool(supported) else 1.0
        multipliers.append(
            max(cfg.minimum_risk_multiplier, min(cfg.maximum_risk_multiplier, raw))
        )
    result = annotated.copy(deep=True)
    result["risk_multiplier"] = multipliers
    result["brain_sizing_execution_authority"] = "none"
    return result


def brain_outcomes_from_replay(
    report: MarketCipherReplayReport,
    signals: pd.DataFrame,
) -> pd.DataFrame:
    """Join completed replay trades to their causal signal contexts."""
    signal_times = _validated_times(signals, _SIGNAL_COLUMNS, "signal_time_utc")
    lookup = _signal_lookup(signals, signal_times)
    rows: list[dict[str, object]] = []
    for trade in report.trades:
        key = _identity(
            pd.Timestamp(trade.signal_time_utc),
            trade.symbol,
            trade.candidate,
            trade.direction,
        )
        if key not in lookup:
            raise ValueError(f"Hulk Brain replay trade has no signal context: {key}")
        signal = lookup[key]
        rows.append(
            _outcome_row(
                trade.exit_time_utc,
                trade.net_pnl_usd,
                trade.risk_budget_usd,
                signal,
            )
        )
    return pd.DataFrame(rows, columns=list(_OUTCOME_ORDER))


def _signal_lookup(
    signals: pd.DataFrame, times: pd.Series
) -> dict[tuple[pd.Timestamp, str, str, str], pd.Series]:
    lookup: dict[tuple[pd.Timestamp, str, str, str], pd.Series] = {}
    for position, (_, row) in enumerate(signals.iterrows()):
        context = _context(row)
        key = _identity(
            times.iloc[position], context.symbol, context.candidate, context.side
        )
        if key in lookup:
            raise ValueError(f"Hulk Brain ambiguous signal identity: {key}")
        lookup[key] = row
    return lookup


def _identity(
    timestamp: pd.Timestamp, symbol: str, candidate: str, side: str
) -> tuple[pd.Timestamp, str, str, str]:
    value = pd.Timestamp(timestamp)
    if value.tz is None:
        raise ValueError("Hulk Brain identity timestamp must be timezone-aware")
    return value.tz_convert("UTC"), symbol, candidate, side


def _outcome_row(
    exit_time: str,
    net_pnl_usd: float,
    risk_budget: float,
    signal: pd.Series,
) -> dict[str, object]:
    if not math.isfinite(risk_budget) or risk_budget <= 0.0:
        raise ValueError("Hulk Brain replay risk budget must be positive")
    return {
        "signal_time_utc": pd.Timestamp(signal["signal_time_utc"]),
        "exit_time_utc": pd.Timestamp(exit_time),
        "symbol": str(signal["symbol"]),
        "candidate": str(signal["candidate"]),
        "side": str(signal["side"]),
        "trigger": str(signal["trigger"]),
        "evidence": signal["evidence"],
        "net_return_r": float(net_pnl_usd) / risk_budget,
    }


def _validated_times(
    frame: pd.DataFrame, required: set[str], time_column: str
) -> pd.Series:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Hulk Brain input missing columns: {missing}")
    try:
        values = pd.to_datetime(frame[time_column], utc=True, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Hulk Brain invalid {time_column}") from exc
    if values.isna().any():
        raise ValueError(f"Hulk Brain {time_column} contains missing timestamps")
    return values


def _memories(
    outcomes: pd.DataFrame,
    exit_times: pd.Series,
    config: HulkBrainConfig,
) -> tuple[_Memory, ...]:
    memories: list[_Memory] = []
    for position, (_, row) in enumerate(outcomes.iterrows()):
        value = float(row["net_return_r"])
        if not math.isfinite(value):
            raise ValueError("Hulk Brain net_return_r must be finite")
        clipped = max(-config.return_clip_r, min(config.return_clip_r, value))
        memories.append(_Memory(_context(row), exit_times.iloc[position], clipped))
    return tuple(memories)


def _context(row: pd.Series) -> _Context:
    side = str(row["side"])
    if side not in {"long", "short"}:
        raise ValueError(f"Hulk Brain side must be long or short, got {side!r}")
    candidate = _nonempty(row["candidate"], "candidate")
    evidence = _evidence(row["evidence"])
    return _Context(
        symbol=_nonempty(row["symbol"], "symbol"),
        candidate=candidate,
        archetype=_archetype(candidate),
        side=side,
        trigger=_nonempty(row["trigger"], "trigger"),
        evidence=evidence,
    )


def _nonempty(value: object, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"Hulk Brain {label} must be non-empty")
    return text


def _evidence(value: object) -> frozenset[str]:
    if not isinstance(value, (tuple, list, set, frozenset)):
        raise ValueError("Hulk Brain evidence must be a sequence of names")
    evidence = frozenset(str(item).strip() for item in value)
    if not evidence or "" in evidence:
        raise ValueError("Hulk Brain evidence must contain non-empty names")
    return evidence


def _archetype(candidate: str) -> str:
    for name in ("continuation", "expansion", "reversal"):
        if name in candidate:
            return name
    return candidate


def _pool(
    memories: tuple[_Memory, ...],
    context: _Context,
    decision_time: pd.Timestamp,
    config: HulkBrainConfig,
) -> _Pool:
    weighted_returns: list[tuple[float, float]] = []
    wins = 0
    exact_support = 0
    for memory in memories:
        if memory.exit_time >= decision_time:
            continue
        similarity = _similarity(context, memory.context)
        if similarity < config.minimum_similarity:
            continue
        weight = similarity * _decay(memory.exit_time, decision_time, config)
        weighted_returns.append((weight, memory.net_return_r))
        wins += memory.net_return_r > 0.0
        exact_support += memory.context == context
    return _summarize(weighted_returns, wins, exact_support, config)


def _similarity(left: _Context, right: _Context) -> float:
    if left.side != right.side:
        return 0.0
    similarity = 0.15
    similarity += 0.25 if left.archetype == right.archetype else 0.0
    similarity += 0.15 if left.trigger == right.trigger else 0.0
    similarity += 0.10 if left.symbol == right.symbol else 0.0
    union = left.evidence | right.evidence
    similarity += 0.35 * len(left.evidence & right.evidence) / len(union)
    return similarity


def _decay(
    exit_time: pd.Timestamp,
    decision_time: pd.Timestamp,
    config: HulkBrainConfig,
) -> float:
    age_days = (decision_time - exit_time).total_seconds() / 86_400.0
    return 0.5 ** (age_days / config.half_life_days)


def _summarize(
    weighted_returns: list[tuple[float, float]],
    wins: int,
    exact_support: int,
    config: HulkBrainConfig,
) -> _Pool:
    effective_support = sum(weight for weight, _ in weighted_returns)
    weighted_total = sum(weight * value for weight, value in weighted_returns)
    denominator = config.neutral_prior_weight + effective_support
    mean_return = weighted_total / denominator
    score = mean_return / config.return_clip_r
    return _Pool(
        raw_support=len(weighted_returns),
        exact_support=exact_support,
        effective_support=effective_support,
        score=max(-1.0, min(1.0, score)),
        mean_return_r=mean_return,
        wins=wins,
    )


def _annotation(pool: _Pool, config: HulkBrainConfig) -> dict[str, object]:
    lower, upper = wilson_interval(pool.wins, pool.raw_support, config.wilson_z)
    supported = pool.raw_support >= config.minimum_support
    label: BrainAnnotation = "insufficient_support"
    if supported and pool.score > config.annotation_threshold:
        label = "positive"
    elif supported and pool.score < -config.annotation_threshold:
        label = "negative"
    elif supported:
        label = "neutral"
    return {
        "brain_score": pool.score,
        "brain_mean_return_r": pool.mean_return_r,
        "brain_raw_support": pool.raw_support,
        "brain_exact_support": pool.exact_support,
        "brain_effective_support": pool.effective_support,
        "brain_wilson_lower": lower,
        "brain_wilson_upper": upper,
        "brain_supported": supported,
        "brain_annotation": label,
        "brain_execution_authority": "none",
    }


def _annotation_columns() -> tuple[str, ...]:
    return (
        "brain_score",
        "brain_mean_return_r",
        "brain_raw_support",
        "brain_exact_support",
        "brain_effective_support",
        "brain_wilson_lower",
        "brain_wilson_upper",
        "brain_supported",
        "brain_annotation",
        "brain_execution_authority",
    )
