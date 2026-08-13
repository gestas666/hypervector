"""Report-only parity audit for live and historical HT-Breakout entries."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from hypervector.live.hype_breakout_cohort_provider import (
    HYPE_BREAKOUT_COHORT_STRATEGY,
    HypeBreakoutOnsetCollector,
)
from hypervector.research.hype_breakout_exit_market import build_hype_exit_market
from hypervector.research.range_onset_observation import index_range_onset_bars

_MINUTE = pd.Timedelta(minutes=1)
_PRICE_TOLERANCE = 1e-12


@dataclass(frozen=True)
class ParityEntry:
    """One provider entry decision projected onto a common comparison clock."""

    decision_time_ms: int
    side: str
    reference_price: float

    def __post_init__(self) -> None:
        """Reject malformed decision identities and non-economic prices."""
        if (
            isinstance(self.decision_time_ms, bool)
            or not isinstance(self.decision_time_ms, int)
            or self.decision_time_ms < 0
        ):
            raise ValueError("parity decision_time_ms must be nonnegative")
        if self.side not in {"long", "short"}:
            raise ValueError("parity side must be long or short")
        if not math.isfinite(self.reference_price) or self.reference_price <= 0.0:
            raise ValueError("parity reference_price must be positive and finite")


def compare_hype_breakout_entries(
    historical: tuple[ParityEntry, ...],
    live: tuple[ParityEntry, ...],
) -> dict[str, object]:
    """Compare exact decision-side identities and their source close prices."""
    historical_map = _entry_map(historical, "historical")
    live_map = _entry_map(live, "live")
    historical_keys = set(historical_map)
    live_keys = set(live_map)
    missing = [
        _payload(historical_map[key]) for key in sorted(historical_keys - live_keys)
    ]
    extra = [_payload(live_map[key]) for key in sorted(live_keys - historical_keys)]
    prices = _price_mismatches(historical_map, live_map)
    return {
        "historical_entries": len(historical),
        "live_entries": len(live),
        "matched_identities": len(historical_keys & live_keys),
        "missing_from_live": missing,
        "extra_in_live": extra,
        "reference_price_mismatches": prices,
        "exact_parity": not missing and not extra and not prices,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def build_hype_breakout_provider_parity(
    raw_bars: pd.DataFrame,
    funding: pd.DataFrame,
    *,
    symbol: str,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int,
) -> dict[str, object]:
    """Run both current provider paths on one identical completed-bar window."""
    observed = _aware_utc(observed_at)
    observed_ms = int(observed.timestamp() * 1_000)
    _validate_boundary(after_decision_time_ms, observed_ms)
    completed = _completed_raw(raw_bars, observed)
    market, market_evidence = build_hype_exit_market(completed, funding)
    collector = HypeBreakoutOnsetCollector()
    batch = collector(
        completed,
        symbol=symbol,
        observed_at=observed,
        after_decision_time_ms=after_decision_time_ms,
    )
    historical = _historical_entries(
        market,
        after_decision_time_ms,
        observed_ms,
    )
    live = tuple(
        ParityEntry(row.decision_time_ms, row.side, row.reference_price)
        for row in batch.intents
    )
    report = compare_hype_breakout_entries(historical, live)
    report.update(
        _integration_contract(
            symbol,
            observed,
            after_decision_time_ms,
            len(completed),
            len(batch.evaluations),
            market_evidence.breakout_onsets,
        )
    )
    return report


def _historical_entries(
    market: pd.DataFrame,
    boundary_ms: int,
    observed_ms: int,
) -> tuple[ParityEntry, ...]:
    selected: list[ParityEntry] = []
    for timestamp, row in market.loc[market["entry_side"].notna()].iterrows():
        decision_ms = int((pd.Timestamp(timestamp) + _MINUTE).timestamp() * 1_000)
        if boundary_ms < decision_ms <= observed_ms:
            selected.append(
                ParityEntry(decision_ms, str(row["entry_side"]), float(row["close"]))
            )
    return tuple(selected)


def _entry_map(
    values: tuple[ParityEntry, ...],
    label: str,
) -> dict[tuple[int, str], ParityEntry]:
    mapped: dict[tuple[int, str], ParityEntry] = {}
    for value in values:
        key = (value.decision_time_ms, value.side)
        if key in mapped:
            raise ValueError(f"duplicate {label} HT-Breakout entry identity: {key}")
        mapped[key] = value
    return mapped


def _price_mismatches(
    historical: dict[tuple[int, str], ParityEntry],
    live: dict[tuple[int, str], ParityEntry],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for key in sorted(set(historical) & set(live)):
        left = historical[key].reference_price
        right = live[key].reference_price
        difference = abs(left - right)
        if difference > max(_PRICE_TOLERANCE, abs(left) * _PRICE_TOLERANCE):
            output.append(
                {
                    "decision_time_ms": key[0],
                    "side": key[1],
                    "historical_reference_price": left,
                    "live_reference_price": right,
                    "absolute_difference": difference,
                }
            )
    return output


def _payload(value: ParityEntry) -> dict[str, object]:
    return {
        "decision_time_ms": value.decision_time_ms,
        "side": value.side,
        "reference_price": value.reference_price,
    }


def _completed_raw(raw_bars: pd.DataFrame, observed: pd.Timestamp) -> pd.DataFrame:
    indexed = index_range_onset_bars(raw_bars)
    completed = indexed.loc[indexed.index + _MINUTE <= observed]
    if completed.empty:
        raise ValueError("HT-Breakout parity window has no completed bars")
    return completed.reset_index()


def _integration_contract(
    symbol: str,
    observed: pd.Timestamp,
    boundary_ms: int,
    bars: int,
    evaluations: int,
    onsets: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_breakout_historical_live_provider_parity_v1",
        "strategy_id": HYPE_BREAKOUT_COHORT_STRATEGY,
        "symbol": symbol,
        "observed_at_utc": observed.isoformat(),
        "after_decision_time_ms": boundary_ms,
        "completed_bar_rows": bars,
        "live_evaluations": evaluations,
        "historical_breakout_onsets": onsets,
        "contract": {
            "entry_event": "completed_5m_breakout_onset",
            "entry_side": "completed_1h_sma10_sma30_structural_direction",
            "decision_time": "source_bar_close_plus_one_minute",
            "reference_price": "source_bar_close",
        },
        "limitations": [
            "decision parity does not establish profitable execution",
            "the audit does not reproduce IOC queue position or realized slippage",
            "a finite window cannot prove historical parity outside that window",
        ],
    }


def _aware_utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("HT-Breakout parity observed_at must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _validate_boundary(boundary_ms: int, observed_ms: int) -> None:
    if isinstance(boundary_ms, bool) or not isinstance(boundary_ms, int):
        raise ValueError("HT-Breakout parity boundary must be an integer")
    if boundary_ms < 0 or boundary_ms >= observed_ms:
        raise ValueError("HT-Breakout parity boundary must precede observation")
