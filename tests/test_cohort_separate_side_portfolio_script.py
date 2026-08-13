"""Tests for the immutable separate-side portfolio experiment command."""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_separate_side_portfolio.py"


def _load() -> ModuleType:
    """Load the command module without invoking its entry point."""
    spec = spec_from_file_location("cohort_separate_side_portfolio_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load separate-side portfolio script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_predeclared_variants_compare_asymmetric_core_to_explicit_baselines() -> None:
    """The primary hypothesis and its two comparators must remain frozen."""
    module = _load()

    variants = {row.variant_id: row for row in module.portfolio_variants()}

    assert set(variants) == {
        "separate_long_short_core",
        "sol_symmetric_sensitivity",
        "source_symmetric_baseline",
    }
    assert set(variants["separate_long_short_core"].route_sides) == {
        ("hype_breakout_onset_bidirectional_v1", "HYPE", "long"),
        (
            "eth_breakout_precompression_pullback_bidirectional_v1",
            "ETH",
            "long",
        ),
        ("range_onset_bidirectional_v1", "SOL", "short"),
    }
    assert set(variants["sol_symmetric_sensitivity"].route_sides) == {
        *variants["separate_long_short_core"].route_sides,
        ("range_onset_bidirectional_v1", "SOL", "long"),
    }
    assert len(variants["source_symmetric_baseline"].route_sides) == 6


def test_parser_defaults_to_exact_local_venue_sources() -> None:
    """The command must bind local bars, funding, and measured SOL blocks."""
    module = _load()

    args = module.build_parser().parse_args(["--out", "result.json"])

    assert args.hype_bars == Path("data/cache/HYPE_1m_365d.parquet")
    assert args.eth_bars == Path("data/cache/ETH_1m_365d.parquet")
    assert len(args.sol_artifact) == 12
    assert args.out == Path("result.json")


def test_trade_specs_match_current_fixed_cap_friction_contract() -> None:
    """Each source must retain its current cap, leverage, and entry-fee identity."""
    module = _load()

    specs = module.trade_specs()

    assert {
        key: (value.notional_usd, value.leverage, value.entry_fee_bps)
        for key, value in specs.items()
    } == {
        "HYPE": (75.0, 5.0, 4.5),
        "ETH": (25.0, 5.0, 4.5),
        "SOL": (75.0, 5.0, 4.5),
    }


def test_run_fails_before_replay_when_a_source_is_missing(tmp_path: Path) -> None:
    """A missing immutable source must fail fast without publishing output."""
    module = _load()
    output = tmp_path / "result.json"
    args = module.build_parser().parse_args(
        ["--hype-bars", str(tmp_path / "missing.parquet"), "--out", str(output)]
    )

    with pytest.raises(FileNotFoundError, match="source is missing"):
        module.run(args)

    assert not output.exists()


def test_command_summary_excludes_trade_level_payloads() -> None:
    """Console output must retain decision metrics without dumping every trade."""
    module = _load()
    metrics = {
        "completed_trades": 3,
        "wins": 2,
        "losses": 1,
        "net_pnl_usd": 1.25,
        "return_pct": 0.25,
        "profit_factor": 1.5,
        "maximum_drawdown_pct": 0.1,
        "concentration": {"net_without_largest_winner_usd": 0.75},
        "accepted": [{"sentinel_trade_payload": "must-not-leak"}],
        "rejected": [{"sentinel_rejection_payload": "must-not-leak"}],
    }
    artifact = {
        "variants": {
            "candidate": {
                "development": dict(metrics),
                "opened_final_block": dict(metrics),
            }
        }
    }

    summary = module.command_summary(artifact)
    rendered = json.dumps(summary, sort_keys=True)

    assert summary["candidate"]["development"] == {
        key: metrics[key]
        for key in (
            "completed_trades",
            "wins",
            "losses",
            "net_pnl_usd",
            "return_pct",
            "profit_factor",
            "maximum_drawdown_pct",
            "concentration",
        )
    }
    assert "must-not-leak" not in rendered
