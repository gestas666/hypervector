#!/usr/bin/env python3
"""Qualify an exact report-only bidirectional MU HIP-3 Swing/HA candidate."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.data.hl import fetch_hl_funding_history, fetch_hl_ohlcv_snapshot
from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.research.hip3_transfer_sources import attach_official_funding
from hypervector.research.mu_hip3_archive_provenance import (
    require_unchanged_generator,
    source_tree_identity,
)
from hypervector.research.mu_hip3_artifacts import (
    publish_bundle,
    require_new_outputs,
    staged_file_reference,
    staging_paths,
)
from hypervector.research.mu_hip3_candidate import (
    MU_SYMBOL,
    MuCandidateResult,
    MuDepthFriction,
    evaluate_mu_swing_candidate,
    summarize_trades,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioReport
from hypervector.research.swing_ha_screen import base_trial_grid
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

_DEFAULT_QUALIFICATION = Path(
    "data/logs/research/xyz_mu_qualification_20260810T093600Z.json"
)
_DEFAULT_LIQUIDITY = Path(
    "data/logs/research/xyz_mu_liquidity_profile_fee_sensitivity_20260810.json"
)
_DEFAULT_REGULAR_AUDIT = Path("data/logs/research/xyz_mu_l2_probe_audit_20260810.json")
_DEFAULT_OUTSIDE_AUDIT = Path(
    "data/logs/research/xyz_mu_l2_after_hours_probe_audit_20260810.json"
)
_DEFAULT_OUTPUT = Path(
    "data/logs/research/xyz_mu_swing_ha_bidirectional_20260810_v1.json"
)
_DEFAULT_TRADES = Path(
    "data/logs/research/xyz_mu_swing_ha_bidirectional_20260810_v1.trades.parquet"
)
_DEFAULT_SOURCES = Path(
    "data/logs/research/xyz_mu_swing_ha_bidirectional_20260810_v1.sources.parquet"
)


class CandleFetcher(Protocol):
    """Read-only public-candle acquisition boundary."""

    def __call__(
        self,
        symbol: str,
        timeframe: str,
        lookback_days: int,
        *,
        end_ms: int,
    ) -> pd.DataFrame:
        """Return official venue candles."""
        ...


class FundingFetcher(Protocol):
    """Read-only public-funding acquisition boundary."""

    def __call__(
        self,
        symbol: str,
        *,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp,
    ) -> pd.DataFrame:
        """Return official venue funding rows."""
        ...


def build_parser() -> argparse.ArgumentParser:
    """Return a parser with no execution or promotion options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qualification-report", type=Path, default=_DEFAULT_QUALIFICATION
    )
    parser.add_argument("--liquidity-report", type=Path, default=_DEFAULT_LIQUIDITY)
    parser.add_argument(
        "--regular-audit-report", type=Path, default=_DEFAULT_REGULAR_AUDIT
    )
    parser.add_argument(
        "--outside-audit-report", type=Path, default=_DEFAULT_OUTSIDE_AUDIT
    )
    parser.add_argument("--lookback-days", type=int, default=60)
    parser.add_argument("--nominal-latency-bps-per-side", type=float, default=1.0)
    parser.add_argument("--stress-latency-bps-per-side", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--trades-output", type=Path, default=_DEFAULT_TRADES)
    parser.add_argument("--sources-output", type=Path, default=_DEFAULT_SOURCES)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    candle_fetcher: CandleFetcher = fetch_hl_ohlcv_snapshot,
    funding_fetcher: FundingFetcher = fetch_hl_funding_history,
    configs: tuple[SwingHaSignalConfig, ...] | None = None,
) -> dict[str, object]:
    """Run the immutable, execution-incapable chronological experiment."""
    _require_new(args.output, args.trades_output, args.sources_output)
    generator_identity = _generator_identity()
    qualification = _load_json(args.qualification_report)
    liquidity = _load_json(args.liquidity_report)
    _require_complete_audit(args.regular_audit_report)
    _require_complete_audit(args.outside_audit_report)
    end_ms, max_leverage = _qualification(qualification)
    friction = _friction(args, liquidity, max_leverage)
    candles = candle_fetcher(MU_SYMBOL, "15m", args.lookback_days, end_ms=end_ms)
    bars, funding, funding_evidence = _prepare_bars(
        candles, funding_fetcher, requested_end_ms=end_ms
    )
    result = evaluate_mu_swing_candidate(
        bars,
        friction,
        configs=configs or base_trial_grid(),
    )
    trades = _trade_frame(result)
    sources = _source_frame(candles, funding)
    stages = staging_paths(args.output, args.trades_output, args.sources_output)
    report_stage, trades_stage, sources_stage = stages
    try:
        write_immutable_parquet(trades_stage, trades)
        write_immutable_parquet(sources_stage, sources)
        report = _report(args, result, friction, funding_evidence, generator_identity)
        report["trade_sidecar"] = staged_file_reference(
            args.trades_output, trades_stage, len(trades)
        )
        report["source_sidecar"] = staged_file_reference(
            args.sources_output, sources_stage, len(sources)
        )
        json.dumps(report, sort_keys=True)
        write_immutable_json(report_stage, report)
        _require_generator_unchanged(generator_identity)
        publish_bundle(
            (
                (trades_stage, args.trades_output),
                (sources_stage, args.sources_output),
                (report_stage, args.output),
            )
        )
        return report
    finally:
        for stage in stages:
            stage.unlink(missing_ok=True)


def _prepare_bars(
    candles: pd.DataFrame,
    funding_fetcher: FundingFetcher,
    *,
    requested_end_ms: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    bars = _official_bars(candles, requested_end_ms=requested_end_ms)
    start = bars.index.min().floor("h")
    end = bars.index.max().ceil("h")
    funding = funding_fetcher(MU_SYMBOL, start_time=start, end_time=end)
    funded, evidence = attach_official_funding(bars, funding)
    return (
        funded,
        funding,
        {
            **asdict(evidence),
            "candle_source": "hl",
            "requested_symbol": MU_SYMBOL,
            "identical_candle_duplicates_dropped": int(
                bars.attrs.get("identical_duplicates_dropped", 0)
            ),
        },
    )


def _official_bars(
    candles: pd.DataFrame,
    *,
    requested_end_ms: int | None = None,
) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume", "source"}
    missing = sorted(required.difference(candles.columns))
    if missing:
        raise ValueError(f"official MU candles missing columns: {missing}")
    bars = candles.copy()
    if set(bars["source"].astype(str)) != {"hl"}:
        raise ValueError(
            "official MU candles require exact Hyperliquid source identity"
        )
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    if requested_end_ms is not None:
        cutoff = pd.Timestamp(requested_end_ms, unit="ms", tz="UTC")
        bars = bars.loc[bars["timestamp"] + pd.Timedelta(minutes=15) <= cutoff].copy()
    duplicate_count = _validate_identical_candle_duplicates(bars)
    bars = (
        bars.sort_values("timestamp")
        .drop_duplicates("timestamp")
        .set_index("timestamp")
    )
    bars.attrs["identical_duplicates_dropped"] = duplicate_count
    if len(bars) < 100:
        raise ValueError("MU qualification requires at least 100 official 15m bars")
    gaps = bars.index.to_series().diff().div(pd.Timedelta(minutes=15)) - 1.0
    if gaps.dropna().lt(0.0).any() or not gaps.dropna().mod(1.0).eq(0.0).all():
        raise ValueError("official MU candles violate 15m cadence")
    bars["gap_before_bars"] = gaps.fillna(0.0).astype(int)
    return bars


def _validate_identical_candle_duplicates(candles: pd.DataFrame) -> int:
    duplicate_rows = candles[candles.duplicated("timestamp", keep=False)]
    if duplicate_rows.empty:
        return 0
    values = ("open", "high", "low", "close", "volume", "source")
    conflicts = duplicate_rows.groupby("timestamp", sort=False).agg(
        {column: "nunique" for column in values}
    )
    if conflicts.gt(1).any(axis=None):
        raise ValueError("official MU candles contain conflicting duplicate timestamps")
    return int(duplicate_rows.duplicated("timestamp").sum())


def _friction(
    args: argparse.Namespace,
    liquidity: dict[str, object],
    max_leverage: float,
) -> MuDepthFriction:
    profile = _mapping(liquidity.get("profile"), "liquidity profile")
    if profile.get("symbol") != MU_SYMBOL:
        raise ValueError("liquidity profile is not exact xyz:MU")
    sessions = {
        str(row.get("session")): row
        for item in _sequence(profile.get("sessions"), "liquidity sessions")
        if (row := _mapping(item, "liquidity session"))
    }
    regular = _session_cost(sessions, "us_regular_hours")
    outside = _session_cost(sessions, "outside_us_regular_hours")
    _require_notional(profile, 75.0)
    fees = _mapping(profile.get("fees"), "liquidity fees")
    return MuDepthFriction(
        75.0,
        _number(fees.get("effective_taker_rate"), "effective_taker_rate"),
        regular[0],
        regular[1],
        outside[0],
        outside[1],
        float(args.nominal_latency_bps_per_side),
        float(args.stress_latency_bps_per_side),
        max_leverage,
    )


def _report(
    args: argparse.Namespace,
    result: MuCandidateResult,
    friction: MuDepthFriction,
    funding_evidence: dict[str, object],
    generator_identity: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "mu_hip3_bidirectional_research_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "symbol": result.symbol,
        "report_only": True,
        "qualification_authority": "none_recent_probe_diagnostic_only",
        "execution_authority": result.execution_authority,
        "automatic_promotion": result.automatic_promotion,
        "place_attempted": False,
        "runtime_strategy_changed": False,
        "proposed_provider_id": result.proposed_provider_id,
        "proposed_profile_id": result.proposed_profile_id,
        "friction": asdict(friction),
        "funding": funding_evidence,
        "windows": _windows(result),
        "searched_trial_count": len(result.trials),
        "trials": [_trial_summary(trial) for trial in result.trials],
        "selected_config": asdict(result.selected_config),
        "partitions": {
            item.name: {
                "start_utc": item.start_utc.isoformat(),
                "end_utc": item.end_utc.isoformat(),
                "nominal": _report_summary(item.nominal),
                "stress": _report_summary(item.stress),
            }
            for item in result.partitions
        },
        "assessment": _assessment(result),
        "source_evidence": _source_evidence(args),
        "generator_identity": generator_identity,
        "limitations": _limitations(),
    }


def _report_summary(report: SharedPortfolioReport) -> dict[str, object]:
    value = report.to_dict()
    value.pop("trades")
    value["diagnostics"] = {
        name: asdict(summary)
        for name, summary in summarize_trades(report.trades).items()
    }
    return value


def _trial_summary(trial: object) -> dict[str, object]:
    config = getattr(trial, "config")
    development = getattr(trial, "development")
    folds = getattr(trial, "folds")
    return {
        "config": asdict(config),
        "development": _report_summary(development),
        "folds": [_report_summary(report) for report in folds],
    }


def _assessment(result: MuCandidateResult) -> dict[str, object]:
    partitions = {item.name: item for item in result.partitions}
    validation = partitions["validation"]
    holdout = partitions["holdout"]
    holdout_diagnostics = summarize_trades(holdout.nominal.trades)["all"]
    checks = {
        "validation_nominal_positive": validation.nominal.net_pnl_usd > 0.0,
        "holdout_nominal_positive": holdout.nominal.net_pnl_usd > 0.0,
        "validation_stress_positive": validation.stress.net_pnl_usd > 0.0,
        "holdout_stress_positive": holdout.stress.net_pnl_usd > 0.0,
        "holdout_positive_without_largest_winner": (
            holdout_diagnostics.net_without_largest_winner_usd > 0.0
        ),
        "holdout_observed_both_sides": {
            trade.direction for trade in holdout.nominal.trades
        }
        == {"long", "short"},
    }
    return {
        "status": "RECENT_PROBE_DIAGNOSTIC_ONLY",
        "research_supportive": False,
        "descriptive_checks_only": checks,
        "promotion": None,
        "superseded_by": "full_xyz_mu_0x_l2_trade_tape_qualification",
    }


def _trade_frame(result: MuCandidateResult) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for partition in result.partitions:
        for scenario, report in (
            ("nominal", partition.nominal),
            ("stress", partition.stress),
        ):
            rows.extend(
                {
                    "partition": partition.name,
                    "friction_scenario": scenario,
                    "symbol": MU_SYMBOL,
                    **asdict(trade),
                }
                for trade in report.trades
            )
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=["partition", "friction_scenario", "symbol"])


def _source_frame(candles: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    candle_rows = candles.copy()
    candle_rows.insert(0, "symbol", MU_SYMBOL)
    candle_rows.insert(1, "record_type", "official_candle_15m")
    funding_rows = funding.copy()
    funding_rows.insert(0, "symbol", MU_SYMBOL)
    funding_rows.insert(1, "record_type", "official_funding")
    columns = [
        "symbol",
        "record_type",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "funding_rate",
        "source",
    ]
    return pd.concat([candle_rows, funding_rows], ignore_index=True).reindex(
        columns=columns
    )


def _qualification(value: dict[str, object]) -> tuple[int, float]:
    markets = _sequence(value.get("markets"), "qualification markets")
    rows = [_mapping(item, "qualification market") for item in markets]
    matches = [row for row in rows if row.get("symbol") == MU_SYMBOL]
    if len(matches) != 1:
        raise ValueError("qualification requires exactly one xyz:MU market")
    source = _mapping(value.get("source"), "qualification source")
    return (
        int(_number(source.get("requested_end_ms"), "requested_end_ms")),
        _number(matches[0].get("max_leverage"), "max_leverage"),
    )


def _session_cost(
    sessions: dict[str, dict[str, object]], name: str
) -> tuple[float, float]:
    if name not in sessions:
        raise ValueError(f"liquidity profile missing {name}")
    spread = _mapping(sessions[name].get("spread_bps"), f"{name} spread")
    return _number(spread.get("p90"), f"{name} p90"), _number(
        spread.get("p99"), f"{name} p99"
    )


def _require_notional(profile: dict[str, object], expected: float) -> None:
    notionals = [
        _mapping(item, "liquidity notional")
        for item in _sequence(profile.get("notionals"), "liquidity notionals")
    ]
    matches = [row for row in notionals if row.get("notional_usd") == expected]
    if len(matches) != 1 or matches[0].get("both_complete_rate") != 1.0:
        raise ValueError("MU `$75` visible-depth completion evidence is incomplete")


def _windows(result: MuCandidateResult) -> dict[str, object]:
    value = result.windows
    return {
        "development_start_utc": value.development_start_utc.isoformat(),
        "development_end_utc": value.development_end_utc.isoformat(),
        "validation_end_utc": value.validation_end_utc.isoformat(),
        "holdout_end_utc": value.holdout_end_utc.isoformat(),
        "development_folds": [
            {"start_utc": start.isoformat(), "end_utc": end.isoformat()}
            for start, end in value.development_folds
        ],
    }


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    return {
        "qualification": _file_reference(args.qualification_report),
        "liquidity": _file_reference(args.liquidity_report),
        "regular_session_l2_audit": _file_reference(args.regular_audit_report),
        "outside_session_l2_audit": _file_reference(args.outside_audit_report),
    }


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    return source_tree_identity(root, Path(__file__).resolve())


def _require_generator_unchanged(expected: dict[str, object]) -> None:
    root = Path(__file__).resolve().parents[1]
    require_unchanged_generator(expected, root, Path(__file__).resolve())


def _limitations() -> list[str]:
    return [
        "official candles are limited to the venue-retained recent window",
        "two one-hour L2 probes estimate regular and after-hours friction",
        "L2 snapshots do not identify queue position or adverse selection",
        "current account fees are modeled and are not historical fee truth",
        "weekly U.S. regular-hours slices do not identify exchange holidays",
        "single-asset historical evidence cannot replace a forward live canary",
    ]


def _require_complete_audit(path: Path) -> None:
    value = _load_json(path)
    if (
        value.get("complete") is not True
        or _number(value.get("book_snapshots"), "book_snapshots") <= 0.0
    ):
        raise ValueError(f"incomplete MU L2 audit: {path}")


def _file_reference(path: Path, rows: int | None = None) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"MU evidence file does not exist: {path}")
    output = {"path": str(path.resolve()), **file_evidence(path)}
    if rows is not None:
        output["rows"] = rows
    return output


def _load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"MU JSON evidence does not exist: {path}")
    return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _require_new(*paths: Path) -> None:
    require_new_outputs(*paths)


def main() -> int:
    """Run once and print the immutable report path."""
    args = build_parser().parse_args()
    run_command(args)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
