"""Common command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from hypervector.config import DEFAULT_LOOKBACK
from typing import TYPE_CHECKING
from hypervector.infra import DataPaths, ensure_data_layout

if TYPE_CHECKING:
    import pandas as pd

    from hypervector.sweep.exits import ExitConfig

SECRET_ENV_WALLET = "HYPERVECTOR_HL_WALLET_ADDRESS"
SECRET_ENV_API_KEY = "HYPERVECTOR_HL_API_PRIVATE_KEY"


class CommandRefused(Exception):
    """A refusal before any side effect; the CLI maps it to exit code 2."""


def exit_config_from_args(args: argparse.Namespace) -> ExitConfig:
    """Build the shared exit model from the canonical exits fragment."""
    from hypervector.sweep.exits import ExitConfig

    return ExitConfig(
        mode=args.exit_mode,
        sl_pct=float(args.sl_pct),
        rr=float(args.rr),
        atr_length=int(args.atr_length),
        sl_atr_mult=float(args.sl_atr_mult),
        trail_atr_mult=float(args.trail_atr_mult),
    )


def _secrets_present() -> bool:
    """True when both live secret env vars are set (values never logged)."""
    return bool(os.environ.get(SECRET_ENV_WALLET)) and bool(
        os.environ.get(SECRET_ENV_API_KEY)
    )


def _default_data_root() -> Path:
    return Path("data")


def _ensure_root(args: argparse.Namespace) -> DataPaths:
    """Create I2 layout under --data-root before any IO."""
    return ensure_data_layout(Path(args.data_root))


def _load_bars(args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load OHLCV from cache or live HL→Binance→Bybit pipeline."""
    from hypervector.data.pipeline import load_research_history

    _ensure_root(args)
    return load_research_history(
        args.data_root,
        symbol=getattr(args, "symbol", "BTC"),
        timeframe=getattr(args, "timeframe", "1m"),
        lookback_days=getattr(args, "lookback", DEFAULT_LOOKBACK),
        strict_hl_only=getattr(args, "strict_hl_only", False),
        force_refresh=getattr(args, "force", False),
    )
