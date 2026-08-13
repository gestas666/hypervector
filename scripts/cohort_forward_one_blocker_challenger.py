#!/usr/bin/env python3
"""Publish one frozen post-cutoff exact-one-blocker challenger."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

from requests import RequestException

from hypervector.data.hl_funding_evidence import (
    HlFundingEvidence,
    read_complete_hl_funding_evidence,
)
from hypervector.data.hl_funding_archive import (
    HlFundingRequest,
    acquire_and_store_hl_funding,
    funding_output_directory,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_candidate_portfolio_journal import (
    CandidatePortfolioJournalSpec,
    build_candidate_portfolio_journal,
)
from hypervector.research.cohort_forward_one_blocker_challenger import (
    ForwardOneBlockerChallengerSpec,
    build_forward_challenger_report,
)
from hypervector.research.cohort_forward_experiments import (
    FORWARD_EXPERIMENT_NAMES,
    ForwardExperiment as _Experiment,
    forward_experiment as _experiment,
    source_authority_matches,
)
from hypervector.research.cohort_live_audit_values import (
    event_rows,
    is_armed_live,
    payload,
    run_id,
    text,
)
from hypervector.research.cohort_live_run_selection import (
    select_compatible_armed_live_runs,
)
from hypervector.research.cohort_one_blocker_execution_feasibility import (
    build_one_blocker_execution_feasibility,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

_SYMBOL = "HYPE"
_HORIZON_MINUTES = 60
_MINIMUM_ENTRY_SPACING_MINUTES = 75
_MAXIMUM_CONTEXT_AGE_MS = 30_000
_MAXIMUM_EXIT_DELAY_MS = 30_000
_TAKER_FEE_RATE = 0.000432


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--funding", type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--matrix-template", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--experiment",
        choices=FORWARD_EXPERIMENT_NAMES,
        default="v2-fixed",
    )
    parser.add_argument("--interval-seconds", type=float, default=300.0)
    parser.add_argument("--once", action="store_true")
    return parser


def _publish(args: argparse.Namespace) -> dict[str, object]:
    config = load_multi_asset_live_config(args.config, mode="observe")
    experiment = _experiment(args.experiment)
    spec = _frozen_spec(config, experiment)
    observed_at = datetime.now(timezone.utc)
    funding = _funding_evidence(args.funding, args.data_root, observed_at, experiment)
    with ExitStack() as stack:
        cohort_path = args.ledger_root / "decisions.jsonl"
        cohort, cohort_evidence = stack.enter_context(
            snapshot_decision_ledger(cohort_path, allow_incomplete_tail=True)
        )
        selected, identities = select_compatible_armed_live_runs(
            cohort,
            profile_fingerprint=config.profile_fingerprint,
            required_run_id=args.run_id,
        )
        compatible_run_ids = tuple(run_id(identity) for identity in identities)
        for identity in identities:
            _validate_runtime_identity(identity, config, run_id(identity))
        asset_path = args.ledger_root / f"{experiment.symbol.lower()}.jsonl"
        asset, asset_evidence = stack.enter_context(
            snapshot_decision_ledger(asset_path, allow_incomplete_tail=True)
        )
        selected_asset = _select_compatible_asset_records(
            asset,
            compatible_run_ids,
            experiment.symbol,
        )
        replay = build_one_blocker_execution_feasibility(
            selected,
            {experiment.symbol: selected_asset},
            funding.rows,
            contract=spec.execution_contract(),
        )
        _validate_funding_coverage(replay, funding.start_ms, funding.end_ms)
    report = _build_report(selected, replay, spec, experiment, config.maximum_positions)
    report["generated_at_utc"] = observed_at.isoformat()
    report["evidence"] = _report_evidence(
        args,
        config,
        compatible_run_ids,
        cohort_path,
        cohort_evidence,
        asset_path,
        asset_evidence,
        funding,
    )
    matrix = _matrix_template(args.matrix_template)
    matrix["forward_challenger"] = report
    matrix["runtime_updated_at_utc"] = report["generated_at_utc"]
    write_atomic_json(args.out, matrix)
    return report


def _build_report(
    selected: Sequence[Mapping[str, object]],
    replay: Mapping[str, object],
    spec: ForwardOneBlockerChallengerSpec,
    experiment: _Experiment,
    maximum_positions: int,
) -> dict[str, object]:
    report = build_forward_challenger_report(replay, spec=spec)
    report["portfolio_journal"] = build_candidate_portfolio_journal(
        selected,
        replay,
        spec=CandidatePortfolioJournalSpec(
            source_strategy_id=experiment.source_strategy_id,
            candidate_strategy_id=experiment.candidate_strategy_id,
            symbol=experiment.symbol,
            maximum_positions=maximum_positions,
        ),
    )
    return report


def _report_evidence(
    args: argparse.Namespace,
    config: MultiAssetLiveConfig,
    compatible_run_ids: Sequence[str],
    cohort_path: Path,
    cohort_evidence: Mapping[str, object],
    asset_path: Path,
    asset_evidence: Mapping[str, object],
    funding: HlFundingEvidence,
) -> dict[str, object]:
    return {
        "run_id": args.run_id,
        "compatible_run_ids": list(compatible_run_ids),
        "compatible_run_count": len(compatible_run_ids),
        "profile_fingerprint": config.profile_fingerprint,
        "config": str(args.config),
        "cohort": {"path": str(cohort_path), **cohort_evidence},
        "asset": {"path": str(asset_path), **asset_evidence},
        "funding": funding.evidence,
    }


def _funding_evidence(
    explicit_path: Path | None,
    data_root: Path,
    observed_at: datetime,
    experiment: _Experiment,
) -> HlFundingEvidence:
    if explicit_path is not None:
        return read_complete_hl_funding_evidence(explicit_path, experiment.symbol)
    request = _funding_request(observed_at, experiment)
    directory = funding_output_directory(data_root, request)
    path = directory / "funding.parquet"
    if not path.is_file():
        acquire_and_store_hl_funding(data_root=data_root, request=request)
    return read_complete_hl_funding_evidence(path, experiment.symbol)


def _funding_request(
    observed_at: datetime,
    experiment: _Experiment | None = None,
) -> HlFundingRequest:
    if observed_at.tzinfo is None:
        raise ValueError("forward challenger time must include a timezone")
    selected = experiment or _experiment("v2-fixed")
    current = observed_at.astimezone(timezone.utc)
    start = datetime.fromtimestamp(
        selected.funding_start_time_ms / 1_000,
        tz=timezone.utc,
    ).replace(minute=0, second=0, microsecond=0)
    end = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    if end <= start:
        raise ValueError("forward challenger funding window is not yet available")
    return HlFundingRequest(symbol=selected.symbol, start=start, end=end)


def _frozen_spec(
    config: MultiAssetLiveConfig, experiment: _Experiment
) -> ForwardOneBlockerChallengerSpec:
    providers = [
        row
        for row in config.providers
        if row.strategy_id == experiment.source_strategy_id
    ]
    assets = [row for row in config.assets if row.symbol == experiment.symbol]
    if len(providers) != 1 or len(assets) != 1:
        raise ValueError("frozen challenger requires one exact provider and asset")
    provider, asset = providers[0], assets[0]
    execution = provider.execution
    sizing = provider.entry_sizing(experiment.symbol)
    notional_usd = sizing.max_notional_usd if sizing else asset.max_notional_usd
    if (
        experiment.symbol not in provider.symbols
        or not source_authority_matches(experiment, provider.execution_symbols)
        or provider.executable_sides(experiment.symbol) != frozenset({"long", "short"})
        or execution.entry_liquidity != "taker_ioc"
        or not _source_stop_matches(execution, experiment)
        or notional_usd != experiment.notional_usd
    ):
        raise ValueError(
            f"deployed {experiment.symbol} contract no longer matches the challenger"
        )
    return ForwardOneBlockerChallengerSpec(
        strategy_id=experiment.source_strategy_id,
        symbol=experiment.symbol,
        blocker=experiment.blocker,
        cutoff_time_ms=experiment.cutoff_time_ms,
        horizon_minutes=_HORIZON_MINUTES,
        maximum_context_age_ms=_MAXIMUM_CONTEXT_AGE_MS,
        maximum_entry_delay_ms=provider.maximum_entry_delay_seconds * 1_000,
        maximum_exit_delay_ms=_MAXIMUM_EXIT_DELAY_MS,
        notional_usd=experiment.notional_usd,
        taker_fee_rate=_TAKER_FEE_RATE,
        stop_proxy_bps=experiment.stop_proxy_bps,
        opi_cohort=experiment.opi_cohort,
        target_proxy_bps=experiment.target_proxy_bps,
        minimum_entry_spacing_minutes=_MINIMUM_ENTRY_SPACING_MINUTES,
        source_authority=experiment.source_authority,
    )


def _source_stop_matches(
    execution: ProviderExecutionContract, experiment: _Experiment
) -> bool:
    if execution.stop_policy != experiment.source_stop_policy:
        return False
    if experiment.source_stop_policy == "fixed_bps":
        return (
            experiment.source_stop_range_bps is None
            and execution.stop_bps == experiment.stop_proxy_bps
        )
    if experiment.source_stop_policy != "structural_clamped_bps":
        return False
    bounds = experiment.source_stop_range_bps
    return (
        bounds is not None
        and execution.minimum_stop_bps == bounds[0]
        and execution.maximum_stop_bps == bounds[1]
        and experiment.stop_proxy_bps == bounds[1]
    )


def _validate_runtime_identity(
    identity: Mapping[str, object], config: MultiAssetLiveConfig, expected_run_id: str
) -> None:
    values = payload(identity)
    if run_id(identity) != expected_run_id:
        raise ValueError("forward challenger run identity changed")
    if values.get("profile_fingerprint") != config.profile_fingerprint:
        raise ValueError("forward challenger profile fingerprint changed")


def _select_compatible_asset_records(
    records: Sequence[Mapping[str, object]],
    compatible_run_ids: Sequence[str],
    symbol: str = _SYMBOL,
) -> tuple[Mapping[str, object], ...]:
    """Bind asset books to the exact compatible cohort restarts."""
    run_ids = tuple(compatible_run_ids)
    if not run_ids or len(set(run_ids)) != len(run_ids):
        raise ValueError("compatible asset run ids must be unique and non-empty")
    allowed = set(run_ids)
    selected = tuple(row for row in records if row.get("run_id") in allowed)
    if not selected or not all(is_armed_live(row) for row in selected):
        raise ValueError("compatible asset history contains non-armed evidence")
    execution_identities: list[tuple[str, str, str]] = []
    for source_run_id in run_ids:
        run_rows = tuple(row for row in selected if row.get("run_id") == source_run_id)
        identities = event_rows(run_rows, "configuration_identity")
        if len(identities) != 1 or payload(identities[0]).get("symbol") != symbol:
            raise ValueError(
                f"{symbol} asset identity is invalid for run {source_run_id}"
            )
        execution_identities.append(
            tuple(
                text(identities[0].get(key), key)
                for key in ("profile_id", "profile_fingerprint", "run_fingerprint")
            )
        )
    if len(set(execution_identities)) != 1:
        raise ValueError("compatible asset execution identity changed across runs")
    return selected


def _validate_funding_coverage(
    replay: Mapping[str, object], start_ms: int, end_ms: int
) -> None:
    executions = replay.get("executions")
    if not isinstance(executions, Sequence) or isinstance(executions, (str, bytes)):
        raise ValueError("forward replay executions must be a sequence")
    for row in executions:
        if not isinstance(row, Mapping):
            raise ValueError("forward replay execution must be a mapping")
        entry, exit_time = row.get("entry_time_ms"), row.get("exit_time_ms")
        if not isinstance(entry, int) or not isinstance(exit_time, int):
            raise ValueError("forward replay execution interval is invalid")
        if entry < start_ms or exit_time >= end_ms:
            raise ValueError("funding evidence does not cover forward execution")


def _matrix_template(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"matrix template does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("matrix template must be a JSON object")
    contract = value.get("contract")
    if (
        value.get("schema_version") != 1
        or value.get("mode") != "cohort_execution_opportunity_matrix"
        or not isinstance(contract, Mapping)
        or contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
        or "forward_challenger" in value
    ):
        raise ValueError("matrix template is not an immutable report-only baseline")
    return value


def _status(report: Mapping[str, object]) -> str:
    return json.dumps(
        {
            "state": report["state"],
            "summary": report["summary"],
            "execution_authority": "none",
        },
        sort_keys=True,
    )


def run(args: argparse.Namespace) -> int:
    """Refresh until terminated, retaining the last good report on errors."""
    if args.interval_seconds <= 0.0:
        raise ValueError("forward challenger interval must be positive")
    while True:
        try:
            report = _publish(args)
        except (
            FileNotFoundError,
            OSError,
            RequestException,
            RuntimeError,
            ValueError,
        ) as exc:
            print(f"forward challenger refresh failed: {exc}", file=sys.stderr)
            if args.once:
                return 2
        else:
            print(_status(report), flush=True)
            if args.once:
                return 0
        time.sleep(args.interval_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the execution-incapable forward evidence refresher."""
    return run(_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
