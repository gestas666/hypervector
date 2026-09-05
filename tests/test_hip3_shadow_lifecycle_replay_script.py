"""Immutable command boundary for HIP-3 shadow lifecycle replay."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

from hypervector.cohort_profit_lock_policy import policy_declaration
from hypervector.research.hip3_shadow_lifecycle_archive_marks import (
    ArchiveRepairingHip3MarkSource,
)


def _script() -> ModuleType:
    path = Path("scripts/hip3_shadow_lifecycle_replay.py")
    spec = importlib.util.spec_from_file_location("hip3_lifecycle_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("HIP-3 lifecycle script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_command_publishes_one_authority_none_source_bound_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _script()
    args = _arguments(script, tmp_path)
    expected = _report()
    monkeypatch.setattr(
        script, "build_hip3_shadow_lifecycle_replay", lambda **_: expected
    )

    report = script.run_command(
        args,
        candle_fetcher=lambda *_args, **_kwargs: _candles(),
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        mark_source=_MarkSource(),
    )

    persisted = json.loads(Path(args.output).read_text())
    assert report == persisted
    assert persisted["execution_authority"] == "none"
    assert persisted["automatic_promotion"] is False
    assert persisted["runtime_strategy_changed"] is False
    assert persisted["input_evidence"]["journal_prefix"]["rows"] == 1
    assert persisted["input_evidence"]["book_ledger_prefix"]["rows"] == 1
    assert persisted["input_evidence"]["mark_archive"]["rows"] == 2
    assert persisted["source_snapshots"]["candles"][0]["source"] == "hl"
    assert persisted["source_snapshots"]["funding"][0]["source"] == "hl_funding_history"


def test_prefix_mutation_aborts_without_partial_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _script()
    args = _arguments(script, tmp_path)

    def mutate(**_kwargs: object) -> dict[str, object]:
        Path(args.journal).write_text("{}\n", encoding="utf-8")
        return _report()

    monkeypatch.setattr(script, "build_hip3_shadow_lifecycle_replay", mutate)
    with pytest.raises(ValueError, match="prefix changed"):
        script.run_command(
            args,
            candle_fetcher=lambda *_args, **_kwargs: _candles(),
            funding_fetcher=lambda *_args, **_kwargs: _funding(),
            mark_source=_MarkSource(),
        )

    assert not Path(args.output).exists()


def test_existing_output_is_rejected_before_acquisition(tmp_path: Path) -> None:
    script = _script()
    args = _arguments(script, tmp_path)
    Path(args.output).write_text("reserved", encoding="utf-8")

    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        script.run_command(args, mark_source=_FailingMarkSource())


def test_parser_accepts_explicit_close_only_opposite_comparison(
    tmp_path: Path,
) -> None:
    """Keep close-only evaluation explicit and disabled by default."""
    script = _script()

    control = _arguments(script, tmp_path)
    comparison = _arguments(
        script, tmp_path / "comparison", extra=("--close-only-opposite-comparison",)
    )

    assert control.close_only_opposite_comparison is False
    assert comparison.close_only_opposite_comparison is True


def test_command_builds_an_explicit_archive_mark_repair_source(tmp_path: Path) -> None:
    script = _script()
    args = _arguments(script, tmp_path)
    args.archive_mark_repair_audit = tmp_path / "path-audit.json"
    args.archive_mark_repair_audit.write_text(
        json.dumps(
            {
                "schema_version": "hip3_prospective_path_audit_v1",
                "source": {"symbol": "xyz:MU"},
                "contract": {"report_only": True, "execution_authority": "none"},
                "bar_diagnostics": [
                    {
                        "bar_open_ms": 1_786_701_600_000,
                        "bar_close_ms": 1_786_702_500_000,
                        "mark": {"complete": False},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    source = script._configured_mark_source(args, _MarkSource())

    assert isinstance(source, ArchiveRepairingHip3MarkSource)


def test_route_config_mismatch_fails_before_public_acquisition(tmp_path: Path) -> None:
    script = _script()
    args = _arguments(script, tmp_path)
    diagnostic = json.loads(Path(args.development_diagnostic).read_text())
    diagnostic["diagnostic"]["track"]["config"]["fast_ema"] = 8
    Path(args.development_diagnostic).write_text(json.dumps(diagnostic))

    def no_network(*_args: object, **_kwargs: object) -> pd.DataFrame:
        raise AssertionError("public acquisition must not start")

    with pytest.raises(ValueError, match="signal config"):
        script.run_command(
            args,
            candle_fetcher=no_network,
            funding_fetcher=no_network,
            mark_source=_FailingMarkSource(),
        )


def test_sp500_command_config_matches_exact_v51_exit_contract() -> None:
    """Bind the production command to the active provider exit contract."""
    script = _script()
    args = argparse.Namespace(
        notional_usd=5_000.0,
        stress_extra_bps_per_side=2.0,
        maximum_book_lateness_ms=15_000,
        maximum_mark_gap_ms=5_000,
        execution_config=Path(
            "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
        ),
    )

    config = script._config(args, script._spec("xyz:SP500"), 0.864, 1.0)

    assert config.fixed_stop_bps == pytest.approx(80.0)
    assert config.maximum_hold_minutes == 1_440
    assert config.signal_exit_enabled is False
    assert config.opposite_entry_exit_enabled is True
    assert policy_declaration(config.profit_lock_policy) == {
        "policy_id": "v51_hip3_sp500_100_40_80",
        "activation_bps": 100.0,
        "floor_bps": 40.0,
        "trailing_giveback_bps": 80.0,
    }
    assert config.execution_profile_id == (
        "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51"
    )


def test_sp500_command_models_v61_short_only_control_without_opposite_exit() -> None:
    """Do not alias V61 observe-only longs into executable entries or exits."""
    script = _script()
    args = argparse.Namespace(
        notional_usd=1_750.0,
        stress_extra_bps_per_side=2.0,
        maximum_book_lateness_ms=15_000,
        maximum_mark_gap_ms=5_000,
        execution_config=Path(
            "configs/multi_asset_growth_first_5000_eight_asset_sndk_exit_preserved_candidate_v61.toml"
        ),
    )

    config = script._config(args, script._spec("xyz:SP500"), 0.864, 1.0)

    assert config.entry_sides == frozenset({"short"})
    assert config.opposite_entry_exit_enabled is False
    assert config.fixed_stop_bps == pytest.approx(80.0)
    assert config.notional_usd == pytest.approx(1_750.0)


def test_sp500_command_freezes_live_config_and_profit_lock_candles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Persist the exact exit source and completed one-minute lock path."""
    script = _script()
    args = _sp500_arguments(script, tmp_path)
    captured: dict[str, object] = {}
    timeframes: list[str] = []

    def replay(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return _sp500_report()

    def candles(*values: object, **_kwargs: object) -> pd.DataFrame:
        timeframes.append(str(values[1]))
        return _candles()

    monkeypatch.setattr(script, "build_hip3_shadow_lifecycle_replay", replay)
    report = script.run_command(
        args,
        candle_fetcher=candles,
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        mark_source=_MarkSource(),
    )

    persisted = json.loads(Path(args.output).read_text())
    assert report == persisted
    assert timeframes == ["15m", "1m"]
    config = captured["config"]
    assert config.fixed_stop_bps == pytest.approx(80.0)
    assert config.opposite_entry_exit_enabled is True
    assert captured["profit_lock_bars"] is not None
    execution = persisted["input_evidence"]["execution_config"]
    assert execution["path"].endswith("candidate_v51.toml")
    assert len(execution["sha256"]) == 64
    assert persisted["source_snapshots"]["profit_lock_candles"]


def test_sp500_command_rejects_unbound_exit_contract_before_acquisition(
    tmp_path: Path,
) -> None:
    """Do not silently replay a live-bound route with legacy exits."""
    script = _script()
    args = _sp500_arguments(script, tmp_path)
    args.execution_config = None

    def no_network(*_args: object, **_kwargs: object) -> pd.DataFrame:
        raise AssertionError("public acquisition must not start")

    with pytest.raises(ValueError, match="requires --execution-config"):
        script.run_command(
            args,
            candle_fetcher=no_network,
            funding_fetcher=no_network,
            mark_source=_FailingMarkSource(),
        )


def test_sp500_command_rejects_mutable_candle_refetch_before_acquisition(
    tmp_path: Path,
) -> None:
    """Live-bound signal and exit paths require frozen observer prefixes."""
    script = _script()
    args = _sp500_arguments(script, tmp_path)

    with pytest.raises(ValueError, match="frozen candle ledgers"):
        script.run_command(args, mark_source=_FailingMarkSource())


def _arguments(
    script: ModuleType,
    tmp_path: Path,
    *,
    extra: tuple[str, ...] = (),
) -> argparse.Namespace:
    tmp_path.mkdir(parents=True, exist_ok=True)
    journal = tmp_path / "journal.jsonl"
    books = tmp_path / "books.jsonl"
    diagnostic = tmp_path / "diagnostic.json"
    fee = tmp_path / "fee.json"
    journal.write_text(
        json.dumps(
            {
                "decision": {
                    "decision_time_ms": 1_800_000_900_000,
                    "observed_at_ms": 1_800_000_900_500,
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    books.write_text(
        json.dumps(
            {
                "event_type": "book_observation",
                "payload": {"recv_ts_ms": 1_800_000_901_000},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    diagnostic.write_text(json.dumps(_diagnostic()), encoding="utf-8")
    fee.write_text(json.dumps(_fee()), encoding="utf-8")
    return script.build_parser().parse_args(
        [
            "--symbol",
            "xyz:MU",
            "--journal",
            str(journal),
            "--book-ledger",
            str(books),
            "--development-diagnostic",
            str(diagnostic),
            "--fee-evidence",
            str(fee),
            "--observed-at-ms",
            "1800100000000",
            *extra,
            "--output",
            str(tmp_path / "report.json"),
        ]
    )


def _sp500_arguments(script: ModuleType, tmp_path: Path) -> argparse.Namespace:
    args = _arguments(script, tmp_path)
    args.symbol = "xyz:SP500"
    args.execution_config = Path(
        "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
    )
    journal = json.loads(Path(args.journal).read_text())
    journal["event_type"] = "sp500_hip3_breakout_shadow_decision"
    journal["decision"].update(
        {
            "symbol": "xyz:SP500",
            "provider_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
            "profile_id": "sp500_fresh15_pressure_shadow_research_v3",
        }
    )
    Path(args.journal).write_text(json.dumps(journal) + "\n", encoding="utf-8")
    book = json.loads(Path(args.book_ledger).read_text())
    book["profile_id"] = "index_fresh15_shadow_xyz:sp500"
    book["payload"]["symbol"] = "xyz:SP500"
    Path(args.book_ledger).write_text(json.dumps(book) + "\n", encoding="utf-8")
    Path(args.development_diagnostic).write_text(
        json.dumps(_sp500_diagnostic()), encoding="utf-8"
    )
    Path(args.fee_evidence).write_text(json.dumps(_sp500_fee()), encoding="utf-8")
    return args


class _MarkSource:
    def load(
        self, *, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        del data_root, start_ms, end_ms
        rows = tuple(
            {
                "symbol": symbol,
                "observed_ts_ms": value,
                "received_ts_ns": value * 1_000_000,
                "mark_price": 100.0,
                "source": "hyperliquid_ws_activeAssetCtx",
            }
            for value in (1_800_000_000_000, 1_800_000_001_000)
        )
        return rows, {"rows": len(rows), "files": []}

    def require_unchanged(self, evidence: dict[str, object]) -> None:
        assert evidence["rows"] == 2


class _FailingMarkSource:
    def load(self, **_kwargs: object) -> tuple[object, object]:
        raise AssertionError("acquisition must not start for an existing output")

    def require_unchanged(self, evidence: dict[str, object]) -> None:
        raise AssertionError(evidence)


def _candles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2027-01-15T08:00:00Z")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.0],
            "volume": [1.0],
            "source": ["hl"],
        }
    )


def _funding() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2027-01-15T08:00:00Z")],
            "funding_rate": [0.0],
            "source": ["hl_funding_history"],
        }
    )


def _report() -> dict[str, object]:
    return {
        "schema_version": "hip3_shadow_lifecycle_replay_v2",
        "symbol": "xyz:MU",
        "provider_id": "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1",
        "profile_id": "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def _sp500_report() -> dict[str, object]:
    report = _report()
    report.update(
        {
            "symbol": "xyz:SP500",
            "provider_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
            "profile_id": "sp500_fresh15_pressure_shadow_research_v3",
        }
    )
    return report


def _diagnostic() -> dict[str, object]:
    return {
        "schema_version": "mu_development_path_threshold_diagnostic_v1",
        "symbol": "xyz:MU",
        "execution_authority": "none",
        "automatic_promotion": False,
        "validation_accessed": False,
        "holdout_accessed": False,
        "qualification_abort_preserved": True,
        "diagnostic": {
            "track": {
                "provider_id": "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1",
                "profile_id": "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1",
                "timeframe": "15m",
                "family": "breakout_pressure",
                "config": {
                    "breakout_lookback_bars": 32,
                    "fast_ema": 9,
                    "slow_ema": 21,
                    "minimum_abs_imbalance": 0.1,
                    "maximum_stop_bps": 80.0,
                },
            }
        },
        "inputs": {"nominal_latency_bps_per_side": 1.0},
    }


def _fee() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "profile": {
            "symbol": "xyz:MU",
            "fees": {"one_way_taker_fee_bps": 0.864},
        },
    }


def _sp500_diagnostic() -> dict[str, object]:
    report = _diagnostic()
    report["symbol"] = "xyz:SP500"
    track = report["diagnostic"]["track"]
    track["provider_id"] = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
    track["profile_id"] = "sp500_fresh15_pressure_shadow_research_v3"
    track["config"] = {
        "breakout_lookback_bars": 32,
        "fast_ema": 21,
        "slow_ema": 55,
        "minimum_abs_imbalance": 0.1,
        "maximum_stop_bps": 120.0,
    }
    return report


def _sp500_fee() -> dict[str, object]:
    report = _fee()
    report["profile"]["symbol"] = "xyz:SP500"
    return report
