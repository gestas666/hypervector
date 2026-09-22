"""Freeze unsigned native inputs for the V90 out-of-sample replay window.

Report-only. execution_authority: none. No credentials, no order client.

The frozen 2026-09-07 selection screen ends at 2026-09-06T23:45Z. This captures
the strictly later interval so the roster can be scored on tape that did not
exist when the roster was chosen.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

from hypervector.data.hl import (
    bars_from_hl_payload,
    fetch_hl_funding_pages,
    funding_from_hl_payload,
)
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_transfer_sources import validated_official_funding

SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SPCX",
    "xyz:SP500",
    "xyz:SNDK",
    "xyz:BRENTOIL",
)
START = pd.Timestamp("2026-09-07T00:00:00Z")
END = pd.Timestamp("2026-09-20T00:00:00Z")
INFO_URL = "https://api.hyperliquid.xyz/info"


def capture_symbol(symbol: str, output: Path) -> dict[str, object]:
    """Capture exact raw public payloads and require complete bounded chronology."""
    directory = output / symbol.replace(":", "_")
    directory.mkdir(parents=True, exist_ok=False)
    with requests.Session() as session:
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": symbol,
                "interval": "15m",
                "startTime": int(START.timestamp() * 1000),
                "endTime": int(END.timestamp() * 1000),
            },
        }
        response = session.post(INFO_URL, json=payload, timeout=30)
        response.raise_for_status()
        raw = response.json()
        if not isinstance(raw, list):
            raise ValueError(f"{symbol}: native candle response must be a list")
        pages = fetch_hl_funding_pages(
            symbol,
            start_time=START,
            end_time=END - pd.Timedelta(milliseconds=1),
            session=session,
        )
    write_immutable_json(
        directory / "raw.json",
        {
            "symbol": symbol,
            "request": payload,
            "candles": raw,
            "funding_pages": pages,
            "observed_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "execution_authority": "none",
        },
    )
    return _publish_inputs(
        symbol,
        directory,
        bars_from_hl_payload(raw).set_index("timestamp"),
        funding_from_hl_payload([row for page in pages for row in page]),
    )


def _publish_inputs(
    symbol: str,
    directory: Path,
    bars: pd.DataFrame,
    funding: pd.DataFrame,
) -> dict[str, object]:
    """Validate complete native chronology before publishing normalized inputs."""
    bars = bars.loc[(bars.index >= START) & (bars.index < END)]
    expected = pd.date_range(START, END, freq="15min", inclusive="left")
    if not bars.index.as_unit("ns").equals(expected.as_unit("ns")):
        raise ValueError(
            f"{symbol}: expected {len(expected)} ordered native bars, got {len(bars)}"
        )
    rates = validated_official_funding(funding)
    expected_rates = pd.date_range(START, END, freq="h", inclusive="left")
    if not rates.index.as_unit("ns").equals(expected_rates.as_unit("ns")):
        raise ValueError(
            f"{symbol}: native hourly funding does not cover the requested interval"
        )
    bars.to_parquet(directory / "bars.parquet")
    funding.to_parquet(directory / "funding.parquet", index=False)
    result = {
        "symbol": symbol,
        "bar_rows": len(bars),
        "funding_rows": len(rates),
        "evidence": {
            str(path): file_evidence(path) for path in sorted(directory.iterdir())
        },
    }
    print(
        {key: value for key, value in result.items() if key != "evidence"}, flush=True
    )
    return result


def main() -> None:
    """Publish one immutable input manifest without credentials or order clients."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(capture_symbol, symbol, output) for symbol in SYMBOLS]
        rows = [future.result() for future in futures]
    write_immutable_json(
        output / "manifest.json",
        {
            "schema_version": 1,
            "execution_authority": "none",
            "symbols": rows,
            "source": "official_hyperliquid_public_info",
            "start_utc": START.isoformat(),
            "end_exclusive_utc": END.isoformat(),
            "bar_interval_minutes": 15,
            "credentials_loaded": False,
            "execution_client_constructed": False,
            "selection_screen_end_exclusive_utc": "2026-09-07T00:00:00+00:00",
            "generator": {
                "path": str(Path(__file__).resolve()),
                **file_evidence(Path(__file__)),
            },
        },
    )


if __name__ == "__main__":
    main()
