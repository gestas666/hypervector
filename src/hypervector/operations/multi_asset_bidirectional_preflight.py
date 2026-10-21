"""Run a public-wallet-only multi-asset transition and sizing preflight."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import sys

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.live.hyperliquid_sdk_factory import HyperliquidSdkFactoryError
from hypervector.live.hyperliquid_parsing import HyperliquidAdapterError
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_read_only_preflight import (
    AssetLedgerExpectation,
    MultiAssetReadOnlyReaderProtocol,
    collect_multi_asset_read_only_preflight,
)
from hypervector.live.multi_asset_read_only_factory import (
    create_multi_asset_read_only_readers,
)
from hypervector.live.multi_asset_retired_transition import (
    apply_retired_asset_reports,
    collect_retired_asset_report,
)
from hypervector.live.cohort_profile_change_approval import (
    ProfileChangeApprovalError,
    validate_profile_change_approval,
)
from hypervector.live.cohort_profile_transition_evidence import (
    validate_profile_transition_archive,
)
from hypervector.live.cohort_transition_drain import CohortTransitionDrainError
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.live_ledger_snapshot import latest_decision_ledger_event
from hypervector.runtime_env import load_wallet_env_if_present

_DEFAULT_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")


def build_parser() -> argparse.ArgumentParser:
    """Build a command surface with no live-arm or mutation options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, required=True, help="candidate profile TOML"
    )
    parser.add_argument(
        "--active-config",
        type=Path,
        required=True,
        help="profile the active cohort run uses",
    )
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
    active_id, active_fingerprint, active_run_id, expectations = _checkpoint_context(
        args.checkpoint,
        active_config,
    )
    _require_candidate_compatibility(config, active_config)
    observed_at = datetime.now(UTC)
    readers, candidate_expectations = _candidate_inputs(
        config,
        active_config,
        expectations,
    )
    report = collect_multi_asset_read_only_preflight(
        config=config,
        readers={symbol: readers[symbol] for symbol in config.symbols},
        ledger_expectations={
            symbol: candidate_expectations[symbol] for symbol in config.symbols
        },
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
    report = _attach_profile_change_evidence(
        report,
        config,
        active_config,
        active_run_id,
    )
    return _publish_preflight(args, report)


def _publish_preflight(
    args: argparse.Namespace,
    report: dict[str, object],
) -> int:
    """Persist, print, and return the report's fail-closed readiness status."""
    if args.output is not None:
        write_atomic_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    portfolio = _mapping(report.get("portfolio"), "preflight portfolio")
    ready = portfolio.get("technically_ready_for_profile_transition")
    if not isinstance(ready, bool):
        raise ValueError("preflight report omitted transition readiness")
    return 0 if ready else 3


def _candidate_inputs(
    config: MultiAssetLiveConfig,
    active_config: MultiAssetLiveConfig,
    expectations: Mapping[str, AssetLedgerExpectation],
) -> tuple[
    dict[str, MultiAssetReadOnlyReaderProtocol],
    dict[str, AssetLedgerExpectation],
]:
    """Build exact readers and ledger expectations for one additive candidate."""
    readers = _readers(config)
    retired_symbols = set(active_config.symbols) - set(config.symbols)
    if retired_symbols:
        active_readers = _readers(active_config)
        readers.update({symbol: active_readers[symbol] for symbol in retired_symbols})
    candidate_expectations = dict(expectations)
    candidate_expectations.update(
        {
            asset.symbol: _addition_expectation(asset)
            for asset in config.assets
            if asset.symbol not in active_config.symbols
        }
    )
    return readers, candidate_expectations


def _readers(
    config: MultiAssetLiveConfig,
) -> dict[str, MultiAssetReadOnlyReaderProtocol]:
    """Construct Info-only readers sharing one retrying public SDK boundary."""
    return create_multi_asset_read_only_readers(config.symbols)


def _checkpoint_context(
    path: Path,
    active_config: MultiAssetLiveConfig,
) -> tuple[str, str, str, dict[str, AssetLedgerExpectation]]:
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
    run_id = _text(run.get("run_id"), "checkpoint run id")
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
    positions = _execution_positions(audit)
    expectations = {
        symbol: _asset_expectation(symbol, assets[symbol], positions)
        for symbol in active_config.symbols
    }
    return profile_id, fingerprint, run_id, expectations


def _require_candidate_compatibility(
    candidate: MultiAssetLiveConfig,
    active: MultiAssetLiveConfig,
) -> None:
    """Require the candidate and active profile to share one venue contract."""
    if (
        candidate.network != active.network
        or candidate.margin_mode != active.margin_mode
    ):
        raise ValueError("candidate and active profile venue contracts differ")


def _profile_change_approval_evidence(
    candidate: MultiAssetLiveConfig,
    active: MultiAssetLiveConfig,
) -> dict[str, object]:
    """Project a change-approval blocker without granting execution authority."""
    try:
        return validate_profile_change_approval(
            active,
            candidate,
            candidate.transition_approval,
        )
    except ProfileChangeApprovalError as exc:
        return {
            "state": "blocked_profile_change",
            "approval_required": True,
            "reason": str(exc),
            "execution_authority": "none",
        }


def _profile_transition_archive_evidence(
    candidate: MultiAssetLiveConfig,
    active: MultiAssetLiveConfig,
    active_run_id: str,
) -> dict[str, object]:
    """Project the exact live-start archive gate without execution authority."""
    if candidate.profile_fingerprint == active.profile_fingerprint:
        return {
            "state": "not_required_unchanged_profile",
            "execution_authority": "none",
            "automatic_order_action": False,
        }
    try:
        return validate_profile_transition_archive(candidate, active, active_run_id)
    except CohortTransitionDrainError as exc:
        return {
            "state": "blocked_profile_transition_archive",
            "reason": str(exc),
            "execution_authority": "none",
            "automatic_order_action": False,
        }


def _attach_profile_change_evidence(
    report: dict[str, object],
    candidate: MultiAssetLiveConfig,
    active: MultiAssetLiveConfig,
    active_run_id: str,
) -> dict[str, object]:
    """Attach approval and archive gates to the reported transition verdict."""
    approval = _profile_change_approval_evidence(candidate, active)
    archive = _profile_transition_archive_evidence(
        candidate,
        active,
        active_run_id,
    )
    blockers = _profile_change_blockers(approval, archive)
    updated = dict(report)
    updated["profile_change_approval"] = approval
    updated["profile_transition_archive"] = archive
    portfolio = dict(_mapping(updated.get("portfolio"), "preflight portfolio"))
    existing = portfolio.get("readiness_reasons", ())
    if not isinstance(existing, (list, tuple)):
        raise ValueError("preflight readiness_reasons must be a sequence")
    portfolio["readiness_reasons"] = (*existing, *blockers)
    portfolio["technically_ready_for_profile_transition"] = (
        bool(portfolio.get("technically_ready_for_profile_transition")) and not blockers
    )
    updated["portfolio"] = portfolio
    return updated


def _profile_change_blockers(
    approval: Mapping[str, object],
    archive: Mapping[str, object],
) -> tuple[str, ...]:
    """Return explicit profile-change reasons that invalidate readiness."""
    blockers: list[str] = []
    for label, evidence in (("approval", approval), ("archive", archive)):
        if str(evidence.get("state", "")).startswith("blocked_"):
            reason = _text(evidence.get("reason"), f"profile change {label} reason")
            blockers.append(reason)
    return tuple(blockers)


def _addition_expectation(asset: AssetLiveConfig) -> AssetLedgerExpectation:
    """Resolve prior ledger truth for an additive asset or a new zero state."""
    path = asset.live_ledger
    if not path.exists():
        return AssetLedgerExpectation(0.0, frozenset())
    row = latest_decision_ledger_event(path, "state_transition")
    payload = _mapping(row.get("payload"), "candidate asset state transition")
    position = _number(payload.get("position_size_signed"), "position size")
    owned = frozenset(
        _oid(value, asset.symbol)
        for key in ("stop_oid", "target_oid", "close_oid")
        if (value := payload.get(key)) is not None
    )
    return AssetLedgerExpectation(position, owned)


def _asset_expectation(
    symbol: str,
    value: object,
    positions: Mapping[str, Mapping[str, object]],
) -> AssetLedgerExpectation:
    row = _mapping(value, f"{symbol} checkpoint health")
    state = row.get("final_state")
    size = _checkpoint_position_size(symbol, row, state, positions)
    oids = _checkpoint_order_ids(symbol, row, state)
    return AssetLedgerExpectation(size, frozenset(oids))


def _checkpoint_position_size(
    symbol: str,
    row: Mapping[str, object],
    state: object,
    positions: Mapping[str, Mapping[str, object]],
) -> float:
    value = row.get("position_size_signed")
    if value is not None:
        return _number(value, f"{symbol} position size")
    if state == "FLAT":
        if symbol in positions:
            raise ValueError(f"{symbol} is FLAT but has an execution position")
        return 0.0
    if state != "OPEN" or symbol not in positions:
        raise ValueError(f"{symbol} is {state!s} but has no execution position")
    return _number(positions[symbol].get("size_signed"), f"{symbol} position size")


def _checkpoint_order_ids(
    symbol: str, row: Mapping[str, object], state: object
) -> tuple[int, ...]:
    raw_oids = row.get("open_order_ids")
    if raw_oids is None:
        stop_oid = row.get("stop_oid")
        return () if stop_oid is None else (_oid(stop_oid, symbol),)
    if not isinstance(raw_oids, list):
        raise ValueError(f"{symbol} open_order_ids must be a list")
    oids = tuple(_oid(item, symbol) for item in raw_oids)
    if len(set(oids)) != len(oids):
        raise ValueError(f"{symbol} open_order_ids contain duplicates")
    if state == "FLAT" and oids:
        raise ValueError(f"{symbol} is FLAT but has open order ids")
    return oids


def _execution_positions(
    audit: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    value = audit.get("execution")
    if value is None:
        return {}
    execution = _mapping(value, "checkpoint execution")
    raw_positions = execution.get("open_positions", [])
    if not isinstance(raw_positions, list):
        raise ValueError("checkpoint open positions must be a list")
    positions: dict[str, Mapping[str, object]] = {}
    for value in raw_positions:
        row = _mapping(value, "checkpoint open position")
        symbol = _text(row.get("symbol"), "checkpoint open position symbol")
        size = _number(row.get("size_signed"), f"{symbol} position size")
        if size == 0.0 or symbol in positions:
            raise ValueError("checkpoint open positions are zero-sized or duplicated")
        positions[symbol] = row
    return positions


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
        HyperliquidSdkFactoryError,
        ValueError,
    ) as exc:
        print(f"multi-asset read-only preflight failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
