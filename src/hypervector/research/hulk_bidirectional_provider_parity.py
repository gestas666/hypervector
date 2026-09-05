"""Report-only research/live parity for the bidirectional Hulk route."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import pandas as pd

from hypervector.live.hulk_smash_live_decisions import (
    ComponentBuilder,
    HulkSmashLiveDecision,
    QualityBuilder,
    build_completed_hulk_decisions,
)
from hypervector.live.multi_asset_route_contract_validation import (
    HULK_BIDIRECTIONAL_STRATEGY,
)
from hypervector.research.backtest_lab_cipher_adapter import (
    compute_market_cipher_signal_components,
)
from hypervector.research.cipher_suite_timeframes import resample_cipher_bars
from hypervector.research.hulk_smash_quality import build_hulk_quality_frame
from hypervector.research.market_cipher_strategy_research import (
    HulkResearchProfile,
    _profile_signals,
    resolve_hulk_research_profile,
)

_BAR = pd.Timedelta(minutes=30)
_SOURCE_BAR = pd.Timedelta(minutes=5)
_CORE_SYMBOLS = frozenset(("BTC", "ETH", "SOL", "HYPE"))
_PRICE_FIELDS = ("reference_price", "stop_anchor")


@dataclass(frozen=True)
class HulkParityEntry:
    """One normalized entry row shared by research and live paths."""

    decision_time_ms: int
    side: str
    reference_price: float
    score: int
    trigger: str
    evidence: tuple[str, ...]
    stop_anchor: float

    def __post_init__(self) -> None:
        """Reject malformed entry identities and economic fields."""
        if isinstance(self.decision_time_ms, bool) or self.decision_time_ms < 0:
            raise ValueError("Hulk parity decision time must be nonnegative")
        if self.side not in {"long", "short"}:
            raise ValueError("Hulk parity side must be long or short")
        prices = (self.reference_price, self.stop_anchor)
        if not all(math.isfinite(value) and value > 0.0 for value in prices):
            raise ValueError("Hulk parity prices must be positive and finite")
        if self.score < 1 or not self.trigger or not self.evidence:
            raise ValueError("Hulk parity signal evidence is incomplete")


@dataclass(frozen=True)
class _ParityConfig:
    backtest_lab_root: Path
    supertrend_period: int
    supertrend_multiplier: float
    adx_period: int
    squeeze_period: int
    minimum_score: int
    pivot_bars: int
    adx_usable: float
    adx_trending: float


def compare_hulk_bidirectional_entries(
    historical: tuple[HulkParityEntry, ...],
    live: tuple[HulkParityEntry, ...],
) -> dict[str, object]:
    """Compare exact entry identities and all frozen decision-risk fields."""
    historical_map = _entry_map(historical, "historical")
    live_map = _entry_map(live, "live")
    historical_keys = set(historical_map)
    live_keys = set(live_map)
    missing = [
        _payload(historical_map[key]) for key in sorted(historical_keys - live_keys)
    ]
    extra = [_payload(live_map[key]) for key in sorted(live_keys - historical_keys)]
    mismatches = _entry_mismatches(historical_map, live_map)
    return {
        "historical_entries": len(historical),
        "live_entries": len(live),
        "matched_entry_rows": len(historical_keys & live_keys),
        "missing_from_live": missing,
        "extra_in_live": extra,
        "mismatches": mismatches,
        "exact_parity": not missing and not extra and not mismatches,
    }


def build_hulk_bidirectional_provider_parity(
    raw_bars: pd.DataFrame,
    *,
    symbol: str,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int,
    backtest_lab_root: Path,
    component_builder: ComponentBuilder = compute_market_cipher_signal_components,
    quality_builder: QualityBuilder = build_hulk_quality_frame,
) -> dict[str, object]:
    """Run frozen research and live builders over identical completed 5m rows."""
    observed = _validated_scope(symbol, observed_at, after_decision_time_ms)
    profile = resolve_hulk_research_profile(HULK_BIDIRECTIONAL_STRATEGY)
    strategy, components, quality = _research_inputs(
        raw_bars,
        observed,
        profile,
        backtest_lab_root,
        component_builder,
        quality_builder,
    )
    historical = _historical_entries(
        strategy,
        components,
        quality,
        profile,
        symbol,
        after_decision_time_ms,
    )
    live = _live_entries(
        raw_bars,
        observed,
        after_decision_time_ms,
        _config(profile, backtest_lab_root),
        component_builder,
        quality_builder,
    )
    report = compare_hulk_bidirectional_entries(historical, live)
    report.update(_report_contract(symbol, observed, after_decision_time_ms, report))
    return report


def _research_inputs(
    raw: pd.DataFrame,
    observed: pd.Timestamp,
    profile: HulkResearchProfile,
    root: Path,
    component_builder: ComponentBuilder,
    quality_builder: QualityBuilder,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    completed = _completed_source(raw, observed)
    strategy = resample_cipher_bars(completed, bar_minutes=30)
    indexed = strategy.set_index("bar_open_at")
    components = component_builder(strategy, root, bar_minutes=30)
    quality = quality_builder(
        indexed,
        supertrend_period=profile.supertrend_period,
        supertrend_multiplier=profile.supertrend_multiplier,
        adx_period=profile.adx_period,
        squeeze_period=profile.squeeze_period,
    )
    return indexed, components, quality


def _completed_source(raw: pd.DataFrame, observed: pd.Timestamp) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"Hulk parity source bars missing columns: {missing}")
    source = raw.loc[:, sorted(required)].copy()
    times = pd.DatetimeIndex(source.pop("timestamp"))
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Hulk parity timestamps must be aware, unique, and ordered")
    source.insert(0, "bar_open_at", times.tz_convert("UTC"))
    completed = source.loc[source["bar_open_at"] + _SOURCE_BAR <= observed]
    if completed.empty:
        raise ValueError("Hulk parity source has no completed 5m bars")
    return completed


def _historical_entries(
    bars: pd.DataFrame,
    components: pd.DataFrame,
    quality: pd.DataFrame,
    profile: HulkResearchProfile,
    symbol: str,
    boundary_ms: int,
) -> tuple[HulkParityEntry, ...]:
    signals = _profile_signals(bars, components, quality, profile, symbol)
    output = []
    for _, signal in signals.iterrows():
        timestamp = pd.Timestamp(signal["signal_time_utc"])
        entry = _signal_entry(signal, float(bars.loc[timestamp, "close"]))
        if entry.decision_time_ms > boundary_ms:
            output.append(entry)
    return tuple(output)


def _live_entries(
    raw: pd.DataFrame,
    observed: pd.Timestamp,
    boundary_ms: int,
    config: _ParityConfig,
    component_builder: ComponentBuilder,
    quality_builder: QualityBuilder,
) -> tuple[HulkParityEntry, ...]:
    decisions = build_completed_hulk_decisions(
        raw,
        observed_at=observed,
        config=config,
        after_decision_time_ms=boundary_ms,
        allowed_sides=frozenset(("long", "short")),
        component_builder=component_builder,
        quality_builder=quality_builder,
    )
    return tuple(_decision_entry(row) for row in decisions if row.entry_eligible)


def _signal_entry(signal: pd.Series, reference_price: float) -> HulkParityEntry:
    timestamp = pd.Timestamp(signal["signal_time_utc"])
    return HulkParityEntry(
        decision_time_ms=int((timestamp + _BAR).timestamp() * 1_000),
        side=str(signal["side"]),
        reference_price=reference_price,
        score=int(signal["score"]),
        trigger=str(signal["trigger"]),
        evidence=tuple(str(value) for value in signal["evidence"]),
        stop_anchor=float(signal["stop_anchor"]),
    )


def _decision_entry(decision: HulkSmashLiveDecision) -> HulkParityEntry:
    if decision.signal_side is None or decision.stop_anchor is None:
        raise ValueError("eligible Hulk live decision is incomplete")
    return HulkParityEntry(
        decision_time_ms=decision.decision_time_ms,
        side=decision.signal_side,
        reference_price=decision.reference_price,
        score=decision.score,
        trigger=decision.trigger,
        evidence=decision.evidence,
        stop_anchor=decision.stop_anchor,
    )


def _entry_map(
    values: tuple[HulkParityEntry, ...], label: str
) -> dict[tuple[int, str], HulkParityEntry]:
    output: dict[tuple[int, str], HulkParityEntry] = {}
    for value in values:
        key = (value.decision_time_ms, value.side)
        if key in output:
            raise ValueError(f"duplicate {label} Hulk entry identity: {key}")
        output[key] = value
    return output


def _entry_mismatches(
    historical: dict[tuple[int, str], HulkParityEntry],
    live: dict[tuple[int, str], HulkParityEntry],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    fields = (*_PRICE_FIELDS, "score", "trigger", "evidence")
    for key in sorted(set(historical) & set(live)):
        for field in fields:
            left = getattr(historical[key], field)
            right = getattr(live[key], field)
            if not _equal(left, right):
                output.append(_mismatch(key, field, left, right))
    return output


def _equal(left: object, right: object) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
    return left == right


def _mismatch(
    key: tuple[int, str], field: str, historical: object, live: object
) -> dict[str, object]:
    return {
        "decision_time_ms": key[0],
        "side": key[1],
        "field": field,
        "historical": historical,
        "live": live,
    }


def _payload(value: HulkParityEntry) -> dict[str, object]:
    return {
        "decision_time_ms": value.decision_time_ms,
        "side": value.side,
        "reference_price": value.reference_price,
        "score": value.score,
        "trigger": value.trigger,
        "evidence": list(value.evidence),
        "stop_anchor": value.stop_anchor,
    }


def _validated_scope(
    symbol: str, observed_at: pd.Timestamp, boundary_ms: int
) -> pd.Timestamp:
    if symbol not in _CORE_SYMBOLS:
        raise ValueError("Hulk parity symbol must be a supported core asset")
    observed = pd.Timestamp(observed_at)
    if observed.tzinfo is None:
        raise ValueError("Hulk parity observed_at must be timezone-aware")
    if isinstance(boundary_ms, bool) or not isinstance(boundary_ms, int):
        raise ValueError("Hulk parity boundary must be an integer")
    if boundary_ms < 0 or boundary_ms >= int(observed.timestamp() * 1_000):
        raise ValueError("Hulk parity boundary must precede observation")
    return observed.tz_convert("UTC")


def _config(profile: HulkResearchProfile, root: Path) -> _ParityConfig:
    return _ParityConfig(
        root,
        profile.supertrend_period,
        profile.supertrend_multiplier,
        profile.adx_period,
        profile.squeeze_period,
        profile.minimum_score,
        profile.pivot_bars,
        profile.adx_usable,
        profile.adx_trending,
    )


def _report_contract(
    symbol: str,
    observed: pd.Timestamp,
    boundary_ms: int,
    report: dict[str, object],
) -> dict[str, object]:
    exact = bool(report["exact_parity"])
    nonvacuous = bool(report["historical_entries"])
    return {
        "schema_version": "hulk_bidirectional_provider_parity_v1",
        "strategy_id": HULK_BIDIRECTIONAL_STRATEGY,
        "symbol": symbol,
        "observed_at_utc": observed.isoformat(),
        "after_decision_time_ms": boundary_ms,
        "technical_assessment": {
            "source_signal_parity_resolved": exact and nonvacuous,
            "decision_parity_non_vacuous": nonvacuous,
        },
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
        },
        "limitations": [
            "signal parity does not establish profitable execution",
            "the audit does not reproduce IOC fills, slippage, fees, or funding",
            "a finite input window cannot prove parity outside that window",
        ],
    }
