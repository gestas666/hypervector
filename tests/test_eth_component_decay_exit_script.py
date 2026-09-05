"""Tests for the immutable ETH component-decay exit experiment."""

from __future__ import annotations

from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from hypervector.research.hype_breakout_exit_models import HypeExitTrade

SCRIPT = Path(__file__).parents[1] / "scripts" / "eth_component_decay_exit.py"


def test_run_uses_exact_windows_fixed_entries_and_report_only_authority(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    """The command must compare only the exact ETH control entry cohorts."""
    script = _load()
    args = _args(tmp_path)
    replay_windows, candidate_counts = _install_run_stubs(script, args, monkeypatch)

    artifact = script.run(args)

    assert artifact["execution_authority"] == "none"
    assert artifact["runtime_strategy_changed"] is False
    assert candidate_counts == [5, 5]
    assert "2026-05-28 18:00:00+00:00" not in replay_windows[0]
    assert "2026-05-28 18:00:00+00:00" in replay_windows[1]
    assert artifact["segments"]["development"]["entry_parity"] is True
    assert artifact["segments"]["opened_final_60d"]["entry_parity"] is True
    assert len(artifact["segments"]["development"]["chronological_folds"]) == 5


def _install_run_stubs(
    script: ModuleType,
    args: SimpleNamespace,
    monkeypatch: object,
) -> tuple[list[tuple[str, ...]], list[int]]:
    """Install deterministic source, replay, and provenance seams."""
    replay_windows, candidate_counts = _source_replay_stubs(script, args, monkeypatch)
    _provenance_stubs(script, monkeypatch)
    return replay_windows, candidate_counts


def _source_replay_stubs(
    script: ModuleType,
    args: SimpleNamespace,
    monkeypatch: object,
) -> tuple[list[tuple[str, ...]], list[int]]:
    """Install deterministic input and candidate replay seams."""
    raw_bars = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-05-28T18:00:00Z",
                    "2026-06-01T00:00:00Z",
                ],
                utc=True,
            )
        }
    )
    funding = pd.DataFrame()
    replays = (_replay(_trades("2026-01-01", 5)), _replay(_trades("2026-06-01", 5)))
    replay_windows: list[tuple[str, ...]] = []
    candidate_counts: list[int] = []
    monkeypatch.setattr(
        script.pd,
        "read_parquet",
        lambda path: raw_bars if path == args.bars else funding,
    )

    def replay(window: pd.DataFrame, rates: pd.DataFrame) -> object:
        replay_windows.append(tuple(str(value) for value in window["timestamp"]))
        assert rates is funding
        return replays[len(replay_windows) - 1]

    def candidate(market: pd.DataFrame, trades: tuple[HypeExitTrade, ...]) -> object:
        candidate_counts.append(len(trades))
        changed = tuple(
            _replace_net(trade, trade.net_return_bps + 5.0) for trade in trades
        )
        return SimpleNamespace(
            report=SimpleNamespace(trades=changed),
            triggers=_trigger_rows(trades),
            unavailable_component_rows=(),
            technical_status="resolved",
            execution_authority="none",
        )

    monkeypatch.setattr(script, "replay_eth_precompression_pullback", replay)
    monkeypatch.setattr(script, "replay_eth_component_decay_exit", candidate)
    return replay_windows, candidate_counts


def _trigger_rows(trades: tuple[HypeExitTrade, ...]) -> tuple[SimpleNamespace, ...]:
    """Return one deterministic candidate trigger per fixed entry."""
    return tuple(SimpleNamespace(decision_time_utc="trigger") for _ in trades)


def _provenance_stubs(script: ModuleType, monkeypatch: object) -> None:
    """Install deterministic immutable-evidence seams."""
    monkeypatch.setattr(script, "file_evidence", lambda path: _evidence(path))
    monkeypatch.setattr(script, "_generator_identity", lambda: {"tree_sha256": "gen"})
    monkeypatch.setattr(script, "require_unchanged_file", lambda path, expected: None)
    monkeypatch.setattr(
        script,
        "require_unchanged_dependencies",
        lambda expected, root: None,
    )


def test_assessment_requires_both_sides_and_largest_winner_robustness() -> None:
    """A good headline cannot hide a failed side or winner concentration."""
    script = _load()
    passing = _comparison()

    accepted = script._assessment(passing, passing)
    failed_side = json.loads(json.dumps(passing))
    failed_side["candidate"]["by_side"]["short"]["net_return_bps"] = -1.0
    rejected = script._assessment(passing, failed_side)

    assert accepted["status"] == "eligible_for_future_report_only_observer"
    assert accepted["proposed_live_change"] == "none"
    assert rejected["status"] == "rejected_historical_candidate"
    assert "opened_final_both_sides_positive" in rejected["failed_conditions"]


def test_segment_rejects_more_component_exits_than_declared_triggers() -> None:
    """Adapter exits must reconcile to the exact component trigger inventory."""
    script = _load()
    control = _trades("2026-01-01", 5)
    changed = tuple(
        replace(trade, exit_reason="structural_reversal") for trade in control
    )
    result = SimpleNamespace(
        report=SimpleNamespace(trades=changed),
        triggers=(),
        unavailable_component_rows=(),
        technical_status="resolved",
    )

    with pytest.raises(ValueError, match="exits exceed causal triggers"):
        script._segment(control, result, include_folds=False)


def _load() -> ModuleType:
    """Load the script without requiring scripts to be a package."""
    spec = spec_from_file_location("eth_component_decay_exit_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load ETH component-decay script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(tmp_path: Path) -> SimpleNamespace:
    """Create source-bound command arguments and preregistration."""
    bars = tmp_path / "bars.parquet"
    funding = tmp_path / "funding.parquet"
    prereg = tmp_path / "prereg.json"
    bars.write_bytes(b"bars")
    funding.write_bytes(b"funding")
    prereg.write_text(json.dumps(_preregistration()), encoding="utf-8")
    return SimpleNamespace(
        bars=bars,
        funding=funding,
        preregistration=prereg,
        out=tmp_path / "out.json",
    )


def _preregistration() -> dict[str, object]:
    """Return the exact frozen candidate contract expected by the command."""
    return {
        "hypothesis_id": "v58-eth-r5-component-decay-exit-v1",
        "execution_authority": "none",
        "automatic_promotion": False,
        "candidate_contract": {
            "activation_mfe_bps": 300.0,
            "component_alignment_threshold": -0.5,
            "persistence_completed_1m_bars": 5,
            "stop_bps": 60.0,
            "maximum_hold_minutes": 720,
            "fee_bps_per_side": 4.5,
            "slippage_bps_per_side": 2.0,
            "parameter_grid": False,
        },
        "evaluation_windows": {
            "development_end_utc": "2026-05-28T12:00:00Z",
            "opened_final_start_utc": "2026-05-29T00:00:00Z",
            "opened_final_end_utc": "2026-07-28T00:00:00Z",
        },
        "frozen_inputs": {
            "bars": {"sha256": "sha-bars.parquet"},
            "funding": {"sha256": "sha-funding.parquet"},
        },
    }


def _evidence(path: Path) -> dict[str, object]:
    """Return deterministic evidence matching the preregistration fixture."""
    return {"sha256": f"sha-{path.name}", "bytes": path.stat().st_size}


def _replay(trades: tuple[HypeExitTrade, ...]) -> SimpleNamespace:
    """Build a deterministic exact-replay facade."""
    index = pd.date_range("2026-01-01", periods=10, freq="1min", tz="UTC")
    market = pd.DataFrame({"entry_side": None}, index=index)
    return SimpleNamespace(report=SimpleNamespace(trades=trades), market=market)


def _trades(start: str, count: int) -> tuple[HypeExitTrade, ...]:
    """Build alternating fixed-entry trades inside one requested segment."""
    base = pd.Timestamp(start, tz="UTC")
    return tuple(
        _trade(base + pd.Timedelta(minutes=index * 2), index) for index in range(count)
    )


def _trade(timestamp: pd.Timestamp, index: int) -> HypeExitTrade:
    """Build one fully specified ETH control lifecycle."""
    side = "long" if index % 2 == 0 else "short"
    net = 10.0 + index
    return HypeExitTrade(
        side,
        timestamp.isoformat(),
        (timestamp + pd.Timedelta(minutes=1)).isoformat(),
        (timestamp + pd.Timedelta(minutes=2)).isoformat(),
        100.0,
        100.2,
        99.4,
        net + 9.0,
        9.0,
        0.0,
        net,
        1,
        20.0,
        2.0,
        "maximum_hold",
    )


def _replace_net(trade: HypeExitTrade, net: float) -> HypeExitTrade:
    """Copy one trade with a changed candidate net return."""
    return replace(trade, net_return_bps=net)


def _comparison() -> dict[str, object]:
    """Build one assessment payload satisfying every frozen condition."""
    summary = {
        "trades": 10,
        "net_return_bps": 100.0,
        "profit_factor": 2.0,
        "maximum_drawdown_bps": 20.0,
        "net_excluding_largest_winner_bps": 50.0,
        "by_side": {
            "long": {"net_return_bps": 60.0},
            "short": {"net_return_bps": 40.0},
        },
    }
    control = summary | {
        "net_return_bps": 50.0,
        "profit_factor": 1.2,
        "maximum_drawdown_bps": 25.0,
    }
    folds = [
        {"candidate": {"net_return_bps": 10.0}, "delta_net_return_bps": 5.0}
        for _ in range(5)
    ]
    return {
        "technical_status": "resolved",
        "control": control,
        "candidate": summary,
        "chronological_folds": folds,
    }
