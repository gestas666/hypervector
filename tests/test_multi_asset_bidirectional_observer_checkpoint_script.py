"""CLI boundary tests for the disarmed observer checkpoint sidecar."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "multi_asset_bidirectional_observer_checkpoint.py"
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
