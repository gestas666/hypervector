"""Tests for the immutable ETH pullback mechanism-attribution command."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.hype_breakout_exit_models import HypeExitTrade, HypeSide

SCRIPT = Path(__file__).parents[1] / "scripts" / "eth_pullback_mechanism_attribution.py"


@dataclass(frozen=True)
class _Evidence:
    rows: int


def test_run_binds_exact_replay_and_source_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command must attribute the exact reusable ETH replay, not a proxy."""
    script = _load()
    args, replay_windows = _install_run_stubs(tmp_path, script, monkeypatch)

    artifact = script.run(args)

    _assert_exact_run_artifact(artifact, args.bars, replay_windows)


def _install_run_stubs(
    tmp_path: Path, script: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> tuple[SimpleNamespace, list[tuple[str, ...]]]:
    """Install deterministic exact-replay sources for the command contract."""
    bars = tmp_path / "bars.parquet"
    funding = tmp_path / "funding.parquet"
    bars.write_bytes(b"bars")
    funding.write_bytes(b"funding")
    development_replay, final_replay = _run_replays()
    raw_bars = _raw_bars()
    funding_rows = pd.DataFrame()
    monkeypatch.setattr(
        script.pd,
        "read_parquet",
        lambda path: raw_bars if path == bars else funding_rows,
    )
    replay_windows: list[tuple[str, ...]] = []

    def replay_window(raw_window: pd.DataFrame, raw_funding: pd.DataFrame) -> object:
        timestamps = tuple(str(value) for value in raw_window["timestamp"])
        replay_windows.append(timestamps)
        assert raw_funding is funding_rows
        return development_replay if len(replay_windows) == 1 else final_replay

    monkeypatch.setattr(script, "replay_eth_precompression_pullback", replay_window)
    monkeypatch.setattr(
        script,
        "file_evidence",
        lambda path: {"sha256": f"sha-{path.name}", "bytes": len(path.name)},
    )
    for name in ("_profit_lock_comparison", "_duration_comparison"):
        monkeypatch.setattr(
            script, name, lambda market, trades: {"marker": len(trades)}
        )
    return SimpleNamespace(bars=bars, funding=funding), replay_windows


def _run_replays() -> tuple[SimpleNamespace, SimpleNamespace]:
    """Build deterministic development and final replay objects."""
    development_market = pd.DataFrame(
        {"entry_side": ["long"], "breakout_side": ["long"]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-01-01T00:00:00Z")]),
    )
    final_market = pd.DataFrame(
        {"entry_side": ["short"], "breakout_side": ["long"]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-06-01T00:00:00Z")]),
    )
    development_replay = SimpleNamespace(
        market=development_market,
        report=SimpleNamespace(trades=(_trade("2026-01-01T00:00:00Z", "long"),)),
        market_evidence=_Evidence(rows=10),
        policy_evidence=_Evidence(rows=1),
    )
    final_replay = SimpleNamespace(
        market=final_market,
        report=SimpleNamespace(trades=(_trade("2026-06-01T00:00:00Z", "short"),)),
        market_evidence=_Evidence(rows=20),
        policy_evidence=_Evidence(rows=2),
    )
    return development_replay, final_replay


def _raw_bars() -> pd.DataFrame:
    """Build the boundary-spanning raw bar input."""
    return pd.DataFrame(
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


def _assert_exact_run_artifact(
    artifact: dict[str, object],
    bars: Path,
    replay_windows: list[tuple[str, ...]],
) -> None:
    """Assert identity, boundary, provenance, and comparison bindings."""
    assert artifact["strategy_id"] == (
        "eth_breakout_precompression_pullback_bidirectional_v1"
    )
    assert artifact["contract"]["execution_authority"] == "none"
    assert len(replay_windows) == 2
    assert "2026-05-28 18:00:00+00:00" not in replay_windows[0]
    assert "2026-05-28 18:00:00+00:00" in replay_windows[1]
    final = artifact["segments"]["opened_final_60d"]
    assert final["by_side_relation"]["short|opposed"]["trades"] == 1
    assert artifact["source_replay"] == {
        "development": {
            "market_evidence": {"rows": 10},
            "policy_evidence": {"rows": 1},
            "selection": {
                "source_scope": "development_boundary_replay",
                "selected_trades": 1,
            },
        },
        "opened_final_60d": {
            "market_evidence": {"rows": 20},
            "policy_evidence": {"rows": 2},
            "selection": {
                "source_scope": "full_history_causal_warmup_then_boundary_selection",
                "selected_trades": 1,
            },
        },
    }
    assert artifact["data_evidence"][str(bars)]["sha256"] == "sha-bars.parquet"
    assert artifact["profit_lock_comparison"] == {
        "development": {"marker": 1},
        "opened_final_60d": {"marker": 1},
    }
    assert artifact["duration_comparison"] == {
        "development": {"marker": 1},
        "opened_final_60d": {"marker": 1},
    }


def test_profit_lock_comparison_uses_exact_eth_exit_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ETH locks must retain the candidate's 60-bps stop and 12-hour horizon."""
    script = _load()
    market = pd.DataFrame({"entry_side": ["short"]})
    trade = _trade("2026-06-01T00:00:00Z", "short")
    configs: list[object] = []
    monkeypatch.setattr(
        script,
        "freeze_hype_entry_cohort",
        lambda source, trades: source,
    )

    def replay_policy(source: object, policy: object, config: object) -> object:
        configs.append(config)
        return SimpleNamespace(
            completed_trades=1,
            wins=1,
            losses=0,
            net_return_bps=12.0,
            profit_factor=None,
            maximum_drawdown_bps=0.0,
            exit_reasons={"maximum_hold": 1},
        )

    monkeypatch.setattr(script, "replay_hype_breakout_exits", replay_policy)

    comparison = script._profit_lock_comparison(market, (trade,))

    assert len(comparison) == 4
    assert comparison["generic_8h_control"]["net_return_bps"] == 12.0
    assert all(config.stop_bps == 60.0 for config in configs)
    assert all(config.maximum_hold_minutes == 720 for config in configs)


def test_duration_comparison_preserves_entries_costs_and_side_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bounded duration screen must vary only the maximum hold."""
    script = _load()
    market = pd.DataFrame({"entry_side": ["short"]})
    trade = _trade("2026-06-01T00:00:00Z", "short")
    configs: list[object] = []
    policies: list[object] = []
    monkeypatch.setattr(
        script,
        "freeze_hype_entry_cohort",
        lambda source, trades: source,
    )

    def replay_policy(source: object, policy: object, config: object) -> object:
        configs.append(config)
        policies.append(policy)
        return SimpleNamespace(
            completed_trades=1,
            wins=1,
            losses=0,
            net_return_bps=11.0,
            profit_factor=None,
            maximum_drawdown_bps=0.0,
            exit_reasons={"maximum_hold": 1},
            monthly_net_bps={"2026-06": 11.0},
            trades=(trade,),
        )

    monkeypatch.setattr(script, "replay_hype_breakout_exits", replay_policy)

    comparison = script._duration_comparison(market, (trade,))

    assert set(comparison) == {"fixed_240m", "fixed_480m", "fixed_720m"}
    assert [config.maximum_hold_minutes for config in configs] == [240, 480, 720]
    assert all(config.stop_bps == 60.0 for config in configs)
    assert all(config.fee_bps_per_side == 4.5 for config in configs)
    assert all(config.slippage_bps_per_side == 2.0 for config in configs)
    assert all(policy.profit_activation_bps is None for policy in policies)
    assert comparison["fixed_240m"]["by_side"]["short"]["trades"] == 1
    assert comparison["fixed_240m"]["by_side"]["long"]["trades"] == 0
    assert comparison["fixed_240m"]["net_excluding_largest_winner_bps"] == 0.0


def _load() -> ModuleType:
    """Load the report-only command without invoking its CLI entry point."""
    spec = spec_from_file_location("eth_pullback_mechanism_attribution_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load ETH pullback attribution script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trade(timestamp: str, side: HypeSide) -> HypeExitTrade:
    signal = pd.Timestamp(timestamp)
    return HypeExitTrade(
        side=side,
        signal_time_utc=signal.isoformat(),
        entry_time_utc=(signal + pd.Timedelta(minutes=1)).isoformat(),
        exit_time_utc=(signal + pd.Timedelta(minutes=11)).isoformat(),
        entry_price=100.0,
        exit_price=99.8,
        stop_price=100.6,
        gross_return_bps=20.0,
        fee_bps=9.0,
        funding_bps=0.0,
        net_return_bps=11.0,
        hold_minutes=10,
        maximum_favorable_excursion_bps=25.0,
        maximum_adverse_excursion_bps=3.0,
        exit_reason="maximum_hold",
    )
