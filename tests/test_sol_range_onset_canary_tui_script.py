"""Command-resolution tests for the one-terminal SOL canary launcher."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from hypervector.live.sol_range_onset_config import SolCanaryConfigError
from hypervector.live.sol_range_onset_config import load_sol_range_onset_config

SCRIPT = Path(__file__).parents[1] / "scripts" / "sol_range_onset_canary_tui.py"
PROFILE = Path("configs/sol_range_onset_canary.toml")


class TimeoutBackend:
    """Model a backend still resolving a venue lifecycle after the grace period."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, *, timeout: float) -> int:
        if not self.terminated:
            raise subprocess.TimeoutExpired(cmd="backend", timeout=timeout)
        self.returncode = -15
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True


def _load_module() -> ModuleType:
    spec = spec_from_file_location("sol_range_onset_canary_tui", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_one_terminal_launcher_defaults_to_shadow() -> None:
    """The shortest command has no order authority and reads the shadow ledger."""
    module = _load_module()
    args = module.build_parser().parse_args([])

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.config.mode == "shadow"
    assert "scripts/sol_range_onset_forward_observer.py" in launch.backend_command
    assert "--enabled" not in launch.backend_command
    assert str(launch.config.backend_ledger) == launch.tui_command[-1]


def test_live_launcher_requires_both_flags_before_command_resolution() -> None:
    """Selecting LIVE alone is not execution authority."""
    module = _load_module()
    args = module.build_parser().parse_args(["--mode", "live"])

    with pytest.raises(SolCanaryConfigError, match="--enabled"):
        module.resolve_launch(args, credentials_present=True)


def test_explicit_live_launcher_targets_only_the_live_ledger() -> None:
    """Armed backend and read-only TUI share the separate live ledger path."""
    module = _load_module()
    args = module.build_parser().parse_args(
        ["--mode", "live", "--enabled", "--i-accept-live-risk"]
    )

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.config.mode == "live"
    assert "scripts/sol_range_onset_live.py" in launch.backend_command
    assert "--enabled" in launch.backend_command
    assert "--i-accept-live-risk" in launch.backend_command
    assert str(launch.config.live_ledger) == launch.tui_command[-1]
    assert launch.config.authoritative_stop_file == launch.config.live_stop_file


def test_launcher_main_reports_refusal_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An incompletely armed launcher gives a clean actionable refusal."""
    module = _load_module()
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--mode", "live"])

    result = module.main()

    captured = capsys.readouterr()
    assert result == 2
    assert "live start requires --enabled" in captured.err
    assert "Traceback" not in captured.err


def test_live_supervisor_never_terminates_backend_during_slow_shutdown(
    tmp_path: Path,
) -> None:
    """A possible in-flight venue lifecycle must outlive the TUI grace period."""
    module = _load_module()
    backend = TimeoutBackend()
    config = load_sol_range_onset_config(
        PROFILE,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    stop_file = tmp_path / "STOP"

    with pytest.raises(RuntimeError, match="left running"):
        module._stop_owned_backend(backend, stop_file, config)

    assert backend.terminated is False
    assert stop_file.read_text(encoding="utf-8") == "operator_tui_exit\n"


def test_launcher_waits_for_fresh_backend_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale SOL ledger cannot satisfy a newly launched backend startup."""
    module = _load_module()
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text(
        '{"event_type":"configuration_identity","run_id":"old"}\n',
        encoding="utf-8",
    )
    backend = TimeoutBackend()
    config = load_sol_range_onset_config(PROFILE, mode="shadow")
    snapshot = module.capture_ledger_start(ledger)
    polls = 0

    def advance(_seconds: float) -> None:
        nonlocal polls
        polls += 1
        with ledger.open("a", encoding="utf-8") as handle:
            if polls == 1:
                handle.write('{"event_type":"configuration_identity","run_id":"old"}\n')
            if polls == 2:
                handle.write(
                    '{"event_type":"configuration_identity",'
                    '"run_id":"fresh",'
                    f'"profile_fingerprint":"{config.profile_fingerprint}",'
                    '"live_armed":false}\n'
                )

    monkeypatch.setattr(module.time, "sleep", advance)

    module.wait_for_fresh_configuration_identity(
        backend,
        ledger,
        snapshot=snapshot,
        expected_profile_fingerprint=config.profile_fingerprint,
        expected_live_armed=False,
        timeout_seconds=1.0,
        backend_label="SOL shadow",
        log_path=Path("backend.log"),
        sleep_fn=module.time.sleep,
    )

    assert polls == 2
