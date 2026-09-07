"""Build an execution-incapable candidate cockpit with isolated output identity."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from hypervector.live.cohort_tui_commands import (
    MultiAssetTuiLaunch,
    observer_audit_command,
    observer_checkpoint_command,
    observer_command,
    tui_command,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root

_REFRESH_MS = 500
_STARTUP_TIMEOUT_SECONDS = 900.0


@dataclass(frozen=True)
class _PreviewArguments:
    config: Path
    backtest_lab_root: Path
    mode: Literal["observe"] = field(default="observe", init=False)
    refresh_ms: int = _REFRESH_MS
    growth_preflight: Path | None = None
    resume_transition_drain: bool = False
    accounting_epoch_bundle: Path | None = None


def build_candidate_preview(
    config_path: Path, output_root: Path, backtest_lab_root: Path
) -> MultiAssetTuiLaunch:
    """Bind the observer, checkpoint, display and audit to one separate directory."""
    args = _PreviewArguments(config_path, backtest_lab_root)
    config = with_observer_ledger_root(
        load_multi_asset_live_config(config_path, mode="observe"), output_root
    )
    checkpoint = output_root / "checkpoint.json"
    return MultiAssetTuiLaunch(
        config=config,
        staged_config=None,
        backend_command=(*observer_command(args), "--ledger-root", str(output_root)),
        checkpoint_command=_replace_option(
            observer_checkpoint_command(config), "--out", checkpoint
        ),
        tui_command=_replace_option(
            tui_command(args, config, config.cohort_ledger, include_checkpoint=True),
            "--cohort-checkpoint",
            checkpoint,
        ),
        audit_command=_replace_option(
            observer_audit_command(config), "--out-dir", output_root / "audits"
        ),
        startup_timeout_seconds=_STARTUP_TIMEOUT_SECONDS,
    )


def _replace_option(
    command: tuple[str, ...], option: str, value: Path
) -> tuple[str, ...]:
    index = command.index(option) + 1
    return (*command[:index], str(value), *command[index + 1 :])
