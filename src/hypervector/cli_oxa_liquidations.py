"""CLI boundary for bounded 0xArchive liquidation acquisition."""

from __future__ import annotations

import argparse
import os

from hypervector.data.oxa_api import OxaHistoryError


def cmd_oxa_liquidation_fetch(args: argparse.Namespace) -> int:
    """Acquire one explicitly bounded Hyperliquid liquidation window."""
    from hypervector.cli_oxa import (
        _print_failure,
        _print_success,
        acquisition_options,
    )
    from hypervector.data.oxa_liquidations import (
        OxaLiquidationRequest,
        acquire_and_store_liquidations,
    )

    try:
        request = OxaLiquidationRequest(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            limit=args.limit,
            max_pages=args.max_pages,
            timeout_seconds=args.timeout,
        )
        report = acquire_and_store_liquidations(
            data_root=args.data_root,
            api_key=os.environ.get("OXA_API_KEY", ""),
            request=request,
            **acquisition_options(args),
        )
    except (OxaHistoryError, ValueError, OSError) as exc:
        return _print_failure(exc, args)
    return _print_success(report)
