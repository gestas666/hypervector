"""Test-only per-symbol engine configuration from the generic cohort asset model.

The live engine runs one protected-order lifecycle per enabled symbol from an
``AssetLiveConfig``. These helpers build one with fixed, neutral values so the
engine, ledger, restart and telemetry tests need no strategy profile.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_live_config import AssetLiveConfig

ENGINE_PROFILE_ID = "fixture_engine"


def engine_ledger_path(root: Path, symbol: str = "SOL") -> Path:
    """Return the per-symbol live ledger path the ledger accepts under ``root``."""
    return root / "data" / "live" / "bidirectional_cohort" / f"{symbol.lower()}.jsonl"


def engine_asset_config(
    live_ledger: Path,
    *,
    symbol: str = "SOL",
    mode: str = "live",
    enabled: bool = True,
    accepts_live_risk: bool = True,
    **overrides: object,
) -> AssetLiveConfig:
    """Return one armed (by default) single-symbol execution envelope."""
    config = AssetLiveConfig(
        parent_profile_id=ENGINE_PROFILE_ID,
        network="mainnet",
        margin_mode="isolated",
        symbol=symbol,
        sides=frozenset({"long", "short"}),
        leverage=5.0,
        venue_max_leverage=20.0,
        margin_fraction=0.03,
        max_notional_usd=22.5,
        market_slippage_cap_fraction=0.01,
        stop_bps=80.0,
        maximum_hold_seconds=172_800,
        live_ledger=live_ledger,
        mode=mode,  # type: ignore[arg-type]
        enabled=enabled,
        accepts_live_risk=accepts_live_risk,
    )
    return replace(config, **overrides) if overrides else config
