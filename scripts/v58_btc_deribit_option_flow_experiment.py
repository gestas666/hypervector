#!/usr/bin/env python3
"""Run and immutably publish the frozen BTC option-flow experiment."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    verify_file_evidence,
    write_json,
)
from hypervector.research.btc_option_directional_flow import (
    build_causal_flow_signals,
)
from hypervector.research.btc_option_flow_experiment import (
    BtcOptionFlowExperimentResult,
    OptionFlowPartition,
    run_frozen_option_flow_experiment,
)
from hypervector.research.btc_option_flow_market_inputs import (
    OptionFlowMarketInputs,
    prepare_gap_aware_option_flow_market,
)
from hypervector.research.btc_option_flow_source_merge import (
    merge_option_flow_candles,
    merge_option_flow_funding,
)
from hypervector.research.hip3_development_provenance import (
    loaded_project_source_paths,
    require_unchanged_dependencies,
    require_unchanged_file,
    source_dependency_identity,
)


_HYPOTHESIS = "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1"
_REGISTERED_SCHEMA = "v58_btc_deribit_option_flow_registered_source_v2"
_PREREGISTRATION_SCHEMA = "v58_btc_deribit_option_flow_long_preregistration_v4"
_PROTOCOL_SCHEMA = "v58_btc_deribit_option_flow_experiment_protocol_v1"
_REGISTERED = Path("data/cache/research/v58_btc_deribit_option_flow_source_20260822_v2")
_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v4.json"
)
_PROTOCOL = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-experiment-protocol-20260822-v1.json"
)
_OUTPUT = Path("data/logs/research/v58_btc_deribit_option_flow_experiment_20260822_v1")


def build_parser() -> argparse.ArgumentParser:
    """Return the exact report-only experiment parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registered-source", type=Path, default=_REGISTERED)
    parser.add_argument("--preregistration", type=Path, default=_PREREGISTRATION)
    parser.add_argument("--experiment-protocol", type=Path, default=_PROTOCOL)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--recorded-at-utc", required=True)
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Load frozen sources, run all cells, and atomically publish evidence."""
    project = Path.cwd().resolve()
    dependencies = source_dependency_identity(
        project,
        loaded_project_source_paths(project, Path(__file__)),
    )
    preregistration = load_validated_preregistration(args.preregistration)
    protocol = load_validated_protocol(args.experiment_protocol)
    preregistration_evidence = _path_evidence(args.preregistration)
    protocol_evidence = _path_evidence(args.experiment_protocol)
    hourly, registered = load_registered_hourly_source(
        args.registered_source,
        args.preregistration,
        args.experiment_protocol,
    )
    market, market_evidence, market_files = load_option_flow_market(
        project, preregistration
    )
    partitions, folds = experiment_partitions(preregistration, protocol)
    signals = build_causal_flow_signals(hourly)
    result = _run_cells(market, signals, partitions, folds, protocol)
    _require_inputs_unchanged(
        project,
        dependencies,
        args,
        preregistration_evidence,
        protocol_evidence,
        registered,
        market_files,
    )
    report = dict(result.report)
    report.update(
        _report_context(
            args.recorded_at_utc,
            registered,
            preregistration_evidence,
            protocol_evidence,
            market_evidence,
            market,
            signals,
            partitions,
            dependencies,
        )
    )
    return _publish(args.output, report, result.trade_rows, signals)


def _run_cells(
    market: OptionFlowMarketInputs,
    signals: pd.DataFrame,
    partitions: Sequence[OptionFlowPartition],
    folds: Sequence[OptionFlowPartition],
    protocol: Mapping[str, object],
) -> BtcOptionFlowExperimentResult:
    return run_frozen_option_flow_experiment(
        market.execution_bars,
        market.signal_bars,
        signals,
        partitions=partitions,
        development_folds=folds,
        bootstrap_resamples=_protocol_integer(protocol, "resamples"),
        bootstrap_seed=_protocol_integer(protocol, "seed"),
    )


def _require_inputs_unchanged(
    project: Path,
    dependencies: dict[str, object],
    args: argparse.Namespace,
    preregistration: dict[str, object],
    protocol: dict[str, object],
    registered: Mapping[str, object],
    market_files: Sequence[tuple[Path, dict[str, object]]],
) -> None:
    require_unchanged_dependencies(dependencies, project)
    require_unchanged_file(args.preregistration, preregistration)
    require_unchanged_file(args.experiment_protocol, protocol)
    require_unchanged_file(
        args.registered_source / "manifest.json", _mapping(registered, "manifest")
    )
    require_unchanged_file(
        args.registered_source / "hourly_flow.parquet",
        _mapping(registered, "hourly_flow"),
    )
    for path, evidence in market_files:
        require_unchanged_file(path, evidence)


def _report_context(
    recorded_at_utc: str,
    registered: dict[str, object],
    preregistration: dict[str, object],
    protocol: dict[str, object],
    market_evidence: dict[str, object],
    market: OptionFlowMarketInputs,
    signals: pd.DataFrame,
    partitions: Sequence[OptionFlowPartition],
    dependencies: dict[str, object],
) -> dict[str, object]:
    return {
        "recorded_at_utc": _utc_text(recorded_at_utc),
        "status": "frozen_historical_experiment_complete_report_only",
        "registered_source": registered,
        "preregistration": preregistration,
        "experiment_protocol": protocol,
        "market_source_evidence": market_evidence,
        "market_preparation": market.evidence(),
        "signal_diagnostics": _signal_diagnostics(signals, partitions),
        "source_dependency_identity": dependencies,
    }


def load_registered_hourly_source(
    bundle: Path, preregistration: Path, protocol: Path
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load only a source registered before candidate signals or outcomes."""
    manifest_path = bundle / "manifest.json"
    manifest = _load_mapping(manifest_path)
    expected = {
        "schema_version": _REGISTERED_SCHEMA,
        "hypothesis_id": _HYPOTHESIS,
        "status": "registered_before_candidate_signals_or_outcomes",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "live_change_authorized": False,
        "candidate_signals_computed": False,
        "candidate_outcomes_computed": False,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("registered option-flow source identity or authority drifted")
    _require_bound_file(manifest, "instrument_preregistration", preregistration)
    _require_bound_file(manifest, "experiment_protocol", protocol)
    verify_file_evidence(bundle, manifest.get("files"))
    path = bundle / "hourly_flow.parquet"
    hourly = pd.read_parquet(path)
    evidence = {
        "bundle": str(bundle.resolve()),
        "manifest": file_evidence(manifest_path),
        "hourly_flow": file_evidence(path),
        "candidate_signals_computed": False,
        "candidate_outcomes_computed": False,
    }
    return hourly, evidence


def experiment_partitions(
    preregistration: Mapping[str, object], protocol: Mapping[str, object]
) -> tuple[tuple[OptionFlowPartition, ...], tuple[OptionFlowPartition, ...]]:
    """Construct exact runtime partitions from the frozen contracts."""
    values = _mapping(preregistration, "partitions")
    partitions = tuple(
        _partition(name, values.get(field))
        for name, field in (
            ("development", "development_entries"),
            ("validation", "validation_entries"),
            ("pseudo_holdout", "pseudo_holdout_entries"),
        )
    )
    raw_folds = protocol.get("development_folds")
    if not isinstance(raw_folds, list) or len(raw_folds) != 5:
        raise ValueError("option-flow protocol lacks five development folds")
    folds = tuple(_fold(value, index) for index, value in enumerate(raw_folds))
    return partitions, folds


def load_option_flow_market(
    project: Path, preregistration: Mapping[str, object]
) -> tuple[
    OptionFlowMarketInputs,
    dict[str, object],
    tuple[tuple[Path, dict[str, object]], ...],
]:
    """Load and gap-repair the exact frozen BTC market inputs."""
    source = _mapping(preregistration, "source_contract")
    candles = _mapping(source, "hyperliquid_btc_minutes")
    funding = _mapping(source, "hyperliquid_funding")
    candle_paths, candle_evidence, candle_files = _source_pair(
        project, candles, "candles"
    )
    funding_paths, funding_evidence, funding_files = _source_pair(
        project, funding, "funding"
    )
    start = _timestamp(candles.get("start_utc"), "market start")
    end = _timestamp(candles.get("execution_end_utc"), "execution end")
    merged_candles = merge_option_flow_candles(
        tuple(pd.read_parquet(path) for path in candle_paths), start=start, end=end
    )
    merged_funding = merge_option_flow_funding(
        tuple(pd.read_parquet(path) for path in funding_paths), start=start, end=end
    )
    market = prepare_gap_aware_option_flow_market(
        merged_candles,
        merged_funding,
        start=start,
        end=end,
        maximum_repair_minutes=30,
    )
    files = candle_files + funding_files
    return (
        market,
        {
            "candles": [_path_and_evidence(path) for path in candle_paths],
            "funding": [_path_and_evidence(path) for path in funding_paths],
        },
        files,
    )


def _source_pair(
    project: Path, contract: Mapping[str, object], filename: str
) -> tuple[
    tuple[Path, Path],
    tuple[dict[str, object], dict[str, object]],
    tuple[tuple[Path, dict[str, object]], ...],
]:
    primary = _mapping(contract, "registered_source")
    horizon = _mapping(contract, "execution_horizon_source")
    primary_bundle = _project_path(project, primary.get("bundle"))
    horizon_bundle = _project_path(project, horizon.get("bundle"))
    primary_path = primary_bundle / f"{filename}.parquet"
    horizon_path = horizon_bundle / f"{filename}.parquet"
    evidences = (_mapping(primary, filename), _mapping(horizon, filename))
    primary_manifest = _mapping(primary, "manifest")
    horizon_manifest = _mapping(horizon, "manifest")
    primary_manifest_path = primary_bundle / "manifest.json"
    horizon_manifest_path = horizon_bundle / "manifest.json"
    require_unchanged_file(primary_path, evidences[0])
    require_unchanged_file(horizon_path, evidences[1])
    require_unchanged_file(primary_manifest_path, primary_manifest)
    require_unchanged_file(horizon_manifest_path, horizon_manifest)
    tracked = (
        (primary_path, evidences[0]),
        (horizon_path, evidences[1]),
        (primary_manifest_path, primary_manifest),
        (horizon_manifest_path, horizon_manifest),
    )
    return (primary_path, horizon_path), evidences, tracked


def load_validated_preregistration(path: Path) -> dict[str, object]:
    """Load and validate the frozen option-flow preregistration."""
    value = _load_mapping(path)
    if value.get("schema_version") != _PREREGISTRATION_SCHEMA:
        raise ValueError("option-flow experiment preregistration schema drifted")
    if value.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("option-flow experiment hypothesis drifted")
    if (
        value.get("execution_authority") != "none"
        or value.get("live_change_authorized") is not False
    ):
        raise ValueError("option-flow experiment preregistration gained live authority")
    return value


def load_validated_protocol(path: Path) -> dict[str, object]:
    """Load and validate the frozen option-flow experiment protocol."""
    value = _load_mapping(path)
    if value.get("schema_version") != _PROTOCOL_SCHEMA:
        raise ValueError("option-flow experiment protocol schema drifted")
    authority = _mapping(value, "authority")
    if (
        authority.get("execution_authority") != "none"
        or authority.get("live_change_authorized") is not False
    ):
        raise ValueError("option-flow experiment protocol gained live authority")
    return value


def _publish(
    output: Path,
    report: dict[str, object],
    trade_rows: Sequence[Mapping[str, object]],
    signals: pd.DataFrame,
) -> Path:
    def writer(staging: Path) -> None:
        trades_path = staging / "trades.parquet"
        signal_path = staging / "signals.parquet"
        trades = pd.DataFrame.from_records(trade_rows)
        if trades.empty:
            trades = pd.DataFrame(columns=("partition", "scenario", "arm"))
        trades.to_parquet(trades_path, index=False)
        signals.to_parquet(signal_path, index=False)
        report["files"] = {
            "trades.parquet": file_evidence(trades_path),
            "signals.parquet": file_evidence(signal_path),
        }
        write_json(staging / "report.json", report)

    publish_immutable_directory(output, writer)
    return output


def _signal_diagnostics(
    signals: pd.DataFrame, partitions: Sequence[OptionFlowPartition]
) -> dict[str, object]:
    available = pd.to_datetime(signals["available_at"], utc=True)
    per_partition: dict[str, dict[str, int]] = {}
    for partition in partitions:
        inside = available.ge(partition.start) & available.lt(partition.end)
        per_partition[partition.name] = {
            "primary_onsets": int(signals.loc[inside, "long_onset"].sum()),
            "opposing_onsets": int(signals.loc[inside, "opposing_onset"].sum()),
        }
    return {
        "hour_rows": len(signals),
        "eligible_hours": int(signals["directional_imbalance"].notna().sum()),
        "threshold_ready_hours": int(signals["upper_threshold"].notna().sum()),
        "primary_onsets": int(signals["long_onset"].sum()),
        "opposing_onsets": int(signals["opposing_onset"].sum()),
        "per_partition": per_partition,
    }


def _protocol_integer(protocol: Mapping[str, object], key: str) -> int:
    value = _mapping(protocol, "pooled_oos_trade_bootstrap").get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"option-flow bootstrap {key} is invalid")
    return value


def _partition(name: str, value: object) -> OptionFlowPartition:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"option-flow partition bounds are invalid: {name}")
    return OptionFlowPartition(
        name, _timestamp(value[0], name), _timestamp(value[1], name)
    )


def _fold(value: object, index: int) -> OptionFlowPartition:
    if not isinstance(value, dict) or value.get("fold_id") != index:
        raise ValueError("option-flow development fold identity drifted")
    return OptionFlowPartition(
        f"development_fold_{index}",
        _timestamp(value.get("entry_start_utc"), "fold start"),
        _timestamp(value.get("entry_end_exclusive_utc"), "fold end"),
    )


def _require_bound_file(manifest: Mapping[str, object], key: str, path: Path) -> None:
    require_unchanged_file(path, _mapping(manifest, key))


def _project_path(project: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("option-flow source bundle path is invalid")
    path = Path(value)
    return path.resolve() if path.is_absolute() else (project / path).resolve()


def _path_and_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path), **file_evidence(path)}


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _load_mapping(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"option-flow input must be an object: {path}")
    return value


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"option-flow input lacks object: {key}")
    return nested


def _timestamp(value: object, label: str) -> pd.Timestamp:
    if not isinstance(value, str):
        raise ValueError(f"option-flow {label} is not text")
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"option-flow {label} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _utc_text(value: str) -> str:
    return _timestamp(value, "recorded_at_utc").isoformat().replace("+00:00", "Z")


def main() -> int:
    """Publish the frozen report-only experiment and print its path."""
    print(run_command(build_parser().parse_args()).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
