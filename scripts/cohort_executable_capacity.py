"""Publish offline executable-capacity sensitivities from a pinned venue snapshot."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_config_parsing import (
    mapping,
    mapping_rows,
    number,
    text,
)
from hypervector.research.cohort_executable_capacity import (
    CapacityScenario,
    build_executable_capacity,
)


def build_parser() -> argparse.ArgumentParser:
    """Require explicit source artifacts and optional declared adverse costs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--venue-snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--slippage-bps", type=float, default=0)
    parser.add_argument("--funding-bps", type=float, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Bind configuration and source bytes before immutable report publication."""
    args = build_parser().parse_args(argv)
    config_evidence = file_evidence(args.config)
    config = load_multi_asset_live_config(args.config, mode="observe")
    raw = args.venue_snapshot.read_bytes()
    snapshot = mapping(json.loads(raw), "venue snapshot")
    identity = mapping(snapshot.get("identity"), "snapshot identity")
    if identity.get("candidate_profile_fingerprint") != config.profile_fingerprint:
        raise ValueError("venue snapshot profile fingerprint does not match config")
    portfolio = mapping(snapshot.get("portfolio"), "snapshot portfolio")
    observed_at = _observation_time(snapshot)
    report = build_executable_capacity(
        config,
        number(portfolio, "sizing_reference_equity_usd"),
        _fees(snapshot),
        scenarios=(
            CapacityScenario("stop_and_fees", 0, 0),
            CapacityScenario(
                "declared_adverse_costs", args.slippage_bps, args.funding_bps
            ),
        ),
    )
    if file_evidence(args.config) != config_evidence:
        raise ValueError("configuration changed while building capacity report")
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "venue_observed_at_utc": observed_at,
            "evidence": {
                "config": {"path": str(args.config.resolve()), **config_evidence},
                "venue_snapshot": {
                    "path": str(args.venue_snapshot.resolve()),
                    "sha256": sha256(raw).hexdigest(),
                    "bytes": len(raw),
                },
                "generator": {
                    "path": str(Path(__file__).resolve()),
                    **file_evidence(Path(__file__)),
                },
            },
        }
    )
    write_immutable_json(args.out, report)
    print(
        json.dumps({"output": str(args.out.resolve()), "capacity": report["capacity"]})
    )
    return 0


def _fees(snapshot: Mapping[str, object]) -> dict[str, float]:
    fees: dict[str, float] = {}
    for asset in mapping_rows(snapshot.get("assets"), "snapshot assets"):
        symbol = text(asset, "symbol")
        if symbol in fees:
            raise ValueError(f"duplicate venue snapshot asset: {symbol}")
        venue = mapping(asset.get("venue"), "snapshot venue")
        fee = venue.get("one_way_taker_fee_bps")
        if isinstance(fee, bool) or not isinstance(fee, (int, float)):
            raise ValueError(f"missing or nonnumeric taker fee: {symbol}")
        fees[symbol] = float(fee)
    return fees


def _observation_time(snapshot: Mapping[str, object]) -> str:
    value = text(snapshot, "observed_at_utc")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("venue observation timestamp requires a timezone")
    return parsed.astimezone(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
