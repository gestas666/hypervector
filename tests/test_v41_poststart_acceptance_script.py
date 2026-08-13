"""CLI tests for exact v41 post-start technical acceptance."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v41_poststart_acceptance.py")
_CONFIG = Path(
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41.toml"
)


def test_command_binds_readiness_and_publishes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The future verifier is input-bound and execution-incapable."""
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    readiness = tmp_path / "readiness.json"
    output = tmp_path / "acceptance.json"
    checkpoint.write_text('{"audit":{"run":{"run_id":"v41"}}}\n')
    readiness.write_text('{"material_state_sha256":"ready"}\n')
    monkeypatch.setattr(module, "build_v41_poststart_acceptance", _accepted)
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--config",
            str(_CONFIG),
            "--readiness",
            str(readiness),
            "--out",
            str(output),
        ]
    )

    report = module.run_report(args)
    module.require_unchanged_inputs(report)
    module.write_immutable_report(output, report)

    persisted = json.loads(output.read_text())
    assert set(persisted["evidence"]) == {"checkpoint", "config", "readiness"}
    assert module.exit_code(persisted) == 0
    with pytest.raises(FileExistsError, match="already exists"):
        module.write_immutable_report(output, report)


def test_readiness_is_mandatory_and_rejection_exits_two(tmp_path: Path) -> None:
    """No default stale readiness can be selected accidentally."""
    module = _module()
    with pytest.raises(SystemExit):
        module.build_parser().parse_args(["--out", str(tmp_path / "out.json")])

    assert module.exit_code({"accepted": False}) == 2


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v41 post-start acceptance script is missing")
    spec = spec_from_file_location("v41_poststart_acceptance_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v41 post-start acceptance script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _accepted(*args: object, **kwargs: object) -> dict[str, object]:
    assert args[0] == {"audit": {"run": {"run_id": "v41"}}}
    assert getattr(args[1], "profile_id").endswith("v41")
    assert args[2] == {"material_state_sha256": "ready"}
    assert kwargs["now_utc"] is not None
    return {
        "schema_version": "v41_poststart_acceptance_v1",
        "contract": {"report_only": True, "execution_authority": "none"},
        "accepted": True,
        "decision": "accepted",
        "reasons": [],
    }
