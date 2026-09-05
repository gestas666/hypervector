"""Fail-closed command-boundary tests for the multi-asset live cohort."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from hypervector.live.cohort_prestart_backup import CohortPrestartBackupError
from hypervector.live.cohort_transition_drain import CohortTransitionDrainError
from hypervector.live.cohort_transition_drain import CohortTransitionDrain
from hypervector.live.cohort_transition_drain import archive_completed_transition_drain
from hypervector.live.cohort_transition_drain import load_transition_drain_snapshot
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfigError

SCRIPT = Path(__file__).parents[1] / "scripts" / "multi_asset_bidirectional_live.py"
V25 = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")


def _load_module() -> ModuleType:
    spec = spec_from_file_location("multi_asset_bidirectional_live", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "config": Path("configs/multi_asset_bidirectional_canary.toml"),
        "backtest_lab_root": Path("../backtest-lab/backtest_lab"),
        "enabled": False,
        "i_accept_live_risk": False,
        "resume_transition_drain": False,
        "max_polls": 1,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_live_command_defaults_to_the_complete_staged_portfolio() -> None:
    """A future explicitly armed start must not silently select the old shell."""
    live_script = _load_module()

    assert live_script.build_parser().parse_args([]).config == V25


def test_router_preserves_canonical_asset_order_across_providers() -> None:
    """Provider declaration order must not reorder runner-owned assets."""
    live_script = _load_module()
    config = live_script.load_multi_asset_live_config(
        Path(
            "configs/multi_asset_bidirectional_eth_sol_full_observation_canary_v24.toml"
        ),
        mode="observe",
    )

    assert live_script.build_router(config).symbols == config.symbols


def _backup_result(
    live_script: ModuleType,
    tmp_path: Path,
    *,
    strategy_changed: bool,
    previous_profile_fingerprint: str | None = None,
    previous_run_id: str | None = None,
    previous_config_path: Path | None = None,
) -> object:
    manifest_path = tmp_path / "backup/manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "previous_identity": {
            "profile_fingerprint": previous_profile_fingerprint,
            "run_id": previous_run_id,
            "config_source_path": (
                str(previous_config_path) if previous_config_path is not None else None
            ),
        }
    }
    encoded = json.dumps(manifest).encode()
    manifest_path.write_bytes(encoded)
    return live_script.CohortPrestartBackupResult(
        path=tmp_path / "backup",
        manifest_path=manifest_path,
        manifest_sha256=hashlib.sha256(encoded).hexdigest(),
        strategy_changed=strategy_changed,
        implementation_file_count=1,
        implementation_sha256="b" * 64,
    )


def test_disarmed_command_refuses_before_sdk_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neither configured credentials nor imports bypass the two live flags."""
    live_script = _load_module()
    monkeypatch.setattr(
        live_script,
        "credential_presence_from_env",
        lambda: live_script.CredentialPresence(True, True),
    )
    constructed = False

    def forbidden(*_args: object, **_kwargs: object) -> object:
        nonlocal constructed
        constructed = True
        raise AssertionError("SDK construction occurred while disarmed")

    monkeypatch.setattr(live_script, "create_armed_multi_asset_adapters", forbidden)

    with pytest.raises(MultiAssetLiveConfigError, match="--enabled"):
        live_script.run_live(_args(i_accept_live_risk=True))

    assert constructed is False


def test_main_maps_normal_poll_count_to_success_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normal flat shutdown must not expose its poll count as OS failure."""
    live_script = _load_module()
    parser = SimpleNamespace(parse_args=lambda: _args())
    monkeypatch.setattr(live_script, "load_dotenv_if_present", lambda: None)
    monkeypatch.setattr(live_script, "build_parser", lambda: parser)
    monkeypatch.setattr(live_script, "run_live", lambda _args: 12)

    assert live_script.main() == 0


def test_guarded_runner_journals_unhandled_fault_before_reraising() -> None:
    """Unexpected runtime exit is durable even when stderr is unavailable."""
    live_script = _load_module()
    runner = Mock()
    runner.run.side_effect = RuntimeError("sensitive transport detail")
    telemetry = Mock()

    with pytest.raises(RuntimeError, match="sensitive transport detail"):
        live_script._run_guarded(runner, telemetry, max_polls=None)

    telemetry.emit_runtime_fault.assert_called_once_with(exception_type="RuntimeError")


def test_router_declares_both_sides_for_every_provider_and_symbol() -> None:
    """Launcher assembly cannot silently collapse the cohort to one side."""
    live_script = _load_module()
    config = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )

    router = live_script.build_router(config)

    assert router.symbols == ("BTC", "ETH", "SOL", "HYPE")


def test_live_factory_bounds_shared_read_coalescing_below_poll_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Account reads are shared per cycle without remaining stale next cycle."""
    live_script = _load_module()
    config = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    captured: dict[str, object] = {}

    def capture(*_args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(live_script, "create_armed_multi_asset_adapters", capture)

    live_script._create_adapters(config)

    assert captured["read_coalesce_seconds"] == 10.0
    assert captured["read_coalesce_seconds"] < config.poll_seconds


def test_live_operator_inbox_uses_cohort_aware_command_age_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The armed backend wires command freshness to its declared cohort shape."""
    live_script = _load_module()
    config = live_script.load_multi_asset_live_config(
        V25,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    captured: dict[str, object] = {}

    def capture(*_args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(live_script, "CohortOperatorInbox", capture)

    inbox = live_script._create_operator_inbox(config, "fixture-run")

    assert inbox is not None
    assert captured["run_id"] == "fixture-run"
    assert captured["profile_fingerprint"] == config.profile_fingerprint
    assert captured["maximum_age_seconds"] == 120.0


def test_locked_start_refuses_before_adapter_when_backup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No authenticated exchange client exists until backup verification passes."""
    live_script = _load_module()
    loaded = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        loaded,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )
    adapter_constructed = False

    def fail_backup(*_args: object, **_kwargs: object) -> object:
        raise CohortPrestartBackupError("injected backup failure")

    def forbidden_adapter(*_args: object, **_kwargs: object) -> object:
        nonlocal adapter_constructed
        adapter_constructed = True
        raise AssertionError("adapter construction bypassed failed backup")

    monkeypatch.setattr(
        live_script,
        "create_cohort_prestart_backup",
        fail_backup,
        raising=False,
    )
    monkeypatch.setattr(live_script, "_create_adapters", forbidden_adapter)

    with pytest.raises(CohortPrestartBackupError, match="injected backup failure"):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )

    assert adapter_constructed is False


def test_changed_profile_requires_completed_prior_drain_before_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A profile change without exact drain evidence fails before SDK creation."""
    live_script = _load_module()
    base = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        base,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )
    backup = _backup_result(
        live_script,
        tmp_path,
        strategy_changed=True,
        previous_profile_fingerprint="c" * 64,
        previous_run_id="prior-run",
    )
    adapter_constructed = False
    monkeypatch.setattr(
        live_script,
        "discover_cohort_implementation_sources",
        lambda *_args: {"launcher": SCRIPT},
    )
    monkeypatch.setattr(
        live_script,
        "create_cohort_prestart_backup",
        lambda *_args, **_kwargs: backup,
    )
    monkeypatch.setattr(live_script, "_announce_backup", lambda _backup: None)

    def forbidden_adapter(*_args: object, **_kwargs: object) -> object:
        nonlocal adapter_constructed
        adapter_constructed = True
        raise AssertionError("adapter constructed without completed drain")

    monkeypatch.setattr(live_script, "_create_adapters", forbidden_adapter)

    with pytest.raises(CohortTransitionDrainError, match="completed drain archive"):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )

    assert adapter_constructed is False


def test_changed_profile_requires_exact_approval_before_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Completed drain evidence cannot substitute for operator change approval."""
    live_script = _load_module()
    previous = live_script.load_multi_asset_live_config(V25, mode="observe")
    base = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        base,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )
    backup = _backup_result(
        live_script,
        tmp_path,
        strategy_changed=True,
        previous_profile_fingerprint=previous.profile_fingerprint,
        previous_run_id="prior-run",
        previous_config_path=V25,
    )
    adapter_constructed = False
    monkeypatch.setattr(
        live_script,
        "discover_cohort_implementation_sources",
        lambda *_args: {"launcher": SCRIPT},
    )
    monkeypatch.setattr(
        live_script,
        "create_cohort_prestart_backup",
        lambda *_args, **_kwargs: backup,
    )
    monkeypatch.setattr(live_script, "_announce_backup", lambda _backup: None)
    monkeypatch.setattr(
        live_script,
        "_require_completed_profile_transition",
        lambda _config, _backup: None,
    )

    def forbidden_adapter(*_args: object, **_kwargs: object) -> object:
        nonlocal adapter_constructed
        adapter_constructed = True
        raise AssertionError("adapter constructed without exact approval")

    monkeypatch.setattr(live_script, "_create_adapters", forbidden_adapter)

    with pytest.raises(
        live_script.ProfileChangeApprovalError,
        match="changed profile requires an exact approval document",
    ):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )

    assert adapter_constructed is False


def test_changed_profile_requires_fresh_flat_order_free_venue_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Completed local evidence does not override current venue exposure."""
    live_script = _load_module()
    base = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        base,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )
    prior_profile = "c" * 64
    prior_run = "prior-run"
    backup = _backup_result(
        live_script,
        tmp_path,
        strategy_changed=True,
        previous_profile_fingerprint=prior_profile,
        previous_run_id=prior_run,
    )
    archive_root = tmp_path / "data/backups/bidirectional_cohort/transition_drains"
    marker = tmp_path / "prior-transition-drain.json"
    control = CohortTransitionDrain(
        path=marker,
        run_id=prior_run,
        profile_fingerprint=prior_profile,
        now_fn=lambda: live_script.datetime(2026, 8, 5, 12, tzinfo=live_script.UTC),
    )
    control.activate(
        request_id="d" * 32,
        requested_at_utc="2026-08-05T11:59:59+00:00",
    )
    control.complete()
    archive_completed_transition_drain(
        path=marker,
        archive_root=archive_root,
        expected_run_id=prior_run,
        now=live_script.datetime(2026, 8, 5, 12, tzinfo=live_script.UTC),
        confirmed=True,
    )
    adapters = {
        asset.symbol: Mock(
            reconcile=Mock(
                return_value=SimpleNamespace(
                    position=SimpleNamespace(size_signed=0.0),
                    open_orders=(),
                )
            )
        )
        for asset in config.assets
    }
    adapters["ETH"].reconcile.return_value = SimpleNamespace(
        position=SimpleNamespace(size_signed=-0.2),
        open_orders=(SimpleNamespace(oid=202),),
    )
    engines_created = False
    monkeypatch.setattr(
        live_script,
        "discover_cohort_implementation_sources",
        lambda *_args: {"launcher": SCRIPT},
    )
    monkeypatch.setattr(
        live_script,
        "create_cohort_prestart_backup",
        lambda *_args, **_kwargs: backup,
    )
    monkeypatch.setattr(live_script, "_announce_backup", lambda _backup: None)
    monkeypatch.setattr(
        live_script,
        "require_approved_profile_change",
        lambda _config, _backup: None,
    )
    monkeypatch.setattr(
        live_script,
        "_create_adapters",
        lambda _config: SimpleNamespace(by_symbol=adapters),
    )
    boundary = live_script._verify_profile_transition_venue_boundary
    monkeypatch.setattr(
        live_script,
        "_verify_profile_transition_venue_boundary",
        lambda current, current_backup, current_adapters: boundary(
            current,
            current_backup,
            current_adapters,
            previous_config=current,
        ),
    )

    def forbidden_engines(*_args: object, **_kwargs: object) -> object:
        nonlocal engines_created
        engines_created = True
        raise AssertionError("engines created across non-flat boundary")

    monkeypatch.setattr(live_script, "_create_engines", forbidden_engines)

    with pytest.raises(
        CohortTransitionDrainError, match="ETH.*not flat and order-free"
    ):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )

    assert engines_created is False


def test_changed_profile_with_completed_drain_and_flat_boundary_reaches_engines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Exact drain evidence plus fresh venue-flat reads authorizes assembly."""
    live_script = _load_module()
    base = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        base,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )
    prior_profile = "c" * 64
    prior_run = "prior-run"
    backup = _backup_result(
        live_script,
        tmp_path,
        strategy_changed=True,
        previous_profile_fingerprint=prior_profile,
        previous_run_id=prior_run,
    )
    marker = tmp_path / "prior-transition-drain.json"
    control = CohortTransitionDrain(
        path=marker,
        run_id=prior_run,
        profile_fingerprint=prior_profile,
        now_fn=lambda: live_script.datetime(2026, 8, 5, 12, tzinfo=live_script.UTC),
    )
    control.activate(
        request_id="e" * 32,
        requested_at_utc="2026-08-05T11:59:59+00:00",
    )
    control.complete()
    archive_completed_transition_drain(
        path=marker,
        archive_root=(tmp_path / "data/backups/bidirectional_cohort/transition_drains"),
        expected_run_id=prior_run,
        now=live_script.datetime(2026, 8, 5, 12, tzinfo=live_script.UTC),
        confirmed=True,
    )
    adapters = {
        asset.symbol: Mock(
            reconcile=Mock(
                return_value=SimpleNamespace(
                    position=SimpleNamespace(size_signed=0.0),
                    open_orders=(),
                )
            )
        )
        for asset in config.assets
    }
    monkeypatch.setattr(
        live_script,
        "discover_cohort_implementation_sources",
        lambda *_args: {"launcher": SCRIPT},
    )
    monkeypatch.setattr(
        live_script,
        "create_cohort_prestart_backup",
        lambda *_args, **_kwargs: backup,
    )
    monkeypatch.setattr(live_script, "_announce_backup", lambda _backup: None)
    monkeypatch.setattr(
        live_script,
        "require_approved_profile_change",
        lambda _config, _backup: None,
    )
    monkeypatch.setattr(
        live_script,
        "_create_adapters",
        lambda _config: SimpleNamespace(by_symbol=adapters),
    )
    boundary = live_script._verify_profile_transition_venue_boundary
    monkeypatch.setattr(
        live_script,
        "_verify_profile_transition_venue_boundary",
        lambda current, current_backup, current_adapters: boundary(
            current,
            current_backup,
            current_adapters,
            previous_config=current,
        ),
    )

    def stop_at_engines(*_args: object, **_kwargs: object) -> object:
        assert all(adapter.reconcile.call_count == 1 for adapter in adapters.values())
        raise RuntimeError("authorized through boundary")

    monkeypatch.setattr(live_script, "_create_engines", stop_at_engines)

    with pytest.raises(RuntimeError, match="authorized through boundary"):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )


def test_locked_start_refuses_uncleared_transition_before_backup_or_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A prior drain cannot be silently discarded by a new live process."""
    live_script = _load_module()
    config = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    backup_attempted = False
    adapter_attempted = False

    def refuse(_path: Path) -> None:
        raise CohortTransitionDrainError("inspect and archive prior drain")

    def forbidden_backup(*_args: object, **_kwargs: object) -> object:
        nonlocal backup_attempted
        backup_attempted = True
        raise AssertionError("backup ran after stale drain")

    def forbidden_adapter(*_args: object, **_kwargs: object) -> object:
        nonlocal adapter_attempted
        adapter_attempted = True
        raise AssertionError("adapter ran after stale drain")

    monkeypatch.setattr(live_script, "ensure_transition_drain_startable", refuse)
    monkeypatch.setattr(live_script, "create_cohort_prestart_backup", forbidden_backup)
    monkeypatch.setattr(live_script, "_create_adapters", forbidden_adapter)

    with pytest.raises(CohortTransitionDrainError, match="inspect and archive"):
        live_script._run_locked(
            _args(enabled=True, i_accept_live_risk=True),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )

    assert backup_attempted is False
    assert adapter_attempted is False


def test_explicit_recovery_backs_up_then_rebinds_active_drain_before_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A crash-interrupted drain resumes as a new run without admitting entries."""
    live_script = _load_module()
    base = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        base,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )
    state = config.cohort_ledger.parent / "transition_drain.json"
    old_run = "bidirectional-live-1785934800000"
    control = CohortTransitionDrain(
        path=state,
        run_id=old_run,
        profile_fingerprint=config.profile_fingerprint,
        now_fn=lambda: live_script.datetime(2026, 8, 5, 12, tzinfo=live_script.UTC),
    )
    control.activate(
        request_id="d" * 32,
        requested_at_utc="2026-08-05T11:59:59+00:00",
    )
    events: list[str] = []
    backup = live_script.CohortPrestartBackupResult(
        path=tmp_path / "backup",
        manifest_path=tmp_path / "backup/manifest.json",
        manifest_sha256="a" * 64,
        strategy_changed=False,
        implementation_file_count=1,
        implementation_sha256="b" * 64,
    )

    def capture_backup(*_args: object, **_kwargs: object) -> object:
        events.append("backup")
        return backup

    def stop_at_adapter(*_args: object, **_kwargs: object) -> object:
        events.append("adapter")
        snapshot = load_transition_drain_snapshot(state)
        assert snapshot.run_id != old_run
        assert snapshot.origin_run_id == old_run
        assert snapshot.resume_count == 1
        raise RuntimeError("stop after recovery binding")

    monkeypatch.setattr(
        live_script,
        "discover_cohort_implementation_sources",
        lambda *_args: {"launcher": SCRIPT},
    )
    monkeypatch.setattr(live_script, "create_cohort_prestart_backup", capture_backup)
    monkeypatch.setattr(live_script, "_announce_backup", lambda _backup: None)
    monkeypatch.setattr(live_script, "_create_adapters", stop_at_adapter)

    with pytest.raises(RuntimeError, match="stop after recovery binding"):
        live_script._run_locked(
            _args(
                enabled=True,
                i_accept_live_risk=True,
                resume_transition_drain=True,
            ),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )

    assert events == ["backup", "adapter"]


def test_recovery_backup_failure_preserves_the_prior_drain_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failed backup cannot partially migrate crash-recovery authority."""
    live_script = _load_module()
    base = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        base,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )
    state = config.cohort_ledger.parent / "transition_drain.json"
    old_run = "bidirectional-live-1785934800000"
    control = CohortTransitionDrain(
        path=state,
        run_id=old_run,
        profile_fingerprint=config.profile_fingerprint,
        now_fn=lambda: live_script.datetime(2026, 8, 5, 12, tzinfo=live_script.UTC),
    )
    control.activate(
        request_id="d" * 32,
        requested_at_utc="2026-08-05T11:59:59+00:00",
    )
    monkeypatch.setattr(
        live_script,
        "discover_cohort_implementation_sources",
        lambda *_args: {"launcher": SCRIPT},
    )

    def fail_backup(*_args: object, **_kwargs: object) -> object:
        raise CohortPrestartBackupError("injected recovery backup failure")

    monkeypatch.setattr(
        live_script,
        "create_cohort_prestart_backup",
        fail_backup,
    )

    with pytest.raises(CohortPrestartBackupError, match="recovery backup failure"):
        live_script._run_locked(
            _args(
                enabled=True,
                i_accept_live_risk=True,
                resume_transition_drain=True,
            ),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )

    snapshot = load_transition_drain_snapshot(state)
    assert snapshot.run_id == old_run
    assert snapshot.resume_count == 0


def test_locked_start_snapshots_discovered_implementation_before_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The armed boundary supplies the complete source set to its backup gate."""
    live_script = _load_module()
    loaded = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        loaded,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )
    provider_root = tmp_path / "backtest_lab"
    expected = {"provider_0000": tmp_path / "provider.py"}
    discovered: dict[str, Path] = {}
    adapter_constructed = False

    def discover(repository: Path, provider: Path) -> dict[str, Path]:
        assert repository == SCRIPT.parents[1].resolve()
        assert provider == provider_root.resolve()
        discovered.update(expected)
        return expected

    def capture_backup(
        *_args: object,
        implementation_sources: dict[str, Path] | None = None,
        **_kwargs: object,
    ) -> object:
        assert implementation_sources == expected
        raise CohortPrestartBackupError("stop after implementation capture")

    def forbidden_adapter(*_args: object, **_kwargs: object) -> object:
        nonlocal adapter_constructed
        adapter_constructed = True
        raise AssertionError("adapter constructed before source backup")

    monkeypatch.setattr(
        live_script,
        "discover_cohort_implementation_sources",
        discover,
        raising=False,
    )
    monkeypatch.setattr(live_script, "create_cohort_prestart_backup", capture_backup)
    monkeypatch.setattr(live_script, "_create_adapters", forbidden_adapter)

    with pytest.raises(CohortPrestartBackupError, match="implementation capture"):
        live_script._run_locked(
            _args(
                backtest_lab_root=provider_root,
                enabled=True,
                i_accept_live_risk=True,
            ),
            config,
            live_script.CredentialPresence(True, True),
            Mock(),
        )

    assert discovered == expected
    assert adapter_constructed is False


def test_live_engines_refresh_coalesced_truth_during_consistency_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each live engine wires its adapter's explicit cache invalidator."""
    live_script = _load_module()
    config = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    adapters = {asset.symbol: Mock() for asset in config.assets}
    captured: dict[str, dict[str, object]] = {}

    def capture_engine(**kwargs: object) -> object:
        asset = kwargs["config"]
        captured[asset.symbol] = kwargs
        return object()

    monkeypatch.setattr(live_script, "SolRangeOnsetLiveEngine", capture_engine)
    monkeypatch.setattr(live_script, "_ledger", lambda *_args: object())

    live_script._create_engines(
        config,
        SimpleNamespace(by_symbol=adapters),
        live_script.CredentialPresence(True, True),
        "test-run",
    )

    assert set(captured) == set(adapters)
    for symbol, adapter in adapters.items():
        assert (
            captured[symbol]["reconciliation_cache_invalidator"]
            == adapter.invalidate_reconciliation_cache
        )


def test_backup_announcement_includes_implementation_identity(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The operator can independently match the code snapshot at startup."""
    live_script = _load_module()
    result = live_script.CohortPrestartBackupResult(
        path=tmp_path / "bundle",
        manifest_path=tmp_path / "bundle/manifest.json",
        manifest_sha256="manifest-sha",
        strategy_changed=True,
        implementation_file_count=1156,
        implementation_sha256="implementation-sha",
    )

    live_script._announce_backup(result)

    output = capsys.readouterr().out
    assert "implementation_files=1156" in output
    assert "implementation_sha256=implementation-sha" in output


def test_live_telemetry_receives_verified_backup_identity(
    tmp_path: Path,
) -> None:
    """Launcher plumbing carries backup provenance into configuration journal."""
    live_script = _load_module()
    base = live_script.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        base,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )
    bundle = tmp_path / "bundle"
    backup = live_script.CohortPrestartBackupResult(
        path=bundle,
        manifest_path=bundle / "manifest.json",
        manifest_sha256="a" * 64,
        strategy_changed=True,
        implementation_file_count=1_156,
        implementation_sha256="b" * 64,
    )
    drain = CohortTransitionDrain(
        path=tmp_path / "transition_drain.json",
        run_id="test-run",
        profile_fingerprint=config.profile_fingerprint,
        now_fn=lambda: live_script.datetime.now(live_script.UTC),
    )

    telemetry = live_script._create_telemetry(
        config,
        {},
        "test-run",
        backup,
        drain,
    )
    telemetry.emit_configuration()

    row = json.loads(config.cohort_ledger.read_text().splitlines()[0])
    assert row["payload"]["prestart_backup"]["manifest_sha256"] == "a" * 64
    assert row["payload"]["prestart_backup"]["implementation_sha256"] == "b" * 64
