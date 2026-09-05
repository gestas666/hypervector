#!/usr/bin/env python3
"""Publish a public, report-only HIP-3 liquidity ranking."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Protocol, cast

from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.hip3_liquidity_snapshot import (
    build_hip3_liquidity_snapshot,
)


class PublicInfoProtocol(Protocol):
    """Public Hyperliquid Info surface used by the snapshot."""

    def post(self, path: str, payload: dict[str, object]) -> object:
        """Return one public Info response."""
        ...


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable snapshot parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dex", default="xyz")
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_snapshot(
    args: argparse.Namespace,
    *,
    info: PublicInfoProtocol | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Fetch one exact public response and atomically publish its ranking."""
    dex = _dex(args.dex)
    active_info = info or _official_info(dex)
    metadata, contexts = _metadata_and_contexts(active_info, dex)
    report = build_hip3_liquidity_snapshot(
        dex=dex,
        metadata=metadata,
        contexts=contexts,
        observed_at_utc=now_fn(),
    )
    report["source"] = {
        "venue": "hyperliquid_mainnet",
        "api_surface": "official_sdk_public_info_metaAndAssetCtxs",
        "dex": dex,
    }
    write_atomic_json(Path(args.out), report)
    return report


def _official_info(dex: str) -> PublicInfoProtocol:
    try:
        from hyperliquid.info import Info  # type: ignore[import-untyped]
        from hyperliquid.utils.constants import MAINNET_API_URL  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("official Hyperliquid SDK is unavailable") from exc
    return cast(
        PublicInfoProtocol,
        Info(MAINNET_API_URL, skip_ws=True, perp_dexs=[dex], timeout=20.0),
    )


def _metadata_and_contexts(
    info: PublicInfoProtocol, dex: str
) -> tuple[Mapping[str, object], object]:
    response = info.post("/info", {"type": "metaAndAssetCtxs", "dex": dex})
    if not isinstance(response, Sequence) or isinstance(response, (str, bytes)):
        raise ValueError("metaAndAssetCtxs response must be a sequence")
    if len(response) != 2 or not isinstance(response[0], Mapping):
        raise ValueError("metaAndAssetCtxs response must contain metadata and contexts")
    return response[0], response[1]


def _dex(value: object) -> str:
    if not isinstance(value, str) or not value or ":" in value:
        raise ValueError("dex must be a nonempty unqualified name")
    return value


def main() -> int:
    """Run one public snapshot and print only its path-safe summary."""
    args = build_parser().parse_args()
    try:
        report = run_snapshot(args)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"HIP-3 liquidity snapshot failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "active_market_count": report["active_market_count"],
                "execution_authority": "none",
                "out": str(args.out),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
