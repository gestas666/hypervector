"""Command construction for the bidirectional cohort TUI supervisor."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Protocol

from hypervector.live.eth_breakout_transfer_provider import (
    ETH_BREAKOUT_TRANSFER_STRATEGY,
)
from hypervector.live.hype_breakout_cohort_provider import (
    HYPE_BREAKOUT_COHORT_STRATEGY,
)
from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
    require_fresh_index_observer,
    require_fresh_index_observers,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
)
from hypervector.live.spcx_cash_session_breakout_provider import (
    SPCX_CASH_SESSION_LONG_STRATEGY,
)
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

CHECKPOINT_OUTPUT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_HYPE_L2_OBSERVER_STATUS = Path(
    "data/runtime/research/hype_l2_ridge_observer_latest.json"
)
_HIP3_ROSTER_STATUS = Path("data/runtime/research/hip3_roster_latest.json")
_RESEARCH_DATABASE = Path("data/research/market.duckdb")
_AUDIT_DIR = Path("data/logs/research/bidirectional_cohort")
_V25_RESEARCH_PROFILE_ID = "multi_asset_bidirectional_complete_portfolio_canary_v25"
_V25_RESEARCH_PROFILE_FINGERPRINT = (
    "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc"
)
_V25_OPPORTUNITY_MATRIX = Path(
    "data/logs/research/bidirectional_cohort/"
    "v25_execution_opportunity_matrix_exlargest_20260808T2216Z.json"
)
_V25_ASYMMETRIC_JOURNAL = Path(
    "docs/research-journal/cohort-asymmetric-shared-portfolio-v1.json"
)
_V25_SUPPLEMENTAL_MATRICES = (
    Path("data/runtime/bidirectional_cohort/latest_spcx_swing_pivot_challenger.json"),
    Path(
        "data/runtime/bidirectional_cohort/"
        "latest_sol_breakout_continuation_challenger.json"
    ),
    Path("data/runtime/bidirectional_cohort/latest_sndk_swing_pivot_challenger.json"),
)
_RESEARCH_SYNC_INTERVAL_SECONDS = 120
_ELIGIBLE_POLICY_FORWARD_PROFILE_IDS = frozenset(
    {
        "multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11",
        "multi_asset_bidirectional_evidence_routed_candidate_v18",
        "multi_asset_bidirectional_evidence_routed_retest_observer_candidate_v21",
    }
)


class CohortTuiArguments(Protocol):
    """Typed command fields consumed after launcher argument validation."""

    config: Path
    backtest_lab_root: Path
    resume_transition_drain: bool
    accounting_epoch_bundle: Path | None
    refresh_ms: int
    mode: str
    growth_preflight: Path | None


@dataclass(frozen=True)
class MultiAssetTuiLaunch:
    """Resolved backend/TUI commands and lifecycle configuration."""

    config: MultiAssetLiveConfig
    staged_config: MultiAssetLiveConfig | None
    backend_command: tuple[str, ...] | None
    checkpoint_command: tuple[str, ...] | None
    tui_command: tuple[str, ...]
    audit_command: tuple[str, ...] | None
    startup_timeout_seconds: float
    accounting_epoch: CohortAccountingEpoch | None = None
    dependency_command: tuple[str, ...] | None = None


def backend_command(
    args: CohortTuiArguments, config: MultiAssetLiveConfig
) -> tuple[str, ...]:
    """Build the explicit live backend command."""
    if index_observer_dependency_command(config) is None:
        require_live_provider_dependencies(config)
    command = (
        sys.executable,
        "scripts/multi_asset_bidirectional_live.py",
        "--config",
        str(args.config),
        "--backtest-lab-root",
        str(args.backtest_lab_root),
        "--enabled",
        "--i-accept-live-risk",
    )
    if args.resume_transition_drain:
        command += ("--resume-transition-drain",)
    if args.accounting_epoch_bundle is not None:
        command += ("--accounting-epoch-bundle", str(args.accounting_epoch_bundle))
    return command


def require_live_provider_dependencies(config: MultiAssetLiveConfig) -> None:
    """Fail closed when a configured external signal dependency is stale."""
    if any(
        provider.strategy_id == HIP3_INDEX_FRESH15_V3_STRATEGY
        for provider in config.providers
    ):
        require_fresh_index_observers(datetime.now(UTC))
    if any(
        provider.strategy_id == SPCX_CASH_SESSION_LONG_STRATEGY
        for provider in config.providers
    ):
        require_fresh_index_observer("xyz:SPCX", datetime.now(UTC))


def index_observer_dependency_command(
    config: MultiAssetLiveConfig,
) -> tuple[str, ...] | None:
    """Return the unsigned SPCX observer supervisor needed by V79."""
    required = any(
        provider.strategy_id == SPCX_CASH_SESSION_LONG_STRATEGY
        for provider in config.providers
    )
    if not required:
        return None
    return (
        sys.executable,
        "scripts/index_hip3_breakout_shadow_observe.py",
        "--symbol",
        "xyz:SPCX",
    )


def require_checkpoint_accounting_epoch(
    document: object,
    epoch: CohortAccountingEpoch,
) -> None:
    """Reject a checkpoint whose portfolio view uses another epoch."""
    if not isinstance(document, Mapping):
        raise MultiAssetLiveConfigError("checkpoint accounting epoch differs")
    audit = document.get("audit")
    archive = audit.get("portfolio_archive") if isinstance(audit, Mapping) else None
    observed = archive.get("accounting_epoch") if isinstance(archive, Mapping) else None
    if observed != epoch.to_dict():
        raise MultiAssetLiveConfigError("checkpoint accounting epoch differs")


def observer_command(args: CohortTuiArguments) -> tuple[str, ...]:
    """Build the execution-incapable observer command."""
    return (
        sys.executable,
        "scripts/multi_asset_bidirectional_observe.py",
        "--config",
        str(args.config),
        "--backtest-lab-root",
        str(args.backtest_lab_root),
    )


def tui_command(
    args: CohortTuiArguments,
    config: MultiAssetLiveConfig,
    ledger: Path,
    *,
    include_checkpoint: bool,
) -> tuple[str, ...]:
    """Build the read-only Rust cockpit command."""
    command = _tui_base_command(args)
    lifecycle = ("--detached-lifecycle",) if args.mode == "monitor" else ()
    checkpoint = (
        ("--cohort-checkpoint", str(CHECKPOINT_OUTPUT)) if include_checkpoint else ()
    )
    growth = (
        ("--growth-preflight", str(args.growth_preflight))
        if args.growth_preflight is not None
        else ()
    )
    hype_l2_observer = (
        (
            "--hype-l2-observer-status",
            str(_HYPE_L2_OBSERVER_STATUS),
        )
        if any(
            provider.strategy_id == HYPE_BREAKOUT_COHORT_STRATEGY
            for provider in config.providers
        )
        else ()
    )
    return (
        *command,
        *lifecycle,
        *checkpoint,
        *growth,
        *hype_l2_observer,
        "--hip3-roster-status",
        str(_HIP3_ROSTER_STATUS),
        "--cohort-command-inbox",
        str(ledger.parent / "operator_commands"),
        "--backend-ledger",
        str(ledger),
    )


def _tui_base_command(args: CohortTuiArguments) -> tuple[str, ...]:
    return (
        "cargo",
        "run",
        "--release",
        "-p",
        "hypervector-tui",
        "--bin",
        "tui-regime-detector",
        "--",
        "--symbol",
        "MULTI",
        "--timeframe",
        "1m",
        "--live",
        "--refresh-ms",
        str(args.refresh_ms),
        "--initial-tab",
        "2" if args.mode == "observe" else "1",
    )


def checkpoint_command(
    config: MultiAssetLiveConfig,
    *,
    staged_config: MultiAssetLiveConfig | None = None,
    accounting_epoch_bundle: Path | None = None,
) -> tuple[str, ...]:
    """Build the report-only live checkpoint command."""
    generation = staged_config or config
    command = (
        sys.executable,
        "scripts/multi_asset_bidirectional_live_checkpoint.py",
        "--ledger-root",
        str(config.cohort_ledger.parent),
        "--out",
        str(CHECKPOINT_OUTPUT),
        "--config",
        str(generation.source_path),
        "--research-database",
        str(_RESEARCH_DATABASE),
        "--research-sync-interval-seconds",
        str(_RESEARCH_SYNC_INTERVAL_SECONDS),
        "--venue-portfolio",
        "--current-run-only",
        *_profile_bound_research_args(config),
    )
    if _eligible_policy_forward(config):
        command = (*command, "--eligible-policy-forward")
    if accounting_epoch_bundle is not None:
        command = (*command, "--accounting-epoch-bundle", str(accounting_epoch_bundle))
    return command


def _eligible_policy_forward(config: MultiAssetLiveConfig) -> bool:
    return config.profile_id in _ELIGIBLE_POLICY_FORWARD_PROFILE_IDS and any(
        provider.strategy_id == ETH_BREAKOUT_TRANSFER_STRATEGY
        for provider in config.providers
    )


def _profile_bound_research_args(config: MultiAssetLiveConfig) -> tuple[str, ...]:
    if (
        config.profile_id != _V25_RESEARCH_PROFILE_ID
        or config.profile_fingerprint != _V25_RESEARCH_PROFILE_FINGERPRINT
    ):
        return ("--disable-asymmetric-forward-observer",)
    args = (
        "--opportunity-matrix",
        str(_V25_OPPORTUNITY_MATRIX),
        "--asymmetric-forward-journal",
        str(_V25_ASYMMETRIC_JOURNAL),
    )
    supplemental = tuple(
        value
        for path in _V25_SUPPLEMENTAL_MATRICES
        for value in ("--supplemental-opportunity-matrix", str(path))
    )
    return (*args, *supplemental)


def observer_checkpoint_command(config: MultiAssetLiveConfig) -> tuple[str, ...]:
    """Build the observer-only bounded checkpoint command."""
    return (
        sys.executable,
        "scripts/multi_asset_bidirectional_observer_checkpoint.py",
        "--decisions",
        str(config.cohort_ledger),
        "--out",
        str(CHECKPOINT_OUTPUT),
    )


def audit_command(config: MultiAssetLiveConfig) -> tuple[str, ...]:
    """Build the immutable stopped-live audit command."""
    return (
        sys.executable,
        "scripts/multi_asset_bidirectional_live_audit.py",
        "--ledger-root",
        str(config.cohort_ledger.parent),
        "--history-scope",
        "current-run",
        "--out-dir",
        str(_AUDIT_DIR),
    )


def observer_audit_command(config: MultiAssetLiveConfig) -> tuple[str, ...]:
    """Build the immutable observer audit command."""
    return (
        sys.executable,
        "scripts/multi_asset_bidirectional_observer_audit.py",
        "--decisions",
        str(config.cohort_ledger),
        "--out-dir",
        str(_AUDIT_DIR),
    )
