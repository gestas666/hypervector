"""Printed direction coverage and process failure regressions for report audits."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from historic_report_io import write
from historic_report_metrics import compare_direction_table
from test_historic_report_metrics import calculated, synthetic_rows

PAIR = "| `test` | `BTC` | 2 | 50.0% | $5.00 | $7.00 | $2.00 | 2.00 | $5.00 |"
LONG = "| **Long** | 2 | 1 | 1 | 50.0% | $7.00 | $2.00 | $0.00 | $5.00 |"
DIRECTION = LONG + "\n" + LONG.replace("**Long**", "**Total**")


def test_direction_numbers_and_optional_funding_are_checked(tmp_path: Path) -> None:
    """Directional attribution cannot borrow correct totals as its validation."""
    summaries = calculated(tmp_path)
    checked = compare_direction_table(DIRECTION, summaries)
    assert len(checked) == 16 and all(row["passed"] for row in checked)
    legacy = DIRECTION.replace(" | $0.00", "")
    assert len(compare_direction_table(legacy, summaries)) == 14
    wrong = compare_direction_table(DIRECTION.replace("$7.00", "$8.00", 1), summaries)
    assert sum(not row["passed"] for row in wrong) == 1


@pytest.mark.parametrize(
    "report,match",
    [
        (LONG, "cover"),
        (DIRECTION + "\n" + LONG, "duplicated"),
        (DIRECTION.replace(" | $5.00", "").replace(" | $0.00", ""), "malformed"),
    ],
)
def test_direction_coverage_and_shape_fail(
    tmp_path: Path, report: str, match: str
) -> None:
    """Incomplete, duplicated or ambiguous rows cannot silently pass."""
    with pytest.raises(ValueError, match=match):
        compare_direction_table(report, calculated(tmp_path))


def _inputs(tmp_path: Path, report: str) -> None:
    summaries = calculated(tmp_path)
    scopes = {
        scope: {
            r["group_key"]: {
                k: v for k, v in r.items() if k not in ("scope", "group_key")
            }
            for r in summaries
            if r["scope"] == scope
        }
        for scope in ("strategy", "pair", "total")
    }
    checkpoint = {
        "audit": {
            "portfolio_archive": {
                "performance": {
                    "by_strategy": scopes["strategy"],
                    "by_provider_symbol": scopes["pair"],
                    "total": scopes["total"]["total"],
                }
            },
            "execution": {
                "scope": "synthetic",
                "fill_details": [],
                "acknowledgement_latency_ms": {"count": 0},
            },
        }
    }
    write(tmp_path / "lifecycle_rows.json", synthetic_rows())
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    write(inputs / "checkpoint.json", checkpoint)
    (inputs / "2026-09-12-historic-trade-analysis-131-trades.md").write_text(report)
    (inputs / "multi_asset_growth_first_5000_noncrypto_live_v89.toml").write_text(
        '[[providers]]\nstrategy_id="test"\nexecution_symbols=["BTC"]\n'
    )


def _command(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "scripts/historic_report_metrics.py"
    return subprocess.run(
        [sys.executable, str(script), "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_valid_tables_exit_successfully_with_both_check_artifacts(
    tmp_path: Path,
) -> None:
    """A passing command reports explicit coverage for both displayed populations."""
    _inputs(tmp_path, PAIR + "\n" + DIRECTION)
    result = _command(tmp_path)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["direction_cells_checked"] == 16
    assert summary["table_cell_discrepancies"] == 0
    assert (tmp_path / "direction_table_checks.json").is_file()


@pytest.mark.parametrize("population", ["pair", "direction"])
def test_wrong_printed_number_exits_nonzero_after_preserving_checks(
    tmp_path: Path, population: str
) -> None:
    """Detected numerical failure must propagate to shell callers and retain evidence."""
    pair = PAIR.replace("$5.00", "$6.00", 1) if population == "pair" else PAIR
    direction = (
        DIRECTION.replace("$7.00", "$8.00", 1)
        if population == "direction"
        else DIRECTION
    )
    _inputs(tmp_path, pair + "\n" + direction)
    result = _command(tmp_path)
    assert result.returncode != 0
    assert "mismatched table cells" in result.stderr
    filename = (
        "report_table_checks.json"
        if population == "pair"
        else "direction_table_checks.json"
    )
    checks = json.loads((tmp_path / filename).read_text())
    assert sum(not row["passed"] for row in checks) == 1
    assert not result.stdout.strip()


@pytest.mark.parametrize("wrong", [False, True])
def test_main_preserves_outputs_before_table_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    wrong: bool,
) -> None:
    """Exercise the main failure boundary in-process as well as through shell callers."""
    from historic_report_metrics import main

    pair = PAIR.replace("$5.00", "$6.00", 1) if wrong else PAIR
    _inputs(tmp_path, pair + "\n" + DIRECTION)
    monkeypatch.setattr(
        sys, "argv", ["historic_report_metrics", "--out", str(tmp_path)]
    )
    if wrong:
        with pytest.raises(ValueError, match="mismatched table cells"):
            main()
    else:
        main()
    captured = capsys.readouterr()
    assert bool(captured.out.strip()) is not wrong
    assert (tmp_path / "direction_table_checks.json").is_file()
    assert (tmp_path / "decimal_cash.json").is_file()
