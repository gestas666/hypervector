"""The canonical regime classification runs once per live bar, not per consumer."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from paper_fix_fixtures import faithful_profile, hl_bars, write_strict_export

from hypervector.paper.session import PaperSession


def _decisions(direction: str | None):
    calls = {"n": 0}

    def classify(frame: pd.DataFrame, config) -> pd.DataFrame:
        del config
        calls["n"] += 1
        n = len(frame)
        regime = "TREND_UP" if direction == "long" else "RANGE"
        return pd.DataFrame(
            {
                "primary_regime": [regime] * n,
                "breakout_direction": [None] * n,
                "structural_direction": [direction] * n,
                "entry_direction": [direction] * n,
                "state_1m": [regime] * n,
                "state_5m": [regime] * n,
                "context_15m": [regime] * n,
                "confidence": [0.7] * n,
                "reason": ["fixture"] * n,
            },
            index=frame.index,
        )

    return classify, calls


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize("direction", ["long", None])
def test_legacy_live_bar_classifies_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direction: str | None
) -> None:
    classify, calls = _decisions(direction)
    monkeypatch.setattr("hypervector.strategies.hypervelocity._classify_regimes", classify)
    export = write_strict_export(tmp_path, strategy="hypervelocity_1m_scalper_long")
    session = PaperSession(export_dir=export, data_root=tmp_path / "data")
    bars = hl_bars("2026-07-25T12:00:00Z", 6)
    session.warm_up(bars.iloc[:4])
    session.enable_live_telemetry()

    for _, bar in bars.iloc[4:].iterrows():
        before = calls["n"]
        session.on_bar(bar)
        assert calls["n"] - before == 1

    rows = _rows(session.decisions_path)
    observed = [row for row in rows if row["action"] == "regime_observation"]
    assert [row["entry_direction"] for row in observed] == [direction, direction]
    submits = [row for row in rows if row["action"] == "submit_entry"]
    # Entry permission still follows the single classification.
    assert bool(submits) is (direction == "long")


def test_event_profile_live_bar_classifies_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    classify, calls = _decisions(None)
    monkeypatch.setattr("hypervector.strategies.hypervelocity._classify_regimes", classify)
    export = write_strict_export(tmp_path, strategy="hypervelocity_1m_scalper_long")
    profile = faithful_profile(tmp_path, export)
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        execution_mode="shadow",
        hypervelocity_profile=profile,
    )
    session.activate_hypervelocity_event_runtime(
        observed_at="2026-07-25T12:03:30+00:00"
    )
    bars = hl_bars("2026-07-25T12:00:00Z", 6)
    session.warm_up(bars.iloc[:4])
    session.enable_live_telemetry()

    for _, bar in bars.iloc[4:].iterrows():
        before = calls["n"]
        session.on_bar(bar)
        assert calls["n"] - before == 1

    # A later buffer state is never served from the previous bar's memo.
    session.on_bar(hl_bars("2026-07-25T12:06:00Z", 1).iloc[0])
    assert calls["n"] == 3
