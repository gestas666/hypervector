"""Exercise the independent monitor entrypoints without an inherited repository import path."""

from pathlib import Path
import subprocess
import sys

import pytest

from hypervector.cli import build_parser
from hypervector.cli_cohort import cohort_command

ROOT = Path(__file__).resolve().parents[1]


def clean_environment() -> dict[str, str]:
    """Select this checkout's package without adding its scripts namespace or credentials."""
    return {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(ROOT / "src")}


@pytest.mark.parametrize("worker", [False, True])
@pytest.mark.parametrize("outside_repository", [False, True])
def test_direct_monitor_help_without_repository_pythonpath(
    tmp_path: Path, worker: bool, outside_repository: bool,
) -> None:
    """Parent and worker must import before parsing help, including from another directory."""
    args = build_parser().parse_args([
        "cohort-tui", "--mode", "monitor", "--independent-monitor",
    ])
    command = [*cohort_command(args), *(["--worker"] if worker else []), "--help"]
    result = subprocess.run(command, cwd=tmp_path if outside_repository else ROOT,
                            env=clean_environment(), capture_output=True, text=True,
                            timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout and "--tui-bin-sha256" in result.stdout


def test_package_monitor_help_without_repository_pythonpath() -> None:
    """Module imports used by callers and existing tests retain their package behavior."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.cohort_independent_monitor", "--help"],
        cwd=ROOT, env=clean_environment(), capture_output=True, text=True,
        timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


@pytest.mark.parametrize("flag", ["--enabled", "--i-accept-live-risk"])
def test_direct_monitor_rejects_authority_after_clean_import(flag: str) -> None:
    """A successful import still reaches the explicit refusal before any worker starts."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/cohort_independent_monitor.py"), flag],
        cwd=ROOT, env=clean_environment(), capture_output=True, text=True,
        timeout=30, check=False,
    )
    assert result.returncode == 2, result.stderr
    assert "monitor mode without execution flags" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
