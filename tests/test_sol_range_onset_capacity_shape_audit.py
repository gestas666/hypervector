"""Tests for paired SOL capacity-shape evidence aggregation."""

from __future__ import annotations

import copy
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.research.sol_range_onset_capacity_shape_audit import (
    audit_capacity_shape_pairs,
)
from hypervector.research.sol_range_onset_backward_exact_audit import (
    audit_backward_exact_blocks,
)

SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "sol_range_onset_capacity_shape_audit.py"
)
BACKWARD_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "sol_range_onset_backward_exact_audit.py"
)


def _load_script() -> ModuleType:
    spec = spec_from_file_location("sol_range_onset_capacity_shape_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_backward_script() -> ModuleType:
    spec = spec_from_file_location(
        "sol_range_onset_backward_exact_audit", BACKWARD_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trade(
    direction: str,
    entry_time: int,
    exit_time: int,
    pnl: float,
) -> dict[str, object]:
    return {
        "direction": direction,
        "entry_decision_time_ms": entry_time,
        "exit_event_time_ms": exit_time,
        "exit_reason": "stop" if pnl < 0.0 else "signal",
        "net_pnl_usd": pnl,
        "fees_usd": 1.0,
        "funding_cashflow_usd": -0.1,
    }


def _replay(trades: list[dict[str, object]]) -> dict[str, object]:
    pnl = sum(float(trade["net_pnl_usd"]) for trade in trades)
    profits = sum(
        float(trade["net_pnl_usd"])
        for trade in trades
        if float(trade["net_pnl_usd"]) > 0.0
    )
    losses = -sum(
        float(trade["net_pnl_usd"])
        for trade in trades
        if float(trade["net_pnl_usd"]) < 0.0
    )
    return {
        "status": "complete",
        "failure": None,
        "initial_equity": 15_000.0,
        "final_equity": 15_000.0 + pnl,
        "completed_trades": len(trades),
        "wins": sum(float(trade["net_pnl_usd"]) > 0.0 for trade in trades),
        "losses": sum(float(trade["net_pnl_usd"]) < 0.0 for trade in trades),
        "profit_factor": profits / losses if losses else None,
        "total_fees_usd": float(len(trades)),
        "funding_cashflow_usd": -0.1 * len(trades),
        "liquidations": 0,
        "realized_maximum_drawdown_pct": -1.0,
        "mark_to_market_maximum_drawdown_pct": None,
        "trades": trades,
    }


def _trial(stop_bps: float, replay: dict[str, object]) -> dict[str, object]:
    return {
        "trial_id": f"stop={stop_bps:g}__exposure=0.15",
        "trial": {
            "stop_bps": stop_bps,
            "margin_fraction": 0.03,
            "leverage": 5.0,
        },
        "effective_exposure": 0.15,
        "execution_authority": "none",
        "event_replay": replay,
    }


def _artifact(
    path: Path,
    *,
    start: str,
    end: str,
    surface: str,
    sixty: dict[str, object],
    eighty: dict[str, object] | None = None,
) -> Path:
    trials = [_trial(60.0, sixty)]
    if eighty is not None:
        trials.append(_trial(80.0, eighty))
    segment = {
        "start_utc": start,
        "end_utc": end,
        "signal_events": 2,
        "funding_events": 1,
        "trials": trials,
    }
    payload = {
        "schema_version": 2,
        "symbol": "SOL",
        "execution_authority": "none",
        "model_authority": "none",
        "trial_surface": surface,
        "development": copy.deepcopy(segment),
        "validation": copy.deepcopy(segment),
        "pseudo_holdout": copy.deepcopy(segment),
        "continuous": copy.deepcopy(segment),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _pair(
    tmp_path: Path,
    name: str,
    start: str,
    end: str,
    sixty_trades: list[dict[str, object]],
    eighty_trades: list[dict[str, object]],
) -> tuple[Path, Path]:
    sixty = _replay(sixty_trades)
    source = _artifact(
        tmp_path / f"{name}-source.json",
        start=start,
        end=end,
        surface="capacity",
        sixty=sixty,
    )
    shape = _artifact(
        tmp_path / f"{name}-shape.json",
        start=start,
        end=end,
        surface="capacity-shape",
        sixty=copy.deepcopy(sixty),
        eighty=_replay(eighty_trades),
    )
    return source, shape


def test_audit_binds_controls_and_aggregates_paired_shapes(tmp_path: Path) -> None:
    pairs = (
        _pair(
            tmp_path,
            "one",
            "2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z",
            [_trade("long", 1, 2, 10.0), _trade("short", 3, 4, -2.0)],
            [_trade("long", 1, 5, 12.0), _trade("short", 3, 4, -3.0)],
        ),
        _pair(
            tmp_path,
            "two",
            "2026-01-03T00:00:00Z",
            "2026-01-04T00:00:00Z",
            [_trade("long", 6, 7, -1.0)],
            [_trade("long", 6, 8, 4.0)],
        ),
    )

    report = audit_capacity_shape_pairs(pairs, expected_trades=3)

    assert report["control_match"] is True
    assert report["entry_population_match"] is True
    assert report["artifact_pair_count"] == 2
    assert report["paired_changed_exits"] == 2
    assert report["runtime_strategy_changed"] is False
    sixty = report["stops"]["60"]
    assert sixty["trades"] == 3
    assert sixty["reset_block_net_pnl_usd"] == pytest.approx(7.0)
    assert sixty["profit_factor"] == pytest.approx(10.0 / 3.0)
    assert sixty["largest_winner_usd"] == pytest.approx(10.0)
    assert sixty["largest_winner_gross_profit_share"] == pytest.approx(1.0)
    assert sixty["net_pnl_without_largest_winner_usd"] == pytest.approx(-3.0)
    assert sixty["directions"]["long"]["net_pnl_usd"] == pytest.approx(9.0)
    eighty = report["stops"]["80"]
    assert eighty["reset_block_net_pnl_usd"] == pytest.approx(13.0)
    assert eighty["largest_winner_usd"] == pytest.approx(12.0)
    assert eighty["largest_winner_gross_profit_share"] == pytest.approx(0.75)
    assert eighty["net_pnl_without_largest_winner_usd"] == pytest.approx(1.0)
    assert len(report["source_evidence"]) == 2


def test_audit_rejects_nonidentical_sixty_control(tmp_path: Path) -> None:
    source, shape = _pair(
        tmp_path,
        "one",
        "2026-01-01T00:00:00Z",
        "2026-01-02T00:00:00Z",
        [_trade("long", 1, 2, 10.0)],
        [_trade("long", 1, 3, 11.0)],
    )
    payload = json.loads(shape.read_text(encoding="utf-8"))
    payload["continuous"]["trials"][0]["event_replay"]["final_equity"] += 1.0
    shape.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="60-bps control differs"):
        audit_capacity_shape_pairs(((source, shape),), expected_trades=1)


def test_audit_rejects_changed_entry_population(tmp_path: Path) -> None:
    source, shape = _pair(
        tmp_path,
        "one",
        "2026-01-01T00:00:00Z",
        "2026-01-02T00:00:00Z",
        [_trade("long", 1, 2, 10.0)],
        [_trade("long", 2, 3, 11.0)],
    )

    with pytest.raises(ValueError, match="entry population differs"):
        audit_capacity_shape_pairs(((source, shape),), expected_trades=1)


def test_capacity_shape_audit_script_writes_once(tmp_path: Path) -> None:
    source, shape = _pair(
        tmp_path,
        "one",
        "2026-01-01T00:00:00Z",
        "2026-01-02T00:00:00Z",
        [_trade("long", 1, 2, 10.0)],
        [_trade("long", 1, 3, 11.0)],
    )
    output = tmp_path / "audit.json"
    module = _load_script()
    arguments = [
        "--pair",
        str(source),
        str(shape),
        "--expected-trades",
        "1",
        "--out",
        str(output),
    ]

    assert module.main(arguments) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["control_match"] is True
    assert module.main(arguments) == 1


def test_backward_exact_audit_binds_declaration_and_reports_fragility(
    tmp_path: Path,
) -> None:
    """Four predeclared exact blocks must yield a mechanical disposition."""
    bounds = [
        ("2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"),
        ("2025-01-03T00:00:00Z", "2025-01-04T00:00:00Z"),
        ("2025-01-05T00:00:00Z", "2025-01-06T00:00:00Z"),
        ("2025-01-07T00:00:00Z", "2025-01-08T00:00:00Z"),
    ]
    declaration = _backward_declaration(tmp_path, bounds)
    pnl_pairs = ((130.0, 100.0), (10.0, 5.0), (-5.0, -10.0), (-5.0, -10.0))
    artifacts = tuple(
        _backward_artifact(tmp_path, index, bounds[index - 1], *pnl)
        for index, pnl in enumerate(pnl_pairs, start=1)
    )

    report = audit_backward_exact_blocks(declaration, artifacts)

    sixty = report["stops"]["60"]
    assert sixty["reset_block_net_pnl_usd"] == pytest.approx(130.0)
    assert sixty["positive_blocks"] == 2
    assert sixty["liquidations"] == 0
    assert report["disposition"]["60"] == "supportive_but_fragile"
    assert "aggregate profit depends on one block" in report["fragility"]["60"]
    assert len(report["artifact_evidence"]) == 4


def test_backward_exact_audit_preserves_public_result_when_mark_is_censored(
    tmp_path: Path,
) -> None:
    """A declared mark gap must not erase the independently complete public bound."""
    bounds = [
        ("2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"),
        ("2025-01-03T00:00:00Z", "2025-01-04T00:00:00Z"),
        ("2025-01-05T00:00:00Z", "2025-01-06T00:00:00Z"),
        ("2025-01-07T00:00:00Z", "2025-01-08T00:00:00Z"),
    ]
    declaration = _backward_declaration(tmp_path, bounds)
    artifacts = [
        _backward_artifact(tmp_path, index, bounds[index - 1], 10.0, 5.0)
        for index in range(1, 5)
    ]
    censored = json.loads(artifacts[1].read_text(encoding="utf-8"))
    censored["sampled_mark_surface"] = {
        "mark_validation_status": "censored",
        "censor_reason": "mark query gap 130000ms exceeds 120000ms",
        "price_archive": {"partition_hours": 1},
    }
    artifacts[1].write_text(json.dumps(censored), encoding="utf-8")

    report = audit_backward_exact_blocks(declaration, artifacts)

    public = report["surfaces"]["public_trade"]
    assert public["status"] == "complete"
    assert public["completed_blocks"] == 4
    assert public["stops"]["60"]["trades"] == 4
    assert report["stops"] == public["stops"]
    mark = report["surfaces"]["sampled_mark"]
    assert mark["status"] == "censored"
    assert mark["completed_blocks"] == 3
    assert mark["censored_blocks"] == [2]
    assert mark["censor_reasons"] == {"2": "mark query gap 130000ms exceeds 120000ms"}


def test_backward_exact_audit_script_writes_once(tmp_path: Path) -> None:
    """The final declaration-bound report must be immutable."""
    bounds = [
        ("2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"),
        ("2025-01-03T00:00:00Z", "2025-01-04T00:00:00Z"),
        ("2025-01-05T00:00:00Z", "2025-01-06T00:00:00Z"),
        ("2025-01-07T00:00:00Z", "2025-01-08T00:00:00Z"),
    ]
    declaration = _backward_declaration(tmp_path, bounds)
    artifacts = [
        _backward_artifact(tmp_path, index, bounds[index - 1], 10.0, 5.0)
        for index in range(1, 5)
    ]
    output = tmp_path / "backward-audit.json"
    arguments = ["--declaration", str(declaration)]
    for artifact in artifacts:
        arguments.extend(("--artifact", str(artifact)))
    arguments.extend(("--out", str(output)))
    module = _load_backward_script()

    assert module.main(arguments) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["stops"]["60"]["trades"] == 4
    assert module.main(arguments) == 1


def _backward_declaration(
    tmp_path: Path,
    bounds: list[tuple[str, str]],
) -> Path:
    blocks = [
        {
            "number": index,
            "signal_warmup_start_utc": start,
            "development_start_utc": start,
            "development_end_utc": end,
            "validation_end_utc": end,
            "pseudo_holdout_end_utc": end,
        }
        for index, (start, end) in enumerate(bounds, start=1)
    ]
    payload = {
        "mode": "sol_range_onset_backward_exact_replay_declaration",
        "symbol": "SOL",
        "execution_authority": "none",
        "model_authority": "none",
        "blocks": blocks,
        "fixed_trial": {
            "effective_exposure": 0.15,
            "initial_equity_per_block": 15_000.0,
            "leverage": 5.0,
            "margin_fraction": 0.03,
            "maximum_hold_hours": 48,
            "price_partition_hours": 1,
            "stop_bps": [60.0, 80.0],
        },
    }
    path = tmp_path / "declaration.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _backward_artifact(
    tmp_path: Path,
    number: int,
    bounds: tuple[str, str],
    sixty_pnl: float,
    eighty_pnl: float,
) -> Path:
    entry = number * 10
    sixty = _replay([_trade("long", entry, entry + 1, sixty_pnl)])
    eighty = _replay([_trade("long", entry, entry + 2, eighty_pnl)])
    path = _artifact(
        tmp_path / f"backward-{number}.json",
        start=bounds[0],
        end=bounds[1],
        surface="capacity-shape",
        sixty=sixty,
        eighty=eighty,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 3
    payload["signal_warmup_start_utc"] = bounds[0]
    segments = {
        name: payload[name]
        for name in ("development", "validation", "pseudo_holdout", "continuous")
    }
    for name in ("validation", "pseudo_holdout"):
        segments[name]["start_utc"] = bounds[1]
    for segment in segments.values():
        for trial in segment["trials"]:
            trial["replay_config"] = _replay_config(trial["trial"]["stop_bps"])
    payload["sampled_mark_surface"] = {
        "mark_validation_status": "complete",
        "price_archive": {"partition_hours": 1},
        **segments,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _replay_config(stop_bps: float) -> dict[str, object]:
    return {
        "initial_equity": 15_000.0,
        "margin_fraction": 0.03,
        "leverage": 5.0,
        "venue_max_leverage": 20.0,
        "stop_bps": stop_bps,
        "max_hold_ms": 172_800_000,
        "taker_fee_rate": 0.00045,
        "reentry_cooldown_ms": 60_000,
    }
