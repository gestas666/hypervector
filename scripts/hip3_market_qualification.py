#!/usr/bin/env python3
"""Capture public, read-only qualification evidence for HIP-3 roster candidates."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Protocol, cast

from hypervector.live.hyperliquid_sol_parsing import mapping, sequence, text
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.hip3_market_qualification import (
    build_hip3_market_qualification,
    validate_hip3_symbol,
)

_DEFAULT_SYMBOLS = ("xyz:SP500", "xyz:SPCX")
_DEFAULT_OUTPUT = Path("data/logs/research/xyz_sp500_spcx_qualification_latest.json")
_DEFAULT_START = "2025-01-01T00:00:00+00:00"
_TIMEFRAMES = ("1m", "5m", "15m")


class Hip3InfoProtocol(Protocol):
    """Official SDK read methods required by this public qualifier."""

    def perp_dexs(self) -> object:
        """Return active builder-deployed perp dex metadata."""
        ...

    def post(self, path: str, payload: dict[str, object]) -> object:
        """Read one official info endpoint payload."""
        ...

    def l2_snapshot(self, name: str) -> object:
        """Return one exact namespaced order book."""
        ...

    def spot_meta(self) -> object:
        """Return public spot-token metadata for collateral resolution."""
        ...

    def candles_snapshot(
        self,
        name: str,
        interval: str,
        startTime: int,
        endTime: int,
    ) -> object:
        """Return one bounded public candle window."""
        ...


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable qualification command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--start", default=_DEFAULT_START)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUTPUT)
    return parser


def run_qualification(
    args: argparse.Namespace,
    *,
    info: Hip3InfoProtocol | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Read exact public venue facts and atomically publish one report."""
    symbols = tuple(args.symbols or _DEFAULT_SYMBOLS)
    dexes = tuple(sorted({validate_hip3_symbol(symbol)[0] for symbol in symbols}))
    if len(dexes) != 1:
        raise ValueError("one qualification run must target exactly one perp dex")
    active_info = info or _official_info(dexes)
    dex = _requested_dex(active_info.perp_dexs(), dexes[0])
    metadata, contexts = _metadata_and_contexts(active_info, dexes[0])
    observed = _aware_now(now_fn)
    start_ms = _timestamp_ms(args.start, "start")
    end_ms = int(observed.timestamp() * 1_000)
    if start_ms >= end_ms:
        raise ValueError("qualification start must precede observation time")
    report = build_hip3_market_qualification(
        dex=dex,
        metadata=metadata,
        spot_metadata=active_info.spot_meta(),
        contexts=contexts,
        books={symbol: active_info.l2_snapshot(symbol) for symbol in symbols},
        candles=_candles(active_info, symbols, start_ms, end_ms),
        requested_symbols=symbols,
        observed_at_utc=observed.isoformat(),
    )
    report["source"] = _source_contract(start_ms, end_ms)
    write_atomic_json(args.out, report)
    return report


def _official_info(dexes: tuple[str, ...]) -> Hip3InfoProtocol:
    try:
        from hyperliquid.info import Info  # type: ignore[import-untyped]
        from hyperliquid.utils.constants import MAINNET_API_URL  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("official Hyperliquid SDK is unavailable") from exc
    return cast(
        Hip3InfoProtocol,
        Info(
            MAINNET_API_URL,
            skip_ws=True,
            perp_dexs=list(dexes),
            timeout=20.0,
        ),
    )


def _requested_dex(value: object, name: str) -> Mapping[str, object]:
    rows = (
        mapping(row, "perp dex")
        for row in sequence(value, "perp dexs")
        if isinstance(row, Mapping)
    )
    matches = [row for row in rows if row.get("name") == name]
    if len(matches) != 1:
        raise ValueError(f"{name} perp dex is unavailable or ambiguous")
    return matches[0]


def _metadata_and_contexts(
    info: Hip3InfoProtocol,
    dex: str,
) -> tuple[object, object]:
    response = sequence(
        info.post("/info", {"type": "metaAndAssetCtxs", "dex": dex}),
        "metaAndAssetCtxs response",
    )
    if len(response) != 2:
        raise ValueError("metaAndAssetCtxs response must contain metadata and contexts")
    return response[0], response[1]


def _candles(
    info: Hip3InfoProtocol,
    symbols: tuple[str, ...],
    start_ms: int,
    end_ms: int,
) -> dict[str, dict[str, Sequence[object]]]:
    return {
        symbol: {
            timeframe: sequence(
                info.candles_snapshot(symbol, timeframe, start_ms, end_ms),
                f"{symbol} {timeframe} candles",
            )
            for timeframe in _TIMEFRAMES
        }
        for symbol in symbols
    }


def _source_contract(start_ms: int, end_ms: int) -> dict[str, object]:
    return {
        "venue": "hyperliquid_mainnet",
        "api_surface": "official_sdk_public_info",
        "requested_start_ms": start_ms,
        "requested_end_ms": end_ms,
        "public_candle_limit": "latest approximately 5000 rows per interval",
        "credentials_loaded": False,
        "execution_client_constructed": False,
    }


def _timestamp_ms(value: object, label: str) -> int:
    raw = text(value, label)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return int(parsed.timestamp() * 1_000)


def _aware_now(now_fn: Callable[[], datetime]) -> datetime:
    value = now_fn()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("qualification clock must be timezone-aware")
    return value.astimezone(UTC)


def main() -> int:
    """Run one public qualification snapshot and print its path-safe summary."""
    args = build_parser().parse_args()
    try:
        report = run_qualification(args)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"HIP-3 qualification failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "status": report["status"],
                "symbols": report["symbols"],
                "execution_authority": report["execution_authority"],
                "out": str(args.out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
