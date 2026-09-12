"""Independently recompute the cited archive and test displayed report figures."""

import argparse
from datetime import UTC, datetime
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import tomllib

import duckdb

from historic_report_io import write

TOLERANCE = 1e-8
SUMMARY_SQL = """
WITH expanded AS (
 SELECT r.*,g.scope,g.group_key,
 net_pnl_usd+fees_usd-funding_usd AS gross_market,
 net_pnl_usd/entry_margin_usd*100 AS trade_return
 FROM lifecycles r CROSS JOIN LATERAL (VALUES
 ('total','total'),('strategy',strategy_id),('pair',strategy_id||'|'||symbol),
 ('side',entry_direction),('profile',profile_fingerprint)) g(scope,group_key)
), paths AS (
 SELECT *,sum(net_pnl_usd) OVER(PARTITION BY scope,group_key ORDER BY row_index) AS cumulative
 FROM expanded
), peaks AS (
 SELECT *,greatest(0,max(cumulative) OVER(PARTITION BY scope,group_key ORDER BY row_index)) AS peak
 FROM paths
)
SELECT scope,group_key,count(*) AS closed_trades,
 count(*) FILTER(WHERE net_pnl_usd>0) AS wins,
 count(*) FILTER(WHERE net_pnl_usd<0) AS losses,
 count(*) FILTER(WHERE net_pnl_usd=0) AS breakeven,
 count(*) FILTER(WHERE net_pnl_usd>0)*100.0/count(*) AS win_rate_pct,
 sum(net_pnl_usd) AS net_pnl_usd,sum(entry_margin_usd) AS entry_margin_used_usd,
 sum(net_pnl_usd)/sum(entry_margin_usd)*100 AS net_return_on_margin_pct,
 avg(trade_return) AS mean_trade_return_on_margin_pct,
 coalesce(sum(net_pnl_usd) FILTER(WHERE net_pnl_usd>0),0)/nullif(-sum(net_pnl_usd) FILTER(WHERE net_pnl_usd<0),0) AS profit_factor,
 sum(fees_usd) AS fees_usd,sum(funding_usd) AS funding_usd,
 avg(net_pnl_usd) AS mean_trade_net_pnl_usd,median(net_pnl_usd) AS median_trade_net_pnl_usd,
 median(trade_return) AS median_trade_return_on_margin_pct,
 max(net_pnl_usd) FILTER(WHERE net_pnl_usd>0) AS largest_winner_usd,
 max(net_pnl_usd) FILTER(WHERE net_pnl_usd>0)/nullif(sum(net_pnl_usd) FILTER(WHERE net_pnl_usd>0),0)*100 AS largest_winner_share_of_gross_profit_pct,
 sum(net_pnl_usd)-max(net_pnl_usd) FILTER(WHERE net_pnl_usd>0) AS net_pnl_excluding_largest_winner_usd,
 max(peak-cumulative) AS maximum_closed_sequence_drawdown_usd,
 sum(gross_market) AS gross_market_pnl_usd,
 sum(fees_usd)/nullif(sum(gross_market) FILTER(WHERE gross_market>0),0)*100 AS fees_as_pct_of_positive_gross_market_pnl,
 sum(fees_usd)-sum(funding_usd) AS execution_cash_drag_usd,
 (sum(fees_usd)-sum(funding_usd))/nullif(sum(gross_market) FILTER(WHERE gross_market>0),0)*100 AS execution_cash_drag_as_pct_of_positive_gross_market_pnl
FROM peaks GROUP BY scope,group_key ORDER BY scope,group_key
"""


def check(actual: object, expected: object) -> float:
    """Reject changed missingness or an unreconciled numerical projection."""
    if actual is None or expected is None:
        if actual is not expected:
            raise ValueError("Summary missingness differs")
        return 0.0
    if not math.isfinite(float(actual)) or not math.isfinite(float(expected)):
        raise ValueError("Summary value is nonfinite")
    difference = abs(float(actual) - float(expected))
    if difference > TOLERANCE:
        raise ValueError(f"Archive summary differs by {difference}")
    return difference


def sql_summaries(path: Path) -> list[dict[str, object]]:
    """Run independent SQL arithmetic on all preserved lifecycle records."""
    with duckdb.connect() as db:
        db.execute("SET threads=1")
        db.read_json(str(path)).create_view("lifecycles")
        cursor = db.execute(SUMMARY_SQL)
        columns = [r[0] for r in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def compare_checkpoint(
    summaries: list[dict[str, object]], checkpoint: dict[str, object]
) -> dict[str, object]:
    """Check every numerical total, strategy and provider/symbol archive field."""
    performance = checkpoint["audit"]["portfolio_archive"]["performance"]
    groups = {
        "strategy": performance["by_strategy"],
        "pair": performance["by_provider_symbol"],
        "total": {"total": performance["total"]},
    }
    checked = []
    for row in summaries:
        if row["scope"] not in groups:
            continue
        original = groups[row["scope"]][row["group_key"]]
        for field, expected in original.items():
            if isinstance(expected, dict):
                continue
            residual = check(row[field], expected)
            checked.append(
                {
                    "scope": row["scope"],
                    "group_key": row["group_key"],
                    "field": field,
                    "residual": residual,
                }
            )
    for scope, originals in groups.items():
        if {r["group_key"] for r in summaries if r["scope"] == scope} != set(originals):
            raise ValueError("Archive summary roster differs")
    return {
        "checked_cells": len(checked),
        "maximum_residual": max(r["residual"] for r in checked),
        "checks": checked,
    }


def displayed_number(value: str) -> Decimal | None:
    """Parse a displayed numeric table cell without discarding its sign."""
    cleaned = (
        value.replace("**", "")
        .replace("$", "")
        .replace("%", "")
        .replace(",", "")
        .replace("−", "-")
    )
    return None if cleaned.strip() == "N/A" else Decimal(cleaned.strip())


def compare_report_table(
    report: str, summaries: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Validate the complete displayed 34-row strategy/asset table at printed precision."""
    lookup = {r["group_key"]: r for r in summaries if r["scope"] == "pair"}
    seen = set()
    results = []
    metrics = (
        "closed_trades",
        "win_rate_pct",
        "net_pnl_usd",
        "gross_market_pnl_usd",
        "fees_usd",
        "profit_factor",
        "maximum_closed_sequence_drawdown_usd",
    )
    for line in report.splitlines():
        if not re.match(r"^\| `[^`]+` \| `[^`]+` \|", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        key = cells[0].strip("`") + "|" + cells[1].strip("`")
        if key in seen or len(cells) != 9:
            raise ValueError("Report table row is duplicated or malformed")
        seen.add(key)
        results.extend(_compare_cells(key, cells[2:], metrics, lookup[key]))
    if seen != set(lookup):
        raise ValueError("Displayed report table does not cover all archive pairs")
    return results


def _compare_cells(
    key: str, cells: list[str], metrics: tuple[str, ...], expected: dict[str, object]
) -> list[dict[str, object]]:
    results = []
    for text, field in zip(cells, metrics, strict=True):
        observed, value = displayed_number(text), expected[field]
        tolerance = (
            Decimal(0)
            if field in {"closed_trades", "wins", "losses"}
            else (Decimal("0.05") if field == "win_rate_pct" else Decimal("0.005"))
        )
        passed = observed is None and value is None
        if observed is not None and value is not None:
            passed = abs(observed - Decimal(str(value))) <= tolerance
        results.append(
            {
                "key": key,
                "field": field,
                "displayed": text,
                "recomputed": value,
                "passed": passed,
            }
        )
    return results


def compare_direction_table(
    report: str, summaries: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Validate directional attribution, totals and optional funding at printed precision."""
    lookup = {
        row["group_key"].removeprefix("Open "): row
        for row in summaries
        if row["scope"] == "side"
    }
    lookup["Total"] = next(row for row in summaries if row["scope"] == "total")
    metrics = (
        "closed_trades",
        "wins",
        "losses",
        "win_rate_pct",
        "gross_market_pnl_usd",
        "fees_usd",
    )
    seen, results = set(), []
    for line in report.splitlines():
        if not re.match(r"^\| \*\*(Long|Short|Total)\*\* \|", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        key = cells[0].strip("*")
        if key in seen or len(cells) not in {8, 9}:
            raise ValueError("Direction table row is duplicated or malformed")
        if key not in lookup:
            raise ValueError(
                "Direction table coverage includes an unsupported population"
            )
        seen.add(key)
        fields = (
            metrics + (("funding_usd",) if len(cells) == 9 else ()) + ("net_pnl_usd",)
        )
        results.extend(_compare_cells(key, cells[1:], fields, lookup[key]))
    if seen != set(lookup):
        raise ValueError(
            "Direction table does not cover all archive directions and total"
        )
    return results


def _require_valid_tables(checks: list[dict[str, object]]) -> None:
    failures = sum(not row["passed"] for row in checks)
    if failures:
        raise ValueError(
            f"Report contains {failures} mismatched table cells; inspect "
            "report_table_checks.json and direction_table_checks.json before publishing"
        )


def decimal_cash(
    rows: list[dict[str, object]], summaries: list[dict[str, object]]
) -> dict[str, object]:
    """Cross-check the full archived cash decomposition using Decimal arithmetic."""
    totals = {
        key: sum((Decimal(str(r[key])) for r in rows), Decimal(0))
        for key in ("net_pnl_usd", "fees_usd", "funding_usd", "entry_margin_usd")
    }
    totals["gross_market_pnl_usd"] = (
        totals["net_pnl_usd"] + totals["fees_usd"] - totals["funding_usd"]
    )
    total = next(r for r in summaries if r["scope"] == "total")
    residuals = {}
    for key, value in totals.items():
        field = "entry_margin_used_usd" if key == "entry_margin_usd" else key
        residuals[field] = check(value, total[field])
    return {
        "totals": {k: str(v) for k, v in totals.items()},
        "maximum_residual": max(residuals.values()),
    }


def population(
    rows: list[dict[str, object]], config: dict[str, object]
) -> dict[str, object]:
    """Expose dates, mixed-profile coverage and exact configured-provider overlap."""
    current = {
        (p["strategy_id"], symbol)
        for p in config["providers"]
        for symbol in p["execution_symbols"]
    }
    active_rows = [r for r in rows if (r["strategy_id"], r["symbol"]) in current]
    retired = {"hulk_expansion_short_tuned_v2", "hulk_expansion_short_robust_v3"}
    return {
        "closed_lifecycles": len(rows),
        "profile_fingerprints": len({r["profile_fingerprint"] for r in rows}),
        "entry_start_utc": utc_text(min(r["entry_ms"] for r in rows)),
        "entry_end_utc": utc_text(max(r["entry_ms"] for r in rows)),
        "exit_start_utc": utc_text(min(r["exit_ms"] for r in rows)),
        "exit_end_utc": utc_text(max(r["exit_ms"] for r in rows)),
        "configured_provider_pairs": [list(key) for key in sorted(current)],
        "matching_provider_pair_rows": len(active_rows),
        "pair_match_is_full_contract_match": False,
        "legacy_short_variants_in_config": sorted(
            retired.intersection(p["strategy_id"] for p in config["providers"])
        ),
    }


def utc_text(timestamp_ms: int) -> str:
    """Format the actual stored venue clock with an explicit UTC offset."""
    return datetime.fromtimestamp(timestamp_ms / 1000, UTC).isoformat()


def friction(checkpoint: dict[str, object]) -> dict[str, object]:
    """Retain the actual entry-fill and acknowledgement observation populations."""
    execution = checkpoint["audit"]["execution"]
    entries = [r for r in execution["fill_details"] if r["operation"] == "entry"]
    sndk = [r for r in entries if r["symbol"] == "xyz:SNDK"]
    return {
        "scope": execution["scope"],
        "all_fill_rows": len(execution["fill_details"]),
        "fill_symbols": sorted({r["symbol"] for r in execution["fill_details"]}),
        "sndk_entry_fills": len(sndk),
        "sndk_entry_orders": len({r["oid"] for r in sndk}),
        "sndk_entry_slippage_bps": [r["slippage_bps"] for r in sndk],
        "spcx_entry_fills": sum(r["symbol"] == "xyz:SPCX" for r in entries),
        "reported_all_fill_acknowledgement_latency_ms": execution[
            "acknowledgement_latency_ms"
        ],
        "unique_fill_order_acknowledgements": len(
            {(r["symbol"], r["oid"]) for r in execution["fill_details"]}
        ),
        "physical_latency_cause_identified": False,
    }


def main() -> None:
    """Publish the reproducible numerical audit of the cited historical report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    rows = json.loads((out / "lifecycle_rows.json").read_text())
    checkpoint = json.loads((out / "inputs/checkpoint.json").read_text())
    report = (
        out / "inputs/2026-09-12-historic-trade-analysis-131-trades.md"
    ).read_text()
    config = tomllib.loads(
        (
            out / "inputs/multi_asset_growth_first_5000_noncrypto_live_v89.toml"
        ).read_text()
    )
    summaries = sql_summaries(out / "lifecycle_rows.json")
    checks = compare_checkpoint(summaries, checkpoint)
    table = compare_report_table(report, summaries)
    directions = compare_direction_table(report, summaries)
    for name, value in (
        ("sql_summaries", summaries),
        ("checkpoint_checks", checks),
        ("report_table_checks", table),
        ("direction_table_checks", directions),
        ("decimal_cash", decimal_cash(rows, summaries)),
        ("population", population(rows, config)),
        ("friction_population", friction(checkpoint)),
        ("metric_sql", {"sql": SUMMARY_SQL}),
    ):
        write(out / (name + ".json"), value)
    _require_valid_tables(table + directions)
    print(
        json.dumps(
            {
                "archive_cells_reconciled": checks["checked_cells"],
                "table_cells_checked": len(table),
                "direction_cells_checked": len(directions),
                "table_cell_discrepancies": sum(
                    not r["passed"] for r in table + directions
                ),
                "maximum_archive_residual": checks["maximum_residual"],
            }
        )
    )


if __name__ == "__main__":
    main()
