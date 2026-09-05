"""Frozen dependency paths for the V58 continuous research consolidator."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.hip3_development_provenance import require_unchanged_file


_V58_GENERATOR_RELATIVE_PATHS = (
    "src/hypervector/data/jsonl_prefix.py",
    "src/hypervector/data/oxa_storage.py",
    "src/hypervector/live/cohort_entry_sizing.py",
    "src/hypervector/live/multi_asset_live_config.py",
    "src/hypervector/research/cohort_candidate_notionals.py",
    "src/hypervector/research/cohort_exact_depth_books.py",
    "src/hypervector/research/cohort_live_audit_values.py",
    "src/hypervector/research/cohort_observer_exact_books.py",
    "src/hypervector/research/market_depth_fill.py",
    "src/hypervector/research/v58_continuous_improvement.py",
    "src/hypervector/research/v58_continuous_cli.py",
    "src/hypervector/research/v58_brentoil_continuous_context.py",
    "src/hypervector/research/v58_active_route_lifecycle_context.py",
    "src/hypervector/research/v58_future_only_experiment_context.py",
    "src/hypervector/research/cohort_active_route_lifecycle_status.py",
    "src/hypervector/research/cohort_active_route_side_reconciliation.py",
    "src/hypervector/research/cohort_route_lifecycle_values.py",
    "src/hypervector/research/v58_current_investigation.py",
    "src/hypervector/research/v58_lifecycle_capture.py",
    "src/hypervector/research/v58_btc_sweep_status.py",
    "src/hypervector/research/v58_btc_sweep_lifecycle.py",
    "src/hypervector/research/v58_btc_sweep_reporting.py",
    "src/hypervector/research/v58_btc_sweep_marks.py",
    "src/hypervector/research/v58_btc_long_coverage_context.py",
    "src/hypervector/research/v58_hypothesis_ledger.py",
    "src/hypervector/research/v58_current_funding_context.py",
    "src/hypervector/research/v58_eth_censored_context.py",
    "src/hypervector/research/v58_eth_open_path_context.py",
    "src/hypervector/research/v58_eth_path_economics.py",
    "src/hypervector/research/v58_eth_source_history_context.py",
    "src/hypervector/research/v58_eth_exit_research_context.py",
    "src/hypervector/research/v58_eth_profit_lock_context.py",
    "src/hypervector/research/v58_eth_risk_normalized_lock_context.py",
    "src/hypervector/research/v58_eth_historical_disposition.py",
    "src/hypervector/research/v58_eth_risk_lock_evidence.py",
    "src/hypervector/research/v58_eth_duration_evidence.py",
    "src/hypervector/research/v58_eth_historical_funding_context.py",
    "src/hypervector/research/v58_sp500_gap_recovery_context.py",
    "src/hypervector/research/v58_sp500_recovery_ledger.py",
    "src/hypervector/research/v58_sp500_source_history_context.py",
    "src/hypervector/research/cohort_policy_forward_profit_lock.py",
    "src/hypervector/research/cohort_open_profit_lock_challenger.py",
    "src/hypervector/research/cohort_trade_reflection_index.py",
    "src/hypervector/cohort_profit_lock_policy.py",
    "src/hypervector/research/v58_continuous_liquidity_context.py",
    "src/hypervector/research/v58_route_opportunity.py",
    "src/hypervector/research/v58_observer_technical_state.py",
    "src/hypervector/research/v58_continuous_portfolio_context.py",
    "src/hypervector/research/v58_continuous_regime_context.py",
    "src/hypervector/research/v58_continuous_runtime_context.py",
    "src/hypervector/research/v58_continuous_live_attachment.py",
    "src/hypervector/research/v58_live_backend_context.py",
    "src/hypervector/research/v58_execution_mandate_context.py",
    "src/hypervector/research/cohort_mandate_evidence.py",
    "src/hypervector/research/cohort_mandate_execution_outcomes.py",
    "src/hypervector/research/v58_live_closed_lifecycles.py",
    "src/hypervector/research/v58_live_open_lifecycles.py",
    "src/hypervector/research/v58_live_profit_lock_context.py",
    "src/hypervector/research/v58_venue_state_context.py",
    "src/hypervector/research/v58_continuous_return_context.py",
    "src/hypervector/research/v58_continuous_risk_context.py",
    "src/hypervector/research/v58_opportunity_cotrigger.py",
    "src/hypervector/research/cohort_successor_observer_status.py",
    "src/hypervector/research/checkpoint_storage.py",
    "pyproject.toml",
    "uv.lock",
)


def v58_continuous_generator_paths(script_path: str) -> tuple[Path, ...]:
    """Return every source capable of changing the consolidated report."""
    roots = (Path(script_path), Path(__file__))
    return roots + tuple(Path(value) for value in _V58_GENERATOR_RELATIVE_PATHS)


def v58_continuous_generator_payload(
    references: Mapping[Path, Mapping[str, object]],
) -> list[dict[str, object]]:
    """Serialize a frozen generator identity for report publication."""
    return [{"path": str(path), **evidence} for path, evidence in references.items()]


def v58_continuous_generator_references(
    paths: tuple[Path, ...],
) -> dict[Path, dict[str, object]]:
    """Capture an immutable evidence snapshot for every generator path."""
    return {path: file_evidence(path) for path in paths}


def require_unchanged_v58_generators(
    references: Mapping[Path, Mapping[str, object]],
) -> None:
    """Reject source drift from the process-start generator identity."""
    for path, evidence in references.items():
        require_unchanged_file(path, evidence)
