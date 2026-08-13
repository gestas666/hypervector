"""Read-only CLI reports for exact HIP-3 market evidence."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hypervector.research.hip3_fee_model import Hip3FeeInputs


def add_hip3_research_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register HIP-3 liquidity evidence reporting commands."""
    parser = subparsers.add_parser(
        "research-hip3-liquidity-profile",
        help="Measure point-in-time HIP-3 visible liquidity without execution",
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--notional-usd", type=float, action="append")
    parser.add_argument("--sample-minutes", type=int, default=5)
    parser.add_argument("--maximum-boundary-delay-ms", type=int, default=15_000)
    parser.add_argument("--account-maker-rate", type=float)
    parser.add_argument("--account-taker-rate", type=float)
    parser.add_argument("--active-referral-discount", type=float)
    parser.add_argument("--deployer-fee-scale", type=float)
    parser.add_argument(
        "--growth-mode", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--aligned-quote", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument("--aligned-quote-status")
    parser.add_argument("--fee-evidence-label")
    parser.add_argument("--output", type=Path)
    parser.set_defaults(func=cmd_hip3_liquidity_profile)


def cmd_hip3_liquidity_profile(args: argparse.Namespace) -> int:
    """Build and optionally persist one read-only HIP-3 liquidity profile."""
    import duckdb

    from hypervector.research.hip3_liquidity_profile import build_liquidity_profile

    notionals = tuple(args.notional_usd or (25.0, 50.0, 75.0))
    try:
        fee_inputs = _fee_inputs(args)
        profile = build_liquidity_profile(
            Path(args.database),
            symbol=str(args.symbol),
            notionals_usd=notionals,
            sample_interval_minutes=args.sample_minutes,
            maximum_boundary_delay_ms=args.maximum_boundary_delay_ms,
            fee_inputs=fee_inputs,
        )
        report: dict[str, object] = {
            "ok": True,
            "venue": "hyperliquid",
            "report_only": True,
            "execution_authority": "none",
            "database_path": str(Path(args.database).resolve()),
            "profile": profile.to_dict(),
        }
        rendered = json.dumps(report, indent=2, default=_json_default)
        if args.output is not None:
            _write_exclusive(Path(args.output), rendered)
    except (duckdb.Error, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(rendered)
    return 0


def _fee_inputs(args: argparse.Namespace) -> Hip3FeeInputs | None:
    from hypervector.research.hip3_fee_model import Hip3FeeInputs

    values = (
        args.account_maker_rate,
        args.account_taker_rate,
        args.active_referral_discount,
        args.deployer_fee_scale,
        args.growth_mode,
        args.aligned_quote,
        args.aligned_quote_status,
        args.fee_evidence_label,
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("all HIP-3 fee evidence arguments are required together")
    return Hip3FeeInputs(
        account_maker_rate=args.account_maker_rate,
        account_taker_rate=args.account_taker_rate,
        active_referral_discount=args.active_referral_discount,
        deployer_fee_scale=args.deployer_fee_scale,
        growth_mode=args.growth_mode,
        aligned_quote=args.aligned_quote,
        aligned_quote_status=args.aligned_quote_status,
        evidence_label=args.fee_evidence_label,
    )


def _write_exclusive(path: Path, rendered: str) -> None:
    if path.exists():
        raise FileExistsError(f"liquidity profile already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(rendered)
        handle.write("\n")


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    raise TypeError(f"unsupported liquidity report value: {type(value).__name__}")
