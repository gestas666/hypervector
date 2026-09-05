"""Continuous-report attachment for V58 ETH historical funding evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.research.v58_continuous_cli import build_v58_continuous_parser
from hypervector.research.v58_continuous_generator_paths import (
    v58_continuous_generator_paths,
)
from hypervector.research.v58_eth_historical_funding_context import (
    attach_v58_eth_historical_funding_context,
)

_ROUTE = "eth_breakout_precompression_pullback_bidirectional_v1|ETH"


def test_attaches_source_bound_funding_stress_to_eth_hypothesis(
    tmp_path: Path,
) -> None:
    """Measured history must remain explicit and unable to change live authority."""
    source = tmp_path / "funding-stress.json"
    source.write_text(json.dumps(_artifact()), encoding="utf-8")
    report = _report()

    attach_v58_eth_historical_funding_context(report, source)

    context = report["eth_historical_funding_stress_context"]
    assert context["status"] == "report_only_stress_recalibration"
    assert context["long_p99_cost_bps"] == pytest.approx(3.43532332)
    assert context["p99_minus_frozen_loss_usd"] == pytest.approx(0.231415149)
    assert context["execution_authority"] == "none"
    assert context["live_change_supported"] is False
    eth = report["hypothesis_ledger"][0]
    assert eth["historical_funding_stress"] == context
    assert eth["funding_stress_assumption_state"] == "historically_understated"
    assert report["evidence"]["eth_historical_funding_stress_context"]["bytes"] > 0


def test_missing_funding_stress_is_explicitly_unavailable(tmp_path: Path) -> None:
    """A missing report must not become a zero-cost or passing observation."""
    report = _report()

    attach_v58_eth_historical_funding_context(report, tmp_path / "missing.json")

    assert report["eth_historical_funding_stress_context"] == {
        "status": "not_available",
        "reason": "historical_funding_stress_not_published",
        "execution_authority": "none",
        "live_change_supported": False,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (("execution_authority", "live"), ("live_change_supported", True)),
)
def test_rejects_funding_stress_with_live_authority(
    tmp_path: Path, field: str, value: object
) -> None:
    """Historical funding evidence cannot smuggle a live behavior change."""
    artifact = _artifact()
    artifact[field] = value
    source = tmp_path / "funding-stress.json"
    source.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(ValueError, match="authority or contract"):
        attach_v58_eth_historical_funding_context(_report(), source)


def test_rejects_inconsistent_funding_comparison(tmp_path: Path) -> None:
    """Dollar materiality must reconcile to bps and frozen route notional."""
    artifact = _artifact()
    artifact["comparisons"]["p99_minus_frozen_loss_usd"] = 99.0
    source = tmp_path / "funding-stress.json"
    source.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(ValueError, match="dollar comparison"):
        attach_v58_eth_historical_funding_context(_report(), source)


def test_continuous_contract_loads_and_hashes_historical_funding_context() -> None:
    """The active consolidator must not orphan or silently drift this evidence."""
    args = build_v58_continuous_parser("test").parse_args([])
    expected = Path(
        "data/logs/research/v58_eth_historical_funding_stress_20260820_v2.json"
    )
    assert args.eth_historical_funding_stress == expected
    paths = v58_continuous_generator_paths("scripts/v58_continuous_improvement.py")
    assert (
        Path("src/hypervector/research/v58_eth_historical_funding_context.py") in paths
    )


def _report() -> dict[str, object]:
    return {
        "hypothesis_ledger": [{"route": _ROUTE, "symbol": "ETH"}],
        "evidence": {},
    }


def _artifact() -> dict[str, object]:
    frozen = 0.349788
    p99 = 3.43532332
    return {
        "schema_version": 1,
        "mode": "v58_eth_historical_funding_stress_v1",
        "symbol": "ETH",
        "hold_hours": 12,
        "hourly_event_count": 8_760,
        "rolling_window_count": 8_749,
        "historical_distribution_claim": True,
        "sizing_input": False,
        "live_change_supported": False,
        "execution_authority": "none",
        "route_identity": {
            "strategy_id": _ROUTE.split("|", 1)[0],
            "symbol": "ETH",
            "notional_usd": 750.0,
            "hold_hours": 12,
        },
        "rolling_12h_cost_bps": {
            "long": {"p99": p99, "maximum": 7.156146},
            "short": {"p99": 2.664533, "maximum": 8.968245},
        },
        "comparisons": {
            "frozen_projection": {
                "cost_bps": frozen,
                "empirical_percentile": 0.22882615156,
                "fraction_historical_windows_above": 0.77117384844,
            },
            "current_projection": {
                "cost_bps": 1.5,
                "empirical_percentile": 0.66030403475,
                "fraction_historical_windows_above": 0.33969596525,
            },
            "p99_minus_frozen_bps": p99 - frozen,
            "p99_minus_frozen_loss_usd": (p99 - frozen) * 750.0 / 10_000.0,
        },
        "disposition": {
            "status": "report_only_stress_recalibration",
            "p99_exceeds_frozen": True,
            "proposed_live_change": None,
        },
        "source_evidence": {
            "funding": {
                "path": "/evidence/funding.parquet",
                "bytes": 1,
                "sha256": "a" * 64,
            },
            "manifest": {
                "path": "/evidence/manifest.json",
                "bytes": 1,
                "sha256": "b" * 64,
            },
            "stress": {"path": "/evidence/stress.json", "bytes": 1, "sha256": "c" * 64},
            "generator": {
                "path": "/evidence/generator.py",
                "bytes": 1,
                "sha256": "d" * 64,
            },
        },
    }
