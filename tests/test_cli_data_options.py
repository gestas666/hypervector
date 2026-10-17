"""Public research flags must govern the underlying data acquisition policy."""

from pathlib import Path

import pytest

from hypervector.cli import main


class HistoryBoundaryReached(RuntimeError):
    """Stop before expensive business logic once the data policy is observed."""


@pytest.mark.parametrize(
    ("command", "loader"),
    [
        (["research", "backtest"], "hypervector.data.pipeline.load_research_history"),
        (["research", "autotune"], "hypervector.sweep.autotune.load_research_history"),
        (
            ["data", "book-align", "--book-path", "fixture.jsonl"],
            "hypervector.data.pipeline.load_research_history",
        ),
        (["regime", "eval"], "hypervector.data.pipeline.load_research_history"),
    ],
)
def test_history_flags_reach_the_acquisition_boundary(
    command: list[str],
    loader: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force refresh and venue-only selection cannot be silently ignored."""
    observed: dict[str, object] = {}

    def capture(_root: object, **kwargs: object) -> None:
        observed.update(kwargs)
        raise HistoryBoundaryReached

    monkeypatch.setattr(loader, capture)
    with pytest.raises(HistoryBoundaryReached):
        main(["--data-root", str(tmp_path), *command, "--strict-hl-only", "--force"])
    assert observed.get("strict_hl_only") is True
    assert observed.get("force_refresh") is True
