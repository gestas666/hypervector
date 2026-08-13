"""Contract tests for the compact v29 live-boundary projector."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace

import pytest


SCRIPT = Path("scripts/evidence_selected_portfolio_v29_live_boundary.py")
CONFIG = Path(
    "configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml"
)
PRIOR = Path("data/logs/research/v25_live_monitor_20260808T064253Z.json")
ROUTES = (
    ("range_onset_bidirectional_v1", "ETH"),
    ("range_onset_bidirectional_v1", "SOL"),
    ("eth_breakout_precompression_pullback_bidirectional_v1", "ETH"),
    ("hip3_swing_ha_sp500_spcx_bidirectional_v2", "xyz:SPCX"),
    ("hip3_breakout_pressure_sp500_spcx_bidirectional_v1", "xyz:SP500"),
    ("hip3_swing_ha_sndk_gold_brent_bidirectional_v1", "xyz:GOLD"),
)


def _load(name: str) -> ModuleType:
    """Load the versioned command without invoking its entry point."""
    spec = spec_from_file_location(name, SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load script: {SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _route(strategy: str, symbol: str) -> str:
    """Return one exact provider-symbol identity."""
    return f"{strategy}|{symbol}"


def _contract() -> SimpleNamespace:
    """Return the exact candidate fields consumed by the projector."""
    return SimpleNamespace(
        profile_id="multi_asset_bidirectional_evidence_selected_portfolio_canary_v29",
        profile_fingerprint="d1f4cd3b03197e9e7a9899ab32e2b198fd4bd2a4117f1ea64261824fcdc4a393",
        execution_scope=ROUTES,
    )


def _audit() -> dict[str, object]:
    """Return a minimal canonical live-audit fixture with selected-route evidence."""
    scorecards = {
        _route(strategy, symbol): {
            "eligible_signals": int(symbol in {"ETH", "xyz:SPCX", "xyz:GOLD"}),
            "resolved_signal_horizons": 4
            if symbol in {"ETH", "xyz:SPCX", "xyz:GOLD"}
            else 0,
            "forward_assessment": "descriptive_mixed_paths",
            "research_state": "prospective_candidate",
            "eligible_signal_horizons": {},
        }
        for strategy, symbol in ROUTES
    }
    spcx = _route(ROUTES[3][0], ROUTES[3][1])
    return {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_audit",
        "experiment_contract": {
            "execution_authority": "none",
            "report_only": True,
            "runtime_strategy_changed": False,
        },
        "coverage": {"complete": True, "technical_gaps": []},
        "run": {
            "run_id": "bidirectional-live-fixture",
            "profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
            "profile_fingerprint": "e" * 64,
            "last_observed_at_utc": "2026-08-08T08:23:03+00:00",
        },
        "health": {"faults": 0, "assets": {}},
        "execution": {
            "closed_trades": 2,
            "wins": 1,
            "losses": 1,
            "net_pnl_usd": 0.024252,
            "profit_factor": 1.0369,
            "fees_usd": 0.055802,
            "funding_usd": -0.003146,
            "slippage_bps": {"mean": 0.867},
            "acknowledgement_latency_ms": {"mean": 993.875},
            "markout_bps": {"mean": -0.3735},
        },
        "strategy_scorecard": {"by_provider_symbol": scorecards},
        "trade_reflections": {
            "performance": {
                "current_run": {
                    "by_provider_symbol": {
                        spcx: {
                            "closed_trades": 1,
                            "wins": 0,
                            "losses": 1,
                            "net_pnl_usd": -0.656872,
                            "profit_factor": 0.0,
                            "fees_usd": 0.012872,
                            "funding_usd": 0.0,
                            "by_side": {"long": {"closed_trades": 1}},
                        }
                    }
                }
            }
        },
        "open_trade_reflections": {
            "trades": [
                {
                    "strategy_id": ROUTES[2][0],
                    "symbol": ROUTES[2][1],
                    "side": "long",
                    "holding_time_ms": 1_000,
                    "marked_economics": {
                        "active_lifecycle_marked_net_pnl_usd": -0.05,
                        "fees_usd": 0.01,
                        "funding_usd": -0.001,
                        "liquidation_distance_pct": 18.0,
                    },
                    "protective_stop": {"oid": 123, "trigger_price": 1_900.0},
                },
                {
                    "strategy_id": "hype_breakout_onset_bidirectional_v1",
                    "symbol": "SOL",
                    "side": "long",
                    "marked_economics": {"active_lifecycle_marked_net_pnl_usd": 0.20},
                    "protective_stop": {"oid": 456, "trigger_price": 73.0},
                },
            ]
        },
    }


def _prior_boundary() -> dict[str, object]:
    """Return the previously journaled route counts with different open marks."""
    return {
        "execution_authority": "none",
        "report_only": True,
        "v29_route_observations": [
            {
                "route": _route(strategy, symbol),
                "eligible_signals": int(symbol in {"ETH", "xyz:SPCX", "xyz:GOLD"}),
                "resolved_signal_horizons": 4
                if symbol in {"ETH", "xyz:SPCX", "xyz:GOLD"}
                else 0,
                "resolved_execution_outcomes": int(symbol == "xyz:SPCX"),
            }
            for strategy, symbol in ROUTES
        ],
    }


def test_versioned_live_boundary_command_exists() -> None:
    """The repeatable report-only projector must be checked into the workspace."""
    assert SCRIPT.is_file()


def test_parser_requires_audit_and_output_while_binding_v29_inputs() -> None:
    """The command must bind the candidate and prior immutable live boundary."""
    module = _load("v29_live_boundary_parser")

    args = module.build_parser().parse_args(
        ["--audit", "audit.json", "--out", "out.json"]
    )

    assert args.audit == Path("audit.json")
    assert args.out == Path("out.json")
    assert args.config == CONFIG
    assert args.prior_boundary == PRIOR


def test_artifact_is_report_only_and_ignores_provisional_mark_changes() -> None:
    """Unchanged resolved counts must not create journal churn from open marks."""
    module = _load("v29_live_boundary_artifact")

    artifact = module.build_live_boundary(
        _audit(),
        _prior_boundary(),
        contract=_contract(),
        audit_evidence={"sha256": "a" * 64, "bytes": 100},
        prior_evidence={"sha256": "b" * 64, "bytes": 50},
        config_evidence={"sha256": "c" * 64, "bytes": 25},
    )

    assert (
        artifact["schema_version"] == "evidence_selected_portfolio_v29_live_boundary_v1"
    )
    assert artifact["execution_authority"] == "none"
    assert artifact["report_only"] is True
    assert artifact["runtime_strategy_changed"] is False
    assert artifact["candidate"]["active"] is False
    assert artifact["source_audit"]["sha256"] == "a" * 64
    assert artifact["current_run"]["closed_trades"] == 2
    assert len(artifact["v29_route_observations"]) == 6
    spcx = next(
        row for row in artifact["v29_route_observations"] if row["symbol"] == "xyz:SPCX"
    )
    assert spcx["resolved_execution_outcomes"] == 1
    assert spcx["execution_net_pnl_usd"] == -0.656872
    eth = next(
        row
        for row in artifact["v29_route_observations"]
        if row["strategy_id"] == ROUTES[2][0]
    )
    assert eth["open_lifecycles"] == 1
    assert eth["open_marked_net_pnl_usd"] == -0.05
    flat = next(
        row for row in artifact["v29_route_observations"] if row["symbol"] == "SOL"
    )
    assert flat["all_open_positions_protected"] is None
    assert artifact["delta"]["material"] is False
    assert (
        artifact["assessment"]["decision"] == "retain_v29_without_new_journal_revision"
    )


def test_run_publishes_immutable_material_delta_from_real_candidate_config(
    tmp_path: Path,
) -> None:
    """A changed resolved counter must publish a reviewable, non-executable delta."""
    module = _load("v29_live_boundary_run")
    audit_path = tmp_path / "audit.json"
    prior_path = tmp_path / "prior.json"
    out_path = tmp_path / "boundary.json"
    prior = _prior_boundary()
    rows = prior["v29_route_observations"]
    assert isinstance(rows, list)
    rows[0]["eligible_signals"] = 0
    audit_path.write_text(json.dumps(_audit()), encoding="utf-8")
    prior_path.write_text(json.dumps(prior), encoding="utf-8")
    args = module.build_parser().parse_args(
        [
            "--audit",
            str(audit_path),
            "--prior-boundary",
            str(prior_path),
            "--out",
            str(out_path),
        ]
    )

    artifact = module.run(args)

    assert out_path.is_file()
    assert json.loads(out_path.read_text(encoding="utf-8")) == artifact
    assert artifact["delta"]["material"] is True
    assert artifact["delta"]["changes"] == [
        {
            "route": "range_onset_bidirectional_v1|ETH",
            "field": "eligible_signals",
            "before": 0,
            "after": 1,
        }
    ]
    assert artifact["assessment"]["decision"].startswith("review_material_evidence")


def test_missing_selected_route_scorecard_fails_with_exact_identity() -> None:
    """Incomplete candidate coverage must not become a zero-evidence route."""
    module = _load("v29_live_boundary_missing_route")
    audit = _audit()
    scorecards = audit["strategy_scorecard"]["by_provider_symbol"]
    missing = _route(ROUTES[-1][0], ROUTES[-1][1])
    del scorecards[missing]

    message = re.escape(f"missing selected v29 route scorecard: {missing}")
    with pytest.raises(ValueError, match=message):
        module.build_live_boundary(
            audit,
            _prior_boundary(),
            contract=_contract(),
            audit_evidence={"sha256": "a" * 64, "bytes": 100},
            prior_evidence={"sha256": "b" * 64, "bytes": 50},
            config_evidence={"sha256": "c" * 64, "bytes": 25},
        )


def test_prior_boundary_with_execution_authority_is_refused() -> None:
    """A comparison source must not carry strategy or order authority."""
    module = _load("v29_live_boundary_prior_authority")
    prior = _prior_boundary()
    prior["execution_authority"] = "live"

    with pytest.raises(
        ValueError, match="prior boundary must have no execution authority"
    ):
        module.build_live_boundary(
            _audit(),
            prior,
            contract=_contract(),
            audit_evidence={"sha256": "a" * 64, "bytes": 100},
            prior_evidence={"sha256": "b" * 64, "bytes": 50},
            config_evidence={"sha256": "c" * 64, "bytes": 25},
        )


def test_main_prints_compact_report_only_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The executable command must publish once and print no oversized audit body."""
    module = _load("v29_live_boundary_main")
    audit_path = tmp_path / "audit.json"
    prior_path = tmp_path / "prior.json"
    out_path = tmp_path / "out.json"
    audit_path.write_text(json.dumps(_audit()), encoding="utf-8")
    prior_path.write_text(json.dumps(_prior_boundary()), encoding="utf-8")

    exit_code = module.main(
        [
            "--audit",
            str(audit_path),
            "--prior-boundary",
            str(prior_path),
            "--out",
            str(out_path),
        ]
    )

    printed = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert printed == {
        "execution_authority": "none",
        "material_delta": False,
        "out": str(out_path),
        "report_only": True,
        "resolved_selected_route_lifecycles": 1,
    }
