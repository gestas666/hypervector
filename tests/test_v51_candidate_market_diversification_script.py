"""Command tests for immutable v51 candidate-diversification evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "v51_candidate_market_diversification.py"
)


def _module() -> object:
    spec = spec_from_file_location(
        "v51_candidate_market_diversification_script", _SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frame(symbol: str) -> pd.DataFrame:
    timestamps = pd.date_range("2026-06-08", periods=121, freq="1h", tz="UTC")
    shift = float(sum(symbol.encode()) % 11)
    returns = 0.001 * np.sin(np.linspace(shift, shift + 15.0, 120))
    closes = 100.0 * np.cumprod(np.r_[1.0, 1.0 + returns])
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": 1.0,
            "source": "hl",
        }
    )


def test_command_fetches_exact_roster_and_publishes_immutable_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    calls: list[tuple[str, str, float, int | None]] = []

    def fake_fetch(
        symbol: str, timeframe: str, lookback_days: float, *, end_ms: int | None
    ) -> pd.DataFrame:
        calls.append((symbol, timeframe, lookback_days, end_ms))
        return _frame(symbol)

    monkeypatch.setattr(module, "fetch_hl_ohlcv_snapshot", fake_fetch)
    output = tmp_path / "report.json"
    argv = [
        "--start",
        "2026-06-08T00:00:00Z",
        "--end",
        "2026-06-13T01:00:00Z",
        "--minimum-shared-returns",
        "90",
        "--output",
        str(output),
    ]

    assert module.main(argv) == 0
    report = json.loads(output.read_text())
    assert report["coverage"]["shared_return_rows"] == 120
    assert report["contract"]["execution_authority"] == "none"
    assert set(report["provenance"]["generator_files"]) == {
        "pyproject.toml",
        "uv.lock",
        "scripts/v51_candidate_market_diversification.py",
        "src/hypervector/data/hl.py",
        "src/hypervector/data/oxa_storage.py",
        "src/hypervector/research/v51_candidate_market_diversification.py",
    }
    assert len(calls) == 8
    assert {call[0] for call in calls} == set(
        report["method"]["baseline_symbols"]
    ) | set(report["method"]["candidate_symbols"])
    assert all(call[1] == "1h" and call[3] is not None for call in calls)
    with pytest.raises(FileExistsError):
        module.main(argv)
    assert len(calls) == 8


def test_command_aborts_if_generator_changes_during_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    identities = iter(
        [
            {"script.py": {"sha256": "before", "bytes": 1}},
            {"script.py": {"sha256": "after", "bytes": 2}},
        ]
    )
    monkeypatch.setattr(module, "_generator_identity", lambda: next(identities))
    monkeypatch.setattr(
        module,
        "fetch_hl_ohlcv_snapshot",
        lambda symbol, timeframe, lookback_days, *, end_ms: _frame(symbol),
    )
    output = tmp_path / "changed.json"

    with pytest.raises(RuntimeError, match="generator changed"):
        module.main(
            [
                "--start",
                "2026-06-08T00:00:00Z",
                "--end",
                "2026-06-13T01:00:00Z",
                "--minimum-shared-returns",
                "90",
                "--output",
                str(output),
            ]
        )
    assert not output.exists()


def test_command_accepts_an_explicit_distinct_candidate_roster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    calls: list[str] = []

    def fake_fetch(
        symbol: str, timeframe: str, lookback_days: float, *, end_ms: int | None
    ) -> pd.DataFrame:
        del timeframe, lookback_days, end_ms
        calls.append(symbol)
        return _frame(symbol)

    monkeypatch.setattr(module, "fetch_hl_ohlcv_snapshot", fake_fetch)
    output = tmp_path / "xyz100.json"

    assert (
        module.main(
            [
                "--start",
                "2026-06-08T00:00:00Z",
                "--end",
                "2026-06-13T01:00:00Z",
                "--minimum-shared-returns",
                "90",
                "--baseline-symbol",
                "xyz:SP500",
                "--baseline-symbol",
                "xyz:SPCX",
                "--candidate-symbol",
                "xyz:XYZ100",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text())
    assert report["method"]["baseline_symbols"] == ["xyz:SP500", "xyz:SPCX"]
    assert report["method"]["candidate_symbols"] == ["xyz:XYZ100"]
    assert calls == ["xyz:SP500", "xyz:SPCX", "xyz:XYZ100"]
