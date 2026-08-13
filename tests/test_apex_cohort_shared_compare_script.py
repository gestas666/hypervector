"""Contracts for immutable shared-capital Apex artifact comparison."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest


_SCRIPT = Path("scripts/apex_cohort_shared_compare.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("apex_cohort_shared_compare", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load shared compare script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    directional = tmp_path / "directional.json"
    directional.write_text(
        json.dumps(
            {
                "candidate": "apex_mean_reversion_v2",
                "segment": "development",
                "result": {
                    "metrics": {
                        "trades": [
                            {
                                "entry_time_utc": "2026-01-01T00:10:00+00:00",
                                "exit_time_utc": "2026-01-01T00:20:00+00:00",
                                "margin_usd": 1500.0,
                                "fees_usd": 5.0,
                                "net_pnl_usd": -10.0,
                            }
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    market_maker = tmp_path / "mm.json"
    market_maker.write_text(
        json.dumps(
            {
                "candidate": "apex_regime_mm_v2",
                "segment": "development",
                "result": {
                    "sessions": [
                        {
                            "start_utc": "2026-01-01T00:05:00+00:00",
                            "end_utc": "2026-01-01T00:35:00+00:00",
                            "fees_usd": 2.0,
                            "net_pnl_usd": 3.0,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    return directional, market_maker


def _write_hulk_artifact(tmp_path: Path) -> Path:
    hulk = tmp_path / "hulk.json"
    hulk.write_text(
        json.dumps(
            {
                "segment": "development",
                "profile": {"name": "hulk_expansion_short_robust_v3"},
                "replay": {
                    "trades": [
                        {
                            "symbol": "BTC",
                            "entry_time_utc": "2026-01-01T00:05:00+00:00",
                            "exit_time_utc": "2026-01-01T00:25:00+00:00",
                            "isolated_margin_usd": 1_000.0,
                            "fees_usd": 4.0,
                            "exit_legs": [{"fee_usd": 2.0}],
                            "net_pnl_usd": 20.0,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    return hulk


def test_comparison_retains_conflicts_and_strategy_attribution(tmp_path: Path) -> None:
    directional, market_maker = _write_artifacts(tmp_path)
    output = tmp_path / "shared.json"

    assert (
        _module().main(
            [
                "--directional",
                str(directional),
                "--market-maker",
                str(market_maker),
                "--out",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["segment"] == "development"
    assert payload["report_only"] is True
    assert payload["execution_authority"] == "none"
    assert payload["portfolio"]["net_pnl_usd"] == 3.0
    assert payload["portfolio"]["strategy_net_pnl_usd"] == {"apex_regime_mm_v2": 3.0}
    assert payload["portfolio"]["rejected"][0]["reason"] == "symbol_occupied"


def test_comparison_refuses_segment_mismatch(tmp_path: Path) -> None:
    directional, market_maker = _write_artifacts(tmp_path)
    payload = json.loads(market_maker.read_text(encoding="utf-8"))
    payload["segment"] = "validation"
    market_maker.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="same segment"):
        _module().main(
            [
                "--directional",
                str(directional),
                "--market-maker",
                str(market_maker),
                "--out",
                str(tmp_path / "shared.json"),
            ]
        )


def test_comparison_refuses_output_overwrite(tmp_path: Path) -> None:
    directional, market_maker = _write_artifacts(tmp_path)
    output = tmp_path / "shared.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="shared output exists"):
        _module().main(
            [
                "--directional",
                str(directional),
                "--market-maker",
                str(market_maker),
                "--out",
                str(output),
            ]
        )


def test_comparison_accepts_hulk_and_gives_it_same_time_priority(
    tmp_path: Path,
) -> None:
    """Hulk, MM, and the negative control share one attributed BTC owner."""
    directional, market_maker = _write_artifacts(tmp_path)
    hulk = _write_hulk_artifact(tmp_path)
    output = tmp_path / "shared-hulk.json"

    assert (
        _module().main(
            [
                "--directional",
                str(directional),
                "--market-maker",
                str(market_maker),
                "--hulk",
                str(hulk),
                "--start",
                "2026-01-01T00:00:00+00:00",
                "--end",
                "2026-01-01T01:00:00+00:00",
                "--out",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["portfolio"]["net_pnl_usd"] == 20.0
    assert payload["portfolio"]["strategy_net_pnl_usd"] == {
        "hulk_expansion_short_robust_v3": 20.0
    }
    assert {row["candidate"] for row in payload["portfolio"]["rejected"]} == {
        "apex_regime_mm_v2",
        "apex_mean_reversion_v2",
    }
    assert payload["comparison_window"] == {
        "start_utc": "2026-01-01T00:00:00+00:00",
        "end_utc": "2026-01-01T01:00:00+00:00",
        "excluded_outcomes": 0,
    }


def test_hulk_comparison_requires_explicit_common_window(tmp_path: Path) -> None:
    """Mismatched source windows may not be compared by segment label alone."""
    directional, market_maker = _write_artifacts(tmp_path)
    hulk = _write_hulk_artifact(tmp_path)

    with pytest.raises(ValueError, match="explicit common window"):
        _module().main(
            [
                "--directional",
                str(directional),
                "--market-maker",
                str(market_maker),
                "--hulk",
                str(hulk),
                "--out",
                str(tmp_path / "shared.json"),
            ]
        )


def test_active_survivor_comparison_omits_negative_control_intents(
    tmp_path: Path,
) -> None:
    """Observer-only mean reversion need not occupy the active shared account."""
    _, market_maker = _write_artifacts(tmp_path)
    hulk = _write_hulk_artifact(tmp_path)
    output = tmp_path / "active.json"

    assert (
        _module().main(
            [
                "--market-maker",
                str(market_maker),
                "--hulk",
                str(hulk),
                "--start",
                "2026-01-01T00:00:00+00:00",
                "--end",
                "2026-01-01T01:00:00+00:00",
                "--out",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["portfolio"]["net_pnl_usd"] == 20.0
    assert payload["portfolio"]["strategy_net_pnl_usd"] == {
        "hulk_expansion_short_robust_v3": 20.0
    }
    assert "directional" not in payload["input_identity"]
