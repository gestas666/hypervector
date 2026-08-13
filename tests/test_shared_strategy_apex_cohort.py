"""Integration contract for the report-only Apex directional cohort."""

from __future__ import annotations

from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import numpy as np
import pandas as pd


_SCRIPT = Path(__file__).parents[1] / "scripts" / "shared_strategy_screen.py"
_SPEC = spec_from_file_location("shared_strategy_screen_apex_test", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_apex_directional_cohort_is_bounded_and_report_only(tmp_path: Path) -> None:
    parser = _MODULE.build_parser()
    parsed = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-01-01T00:00:00Z",
            "--end",
            "2026-01-02T00:00:00Z",
            "--execution-timeframe",
            "5min",
            "--cohort",
            "apex-directional-v1",
            "--output",
            "report.json",
        ]
    )
    candidates, profiles = _MODULE._trial_design(parsed.cohort)

    assert [candidate.name for candidate in candidates] == [
        "apex_trend",
        "apex_ensemble",
        "apex_breakout",
    ]
    assert len(profiles) == 4

    bars_path, funding_path, start, end = _evidence(tmp_path)
    report = _MODULE.run_screen(
        bars_path=bars_path,
        funding_paths=[funding_path],
        start=start,
        end=end,
        execution_timeframe="5min",
        cohort="apex-directional-v1",
    )

    assert report["mode"] == "bar_screen_only_not_executable_evidence"
    assert report["selection_applied"] is False
    assert report["trial_count"] == 12
    assert report["development_selection"] is None


def _evidence(
    root: Path,
) -> tuple[Path, Path, datetime, datetime]:
    index = pd.date_range("2026-01-01", periods=600, freq="1min", tz="UTC")
    close = np.linspace(100.0, 120.0, len(index))
    bars = pd.DataFrame(
        {
            "timestamp": index,
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": np.where(np.arange(len(index)) % 75 == 0, 3.0, 1.0),
            "source": "synthetic",
        }
    )
    funding = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=10, freq="1h", tz="UTC"),
            "funding_rate": 0.0,
        }
    )
    bars_path = root / "bars.parquet"
    funding_path = root / "funding.parquet"
    bars.to_parquet(bars_path, index=False)
    funding.to_parquet(funding_path, index=False)
    return (
        bars_path,
        funding_path,
        index[0].to_pydatetime(),
        (index[-1] + pd.Timedelta(minutes=1)).to_pydatetime(),
    )
