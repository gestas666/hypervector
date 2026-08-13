"""Symbol-exact immutable sidecar frames for HIP-3 archive research."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from hypervector.data.oxa_api import validate_market_symbol
from hypervector.research.mu_hip3_archive_candidate import MuArchiveCandidateResult


def build_archive_trade_frame(
    results: tuple[MuArchiveCandidateResult, ...],
) -> pd.DataFrame:
    """Return nominal and stress lifecycle rows with exact result symbols."""
    rows: list[dict[str, object]] = []
    for result in results:
        validate_market_symbol(result.symbol, "hip3")
        rows.extend(_result_trade_rows(result))
    columns = ["timeframe", "family", "partition", "symbol"]
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=columns)


def build_archive_source_frame(
    bars_by_timeframe: dict[str, pd.DataFrame],
    funding: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:
    """Return causal bar and funding sources under one exact HIP-3 identity."""
    validate_market_symbol(symbol, "hip3")
    frames = [
        _identified_frame(
            bars.reset_index(names="timestamp"),
            symbol,
            f"hip3_l2_venue_path_{timeframe}",
        )
        for timeframe, bars in bars_by_timeframe.items()
    ]
    frames.append(_identified_frame(funding.copy(), symbol, "official_funding"))
    return pd.concat(frames, ignore_index=True, sort=False)


def _result_trade_rows(result: MuArchiveCandidateResult) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for family in result.families:
        for partition in family.partitions:
            scenarios = (("nominal", partition.nominal), ("stress", partition.stress))
            rows.extend(
                {
                    "timeframe": result.timeframe,
                    "family": family.family,
                    "partition": partition.name,
                    "friction_scenario": scenario,
                    "symbol": result.symbol,
                    **asdict(trade),
                }
                for scenario, report in scenarios
                for trade in report.trades
            )
    return rows


def _identified_frame(
    frame: pd.DataFrame, symbol: str, record_type: str
) -> pd.DataFrame:
    if "symbol" in frame:
        observed = set(frame["symbol"].dropna().astype(str))
        if observed and observed != {symbol}:
            raise ValueError("HIP-3 sidecar source contains a conflicting symbol")
        frame["symbol"] = symbol
    else:
        frame.insert(0, "symbol", symbol)
    if "record_type" in frame:
        raise ValueError("HIP-3 sidecar source already defines record_type")
    frame.insert(1, "record_type", record_type)
    return frame
