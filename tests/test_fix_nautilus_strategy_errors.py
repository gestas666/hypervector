"""Strategy errors are technical failures: never ok:true with 0 orders."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.cli import main
from hypervector.data.sources import fixture_ohlcv
from hypervector.export.schema import ExportSchemaError
from hypervector.nautilus.config_stub import phase2_check_report
from hypervector.nautilus.errors import (
    Phase2IntentError,
    Phase2TechnicalFailure,
    UnknownStrategyError,
)
from hypervector.nautilus.runner import run_phase2_backtest
from nautilus_fix_support import (
    FIXTEST_RAISE_AFTER,
    register_fix_strategies,
    synth_ohlcv,
    write_export,
)


@pytest.fixture(autouse=True)
def _strategies() -> None:
    register_fix_strategies()


def _summaries(data_root: Path) -> list[Path]:
    return list((data_root / "nautilus" / "backtest").rglob("summary.json"))


@pytest.mark.parametrize("signal_mode", ["windowed", "auto", "precomputed"])
def test_builder_error_fails_the_run_without_success_summary(
    tmp_path: Path, signal_mode: str
) -> None:
    export_dir = write_export(
        tmp_path, strategy=FIXTEST_RAISE_AFTER, params={"max_rows": 40}
    )
    data_root = tmp_path / "data"
    with pytest.raises(Phase2IntentError) as info:
        run_phase2_backtest(
            export_dir=export_dir,
            data_root=data_root,
            ohlcv=synth_ohlcv(120),
            signal_mode=signal_mode,
        )
    assert "fixtest builder refuses" in str(info.value)
    assert info.value.strategy == FIXTEST_RAISE_AFTER
    assert info.value.first_error is not None
    assert _summaries(data_root) == []


def test_windowed_failure_reports_first_failing_bar(tmp_path: Path) -> None:
    export_dir = write_export(
        tmp_path, strategy=FIXTEST_RAISE_AFTER, params={"max_rows": 40}
    )
    with pytest.raises(Phase2IntentError) as info:
        run_phase2_backtest(
            export_dir=export_dir,
            data_root=tmp_path / "data",
            ohlcv=synth_ohlcv(120),
            signal_mode="windowed",
        )
    first = info.value.first_error
    assert isinstance(first, dict)
    assert first["bar"] == 41  # first window with more than 40 rows
    assert first["signal_source"] == "windowed"
    assert first["bar_open"].startswith("2026-01-01T10:00")


def test_hypervelocity_contract_violation_is_not_ok_with_zero_orders(
    tmp_path: Path,
) -> None:
    """Repro: leverage=20 hypervelocity export used to print ok:true, 0 orders."""
    export_dir = write_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
        params={"leverage": 20.0, "target_margin_pct": 12.0},
        timeframe="1m",
    )
    with pytest.raises(Phase2TechnicalFailure, match="leverage must be 30.0"):
        run_phase2_backtest(
            export_dir=export_dir,
            data_root=tmp_path / "data",
            ohlcv=fixture_ohlcv(n_bars=120, drift=2.0, wave_period=20),
        )


def test_engine_still_usable_after_a_failed_run(tmp_path: Path) -> None:
    bad = write_export(
        tmp_path / "bad", strategy=FIXTEST_RAISE_AFTER, params={"max_rows": 10}
    )
    with pytest.raises(Phase2IntentError):
        run_phase2_backtest(
            export_dir=bad,
            data_root=tmp_path / "data",
            ohlcv=synth_ohlcv(60),
            signal_mode="windowed",
        )
    good = write_export(tmp_path / "good")
    result = run_phase2_backtest(
        export_dir=good, data_root=tmp_path / "data", ohlcv=synth_ohlcv(200)
    )
    assert result.orders_count > 0


def test_unknown_strategy_is_refused_before_history_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_dir = write_export(tmp_path, strategy="no_such_strategy_xyz")

    def _no_history(*_a, **_k):  # pragma: no cover - must not be reached
        raise AssertionError("history must not load for an unknown strategy")

    monkeypatch.setattr(
        "hypervector.nautilus.runner.load_research_history", _no_history
    )
    with pytest.raises(UnknownStrategyError) as info:
        run_phase2_backtest(export_dir=export_dir, data_root=tmp_path / "data")
    assert isinstance(info.value, ExportSchemaError)
    assert "no_such_strategy_xyz" in info.value.errors[0]


def test_check_rejects_unknown_strategy(tmp_path: Path) -> None:
    export_dir = write_export(tmp_path, strategy="no_such_strategy_xyz")
    with pytest.raises(UnknownStrategyError):
        phase2_check_report(
            export_dir, data_root=tmp_path / "data", probe_nautilus=False
        )


def test_check_signal_probe_flags_rejected_params(tmp_path: Path) -> None:
    export_dir = write_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
        params={"leverage": 20.0, "target_margin_pct": 12.0},
        timeframe="1m",
    )
    report = phase2_check_report(
        export_dir, data_root=tmp_path / "data", probe_nautilus=False
    )
    assert report["ok"] is False
    assert report["signal_probe"]["ok"] is False
    assert "leverage must be 30.0" in report["signal_probe"]["error"]


def test_check_signal_probe_passes_valid_export(tmp_path: Path) -> None:
    export_dir = write_export(tmp_path)
    report = phase2_check_report(
        export_dir, data_root=tmp_path / "data", probe_nautilus=False
    )
    assert report["ok"] is True
    assert report["strategy_registered"] is True
    assert report["signal_probe"]["ok"] is True
    assert report["signal_probe"]["direction"] == "long"


def test_cli_run_reports_technical_failure_as_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    export_dir = write_export(
        tmp_path, strategy=FIXTEST_RAISE_AFTER, params={"max_rows": 40}
    )
    frame = synth_ohlcv(120)
    monkeypatch.setattr(
        "hypervector.nautilus.runner.load_research_history",
        lambda *_a, **_k: (frame, {}),
    )
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "nautilus",
            "run",
            "--export",
            str(export_dir),
            "--no-network",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert '"ok": true' not in captured.out
    err = json.loads(captured.err.strip().splitlines()[-1])
    assert err["ok"] is False
    assert err["error_type"] == "Phase2IntentError"
    assert "fixtest builder refuses" in err["error"]
