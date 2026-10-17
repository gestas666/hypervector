"""Public workflow and startup contracts for the unified command line."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from hypervector.cli import build_parser, main


def test_status_does_not_create_a_data_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Inventory is an observation, even when its data root does not exist."""
    root = tmp_path / "absent"
    assert main(["--data-root", str(root), "system", "status"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["root"] == str(root)
    assert not root.exists()
    assert {"vectorbt", "nautilus", "hyperliquid", "0xarchive", "karpathy"} <= set(
        result["capabilities"]
    )


def test_status_shortcut_matches_system_status() -> None:
    """The documented 'status' shortcut selects the same command."""
    parser = build_parser()
    assert vars(parser.parse_args(["status"])) == vars(
        parser.parse_args(["system", "status"])
    )


def test_data_root_is_accepted_after_a_group() -> None:
    """Operators can scope a workflow at either side of the group name."""
    args = build_parser().parse_args(["paper", "--data-root", "isolated", "check"])
    assert args.data_root == "isolated"


def test_autotuning_defaults_to_the_retained_karpathy_sampler() -> None:
    """The default optimizer must not depend on an undeclared Optuna install."""
    assert build_parser().parse_args(["tune", "strategy"]).sampler == "karpathy"


def test_status_does_not_initialize_engine_packages() -> None:
    """Installed capability metadata does not need a paper or live runner import."""
    program = (
        "import sys; from hypervector.cli import main; main(['system', 'status']); "
        "assert not {'pandas', 'vectorbt', 'nautilus_trader'} & sys.modules.keys()"
    )
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        timeout=15,
        stdout=subprocess.DEVNULL,
    )
