"""The independent monitor script exposes no financial execution branch."""

from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path

import pytest

from hypervector.live.process_signal_stop import ProcessSignalStop
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock
from test_cohort_independent_checkpoint import CONFIG


@pytest.mark.parametrize("extra", [
    ["--mode", "live"], ["--enabled"], ["--i-accept-live-risk"],
    ["--resume-transition-drain"], ["--out", "unowned.json"],
    ["--staged-config", "unavailable.toml"],
])
def test_script_rejects_authority_and_unowned_parent_options(
    monkeypatch: pytest.MonkeyPatch, extra: list[str],
) -> None:
    """Invalid direct script invocation cannot reach child startup."""
    module = import_module("scripts.cohort_independent_monitor")

    def refuse_start(*_args: object, **_kwargs: object) -> None:
        pytest.fail("an invalid monitor started a process")

    monkeypatch.setattr(module, "run_independent_monitor", refuse_start)
    assert module.main(["--config", str(CONFIG), *extra]) == 2


def test_script_requires_active_config() -> None:
    """A monitor cannot guess the active execution profile."""
    module = import_module("scripts.cohort_independent_monitor")
    assert module.main([]) == 2


@pytest.mark.parametrize("extra", [[], ["--run-id", "active"],
    ["--run-id", "active", "--out", "result.json", "--interval-seconds", "nan"],
    ["--run-id", "active", "--out", "result.json", "--interval-seconds", "-1"],
])
def test_worker_rejects_incomplete_identity_or_invalid_interval(extra: list[str]) -> None:
    """A malformed worker must fail before acquiring an output lock."""
    module = import_module("scripts.cohort_independent_monitor")
    assert module.main(["--worker", "--config", str(CONFIG), *extra]) == 2


def test_worker_releases_its_lock_after_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One successful publication followed by interruption retains no writer lock."""
    module = import_module("scripts.cohort_independent_monitor")
    output = tmp_path / "checkpoint.json"
    calls: list[dict[str, object]] = []

    def publish(**values: object) -> dict[str, object]:
        calls.append(values)
        return {"generated_at_utc": datetime.now(timezone.utc).isoformat()}

    def interrupt(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "publish_independent_checkpoint", publish)
    monkeypatch.setattr(module.time, "sleep", interrupt)
    result = module.main(["--worker", "--config", str(CONFIG), "--run-id", "active", "--out", str(output)])
    assert result == 130 and len(calls) == 1
    assert calls[0]["destination"] == output and calls[0]["run_id"] == "active"
    with cohort_checkpoint_runtime_lock(output):
        pass


def test_script_propagates_parent_result_without_loading_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parent receives only a resolved monitor and a process-local stop latch."""
    module = import_module("scripts.cohort_independent_monitor")
    received: list[bool] = []

    def resolve(_args: object, *, credentials_present: bool) -> object:
        received.append(credentials_present)
        return object()

    monkeypatch.setattr(module, "resolve_launch", resolve)
    monkeypatch.setattr(module, "install_process_signal_stop", lambda: ProcessSignalStop())
    monkeypatch.setattr(module, "run_independent_monitor", lambda *_a, **_k: 7)
    assert module.main(["--config", str(CONFIG)]) == 7
    assert received == [False]
