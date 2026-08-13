#!/usr/bin/env python3
"""Run one immutable, report-only Hulk Smash development tuning surface."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import math
from numbers import Integral, Real
from pathlib import Path
from typing import Sequence

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.hulk_smash_autotune import (
    build_hulk_tune_signal_matrix,
    evaluate_hulk_autotune_results,
    rank_hulk_autotune_trials,
)
from hypervector.research.hulk_smash_autotune_inputs import (
    load_hulk_autotune_inputs,
)
from hypervector.research.cipher_suite_duckdb import CIPHER_RESEARCH_SYMBOLS
from hypervector.research.hulk_smash_autotune_journal import (
    HulkAutotuneJournal,
)
from hypervector.research.hulk_smash_autotune_surfaces import (
    development_folds_v1,
    local_signal_surface_v1,
    robust_development_scenarios_v1,
)
from hypervector.research.market_cipher_source_contract import (
    audit_market_cipher_sources,
)


def _parser() -> argparse.ArgumentParser:
    """Build the explicit non-executable AutoTune command contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--journal", required=True, type=Path)
    parser.add_argument("--backtest-lab-root", required=True, type=Path)
    parser.add_argument("--mc-scalper-root", required=True, type=Path)
    parser.add_argument("--market-cipher-cli-root", required=True, type=Path)
    parser.add_argument(
        "--symbol",
        action="append",
        required=True,
        choices=CIPHER_RESEARCH_SYMBOLS,
    )
    parser.add_argument("--funding", action="append", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--surface", required=True, choices=("local_signal_v1",))
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Evaluate, journal, and report one complete development surface."""
    args = _parser().parse_args(argv)
    output = Path(args.out)
    if output.exists():
        raise FileExistsError(f"Hulk AutoTune report already exists: {output}")
    parameters = local_signal_surface_v1()
    folds = development_folds_v1()
    scenarios = robust_development_scenarios_v1()
    start, end = _protocol_window(args.start, args.end, folds)
    inputs = load_hulk_autotune_inputs(
        database_path=Path(args.database),
        backtest_lab_root=Path(args.backtest_lab_root),
        funding_by_symbol=_funding_map(args.funding),
        symbols=tuple(args.symbol),
        start_utc=start,
        end_utc=end,
    )
    signals = build_hulk_tune_signal_matrix(
        inputs.bars_by_symbol, inputs.components_by_symbol, parameters
    )
    results = evaluate_hulk_autotune_results(
        bars_by_symbol=inputs.bars_by_symbol,
        signals_by_trial=signals,
        parameters=parameters,
        folds=folds,
        scenarios=scenarios,
    )
    summaries = rank_hulk_autotune_trials(parameters, results)
    source_identity = _source_identity(args, inputs.source_identity)
    HulkAutotuneJournal(Path(args.journal)).write_run(
        run_id=str(args.run_id),
        surface=str(args.surface),
        source_identity=source_identity,
        parameters=parameters,
        results=results,
        summaries=summaries,
    )
    report = _report(
        str(args.run_id),
        str(args.surface),
        start,
        end,
        source_identity,
        parameters,
        folds,
        scenarios,
        summaries,
        results,
    )
    write_immutable_json(output, _json_safe(report))
    print(f"wrote report-only Hulk AutoTune artifact: {output}")
    return 0


def _protocol_window(
    start_value: str, end_value: str, folds: tuple[object, ...]
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = _timestamp(start_value), _timestamp(end_value)
    first = getattr(folds[0], "start_utc", None) if folds else None
    last = getattr(folds[-1], "end_utc", None) if folds else None
    if start != first or end != last:
        raise ValueError("Hulk local_signal_v1 requires its frozen development window")
    return start, end


def _source_identity(
    args: argparse.Namespace, data_identity: dict[str, object]
) -> dict[str, object]:
    identity = audit_market_cipher_sources(
        Path(args.mc_scalper_root), Path(args.market_cipher_cli_root)
    )
    identity["data"] = data_identity
    return identity


def _report(
    run_id: str,
    surface: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    source_identity: dict[str, object],
    parameters: tuple[object, ...],
    folds: tuple[object, ...],
    scenarios: tuple[object, ...],
    summaries: tuple[object, ...],
    results: tuple[object, ...],
) -> dict[str, object]:
    return {
        "schema_version": "hulk_smash_autotune_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "place_attempted": False,
        "run_id": run_id,
        "surface": surface,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "source_identity": source_identity,
        "parameters": [_dataclass_payload(value) for value in parameters],
        "folds": [_dataclass_payload(value) for value in folds],
        "scenarios": [_dataclass_payload(value) for value in scenarios],
        "summaries": [_dataclass_payload(value) for value in summaries],
        "results": [_dataclass_payload(value) for value in results],
    }


def _dataclass_payload(value: object) -> dict[str, object]:
    payload = asdict(value)  # type: ignore[arg-type]
    trial_id = getattr(value, "trial_id", None)
    if isinstance(trial_id, str):
        payload["trial_id"] = trial_id
    return payload


def _funding_map(values: list[str]) -> dict[str, tuple[Path, ...]]:
    grouped: dict[str, list[Path]] = {}
    for value in values:
        symbol, separator, path = value.partition("=")
        normalized = symbol.strip().upper()
        if (
            not separator
            or normalized not in CIPHER_RESEARCH_SYMBOLS
            or not path.strip()
        ):
            supported = ", ".join(CIPHER_RESEARCH_SYMBOLS)
            raise ValueError(f"funding must use SYMBOL=PATH for: {supported}")
        grouped.setdefault(normalized, []).append(Path(path.strip()))
    return {symbol: tuple(paths) for symbol, paths in grouped.items()}


def _timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError("Hulk AutoTune timestamps must include a timezone")
    return timestamp.tz_convert("UTC")


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Hulk AutoTune report contains non-finite numeric output")
        return number
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
