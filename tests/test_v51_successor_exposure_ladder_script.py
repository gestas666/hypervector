"""CLI tests for immutable successor exposure evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

_SCRIPT = Path("scripts/v51_successor_exposure_ladder.py")
_PROFILE = "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51"


def test_command_publishes_source_bound_report_only_ladder(tmp_path: Path) -> None:
    module = _load_module()
    source = tmp_path / "disposition.json"
    fees = tmp_path / "preflight.json"
    output = tmp_path / "ladder.json"
    source.write_text(json.dumps(_disposition()), encoding="utf-8")
    fees.write_text(json.dumps(_preflight()), encoding="utf-8")
    args = module.build_parser().parse_args(
        [
            "--disposition",
            str(source),
            "--fee-preflight",
            str(fees),
            "--output",
            str(output),
        ]
    )

    assert module.run(args) == 0

    report = json.loads(output.read_text())
    assert report["schema_version"] == "v51_successor_exposure_ladder_v2"
    assert report["contract"]["execution_authority"] == "none"
    assert report["assessment"]["successor_live_ready"] is False
    assert report["evidence"]["disposition"]["path"] == str(source)
    assert report["evidence"]["fee_preflight"]["path"] == str(fees)
    assert not Path(report["evidence"]["generator"]["path"]).is_absolute()
    assert report["evidence"]["builder"]["path"] == (
        "src/hypervector/research/v51_successor_exposure_ladder.py"
    )
    help_text = module.build_parser().format_help()
    assert "--enabled" not in help_text
    assert "--i-accept-live-risk" not in help_text


def _disposition() -> dict[str, object]:
    return {
        "mode": "report_only",
        "execution_authority": "none",
        "automatic_live_change": False,
        "portfolio_conclusion": {"full_size_routes_supported": 0},
        "route_dispositions": [
            {
                "strategy_id": "hulk_expansion_short_robust_v3",
                "symbol": "BTC",
                "side": "short",
                "disposition": "conditional_successor_candidate_not_full_size",
            }
        ],
    }


def _preflight() -> dict[str, object]:
    return {
        "identity": {"candidate_profile_id": _PROFILE},
        "assets": [
            {
                "symbol": "BTC",
                "venue": {"one_way_taker_fee_bps": 4.32},
            },
            {
                "symbol": "xyz:SP500",
                "venue": {"one_way_taker_fee_bps": 0.864},
            },
        ],
    }


def _load_module() -> ModuleType:
    spec = spec_from_file_location("v51_successor_exposure_ladder_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
