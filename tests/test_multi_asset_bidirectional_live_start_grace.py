"""A start that waited for the venue restarts its monitors' startup grace.

The runtime lock is written when the process starts, before the venue wait. The
watch agent anchors its startup grace on that lock's age, so after a long wait
the ledger replay still ahead of the backend read as a stale heartbeat. Once the
wait returns, the process refreshes the lock it holds, so the grace begins when
the start actually proceeds.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
import os
from pathlib import Path
import time
from unittest.mock import Mock

import pytest

from test_cohort_candle_session import PROFILE, _boundary
from test_multi_asset_bidirectional_live_script import SCRIPT, _args, _load_module

_HOUR = 3_600.0


def _tmp_config(live_script: object, tmp_path: Path) -> object:
    loaded = live_script.load_multi_asset_live_config(  # type: ignore[attr-defined]
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    live_root = tmp_path / "data/live/bidirectional_cohort"
    live_root.mkdir(parents=True)
    return replace(
        loaded,
        cohort_ledger=live_root / "decisions.jsonl",
        stop_file=live_root / "STOP",
    )


def _stale_lock(config: object) -> Path:
    lock = config.cohort_ledger.parent / "process.lock"  # type: ignore[attr-defined]
    lock.write_text(str(os.getpid()), encoding="utf-8")
    stale = time.time() - 2 * _HOUR
    os.utime(lock, (stale, stale))
    return lock


def _stop_at_backup(
    live_script: object, monkeypatch: pytest.MonkeyPatch, observe: object
) -> None:
    monkeypatch.setattr(
        live_script, "discover_cohort_implementation_sources", lambda *_a: {"x": SCRIPT}
    )

    def backup(*_args: object, **_kwargs: object) -> object:
        observe("backup")  # type: ignore[operator]
        raise live_script.CohortPrestartBackupError("stop at backup")  # type: ignore[attr-defined]

    monkeypatch.setattr(live_script, "create_cohort_prestart_backup", backup)


def test_the_held_lock_is_refreshed_after_the_venue_wait_returns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    live_script = _load_module()
    config = _tmp_config(live_script, tmp_path)
    lock = _stale_lock(config)
    ages: dict[str, float] = {}

    def observe(stage: str) -> None:
        ages[stage] = time.time() - lock.stat().st_mtime

    monkeypatch.setattr(live_script, "_await_venue", lambda _config: observe("wait"))
    _stop_at_backup(live_script, monkeypatch, observe)

    with pytest.raises(live_script.CohortPrestartBackupError, match="at backup"):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
            lock_path=lock,
        )

    assert ages["wait"] > _HOUR  # still the process-start stamp during the wait
    assert 0.0 <= ages["backup"] < 60.0  # the grace restarts when the start proceeds
    assert lock.read_text(encoding="utf-8") == str(os.getpid())


def test_without_a_held_lock_nothing_is_touched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A caller that holds no runtime lock (a test harness) never refreshes one."""
    live_script = _load_module()
    config = _tmp_config(live_script, tmp_path)
    lock = _stale_lock(config)
    before = lock.stat().st_mtime
    monkeypatch.setattr(live_script, "_await_venue", lambda _config: None)
    _stop_at_backup(live_script, monkeypatch, lambda _stage: None)

    with pytest.raises(live_script.CohortPrestartBackupError):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )

    assert lock.stat().st_mtime == before


def test_an_unrefreshable_lock_is_reported_but_does_not_refuse_the_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live_script = _load_module()
    config = _tmp_config(live_script, tmp_path)
    reached: list[str] = []
    monkeypatch.setattr(live_script, "_await_venue", lambda _config: None)
    _stop_at_backup(live_script, monkeypatch, reached.append)

    with pytest.raises(live_script.CohortPrestartBackupError):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
            lock_path=tmp_path / "missing" / "process.lock",
        )

    assert reached == ["backup"]
    assert "runtime lock not refreshed" in capsys.readouterr().out


def test_run_live_hands_the_lock_it_holds_to_the_locked_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module, _session = _boundary(monkeypatch)
    held = tmp_path / "process.lock"
    received: dict[str, object] = {}

    @contextmanager
    def lock(_ledger: Path) -> Iterator[Path]:
        yield held

    def locked(*_args: object, lock_path: Path | None = None, **_kwargs: object) -> int:
        received["lock_path"] = lock_path
        return 0

    monkeypatch.setattr(module, "bidirectional_live_runtime_lock", lock)
    monkeypatch.setattr(
        module.ConfiguredMultiAssetIntentPoller,
        "with_default_collectors",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(module, "_run_locked", locked)

    assert (
        module.run_live(_args(config=PROFILE, enabled=True, i_accept_live_risk=True))
        == 0
    )
    assert received == {"lock_path": held}
