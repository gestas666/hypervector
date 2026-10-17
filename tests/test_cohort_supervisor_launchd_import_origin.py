"""Keep generated supervisor children bound to the intended source checkout."""

from pathlib import Path
import plistlib

import pytest

import cohort_backend_supervisor as supervisor


@pytest.mark.parametrize("resume", [False, True])
def test_supervise_plist_pins_source_without_changing_opt_in(resume: bool) -> None:
    """Both supervisor policies retain the explicit source path for children."""
    arguments = ["supervise", "--", "/usr/bin/true"]
    plist = plistlib.loads(
        supervisor.launchd_plist(
            "supervise",
            arguments,
            python=Path("/usr/bin/python3"),
            resume_after_host_restart=resume,
        )
    )
    environment = plist["EnvironmentVariables"]
    assert environment["PYTHONPATH"] == str(supervisor.REPOSITORY_ROOT / "src")
    assert environment.get(supervisor.RESUME_AFTER_HOST_RESTART_ENV) == (
        "1" if resume else None
    )
    assert plist["ProgramArguments"][2:] == arguments


def test_watch_plist_does_not_add_supervised_package_to_import_path() -> None:
    """The independent watch needs no import path for the supervised package."""
    plist = plistlib.loads(
        supervisor.launchd_plist(
            "watch", ["watch"], python=Path("/usr/bin/python3")
        )
    )
    assert "PYTHONPATH" not in plist["EnvironmentVariables"]
