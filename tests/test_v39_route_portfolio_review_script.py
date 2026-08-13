"""CLI tests for immutable exact-v39 route portfolio reviews."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from hashlib import sha256
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v39_route_portfolio_review.py")
_CONFIG = Path(
    "configs/"
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)


def test_report_binds_exact_input_bytes_and_publishes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checkpoint/config bytes and the generated review are immutable."""
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "review.json"
    raw = b'{"audit":{"marker":39}}\n'
    checkpoint.write_bytes(raw)
    monkeypatch.setattr(module, "build_v39_forward_evidence", _forward)
    monkeypatch.setattr(module, "build_v39_route_portfolio_review", _review)
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--config",
            str(_CONFIG),
            "--out",
            str(output),
        ]
    )

    report = module.run_report(args)
    module.write_immutable_report(output, report)

    persisted = json.loads(output.read_text())
    assert persisted["evidence"]["checkpoint"]["sha256"] == sha256(raw).hexdigest()
    assert persisted["evidence"]["config"]["sha256"]
    assert persisted["generator_identity"]["files"]
    with pytest.raises(FileExistsError, match="already exists"):
        module.write_immutable_report(output, report)


def test_output_cannot_alias_an_input(tmp_path: Path) -> None:
    """Immutable publication cannot overwrite its checkpoint or config."""
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--config",
            str(_CONFIG),
            "--out",
            str(checkpoint),
        ]
    )

    with pytest.raises(ValueError, match="output must differ"):
        module.run_report(args)


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v39 route review script is missing")
    spec = spec_from_file_location("v39_route_portfolio_review_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v39 route review script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _forward(
    checkpoint: object, config: object, *, observed_at: object
) -> dict[str, object]:
    assert checkpoint == {"audit": {"marker": 39}}
    assert getattr(config, "profile_id").endswith("v39")
    assert observed_at is not None
    return {"source": {"run_id": "v39"}}


def _review(forward: object, checkpoint: object) -> dict[str, object]:
    assert forward == {"source": {"run_id": "v39"}}
    assert checkpoint == {"audit": {"marker": 39}}
    return {
        "contract": {"report_only": True, "execution_authority": "none"},
        "summary": {"current_run_closed_trades": 0},
    }
