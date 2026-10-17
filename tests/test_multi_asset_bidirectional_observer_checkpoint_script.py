"""CLI boundary tests for the disarmed observer checkpoint sidecar."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

SCRIPT = (
    Path(__file__).parents[1]
    / "src" / "hypervector" / "operations" / 'multi_asset_bidirectional_observer_checkpoint.py'
)


def _load_module() -> ModuleType:
    spec = spec_from_file_location("multi_asset_observer_checkpoint_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_once_publishes_one_execution_incapable_checkpoint(tmp_path: Path) -> None:
    """The deterministic observer path forwards no strategy authority."""
    module = _load_module()
    output = tmp_path / "latest.json"
    calls: list[tuple[Path, Path, str | None]] = []

    def publish(ledger: Path, out: Path, *, run_id: str | None) -> dict[str, object]:
        calls.append((ledger, out, run_id))
        return {"status": "ready"}

    args = module.build_parser().parse_args(
        [
            "--decisions",
            str(tmp_path / "decisions.jsonl"),
            "--out",
            str(output),
            "--run-id",
            "observer-a",
            "--once",
        ]
    )

    assert module.run_checkpoint_loop(args, publish_fn=publish) == 0
    assert calls == [(tmp_path / "decisions.jsonl", output, "observer-a")]
    source = SCRIPT.read_text(encoding="utf-8")
    assert "submit_market" not in source
    assert "create_armed" not in source
    assert "private_key" not in source


def test_once_publishes_explicit_unavailable_status(tmp_path: Path) -> None:
    """Missing observer evidence is visible and returns a failing status."""
    module = _load_module()
    output = tmp_path / "latest.json"

    def missing(
        _ledger: Path,
        _out: Path,
        *,
        run_id: str | None,
    ) -> dict[str, object]:
        del run_id
        raise FileNotFoundError("observer ledger not ready")

    args = module.build_parser().parse_args(
        ["--decisions", str(tmp_path / "missing.jsonl"), "--out", str(output), "--once"]
    )

    assert module.run_checkpoint_loop(args, publish_fn=missing) == 2
    status = json.loads(output.read_text(encoding="utf-8"))
    assert status["mode"] == "multi_asset_bidirectional_observer_checkpoint"
    assert status["status"] == {
        "state": "unavailable",
        "technical_issue": "observer ledger not ready",
    }
    assert status["checkpoint_contract"]["execution_authority"] == "none"


def test_main_treats_operator_interrupt_as_a_clean_stop() -> None:
    """Ctrl-C exits with the conventional status without a traceback."""
    module = _load_module()

    def interrupted(_args: object) -> int:
        raise KeyboardInterrupt

    original = module.run_checkpoint_loop
    module.run_checkpoint_loop = interrupted
    try:
        assert module.main([]) == 130
    finally:
        module.run_checkpoint_loop = original


def test_defaults_read_the_paper_ledger_and_write_the_observer_directory() -> None:
    """The observer never reads the live ledger or overwrites the live checkpoint."""
    module = _load_module()
    args = module.build_parser().parse_args([])
    assert args.decisions == Path("data/paper/cohort/decisions.jsonl")
    assert args.out == Path("data/runtime/cohort_observer/latest_checkpoint.json")


def test_an_out_owned_by_a_live_checkpoint_writer_is_refused(
    tmp_path: Path, capsys
) -> None:
    """A live checkpoint writer's output can never be overwritten by the observer."""
    from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

    module = _load_module()
    output = tmp_path / "latest_checkpoint.json"
    calls: list[object] = []
    module.run_checkpoint_loop = lambda args: calls.append(args) or 0
    with cohort_checkpoint_runtime_lock(output):
        assert module.main(["--out", str(output), "--once"]) == 2
    assert calls == []
    assert not output.exists()
    assert "active live checkpoint writer" in capsys.readouterr().err
    # Once the live writer is gone the same output is accepted.
    assert module.main(["--out", str(output), "--once"]) == 0
    assert len(calls) == 1


def test_a_live_writer_cannot_take_the_output_while_the_observer_runs(
    tmp_path: Path,
) -> None:
    """A live writer that starts after the observer began is refused, not raced.

    The observer owns the output's writer lock for its whole loop, so the
    check-then-publish window that let a (re)starting writer be overwritten no
    longer exists.
    """
    import pytest

    from hypervector.runtime_lock import (
        RuntimeLockError,
        cohort_checkpoint_runtime_lock,
    )

    module = _load_module()
    output = tmp_path / "latest_checkpoint.json"
    published: list[Path] = []
    refusals: list[str] = []

    class Stop(Exception):
        pass

    def publish(_ledger: Path, out: Path, *, run_id: str | None) -> dict[str, object]:
        published.append(out)
        return {"status": "ready"}

    def live_writer_starts(_seconds: float) -> None:
        # The live checkpoint writer (re)starts between two observer publications.
        try:
            with cohort_checkpoint_runtime_lock(output):
                pass
        except RuntimeLockError as exc:
            refusals.append(str(exc))
        raise Stop

    args = module.build_parser().parse_args(
        ["--out", str(output), "--interval-seconds", "1"]
    )
    with pytest.raises(Stop):
        module.run_checkpoint_loop(
            args, publish_fn=publish, sleep_fn=live_writer_starts
        )
    assert published == [output]
    assert len(refusals) == 1
    # Released when the loop ends: the writer can then take the output.
    with cohort_checkpoint_runtime_lock(output):
        pass
