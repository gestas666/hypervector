"""CLI contracts for the exact-profile v39 forward evidence monitor."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from hashlib import sha256
import json
import math
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v39_forward_evidence_monitor.py")
_CONFIG = Path(
    "configs/"
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)


def test_once_publishes_atomic_source_bound_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid exact-profile build binds checkpoint and config evidence."""
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "latest.json"
    _write_checkpoint(checkpoint, {"marker": 39})
    monkeypatch.setattr(module, "build_v39_forward_evidence", _success_builder)
    args = _args(module, checkpoint, _CONFIG, output)

    assert module.run_monitor(args, sleep_fn=lambda _: None) == 0
    persisted = json.loads(output.read_text())
    assert persisted["evidence"]["checkpoint"]["sha256"]
    assert persisted["evidence"]["config"]["sha256"]
    assert persisted["material_state_sha256"]
    assert persisted["contract"]["execution_authority"] == "none"


def test_identity_failure_preserves_last_good_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A v35 checkpoint cannot overwrite the last exact v39 snapshot."""
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "latest.json"
    checkpoint.write_text(
        json.dumps(
            {
                "checkpoint_contract": {
                    "report_only": True,
                    "execution_authority": "none",
                    "runtime_strategy_changed": False,
                },
                "audit": {},
            }
        )
    )
    output.write_text('{"last":"good-v39"}\n')

    def fail_identity(
        payload: object,
        config: object,
        *,
        observed_at: object,
    ) -> dict[str, object]:
        raise ValueError("v39 forward evidence profile identity does not match runtime")

    monkeypatch.setattr(module, "build_v39_forward_evidence", fail_identity)
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--config",
            str(_CONFIG),
            "--out",
            str(output),
            "--once",
        ]
    )

    assert module.run_monitor(args, sleep_fn=lambda _: None) == 2
    assert json.loads(output.read_text()) == {"last": "good-v39"}


@pytest.mark.parametrize("alias", ["checkpoint", "config"])
def test_output_cannot_alias_an_evidence_input(tmp_path: Path, alias: str) -> None:
    """The monitor must reject destructive output paths before reading inputs."""
    module = _module()
    checkpoint = tmp_path / "missing-checkpoint.json"
    config = tmp_path / "missing-config.toml"
    output = checkpoint if alias == "checkpoint" else config
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--config",
            str(config),
            "--out",
            str(output),
            "--once",
        ]
    )

    with pytest.raises(ValueError, match="output must differ"):
        module.run_monitor(args, sleep_fn=lambda _: None)


@pytest.mark.parametrize("interval", [math.nan, math.inf, -math.inf])
def test_monitor_rejects_nonfinite_interval(
    tmp_path: Path,
    interval: float,
) -> None:
    """Polling must fail fast instead of passing nonfinite values to sleep."""
    module = _module()
    args = _args(
        module,
        tmp_path / "checkpoint.json",
        tmp_path / "config.toml",
        tmp_path / "latest.json",
    )
    args.interval_seconds = interval

    with pytest.raises(ValueError, match="finite and positive"):
        module.run_monitor(args, sleep_fn=lambda _: None)


def test_config_hash_and_parser_consume_the_same_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A concurrent config mutation cannot separate parsed identity from its hash."""
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    config = tmp_path / "v39.toml"
    output = tmp_path / "latest.json"
    original = _CONFIG.read_bytes()
    config.write_bytes(original)
    checkpoint.write_text(json.dumps({"audit": {}}))
    real_loader = module.load_multi_asset_live_config

    def mutating_loader(path: Path, **kwargs: object) -> object:
        config.write_text("not valid toml = [")
        assert Path(path).resolve() != config.resolve()
        assert kwargs == {
            "mode": "observe",
            "enabled": False,
            "accepts_live_risk": False,
        }
        return real_loader(path, **kwargs)

    monkeypatch.setattr(module, "load_multi_asset_live_config", mutating_loader)
    monkeypatch.setattr(module, "build_v39_forward_evidence", _success_builder)
    args = _args(module, checkpoint, config, output)

    assert module.run_monitor(args, sleep_fn=lambda _: None) == 0
    persisted = json.loads(output.read_text())
    assert persisted["evidence"]["config"]["sha256"] == sha256(original).hexdigest()


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v39 forward evidence monitor script is missing")
    spec = spec_from_file_location("v39_forward_evidence_monitor_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v39 forward evidence monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(
    module: ModuleType,
    checkpoint: Path,
    config: Path,
    output: Path,
) -> object:
    return module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--config",
            str(config),
            "--out",
            str(output),
            "--once",
        ]
    )


def _write_checkpoint(path: Path, audit: dict[str, object]) -> None:
    path.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-08-11T10:00:00+00:00",
                "checkpoint_contract": {
                    "report_only": True,
                    "execution_authority": "none",
                    "runtime_strategy_changed": False,
                },
                "audit": audit,
            }
        )
    )


def _success_builder(
    payload: dict[str, object],
    config: object,
    *,
    observed_at: object,
) -> dict[str, object]:
    assert isinstance(payload["audit"], dict)
    assert getattr(config, "profile_id").endswith("v39")
    assert observed_at is not None
    return {
        "contract": {"report_only": True, "execution_authority": "none"},
        "source": {"run_id": "run-v39"},
        "summary": {"closed_trades": 0},
    }
