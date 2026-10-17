"""Acceptance for the source-bound v39-to-v49 growth operating delta."""

from __future__ import annotations

import pytest

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

_REPORT = Path("docs/research-journal/v49-growth-operating-delta-20260813-v1.json")
_V39 = Path(
    "data/logs/research/bidirectional_cohort/"
    "v39_route_portfolio_review_20260813T0452Z_v1.json"
)
_REGIME = Path(
    "data/logs/research/bidirectional_cohort/"
    "v49_observer_regime_forward_accuracy_20260813T0450Z_v6.json"
)
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/v49_growth_sizing_stress_20260812_v1.json"
)
_SOL = Path("data/logs/research/v49_sol_profit_lock_forward_20260813_v3.json")
_EXPANSION = Path(
    "data/logs/research/hip3_expansion_forward_disposition_20260813T0436Z_v3.json"
)
_BASE = Path("docs/research-journal/v49-strategy-repair-disposition.json")
_CONFIG = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _evidence(report: dict[str, object], key: str) -> dict[str, object]:
    evidence = report["evidence"]
    assert isinstance(evidence, dict)
    value = evidence[key]
    assert isinstance(value, dict)
    return value


def _stable_ledger_rows(regime: dict[str, object]) -> list[dict[str, object]]:
    evidence = regime["evidence"]
    assert isinstance(evidence, dict)
    ledger = evidence["ledger"]
    assert isinstance(ledger, dict)
    raw = Path(str(ledger["path"])).read_bytes()[: int(ledger["stable_bytes"])]
    assert sha256(raw).hexdigest() == ledger["sha256"]
    return [json.loads(line) for line in raw.splitlines()]


def _forward_counts(
    rows: list[dict[str, object]], run_ids: set[str]
) -> tuple[int, int, float]:
    seen: set[tuple[object, ...]] = set()
    bounds: dict[str, list[str]] = {}
    eligible = evaluations = 0
    for row in rows:
        run_id = str(row["run_id"])
        if run_id not in run_ids:
            continue
        bounds.setdefault(run_id, [str(row["observed_at_utc"])] * 2)[1] = str(
            row["observed_at_utc"]
        )
        if row.get("event_type") != "intent_routing":
            continue
        payload = row["payload"]
        assert isinstance(payload, dict)
        for value in payload["evaluations"]:
            assert isinstance(value, dict)
            key = (
                run_id,
                value["strategy_id"],
                value["symbol"],
                value["decision_time_ms"],
            )
            if key in seen:
                continue
            seen.add(key)
            evaluations += 1
            eligible += value["eligible"] is True
    seconds = sum(
        (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
        for start, end in bounds.values()
    )
    return evaluations, eligible, seconds / 3_600.0


@pytest.mark.evidence
def test_delta_is_report_only_and_binds_every_authoritative_source() -> None:
    """The operating decision must be immutable-source-bound and non-executable."""
    report = _load(_REPORT)
    assert report["schema_version"] == "v49_growth_operating_delta_v1"
    assert report["contract"] == {
        "automatic_live_promotion": False,
        "automatic_roster_change": False,
        "automatic_strategy_change": False,
        "execution_authority": "none",
        "performance_gate": False,
        "report_only": True,
        "runtime_strategy_changed": False,
    }
    paths = {
        "base_disposition": _BASE,
        "config": _CONFIG,
        "expansion": _EXPANSION,
        "regime": _REGIME,
        "sol_forward": _SOL,
        "stress": _STRESS,
        "v39_snapshot": _V39,
    }
    for key, path in paths.items():
        source = _evidence(report, key)
        assert source["path"] == str(path)
        assert source["sha256"] == _digest(path)


@pytest.mark.evidence
def test_delta_reconciles_current_live_closed_and_open_economics() -> None:
    """The frozen v39 snapshot must support every stated live total."""
    report = _load(_REPORT)
    source = _load(_V39)
    live = report["current_live_v39"]
    assert isinstance(live, dict)
    assert live["run_id"] == source["source"]["run_id"]
    assert live["closed_trades"] == source["summary"]["current_run_closed_trades"]
    assert live["closed_net_pnl_usd"] == source["summary"]["current_run_net_pnl_usd"]
    open_net = 0.0
    open_count = 0
    for route in source["routes"].values():
        for side in route["current_run"]["sides"].values():
            open_count += side["open_positions"]
            open_net += side["open_marked_pnl_usd"]
    assert live["open_positions"] == open_count == 4
    assert abs(float(live["open_marked_net_pnl_usd"]) - open_net) < 1e-9
    combined = float(live["closed_net_pnl_usd"]) + open_net
    assert abs(float(live["provisional_combined_net_pnl_usd"]) - combined) < 1e-9


@pytest.mark.evidence
def test_delta_reconciles_cross_restart_frequency_without_backtest_promotion() -> None:
    """Forward frequency must come from the frozen observer prefix, not history."""
    report = _load(_REPORT)
    regime = _load(_REGIME)
    source = regime["source"]
    run_ids = set(source["compatible_run_ids"])
    evaluations, eligible, duration = _forward_counts(
        _stable_ledger_rows(regime), run_ids
    )
    window = report["v49_forward_window"]
    assert window["compatible_run_ids"] == source["compatible_run_ids"]
    assert window["provider_evaluations"] == evaluations == 2_086
    assert window["eligible_signals"] == eligible == 1
    assert abs(float(window["observed_hours"]) - duration) < 1e-9
    assert window["resolved_lifecycles"] == 0
    assert window["frequency_claim"] == "forward_frequency_not_established"


@pytest.mark.evidence
def test_delta_keeps_sizing_and_regime_claims_empirically_bounded() -> None:
    """Meaningful sizing cannot be mislabeled as proven expectancy or leverage edge."""
    report = _load(_REPORT)
    stress = _load(_STRESS)
    scenario = next(
        row for row in stress["scenarios"] if row["account_value_usd"] == 5_000.0
    )
    sizing = report["v49_sizing"]
    assert sizing["configured_assets"] == 4
    assert sizing["account_position_capacity"] == 10
    assert sizing["maximum_simultaneous_positions"] == 4
    assert sizing["margin_fraction_per_asset"] == 0.15
    assert sizing["route_aware_maximum_margin_fraction"] == 0.60
    assert sizing["planned_notional_usd_per_asset"] == 7_500.0
    assert (
        sizing["p99_stop_wave_loss_usd"] == scenario["stacked_p99_stop_wave_loss_usd"]
    )
    assert report["regime_disposition"]["variable_leverage_authorized"] is False
    assert (
        report["regime_disposition"]["reason"]
        == "independent_episode_evidence_insufficient"
    )


@pytest.mark.evidence
def test_delta_prioritizes_mu_but_makes_no_roster_or_exit_change() -> None:
    """Updated expansion/path evidence may rank research without mutating v49."""
    report = _load(_REPORT)
    expansion = _load(_EXPANSION)
    assert (
        report["expansion_disposition"]["priority_order"]
        == expansion["research_priority_order"]
    )
    assert report["expansion_disposition"]["next_candidate"] == "xyz:MU"
    assert report["expansion_disposition"]["live_roster_changes"] == []
    decision = report["operating_decision"]
    assert decision["entry_contract"] == "retain_frozen_v49"
    assert decision["exit_contract"] == "retain_route_specific_v49_first_window"
    assert decision["sizing_contract"] == "retain_equal_15pct_first_window"
    assert decision["successor_state"] == "forward_evidence_incomplete"
    assert decision["next_live_transition_requires"] == [
        "explicit_user_authorization",
        "verified_flat_and_order_free_boundary",
        "recoverable_accounting_epoch_backup",
        "fresh_v49_technical_preflight",
    ]
