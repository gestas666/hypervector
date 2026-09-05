"""Reproduce continuing-breakout entry parity using the frozen SNDK recipe."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.hip3_cohort_providers import (
    HIP3_BREAKOUT_SNDK_FRESH15_STRATEGY,
    Hip3BreakoutPressureCollector,
)
from hypervector.live.hip3_ledger_pressure import Hip3PressureObservation
from hypervector.live.hip3_provider_recipes import configured_hip3_recipe
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
    build_breakout_pressure_signals,
)

_SYMBOL = "xyz:SNDK"
_PERIODS = 101
_BASE_PRICE = 1000.0
_WICK = 0.1
_PRESSURE = 0.6
_PRESSURE_AGE_MS = 1000
_BAR = pd.Timedelta(minutes=15)


class ContinuousPressure:
    """Deterministic fresh pressure fixture, independent of live ledgers."""

    def __init__(self, direction: int) -> None:
        """Bind one synthetic continuous pressure direction."""
        self._imbalance = direction * _PRESSURE

    def latest_at_or_before(
        self,
        symbol: str,
        not_after_ms: int,
    ) -> Hip3PressureObservation:
        """Return a causal fresh fixture observation for the exact symbol."""
        if symbol != _SYMBOL:
            raise ValueError("diagnostic pressure supports xyz:SNDK only")
        return Hip3PressureObservation(not_after_ms - _PRESSURE_AGE_MS, self._imbalance)


def diagnose(direction: int) -> dict[str, object]:
    """Compare two continuous-state decisions with the canonical onset engine."""
    if direction not in {-1, 1}:
        raise ValueError("diagnostic direction must be -1 or 1")
    recipe = configured_hip3_recipe(HIP3_BREAKOUT_SNDK_FRESH15_STRATEGY)
    if not isinstance(recipe, Hip3BreakoutPressureConfig):
        raise TypeError("SNDK diagnostic requires the configured breakout recipe")
    bars = _bars(direction)
    collector = Hip3BreakoutPressureCollector(
        strategy_id=HIP3_BREAKOUT_SNDK_FRESH15_STRATEGY,
        config=recipe,
        pressure_source=ContinuousPressure(direction),
    )
    current = []
    for count in (_PERIODS - 1, _PERIODS):
        at = bars.timestamp.iloc[count - 1] + _BAR
        batch = collector(
            bars.iloc[:count],
            symbol=_SYMBOL,
            observed_at=at,
            after_decision_time_ms=int(at.timestamp() * 1000) - 1,
        )
        current.append(
            {
                "at": str(at),
                "intents": len(batch.intents),
                "evaluation": batch.evaluations[0].as_payload(),
            }
        )
    source = bars.set_index("timestamp").assign(
        decision_imbalance_10=direction * _PRESSURE,
        gap_before_bars=0,
    )
    canonical = build_breakout_pressure_signals(source, recipe)
    side = "short" if direction < 0 else "long"
    entries = canonical[f"{side}_entry"]
    return {
        "side": side,
        "current_provider": current,
        "canonical_last_two_entries": entries.tail(2).tolist(),
        "canonical_total_entries": int(entries.sum()),
        "mismatched_boundaries": sum(
            bool(row["intents"]) != bool(expected)
            for row, expected in zip(current, entries.tail(2), strict=True)
        ),
    }


def _bars(direction: int) -> pd.DataFrame:
    times = pd.date_range("2026-05-18T00:00:00Z", periods=_PERIODS, freq="15min")
    close = pd.Series([_BASE_PRICE + direction * i for i in range(_PERIODS)])
    return pd.DataFrame(
        {
            "timestamp": times,
            "open": close,
            "high": close + _WICK,
            "low": close - _WICK,
            "close": close,
            "volume": 10.0,
        }
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Publish synthetic discrepancy evidence without live execution authority."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    paths = [
        Path(__file__),
        *[
            root / "src/hypervector" / name
            for name in (
                "live/hip3_cohort_providers.py",
                "live/hip3_provider_recipes.py",
                "research/hip3_breakout_pressure_signals.py",
            )
        ],
    ]
    write_immutable_json(
        args.out,
        {
            "schema_version": 1,
            "execution_authority": "none",
            "strategy_id": HIP3_BREAKOUT_SNDK_FRESH15_STRATEGY,
            "symbol": _SYMBOL,
            "synthetic": True,
            "private_fills_inferred": False,
            "cases": [diagnose(-1), diagnose(1)],
            "evidence": {str(path.resolve()): file_evidence(path) for path in paths},
            "limitation": "Reproduction proves signal mismatch, not realized loss attribution.",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
