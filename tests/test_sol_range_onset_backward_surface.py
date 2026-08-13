from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.sol_range_onset_backward_challenge import (
    prepare_gap_safe_blocks,
)
from hypervector.research.sol_range_onset_backward_surface import (
    BackwardShape,
    evaluate_backward_shapes,
    load_predeclared_shape_grid,
    prepare_backward_shape_blocks,
    shape_grid,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "sol_range_onset_backward_surface.py"


def _load_script() -> ModuleType:
    spec = spec_from_file_location("sol_range_onset_backward_surface", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bars() -> pd.DataFrame:
    index = pd.date_range("2025-03-01T00:00:00Z", periods=32 * 60, freq="1min")
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl",
        }
    )


def _signals(bars: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(
        False,
        index=bars.index,
        columns=("long_entry", "short_entry", "long_exit", "short_exit"),
    )
    result["long_signal_name"] = "fixture_long"
    result["short_signal_name"] = "fixture_short"
    eligible = bars.index[bars.index >= bars.index[0] + pd.Timedelta(hours=30)]
    result.loc[eligible[0], "long_entry"] = True
    result.loc[eligible[60], "long_exit"] = True
    return result


def test_shape_grid_matches_the_predeclared_sixteen_cells() -> None:
    grid = shape_grid()

    assert len(grid) == 16
    assert BackwardShape(60.0, 48) in grid
    assert BackwardShape(100.0, None) in grid


def test_predeclared_shape_grid_requires_exact_prior_trial_ids(tmp_path: Path) -> None:
    path = tmp_path / "prior.json"
    trials = [{"trial_id": shape.trial_id} for shape in shape_grid()]
    path.write_text(
        json.dumps(
            {
                "mode": "multi_asset_range_onset_shape_surface_post_hoc_report_only",
                "symbol": "SOL",
                "execution_authority": "none",
                "model_authority": "none",
                "continuous": {"trials": trials},
            }
        ),
        encoding="utf-8",
    )

    evidence = load_predeclared_shape_grid(path, shape_grid())

    assert evidence["trial_count"] == 16
    assert evidence["sha256"]


def test_backward_shape_evaluation_retains_every_trial_without_authority() -> None:
    blocks = prepare_gap_safe_blocks(_bars())
    funding = pd.Series(
        0.0,
        index=pd.date_range("2025-03-01T00:00:00Z", periods=32, freq="1h"),
    )
    prepared, skipped = prepare_backward_shape_blocks(
        blocks,
        funding,
        signal_builder=_signals,
        warmup_hours=30,
    )
    shapes = (BackwardShape(40.0, 24), BackwardShape(60.0, 48))

    rows = evaluate_backward_shapes(prepared, shapes)

    assert skipped == []
    assert len(rows) == 2
    assert {row["trial_id"] for row in rows} == {
        "stop=40__hold=24",
        "stop=60__hold=48",
    }
    assert all(row["execution_authority"] == "none" for row in rows)
    assert all(row["aggregate"]["completed_trades"] == 1 for row in rows)


def test_backward_surface_script_writes_immutable_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    output = tmp_path / "surface.json"
    report = {
        "mode": "sol_range_onset_backward_predeclared_shape_surface_bar_only",
        "execution_authority": "none",
    }
    monkeypatch.setattr(
        module, "evaluate_sol_backward_shape_surface", lambda **_: report
    )
    arguments = [
        "--bars",
        "bars.parquet",
        "--funding",
        "funding.parquet",
        "--predeclared-surface",
        "prior.json",
        "--start",
        "2025-03-01T00:00:00Z",
        "--end",
        "2025-07-28T00:00:00Z",
        "--out",
        str(output),
    ]

    assert module.main(arguments) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert module.main(arguments) == 1
