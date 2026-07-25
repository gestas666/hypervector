"""One-command Hypervelocity backend and TUI process supervision."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hypervector.tui_launcher import (
    build_backend_command,
    build_tui_command,
    supervise_hypervelocity_tui,
)


class FakeChild:
    """Controllable backend process double."""

    def __init__(self, *, returncode: int | None = None) -> None:
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return int(self.returncode or 0)


def test_commands_share_the_same_data_root(tmp_path: Path) -> None:
    root = tmp_path / "ops"
    config = Path("configs/hypervelocity_faithful.toml")

    backend = build_backend_command(data_root=root, config_path=config)
    tui = build_tui_command(
        data_root=root,
        symbol="BTC",
        timeframe="1m",
        refresh_ms=500,
        tui_binary=Path("/tmp/tui-regime-detector"),
    )

    assert "hypervelocity-shadow-run" in backend
    assert str(root.resolve()) in backend
    assert str(root.resolve()) in tui
    assert tui[0] == "/tmp/tui-regime-detector"


def test_default_tui_command_uses_cargo_freshness_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HYPERVECTOR_TUI_BIN", raising=False)

    tui = build_tui_command(
        data_root=tmp_path / "ops",
        symbol="BTC",
        timeframe="1m",
        refresh_ms=500,
    )

    assert tui[:6] == [
        "cargo",
        "run",
        "-q",
        "-p",
        "hypervector-tui",
        "--bin",
    ]


def test_supervisor_waits_for_ledger_then_stops_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "ops"
    decisions = root / "paper" / "decisions" / "decisions.jsonl"
    child = FakeChild()
    events: list[str] = []

    def fake_popen(command: list[str], **kwargs: object) -> FakeChild:
        del command, kwargs
        events.append("backend")
        decisions.parent.mkdir(parents=True, exist_ok=True)
        decisions.write_text('{"action":"session_start"}\n', encoding="utf-8")
        return child

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        events.append("tui")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("hypervector.tui_launcher.subprocess.Popen", fake_popen)
    monkeypatch.setattr("hypervector.tui_launcher.subprocess.run", fake_run)

    result = supervise_hypervelocity_tui(
        data_root=root,
        backend_command=["backend"],
        tui_command=["tui"],
        startup_timeout_seconds=1.0,
    )

    assert events == ["backend", "tui"]
    assert child.terminated is True
    assert child.killed is False
    assert result.tui_returncode == 0
    assert result.backend_log.is_file()


def test_backend_early_failure_prevents_tui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = FakeChild(returncode=2)
    tui_started = False

    def fake_popen(command: list[str], **kwargs: object) -> FakeChild:
        del command, kwargs
        return child

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del command, kwargs
        nonlocal tui_started
        tui_started = True
        return subprocess.CompletedProcess([], 0)

    monkeypatch.setattr("hypervector.tui_launcher.subprocess.Popen", fake_popen)
    monkeypatch.setattr("hypervector.tui_launcher.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="backend exited before telemetry"):
        supervise_hypervelocity_tui(
            data_root=tmp_path / "ops",
            backend_command=["backend"],
            tui_command=["tui"],
            startup_timeout_seconds=0.1,
        )

    assert tui_started is False
