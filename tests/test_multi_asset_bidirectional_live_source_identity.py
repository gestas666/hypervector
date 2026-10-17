"""Implementation sources that change during the venue wait refuse the start.

The backend imports its modules when the process starts, but the pre-start
bundle hashes the implementation sources only after the venue wait, which has no
upper bound. A deploy during a long outage would bundle and fingerprint code the
running process never imported. The sources are now identified before the wait
and again after it; a difference is a start refusal the operator resolves by
restarting the backend on the new code.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from test_multi_asset_bidirectional_live_script import _args, _load_module

from hypervector.live.cohort_backup_identity import build_implementation_identity
from hypervector.live.cohort_implementation_sources import (
    implementation_source_identity,
)
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfigError

_CONFIG = "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml"


def _sources(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "sources"
    root.mkdir(exist_ok=True)
    engine, provider = root / "engine.py", root / "provider.py"
    engine.write_text("STOP = 'venue'\n", encoding="utf-8")
    provider.write_text("SIGNAL = 1\n", encoding="utf-8")
    return {"repository_0000": engine, "provider_0000": provider}


def _harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    during_wait: object,
    discovered: list[dict[str, Path]] | None = None,
) -> tuple[ModuleType, list[str], dict[str, object]]:
    live_script = _load_module()
    sources = _sources(tmp_path)
    events: list[str] = []
    captured: dict[str, object] = {}
    answers = iter(discovered or [])

    def discover(repository: Path, provider: Path) -> dict[str, Path]:
        events.append("discover")
        return next(answers, sources)

    def wait(_config: object) -> None:
        events.append("wait")
        during_wait(sources)  # type: ignore[operator]

    def backup(*_args: object, **kwargs: object) -> object:
        events.append("backup")
        captured.update(kwargs)
        raise live_script.CohortPrestartBackupError("stop at backup")

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("adapter constructed")

    monkeypatch.setattr(live_script, "discover_cohort_implementation_sources", discover)
    monkeypatch.setattr(live_script, "_await_venue", wait)
    monkeypatch.setattr(live_script, "create_cohort_prestart_backup", backup)
    monkeypatch.setattr(live_script, "_create_adapters", forbidden)
    return live_script, events, captured


def _run_locked(live_script: ModuleType, tmp_path: Path) -> None:
    config = live_script.load_multi_asset_live_config(
        _CONFIG, mode="live", enabled=True, accepts_live_risk=True
    )
    live_root = tmp_path / "data/live/bidirectional_cohort"
    live_root.mkdir(parents=True, exist_ok=True)
    config = replace(
        config,
        cohort_ledger=live_root / "decisions.jsonl",
        stop_file=live_root / "STOP",
    )
    live_script._run_locked(
        _args(enabled=True, i_accept_live_risk=True),
        config,
        live_script.CredentialPresence(True, True),
        Mock(),
    )


def test_unchanged_sources_are_identified_before_and_after_the_wait(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    live_script, events, captured = _harness(
        monkeypatch, tmp_path, lambda _sources: None
    )

    with pytest.raises(live_script.CohortPrestartBackupError, match="at backup"):
        _run_locked(live_script, tmp_path)

    assert events == ["discover", "wait", "discover", "backup"]
    assert captured["implementation_sources"] == _sources(tmp_path)


def test_a_source_edited_during_the_wait_refuses_before_the_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def deploy(sources: dict[str, Path]) -> None:
        sources["repository_0000"].write_text("STOP = 'changed'\n", encoding="utf-8")

    live_script, events, _ = _harness(monkeypatch, tmp_path, deploy)

    with pytest.raises(
        MultiAssetLiveConfigError,
        match="implementation sources changed during the venue wait",
    ):
        _run_locked(live_script, tmp_path)

    assert "backup" not in events


def test_a_source_added_during_the_wait_refuses_before_the_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = _sources(tmp_path)
    added = tmp_path / "sources" / "added.py"
    added.write_text("NEW = True\n", encoding="utf-8")
    after = {**before, "repository_0001": added}
    live_script, events, _ = _harness(
        monkeypatch, tmp_path, lambda _sources: None, discovered=[before, after]
    )

    with pytest.raises(MultiAssetLiveConfigError, match="restart the backend"):
        _run_locked(live_script, tmp_path)

    assert events == ["discover", "wait", "discover"]


def test_the_refusal_exits_with_the_start_refused_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def deploy(sources: dict[str, Path]) -> None:
        sources["provider_0000"].write_text("SIGNAL = 2\n", encoding="utf-8")

    live_script, _, _ = _harness(monkeypatch, tmp_path, deploy)
    monkeypatch.setattr(live_script, "load_dotenv_if_present", lambda: None)
    monkeypatch.setattr(
        live_script, "build_parser", lambda: SimpleNamespace(parse_args=_args)
    )
    monkeypatch.setattr(
        live_script, "run_live", lambda _args: _run_locked(live_script, tmp_path)
    )

    assert live_script.main() == live_script.EXIT_START_REFUSED == 2
    error = capsys.readouterr().err
    assert "live start refused: implementation sources changed" in error


def test_source_identity_is_the_backup_implementation_identity(tmp_path: Path) -> None:
    sources = _sources(tmp_path)
    identity = implementation_source_identity(sources)
    records = [
        {
            "role": f"implementation_{role}",
            "source_bytes": path.stat().st_size,
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for role, path in sources.items()
    ]
    assert identity == build_implementation_identity(records)
    assert identity["file_count"] == 2
    assert implementation_source_identity(dict(reversed(sources.items()))) == identity
    swapped = {
        "repository_0000": sources["provider_0000"],
        "provider_0000": sources["repository_0000"],
    }
    assert implementation_source_identity(swapped) != identity
    with pytest.raises(ValueError, match="implementation sources"):
        implementation_source_identity({})
