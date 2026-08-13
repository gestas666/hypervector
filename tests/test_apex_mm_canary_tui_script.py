"""Command-resolution tests for the one-terminal Apex MM canary."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import signal
import subprocess
import sys
from types import ModuleType

import pytest

from hypervector.live.apex_mm_live_config import ApexMMLiveConfigError

SCRIPT = Path(__file__).parents[1] / "scripts" / "apex_regime_mm_canary_tui.py"


class TimeoutBackend:
    """Model a live backend that remains active during startup polling."""

    def __init__(self) -> None:
        self.returncode: int | None = None

    def poll(self) -> int | None:
        """Return the current process status."""
        return self.returncode

    def wait(self, *, timeout: float) -> int:
        """Remain active for the requested bounded wait."""
        raise subprocess.TimeoutExpired(cmd="backend", timeout=timeout)


def _load_module() -> ModuleType:
    spec = spec_from_file_location("apex_regime_mm_canary_tui", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_launcher_defaults_are_disarmed() -> None:
    """The shortest command has no order authority."""
    args = _load_module().build_parser().parse_args([])

    assert args.enabled is False
    assert args.i_accept_live_risk is False


def test_launcher_requires_both_live_flags() -> None:
    """A TUI request alone cannot grant execution authority."""
    module = _load_module()
    args = module.build_parser().parse_args([])

    with pytest.raises(ApexMMLiveConfigError, match="--enabled"):
        module.resolve_launch(args, credentials_present=True)


def test_armed_launcher_points_backend_and_tui_to_same_ledger() -> None:
    """The read-only view consumes exactly the backend's live ledger."""
    module = _load_module()
    args = module.build_parser().parse_args(["--enabled", "--i-accept-live-risk"])

    launch = module.resolve_launch(args, credentials_present=True)

    assert "scripts/apex_regime_mm_live.py" in launch.backend_command
    assert "--enabled" in launch.backend_command
    assert "--i-accept-live-risk" in launch.backend_command
    assert str(launch.config.backend_ledger) == launch.tui_command[-1]
    assert launch.tui_command[launch.tui_command.index("--symbol") + 1] == "BTC"


def test_supervisor_shutdown_budget_covers_venue_rate_limit_recovery() -> None:
    """TUI exit must not give up while the backend is retrying safe cleanup."""
    module = _load_module()

    assert module._SHUTDOWN_TIMEOUT_SECONDS >= 120.0


def test_launcher_main_reports_refusal_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An incompletely armed launcher gives a clean refusal."""
    module = _load_module()
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    result = module.main()

    captured = capsys.readouterr()
    assert result == 2
    assert "live start requires --enabled" in captured.err
    assert "Traceback" not in captured.err


def test_launcher_main_installs_and_restores_sigterm_cleanup_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Terminating the supervisor must enter its owned-backend cleanup path."""
    module = _load_module()
    calls: list[tuple[signal.Signals, object]] = []
    previous = object()

    def record_handler(signum: signal.Signals, handler: object) -> object:
        calls.append((signum, handler))
        return previous

    monkeypatch.setattr(signal, "signal", record_handler)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--enabled", "--i-accept-live-risk"],
    )
    monkeypatch.setattr(
        module,
        "credential_presence_from_env",
        lambda: type(
            "Presence",
            (),
            {"wallet_configured": True, "signing_key_configured": True},
        )(),
    )
    monkeypatch.setattr(module, "run_supervisor", lambda _launch: 0)

    assert module.main() == 0
    assert calls[0][0] is signal.SIGTERM
    with pytest.raises(KeyboardInterrupt):
        calls[0][1](signal.SIGTERM, None)  # type: ignore[operator]
    assert calls[-1] == (signal.SIGTERM, previous)


def test_launcher_waits_for_fresh_backend_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale Apex ledger cannot satisfy a newly launched backend startup."""
    module = _load_module()
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text(
        '{"event_type":"configuration_identity","run_id":"old"}\n',
        encoding="utf-8",
    )
    backend = TimeoutBackend()
    args = module.build_parser().parse_args(["--enabled", "--i-accept-live-risk"])
    config = module.resolve_launch(args, credentials_present=True).config
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
                    '"live_armed":true}\n'
                )

    monkeypatch.setattr(module.time, "sleep", advance)

    module.wait_for_fresh_configuration_identity(
        backend,
        ledger,
        snapshot=snapshot,
        expected_profile_fingerprint=config.profile_fingerprint,
        expected_live_armed=True,
        timeout_seconds=1.0,
        backend_label="Apex MM",
        log_path=Path("backend.log"),
        sleep_fn=module.time.sleep,
    )

    assert polls == 2
