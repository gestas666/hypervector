"""Command and lifecycle tests for the one-terminal Hulk canary launcher."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from hypervector.live.hulk_smash_live_config import HulkSmashLiveConfigError
from hypervector.live.hulk_smash_live_config import load_hulk_smash_live_config

SCRIPT = Path(__file__).parents[1] / "scripts" / "hulk_smash_canary_tui.py"
PROFILE = Path("configs/hulk_smash_short_robust_v3_canary.toml")


class TimeoutBackend:
    """Model a live backend still completing a protected venue lifecycle."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        """Return the current process status."""
        return self.returncode

    def wait(self, *, timeout: float) -> int:
        """Remain active until an unsafe external termination is attempted."""
        if not self.terminated:
            raise subprocess.TimeoutExpired(cmd="backend", timeout=timeout)
        self.returncode = -15
        return self.returncode

    def terminate(self) -> None:
        """Record an external termination attempt."""
        self.terminated = True


def _load_module() -> ModuleType:
    spec = spec_from_file_location("hulk_smash_canary_tui", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_one_terminal_launcher_defaults_to_execution_incapable_observe() -> None:
    """The shortest command constructs no order-capable backend."""
    module = _load_module()
    args = module.build_parser().parse_args([])

    launch = module.resolve_launch(
        args,
        wallet_configured=True,
        signing_key_configured=False,
    )

    assert launch.config.mode == "observe"
    assert "scripts/hulk_smash_observe.py" in launch.backend_command
    assert "--enabled" not in launch.backend_command
    assert str(launch.config.backend_ledger) == launch.tui_command[-1]
    timeframe_index = launch.tui_command.index("--timeframe") + 1
    assert launch.tui_command[timeframe_index] == "30m"


def test_observe_launcher_requires_only_the_public_wallet_identity() -> None:
    """Observation needs account reads but must not require a signing key."""
    module = _load_module()
    args = module.build_parser().parse_args([])

    with pytest.raises(HulkSmashLiveConfigError, match="public wallet"):
        module.resolve_launch(
            args,
            wallet_configured=False,
            signing_key_configured=False,
        )


def test_live_launcher_requires_both_explicit_risk_flags() -> None:
    """Selecting live mode alone cannot create execution authority."""
    module = _load_module()
    args = module.build_parser().parse_args(["--mode", "live"])

    with pytest.raises(HulkSmashLiveConfigError, match="--enabled"):
        module.resolve_launch(
            args,
            wallet_configured=True,
            signing_key_configured=True,
        )


def test_explicit_live_launcher_projects_the_exact_live_backend_ledger() -> None:
    """The armed backend and read-only TUI consume one durable ledger."""
    module = _load_module()
    args = module.build_parser().parse_args(
        ["--mode", "live", "--enabled", "--i-accept-live-risk"]
    )

    launch = module.resolve_launch(
        args,
        wallet_configured=True,
        signing_key_configured=True,
    )

    assert launch.config.mode == "live"
    assert "scripts/hulk_smash_live.py" in launch.backend_command
    assert "--enabled" in launch.backend_command
    assert "--i-accept-live-risk" in launch.backend_command
    assert str(launch.config.backend_ledger) == launch.tui_command[-1]


def test_live_supervisor_leaves_slow_protected_backend_running(
    tmp_path: Path,
) -> None:
    """TUI exit cannot kill a live process during unresolved venue cleanup."""
    module = _load_module()
    backend = TimeoutBackend()
    config = load_hulk_smash_live_config(
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
    """An old ledger cannot make a newly launched backend look ready."""
    module = _load_module()
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text(
        '{"event_type":"book_observation","run_id":"old"}\n',
        encoding="utf-8",
    )
    backend = TimeoutBackend()
    config = load_hulk_smash_live_config(PROFILE, mode="observe")
    snapshot = module.capture_ledger_start(ledger)
    polls = 0

    def advance(_seconds: float) -> None:
        nonlocal polls
        polls += 1
        if polls == 1:
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write('{"event_type":"book_observation","run_id":"old"}\n')
        if polls == 2:
            with ledger.open("a", encoding="utf-8") as handle:
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
        backend_label="Hulk",
        log_path=Path("backend.log"),
        sleep_fn=module.time.sleep,
    )

    assert polls == 2


def test_live_shutdown_reports_a_backend_that_already_failed(tmp_path: Path) -> None:
    """A dead backend cannot be reported as a successful TUI session."""
    module = _load_module()
    backend = TimeoutBackend()
    backend.returncode = 2
    config = load_hulk_smash_live_config(
        PROFILE,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )

    with pytest.raises(RuntimeError, match="stopped with 2"):
        module._stop_owned_backend(backend, tmp_path / "STOP", config)


def test_observe_main_loads_wallet_identity_without_loading_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The execution-incapable launcher follows least-privilege env loading."""
    module = _load_module()
    calls: list[str] = []
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    monkeypatch.setattr(
        module,
        "load_wallet_env_if_present",
        lambda: calls.append("wallet"),
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "load_dotenv_if_present",
        lambda: calls.append("full"),
    )
    monkeypatch.setattr(
        module,
        "credential_presence_from_env",
        lambda: type(
            "Presence",
            (),
            {"wallet_configured": True, "signing_key_configured": False},
        )(),
    )
    monkeypatch.setattr(module, "run_supervisor", lambda _launch: 0)

    assert module.main() == 0
    assert calls == ["wallet"]


def test_launcher_main_reports_disarmed_live_refusal_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An incomplete live request produces an actionable refusal."""
    module = _load_module()
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--mode", "live"])

    result = module.main()

    captured = capsys.readouterr()
    assert result == 2
    assert "live start requires --enabled" in captured.err
    assert "Traceback" not in captured.err
