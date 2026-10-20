"""Venue reachability, market-contract refusal and the blindness exit at the live boundary.

An offline host must neither write a pre-start bundle nor crash into a charged
relaunch; a venue contract fact that a relaunch cannot change must be a start
refusal; and the account-blindness exit must be distinguishable from a crash.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from test_multi_asset_bidirectional_live_script import (
    SCRIPT,
    _args,
    _load_module,
    _neutralize_start_boundaries,
)

import cohort_supervisor_restart_policy as restart_policy
from hypervector.live.hyperliquid_perp_reader import VenueMetadataMismatchError
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfigError
from hypervector.live.multi_asset_live_runner_support import (
    CohortDegradedBlindnessError,
)
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError

_CONFIG = "tests/fixtures/profiles/cohort_base.toml"


def _config(live_script: ModuleType, tmp_path: Path) -> object:
    loaded = live_script.load_multi_asset_live_config(
        _CONFIG, mode="live", enabled=True, accepts_live_risk=True
    )
    live_root = tmp_path / "data/live/bidirectional_cohort"
    live_root.mkdir(parents=True, exist_ok=True)
    return replace(
        loaded,
        cohort_ledger=live_root / "decisions.jsonl",
        stop_file=live_root / "STOP",
    )


def _meta(config: object, **overrides: int) -> dict[str, object]:
    return {
        "universe": [
            {
                "name": asset.symbol,
                "szDecimals": 2,
                "maxLeverage": overrides.get(
                    asset.symbol, int(asset.venue_max_leverage)
                ),
            }
            for asset in config.assets  # type: ignore[attr-defined]
        ]
    }


def _install_venue(
    live_script: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    failures: int,
    meta: dict[str, object],
    on_sleep: object = None,
) -> None:
    remaining = [failures]

    def fetcher(_session: object) -> object:
        def fetch(dex: str) -> object:
            events.append(f"meta:{dex}")
            if remaining[0] > 0:
                remaining[0] -= 1
                raise requests.ConnectionError("host offline")
            return meta

        return fetch

    def sleep(seconds: float) -> None:
        events.append("sleep")
        if callable(on_sleep):
            on_sleep()

    monkeypatch.setattr(live_script.venue_probe, "http_meta_fetcher", fetcher)
    monkeypatch.setattr(live_script, "time", SimpleNamespace(sleep=sleep))


def _stop_after_backup(
    live_script: ModuleType, monkeypatch: pytest.MonkeyPatch, events: list[str]
) -> None:
    monkeypatch.setattr(
        live_script,
        "discover_cohort_implementation_sources",
        lambda *_args: {"launcher": SCRIPT},
    )

    def backup(*_args: object, **_kwargs: object) -> object:
        events.append("backup")
        raise live_script.CohortPrestartBackupError("stop after backup")

    def forbidden_adapter(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("adapter constructed")

    monkeypatch.setattr(live_script, "create_cohort_prestart_backup", backup)
    monkeypatch.setattr(live_script, "_create_adapters", forbidden_adapter)


def _run_locked(live_script: ModuleType, config: object) -> None:
    live_script._run_locked(
        _args(enabled=True, i_accept_live_risk=True),
        config,
        live_script.CredentialPresence(True, True),
        Mock(),
    )


def test_offline_venue_is_waited_out_before_the_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    live_script = _load_module()
    config = _config(live_script, tmp_path)
    events: list[str] = []
    _install_venue(live_script, monkeypatch, events, failures=3, meta=_meta(config))
    _stop_after_backup(live_script, monkeypatch, events)
    real_datetime = live_script.datetime

    class _Clock:
        @staticmethod
        def now(tz: object = None) -> object:
            events.append("run_stamp")
            return real_datetime.now(tz)  # type: ignore[arg-type]

    monkeypatch.setattr(live_script, "datetime", _Clock)

    with pytest.raises(live_script.CohortPrestartBackupError, match="after backup"):
        _run_locked(live_script, config)

    first_backup = events.index("backup")
    assert events[:first_backup].count("meta:") == 4
    assert "sleep" in events[:first_backup]
    assert "meta:" not in events[first_backup:]
    # The run identity and the bundle stamp are taken after the wait, not before.
    assert events.index("run_stamp") > max(
        index for index, event in enumerate(events) if event == "meta:"
    )
    marker = config.cohort_ledger.parent / live_script.venue_probe.VENUE_WAIT_MARKER
    assert not marker.exists()


def test_stop_file_during_the_wait_refuses_without_a_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    live_script = _load_module()
    config = _config(live_script, tmp_path)
    events: list[str] = []
    _install_venue(
        live_script,
        monkeypatch,
        events,
        failures=1_000,
        meta=_meta(config),
        on_sleep=lambda: config.stop_file.write_text("operator"),
    )
    _stop_after_backup(live_script, monkeypatch, events)

    with pytest.raises(MultiAssetLiveConfigError, match="operator stop file"):
        _run_locked(live_script, config)

    assert "backup" not in events
    assert not (tmp_path / "data/backups").exists()


def test_probe_mismatch_refuses_before_the_bundle_and_exits_two(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live_script = _load_module()
    config = _config(live_script, tmp_path)
    events: list[str] = []
    _install_venue(
        live_script, monkeypatch, events, failures=0, meta=_meta(config, SOL=4)
    )
    _stop_after_backup(live_script, monkeypatch, events)

    with pytest.raises(VenueMetadataMismatchError) as raised:
        _run_locked(live_script, config)

    assert "backup" not in events
    assert (
        "SOL venue max leverage 4 is below the requested leverage 5 "
        "(profile venue maximum 20)"
    ) in str(raised.value)

    monkeypatch.setattr(live_script, "load_dotenv_if_present", lambda: None)
    monkeypatch.setattr(
        live_script, "build_parser", lambda: SimpleNamespace(parse_args=_args)
    )

    def refuse(_args: object) -> int:
        raise raised.value

    monkeypatch.setattr(live_script, "run_live", refuse)
    assert live_script.main() == live_script.EXIT_START_REFUSED == 2
    assert "live start refused: SOL venue max leverage 4" in capsys.readouterr().err


def test_venue_max_leverage_change_that_allows_the_request_warns_and_starts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live_script = _load_module()
    config = _config(live_script, tmp_path)
    events: list[str] = []
    _install_venue(
        live_script, monkeypatch, events, failures=0, meta=_meta(config, SOL=10)
    )
    _stop_after_backup(live_script, monkeypatch, events)

    with pytest.raises(live_script.CohortPrestartBackupError):
        _run_locked(live_script, config)

    assert "backup" in events
    assert "venue_max_leverage_changed" in capsys.readouterr().out


def _engine_start_fault(
    live_script: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    fault: Exception,
) -> tuple[Mock, object]:
    config = live_script.load_multi_asset_live_config(
        _CONFIG, mode="live", enabled=True, accepts_live_risk=True
    )
    _neutralize_start_boundaries(live_script, monkeypatch)
    monkeypatch.setattr(live_script, "_await_venue", lambda _config: None)
    runner = Mock()
    runner.run.side_effect = fault
    telemetry = Mock()
    monkeypatch.setattr(live_script, "_create_telemetry", lambda *_a: telemetry)
    monkeypatch.setattr(live_script, "_create_runner", lambda *_a, **_k: runner)
    return telemetry, config


def test_engine_start_mismatch_is_journaled_then_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The preflight inside engine start raises after the bundle; it still holds."""
    live_script = _load_module()
    fault = VenueMetadataMismatchError(
        "xyz:BRENTOIL max leverage mismatch: expected 20, observed 10"
    )
    telemetry, config = _engine_start_fault(live_script, monkeypatch, fault)

    with pytest.raises(VenueMetadataMismatchError, match="xyz:BRENTOIL"):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )

    telemetry.emit_runtime_fault.assert_called_once_with(
        exception_type="VenueMetadataMismatchError"
    )


def test_a_wrapped_mismatch_is_still_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_script = _load_module()
    try:
        try:
            raise VenueMetadataMismatchError("SOL max leverage mismatch")
        except VenueMetadataMismatchError as inner:
            raise SolLiveEngineError("startup failed") from inner
    except SolLiveEngineError as wrapped:
        fault = wrapped
    _, config = _engine_start_fault(live_script, monkeypatch, fault)

    with pytest.raises(VenueMetadataMismatchError, match="SOL max leverage"):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )


def test_other_start_faults_stay_restartable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the venue contract refusal changes phase; an ordinary fault still crashes."""
    live_script = _load_module()
    _, config = _engine_start_fault(
        live_script, monkeypatch, SolLiveEngineError("receipt not yet visible")
    )

    with pytest.raises(live_script.CohortRunFailure):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )


def test_account_blindness_exits_with_its_own_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The supervisor relaunches this exit without charging the crash budget."""
    live_script = _load_module()
    monkeypatch.setattr(live_script, "load_dotenv_if_present", lambda: None)
    monkeypatch.setattr(
        live_script, "build_parser", lambda: SimpleNamespace(parse_args=_args)
    )

    def blind(_args: object) -> int:
        cause = CohortDegradedBlindnessError("account reconciliation unavailable")
        raise live_script.CohortRunFailure(str(cause)) from cause

    monkeypatch.setattr(live_script, "run_live", blind)

    assert live_script.main() == live_script.EXIT_DEGRADED_BLINDNESS == 4
    assert live_script.EXIT_DEGRADED_BLINDNESS == (
        restart_policy.EXIT_DEGRADED_BLINDNESS
    )
    assert live_script.EXIT_DEGRADED_BLINDNESS not in {
        live_script.EXIT_RUN_FAILED,
        live_script.EXIT_START_REFUSED,
    }
