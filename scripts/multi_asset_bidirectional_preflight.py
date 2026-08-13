#!/usr/bin/env python3
"""Run a public-wallet-only multi-asset transition and sizing preflight."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import sys
from threading import RLock

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.live.hyperliquid_perp_reader import HyperliquidPerpReader
from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
    require_fresh_index_observers,
)
from hypervector.live.hyperliquid_sol_factory import (
    OfficialSolReadOnlySdkBuilder,
    SolSdkFactoryError,
)
from hypervector.live.hyperliquid_sol_parsing import (
    HyperliquidAdapterError,
    validate_address,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_read_only_preflight import (
    AssetLedgerExpectation,
    MultiAssetReadOnlyReaderProtocol,
    collect_multi_asset_read_only_preflight,
)
from hypervector.live.multi_asset_retired_transition import (
    apply_retired_asset_reports,
    collect_retired_asset_report,
)
from hypervector.live.perp_venue_identity import (
    configured_perp_dexes,
    parse_perp_venue_identity,
)
from hypervector.live.policy import SECRET_ENV_WALLET
from hypervector.live.serialized_hyperliquid_clients import (
    SerializedHyperliquidInfo,
)
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.runtime_env import load_wallet_env_if_present

_DEFAULT_CONFIG = Path(
    "configs/multi_asset_bidirectional_evidence_roster_canary_v36.toml"
)
_DEFAULT_ACTIVE_CONFIG = Path(
    "configs/multi_asset_bidirectional_all_live_canary_v35.toml"
)
_DEFAULT_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")


def build_parser() -> argparse.ArgumentParser:
    """Build a command surface with no live-arm or mutation options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    parser.add_argument("--active-config", type=Path, default=_DEFAULT_ACTIVE_CONFIG)
    parser.add_argument("--checkpoint", type=Path, default=_DEFAULT_CHECKPOINT)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--sizing-equity-usd",
        type=float,
        help="walk candidate sizing at this report-only equity scenario",
    )
    return parser


def run_preflight(args: argparse.Namespace) -> int:
    """Collect and optionally persist one sanitized point-in-time report."""
    config = load_multi_asset_live_config(args.config, mode="observe")
    active_config = load_multi_asset_live_config(args.active_config, mode="observe")
    active_id, active_fingerprint, expectations = _checkpoint_context(
        args.checkpoint,
        active_config,
    )
    _require_candidate_subset(config, active_config)
    observed_at = datetime.now(UTC)
    if any(
        provider.strategy_id == HIP3_INDEX_FRESH15_V3_STRATEGY
        for provider in config.providers
    ):
        require_fresh_index_observers(observed_at)
    readers = _readers(active_config)
    report = collect_multi_asset_read_only_preflight(
        config=config,
        readers={symbol: readers[symbol] for symbol in config.symbols},
        ledger_expectations={symbol: expectations[symbol] for symbol in config.symbols},
        active_profile_id=active_id,
        active_profile_fingerprint=active_fingerprint,
        observed_at=observed_at,
        sizing_reference_equity_usd=args.sizing_equity_usd,
    )
    retired = tuple(
        collect_retired_asset_report(
            asset,
            readers[asset.symbol],
            expectations[asset.symbol],
        )
        for asset in active_config.assets
        if asset.symbol not in config.symbols
    )
    report = apply_retired_asset_reports(report, retired)
    if args.output is not None:
        write_atomic_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    portfolio = _mapping(report.get("portfolio"), "preflight portfolio")
    ready = portfolio.get("technically_ready_for_profile_transition")
    if not isinstance(ready, bool):
        raise ValueError("preflight report omitted transition readiness")
    return 0 if ready else 3


def _readers(
    config: MultiAssetLiveConfig,
) -> dict[str, MultiAssetReadOnlyReaderProtocol]:
    """Construct Info-only readers sharing one retrying public SDK boundary."""
    address = validate_address((os.environ.get(SECRET_ENV_WALLET) or "").strip())
    raw = OfficialSolReadOnlySdkBuilder().build(
        perp_dexes=configured_perp_dexes(config.symbols)
    )
    info = SerializedHyperliquidInfo(raw, RLock())
    readers: dict[str, MultiAssetReadOnlyReaderProtocol] = {}
    for symbol in config.symbols:
        identity = parse_perp_venue_identity(symbol)
        readers[symbol] = HyperliquidPerpReader(
            info=info,
            account_address=address,
            symbol=identity.symbol,
            perp_dex=identity.perp_dex,
        )
    return readers


def _checkpoint_context(
    path: Path,
    active_config: MultiAssetLiveConfig,
) -> tuple[str, str, dict[str, AssetLedgerExpectation]]:
    """Load exact active-profile and durable asset expectations from checkpoint."""
    document = _mapping(
        json.loads(path.read_text(encoding="utf-8")),
        "checkpoint",
    )
    contract = _mapping(document.get("checkpoint_contract"), "checkpoint contract")
    if contract.get("report_only") is not True:
        raise ValueError("checkpoint must be explicitly report-only")
    if contract.get("execution_authority") != "none":
        raise ValueError("checkpoint must have no execution authority")
    audit = _mapping(document.get("audit"), "checkpoint audit")
    run = _mapping(audit.get("run"), "checkpoint run")
    profile_id = _text(run.get("profile_id"), "checkpoint profile id")
    fingerprint = _fingerprint(run.get("profile_fingerprint"))
    if profile_id != active_config.profile_id:
        raise ValueError("checkpoint profile id differs from --active-config")
    if fingerprint != active_config.profile_fingerprint:
        raise ValueError("checkpoint profile fingerprint differs from --active-config")
    _require_symbol_coverage(run.get("symbols"), active_config.symbols)
    health = _mapping(audit.get("health"), "checkpoint health")
    assets = _mapping(health.get("assets"), "checkpoint health assets")
    if set(assets) != set(active_config.symbols):
        raise ValueError("checkpoint health asset coverage differs from config")
    expectations = {
        symbol: _asset_expectation(symbol, assets[symbol])
        for symbol in active_config.symbols
    }
    return profile_id, fingerprint, expectations


def _require_candidate_subset(
    candidate: MultiAssetLiveConfig,
    active: MultiAssetLiveConfig,
) -> None:
    """Require a same-venue candidate whose additions are separately qualified."""
    if (
        candidate.network != active.network
        or candidate.margin_mode != active.margin_mode
    ):
        raise ValueError("candidate and active profile venue contracts differ")
    additions = set(candidate.symbols) - set(active.symbols)
    if additions:
        raise ValueError(
            "candidate introduces assets absent from active checkpoint: "
            + ",".join(sorted(additions))
        )


def _asset_expectation(
    symbol: str,
    value: object,
) -> AssetLedgerExpectation:
    row = _mapping(value, f"{symbol} checkpoint health")
    size = _number(row.get("position_size_signed"), f"{symbol} position size")
    raw_oids = row.get("open_order_ids")
    if not isinstance(raw_oids, list):
        raise ValueError(f"{symbol} open_order_ids must be a list")
    oids = tuple(_oid(item, symbol) for item in raw_oids)
    if len(set(oids)) != len(oids):
        raise ValueError(f"{symbol} open_order_ids contain duplicates")
    return AssetLedgerExpectation(size, frozenset(oids))


def _require_symbol_coverage(value: object, expected: tuple[str, ...]) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("checkpoint symbols must be a string list")
    if len(set(value)) != len(value) or set(value) != set(expected):
        raise ValueError("checkpoint symbol coverage differs from config")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    return value


def _fingerprint(value: object) -> str:
    text = _text(value, "checkpoint profile fingerprint")
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError("checkpoint profile fingerprint must be lowercase sha256")
    return text


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _oid(value: object, symbol: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{symbol} open order ids must be positive integers")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Load only public wallet identity and report bounded preflight failures."""
    load_wallet_env_if_present()
    try:
        return run_preflight(build_parser().parse_args(argv))
    except (
        ClientError,
        FileNotFoundError,
        HyperliquidAdapterError,
        json.JSONDecodeError,
        MultiAssetLiveConfigError,
        OSError,
        RequestException,
        ServerError,
        SolSdkFactoryError,
        ValueError,
    ) as exc:
        print(f"multi-asset read-only preflight failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
