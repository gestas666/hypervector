from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest
from cohort_live_audit_trade_fixture import traded_asset_rows

from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from hypervector.research.cohort_live_audit_execution import _merge_fill

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_HULK = "test_trend_5m"
_RANGE = "test_breakout_1m"
_RUN_ID = "cohort-live-a"
_SCRIPT = Path("src/hypervector/operations/multi_asset_bidirectional_live_audit.py")


def test_exact_fill_placeholders_do_not_erase_projected_attribution() -> None:
    """Sentinel asset values must not overwrite known lifecycle attribution."""
    projected = {
        "symbol": "BTC",
        "trade_id": 202,
        "strategy_id": "test_short_drift_5m",
        "operation": "protective_stop",
        "exit_controller_id": "cohort_protective_stop",
        "price": 103.98,
    }
    exact_fill = {
        "symbol": "BTC",
        "trade_id": 202,
        "strategy_id": "unattributed",
        "operation": "unknown",
        "exit_controller_id": "unattributed",
        "price": 103.98,
        "fee_usd": 0.01,
    }

    merged = _merge_fill(projected, {("BTC", 202): exact_fill})

    assert merged["strategy_id"] == "test_short_drift_5m"
    assert merged["operation"] == "protective_stop"
    assert merged["exit_controller_id"] == "cohort_protective_stop"
    assert merged["fee_usd"] == pytest.approx(0.01)


def test_flat_run_preserves_readiness_health_and_zero_trade_evidence() -> None:
    """A quiet live run is auditable without inventing strategy performance."""
    report = audit_multi_asset_live_run(
        _cohort_rows(),
        {symbol: _asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
    )

    assert report["experiment_contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "performance_gate": False,
        "balance_gate": False,
    }
    assert report["run"]["run_id"] == _RUN_ID
    assert report["run"]["symbols"] == list(_SYMBOLS)
    assert report["run"]["maximum_concurrent_positions"] == 4
    assert report["run"]["prestart_backup"] is None
    assert report["run"]["executable_provider_symbols"] == [
        f"{_HULK}|BTC",
        f"{_RANGE}|SOL",
    ]
    assert len(report["run"]["observe_only_provider_symbols"]) == 6
    assert report["runtime"]["poll_cycles"] == 2
    assert report["runtime"]["stop_reasons"] == {"operator_stop": 4}
    assert report["portfolio"]["initial_equity_usd"] == 503.16
    assert report["portfolio"]["final_equity_usd"] == 503.16
    assert report["portfolio"]["maximum_drawdown_pct"] == 0.0
    assert report["portfolio"]["maximum_open_positions"] == 0
    assert report["routing"]["actions"] == 0
    assert report["routing"]["withheld"] == 0
    assert report["regime_conflict_journal"]["state"] == "not_active"
    assert report["readiness"]["evaluations"] == 16
    assert len(report["readiness"]["by_provider_symbol"]) == 8
    hulk_btc = report["readiness"]["by_provider_symbol"][f"{_HULK}|BTC"]
    assert hulk_btc["latest_fraction"] == 0.5
    assert hulk_btc["maximum_fraction"] == 0.5
    assert hulk_btc["blockers"] == {"squeeze_not_armed": 2}
    assert hulk_btc["latest_reason"] == "no_trigger"
    assert hulk_btc["latest_blockers"] == ["squeeze_not_armed"]
    scorecard = report["strategy_scorecard"]
    assert scorecard["contract"] == {
        "report_only": True,
        "performance_gate": False,
        "balance_gate": False,
        "trade_count_gate": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "execution_authority": "none",
    }
    assert scorecard["summary"] == {
        "mappings": 8,
        "mappings_with_live_outcomes": 0,
        "no_eligible_signal_evidence": 8,
    }
    assert set(scorecard["by_provider_symbol"]) == {
        f"{provider}|{symbol}" for provider in (_HULK, _RANGE) for symbol in _SYMBOLS
    }
    assert all(
        row["execution_effect"] == "report_only"
        and row["strategy_edge_identifiable"] is False
        and row["execution_outcomes_identifiable"] is False
        for row in scorecard["by_provider_symbol"].values()
    )
    assert report["execution"]["fills"] == 0
    assert report["execution"]["closed_trades"] == 0
    assert report["execution"]["net_pnl_usd"] == 0.0
    assert report["execution"]["slippage_bps"]["status"] == "not_applicable_no_fills"
    ignored_exits = report["ignored_provider_exit_policy_scorecard"]
    assert ignored_exits["contract"]["execution_authority"] == "none"
    assert ignored_exits["resolved"]["total_lifecycles"] == 0
    assert ignored_exits["provisional_open"]["total_lifecycles"] == 0
    episode_reentry = report["provider_episode_reentry"]
    assert episode_reentry["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
        "execution_gate": False,
        "portfolio_pnl_claimed": False,
    }
    assert episode_reentry["evaluation_coverage"]["matching_rows"] == 0
    assert episode_reentry["resolved"]["matching_trades"] == 0
    assert episode_reentry["provisional_open"]["matching_positions"] == 0
    extension = report["maximum_hold_decisions"]["extension_outcomes"]
    assert extension["contract"]["balance_gate"] is False
    assert extension["summary"]["bound_extension_lifecycles"] == 0
    profit_lock = report["profit_lock_challenger"]
    assert profit_lock["contract"]["execution_authority"] == "none"
    assert profit_lock["contract"]["automatic_promotion"] is False
    assert profit_lock["summary_by_policy"]["a25_floor15_trail10"] == {
        "lifecycles": 0,
        "eligible_lifecycles": 0,
        "withheld_lifecycles": 0,
        "triggered": 0,
        "wins": 0,
        "losses": 0,
        "estimated_net_pnl_usd": 0,
        "actual_net_pnl_usd": 0,
        "estimated_minus_actual_net_usd": 0,
        "profit_factor": None,
    }
    support_decay = profit_lock.get("support_decay_all_time_live_mechanism")
    assert isinstance(support_decay, dict)
    assert support_decay["contract"]["execution_authority"] == "none"
    assert support_decay["contract"]["automatic_promotion"] is False
    assert support_decay["latest_results"] == []
    assert report["execution"]["friction_parity"]["summary"] == {
        "provider_symbols": 8,
        "runtime_shape_aligned": 0,
        "contract_mismatch": 0,
        "unsupported_contract": 8,
        "runtime_contract_missing": 0,
        "provider_symbols_with_entry_fills": 0,
    }
    assert report["health"]["faults"] == 0
    assert all(
        asset["final_state"] == "STOPPED"
        for asset in report["health"]["assets"].values()
    )
    assert report["coverage"] == {"complete": True, "technical_gaps": []}
    assert report["learning"]["strategy_edge_identifiable"] is False
    assert report["learning"]["evidence_state"] == "no_closed_trade_evidence"


def test_audit_preserves_prestart_backup_provenance() -> None:
    """Stopped-run evidence retains the verified source/data recovery identity."""
    rows = _cohort_rows()
    bundle = "data/backups/bidirectional_cohort/prestart_test"
    rows[0]["payload"]["prestart_backup"] = {
        "status": "verified",
        "bundle_path": bundle,
        "manifest_path": f"{bundle}/manifest.json",
        "manifest_sha256": "a" * 64,
        "strategy_changed": True,
        "implementation_file_count": 1_156,
        "implementation_sha256": "b" * 64,
    }

    report = audit_multi_asset_live_run(
        rows,
        {symbol: _asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
    )

    assert report["run"]["prestart_backup"] == rows[0]["payload"]["prestart_backup"]


def test_audit_publishes_regime_conflict_counterfactual_evidence() -> None:
    """The rolling audit compares active regime routing with static priority."""
    rows = _cohort_rows()
    identity = rows[0]["payload"]
    identity["routing_policy"] = {
        "mode": "same_symbol_conflict_preference_v1",
        "alignment_basis": "canonical_1m_5m_15m_1_3_2_v1",
        "standalone_intents_ungated": True,
        "forced_regime_exit": False,
        "fallback": "provider_priority_then_decision_time",
    }
    identity["providers"][0]["priority"] = 10
    identity["providers"][1]["priority"] = 20
    routing = next(row for row in rows if row["event_type"] == "intent_routing")
    routing["payload"]["actions"] = [_regime_intent(_HULK, "long", 1.0)]
    routing["payload"]["withheld"] = [
        {
            **_regime_intent(_RANGE, "short", -1.0),
            "reason": "lower_regime_alignment",
        }
    ]

    report = audit_multi_asset_live_run(
        rows,
        {symbol: _asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
    )

    journal = report["regime_conflict_journal"]
    assert journal["state"] == "active"
    assert journal["conflicts"] == 1
    assert journal["conflicts_changing_static_choice"] == 1
    assert journal["directionally_comparable_conflicts"] == 1
    assert journal["horizons"]["5"]["resolved"] == 1
    assert journal["horizons"]["5"]["ties"] == 1


def test_missing_provider_readiness_is_an_explicit_coverage_gap() -> None:
    """A legacy run cannot look complete when setup diagnostics were absent."""
    rows = _cohort_rows()
    for row in rows:
        if row.get("event_type") != "intent_routing":
            continue
        payload = row.get("payload")
        assert isinstance(payload, dict)
        payload.pop("evaluations")

    report = audit_multi_asset_live_run(
        rows,
        {symbol: _asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
    )

    assert report["readiness"]["evaluations"] == 0
    assert report["coverage"] == {
        "complete": False,
        "technical_gaps": ["provider_readiness_missing"],
    }


def test_audit_rejects_action_outside_explicit_execution_scope() -> None:
    """Observed challengers cannot masquerade as authorized live actions."""
    rows = _cohort_rows()
    routing = next(row for row in rows if row["event_type"] == "intent_routing")
    routing["payload"]["actions"] = [
        {
            "strategy_id": _HULK,
            "symbol": "ETH",
            "side": "long",
        }
    ]

    with pytest.raises(ValueError, match="execution scope"):
        audit_multi_asset_live_run(
            rows,
            {symbol: _asset_rows(symbol) for symbol in _SYMBOLS},
            run_id=_RUN_ID,
        )


def test_audit_accepts_backend_maximum_hold_as_a_lifecycle_close() -> None:
    """A runner-owned timed close is not an undeclared entry provider."""
    rows = _cohort_rows()
    routing = next(row for row in rows if row["event_type"] == "intent_routing")
    routing["payload"]["actions"] = [
        {
            "action": "close",
            "strategy_id": "cohort_maximum_hold",
            "symbol": "BTC",
            "side": "long",
        }
    ]

    report = audit_multi_asset_live_run(
        rows,
        {symbol: _asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
    )

    assert report["routing"]["actions"] == 1
    assert report["routing"]["lifecycle_actions"] == 1


def test_closed_trade_is_attributed_by_provider_side_and_realized_friction() -> None:
    """The learning loop retains who traded, direction, costs, and net outcome."""
    report = audit_multi_asset_live_run(
        _cohort_rows_with_trade(),
        {
            "BTC": traded_asset_rows(_RUN_ID),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    assert report["execution"]["fills"] == 2
    assert report["execution"]["projected_fills"] == 2
    details = report["execution"]["fill_details"]
    assert [fill["trade_id"] for fill in details] == [101, 202]
    assert details[1]["strategy_id"] == _HULK
    assert details[1]["exit_controller_id"] == _HULK
    assert details[1]["expected_price"] == pytest.approx(104.0)
    assert details[1]["slippage_bps"] == pytest.approx(1.9230769)
    assert details[1]["acknowledgement_latency_ms"] == 1_000
    assert details[1]["exit_reason"] == "opposite_strategy_intent"
    assert report["execution"]["closed_trades"] == 1
    assert report["execution"]["net_pnl_usd"] == 0.97
    assert report["execution"]["fees_usd"] == 0.02
    assert report["execution"]["funding_usd"] == -0.01
    provider = report["execution"]["by_strategy_side"][f"{_HULK}|long"]
    assert provider == {
        "closed_trades": 1,
        "wins": 1,
        "losses": 0,
        "net_pnl_usd": 0.97,
        "fees_usd": 0.02,
        "funding_usd": -0.01,
        "profit_factor": None,
    }
    assert report["execution"]["slippage_bps"]["status"] == "observed"
    assert report["execution"]["acknowledgement_latency_ms"]["mean"] == 1_000.0
    assert report["execution"]["markout_bps"]["mean"] == 2.0
    assert report["execution"]["fee_rate_bps"] == {
        "status": "observed",
        "count": 2,
        "minimum": pytest.approx(0.01 / (103.98 * 0.25) * 10_000.0),
        "median": pytest.approx(
            (0.01 / (100.01 * 0.25) * 10_000.0 + 0.01 / (103.98 * 0.25) * 10_000.0)
            / 2.0
        ),
        "maximum": pytest.approx(0.01 / (100.01 * 0.25) * 10_000.0),
        "mean": pytest.approx(
            (0.01 / (100.01 * 0.25) * 10_000.0 + 0.01 / (103.98 * 0.25) * 10_000.0)
            / 2.0
        ),
    }
    assert report["execution"]["friction_parity"]["contract"]["report_only"] is True
    contract_history = report["trade_reflections"]["provider_contract_history"]
    assert contract_history["scope"] == "provider_execution_contract_history"
    assert contract_history["compatible_trades"] == 1
    assert contract_history["incompatible_trades"] == 0
    profit_lock = report["profit_lock_challenger"]
    assert profit_lock["current_run"]["run_id"] == _RUN_ID
    assert (
        profit_lock["current_run"]["summary_by_policy"]["a25_floor15_trail10"][
            "eligible_lifecycles"
        ]
        == 1
    )
    all_time_mechanism = profit_lock.get("all_time_live_mechanism")
    assert isinstance(all_time_mechanism, dict)
    assert all_time_mechanism["scope"] == "all_live_history_normalized_mechanism"
    assert all_time_mechanism["contract"]["portfolio_pnl_claimed"] is False
    assert (
        all_time_mechanism["summary_by_policy"]["a25_floor15_trail10"][
            "eligible_lifecycles"
        ]
        == 1
    )
    risk_normalized = profit_lock.get("risk_normalized_all_time_live_mechanism")
    assert isinstance(risk_normalized, dict)
    assert risk_normalized["contract"]["execution_authority"] == "none"
    assert risk_normalized["risk_multiple_contract"] == {
        "activation_r": 2.0,
        "floor_r": 1.0,
        "peak_giveback_r": 1.0,
    }
    risk_summary = risk_normalized["summary_by_policy"]["r2_floor1_trail1"]
    assert risk_summary["eligible_lifecycles"] == 0
    assert risk_summary["withheld_lifecycles"] == 1
    conditioned = profit_lock.get("regime_conditioned_all_time_live_mechanism")
    assert isinstance(conditioned, dict)
    assert conditioned["contract"]["execution_authority"] == "none"
    assert conditioned["activation_contract"] == {
        "source": "causal_regime_opposition_persistence_v1",
        "persistence_decisions": 5,
        "decision_interval_ms": 60_000,
        "opposition_threshold": -0.5,
        "pre_gate_favorable_excursion_retained": True,
        "same_bar_activation_and_trigger_allowed": False,
    }
    assert (
        conditioned["summary_by_policy"]["a25_floor15_trail10"]["eligible_lifecycles"]
        == 1
    )
    support_decay = profit_lock.get("support_decay_all_time_live_mechanism")
    assert isinstance(support_decay, dict)
    assert support_decay["contract"]["execution_authority"] == "none"
    assert support_decay["contract"]["automatic_promotion"] is False
    assert support_decay["activation_contract"]["source"] == (
        "causal_regime_support_decay_persistence_v1"
    )
    support_summary = support_decay["summary_by_policy"]["a25_floor15_trail10"]
    assert support_summary["eligible_lifecycles"] == 0
    assert support_summary["withheld_lifecycles"] == 1
    entry_alignment = report["entry_alignment_mechanism"]
    assert entry_alignment["contract"]["execution_authority"] == "none"
    assert entry_alignment["closed_trades"] == 1
    alignment_pair = entry_alignment["by_provider_symbol"][f"{_HULK}|BTC"]
    assert alignment_pair["closed_trades"] == 1
    assert alignment_pair["component_stance"]["coverage"] == {
        "attributable": 0,
        "unavailable": 1,
    }
    assert entry_alignment["provider_symbol_sides"] == 1
    alignment_side = entry_alignment["by_provider_symbol_side"][f"{_HULK}|BTC|long"]
    assert alignment_side["side"] == "long"
    assert alignment_side["outcome"]["trades"] == 1
    assert alignment_side["outcome"]["net_pnl_usd"] == pytest.approx(0.97)
    live_score = report["strategy_scorecard"]["by_provider_symbol"][f"{_HULK}|BTC"]
    assert live_score["execution_outcomes_identifiable"] is True
    assert (
        live_score["execution_performance_scope"]
        == "provider_execution_contract_history"
    )
    assert live_score["execution_performance"]["closed_trades"] == 1
    assert live_score["execution_performance"]["net_pnl_usd"] == pytest.approx(0.97)
    assert live_score["execution_performance_by_side"]["long"]["closed_trades"] == 1
    assert live_score["execution_performance_by_side"]["long"][
        "net_pnl_usd"
    ] == pytest.approx(0.97)
    assert report["strategy_scorecard"]["summary"]["mappings_with_live_outcomes"] == 1
    assert report["learning"]["evidence_state"] == "descriptive_trade_evidence"
    assert report["learning"]["strategy_edge_identifiable"] is False


def test_audit_rejects_conflicting_backend_and_asset_fill_identity() -> None:
    """Exact attribution cannot silently rewrite contradictory venue facts."""
    rows = _cohort_rows_with_trade()
    snapshots = [row for row in rows if row["event_type"] == "cohort_snapshot"]
    snapshots[-1]["payload"]["recent_fills"][1]["price"] = 999.0

    with pytest.raises(ValueError, match="fill identity conflicts"):
        audit_multi_asset_live_run(
            rows,
            {
                "BTC": traded_asset_rows(_RUN_ID),
                **{
                    symbol: _asset_rows(symbol)
                    for symbol in _SYMBOLS
                    if symbol != "BTC"
                },
            },
            run_id=_RUN_ID,
        )


def test_current_run_audit_excludes_known_prior_run_projected_fill() -> None:
    """Rolling backend fills must respect the selected asset-ledger run scope."""
    rows = _cohort_rows_with_trade()
    snapshots = [row for row in rows if row["event_type"] == "cohort_snapshot"]
    for snapshot in snapshots:
        recent_fills = snapshot["payload"]["recent_fills"]
        for fill in recent_fills:
            fill["origin_run_id"] = _RUN_ID
        recent_fills.insert(
            0,
            {
                "symbol": "BTC",
                "trade_id": 99,
                "price": 99.0,
                "size": 0.25,
                "fee_usd": 0.01,
                "slippage_bps": 1.0,
                "acknowledgement_latency_ms": 40,
                "markout_bps": 1.0,
                "origin_run_id": "prior-run",
            },
        )

    report = audit_multi_asset_live_run(
        rows,
        {
            "BTC": traded_asset_rows(_RUN_ID),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    assert report["execution"]["fills"] == 2
    assert report["execution"]["projected_fills"] == 2
    assert {fill["origin_run_id"] for fill in report["execution"]["fill_details"]} == {
        _RUN_ID
    }
    assert report["coverage"] == {"complete": True, "technical_gaps": []}


def test_audit_script_publishes_immutable_multi_ledger_evidence(tmp_path: Path) -> None:
    """A published audit fingerprints every source and cannot overwrite history."""
    root = tmp_path / "bidirectional_cohort"
    root.mkdir()
    ledgers = {"decisions": _cohort_rows()}
    ledgers.update({symbol.lower(): _asset_rows(symbol) for symbol in _SYMBOLS})
    evidence = {}
    for name, rows in ledgers.items():
        content = "".join(json.dumps(row) + "\n" for row in rows).encode()
        (root / f"{name}.jsonl").write_bytes(content)
        evidence[name] = hashlib.sha256(content).hexdigest()
    output = tmp_path / "audit.json"
    module = _load_script()
    args = ["--ledger-root", str(root), "--run-id", _RUN_ID, "--out", str(output)]

    assert module.main(args) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["experiment_contract"]["execution_authority"] == "none"
    assert report["evidence"]["cohort"]["sha256"] == evidence["decisions"]
    assert {
        symbol: values["sha256"]
        for symbol, values in report["evidence"]["assets"].items()
    } == {symbol: evidence[symbol.lower()] for symbol in _SYMBOLS}
    assert report["evidence"]["retired_assets"] == {}
    with pytest.raises(FileExistsError, match="immutable cohort audit output exists"):
        module.main(args)
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "private_key" not in source
    assert "create_armed" not in source
    assert "submit_market_entry" not in source

    output_dir = tmp_path / "automatic-audits"
    assert (
        module.main(
            [
                "--ledger-root",
                str(root),
                "--run-id",
                _RUN_ID,
                "--out-dir",
                str(output_dir),
            ]
        )
        == 0
    )
    assert (output_dir / f"multi_asset_live_audit_{_RUN_ID}.json").is_file()


def test_audit_script_preserves_namespaced_asset_identity(tmp_path: Path) -> None:
    """HIP-3 ledger filenames retain the canonical lower-case namespace."""
    root = tmp_path / "bidirectional_cohort"
    root.mkdir()
    cohort = root / "decisions.jsonl"
    cohort.write_text("", encoding="utf-8")
    (root / "btc.jsonl").write_text("", encoding="utf-8")
    (root / "xyz:ddd.jsonl").write_text("", encoding="utf-8")
    module = _load_script()

    paths = module._asset_paths(root, cohort, ("BTC", "xyz:DDD"))

    assert paths == {
        "BTC": root / "btc.jsonl",
        "xyz:DDD": root / "xyz:ddd.jsonl",
    }


def _load_script() -> ModuleType:
    spec = spec_from_file_location("multi_asset_live_audit", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load audit script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _cohort_rows() -> list[dict[str, object]]:
    evaluations = [
        _evaluation(provider, symbol)
        for provider in (_HULK, _RANGE)
        for symbol in _SYMBOLS
    ]
    assets = _snapshot_assets()
    payloads = [
        ("configuration_identity", _cohort_identity()),
        ("intent_routing", {"actions": [], "withheld": [], "evaluations": evaluations}),
        ("market_candles", _market_payload()),
        ("cohort_snapshot", _cohort_snapshot(assets)),
        ("heartbeat", {"status": "running"}),
        ("intent_routing", {"actions": [], "withheld": [], "evaluations": evaluations}),
        ("cohort_snapshot", _cohort_snapshot(assets)),
        ("heartbeat", {"status": "running"}),
    ]
    return [
        _row(sequence, event_type, payload)
        for sequence, (event_type, payload) in enumerate(payloads, start=1)
    ]


def _cohort_identity() -> dict[str, object]:
    return {
        "symbol": "MULTI",
        "strategy_name": "multi_asset_bidirectional_cohort",
        "enabled_symbols": list(_SYMBOLS),
        "assets": [
            {
                "symbol": symbol,
                "sides": ["long", "short"],
                "leverage": 5.0,
                "venue_max_leverage": 40.0 if symbol == "BTC" else 25.0,
                "margin_fraction": 0.03,
                "max_notional_usd": 25.0,
                "stop_bps": 80.0,
                "maximum_hold_seconds": 28_800,
            }
            for symbol in _SYMBOLS
        ],
        "providers": [
            {
                "strategy_id": _HULK,
                "symbols": list(_SYMBOLS),
                "sides": ["long", "short"],
                "priority": 10,
                "position_policy": "enter_and_close",
                "timeframe": "30m",
                "maximum_entry_delay_seconds": 60,
                "execution_symbols": ["BTC"],
                "execution_side_overrides": {},
                "entry_context_overrides": {},
                "sizing_overrides": {},
                "execution": {
                    "entry_liquidity": "taker_ioc",
                    "stop_policy": "structural_clamped_bps",
                    "target_policy": "reward_risk",
                    "maximum_hold_seconds": 86_400,
                    "stop_bps": None,
                    "minimum_stop_bps": 20.0,
                    "maximum_stop_bps": 75.0,
                    "target_bps": None,
                    "target_r_multiple": 3.0,
                    "safety_stop_overlay": False,
                    "maximum_hold_policy": "fixed",
                    "hard_maximum_hold_seconds": None,
                },
                "source_profile": None,
            },
            {
                "strategy_id": _RANGE,
                "symbols": list(_SYMBOLS),
                "sides": ["long", "short"],
                "priority": 20,
                "position_policy": "enter_and_close",
                "timeframe": "1m",
                "maximum_entry_delay_seconds": 60,
                "execution_symbols": ["SOL"],
                "execution_side_overrides": {},
                "entry_context_overrides": {},
                "sizing_overrides": {},
                "execution": {
                    "entry_liquidity": "taker_ioc",
                    "stop_policy": "fixed_bps",
                    "target_policy": "none",
                    "maximum_hold_seconds": 172_800,
                    "stop_bps": 60.0,
                    "minimum_stop_bps": None,
                    "maximum_stop_bps": None,
                    "target_bps": None,
                    "target_r_multiple": None,
                    "safety_stop_overlay": False,
                    "maximum_hold_policy": "fixed",
                    "hard_maximum_hold_seconds": None,
                },
                "source_profile": None,
            },
        ],
        "position_policy": {
            "max_positions_per_symbol": 1,
            "maximum_concurrent_positions": 4,
        },
    }


def _snapshot_assets() -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "state": "FLAT",
            "position_size_signed": 0.0,
            "position_side": None,
            "last_fault": None,
        }
        for symbol in _SYMBOLS
    ]


def _cohort_snapshot(assets: list[dict[str, object]]) -> dict[str, object]:
    return {
        "account_value_usd": 503.16,
        "withdrawable_usd": 503.16,
        "total_margin_used_usd": 0.0,
        "total_notional_position_usd": 0.0,
        "open_position_count": 0,
        "assets": assets,
        "recent_fills": [],
    }


def _cohort_rows_with_trade() -> list[dict[str, object]]:
    rows = _cohort_rows()
    projected = [
        {
            "symbol": "BTC",
            "trade_id": trade_id,
            "price": price,
            "size": 0.25,
            "fee_usd": 0.01,
            "slippage_bps": slippage,
            "acknowledgement_latency_ms": 40,
            "markout_bps": markout,
        }
        for trade_id, slippage, markout, price in (
            (101, 1.0, 3.0, 100.01),
            (202, 2.0, 1.0, 103.98),
        )
    ]
    snapshots = [row for row in rows if row["event_type"] == "cohort_snapshot"]
    snapshots[0]["payload"]["recent_fills"] = projected[:1]
    snapshots[1]["payload"]["recent_fills"] = projected
    snapshots[1]["payload"]["account_value_usd"] = 504.13
    snapshots[1]["payload"]["withdrawable_usd"] = 504.13
    snapshots[1]["observed_at_utc"] = datetime.fromtimestamp(
        1_785_600_016,
        timezone.utc,
    ).isoformat()
    rows[-1]["observed_at_utc"] = datetime.fromtimestamp(
        1_785_600_032,
        timezone.utc,
    ).isoformat()
    return rows


def _evaluation(provider: str, symbol: str) -> dict[str, object]:
    required = 6 if provider == _HULK else 3
    met = 3 if provider == _HULK else 1
    blocker = "squeeze_not_armed" if provider == _HULK else "5m_regime_not_admitted"
    metrics = (
        {"adx": 18.0, "squeeze_on": False}
        if provider == _HULK
        else {"regime_admitted": False, "sma_gap_bps": 5.0}
    )
    return {
        "strategy_id": provider,
        "symbol": symbol,
        "decision_time_ms": 1_785_600_000_000,
        "reference_price": 100.0,
        "decision_action": "hold",
        "eligible": False,
        "reason": "no_trigger" if provider == _HULK else "regime_not_admitted",
        "side": None,
        "readiness": {
            "side": "long",
            "conditions_met": met,
            "conditions_required": required,
            "readiness_fraction": met / required,
            "blockers": [blocker],
            "indicators": ["FIXTURE"],
            "metrics": metrics,
        },
    }


def _regime_intent(strategy_id: str, side: str, score: float) -> dict[str, object]:
    return {
        "action": "enter",
        "strategy_id": strategy_id,
        "symbol": "BTC",
        "side": side,
        "decision_time_ms": 1_785_600_000_000,
        "reference_price": 100.0,
        "regime_alignment_score": score,
        "regime_alignment_stance": (
            "directionally_supported" if score > 0.0 else "directionally_opposed"
        ),
        "regime_decision_time_ms": 1_785_600_000_000,
        "regime_alignment_basis": "canonical_1m_5m_15m_1_3_2_v1",
    }


def _market_payload() -> dict[str, object]:
    return {
        "timeframe": "1m",
        "bars": {
            symbol: [
                {
                    "timestamp_ms": 1_785_600_000_000 + offset * 60_000,
                    "open": 100.0,
                    "high": 100.0,
                    "low": 100.0,
                    "close": 100.0,
                    "volume": 10.0,
                }
                for offset in range(60)
            ]
            for symbol in _SYMBOLS
        },
    }


def _asset_rows(symbol: str) -> list[dict[str, object]]:
    payloads = [
        (
            "configuration_identity",
            {"strategy_name": "cohort_asset", "symbol": symbol},
        ),
        (
            "reconciliation",
            {
                "account_value_usd": 503.16,
                "withdrawable_usd": 503.16,
                "open_order_ids": [],
            },
        ),
        (
            "position",
            {
                "size_signed": 0.0,
                "margin_used_usd": 0.0,
                "position_value_usd": 0.0,
                "unrealized_pnl_usd": 0.0,
            },
        ),
        ("liquidation_price", {"value": None}),
        (
            "state_transition",
            {
                "state": "STOPPED",
                "position_size_signed": 0.0,
                "stop_oid": None,
                "stop_reason": "operator_stop",
                "last_fault": None,
            },
        ),
    ]
    return [
        _row(sequence, event_type, payload, profile=f"{symbol.lower()}-profile")
        for sequence, (event_type, payload) in enumerate(payloads, start=1)
    ]


def _row(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    *,
    profile: str = "cohort-profile",
) -> dict[str, object]:
    observed_ms = 1_785_600_000_000 - 2_000 + sequence * 1_000
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "execution_mode": "live",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": profile,
        "profile_fingerprint": f"{profile}-fingerprint",
        "run_fingerprint": f"{profile}-run",
        "run_id": _RUN_ID,
        "payload": payload,
    }
