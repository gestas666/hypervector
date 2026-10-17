"""Bounded-memory checkpoint regression tests for live profile transitions."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from hypervector.live import canary_supervisor
from hypervector.live.cohort_process_commands import audit_command, checkpoint_command
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research import cohort_rolling_checkpoint

CHECKPOINT_SCRIPT = (
    Path(__file__).parents[1]
    / "src" / "hypervector" / "operations" / 'multi_asset_bidirectional_live_checkpoint.py'
)
V66_CONFIG = Path(
    "tests/fixtures/profiles/multi_asset_growth_first_5000_four_asset_brentoil_retired_candidate_v66.toml"
)


_CHECKPOINT_CONFIG = ["--config", "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml"]


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
        config_path=tmp_path / "v66.toml",
        once=False,
        venue_portfolio=None,
        opportunity_matrix_path=None,
        supplemental_opportunity_matrix_paths=(),
        eligible_policy_forward=False,
        funding_evidence_fn=None,
        portfolio_archive=None,
        asymmetric_forward_journal_path=None,
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
        module._run_once(args, lambda *_args: {}, publish, None, None, lambda _: None)
        == 0
    )
    assert forwarded[0]["current_run_only"] is True


def test_live_checkpoint_command_is_always_current_run_bounded() -> None:
    """Continuous live checkpoint publication must not replay the multi-gigabyte ledger."""
    config = load_multi_asset_live_config(V66_CONFIG, mode="observe")

    command = checkpoint_command(config)

    assert "--current-run-only" in command


def test_live_audit_command_is_current_run_bounded() -> None:
    """Stopped backend audit must not replay all historical cohort ledgers."""
    config = load_multi_asset_live_config(V66_CONFIG, mode="observe")

    command = audit_command(config)

    scope = command.index("--history-scope")
    assert command[scope + 1] == "current-run"




def test_startup_capture_streams_without_materializing_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backend supervision must retain identities, not the full ledger bytes."""
    ledger = tmp_path / "decisions.jsonl"
    rows = [
        {"sequence": 1, "run_id": "run-a"},
        {"sequence": 2, "run_id": "run-b"},
    ]
    ledger.write_text(
        "".join(f"{json.dumps(row)}\n" for row in rows),
        encoding="utf-8",
    )

    def refuse_materialization(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("startup capture materialized the complete ledger")

    monkeypatch.setattr(canary_supervisor, "_read_bytes", refuse_materialization)

    snapshot = canary_supervisor.capture_ledger_start(ledger)

    assert snapshot.initial_size == ledger.stat().st_size
    assert snapshot.prior_run_ids == frozenset(("run-a", "run-b"))
