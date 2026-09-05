from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType


_SCRIPT = Path(__file__).parents[1] / "scripts/hip3_liquidity_snapshot.py"


class _Info:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, path: str, payload: dict[str, object]) -> object:
        self.calls.append((path, payload))
        return [
            {"universe": [{"name": "xyz:MU", "maxLeverage": 10}]},
            [{"dayNtlVlm": "20", "markPx": "4", "openInterest": "3"}],
        ]


def _module() -> ModuleType:
    spec = spec_from_file_location("hip3_liquidity_snapshot_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_writes_exact_public_info_snapshot(tmp_path: Path) -> None:
    module = _module()
    info = _Info()
    output = tmp_path / "snapshot.json"

    report = module.run_snapshot(
        Namespace(dex="xyz", out=output),
        info=info,
        now_fn=lambda: datetime(2026, 8, 17, 16, 45, tzinfo=UTC),
    )

    assert info.calls == [("/info", {"type": "metaAndAssetCtxs", "dex": "xyz"})]
    assert json.loads(output.read_text()) == report
    assert report["source"] == {
        "venue": "hyperliquid_mainnet",
        "api_surface": "official_sdk_public_info_metaAndAssetCtxs",
        "dex": "xyz",
    }
    assert report["markets"][0]["symbol"] == "xyz:MU"
