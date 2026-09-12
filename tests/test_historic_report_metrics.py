"""Synthetic SQL, denominator, coverage and report-table validation regressions."""

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from historic_report_io import write
from historic_report_metrics import (
    check,
    compare_checkpoint,
    compare_report_table,
    decimal_cash,
    displayed_number,
    friction,
    population,
    sql_summaries,
)


def synthetic_rows() -> list[dict[str, object]]:
    """Build two unequal-margin closed trades with independently known cash outcomes."""
    return [
        {
            "row_index": i,
            "strategy_id": "test",
            "symbol": "BTC",
            "entry_direction": "Open Long",
            "profile_fingerprint": "profile",
            "net_pnl_usd": net,
            "entry_margin_usd": margin,
            "fees_usd": 1,
            "funding_usd": 0,
            "entry_ms": i * 60000,
            "exit_ms": (i + 1) * 60000,
        }
        for i, net, margin in [(0, 10, 100), (1, -5, 200)]
    ]


def calculated(tmp_path: Path) -> list[dict[str, object]]:
    """Run the actual standalone SQL on a small local input file."""
    path = tmp_path / "lifecycles.json"
    write(path, synthetic_rows())
    return sql_summaries(path)


def test_sql_uses_summed_margin_and_exit_order(tmp_path: Path) -> None:
    """The ratio of cash to summed margin differs from averaging trade returns."""
    summaries = calculated(tmp_path)
    total = next(r for r in summaries if r["scope"] == "total")
    assert total["closed_trades"] == 2
    assert total["net_pnl_usd"] == 5
    assert total["gross_market_pnl_usd"] == 7
    assert total["net_return_on_margin_pct"] == pytest.approx(5 / 300 * 100)
    assert total["mean_trade_return_on_margin_pct"] == 3.75
    assert total["profit_factor"] == 2
    assert total["maximum_closed_sequence_drawdown_usd"] == 5
    assert total["net_pnl_excluding_largest_winner_usd"] == -5
    assert decimal_cash(synthetic_rows(), summaries)["maximum_residual"] == 0


@pytest.mark.parametrize(
    "nets,profit_factor,largest",
    [([-2, -3], 0, None), ([2, 3], None, 3), ([0, 0], None, None)],
)
def test_zero_and_absent_winner_denominators(
    tmp_path: Path, nets: list[int], profit_factor: int | None, largest: int | None
) -> None:
    """Absent profit/loss populations stay null where their statistic is undefined."""
    rows = synthetic_rows()
    for row, net in zip(rows, nets, strict=True):
        row["net_pnl_usd"] = net
    p = tmp_path / "rows.json"
    write(p, rows)
    total = next(r for r in sql_summaries(p) if r["scope"] == "total")
    assert total["profit_factor"] == profit_factor
    assert total["largest_winner_usd"] == largest


@pytest.mark.parametrize(
    "actual,expected",
    [(None, 0), (0, None), (float("nan"), 0), (0, float("inf")), (1, 2)],
)
def test_nonfinite_missing_or_changed_projection_fails(
    actual: float | None, expected: float | None
) -> None:
    """An invalid comparison cannot pass through NaN arithmetic or a numeric default."""
    with pytest.raises(ValueError):
        check(actual, expected)
    assert check(None, None) == 0


def test_table_precision_roster_and_signs(tmp_path: Path) -> None:
    """Validate every cell at displayed precision while detecting missing rows."""
    summaries = calculated(tmp_path)
    row = "| `test` | `BTC` | 2 | 50.0% | **+$5.00** | +$7.00 | $2.00 | 2.00 | $5.00 |"
    result = compare_report_table(row, summaries)
    assert len(result) == 7 and all(r["passed"] for r in result)
    changed = compare_report_table(row.replace("+$5.00", "-$5.00"), summaries)
    assert sum(not r["passed"] for r in changed) == 1
    with pytest.raises(ValueError, match="duplicated"):
        compare_report_table(row + "\n" + row, summaries)
    with pytest.raises(ValueError, match="cover"):
        compare_report_table("", summaries)
    assert displayed_number("N/A") is None
    assert displayed_number("**−$1,234.56**") == Decimal("-1234.56")
    with pytest.raises(ValueError, match="malformed"):
        compare_report_table(row.replace(" | $5.00 |", " |"), summaries)


def test_table_preserves_undefined_profit_factor(tmp_path: Path) -> None:
    """An all-winning sample's undefined PF cannot become an invented number."""
    rows = synthetic_rows()
    rows[1]["net_pnl_usd"] = 5
    path = tmp_path / "winners.json"
    write(path, rows)
    summaries = sql_summaries(path)
    line = "| `test` | `BTC` | 2 | 100.0% | $15.00 | $17.00 | $2.00 | N/A | $0.00 |"
    assert all(r["passed"] for r in compare_report_table(line, summaries))
    assert not all(
        r["passed"]
        for r in compare_report_table(line.replace("N/A", "0.00"), summaries)
    )


def test_archive_scalar_and_roster_checks(tmp_path: Path) -> None:
    """A changed published number or missing strategy summary is rejected."""
    summaries = calculated(tmp_path)
    scopes = {
        scope: {
            r["group_key"]: {
                k: v for k, v in r.items() if k not in ("scope", "group_key")
            }
            for r in summaries
            if r["scope"] == scope
        }
        for scope in ["strategy", "pair", "total"]
    }
    checkpoint = {
        "audit": {
            "portfolio_archive": {
                "performance": {
                    "by_strategy": scopes["strategy"],
                    "by_provider_symbol": scopes["pair"],
                    "total": scopes["total"]["total"],
                }
            }
        }
    }
    assert compare_checkpoint(summaries, checkpoint)["checked_cells"] == 69
    changed = deepcopy(checkpoint)
    changed["audit"]["portfolio_archive"]["performance"]["total"]["net_pnl_usd"] = 6
    with pytest.raises(ValueError):
        compare_checkpoint(summaries, changed)
    checkpoint["audit"]["portfolio_archive"]["performance"]["by_strategy"]["extra"] = {}
    with pytest.raises(ValueError, match="roster"):
        compare_checkpoint(summaries, checkpoint)


def test_population_and_partial_fill_counts_are_distinct() -> None:
    """Provider-name overlap and repeated fill rows cannot imply current-contract samples."""
    config = {"providers": [{"strategy_id": "test", "execution_symbols": ["BTC"]}]}
    result = population(synthetic_rows(), config)
    assert result["profile_fingerprints"] == 1
    assert result["matching_provider_pair_rows"] == 2
    assert result["pair_match_is_full_contract_match"] is False
    fills = [
        {"symbol": "xyz:SNDK", "operation": "entry", "oid": 1, "slippage_bps": 10},
        {"symbol": "xyz:SNDK", "operation": "entry", "oid": 1, "slippage_bps": 11},
    ]
    checkpoint = {
        "audit": {
            "execution": {
                "scope": "example",
                "fill_details": fills,
                "acknowledgement_latency_ms": {"count": 2},
            }
        }
    }
    result = friction(checkpoint)
    assert result["sndk_entry_fills"] == 2
    assert result["sndk_entry_orders"] == 1
    assert result["spcx_entry_fills"] == 0
    assert result["unique_fill_order_acknowledgements"] == 1


def test_evidence_writer_preserves_existing_bytes(tmp_path: Path) -> None:
    """Reproduction requires a new output rather than silently overwriting evidence."""
    p = tmp_path / "result.json"
    write(p, {"number": 1})
    with pytest.raises(FileExistsError):
        write(p, {"number": 2})
    assert json.loads(p.read_text()) == {"number": 1}
