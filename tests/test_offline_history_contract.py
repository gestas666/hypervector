"""Explicit offline intent may not silently fall through to public APIs."""

from pathlib import Path

import pytest

from hypervector.data.pipeline import load_research_history


def test_cache_miss_fails_before_network_when_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing data is a technical error when the operator forbids network IO."""
    monkeypatch.setattr("hypervector.data.pipeline.live_hl_fetcher", lambda *_a: pytest.fail("network fetch in offline mode"))
    with pytest.raises(FileNotFoundError, match="offline.*cache"):
        load_research_history(tmp_path, lookback_days=30, allow_network=False)
