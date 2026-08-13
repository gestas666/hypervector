"""Command coverage for immutable provider-family concentration evidence."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_family_concentration.py"
ALLOCATION = Path(
    "data/logs/research/bidirectional_cohort/"
    "v40_p99_risk_normalized_exact_reprice_20260811T0226Z_v1.json"
)
CONFIG = Path(
    "configs/"
    "multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41.toml"
)


def test_exact_v41_topology_is_source_bound_and_report_only() -> None:
    """The command must reconcile the exact v41 roster and provider graph."""
    spec = spec_from_file_location("cohort_family_concentration_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    report = module.run_report(
        argparse.Namespace(
            allocation=ALLOCATION,
            config=CONFIG,
            target_equity_usd=5_000.0,
            out=Path("unused.json"),
        )
    )

    assert report["candidate_profile"]["profile_id"].endswith("candidate_v41")
    assert report["candidate_profile"]["profile_fingerprint"]
    assert report["evidence"]["allocation"]["sha256"]
    assert report["evidence"]["config"]["sha256"]
    assert report["portfolio"]["connected_cluster_count"] == 3
    assert report["portfolio"]["p99_stop_wave_loss_usd"] == pytest.approx(
        58.0238627910263
    )
    assert [row["symbols"] for row in report["clusters"]] == [
        ["BTC", "ETH", "HYPE", "SOL"],
        ["xyz:BRENTOIL", "xyz:SNDK"],
        ["xyz:SP500", "xyz:SPCX"],
    ]
    assert report["contract"]["execution_authority"] == "none"
