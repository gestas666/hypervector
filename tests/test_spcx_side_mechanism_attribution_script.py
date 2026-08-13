"""Command contract for immutable SPCX side-mechanism attribution."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

_SCRIPTS = (
    (
        Path("scripts/spcx_side_mechanism_attribution.py"),
        "build_spcx_side_mechanism_attribution",
    ),
    (
        Path("scripts/gold_side_mechanism_attribution.py"),
        "build_gold_side_mechanism_attribution",
    ),
)


@pytest.mark.parametrize(("script", "builder_name"), _SCRIPTS)
def test_command_writes_one_immutable_report_only_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script: Path,
    builder_name: str,
) -> None:
    """The command may publish evidence but cannot grant runtime authority."""
    module = _load_script(script)
    source = tmp_path / "source.json"
    trades = tmp_path / "trades.parquet"
    output = tmp_path / "attribution.json"
    source.touch()
    trades.touch()
    expected = {
        "contract": {"report_only": True, "execution_authority": "none"},
        "decision": "tested_side_timing_set_falsified_requires_new_mechanism_identity",
    }

    def fake_builder(source_path: Path, trades_path: Path) -> dict[str, object]:
        assert source_path == source
        assert trades_path == trades
        return expected

    monkeypatch.setattr(
        module,
        builder_name,
        fake_builder,
    )
    args = module.build_parser().parse_args(
        ["--source", str(source), "--trades", str(trades), "--out", str(output)]
    )

    result = module.run_command(args)

    assert result == expected
    assert json.loads(output.read_text(encoding="utf-8")) == expected
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.run_command(args)


def _load_script(path: Path) -> object:
    name = f"{path.stem}_test_module"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
