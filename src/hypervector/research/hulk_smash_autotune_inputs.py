"""Verified Hyperliquid bar, funding, and Cipher inputs for Hulk AutoTune."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.backtest_lab_cipher_adapter import (
    compute_market_cipher_signal_components,
    inspect_backtest_lab_sources,
)
from hypervector.research.cipher_suite_duckdb import (
    CIPHER_RESEARCH_SYMBOLS,
    load_cipher_ohlcv,
)
from hypervector.research.cipher_suite_timeframes import resample_cipher_bars
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)
from hypervector.research.market_cipher_strategy_research import frame_sha256


@dataclass(frozen=True)
class HulkAutotuneInputs:
    """Causal tuning inputs plus immutable source evidence."""

    bars_by_symbol: dict[str, pd.DataFrame]
    components_by_symbol: dict[str, pd.DataFrame]
    source_identity: dict[str, object]


def load_hulk_autotune_inputs(
    *,
    database_path: Path,
    backtest_lab_root: Path,
    funding_by_symbol: dict[str, tuple[Path, ...]],
    symbols: tuple[str, ...],
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
) -> HulkAutotuneInputs:
    """Load bounded canonical venue inputs with warmup and exact funding."""
    normalized = _validate_request(symbols, funding_by_symbol, start_utc, end_utc)
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    components_by_symbol: dict[str, pd.DataFrame] = {}
    evidence: dict[str, object] = {
        "database_path": str(database_path.resolve()),
        "backtest_lab": inspect_backtest_lab_sources(backtest_lab_root),
        "symbols": {},
    }
    symbol_evidence = evidence["symbols"]
    if not isinstance(symbol_evidence, dict):
        raise RuntimeError("invalid Hulk tuning source evidence container")
    for symbol in normalized:
        bars, components, identity = _symbol_inputs(
            database_path,
            backtest_lab_root,
            funding_by_symbol[symbol],
            symbol,
            start_utc,
            end_utc,
        )
        bars_by_symbol[symbol] = bars
        components_by_symbol[symbol] = components
        symbol_evidence[symbol] = identity
    return HulkAutotuneInputs(bars_by_symbol, components_by_symbol, evidence)


def _symbol_inputs(
    database_path: Path,
    backtest_lab_root: Path,
    funding_paths: tuple[Path, ...],
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    inputs = load_cipher_ohlcv(
        database_path,
        symbol,
        start.to_pydatetime(),
        end.to_pydatetime(),
        history_bars=1_440,
        horizon_bars=288,
    )
    strategy = resample_cipher_bars(inputs.bars, bar_minutes=30)
    bars = strategy.set_index("bar_open_at")
    components = compute_market_cipher_signal_components(
        strategy, backtest_lab_root, bar_minutes=30
    )
    funding = load_verified_hourly_funding(
        list(funding_paths),
        bars.index.min(),
        bars.index.max() + pd.Timedelta(minutes=30),
    )
    replay_bars = attach_hourly_funding(bars, funding)
    replay_bars["wave_cross"] = components["wave_cross"]
    evidence = {
        "bar_count": len(replay_bars),
        "first_bar_utc": replay_bars.index.min().isoformat(),
        "last_bar_utc": replay_bars.index.max().isoformat(),
        "bars_sha256": frame_sha256(replay_bars),
        "components_sha256": frame_sha256(components),
        "funding_files": [
            {"path": str(path.resolve()), **file_evidence(path)}
            for path in funding_paths
        ],
    }
    return replay_bars, components, evidence


def _validate_request(
    symbols: tuple[str, ...],
    funding: dict[str, tuple[Path, ...]],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[str, ...]:
    normalized = tuple(symbol.strip().upper() for symbol in symbols)
    first, last = pd.Timestamp(start), pd.Timestamp(end)
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValueError("Hulk tuning symbols must be non-empty and unique")
    if any(symbol not in CIPHER_RESEARCH_SYMBOLS for symbol in normalized):
        supported = ", ".join(CIPHER_RESEARCH_SYMBOLS)
        raise ValueError(f"Hulk tuning symbol must be one of: {supported}")
    if set(normalized) != set(funding):
        raise ValueError("Hulk tuning requires funding for every symbol")
    if first.tz is None or last.tz is None or first >= last:
        raise ValueError("Hulk tuning window must be aware and ordered")
    return normalized
