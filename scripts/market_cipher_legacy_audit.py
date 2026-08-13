#!/usr/bin/env python3
"""Publish immutable source identity and limitations for recovered MC systems."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Sequence

from hypervector.research.market_cipher_source_contract import (
    audit_market_cipher_sources,
)


_LEGACY_REPRODUCTION: dict[str, object] = {
    "venue": "Binance BTCUSDT OHLCV",
    "timeframe": "30m",
    "validation_start_utc": "2025-03-31T11:00:00+00:00",
    "validation_end_utc": "2026-03-31T11:00:00+00:00",
    "nominal_starting_equity_usd": 10_000.0,
    "trades": 663,
    "wins": 262,
    "losses": 401,
    "win_rate": 0.3952,
    "gross_pnl_usd": 11_900.0,
    "reported_max_drawdown_fraction": 0.591,
    "limitations": [
        "formation discovery reused the four-year source sample",
        "historical ribbon state was calculated from the latest window bar",
        "the MFI slope input was populated from RSI",
        "fees slippage funding liquidation and intrabar stops were omitted",
        "reported final equity includes the pre-validation simulation path",
    ],
}


def _parser() -> argparse.ArgumentParser:
    """Build the report-only audit command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mc-scalper-root", required=True, type=Path)
    parser.add_argument("--market-cipher-cli-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Write one immutable source and legacy-reproduction audit artifact."""
    args = _parser().parse_args(argv)
    output = Path(args.out)
    if output.exists():
        raise FileExistsError(f"Market Cipher audit output exists: {output}")
    report = audit_market_cipher_sources(
        Path(args.mc_scalper_root), Path(args.market_cipher_cli_root)
    )
    report["schema_version"] = "market_cipher_legacy_audit_v1"
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["legacy_reproduction"] = _LEGACY_REPRODUCTION
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote report-only Market Cipher source audit: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
