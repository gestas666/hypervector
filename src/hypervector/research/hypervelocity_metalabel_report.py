"""Report assembly for the venue-matched Hypervelocity metalabel challenger."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.ml.hypervelocity_challenger import (
    CANDIDATE_NAMES,
    HypervelocityChallengerResult,
    train_annotation_only_challengers,
)
from hypervector.research.hypervelocity_metalabel import (
    assert_observe_only_policy,
    build_metalabel_rows,
    feature_coverage,
    resolved_candidate_lifecycles,
    resolved_margin_stop_lifecycles,
    signal_times_utc,
)
from hypervector.research.hypervelocity_metalabel_features import (
    DecisionProfile,
    candidate_feature_frames,
    load_model_bars,
    signal_book_features,
)
from hypervector.research.hypervelocity_metalabel_shape import (
    loss_risk_shape_diagnostics,
    population_summary as _population_summary,
    report_limitations as _report_limitations,
)

_EXPECTED_RESOLVED = 407
_EXPECTED_LIQUIDATIONS = 39
_CANONICAL_CANDIDATE = "canonical_breakout_confirmed_first_opposed_obi5_snapshot"

CandidateProfile = Literal[
    "recovery6",
    "canonical-pressure",
    "faithful-stop14",
    "strict-source-runtime60",
]
BarAlignment = Literal["exact", "backward"]


@dataclass(frozen=True)
class MetalabelPopulationContract:
    """Immutable replay identity and causal feature-alignment contract."""

    profile: CandidateProfile
    identity_field: str
    expected_identity: str
    expected_resolved: int
    expected_liquidations: int
    expected_positives: int
    label_column: str
    decision_profile: DecisionProfile
    bar_alignment: BarAlignment
    source_key: str


def metalabel_population_contract(profile: str) -> MetalabelPopulationContract:
    """Return the frozen population contract for one research candidate."""
    if profile == "recovery6":
        return MetalabelPopulationContract(
            "recovery6",
            "event_candidate",
            "5m_bbwp_hard_range_25_recovery_6_cooldown_300s",
            _EXPECTED_RESOLVED,
            _EXPECTED_LIQUIDATIONS,
            _EXPECTED_LIQUIDATIONS,
            "liquidation_risk",
            "recovery6",
            "exact",
            "recovery_report",
        )
    if profile == "canonical-pressure":
        return MetalabelPopulationContract(
            "canonical-pressure",
            "candidate",
            _CANONICAL_CANDIDATE,
            302,
            41,
            41,
            "liquidation_risk",
            "canonical",
            "backward",
            "replay_report",
        )
    if profile == "faithful-stop14":
        return MetalabelPopulationContract(
            "faithful-stop14",
            "comparison.candidates",
            "stop_14pct_margin",
            371,
            1,
            144,
            "loss_risk",
            "faithful",
            "backward",
            "margin_stop_report",
        )
    raise ValueError(f"unknown metalabel candidate profile: {profile}")


def resolved_population_for_contract(
    payload: Mapping[str, object],
    contract: MetalabelPopulationContract,
) -> pd.DataFrame:
    """Resolve the exact lifecycle population declared by a model contract."""
    if contract.profile == "faithful-stop14":
        return resolved_margin_stop_lifecycles(payload)
    return resolved_candidate_lifecycles(
        payload,
        identity_field=contract.identity_field,
        expected_identity=contract.expected_identity,
    )


@dataclass(frozen=True)
class MetalabelDatasetAssembly:
    """Causal model rows and their verified evidence contract."""

    rows: pd.DataFrame
    source_evidence: dict[str, object]
    archive_evidence: dict[str, object]
    runtime_policy: dict[str, object]
    feature_coverage: dict[str, int]
    population_contract: MetalabelPopulationContract


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} contains a non-string key")
    return value


def _read_json(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Hypervelocity recovery evidence is missing: {path}")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Hypervelocity recovery evidence is invalid JSON: {path}"
        ) from exc
    return _mapping(payload, "Hypervelocity recovery evidence")


def runtime_observe_contract(path: Path) -> dict[str, object]:
    """Return and validate the complete faithful runtime model policy."""
    if not path.is_file():
        raise FileNotFoundError(f"faithful runtime config is missing: {path}")
    with path.open("rb") as handle:
        payload = tomllib.load(handle)
    model = _mapping(payload.get("model"), "faithful model policy")
    runtime = _mapping(payload.get("runtime"), "faithful runtime policy")
    policy = {
        "mode": model.get("mode"),
        "may_filter": model.get("may_filter"),
        "may_scale": model.get("may_scale"),
        "runtime_mode": runtime.get("metalabel_mode"),
    }
    assert_observe_only_policy(policy)
    if policy["runtime_mode"] != "observe":
        raise ValueError(f"metalabel runtime mode is not observe-only: {policy}")
    return policy


def verify_recovery_source_files(
    payload: Mapping[str, object],
    bars_path: Path,
    config_path: Path,
) -> dict[str, object]:
    """Verify exact bars and runtime config against the recovery artifact."""
    declared = _mapping(payload.get("source_evidence"), "recovery source evidence")
    observed = {
        "bars": file_evidence(bars_path),
        "runtime_config": file_evidence(config_path),
    }
    for name, value in observed.items():
        if dict(_mapping(declared.get(name), f"declared {name} evidence")) != value:
            raise ValueError(f"{name} source evidence differs from recovery artifact")
    return observed


def _archive_contract(
    payload: Mapping[str, object], start: datetime, end: datetime
) -> dict[str, object]:
    archive = dict(_mapping(payload.get("archive"), "recovery archive evidence"))
    expected = (start.isoformat(), end.isoformat())
    observed = (archive.get("start"), archive.get("end"))
    if observed != expected or archive.get("checksums_verified") is not True:
        raise ValueError("recovery archive bounds or checksum contract differs")
    return archive


def assemble_metalabel_dataset(
    *,
    replay_path: Path,
    bars_path: Path,
    config_path: Path,
    data_root: Path,
    start: datetime,
    end: datetime,
    candidate_profile: str = "recovery6",
) -> MetalabelDatasetAssembly:
    """Rebuild one exact replay population with causal venue features."""
    contract = metalabel_population_contract(candidate_profile)
    payload = _read_json(replay_path)
    sources = verify_recovery_source_files(payload, bars_path, config_path)
    runtime_policy = runtime_observe_contract(config_path)
    archive = _archive_contract(payload, start, end)
    lifecycles = resolved_population_for_contract(payload, contract)
    bars = load_model_bars(bars_path, start, end)
    mode = contract.decision_profile
    decisions, context_5m, bar_features = candidate_feature_frames(
        bars,
        config_path,
        mode,
    )
    signal_times = signal_times_utc(lifecycles)
    book_features = signal_book_features(data_root, start, end, signal_times)
    rows = build_metalabel_rows(
        lifecycles,
        decisions,
        context_5m,
        bar_features,
        book_features,
        bar_alignment=contract.bar_alignment,
        label_column=contract.label_column,
    )
    _validate_frozen_population(rows, contract)
    sources[contract.source_key] = file_evidence(replay_path)
    return MetalabelDatasetAssembly(
        rows,
        sources,
        archive,
        runtime_policy,
        feature_coverage(rows),
        contract,
    )


def _validate_frozen_population(
    rows: pd.DataFrame,
    contract: MetalabelPopulationContract,
) -> None:
    if len(rows) != contract.expected_resolved:
        raise ValueError(
            f"resolved population changed: {len(rows)} != {contract.expected_resolved}"
        )
    positives = int(rows[contract.label_column].sum())
    if positives != contract.expected_positives:
        raise ValueError(
            f"positive population changed: {positives} != {contract.expected_positives}"
        )
    liquidations = int(rows["status"].eq("liquidated").sum())
    if liquidations != contract.expected_liquidations:
        raise ValueError(
            "liquidation population changed: "
            f"{liquidations} != {contract.expected_liquidations}"
        )


def _json_rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    records = frame.astype(object).where(frame.notna(), None).to_dict("records")
    return [{str(key): value for key, value in row.items()} for row in records]


def _ablation(
    fold_metrics: pd.DataFrame, base_name: str, book_name: str
) -> dict[str, object]:
    base = fold_metrics.loc[
        fold_metrics["candidate"].eq(base_name), ["fold_id", "log_loss"]
    ].set_index("fold_id")
    book = fold_metrics.loc[
        fold_metrics["candidate"].eq(book_name), ["fold_id", "log_loss"]
    ].set_index("fold_id")
    delta = book["log_loss"] - base["log_loss"]
    return {
        "base_candidate": base_name,
        "book_candidate": book_name,
        "mean_log_loss_delta_book_minus_base": float(delta.mean()),
        "book_better_folds": int(delta.lt(0.0).sum()),
        "folds_compared": len(delta),
    }


def _assessment(result: HypervelocityChallengerResult) -> dict[str, object]:
    best = min(
        CANDIDATE_NAMES,
        key=lambda name: float(result.metrics[name]["log_loss_mean"]),
    )
    return {
        "selected_by_mean_log_loss": best,
        "selection_is_promotion": False,
        "logistic_book_ablation": _ablation(
            result.fold_metrics, "logistic_base", "logistic_book"
        ),
        "lightgbm_book_ablation": _ablation(
            result.fold_metrics, "lightgbm_base", "lightgbm_book"
        ),
        "logistic_sequence_ablation": _ablation(
            result.fold_metrics, "logistic_book", "logistic_sequence_book"
        ),
        "lightgbm_sequence_ablation": _ablation(
            result.fold_metrics, "lightgbm_book", "lightgbm_sequence_book"
        ),
    }


def _artifact_paths(out_path: Path) -> dict[str, Path]:
    stem = out_path.with_suffix("")
    return {
        "dataset": Path(f"{stem}_dataset.parquet"),
        "predictions": Path(f"{stem}_predictions.parquet"),
        "fold_metrics": Path(f"{stem}_fold_metrics.parquet"),
    }


def _ensure_new_outputs(
    out_path: Path, model_dir: Path, artifact_paths: Mapping[str, Path]
) -> None:
    existing = [
        path
        for path in (out_path, model_dir, *artifact_paths.values())
        if path.exists()
    ]
    if existing:
        raise FileExistsError(f"metalabel output already exists: {existing[0]}")


def generate_metalabel_report(
    *,
    assembly: MetalabelDatasetAssembly,
    out_path: Path,
    model_dir: Path,
    n_splits: int = 3,
    embargo_minutes: int = 60,
) -> dict[str, object]:
    """Train, persist, and report annotation-only model challengers."""
    artifact_paths = _artifact_paths(out_path)
    _ensure_new_outputs(out_path, model_dir, artifact_paths)
    result = train_annotation_only_challengers(
        assembly.rows,
        model_dir,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
        label_column=assembly.population_contract.label_column,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    assembly.rows.to_parquet(artifact_paths["dataset"], index=False)
    result.predictions.to_parquet(artifact_paths["predictions"], index=False)
    result.fold_metrics.to_parquet(artifact_paths["fold_metrics"], index=False)
    report = _report_payload(assembly, result, artifact_paths)
    write_json(out_path, report)
    return report


def _report_payload(
    assembly: MetalabelDatasetAssembly,
    result: HypervelocityChallengerResult,
    artifact_paths: Mapping[str, Path],
) -> dict[str, object]:
    model_evidence = {
        name: file_evidence(path) for name, path in result.model_paths.items()
    }
    data_evidence = {name: file_evidence(path) for name, path in artifact_paths.items()}
    contract = assembly.population_contract
    economic_shape = (
        loss_risk_shape_diagnostics(result.predictions)
        if contract.label_column == "loss_risk"
        else None
    )
    fold_count = int(result.metrics["base_rate"]["folds_used"] or 0)
    segments = assembly.archive_evidence.get("gap_separated_segments")
    exploration_scope = (
        f"The {len(segments)} non-overlapping replay blocks remain exploration "
        "evidence, not a sealed holdout."
        if isinstance(segments, list)
        else "The same 90-day window remains exploration evidence, not a sealed holdout."
    )
    return {
        "ok": True,
        "report_only": True,
        "runtime_strategy_changed": False,
        "runtime_policy": assembly.runtime_policy,
        "candidate_profile": contract.profile,
        "population_contract": {
            "identity_field": contract.identity_field,
            "expected_identity": contract.expected_identity,
            "bar_alignment": contract.bar_alignment,
            "label_column": contract.label_column,
        },
        "label": contract.label_column,
        "population": _population_summary(assembly.rows, contract.label_column),
        "searched_set": list(CANDIDATE_NAMES),
        "source_evidence": assembly.source_evidence,
        "archive_evidence": assembly.archive_evidence,
        "feature_coverage": assembly.feature_coverage,
        "metrics": result.metrics,
        "fold_metrics": _json_rows(result.fold_metrics),
        "assessment": _assessment(result),
        "economic_shape": economic_shape,
        "model_evidence": model_evidence,
        "data_evidence": data_evidence,
        "limitations": _report_limitations(
            label_column=contract.label_column,
            expected_resolved=contract.expected_resolved,
            expected_positives=contract.expected_positives,
            fold_count=fold_count,
            exploration_scope=exploration_scope,
        ),
    }
