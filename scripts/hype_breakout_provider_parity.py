#!/usr/bin/env python3
"""Audit current historical/live HT-Breakout decisions on fixed SOL windows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hype_breakout_provider_parity import (
    build_hype_breakout_provider_parity,
)

_SOL_BARS = Path("data/cache/SOL_1m_365d.parquet")
_SOL_FUNDING = Path(
    "data/cache/vendor/hyperliquid/SOL/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_CONFIG = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_LIVE_PROVIDER = Path("src/hypervector/live/hype_breakout_cohort_provider.py")
_LIVE_DECISIONS = Path("src/hypervector/live/sol_range_onset_decision_source.py")
_HISTORICAL_MARKET = Path("src/hypervector/research/hype_breakout_exit_market.py")


class ParityWindow:
    """One 14-day live-lookback window with a seven-day audit tail."""

    __slots__ = ("phase", "start_utc", "evaluation_start_utc", "observed_at_utc")

    def __init__(
        self,
        phase: str,
        start_utc: str,
        evaluation_start_utc: str,
        observed_at_utc: str,
    ) -> None:
        """Store one fixed causal window contract."""
        self.phase = phase
        self.start_utc = start_utc
        self.evaluation_start_utc = evaluation_start_utc
        self.observed_at_utc = observed_at_utc


def parity_windows() -> tuple[ParityWindow, ...]:
    """Return three predeclared windows spanning development and final data."""
    return (
        ParityWindow(
            "development_early",
            "2025-08-01T00:00:00+00:00",
            "2025-08-08T00:00:00+00:00",
            "2025-08-15T00:00:00+00:00",
        ),
        ParityWindow(
            "development_late",
            "2026-05-01T00:00:00+00:00",
            "2026-05-08T00:00:00+00:00",
            "2026-05-15T00:00:00+00:00",
        ),
        ParityWindow(
            "opened_final_descriptive",
            "2026-07-14T00:00:00+00:00",
            "2026-07-21T00:00:00+00:00",
            "2026-07-28T00:00:00+00:00",
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only parity command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sol-bars", type=Path, default=_SOL_BARS)
    parser.add_argument("--sol-funding", type=Path, default=_SOL_FUNDING)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def build_artifact(
    reports: dict[str, dict[str, object]],
    *,
    source_evidence: dict[str, object],
) -> dict[str, object]:
    """Aggregate exact window results without success-shaped fallback."""
    expected = {window.phase for window in parity_windows()}
    if set(reports) != expected:
        raise ValueError("HT-Breakout parity requires all three fixed windows")
    if not source_evidence:
        raise ValueError("HT-Breakout parity requires source evidence")
    exact = all(report.get("exact_parity") is True for report in reports.values())
    return {
        "schema_version": 1,
        "mode": "sol_hype_breakout_provider_parity_v1",
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "window_contract": {
            "lookback_days": 14,
            "warmup_days": 7,
            "evaluation_days": 7,
            "opened_final_used_for_selection": False,
        },
        "windows": reports,
        "all_windows_exact_parity": exact,
        "source_evidence": source_evidence,
        "decision": (
            "provider_parity_confirmed_no_route_change"
            if exact
            else "historical_live_provider_mismatch_requires_fix"
        ),
        "limitations": [
            "three finite windows cannot prove parity on every historical bar",
            "decision parity does not validate after-cost profitability",
            "the audit cannot reproduce private IOC fills or queue position",
        ],
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    """Execute the three source-bound parity windows."""
    if args.out.exists():
        raise FileExistsError(f"immutable HT-Breakout parity output exists: {args.out}")
    paths = _source_paths(args)
    _require_files(paths)
    raw_bars = pd.read_parquet(args.sol_bars)
    funding = pd.read_parquet(args.sol_funding)
    reports = {
        window.phase: _run_window(raw_bars, funding, window)
        for window in parity_windows()
    }
    return build_artifact(reports, source_evidence=_data_evidence(paths))


def _run_window(
    raw_bars: pd.DataFrame,
    funding: pd.DataFrame,
    window: ParityWindow,
) -> dict[str, object]:
    start = pd.Timestamp(window.start_utc)
    boundary = pd.Timestamp(window.evaluation_start_utc)
    observed = pd.Timestamp(window.observed_at_utc)
    bars = _slice_bars(raw_bars, start, observed)
    report = build_hype_breakout_provider_parity(
        bars,
        funding,
        symbol="SOL",
        observed_at=observed,
        after_decision_time_ms=int(boundary.timestamp() * 1_000),
    )
    report["phase"] = window.phase
    report["used_for_selection"] = window.phase != "opened_final_descriptive"
    report["input_start_utc"] = start.isoformat()
    report["evaluation_start_utc"] = boundary.isoformat()
    return report


def _slice_bars(
    raw_bars: pd.DataFrame,
    start: pd.Timestamp,
    observed: pd.Timestamp,
) -> pd.DataFrame:
    timestamps = pd.to_datetime(raw_bars["timestamp"], utc=True)
    selected = raw_bars.loc[(timestamps >= start) & (timestamps < observed)].copy()
    if len(selected) != 14 * 24 * 60:
        raise ValueError("HT-Breakout parity window lacks exact 14-day cadence")
    return selected


def _source_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        args.sol_bars,
        args.sol_funding,
        _CONFIG,
        _LIVE_PROVIDER,
        _LIVE_DECISIONS,
        _HISTORICAL_MARKET,
    )


def _data_evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def _require_files(paths: tuple[Path, ...]) -> None:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"HT-Breakout parity sources are missing: {missing}")


def main() -> None:
    """Publish one immutable provider parity artifact."""
    args = build_parser().parse_args()
    artifact = run(args)
    write_immutable_json(args.out, artifact)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "all_windows_exact_parity": artifact["all_windows_exact_parity"],
                "window_counts": {
                    name: {
                        "historical": report["historical_entries"],
                        "live": report["live_entries"],
                    }
                    for name, report in artifact["windows"].items()
                },
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
