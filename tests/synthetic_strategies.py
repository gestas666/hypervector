"""Deterministic test-only strategy family (registered from tests, never from src/).

``src/`` registers no strategy family, so generic engine tests (backtest,
sweep, tune, pipeline, Nautilus, paper, export, ml) use these:

* ``test_sma_cross_long`` / ``test_sma_cross_short``: SMA fast/slow cross,
  entering on the cross and exiting on the opposite cross. Standard
  execution; supports the generic order-book gate.
* ``test_managed_long`` / ``test_managed_short``: the same signals with every
  declared execution option set (post-only entries, fixed margin sizing at a
  declared leverage, strategy-managed exits and the ``hl_maker`` fee model).

The conftest registers the family before every test.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hypervector.strategies.registry import ExecutionProfile, StrategySpec, register

SYNTHETIC_LONG = "test_sma_cross_long"
SYNTHETIC_SHORT = "test_sma_cross_short"
MANAGED_LONG = "test_managed_long"
MANAGED_SHORT = "test_managed_short"

PARAM_GRID: dict[str, list[Any]] = {"fast": [5, 10], "slow": [20, 30]}

#: Every declared option away from the standard path.
MANAGED_EXECUTION = ExecutionProfile(
    post_only_entries=True,
    entry_ttl_seconds=120.0,
    fixed_margin_fraction=0.5,
    leverage=10.0,
    strategy_managed_exits=True,
    fee_model="hl_maker",
)


def sma_cross_signals(
    df: pd.DataFrame,
    *,
    fast: int = 5,
    slow: int = 20,
    direction: str = "long",
    book_gate: bool = False,
    max_spread_bps: float = 3.0,
    min_obi: float = 0.1,
) -> tuple[pd.Series, pd.Series, str]:
    """Enter on the fast/slow SMA cross in ``direction``; exit on the opposite cross."""
    if int(fast) >= int(slow):
        raise ValueError("fast must be < slow")
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be long|short, got {direction}")
    close = df["close"].astype(float)
    fast_ma = close.rolling(int(fast), min_periods=int(fast)).mean()
    slow_ma = close.rolling(int(slow), min_periods=int(slow)).mean()
    cross_up = ((fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))).fillna(
        False
    )
    cross_down = (
        (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))
    ).fillna(False)
    entries, exits = (
        (cross_up, cross_down) if direction == "long" else (cross_down, cross_up)
    )
    if book_gate:
        from hypervector.data.book_align import gate_signals_by_orderbook

        entries = gate_signals_by_orderbook(
            entries,
            df,
            direction=direction,
            max_spread_bps=float(max_spread_bps),
            min_obi=float(min_obi),
        )
    return entries.astype(bool), exits.astype(bool), direction


def sma_cross_long(
    df: pd.DataFrame,
    fast: int = 5,
    slow: int = 20,
    book_gate: bool = False,
    max_spread_bps: float = 3.0,
    min_obi: float = 0.1,
) -> tuple[pd.Series, pd.Series, str]:
    return sma_cross_signals(
        df,
        fast=fast,
        slow=slow,
        direction="long",
        book_gate=book_gate,
        max_spread_bps=max_spread_bps,
        min_obi=min_obi,
    )


def sma_cross_short(
    df: pd.DataFrame,
    fast: int = 5,
    slow: int = 20,
    book_gate: bool = False,
    max_spread_bps: float = 3.0,
    min_obi: float = 0.1,
) -> tuple[pd.Series, pd.Series, str]:
    return sma_cross_signals(
        df,
        fast=fast,
        slow=slow,
        direction="short",
        book_gate=book_gate,
        max_spread_bps=max_spread_bps,
        min_obi=min_obi,
    )


def register_family() -> None:
    """Register the four synthetic specs (idempotent)."""
    for name, role, builder, execution in (
        (SYNTHETIC_LONG, "uptrend", sma_cross_long, ExecutionProfile()),
        (SYNTHETIC_SHORT, "downtrend", sma_cross_short, ExecutionProfile()),
        (MANAGED_LONG, "uptrend", sma_cross_long, MANAGED_EXECUTION),
        (MANAGED_SHORT, "downtrend", sma_cross_short, MANAGED_EXECUTION),
    ):
        register(
            StrategySpec(
                name=name,
                role=role,  # type: ignore[arg-type]
                param_grid={key: list(values) for key, values in PARAM_GRID.items()},
                build_signals=builder,
                description="test-only SMA cross",
                supports_book_gate=execution.standard,
                execution=execution,
            )
        )
