"""Frozen first-observed candle prefixes for HIP-3 lifecycle replays."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from hypervector.data.jsonl_prefix import read_jsonl_prefix
from hypervector.live.hip3_shadow_candle_storage import (
    validate_candle_row,
)
from hypervector.live.hip3_shadow_candle_contracts import (
    hip3_shadow_candle_contract,
)
from hypervector.research.hip3_shadow_command_sources import CandleFetcher


class FrozenHip3CandleFetcher:
    """Serve immutable observer candle prefixes through the fetcher boundary."""

    def __init__(
        self, symbol: str, signal_ledger: Path, profit_lock_ledger: Path | None
    ) -> None:
        """Load and validate every configured prefix before replay evaluation."""
        hip3_shadow_candle_contract(symbol, "15m")
        self._symbol = symbol
        self._frames: dict[str, pd.DataFrame] = {
            "15m": _prefix_frame(signal_ledger, symbol, "15m", "signal candle ledger"),
        }
        if profit_lock_ledger is not None:
            self._frames["1m"] = _prefix_frame(
                profit_lock_ledger, symbol, "1m", "profit-lock candle ledger"
            )

    def __call__(
        self,
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int,
    ) -> pd.DataFrame:
        """Return the frozen completed prefix for one exact source identity."""
        if symbol != self._symbol:
            raise ValueError("frozen HIP-3 candle request identity is invalid")
        if timeframe not in self._frames:
            raise ValueError("frozen HIP-3 candle timeframe is unsupported")
        if lookback_days <= 0.0 or end_ms <= 0:
            raise ValueError("frozen HIP-3 candle request bounds are invalid")
        frame = self._frames[timeframe]
        output = frame.loc[frame["bar_close_ms"].le(end_ms)].copy()
        if output.empty:
            raise ValueError("frozen HIP-3 candle prefix has no completed rows")
        return output


def configured_frozen_candle_fetcher(
    symbol: str,
    signal_ledger: Path | None,
    profit_lock_ledger: Path | None,
    output: Path,
    default: CandleFetcher,
    *,
    required: bool,
) -> CandleFetcher:
    """Select frozen prefixes or fail before a mutable live-bound refetch."""
    if signal_ledger is None and profit_lock_ledger is None:
        if required:
            raise ValueError("live-bound HIP-3 replay requires frozen candle ledgers")
        return default
    if signal_ledger is None:
        raise ValueError("both HIP-3 frozen candle ledgers are required")
    if required and profit_lock_ledger is None:
        raise ValueError("live-bound HIP-3 replay requires frozen candle ledgers")
    configured = [signal_ledger, output]
    if profit_lock_ledger is not None:
        configured.append(profit_lock_ledger)
    resolved = {path.resolve() for path in configured}
    if len(resolved) != len(configured):
        raise ValueError("HIP-3 frozen candle and output paths must be distinct")
    return FrozenHip3CandleFetcher(symbol, signal_ledger, profit_lock_ledger)


def _prefix_frame(path: Path, symbol: str, timeframe: str, label: str) -> pd.DataFrame:
    rows, evidence = read_jsonl_prefix(path, label)
    contract = hip3_shadow_candle_contract(symbol, timeframe)
    for row in rows:
        validate_candle_row(row, contract)
    output = pd.DataFrame([_replay_row(row, evidence) for row in rows])
    if output["timestamp"].duplicated().any():
        raise ValueError(f"{label} contains duplicate timestamps")
    return output.sort_values("timestamp").reset_index(drop=True)


def _replay_row(
    row: Mapping[str, object], evidence: Mapping[str, object]
) -> dict[str, object]:
    return {
        "timestamp": pd.Timestamp(int(row["bar_open_ms"]), unit="ms", tz="UTC"),
        "open": row["open"],
        "high": row["high"],
        "low": row["low"],
        "close": row["close"],
        "volume": row["volume"],
        "source": "hl",
        "bar_close_ms": row["bar_close_ms"],
        "source_observed_at_ms": row["observed_at_ms"],
        "source_prospective": row["prospective"],
        "observation_source": row["source"],
        "source_prefix_path": evidence["path"],
        "source_prefix_bytes": evidence["bytes"],
        "source_prefix_rows": evidence["rows"],
        "source_prefix_sha256": evidence["sha256"],
    }
