"""CLI contract for immutable v39 technical acceptance."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v39_poststart_acceptance.py")


def test_command_is_report_only_and_persists_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command must write one immutable report without live flags."""
    module = _load_module()
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text('{"checkpoint_contract": {}}\n', encoding="utf-8")
    output = tmp_path / "acceptance.json"
    monkeypatch.setattr(
        module,
        "build_v39_poststart_acceptance",
        lambda *args, **kwargs: _report(True),
    )
    args = module.build_parser().parse_args(
        ["--checkpoint", str(checkpoint), "--out", str(output)]
    )

    report = module.run(args)

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert report == persisted
    assert persisted["contract"]["execution_authority"] == "none"
    assert persisted["evidence"]["checkpoint"]["path"] == str(checkpoint.resolve())
    help_text = module.build_parser().format_help()
    assert "--enabled" not in help_text
    assert "--i-accept-live-risk" not in help_text


def test_rejected_report_has_distinct_exit_and_existing_output_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected report is not a crash and immutable output is never overwritten."""
    module = _load_module()
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "acceptance.json"
    monkeypatch.setattr(
        module,
        "build_v39_poststart_acceptance",
        lambda *args, **kwargs: _report(False),
    )
    args = module.build_parser().parse_args(
        ["--checkpoint", str(checkpoint), "--out", str(output)]
    )

    report = module.run(args)

    assert module.exit_code(report) == 2
    with pytest.raises(FileExistsError, match="already exists"):
        module.run(args)


def _load_module() -> ModuleType:
    spec = spec_from_file_location("v39_poststart_acceptance_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _report(accepted: bool) -> dict[str, object]:
    return {
        "schema_version": "v39_poststart_acceptance_v1",
        "contract": {"report_only": True, "execution_authority": "none"},
        "accepted": accepted,
        "decision": "accepted" if accepted else "rejected",
        "reasons": [] if accepted else ["candidate_identity_not_active"],
    }
