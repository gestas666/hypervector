"""Exact execution-incapable v51 prospective index lifecycle adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from hypervector.research.hip3_shadow_lifecycle_replay import (
    build_hip3_shadow_lifecycle_replay,
)
from hypervector.research.v51_index_lifecycle_contract import (
    load_v51_index_lifecycle_contract,
)


def build_v51_index_shadow_lifecycle(
    *,
    config_path: Path,
    stress_path: Path,
    symbol: str,
    decision_rows: Sequence[Mapping[str, object]],
    book_rows: Sequence[Mapping[str, object]],
    candles_15m: pd.DataFrame,
    candles_1m: pd.DataFrame,
    mark_rows: Sequence[Mapping[str, object]],
    funding_rows: pd.DataFrame,
) -> dict[str, object]:
    """Build one source-bound authority-none v51 index replay."""
    contract = load_v51_index_lifecycle_contract(config_path, stress_path, symbol)
    report = build_hip3_shadow_lifecycle_replay(
        decision_rows=decision_rows,
        book_rows=book_rows,
        candles=candles_15m,
        mark_rows=mark_rows,
        funding_rows=funding_rows,
        config=contract.replay_config,
        profit_lock_bars=candles_1m,
    )
    report.update(
        {
            "schema_version": "v51_index_shadow_lifecycle_replay_v1",
            "runtime_profile_id": contract.profile_id,
            "runtime_profile_fingerprint": contract.profile_fingerprint,
            "sizing_contract": {
                "policy": "fixed_percent_of_equity_capped",
                "design_account_value_usd": 5_000.0,
                "margin_fraction": 0.10,
                "leverage": 10.0,
                "notional_cap_usd": 5_000.0,
                "modeled_notional_usd": contract.notional_usd,
            },
            "friction_contract": {
                "nominal_residual_bps_per_side": (
                    contract.nominal_residual_bps_per_side
                ),
                "stress_extra_bps_per_side": contract.stress_extra_bps_per_side,
                "exit_slippage_evidence_scope": (contract.exit_slippage_evidence_scope),
                "exact_depth_consumed_separately": True,
                "depth_cost_not_added_twice": True,
            },
            "contract_source_evidence": contract.source_evidence,
        }
    )
    return report
