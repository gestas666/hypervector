"""Public workflow and startup contracts for the unified command line."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from hypervector.cli import build_parser, main


@pytest.mark.parametrize(
    ("grouped", "legacy"),
    [
        (["research", "backtest"], ["backtest"]),
        (["research", "autotune"], ["autotune"]),
        (["nautilus", "run", "--path", "bundle"], ["phase2-run", "--path", "bundle"]),
        (["paper", "check"], ["paper-check"]),
        (["paper", "shadow-run"], ["hypervelocity-shadow-run"]),
        (["live", "check"], ["live-check"]),
        (["cohort", "live"], ["cohort-live"]),
        (["data", "history"], ["history"]),
        (
            [
                "archive",
                "trade-fetch",
                "--start",
                "2026-01-01T00:00:00Z",
                "--end",
                "2026-01-02T00:00:00Z",
            ],
            [
                "oxa-trade-fetch",
                "--start",
                "2026-01-01T00:00:00Z",
                "--end",
                "2026-01-02T00:00:00Z",
            ],
        ),
    ],
)
def test_grouped_commands_preserve_workflow_arguments(
    grouped: list[str], legacy: list[str]
) -> None:
    """A focused name selects the same service and options as its flat alias."""
    parser = build_parser()
    grouped_args = vars(parser.parse_args(grouped))
    legacy_args = vars(parser.parse_args(legacy))
    for values in (grouped_args, legacy_args):
        values.pop("group", None)
    assert grouped_args == legacy_args


def test_status_does_not_create_a_data_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Inventory is an observation, even when its data root does not exist."""
    root = tmp_path / "absent"
    assert main(["--data-root", str(root), "status"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["root"] == str(root)
    assert not root.exists()
    assert {"vectorbt", "nautilus", "hyperliquid", "0xarchive", "karpathy"} <= set(
        result["capabilities"]
    )


def test_help_does_not_import_engines_or_dataframes() -> None:
    """Discovery must work without initializing heavy optional engines."""
    program = (
        "import sys; from hypervector.cli import build_parser; "
        "build_parser().format_help(); "
        "assert not {'pandas', 'vectorbt', 'nautilus_trader'} & sys.modules.keys()"
    )
    subprocess.run([sys.executable, "-c", program], check=True, timeout=15)


def test_data_root_is_accepted_after_a_group() -> None:
    """Operators can scope a workflow at either side of the group name."""
    args = build_parser().parse_args(["paper", "--data-root", "isolated", "check"])
    assert args.data_root == "isolated"


def test_autotuning_defaults_to_the_retained_karpathy_sampler() -> None:
    """The default optimizer must not depend on an undeclared Optuna install."""
    assert build_parser().parse_args(["autotune"]).sampler == "karpathy"


def test_status_does_not_initialize_engine_packages() -> None:
    """Installed capability metadata does not need a paper or live runner import."""
    program = (
        "import sys; from hypervector.cli import main; main(['status']); "
        "assert not {'pandas', 'vectorbt', 'nautilus_trader'} & sys.modules.keys()"
    )
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        timeout=15,
        stdout=subprocess.DEVNULL,
    )
