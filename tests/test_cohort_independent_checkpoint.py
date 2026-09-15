"""Independent reporting retains shared evidence without copying broken totals."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

CONFIG = Path("configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml")


def _source() -> dict[str, object]:
    """Return one explicit same-profile source with previously incomplete totals."""
    config = load_multi_asset_live_config(CONFIG, mode="observe")
    return {
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "audit": {"run": {"run_id": "active", "profile_id": config.profile_id,
                          "profile_fingerprint": config.profile_fingerprint},
                  "execution": {"fills": 9}, "portfolio_archive": {"historical": True}},
        "venue_portfolio": {"status": "observed", "portfolio_value_usd": 4830.0},
        "research_sync": {"state": "healthy"},
    }


def test_independent_report_retains_shared_data_and_rebuilds_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the rebuilt execution reaches output; shared sections retain provenance."""
    module = import_module("hypervector.research.cohort_independent_checkpoint")
    source = _source()
    original = deepcopy(source)
    monkeypatch.setattr(module, "fresh_checkpoint_document", lambda *_a, **_k: source)
    received: dict[str, object] = {}

    def publish(_root: Path, _out: Path, **options: object) -> dict[str, object]:
        received.update(options)
        result = deepcopy(source)
        result["audit"]["execution"]["fills"] = 18
        return result

    monkeypatch.setattr(module, "publish_live_checkpoint", publish)
    result = module.publish_independent_checkpoint(
        source_path=tmp_path / "shared.json", destination=tmp_path / "new.json",
        config=load_multi_asset_live_config(CONFIG, mode="observe"), run_id="active",
    )
    assert result["audit"]["execution"]["fills"] == 18
    assert received["venue_portfolio"] == original["venue_portfolio"]
    assert received["portfolio_archive"] == original["audit"]["portfolio_archive"]
    assert received["research_sync"] == original["research_sync"]
    assert received["current_run_only"] is True
    assert result["shared_reporting_source"]["execution_authority"] == "none"
    assert source == original
    assert (tmp_path / "new.json").is_file()
    assert not (tmp_path / "shared.json").exists()


@pytest.mark.parametrize("issue", ["stale", "future", "missing", "wrong_run", "alias", "lost_section"])
def test_invalid_shared_evidence_cannot_replace_last_complete_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, issue: str,
) -> None:
    """Bad identity, clock, path or missing panes cannot publish success-shaped output."""
    module = import_module("hypervector.research.cohort_independent_checkpoint")
    source = _source()
    if issue in {"stale", "future"}:
        delta = -300 if issue == "stale" else 300
        source["generated_at_utc"] = (datetime.now(timezone.utc) + timedelta(seconds=delta)).isoformat()
    if issue == "wrong_run":
        source["audit"]["run"]["run_id"] = "other"
    monkeypatch.setattr(module, "fresh_checkpoint_document", lambda *_a, **_k: None if issue == "missing" else source)

    def publish(_root: Path, _out: Path, **_options: object) -> dict[str, object]:
        result = deepcopy(source)
        if issue == "lost_section":
            del result["audit"]["portfolio_archive"]
        return result

    monkeypatch.setattr(module, "publish_live_checkpoint", publish)
    destination = tmp_path / "retained.json"
    destination.write_text("prior complete report")
    shared = destination if issue == "alias" else tmp_path / "shared.json"
    with pytest.raises(ValueError):
        module.publish_independent_checkpoint(
            source_path=shared, destination=destination,
            config=load_multi_asset_live_config(CONFIG, mode="observe"), run_id="active",
        )
    assert destination.read_text() == "prior complete report"
