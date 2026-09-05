"""Publication tests for the exact-route lifecycle watcher."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from collections.abc import Iterator
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest


_SCRIPT = Path("scripts/cohort_route_lifecycle_watch.py")


def test_route_lifecycle_watcher_script_exists() -> None:
    """The prospective route investigation needs durable automation."""
    assert _SCRIPT.is_file()


def test_quiet_poll_writes_only_mutable_report_only_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A quiet route must not manufacture a completed immutable artifact."""
    module = _load_script()
    args = _args(tmp_path)
    monkeypatch.setattr(module, "build_route_lifecycle_status", _quiet_report)

    result = module.capture_once(args)

    assert result["state"] == "awaiting_both_sides"
    assert json.loads(args.status.read_text()) == result
    assert not args.final_out.exists()


def test_completed_poll_writes_one_source_hashed_immutable_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both resolved sides must freeze the exact consumed checkpoint bytes."""
    module = _load_script()
    args = _args(tmp_path)
    monkeypatch.setattr(module, "build_route_lifecycle_status", _complete_report)

    first = module.capture_once(args)
    first_final = args.final_out.read_bytes()
    second = module.capture_once(args)

    final = json.loads(first_final)
    assert first["state"] == "diagnostic_minimum_complete"
    assert second["state"] == "already_complete"
    assert args.final_out.read_bytes() == first_final
    assert final["contract"]["execution_authority"] == "none"
    assert final["source_evidence"]["checkpoint"]["sha256"]
    assert final["source_evidence"]["preregistration"]["sha256"]
    assert final["generator_identity"][0]["sha256"]
    assert final["result"]["minimum_diagnostic_evidence_met"] is True


def test_generator_change_after_preregistration_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changed tracker code cannot publish under a frozen evidence identity."""
    module = _load_script()
    args = _args(tmp_path)
    generator = tmp_path / "generator.py"
    generator.write_text("changed\n")
    monkeypatch.setattr(module, "build_route_lifecycle_status", _quiet_report)

    with pytest.raises(ValueError, match="generator evidence"):
        module.capture_once(args)


def test_generator_change_during_completed_poll_prevents_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mid-poll source change must be detected before immutable writing."""
    module = _load_script()
    args = _args(tmp_path)
    generator = tmp_path / "generator.py"

    def mutate_then_complete(*_args: object, **_kwargs: object) -> dict[str, object]:
        generator.write_text("changed during poll\n")
        return _complete_report()

    monkeypatch.setattr(module, "build_route_lifecycle_status", mutate_then_complete)

    with pytest.raises(ValueError, match="generator evidence"):
        module.capture_once(args)
    assert not args.final_out.exists()


def test_parser_has_no_live_arming_or_order_surface() -> None:
    """The watcher command must be structurally execution-incapable."""
    module = _load_script()
    destinations = {action.dest for action in module.build_parser()._actions}

    assert "enabled" not in destinations
    assert "i_accept_live_risk" not in destinations
    assert "wallet" not in destinations
    assert "private_key" not in destinations


def test_main_holds_singleton_status_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only one writer may own a route's mutable progress status."""
    module = _load_script()
    events: list[object] = []

    @contextmanager
    def lock(path: Path) -> Iterator[Path]:
        events.append(("lock", path))
        yield path.with_name(f"{path.name}.writer.lock")
        events.append("unlock")

    monkeypatch.setattr(module, "cohort_checkpoint_runtime_lock", lock)
    monkeypatch.setattr(module, "run_watcher", lambda args: events.append("run") or 0)

    assert module.main(_argv(tmp_path)) == 0
    assert events == [("lock", tmp_path / "status.json"), "run", "unlock"]


def test_continuous_watcher_retries_transient_checkpoint_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A temporary mixed checkpoint must not terminate continuous collection."""
    module = _load_script()
    args = _args(tmp_path)
    args.once = False
    args.max_cycles = 1
    calls = 0
    sleeps: list[float] = []

    def capture(_: argparse.Namespace) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError(
                "route lifecycle tracker requires a consistent live runtime"
            )
        return _quiet_report()

    monkeypatch.setattr(module, "capture_once", capture)

    result = module.run_watcher(args, sleep_fn=sleeps.append)

    assert result == 0
    assert calls == 2
    assert sleeps == [15.0]


def _load_script() -> ModuleType:
    spec = spec_from_file_location("cohort_route_lifecycle_watch", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(tmp_path: Path) -> argparse.Namespace:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text("{}")
    generator = tmp_path / "generator.py"
    generator.write_text("frozen\n")
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text(json.dumps(_preregistration(generator)))
    return argparse.Namespace(
        checkpoint=checkpoint,
        preregistration=preregistration,
        status=tmp_path / "status.json",
        final_out=tmp_path / "final.json",
        run_id="run-1",
        profile_id="profile-1",
        profile_fingerprint="a" * 64,
        provider_id="provider-1",
        signal_strategy_id="signal-1",
        symbol="HYPE",
        required_side=["long", "short"],
        maximum_checkpoint_age_seconds=180.0,
        interval_seconds=30.0,
        max_cycles=0,
        once=True,
    )


def _argv(tmp_path: Path) -> list[str]:
    args = _args(tmp_path)
    return [
        "--checkpoint",
        str(args.checkpoint),
        "--preregistration",
        str(args.preregistration),
        "--status",
        str(args.status),
        "--final-out",
        str(args.final_out),
        "--run-id",
        args.run_id,
        "--profile-id",
        args.profile_id,
        "--profile-fingerprint",
        args.profile_fingerprint,
        "--provider-id",
        args.provider_id,
        "--signal-strategy-id",
        args.signal_strategy_id,
        "--symbol",
        args.symbol,
        "--required-side",
        "long",
        "--required-side",
        "short",
        "--once",
    ]


def _quiet_report(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_exact_route_lifecycle_evidence",
        "state": "awaiting_both_sides",
        "contract": _contract(),
        "identity": _identity(),
        "minimum_diagnostic_evidence_met": False,
    }


def _complete_report(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {
        **_quiet_report(),
        "state": "diagnostic_minimum_complete",
        "minimum_diagnostic_evidence_met": True,
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "orders_or_fills_assumed": False,
        "promotion_authority": "none",
    }


def _identity() -> dict[str, object]:
    return {
        "run_id": "run-1",
        "profile_id": "profile-1",
        "profile_fingerprint": "a" * 64,
        "provider_id": "provider-1",
        "signal_strategy_id": "signal-1",
        "symbol": "HYPE",
        "route": "provider-1|HYPE",
        "required_sides": ["long", "short"],
    }


def _preregistration(generator: Path) -> dict[str, object]:
    raw = generator.read_bytes()
    return {
        "schema_version": 1,
        "mode": "v57_exact_route_lifecycle_tracker_preregistration",
        "hypothesis_id": "v57-hype-alignment-both-side-live-lifecycle-v1",
        "live_identity": _identity(),
        "prospective_boundary": {
            "capture_start_ms": 800,
            "baseline_route_evaluations": 300,
            "baseline_eligible_evaluations": 0,
        },
        "implementation_evidence": [
            {
                "path": str(generator),
                "bytes": len(raw),
                "sha256": sha256(raw).hexdigest(),
            }
        ],
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
        },
    }
