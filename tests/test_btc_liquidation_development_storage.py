"""Tests for immutable BTC liquidation development-result storage."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd

from hypervector.research.btc_liquidation_covariate_models import (
    DepthExecution,
    EntryAssessment,
    FundingAdjustedHorizon,
    FundingCashflow,
    HorizonReplay,
    ReplayEpisode,
)
from hypervector.research.btc_liquidation_development_materializer import (
    DevelopmentEpisodeReplay,
)
from hypervector.research.btc_liquidation_development_storage import (
    build_development_materialization_report,
    episode_arm_records,
    publish_development_materialization,
)


def _result() -> DevelopmentEpisodeReplay:
    episode = ReplayEpisode(
        "episode-a",
        "development",
        "continuation_long",
        1_000,
        Decimal("100"),
        ("5s_p95", "5s_p99"),
    )
    fill = DepthExecution(
        Decimal("50"),
        Decimal("50"),
        Decimal("5050"),
        Decimal("101"),
        Decimal("101"),
        Decimal("101"),
        Decimal("0"),
        1,
        True,
    )
    entry = EntryAssessment(
        episode,
        "eligible",
        (),
        11_000,
        Decimal("0.25"),
        11_001,
        Decimal("100"),
        fill,
    )
    replay = HorizonReplay(
        300_000,
        311_001,
        "resolved",
        None,
        311_002,
        fill,
        Decimal("50"),
        Decimal("4.5"),
        Decimal("45.5"),
        Decimal("40.0"),
    )
    funding = FundingCashflow(
        11_001,
        311_002,
        Decimal("5000"),
        1,
        Decimal("0.0001"),
        Decimal("-0.5"),
    )
    adjusted = FundingAdjustedHorizon(
        replay,
        funding,
        Decimal("45.0"),
        Decimal("39.5"),
    )
    regime = {
        "bar_open_at": pd.Timestamp("1970-01-01T00:00:00Z"),
        "available_at": pd.Timestamp("1970-01-01T00:05:00Z"),
        "primary_regime": "TREND_UP",
        "regime_strength_score": 0.75,
    }
    return DevelopmentEpisodeReplay(entry, (adjusted,), regime)


def test_episode_storage_preserves_exact_decimal_strings_for_each_arm() -> None:
    """One causal episode is emitted once for every frozen eligible arm."""
    records = episode_arm_records(_result())

    assert [row["arm"] for row in records] == ["5s_p95", "5s_p99"]
    assert records[0]["entry"]["flow_imbalance"] == "0.25"
    assert records[0]["outcomes"][0]["nominal_net_pnl_usd"] == "45.0"
    assert records[0]["outcomes"][0]["funding_cashflow_usd"] == "-0.5"


def test_development_publication_is_immutable_and_execution_incapable(
    tmp_path: Path,
) -> None:
    """The raw economic artifact is report-only and cannot overwrite evidence."""
    records = episode_arm_records(_result())
    report = build_development_materialization_report(
        records,
        episode_count=1,
        window_count=1,
        evidence={"journal": {"sha256": "a" * 64}},
    )
    output = tmp_path / "development"

    publish_development_materialization(output, records, report)

    stored = json.loads((output / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert stored["contract"]["execution_authority"] == "none"
    assert stored["contract"]["validation_outcomes_opened"] is False
    assert stored["summary"]["episode_count"] == 1
    assert set(manifest["files"]) == {"report.json", "results.jsonl.gz"}

    try:
        publish_development_materialization(output, records, report)
    except FileExistsError:
        pass
    else:
        raise AssertionError("immutable development output was overwritten")
