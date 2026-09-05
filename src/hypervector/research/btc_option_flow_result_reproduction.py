"""Independent arithmetic reproduction for BTC option-flow result artifacts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, verify_file_evidence
from hypervector.research.btc_option_flow_acceptance import (
    evaluate_frozen_option_flow_acceptance,
)


_PARTITIONS = ("development", "validation", "pseudo_holdout")
_SCENARIOS = ("nominal", "stress", "delayed")
_ARMS = (
    "candidate",
    "direction_inverted_placebo",
    "sweep_control",
    "no_action",
)


@dataclass(frozen=True)
class BtcOptionFlowResultReproduction:
    """Independent output-file and economic-arithmetic audit."""

    bundle: str
    report: dict[str, object]
    trades: dict[str, object]
    signals: dict[str, object]
    summary_cells: int
    trade_rows: int
    signal_rows: int
    main_cell_arithmetic_verified: bool
    acceptance_predicates_recomputed: bool
    development_fold_trade_sidecar_complete: bool
    full_trade_level_reproduction: bool
    all_output_files_verified: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible reproduction record."""
        return asdict(self)


def reproduce_btc_option_flow_result(
    bundle: Path,
) -> BtcOptionFlowResultReproduction:
    """Verify immutable outputs and independently recalculate main-cell metrics."""
    report_path = bundle / "report.json"
    report = _load_mapping(report_path)
    _validate_report_identity(report)
    verify_file_evidence(bundle, report.get("files"))
    trades_path, signals_path = bundle / "trades.parquet", bundle / "signals.parquet"
    trades = pd.read_parquet(trades_path)
    signals = pd.read_parquet(signals_path)
    rows = _summary_rows(report)
    _reconcile_all_summaries(rows, trades)
    _reconcile_signals(report, signals)
    _reconcile_acceptance(report, rows, trades)
    return BtcOptionFlowResultReproduction(
        str(bundle.resolve()),
        file_evidence(report_path),
        file_evidence(trades_path),
        file_evidence(signals_path),
        len(rows),
        len(trades),
        len(signals),
        True,
        True,
        False,
        False,
        True,
    )


def reconcile_trade_summary(
    summary: Mapping[str, object], trades: pd.DataFrame
) -> None:
    """Raise unless one summary exactly follows from its complete trade rows."""
    net = pd.to_numeric(trades.get("net_pnl_usd"), errors="raise").astype(float)
    fees = pd.to_numeric(trades.get("fees_usd"), errors="raise").astype(float)
    funding = pd.to_numeric(trades.get("funding_cashflow_usd"), errors="raise").astype(
        float
    )
    positive = net[net > 0.0]
    nonpositive = net[net <= 0.0]
    gross_loss = float(-nonpositive.sum())
    profit_factor = float(positive.sum()) / gross_loss if gross_loss else None
    largest = float(positive.max()) if len(positive) else None
    expected = {
        "completed_trades": len(trades),
        "wins": len(positive),
        "losses": len(nonpositive),
        "net_pnl_usd": float(net.sum()),
        "profit_factor": profit_factor,
        "total_fees_usd": float(fees.sum()),
        "funding_cashflow_usd": float(funding.sum()),
        "largest_winner_usd": largest,
        "net_pnl_excluding_largest_winner_usd": (
            float(net.sum()) - largest if largest is not None else float(net.sum())
        ),
        "exit_reasons": dict(sorted(Counter(trades["exit_reason"]).items())),
    }
    for key, value in expected.items():
        _require_equal(summary.get(key), value, _label(key))


def reconcile_development_fold_summaries(
    summaries: list[dict[str, object]], trades: pd.DataFrame
) -> None:
    """Raise unless frozen development-fold summaries match their sidecar."""
    indexed = {_integer(row.get("fold_id"), "fold ID"): row for row in summaries}
    if len(indexed) != len(summaries):
        raise ValueError("option-flow development fold summaries are duplicated")
    required_columns = {"fold_id", "net_pnl_usd"}
    if not required_columns.issubset(trades.columns):
        raise ValueError("option-flow development fold sidecar lacks required columns")
    observed_ids = set(
        pd.to_numeric(trades["fold_id"], errors="raise").astype(int).tolist()
    )
    unexpected = observed_ids.difference(indexed)
    if unexpected:
        raise ValueError(
            f"option-flow development sidecar has unexpected fold IDs: {sorted(unexpected)}"
        )
    for fold_id, summary in indexed.items():
        selected = trades.loc[trades["fold_id"].eq(fold_id)]
        net = pd.to_numeric(selected["net_pnl_usd"], errors="raise").astype(float)
        _require_equal(
            summary.get("completed_trades"),
            len(selected),
            f"fold {fold_id} completed trades",
        )
        _require_equal(
            summary.get("net_pnl_usd"),
            float(net.sum()),
            f"fold {fold_id} net PnL",
        )


def _reconcile_all_summaries(
    rows: list[dict[str, object]], trades: pd.DataFrame
) -> None:
    required = {
        (partition, scenario, arm)
        for partition in _PARTITIONS
        for scenario in _SCENARIOS
        for arm in _ARMS
    }
    indexed = {
        (str(row.get("partition")), str(row.get("scenario")), str(row.get("arm"))): row
        for row in rows
    }
    if set(indexed) != required or len(indexed) != len(rows):
        raise ValueError(
            "option-flow result summary cells are incomplete or duplicated"
        )
    for key, summary in indexed.items():
        selected = _trade_cell(trades, *key)
        if key[2] == "no_action":
            if not selected.empty or summary.get("net_pnl_usd") != 0.0:
                raise ValueError("option-flow no-action cell is not zero")
        else:
            reconcile_trade_summary(summary, selected)


def _reconcile_acceptance(
    report: Mapping[str, object],
    rows: list[dict[str, object]],
    trades: pd.DataFrame,
) -> None:
    acceptance = _mapping(report, "acceptance")
    bootstrap = _mapping(acceptance, "pooled_oos_trade_bootstrap")
    oos = [row for row in rows if row.get("partition") != "development"]
    pooled = trades.loc[
        trades["partition"].isin(("validation", "pseudo_holdout"))
        & trades["scenario"].eq("nominal")
        & trades["arm"].eq("candidate"),
        "net_pnl_usd",
    ].tolist()
    folds = report.get("development_fold_rows")
    if not isinstance(folds, list):
        raise ValueError("option-flow result lacks development fold summaries")
    recomputed = evaluate_frozen_option_flow_acceptance(
        oos,
        folds,
        pooled_oos_trade_net_pnl_usd=pooled,
        bootstrap_resamples=_integer(bootstrap.get("resamples"), "bootstrap resamples"),
        bootstrap_seed=_integer(bootstrap.get("seed"), "bootstrap seed"),
    )
    if recomputed != acceptance:
        raise ValueError("option-flow acceptance predicates do not reproduce")


def _reconcile_signals(report: Mapping[str, object], signals: pd.DataFrame) -> None:
    diagnostics = _mapping(report, "signal_diagnostics")
    expected = {
        "hour_rows": len(signals),
        "eligible_hours": int(signals["directional_imbalance"].notna().sum()),
        "threshold_ready_hours": int(signals["upper_threshold"].notna().sum()),
        "primary_onsets": int(signals["long_onset"].sum()),
        "opposing_onsets": int(signals["opposing_onset"].sum()),
    }
    if any(diagnostics.get(key) != value for key, value in expected.items()):
        raise ValueError("option-flow signal diagnostics do not reproduce")


def _trade_cell(
    trades: pd.DataFrame, partition: str, scenario: str, arm: str
) -> pd.DataFrame:
    return trades.loc[
        trades["partition"].eq(partition)
        & trades["scenario"].eq(scenario)
        & trades["arm"].eq(arm)
    ]


def _validate_report_identity(value: Mapping[str, object]) -> None:
    if value.get("schema_version") != "v58_btc_deribit_option_flow_experiment_v1":
        raise ValueError("option-flow result schema drifted")
    authority = _mapping(value, "authority")
    if (
        authority.get("execution_authority") != "none"
        or authority.get("live_configuration_changed") is not False
    ):
        raise ValueError("option-flow result gained live authority")


def _summary_rows(report: Mapping[str, object]) -> list[dict[str, object]]:
    value = report.get("summary_rows")
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError("option-flow result lacks summary rows")
    return value


def _require_equal(observed: object, expected: object, label: str) -> None:
    if isinstance(expected, float):
        if not isinstance(observed, (int, float)) or not math.isclose(
            float(observed), expected, rel_tol=1e-10, abs_tol=1e-8
        ):
            raise ValueError(f"option-flow {label} does not reproduce")
    elif observed != expected:
        raise ValueError(f"option-flow {label} does not reproduce")


def _label(key: str) -> str:
    return {
        "net_pnl_usd": "net PnL",
        "profit_factor": "profit factor",
    }.get(key, key.replace("_", " "))


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"option-flow {label} is invalid")
    return value


def _load_mapping(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("option-flow result report must be an object")
    return value


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"option-flow result lacks object: {key}")
    return nested
