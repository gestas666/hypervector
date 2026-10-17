"""Report recorded economics and funding revenue capacity without trading."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

ACCOUNTING_FIELDS = (
    "closed_trades",
    "gross_market_pnl_usd",
    "fees_usd",
    "funding_usd",
    "net_pnl_usd",
)
COST_ALLOWANCES_BPS = (0, 10, 30)
BPS_PER_UNIT = 10_000
PERCENT_PER_UNIT = 100
RECONCILIATION_TOLERANCE_USD = 0.0001


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("economic evidence must be an object")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("economic evidence must contain numeric values")
    if not math.isfinite(value):
        raise ValueError("economic evidence must contain finite values")
    return float(value)


def _validate_row(row: Mapping[str, object]) -> None:
    values = {field: _number(row.get(field)) for field in ACCOUNTING_FIELDS}
    count = values["closed_trades"]
    if count < 0 or not count.is_integer():
        raise ValueError("closed trade count must be a nonnegative integer")
    expected = (
        values["gross_market_pnl_usd"] - values["fees_usd"] + values["funding_usd"]
    )
    if not math.isclose(
        expected, values["net_pnl_usd"], rel_tol=0, abs_tol=RECONCILIATION_TOLERANCE_USD
    ):
        raise ValueError("net PnL does not reconcile to gross minus fees plus funding")


def validate_performance(performance: Mapping[str, object]) -> None:
    """Require finite accounting that reconciles both within and across groups."""
    total = _mapping(performance.get("total"))
    groups = _mapping(performance.get("by_strategy"))
    rows = [_mapping(value) for value in groups.values()]
    for row in [total, *rows]:
        _validate_row(row)
    for field in ACCOUNTING_FIELDS:
        actual = sum(_number(row.get(field)) for row in rows)
        if not math.isclose(
            actual,
            _number(total.get(field)),
            rel_tol=0,
            abs_tol=RECONCILIATION_TOLERANCE_USD,
        ):
            raise ValueError(f"strategy aggregates disagree with total: {field}")


def funding_months(
    frame: pd.DataFrame, *, notional_fraction: float
) -> list[dict[str, object]]:
    """Screen complete hourly months without estimating hedge or basis PnL."""
    fraction = _number(notional_fraction)
    if not 0 < fraction <= 1:
        raise ValueError("notional fraction must lie in (0, 1]")
    if not {"ts", "fundingRate"}.issubset(frame.columns) or frame.empty:
        raise ValueError("funding requires nonempty ts and fundingRate columns")
    values = frame.copy()
    values["ts"] = pd.to_datetime(values["ts"], utc=True, errors="raise")
    if values["ts"].isna().any() or values["ts"].duplicated().any():
        raise ValueError("missing or duplicate funding timestamps")
    values["fundingRate"] = values["fundingRate"].map(_number)
    values = values.set_index("ts").sort_index()
    start = values.index.min().normalize().replace(day=1)
    finish = values.index.max().normalize().replace(day=1)
    output = []
    for month in pd.date_range(start, finish, freq="MS"):
        end = month + pd.offsets.MonthBegin(1)
        observed = values.loc[(values.index >= month) & (values.index < end)]
        expected = pd.date_range(month, end, freq="h", inclusive="left")
        row: dict[str, object] = {
            "month": month.isoformat(),
            "observed_hours": len(observed),
            "expected_hours": len(expected),
            "complete": observed.index.equals(expected),
        }
        if row["complete"]:
            rate = float(observed["fundingRate"].sum())
            row["funding_receipt_on_capital_pct"] = rate * fraction * PERCENT_PER_UNIT
            for cost in COST_ALLOWANCES_BPS:
                row[f"after_{cost}bps_allowance_pct"] = (
                    (rate - cost / BPS_PER_UNIT) * fraction * PERCENT_PER_UNIT
                )
        output.append(row)
    return output


def _source(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path.resolve()), "sha256": digest, "bytes": path.stat().st_size}


def build_report(checkpoint: Path, funding_paths: list[Path]) -> dict[str, object]:
    """Build an auditable read-only economic report from frozen local files."""
    snapshot = json.loads(checkpoint.read_text())
    archive = snapshot["audit"]["portfolio_archive"]
    performance = archive["performance"]
    validate_performance(performance)
    funding = [
        {
            "source": _source(path),
            "asset": path.stem,
            "months": funding_months(pd.read_parquet(path), notional_fraction=0.5),
        }
        for path in funding_paths
    ]
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "execution_authority": "none",
        "report_only": True,
        "checkpoint": _source(checkpoint),
        "archive_observed_through_utc": archive["observed_through_utc"],
        "fill_evidence_identity": archive["source_execution"],
        "coverage": archive["coverage"],
        "performance": performance,
        "strategy_identity_count": len(performance["by_strategy"]),
        "funding_capacity": funding,
        "assumptions": {
            "hedge_notional_fraction_of_total_capital": 0.5,
            "monthly_cost_allowances_bps_per_hedge_notional": COST_ALLOWANCES_BPS,
            "constant_notional": True,
        },
        "limitations": [
            "Funding capacity is not strategy PnL or an executable backtest.",
            "Basis, slippage, hedge rebalancing, custody and liquidation are not modeled.",
            "Cost allowances are sensitivities, not observed transaction costs.",
            "Historical months are exploratory evidence, not sealed holdouts.",
            "All-time strategy identities mix policies, sizes and observation periods.",
            "Equal funding rates do not imply equal dollar payments for fixed quantities.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    """Declare explicit immutable accounting report inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--funding", action="append", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write a new immutable report; refuse to overwrite existing evidence."""
    args = build_parser().parse_args(argv)
    report = build_report(args.checkpoint, args.funding)
    with args.out.open("x") as target:
        json.dump(report, target, indent=2, allow_nan=False)
        target.write("\n")
    print(f"Report written to {args.out}; execution_authority=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
