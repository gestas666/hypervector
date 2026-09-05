"""Tests for the immutable ETH opposing-breakout exit command."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd

from hypervector.research.hype_breakout_exit_models import HypeExitTrade

SCRIPT = Path(__file__).parents[1] / "scripts" / "eth_opposing_breakout_exit.py"


def test_run_uses_exact_windows_entries_delays_and_report_only_authority(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    """The command must preserve windows and run both declared delay contracts."""
    script = _load()
    args = _args(tmp_path)
    replay_windows: list[tuple[str, ...]] = []
    candidate_calls: list[tuple[int, int]] = []
    _install_source_stubs(script, args, replay_windows, monkeypatch)

    def candidate(
        market: pd.DataFrame,
        trades: tuple[HypeExitTrade, ...],
        spec: object,
    ) -> SimpleNamespace:
        delay = getattr(spec, "additional_decision_delay_minutes")
        candidate_calls.append((len(trades), delay))
        return SimpleNamespace(
            report=SimpleNamespace(trades=trades),
            triggers=(),
            unavailable_direction_rows=(),
            technical_status="resolved",
        )

    monkeypatch.setattr(script, "replay_eth_opposing_breakout_exit", candidate)

    artifact = script.run(args)

    assert artifact["execution_authority"] == "none"
    assert artifact["runtime_strategy_changed"] is False
    assert candidate_calls == [(5, 0), (5, 1), (5, 0), (5, 1)]
    assert "2026-05-28 18:00:00+00:00" not in replay_windows[0]
    assert "2026-05-28 18:00:00+00:00" in replay_windows[1]
    assert artifact["segments"]["development"]["entry_parity"] is True
    assert artifact["segments"]["opened_final_60d"]["entry_parity"] is True


def _install_source_stubs(
    script: ModuleType,
    args: SimpleNamespace,
    replay_windows: list[tuple[str, ...]],
    monkeypatch: object,
) -> None:
    """Install deterministic market, replay, and provenance seams."""
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
    monkeypatch.setattr(
        script.pd,
        "read_parquet",
        lambda path: raw_bars if path == args.bars else funding,
    )

    def replay(window: pd.DataFrame, rates: pd.DataFrame) -> object:
        replay_windows.append(tuple(str(value) for value in window["timestamp"]))
        assert rates is funding
        return replays[len(replay_windows) - 1]

    monkeypatch.setattr(script, "replay_eth_precompression_pullback", replay)
    monkeypatch.setattr(script, "file_evidence", lambda path: _evidence(path))
    monkeypatch.setattr(script, "_generator_identity", lambda: {"tree_sha256": "gen"})
    monkeypatch.setattr(script, "require_unchanged_file", lambda path, expected: None)
    monkeypatch.setattr(
        script,
        "require_unchanged_dependencies",
        lambda expected, root: None,
    )


def _load() -> ModuleType:
    """Load the command without requiring scripts to be a package."""
    spec = spec_from_file_location("eth_opposing_breakout_exit_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load ETH opposing-breakout script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(tmp_path: Path) -> SimpleNamespace:
    """Create source-bound command arguments and preregistration."""
    bars = tmp_path / "bars.parquet"
    funding = tmp_path / "funding.parquet"
    preregistration = tmp_path / "prereg.json"
    bars.write_bytes(b"bars")
    funding.write_bytes(b"funding")
    preregistration.write_text(json.dumps(_preregistration()), encoding="utf-8")
    return SimpleNamespace(
        bars=bars,
        funding=funding,
        preregistration=preregistration,
        out=tmp_path / "out.json",
    )


def _preregistration() -> dict[str, object]:
    """Return the frozen contract expected by the command."""
    return {
        "hypothesis_id": "v58-eth-opposing-breakout-exit-v1",
        "execution_authority": "none",
        "automatic_promotion": False,
        "candidate_contract": {
            "trigger_state": "fresh_completed_5m_BREAKOUT_onset",
            "trigger_direction": "point_in_time_5m_breakout_side_opposes_open_position",
            "execution_reference": "next_1m_open",
            "delay_stress_execution_reference": "second_1m_open_after_trigger",
            "stop_bps": 60.0,
            "maximum_hold_minutes": 720,
            "fee_bps_per_side": 4.5,
            "slippage_bps_per_side": 2.0,
            "protective_stop_precedence": True,
            "parameter_grid": False,
            "entry_policy_changed": False,
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
    """Return deterministic evidence matching the source fixture."""
    return {"sha256": f"sha-{path.name}", "bytes": path.stat().st_size}


def _replay(trades: tuple[HypeExitTrade, ...]) -> SimpleNamespace:
    """Build a deterministic exact-replay facade."""
    market = pd.DataFrame(index=pd.date_range("2026-01-01", periods=2, tz="UTC"))
    return SimpleNamespace(report=SimpleNamespace(trades=trades), market=market)


def _trades(start: str, count: int) -> tuple[HypeExitTrade, ...]:
    """Build alternating fixed-entry trades inside one segment."""
    base = pd.Timestamp(start, tz="UTC")
    return tuple(
        _trade(base + pd.Timedelta(minutes=3 * index), index) for index in range(count)
    )


def _trade(timestamp: pd.Timestamp, index: int) -> HypeExitTrade:
    """Return one fully specified synthetic lifecycle."""
    side = "long" if index % 2 == 0 else "short"
    return HypeExitTrade(
        side,
        timestamp.isoformat(),
        (timestamp + pd.Timedelta(minutes=1)).isoformat(),
        (timestamp + pd.Timedelta(minutes=2)).isoformat(),
        100.0,
        100.2,
        99.4,
        19.0,
        9.0,
        0.0,
        10.0,
        1,
        20.0,
        2.0,
        "maximum_hold",
    )
