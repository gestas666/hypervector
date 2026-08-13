"""CLI contracts for the rolling portfolio-improvement digest."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_improvement_monitor.py"


def test_once_publishes_source_bound_report_only_digest(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    """One refresh must atomically bind the source checkpoint evidence."""
    module = _load()
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "latest.json"
    overrides = tmp_path / "overrides.json"
    checkpoint.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-08-09T20:00:00+00:00",
                "checkpoint_contract": {
                    "report_only": True,
                    "execution_authority": "none",
                    "runtime_strategy_changed": False,
                },
                "audit": {"marker": 7},
            }
        )
    )
    overrides.write_text(
        json.dumps(
            {
                "contract": {
                    "report_only": True,
                    "execution_authority": "none",
                    "automatic_promotion": False,
                    "runtime_strategy_changed": False,
                },
                "routes": {},
                "evidence": [],
            }
        )
    )

    def fake_digest(
        audit: dict[str, object],
        *,
        experiment_overrides: dict[str, object],
    ) -> dict[str, object]:
        assert experiment_overrides["routes"] == {}
        return {
            "contract": {"report_only": True, "execution_authority": "none"},
            "marker": audit["marker"],
            "assessment": {"top_research_priority": "route|SYMBOL"},
            "performance": {"closed_trades": 3},
        }

    monkeypatch.setattr(
        module,
        "build_cohort_improvement_digest",
        fake_digest,
    )
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--out",
            str(output),
            "--decision-overrides",
            str(overrides),
            "--once",
        ]
    )

    assert module.run_monitor(args, sleep_fn=lambda seconds: None) == 0
    persisted = json.loads(output.read_text())
    assert persisted["marker"] == 7
    assert persisted["source_checkpoint_generated_at_utc"] == (
        "2026-08-09T20:00:00+00:00"
    )
    assert persisted["evidence"]["checkpoint"]["sha256"]
    assert persisted["evidence"]["decision_overrides"]["sha256"]
    assert persisted["material_state_sha256"]


def test_failed_once_preserves_last_good_output(tmp_path: Path) -> None:
    """Malformed evidence must fail without replacing the last valid digest."""
    module = _load()
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "latest.json"
    checkpoint.write_text("not-json")
    output.write_text('{"last":"good"}\n')
    args = module.build_parser().parse_args(
        ["--checkpoint", str(checkpoint), "--out", str(output), "--once"]
    )

    assert module.run_monitor(args, sleep_fn=lambda seconds: None) == 2
    assert json.loads(output.read_text()) == {"last": "good"}


def _load() -> ModuleType:
    spec = spec_from_file_location("cohort_improvement_monitor_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load cohort improvement monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
