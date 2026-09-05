#!/usr/bin/env python3
"""Register verified BTC Deribit option-flow source features without signals."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_json,
)
from hypervector.research.btc_option_flow_source_materialization import (
    materialize_registered_hourly_flow,
)
from hypervector.research.deribit_option_bundle_reproduction import (
    reproduce_deribit_option_bundle,
)
from hypervector.research.deribit_instrument_supplement import (
    reproduce_deribit_instrument_supplement,
)


_HYPOTHESIS = "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1"
_V1_SCHEMA = "v58_btc_deribit_option_flow_long_preregistration_v1"
_V2_SCHEMA = "v58_btc_deribit_option_flow_long_preregistration_v2"
_V2_STATUS = "source_revision_preregistered_before_candidate_outcomes"
_V3_SCHEMA = "v58_btc_deribit_option_flow_long_preregistration_v3"
_V3_STATUS = "execution_horizon_revision_preregistered_before_candidate_outcomes"
_PROTOCOL_SCHEMA = "v58_btc_deribit_option_flow_experiment_protocol_v1"
_PROTOCOL_STATUS = "evaluation_semantics_frozen_before_signals_or_outcomes"
_V4_SCHEMA = "v58_btc_deribit_option_flow_long_preregistration_v4"
_V4_STATUS = "instrument_dictionary_revision_preregistered_before_candidate_signals"
_SOURCE = Path(
    "data/cache/vendor/deribit/BTC_OPTIONS/"
    "20250401T000000Z_20260801T000000Z_directional_flow_v1"
)
_V1 = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v1.json"
)
_V2 = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v2.json"
)
_V3 = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v3.json"
)
_PROTOCOL = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-experiment-protocol-20260822-v1.json"
)
_V4 = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v4.json"
)
_COMPLETENESS = Path(
    "docs/research-journal/"
    "v58-btc-deribit-instrument-completeness-audit-20260822-v1.json"
)
_SUPPLEMENT = Path(
    "data/cache/vendor/deribit/BTC_OPTIONS/"
    "20260822T000000Z_exact_missing_instruments_v1"
)
_OUTPUT = Path("data/cache/research/v58_btc_deribit_option_flow_source_20260822_v2")


@dataclass(frozen=True)
class _RegistrationContext:
    original: dict[str, object]
    revised: dict[str, object]
    execution: dict[str, object]
    experiment_protocol: dict[str, object]
    instrument_preregistration: dict[str, object]
    completeness_audit: dict[str, object]
    start: pd.Timestamp
    end: pd.Timestamp


def build_parser() -> argparse.ArgumentParser:
    """Return the exact source-registration parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-bundle", type=Path, default=_SOURCE)
    parser.add_argument("--original-preregistration", type=Path, default=_V1)
    parser.add_argument("--revised-preregistration", type=Path, default=_V2)
    parser.add_argument("--execution-preregistration", type=Path, default=_V3)
    parser.add_argument("--experiment-protocol", type=Path, default=_PROTOCOL)
    parser.add_argument("--instrument-preregistration", type=Path, default=_V4)
    parser.add_argument("--completeness-audit", type=Path, default=_COMPLETENESS)
    parser.add_argument("--instrument-supplement", type=Path, default=_SUPPLEMENT)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--recorded-at-utc", required=True)
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Reproduce, materialize, and atomically register the frozen source."""
    context = _registration_context(
        args.original_preregistration,
        args.revised_preregistration,
        args.execution_preregistration,
        args.experiment_protocol,
        args.instrument_preregistration,
        args.completeness_audit,
    )
    reproduction = reproduce_deribit_option_bundle(args.source_bundle)
    supplement_reproduction = reproduce_deribit_instrument_supplement(
        args.instrument_supplement
    )
    hourly, source_audit = materialize_registered_hourly_flow(
        args.source_bundle,
        start=context.start,
        end=context.end,
        expected_preregistration_sha256=str(context.original["sha256"]),
        supplemental_instruments_path=(
            args.instrument_supplement / "instruments.parquet"
        ),
    )
    _validate_hourly(hourly, context.start, context.end)
    recorded_at = _validated_recorded_at(args.recorded_at_utc)

    def writer(staging: Path) -> None:
        hourly_path = staging / "hourly_flow.parquet"
        hourly.to_parquet(hourly_path, index=False)
        manifest = _manifest(
            source_bundle=args.source_bundle,
            context=context,
            recorded_at_utc=recorded_at,
            reproduction=reproduction.to_dict(),
            source_audit=source_audit.to_dict(),
            supplement_bundle=args.instrument_supplement,
            supplement_reproduction=supplement_reproduction.to_dict(),
            hourly_path=hourly_path,
        )
        write_json(staging / "manifest.json", manifest)

    publish_immutable_directory(args.output, writer)
    return args.output


def main() -> int:
    """Publish the registered source bundle and print its path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _registration_context(
    original_path: Path,
    revised_path: Path,
    execution_path: Path,
    protocol_path: Path,
    instrument_path: Path,
    completeness_path: Path,
) -> _RegistrationContext:
    original, revised, execution, protocol, instrument = _registration_contracts(
        original_path,
        revised_path,
        execution_path,
        protocol_path,
        instrument_path,
    )
    completeness = _load_mapping(completeness_path)
    _validate_instrument_revision(instrument, completeness_path, completeness)
    trades = _mapping(_mapping(revised, "source_contract"), "deribit_trades")
    start = _aware_hour(trades.get("start_utc"), "analysis start")
    end = _aware_hour(trades.get("end_utc"), "analysis end")
    if end <= start:
        raise ValueError("option-flow source registration window is not increasing")
    return _RegistrationContext(
        original={"path": str(original_path.resolve()), **file_evidence(original_path)},
        revised={"path": str(revised_path.resolve()), **file_evidence(revised_path)},
        execution={
            "path": str(execution_path.resolve()),
            **file_evidence(execution_path),
        },
        experiment_protocol={
            "path": str(protocol_path.resolve()),
            **file_evidence(protocol_path),
        },
        instrument_preregistration={
            "path": str(instrument_path.resolve()),
            **file_evidence(instrument_path),
        },
        completeness_audit={
            "path": str(completeness_path.resolve()),
            **file_evidence(completeness_path),
        },
        start=start,
        end=end,
    )


def _registration_contracts(
    original_path: Path,
    revised_path: Path,
    execution_path: Path,
    protocol_path: Path,
    instrument_path: Path,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    values = tuple(
        _load_mapping(path)
        for path in (
            original_path,
            revised_path,
            execution_path,
            protocol_path,
            instrument_path,
        )
    )
    original, revised, execution, protocol, instrument = values
    _require_identity(original, _V1_SCHEMA, None, "original preregistration")
    _require_identity(revised, _V2_SCHEMA, _V2_STATUS, "revised preregistration")
    _require_identity(execution, _V3_SCHEMA, _V3_STATUS, "execution preregistration")
    _require_identity(protocol, _PROTOCOL_SCHEMA, _PROTOCOL_STATUS, "protocol")
    _require_identity(instrument, _V4_SCHEMA, _V4_STATUS, "instrument revision")
    if any(value.get("hypothesis_id") != _HYPOTHESIS for value in values):
        raise ValueError("option-flow registration hypothesis identity drifted")
    _validate_revised_authority(revised)
    _validate_revised_authority(execution)
    _validate_protocol_authority(protocol)
    _validate_revised_authority(instrument)
    return values


def _require_identity(
    value: Mapping[str, object], schema: str, status: str | None, label: str
) -> None:
    if value.get("schema_version") != schema:
        raise ValueError(f"option-flow {label} schema drifted")
    if status is not None and value.get("status") != status:
        raise ValueError(f"option-flow {label} status drifted")


def _validate_revised_authority(value: Mapping[str, object]) -> None:
    expected = {
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "orders_supported": False,
        "live_change_authorized": False,
        "outcomes_inspected_before_preregistration": False,
        "candidate_signal_counts_inspected": False,
        "candidate_forward_returns_inspected": False,
        "candidate_trade_outcomes_inspected": False,
    }
    if any(
        value.get(key) != expected_value for key, expected_value in expected.items()
    ):
        raise ValueError(
            "revised option-flow preregistration gained outcome/live authority"
        )


def _validate_protocol_authority(value: Mapping[str, object]) -> None:
    authority = _mapping(value, "authority")
    if authority != {
        "execution_authority": "none",
        "live_change_authorized": False,
        "automatic_promotion": False,
    }:
        raise ValueError("option-flow experiment protocol gained live authority")
    blindness = _mapping(value, "outcome_blindness")
    if any(item is not False for item in blindness.values()):
        raise ValueError("option-flow experiment protocol is not outcome-blind")


def _validate_instrument_revision(
    value: Mapping[str, object],
    completeness_path: Path,
    completeness: Mapping[str, object],
) -> None:
    expected = "instrument_dictionary_gap_identified_before_candidate_signals"
    if completeness.get("status") != expected:
        raise ValueError("option-flow instrument completeness status drifted")
    revision = _mapping(value, "instrument_dictionary_revision")
    evidence = _mapping(revision, "completeness_audit")
    observed = file_evidence(completeness_path)
    if observed != {
        "sha256": evidence.get("sha256"),
        "bytes": evidence.get("bytes"),
    }:
        raise ValueError("option-flow instrument completeness hash drifted")
    for field in (
        "candidate_signals_opened",
        "candidate_outcomes_opened",
        "candidate_parameters_changed",
    ):
        if revision.get(field) is not False:
            raise ValueError(
                "option-flow instrument revision opened candidate evidence"
            )


def _validate_hourly(
    frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> None:
    required = {
        "timestamp",
        "eligible_trade_count",
        "weight_usd",
        "signed_weight_usd",
        "directional_imbalance",
    }
    if required.difference(frame.columns):
        raise ValueError("registered option-flow hourly source lacks required columns")
    timestamps = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    expected = pd.date_range(start, end, freq="1h", inclusive="left")
    if not timestamps.equals(expected):
        raise ValueError("registered option-flow hourly source cadence drifted")


def _manifest(
    *,
    source_bundle: Path,
    context: _RegistrationContext,
    recorded_at_utc: str,
    reproduction: Mapping[str, object],
    source_audit: Mapping[str, object],
    supplement_bundle: Path,
    supplement_reproduction: Mapping[str, object],
    hourly_path: Path,
) -> dict[str, object]:
    return {
        "schema_version": "v58_btc_deribit_option_flow_registered_source_v2",
        "hypothesis_id": _HYPOTHESIS,
        "recorded_at_utc": recorded_at_utc,
        "status": "registered_before_candidate_signals_or_outcomes",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "live_change_authorized": False,
        "candidate_signals_computed": False,
        "candidate_outcomes_computed": False,
        "source_bundle": str(source_bundle.resolve()),
        "analysis_start_utc": context.start.isoformat(),
        "analysis_end_utc": context.end.isoformat(),
        "original_preregistration": context.original,
        "revised_preregistration": context.revised,
        "execution_preregistration": context.execution,
        "experiment_protocol": context.experiment_protocol,
        "instrument_preregistration": context.instrument_preregistration,
        "instrument_completeness_audit": context.completeness_audit,
        "instrument_supplement_bundle": str(supplement_bundle.resolve()),
        "instrument_supplement_reproduction": dict(supplement_reproduction),
        "raw_reproduction": dict(reproduction),
        "source_audit": dict(source_audit),
        "files": {"hourly_flow.parquet": file_evidence(hourly_path)},
    }


def _load_mapping(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"option-flow preregistration is missing: {path}")
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"option-flow preregistration must be an object: {path}")
    return value


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"option-flow preregistration lacks object: {key}")
    return nested


def _aware_hour(value: object, label: str) -> pd.Timestamp:
    if not isinstance(value, str):
        raise ValueError(f"option-flow {label} is not text")
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None or timestamp != timestamp.floor("h"):
        raise ValueError(f"option-flow {label} must be an aware whole hour")
    return timestamp.tz_convert("UTC")


def _validated_recorded_at(value: str) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("recorded_at_utc must be timezone-aware")
    return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
