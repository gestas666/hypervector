"""Command contract for the immutable ETH side-mechanism decision."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

_SCRIPT = Path("scripts/eth_side_mechanism_decision.py")
_SPEC = importlib.util.spec_from_file_location("eth_side_mechanism_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_command_publishes_source_bound_report_only_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command writes immutable evidence without changing runtime state."""
    attribution = tmp_path / "attribution.json"
    duration = tmp_path / "duration.json"
    output = tmp_path / "decision.json"
    attribution.write_text('{"source":1}', encoding="utf-8")
    duration.write_text('{"source":2}', encoding="utf-8")
    expected = {
        "contract": {"report_only": True, "execution_authority": "none"},
        "assessment": {"stable_side_arms": [], "stable_side_relation_arms": []},
        "decision": "tested_side_relation_set_falsified_requires_new_mechanism_identity",
    }

    def fake_builder(
        first: dict[str, object], second: dict[str, object]
    ) -> dict[str, object]:
        assert first == {"source": 1}
        assert second == {"source": 2}
        return dict(expected)

    monkeypatch.setattr(_MODULE, "build_eth_side_mechanism_decision", fake_builder)
    args = _MODULE.build_parser().parse_args(
        [
            "--attribution",
            str(attribution),
            "--duration",
            str(duration),
            "--out",
            str(output),
        ]
    )

    result = _MODULE.run_command(args)

    assert result["source"]["attribution"]["sha256"]
    assert result["source"]["duration"]["sha256"]
    assert json.loads(output.read_text(encoding="utf-8")) == result
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        _MODULE.run_command(args)
