"""CLI-boundary tests for the execution-incapable HIP-3 qualifier."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "hip3_market_qualification.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("hip3_market_qualification_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeInfo:
    """Deterministic official-SDK-shaped read-only fixture."""

    def __init__(self, *, include_xyz: bool = True) -> None:
        self.include_xyz = include_xyz
        self.candle_calls: list[tuple[str, str, int, int]] = []

    def perp_dexs(self) -> list[object]:
        if not self.include_xyz:
            return []
        return [
            None,
            {
                "name": "xyz",
                "fullName": "XYZ",
                "deployerFeeScale": "1.0",
                "assetToStreamingOiCap": [
                    ["xyz:SP500", "1250000000"],
                    ["xyz:SPCX", "750000000"],
                ],
                "assetToFundingMultiplier": [
                    ["xyz:SP500", "0.5"],
                    ["xyz:SPCX", "0.5"],
                ],
            },
        ]

    def post(self, _path: str, payload: dict[str, object]) -> list[object]:
        assert payload == {"type": "metaAndAssetCtxs", "dex": "xyz"}
        universe = [
            {
                "name": "xyz:SP500",
                "szDecimals": 3,
                "maxLeverage": 50,
                "marginTableId": 50,
                "growthMode": "enabled",
            },
            {
                "name": "xyz:SPCX",
                "szDecimals": 2,
                "maxLeverage": 20,
                "marginTableId": 20,
                "growthMode": "enabled",
            },
        ]
        contexts = [self._context("7727"), self._context("113.6")]
        metadata = {
            "collateralToken": 0,
            "marginTables": [
                [
                    50,
                    {
                        "description": "",
                        "marginTiers": [{"lowerBound": "0", "maxLeverage": 50}],
                    },
                ]
            ],
            "universe": universe,
        }
        return [metadata, contexts]

    def spot_meta(self) -> dict[str, object]:
        """Return the exact collateral token identity used by XYZ."""
        return {
            "tokens": [
                {
                    "name": "USDC",
                    "index": 0,
                    "szDecimals": 8,
                    "weiDecimals": 8,
                }
            ]
        }

    def l2_snapshot(self, name: str) -> dict[str, object]:
        price = 7727.0 if name.endswith("SP500") else 113.6
        return {
            "coin": name,
            "time": 1_786_026_775_880,
            "levels": [
                [{"px": str(price), "sz": "1", "n": 1}],
                [{"px": str(price + 0.1), "sz": "2", "n": 1}],
            ],
        }

    def candles_snapshot(
        self,
        name: str,
        interval: str,
        startTime: int,
        endTime: int,
    ) -> list[dict[str, int]]:
        self.candle_calls.append((name, interval, startTime, endTime))
        step = {"1m": 60_000, "5m": 300_000, "15m": 900_000}[interval]
        return [{"t": startTime, "T": startTime + step - 1}]

    @staticmethod
    def _context(price: str) -> dict[str, object]:
        return {
            "markPx": price,
            "midPx": price,
            "oraclePx": price,
            "funding": "0",
            "openInterest": "1",
            "dayNtlVlm": "1000000",
        }


def test_once_writes_exact_two_symbol_report_without_execution(tmp_path: Path) -> None:
    """The CLI reads public HIP-3 data and cannot construct trading authority."""
    module = _load_module()
    info = FakeInfo()
    output = tmp_path / "qualification.json"
    args = module.build_parser().parse_args(["--out", str(output)])

    result = module.run_qualification(
        args,
        info=info,
        now_fn=lambda: datetime(2026, 8, 6, 14, 32, tzinfo=UTC),
    )

    assert result["symbols"] == ["xyz:SP500", "xyz:SPCX"]
    assert result["execution_authority"] == "none"
    assert json.loads(output.read_text())["automatic_promotion"] is False
    assert len(info.candle_calls) == 6
    source = SCRIPT.read_text(encoding="utf-8")
    assert "private_key" not in source
    assert "Exchange(" not in source
    assert "submit" not in source


def test_missing_requested_dex_fails_explicitly(tmp_path: Path) -> None:
    """A vanished or renamed deployer namespace cannot look successful."""
    module = _load_module()
    args = module.build_parser().parse_args(["--out", str(tmp_path / "out.json")])

    with pytest.raises(ValueError, match="xyz perp dex is unavailable"):
        module.run_qualification(
            args,
            info=FakeInfo(include_xyz=False),
            now_fn=lambda: datetime(2026, 8, 6, 14, 32, tzinfo=UTC),
        )
