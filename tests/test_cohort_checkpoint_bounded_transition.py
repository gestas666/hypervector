"""Bounded-memory checkpoint regression tests for live profile transitions."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from hypervector.research import cohort_rolling_checkpoint

CHECKPOINT_SCRIPT = (
    Path(__file__).parents[1]
    / "src" / "hypervector" / "operations" / 'multi_asset_bidirectional_live_checkpoint.py'
)

_CHECKPOINT_CONFIG = ["--config", "tests/fixtures/profiles/cohort_base.toml"]


def _load_checkpoint_script() -> ModuleType:
    """Load the checkpoint entry point without executing its CLI."""
    spec = spec_from_file_location("bounded_transition_checkpoint", CHECKPOINT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module




def _complete_checkpoint(path: Path, profile_fingerprint: str) -> None:
    """Write the minimum complete cached checkpoint with an exact run identity."""
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "multi_asset_bidirectional_live_checkpoint",
                "checkpoint_contract": {
                    "report_only": True,
                    "execution_authority": "none",
                },
                "lifecycle": {"state": "running_consistent"},
                "audit": {
                    "run": {
                        "run_id": "run-old",
                        "profile_fingerprint": profile_fingerprint,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_changed_profile_seeds_current_run_without_full_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale prior-profile cache must not trigger an unbounded full replay."""
    checkpoint = tmp_path / "latest.json"
    _complete_checkpoint(checkpoint, "a" * 64)
    monkeypatch.setattr(
        cohort_rolling_checkpoint,
        "load_configuration_expectation",
        lambda _path: SimpleNamespace(profile_fingerprint="b" * 64),
        raising=False,
    )
    forwarded: list[dict[str, object]] = []

    def publish(_root: Path, _out: Path, **kwargs: object) -> dict[str, object]:
        forwarded.append(dict(kwargs))
        return {"status": "ready"}

    cohort_rolling_checkpoint.publish_rolling_checkpoint(
        publish,
        tmp_path / "ledgers",
        checkpoint,
        requested_run_id="run-new",
        config_path=tmp_path / "profile.toml",
        once=False,
        venue_portfolio=None,
        portfolio_archive=None,
    )

    assert len(forwarded) == 1
    assert forwarded[0]["current_run_only"] is True
    assert forwarded[0]["compatible_execution_history"] is False
    assert forwarded[0]["complete_historical_checkpoint"] is None


def test_once_flag_can_force_a_bounded_current_run_checkpoint(tmp_path: Path) -> None:
    """Final checkpoint publication exposes an explicit bounded-memory mode."""
    module = _load_checkpoint_script()
    forwarded: list[dict[str, object]] = []

    def publish(_root: Path, _out: Path, **kwargs: object) -> dict[str, object]:
        forwarded.append(dict(kwargs))
        return {"status": "ready"}

    module.publish_live_checkpoint = publish
    args = module.build_parser().parse_args(_CHECKPOINT_CONFIG + [
            "--out",
            str(tmp_path / "latest.json"),
            "--run-id",
            "run-new",
            "--once",
            "--current-run-only",
        ]
    )

    assert (
        module._run_once(args, lambda *_args: {}, publish, None, lambda _: None)
        == 0
    )
    assert forwarded[0]["current_run_only"] is True
