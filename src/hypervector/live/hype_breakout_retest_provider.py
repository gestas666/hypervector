"""HYPE breakout-direction retest provider with frozen v1 control ancestry."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.hype_breakout_cohort_provider import HypeBreakoutOnsetCollector
from hypervector.live.hype_breakout_retest_policy import (
    BreakoutRetestBar,
    BreakoutRetestResult,
    HypeBreakoutRetestPolicy,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import ReadinessMetric, SignalReadiness

HYPE_BREAKOUT_RETEST_STRATEGY = "hype_breakout_retest_bidirectional_v2"
_MINUTE = pd.Timedelta(minutes=1)
_SUPPORTED_SYMBOLS = frozenset({"BTC", "ETH", "SOL", "HYPE"})


class CanonicalBreakoutCollectorProtocol(Protocol):
    """Frozen v1 onset source consumed without routing its immediate intents."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch: ...


class HypeBreakoutRetestCollector:
    """Convert canonical onsets into breakout-side retest confirmations."""

    def __init__(
        self,
        *,
        canonical_collector: CanonicalBreakoutCollectorProtocol | None = None,
        window_bars: int = 3,
    ) -> None:
        """Bind the frozen source and an isolated per-symbol retest policy."""
        self._canonical = canonical_collector or HypeBreakoutOnsetCollector()
        self._policy = HypeBreakoutRetestPolicy(window_bars=window_bars)
        self._highest_requested_boundary: dict[str, int] = {}

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return only confirmed retests while preserving every setup transition."""
        normalized = _symbol(symbol)
        boundary = _boundary(after_decision_time_ms)
        seed_query = self._is_seed_query(normalized, boundary)
        canonical = self._canonical(
            bars,
            symbol=normalized,
            observed_at=observed_at,
            after_decision_time_ms=after_decision_time_ms,
        )
        if seed_query:
            evaluations = tuple(
                _seed_evaluation(value) for value in canonical.evaluations
            )
            return IntentBatch((), canonical.latest_decision_time_ms, evaluations)
        market = _market_frame(bars)
        evaluations = tuple(
            self._evaluation(normalized, market, value)
            for value in canonical.evaluations
        )
        intents = tuple(_intent(value) for value in evaluations if value.eligible)
        return IntentBatch(intents, canonical.latest_decision_time_ms, evaluations)

    def _is_seed_query(self, symbol: str, boundary: int) -> bool:
        prior = self._highest_requested_boundary.get(symbol)
        seed = prior is not None and boundary < prior
        self._highest_requested_boundary[symbol] = max(boundary, prior or 0)
        return seed

    def _evaluation(
        self,
        symbol: str,
        market: pd.DataFrame,
        source: ProviderEvaluation,
    ) -> ProviderEvaluation:
        bar, prior = _retest_bar(market, source)
        onset = _boolean_metric(source, "breakout_onset")
        boundary = _breakout_boundary(prior, bar.breakout_side) if onset else None
        result = self._policy.evaluate(
            symbol=symbol,
            bar=bar,
            breakout_onset=onset,
            breakout_boundary_price=boundary,
        )
        return _provider_evaluation(source, result, self._policy.window_bars)


def _provider_evaluation(
    source: ProviderEvaluation,
    result: BreakoutRetestResult,
    window_bars: int,
) -> ProviderEvaluation:
    readiness = _readiness(source, result, window_bars)
    action = f"enter_{result.side}" if result.eligible else "hold"
    return ProviderEvaluation(
        strategy_id=HYPE_BREAKOUT_RETEST_STRATEGY,
        symbol=source.symbol,
        decision_time_ms=source.decision_time_ms,
        reference_price=source.reference_price,
        decision_action=action,
        eligible=result.eligible,
        reason=result.reason,
        side=result.side,
        readiness=readiness,
        trigger="1m_breakout_retest" if result.eligible else "retest_setup",
        primary_regime=source.primary_regime,
        state_1m=source.state_1m,
        state_5m=source.state_5m,
        context_15m=source.context_15m,
        confidence=source.confidence,
    )


def _readiness(
    source: ProviderEvaluation,
    result: BreakoutRetestResult,
    window_bars: int,
) -> SignalReadiness:
    metrics: dict[str, ReadinessMetric] = dict(source.readiness.metrics)
    metrics.update(
        {
            "breakout_side_authority": "continuation_or_fade_reference",
            "entry_mode": result.mode,
            "entry_policy_state": result.state,
            "retest_age_bars": result.age_bars,
            "retest_boundary_price": result.boundary_price,
            "retest_window_bars": window_bars,
            "structural_direction_authority": "execution_for_fade",
        }
    )
    side = result.side
    indicators = (
        _breakout_indicator(result),
        f"RETEST {result.state.upper()} {result.age_bars or 0}/{window_bars}",
        _structural_indicator(source, result.mode),
        "V1 IMMEDIATE ENTRY [CONTROL ONLY]",
    )
    return SignalReadiness(
        side=side,
        conditions_met=_conditions_met(result),
        conditions_required=4,
        blockers=() if result.eligible else (result.reason,),
        indicators=indicators,
        metrics=metrics,
    )


def _conditions_met(result: BreakoutRetestResult) -> int:
    if result.state == "confirmed":
        return 4
    if result.state in {"armed", "pending"}:
        return 3
    if result.state in {"expired", "unavailable"}:
        return 2
    return 1


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    state = evaluation.readiness.metrics.get("entry_policy_state")
    breakout = evaluation.readiness.metrics.get("breakout_side")
    structural = evaluation.readiness.metrics.get("structural_direction")
    mode = evaluation.readiness.metrics.get("entry_mode")
    if state != "confirmed" or not _confirmed_side(
        evaluation.side, breakout, structural, mode
    ):
        raise RuntimeError("HYPE retest invariant failed: confirmed side is invalid")
    if evaluation.side not in {"long", "short"}:
        raise RuntimeError("HYPE retest invariant failed: confirmed side is missing")
    return StrategyIntent(
        strategy_id=HYPE_BREAKOUT_RETEST_STRATEGY,
        symbol=evaluation.symbol,
        side=evaluation.side,
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason=f"{evaluation.symbol.lower()}_breakout_retest:{evaluation.side}",
    )


def _seed_evaluation(source: ProviderEvaluation) -> ProviderEvaluation:
    breakout = source.readiness.metrics.get("breakout_side")
    structural = source.readiness.metrics.get("structural_direction")
    breakout_side = breakout if breakout in {"long", "short"} else None
    structural_side = structural if structural in {"long", "short"} else None
    aligned = breakout_side is not None and breakout_side == structural_side
    side = breakout_side if aligned else structural_side
    result = BreakoutRetestResult(
        state="idle",
        reason="historical_seed_observation",
        side=side,
        breakout_side=breakout_side,
        structural_side=structural_side,
        mode="continuation" if aligned else "fade" if side else None,
        eligible=False,
        boundary_price=None,
        age_bars=None,
    )
    return _provider_evaluation(source, result, 3)


def _retest_bar(
    market: pd.DataFrame,
    source: ProviderEvaluation,
) -> tuple[BreakoutRetestBar, pd.DataFrame]:
    timestamp = pd.Timestamp(source.decision_time_ms, unit="ms", tz="UTC") - _MINUTE
    if timestamp not in market.index:
        raise ValueError(f"HYPE retest bar is unavailable at {timestamp.isoformat()}")
    position = market.index.get_loc(timestamp)
    if not isinstance(position, int):
        raise ValueError("HYPE retest market timestamps must be unique")
    row = market.iloc[position]
    prior = market.iloc[max(0, position - 20) : position]
    breakout = source.readiness.metrics.get("breakout_side")
    structural = source.readiness.metrics.get("structural_direction")
    side = breakout if breakout in {"long", "short"} else None
    structural_side = structural if structural in {"long", "short"} else None
    bar = BreakoutRetestBar(
        decision_time_ms=source.decision_time_ms,
        open_price=float(row["open"]),
        high_price=float(row["high"]),
        low_price=float(row["low"]),
        close_price=float(row["close"]),
        state_5m=source.state_5m or "UNAVAILABLE",
        breakout_side=side,
        structural_side=structural_side,
    )
    return bar, prior


def _breakout_boundary(prior: pd.DataFrame, side: str | None) -> float | None:
    if side not in {"long", "short"} or len(prior) < 20:
        return None
    field = "high" if side == "long" else "low"
    reducer = prior[field].max if side == "long" else prior[field].min
    value = float(reducer())
    return value


def _market_frame(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close"}
    missing = sorted(required - set(bars.columns))
    if missing:
        raise ValueError(f"HYPE retest bars are missing columns: {missing}")
    timestamps = bars["timestamp"] if "timestamp" in bars.columns else bars.index
    index = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True))
    if index.has_duplicates:
        raise ValueError("HYPE retest market timestamps must be unique")
    output = bars.loc[:, sorted(required)].copy()
    output.index = index
    return output.sort_index()


def _boolean_metric(source: ProviderEvaluation, name: str) -> bool:
    value = source.readiness.metrics.get(name)
    if not isinstance(value, bool):
        raise ValueError(f"HYPE retest source metric must be boolean: {name}")
    return value


def _structural_indicator(source: ProviderEvaluation, mode: str | None) -> str:
    value = source.readiness.metrics.get("structural_direction")
    label = value.upper() if isinstance(value, str) else "N/A"
    authority = "FADE EXEC" if mode == "fade" else "CONTEXT"
    return f"SMA STRUCT {label} [{authority}]"


def _breakout_indicator(result: BreakoutRetestResult) -> str:
    breakout = (result.breakout_side or "N/A").upper()
    mode = (result.mode or "IDLE").upper()
    return f"5M BREAKOUT {breakout} [{mode}]"


def _confirmed_side(
    side: str | None,
    breakout: ReadinessMetric | None,
    structural: ReadinessMetric | None,
    mode: ReadinessMetric | None,
) -> bool:
    if side not in {"long", "short"}:
        return False
    if mode == "continuation":
        return side == breakout == structural
    if mode == "fade":
        return side == structural and breakout in {"long", "short"} and side != breakout
    return False


def _boundary(value: int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("after_decision_time_ms must be a nonnegative integer")
    return value


def _symbol(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("HYPE retest symbol must be non-empty text")
    normalized = value.strip().upper()
    if normalized not in _SUPPORTED_SYMBOLS:
        raise ValueError("HYPE retest provider supports BTC/ETH/SOL/HYPE only")
    return normalized
