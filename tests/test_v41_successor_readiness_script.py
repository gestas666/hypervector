"""CLI tests for the immutable v41 successor-readiness report."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v41_successor_readiness.py")
_CONFIG = Path(
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41.toml"
)


def test_report_binds_every_input_and_publishes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All evidence bytes and generator files are identity-bound."""
    module = _module()
    sources = _sources(tmp_path)
    output = tmp_path / "readiness.json"
    monkeypatch.setattr(module, "build_v41_successor_readiness", _report)
    args = module.build_parser().parse_args(
        [
            "--config",
            str(_CONFIG),
            *[
                item
                for name, path in sources.items()
                for item in (f"--{name.replace('_', '-')}", str(path))
            ],
            "--out",
            str(output),
        ]
    )

    report = module.run_report(args)
    module.require_unchanged_inputs(report)
    module.write_immutable_report(output, report)

    persisted = json.loads(output.read_text())
    assert set(persisted["evidence"]) == {"config", *sources}
    assert (
        persisted["evidence"]["preflight"]["sha256"]
        == sha256(sources["preflight"].read_bytes()).hexdigest()
    )
    assert persisted["generator_identity"]["files"]
    with pytest.raises(FileExistsError, match="already exists"):
        module.write_immutable_report(output, report)


def test_changed_input_aborts_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A report cannot be published after evidence changes under it."""
    module = _module()
    sources = _sources(tmp_path)
    output = tmp_path / "readiness.json"
    monkeypatch.setattr(module, "build_v41_successor_readiness", _report)
    args = module.build_parser().parse_args(
        [
            "--config",
            str(_CONFIG),
            *[
                item
                for name, path in sources.items()
                for item in (f"--{name.replace('_', '-')}", str(path))
            ],
            "--out",
            str(output),
        ]
    )
    report = module.run_report(args)
    sources["preflight"].write_text('{"changed":true}\n')

    with pytest.raises(RuntimeError, match="input changed"):
        module.require_unchanged_inputs(report)
    assert not output.exists()


def test_real_sources_survive_bound_config_temporary_cleanup(tmp_path: Path) -> None:
    """The exact config digest remains usable after its bound loader closes."""
    module = _module()
    args = module.build_parser().parse_args(["--out", str(tmp_path / "report.json")])

    report = module.run_report(args)

    assert report["candidate"]["profile_id"].endswith("v41")
    assert report["evidence"]["config"]["sha256"]


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v41 successor-readiness script is missing")
    spec = spec_from_file_location("v41_successor_readiness_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v41 successor-readiness script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sources(tmp_path: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for name in ("preflight", "reprice", "concentration", "return_panel", "v39_review"):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"source": name}) + "\n")
        paths[name] = path
    return paths


def _report(**kwargs: object) -> dict[str, object]:
    assert getattr(kwargs["config"], "profile_id").endswith("v41")
    assert isinstance(kwargs["config_source_sha256"], str)
    assert all(
        isinstance(kwargs[name], dict)
        for name in kwargs
        if name not in {"config", "config_source_sha256"}
    )
    return {
        "contract": {"report_only": True, "execution_authority": "none"},
        "assessment": {"profit_optimality_proven": False},
    }
