"""Causal completed-bar decisions for the rebuilt Hulk Smash canary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math
import pandas as pd
from typing import Protocol

from hypervector.research.backtest_lab_cipher_adapter import (
    compute_market_cipher_signal_components,
)
from hypervector.research.cipher_suite_timeframes import resample_cipher_bars
from hypervector.research.hulk_smash_quality import build_hulk_quality_frame
from hypervector.research.hulk_smash_rebuilt_signals import (
    RebuiltHulkConfig,
    evaluate_rebuilt_hulk_signals,
)
from hypervector.live.hulk_smash_live_readiness import (
    HulkEntryReadinessFacts,
    build_hulk_readiness,
)
from hypervector.live.provider_readiness import SignalReadiness

ComponentBuilder = Callable[..., pd.DataFrame]
QualityBuilder = Callable[..., pd.DataFrame]
SignalBuilder = Callable[..., pd.DataFrame]

_SOURCE_BAR = pd.Timedelta(minutes=5)
_SIGNAL_BAR = pd.Timedelta(minutes=30)


class HulkDecisionConfigProtocol(Protocol):
    """Minimum signal parameters required by the completed-bar builder."""

    backtest_lab_root: object
    supertrend_period: int
    supertrend_multiplier: float
    adx_period: int
    squeeze_period: int
    minimum_score: int
    pivot_bars: int
    adx_usable: float
    adx_trending: float


@dataclass(frozen=True)
class HulkSmashLiveDecision:
    """One point-in-time 30-minute Hulk score and its execution disposition."""

    decision_time_ms: int
    bar_open_at: pd.Timestamp
    reference_price: float
    open_price: float
    high_price: float
    low_price: float
    volume: float
    candidate: str
    score: int
    minimum_score: int
    trigger: str
    evidence: tuple[str, ...]
    stop_anchor: float | None
    entry_eligible: bool
    reason: str
    signal_side: str | None = "short"
    readiness: SignalReadiness | None = None

    def __post_init__(self) -> None:
        """Reject malformed timestamps, prices, scores, and dispositions."""
        if self.bar_open_at.tzinfo is None:
            raise ValueError("Hulk decision bar time must be timezone-aware")
        if self.decision_time_ms < 0:
            raise ValueError("Hulk decision time must be nonnegative")
        prices = (
            self.reference_price,
            self.open_price,
            self.high_price,
            self.low_price,
        )
        if not all(math.isfinite(value) and value > 0.0 for value in prices):
            raise ValueError("Hulk decision prices must be positive and finite")
        if not math.isfinite(self.volume) or self.volume < 0.0:
            raise ValueError("Hulk decision volume must be nonnegative and finite")
        if self.score < 0 or self.minimum_score < 1:
            raise ValueError("Hulk decision scores are invalid")
        if self.entry_eligible and self.stop_anchor is None:
            raise ValueError("eligible Hulk decisions require a structural stop anchor")
        if self.entry_eligible and self.signal_side not in {"long", "short"}:
            raise ValueError("eligible Hulk decisions require a long or short side")
        if self.signal_side is not None and self.signal_side not in {"long", "short"}:
            raise ValueError("Hulk signal side must be long, short, or None")
        if not self.reason.strip():
            raise ValueError("Hulk decision reason must be non-empty")

    @property
    def decision_action(self) -> str:
        """Return the backend action label without granting hidden authority."""
        return (
            f"enter_{self.signal_side}"
            if self.entry_eligible and self.signal_side is not None
            else "hold"
        )

    @property
    def primary_regime(self) -> str:
        """Explicitly report that Hulk does not classify market regimes."""
        return "NOT_CLASSIFIED"

    def as_payload(self) -> dict[str, object]:
        """Return a JSON-safe TUI and ledger decision projection."""
        payload: dict[str, object] = {
            "feed_ts": self.available_at.isoformat(),
            "label_time_utc": self.bar_open_at.isoformat(),
            "available_at_utc": self.available_at.isoformat(),
            "candle_timeframe": "30m",
            "market_data_source": "hyperliquid_candle_rest_5m_resampled",
            "reference_price": self.reference_price,
            "open": self.open_price,
            "high": self.high_price,
            "low": self.low_price,
            "close": self.reference_price,
            "volume": self.volume,
            "primary_regime": self.primary_regime,
            "state_1m": "NOT_CLASSIFIED",
            "state_5m": "NOT_CLASSIFIED",
            "context_15m": "NOT_CLASSIFIED",
            "hulk_candidate": self.candidate,
            "hulk_score": self.score,
            "hulk_minimum_score": self.minimum_score,
            "hulk_trigger": self.trigger,
            "hulk_evidence": list(self.evidence),
            "hulk_stop_anchor": self.stop_anchor,
            "entry_direction": self.signal_side if self.entry_eligible else None,
            "short_entry": self.entry_eligible and self.signal_side == "short",
            "long_entry": self.entry_eligible and self.signal_side == "long",
            "entry_allowed": self.entry_eligible,
            "regime_admitted": False,
            "decision_action": self.decision_action,
            "regime_reason": self.reason,
        }
        if self.readiness is not None:
            payload["readiness"] = self.readiness.as_payload()
        return payload

    @property
    def available_at(self) -> pd.Timestamp:
        """Return the first instant at which the completed bar is usable."""
        return self.bar_open_at + _SIGNAL_BAR


def build_completed_hulk_decisions(
    raw_bars: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
    config: HulkDecisionConfigProtocol,
    after_decision_time_ms: int | None = None,
    allowed_sides: frozenset[str] = frozenset({"short"}),
    component_builder: ComponentBuilder = compute_market_cipher_signal_components,
    quality_builder: QualityBuilder = build_hulk_quality_frame,
    signal_builder: SignalBuilder = evaluate_rebuilt_hulk_signals,
) -> tuple[HulkSmashLiveDecision, ...]:
    """Return unseen completed 30-minute decisions in chronological order."""
    if not allowed_sides or not allowed_sides.issubset({"long", "short"}):
        raise ValueError("Hulk allowed_sides must contain long and/or short")
    observed = _aware_utc(observed_at)
    strategy_bars = _completed_strategy_bars(raw_bars, observed)
    indexed = strategy_bars.set_index("bar_open_at")
    components = component_builder(
        strategy_bars,
        config.backtest_lab_root,
        bar_minutes=30,
    )
    quality = quality_builder(
        indexed,
        supertrend_period=config.supertrend_period,
        supertrend_multiplier=config.supertrend_multiplier,
        adx_period=config.adx_period,
        squeeze_period=config.squeeze_period,
    )
    signal_config = RebuiltHulkConfig(
        minimum_score=config.minimum_score,
        pivot_bars=config.pivot_bars,
        adx_usable=config.adx_usable,
        adx_trending=config.adx_trending,
    )
    signals = signal_builder(indexed, components, quality, signal_config)
    by_time = _signals_by_time(signals)
    return _decisions(
        indexed,
        by_time,
        components,
        quality,
        config,
        after_decision_time_ms,
        allowed_sides,
    )


def _completed_strategy_bars(
    raw_bars: pd.DataFrame, observed_at: pd.Timestamp
) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(raw_bars.columns))
    if missing:
        raise ValueError(f"Hulk source bars missing columns: {missing}")
    source = raw_bars.loc[:, sorted(required)].copy()
    times = pd.DatetimeIndex(source.pop("timestamp"))
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Hulk source timestamps must be aware, unique, and ordered")
    source.insert(0, "bar_open_at", times.tz_convert("UTC"))
    source = source.loc[source["bar_open_at"] + _SOURCE_BAR <= observed_at]
    if source.empty:
        raise ValueError("Hulk source has no completed 5m bars")
    strategy = resample_cipher_bars(source, bar_minutes=30)
    if strategy.empty:
        raise ValueError("Hulk source has no complete 30m buckets")
    return strategy


def _signals_by_time(signals: pd.DataFrame) -> dict[pd.Timestamp, pd.Series]:
    if signals.empty:
        return {}
    required = {
        "candidate",
        "signal_time_utc",
        "side",
        "score",
        "eligible",
        "reason",
        "trigger",
        "evidence",
        "stop_anchor",
    }
    missing = sorted(required.difference(signals.columns))
    if missing:
        raise ValueError(f"Hulk signal output missing columns: {missing}")
    times = pd.DatetimeIndex(signals["signal_time_utc"])
    if times.tz is None or times.has_duplicates:
        raise ValueError("Hulk signal times must be aware and unique")
    return {
        pd.Timestamp(timestamp).tz_convert("UTC"): row
        for timestamp, (_, row) in zip(times, signals.iterrows(), strict=True)
    }


def _decisions(
    bars: pd.DataFrame,
    signals: Mapping[pd.Timestamp, pd.Series],
    components: pd.DataFrame,
    quality: pd.DataFrame,
    config: HulkDecisionConfigProtocol,
    after_ms: int | None,
    allowed_sides: frozenset[str],
) -> tuple[HulkSmashLiveDecision, ...]:
    boundary = _optional_boundary(after_ms)
    output: list[HulkSmashLiveDecision] = []
    for timestamp, bar in bars.iterrows():
        decision_ms = int((pd.Timestamp(timestamp) + _SIGNAL_BAR).timestamp() * 1_000)
        if boundary is not None and decision_ms <= boundary:
            continue
        output.append(
            _decision(
                pd.Timestamp(timestamp),
                bar,
                signals.get(timestamp),
                _row_at(components, timestamp),
                _row_at(quality, timestamp),
                config,
                allowed_sides,
            )
        )
    return tuple(output)


def _decision(
    timestamp: pd.Timestamp,
    bar: pd.Series,
    signal: pd.Series | None,
    components: pd.Series | None,
    quality: pd.Series | None,
    config: HulkDecisionConfigProtocol,
    allowed_sides: frozenset[str],
) -> HulkSmashLiveDecision:
    disposition = _signal_disposition(signal, allowed_sides)
    return HulkSmashLiveDecision(
        decision_time_ms=int((timestamp + _SIGNAL_BAR).timestamp() * 1_000),
        bar_open_at=timestamp,
        reference_price=float(bar["close"]),
        open_price=float(bar["open"]),
        high_price=float(bar["high"]),
        low_price=float(bar["low"]),
        volume=float(bar["volume"]),
        candidate=_signal_text(signal, "candidate", "none"),
        score=_signal_integer(signal, "score", 0),
        minimum_score=config.minimum_score,
        trigger=_signal_text(signal, "trigger", "none"),
        evidence=_signal_evidence(signal),
        stop_anchor=_signal_number(signal, "stop_anchor"),
        entry_eligible=disposition == "eligible",
        reason=disposition,
        signal_side=_signal_side(signal),
        readiness=build_hulk_readiness(
            components,
            quality,
            adx_usable=config.adx_usable,
            entry=_entry_readiness_facts(
                signal,
                config.minimum_score,
                allowed_sides,
            ),
        ),
    )


def _entry_readiness_facts(
    signal: pd.Series | None,
    minimum_score: int,
    allowed_sides: frozenset[str],
) -> HulkEntryReadinessFacts:
    return HulkEntryReadinessFacts(
        candidate=_signal_text(signal, "candidate", "none"),
        evidence=_signal_evidence(signal),
        score=_signal_integer(signal, "score", 0),
        minimum_score=minimum_score,
        signal_eligible=signal is not None and bool(signal["eligible"]),
        side=_signal_side(signal),
        allowed_sides=allowed_sides,
    )


def _row_at(frame: pd.DataFrame, timestamp: object) -> pd.Series | None:
    return frame.loc[timestamp] if timestamp in frame.index else None


def _signal_disposition(
    signal: pd.Series | None,
    allowed_sides: frozenset[str],
) -> str:
    if signal is None:
        return "no_trigger"
    if str(signal["candidate"]) != "hulk_rebuilt_expansion_v1":
        return "expansion_trigger_not_present"
    if "adx_usable" not in _signal_evidence(signal):
        return "moderate_adx_not_present"
    if not bool(signal["eligible"]):
        return str(signal["reason"])
    side = str(signal["side"])
    if side not in allowed_sides:
        return f"side_not_{'_or_'.join(sorted(allowed_sides))}"
    return "eligible"


def _signal_side(signal: pd.Series | None) -> str | None:
    if signal is None:
        return None
    side = str(signal["side"])
    return side if side in {"long", "short"} else None


def _signal_text(signal: pd.Series | None, key: str, default: str) -> str:
    if signal is None:
        return default
    value = signal[key]
    return str(value) if str(value).strip() else default


def _signal_integer(signal: pd.Series | None, key: str, default: int) -> int:
    if signal is None:
        return default
    return int(signal[key])


def _signal_number(signal: pd.Series | None, key: str) -> float | None:
    if signal is None or pd.isna(signal[key]):
        return None
    value = float(signal[key])
    return value if math.isfinite(value) else None


def _signal_evidence(signal: pd.Series | None) -> tuple[str, ...]:
    if signal is None:
        return ()
    values = signal["evidence"]
    if not isinstance(values, (tuple, list)):
        raise ValueError("Hulk signal evidence must be a tuple or list")
    return tuple(str(value) for value in values)


def _optional_boundary(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("after_decision_time_ms must be a nonnegative integer")
    return value


def _aware_utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("Hulk observed_at must be timezone-aware")
    return timestamp.tz_convert("UTC")
