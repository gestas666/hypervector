"""The per-symbol configuration surface the shared execution engine reads.

The cohort builds one engine per enabled symbol from its ``AssetLiveConfig``;
this protocol names exactly the fields the engine, its restart recovery and
its lifecycle telemetry read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class SolRangeOnsetConfig(Protocol):
    """Symbol execution and protection envelope consumed by the live engine."""

    @property
    def symbol(self) -> str: ...

    @property
    def strategy_id(self) -> str: ...

    @property
    def profile_id(self) -> str: ...

    @property
    def margin_mode(self) -> str: ...

    @property
    def leverage(self) -> float: ...

    @property
    def venue_max_leverage(self) -> float: ...

    @property
    def margin_fraction(self) -> float: ...

    @property
    def max_notional_usd(self) -> float: ...

    @property
    def market_slippage_cap_fraction(self) -> float: ...

    @property
    def effective_entry_slippage_cap_fraction(self) -> float: ...

    @property
    def max_positions_per_symbol(self) -> int: ...

    @property
    def stop_bps(self) -> float: ...

    @property
    def maximum_hold_seconds(self) -> int: ...

    @property
    def live_ledger(self) -> Path: ...

    @property
    def authoritative_ledger(self) -> Path: ...

    @property
    def capital_source(self) -> str: ...

    @property
    def portfolio_purpose(self) -> str: ...

    @property
    def metalabel_mode(self) -> str: ...

    @property
    def profile_fingerprint(self) -> str: ...

    @property
    def run_fingerprint(self) -> str: ...

    def require_live_start(self, *, credentials_present: bool) -> None:
        """Refuse a live start unless every authority condition holds."""
        ...
