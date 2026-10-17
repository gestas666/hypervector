"""Current operator tools must be reachable through the installed unified CLI."""

from types import SimpleNamespace

import pytest

from hypervector.cli import build_parser
import cohort_supervisor_health as health


@pytest.mark.parametrize("operation", ["status", "watch", "print-launchd"])
def test_supervisor_options_are_forwarded_verbatim(operation: str) -> None:
    """Nested supervisor commands cannot depend on repository-relative scripts."""
    args = build_parser().parse_args(["cohort", "supervisor", operation, "--help"])
    assert args.arguments == [operation, "--help"]


def test_economic_report_uses_a_packaged_service() -> None:
    """The retained local accounting work belongs to the research workflow."""
    from hypervector.commands.operations import operation_command

    args = build_parser().parse_args(
        [
            "research",
            "economics",
            "--checkpoint",
            "snapshot.json",
            "--funding",
            "funding.parquet",
            "--out",
            "new.json",
        ]
    )
    command = operation_command(args)
    assert command[1:3] == ("-m", "hypervector.operations.strategy_economic_reset")


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (
            "python -m hypervector.operations.multi_asset_bidirectional_live --enabled --i-accept-live-risk",
            True,
        ),
        ("python scripts/multi_asset_bidirectional_live.py --enabled", True),
        ("python -c 'print(\"multi_asset_bidirectional_live.py\")'", False),
        (
            "python -m other --note hypervector.operations.multi_asset_bidirectional_live",
            False,
        ),
    ],
)
def test_process_recognition_accepts_only_supported_backend_entries(
    command: str, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The packaged backend must remain visible to the independent watcher."""
    monkeypatch.setattr(health.os, "kill", lambda *_a: None)
    monkeypatch.setattr(
        health.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=command),
    )
    assert health.process_is_backend(1234) is expected


def test_supervision_package_is_independent_of_trading_imports() -> None:
    """An execution-package import failure must not disable its observer."""
    import subprocess
    import sys

    code = "import sys; import hypervector_supervision.cohort_backend_supervisor; assert not any(name == 'hypervector' or name.startswith('hypervector.') for name in sys.modules)"
    subprocess.run([sys.executable, "-c", code], check=True, timeout=15)
