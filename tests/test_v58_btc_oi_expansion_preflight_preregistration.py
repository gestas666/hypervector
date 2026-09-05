from __future__ import annotations

import json
from pathlib import Path


_PATH = Path(
    "docs/research-journal/"
    "v58-btc-oi-expansion-flow-continuation-preflight-"
    "preregistration-20260821-v1.json"
)
_HYPOTHESIS = "V58_BTC_OI_EXPANSION_FLOW_CONTINUATION_LONG_PREFLIGHT_V1"


def test_preregistration_freezes_report_only_count_stage() -> None:
    """Freeze a count-only stage with no outcome or execution authority."""
    payload = json.loads(_PATH.read_text(encoding="utf-8"))

    assert payload["hypothesis_id"] == _HYPOTHESIS
    assert payload["status"] == "preregistered_before_preflight_counts"
    assert payload["authority"] == {
        "report_only": True,
        "execution_authority": "none",
        "outcomes_computed": False,
        "automatic_promotion": False,
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "orders_supported": False,
    }
    assert payload["stage_boundary"]["forbidden_fields"] == [
        "forward_quotes",
        "forward_prices",
        "returns",
        "fees",
        "funding",
        "pnl",
        "orders",
    ]


def test_preregistration_freezes_signal_and_selection_rule() -> None:
    """Prevent outcome-driven changes to clocks, thresholds, and cadence."""
    payload = json.loads(_PATH.read_text(encoding="utf-8"))
    signal = payload["frozen_signal_contract"]

    assert signal["symbols"] == ["BTC"]
    assert signal["sides"] == ["long"]
    assert signal["decision_timeframe"] == "completed_5m"
    assert signal["causal_clock"] == "received_ts_ns"
    assert signal["candidate_quantiles"] == [0.75, 0.8, 0.9]
    assert signal["minimum_positive_shock_bps"] == 13.0
    assert signal["minimum_oi_expansion_pct"] == 0.0005
    assert signal["terminal_trade_imbalance"] == "strictly_positive"
    assert signal["terminal_top10_book_imbalance"] == "strictly_positive"
    assert signal["non_overlap_minutes"] == 60
    selection = payload["cadence_selection_contract"]
    assert selection["selection_partition"] == "development"
    assert selection["minimum_development_candidate_onsets"] == 20
    assert selection["rule"] == (
        "select the strictest candidate quantile with at least the minimum "
        "development candidate onsets"
    )
    assert selection["no_qualifier_disposition"] == "data_insufficient"


def test_preregistration_freezes_partitions_and_research_search_count() -> None:
    """Bind chronological windows, OOS cadence gates, and search accounting."""
    payload = json.loads(_PATH.read_text(encoding="utf-8"))

    assert payload["warmup_start_utc"] == "2026-07-26T23:41:00Z"
    assert [row["name"] for row in payload["frozen_partitions"]] == [
        "development",
        "validation",
        "pseudo_holdout",
    ]
    assert (
        payload["cadence_selection_contract"][
            "minimum_candidate_onsets_per_oos_partition"
        ]
        == 10
    )
    assert payload["prior_search_accounting"]["count_only_quantile_trials"] == 3
    assert payload["prior_search_accounting"]["outcome_trials_in_this_stage"] == 0
    assert payload["outcome_stage_authorization"] == (
        "requires a new preregistration after cadence qualification"
    )
