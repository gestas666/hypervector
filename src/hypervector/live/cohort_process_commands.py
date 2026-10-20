"""Headless process commands and checkpoint configuration."""

from __future__ import annotations

from hypervector.live.cohort_checkpoint_identity import require_checkpoint_accounting_epoch as require_checkpoint_accounting_epoch
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Protocol
from hypervector.live.hip3_fresh15_journal_provider import HIP3_INDEX_FRESH15_V3_STRATEGY, HIP3_SNDK_FRESH15_V4_STRATEGY, require_fresh_index_observer, require_fresh_index_observers
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig, MultiAssetLiveConfigError
from hypervector.live.spcx_cash_session_breakout_provider import SPCX_CASH_SESSION_LONG_STRATEGY

CHECKPOINT_OUTPUT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_RESEARCH_DATABASE = Path("data/research/market.duckdb")
_AUDIT_DIR = Path("data/logs/research/bidirectional_cohort")
_RESEARCH_SYNC_INTERVAL_SECONDS = 120

class CohortProcessArguments(Protocol):
    """Typed command fields consumed after launcher argument validation."""

    config: Path
    backtest_lab_root: Path
    resume_transition_drain: bool
    accounting_epoch_bundle: Path | None
    refresh_ms: int
    mode: str
    growth_preflight: Path | None


def backend_command(
    args: CohortProcessArguments, config: MultiAssetLiveConfig
) -> tuple[str, ...]:
    """Build the explicit live backend command."""
    if index_observer_dependency_command(config) is None:
        require_live_provider_dependencies(config)
    command = (
        sys.executable,
        "-m", "hypervector.operations.multi_asset_bidirectional_live",
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
    if any(
        provider.strategy_id == HIP3_SNDK_FRESH15_V4_STRATEGY
        for provider in config.providers
    ):
        require_fresh_index_observer("xyz:SNDK", datetime.now(UTC))


def index_observer_dependency_command(
    config: MultiAssetLiveConfig,
) -> tuple[str, ...] | None:
    """Return an unsigned source supervisor for SPCX and corrected SNDK routes."""
    if any(
        provider.strategy_id == HIP3_SNDK_FRESH15_V4_STRATEGY
        for provider in config.providers
    ):
        return (
            sys.executable,
            "-m", "hypervector.operations.hip3_pressure_dependency_group",
            "--config",
            str(config.source_path),
        )
    required = any(
        provider.strategy_id == SPCX_CASH_SESSION_LONG_STRATEGY
        for provider in config.providers
    )
    if not required:
        return None
    return (
        sys.executable,
        "-m", "hypervector.operations.index_hip3_breakout_shadow_observe",
        "--symbol",
        "xyz:SPCX",
    )




def observer_command(args: CohortProcessArguments) -> tuple[str, ...]:
    """Build the execution-incapable observer command."""
    return (
        sys.executable,
        "-m", "hypervector.operations.multi_asset_bidirectional_observe",
        "--config",
        str(args.config),
        "--backtest-lab-root",
        str(args.backtest_lab_root),
    )


def launch_checkpoint_command(
    args: CohortProcessArguments,
    config: MultiAssetLiveConfig,
    staged_config: MultiAssetLiveConfig | None,
) -> tuple[str, ...]:
    """Keep live/monitor checkpoint arguments separate from observer projection."""
    if args.mode in {"live", "monitor"}:
        return checkpoint_command(
            config,
            staged_config=staged_config,
            accounting_epoch_bundle=args.accounting_epoch_bundle,
        )
    if args.mode == "observe":
        return observer_checkpoint_command(config)
    raise MultiAssetLiveConfigError(f"unsupported cohort mode: {args.mode}")


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
        "-m", "hypervector.operations.multi_asset_bidirectional_live_checkpoint",
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
        "--disable-asymmetric-forward-observer",
    )
    if accounting_epoch_bundle is not None:
        command = (*command, "--accounting-epoch-bundle", str(accounting_epoch_bundle))
    return command


def observer_checkpoint_command(config: MultiAssetLiveConfig) -> tuple[str, ...]:
    """Build the observer-only bounded checkpoint command."""
    return (
        sys.executable,
        "-m", "hypervector.operations.multi_asset_bidirectional_observer_checkpoint",
        "--decisions",
        str(config.cohort_ledger),
        "--out",
        str(CHECKPOINT_OUTPUT),
    )


def audit_command(config: MultiAssetLiveConfig) -> tuple[str, ...]:
    """Build the immutable stopped-live audit command."""
    return (
        sys.executable,
        "-m", "hypervector.operations.multi_asset_bidirectional_live_audit",
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
        "-m", "hypervector.operations.multi_asset_bidirectional_observer_audit",
        "--decisions",
        str(config.cohort_ledger),
        "--out-dir",
        str(_AUDIT_DIR),
    )
