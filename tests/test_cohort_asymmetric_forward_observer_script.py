"""Tests for the bounded asymmetric forward-observer command."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_asymmetric_forward_observer.py"


def _load() -> ModuleType:
    """Load the command module without invoking its entry point."""
    spec = spec_from_file_location("cohort_asymmetric_forward_observer_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load asymmetric observer script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_binds_checkpoint_to_the_predeclared_journal(tmp_path: Path) -> None:
    """The report must derive its profile, run, and cutoff from strict sources."""
    module = _load()
    checkpoint = tmp_path / "checkpoint.json"
    journal = tmp_path / "journal.json"
    output = tmp_path / "observer.json"
    _write(checkpoint, _checkpoint())
    _write(journal, _journal())
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--journal",
            str(journal),
            "--out",
            str(output),
        ]
    )

    report = module.run(args)

    assert report["current_profile_fingerprint"] == "profile-v25"
    assert report["current_run_id"] == "run-v25"
    assert report["entry_cutoff_timestamp_ms"] == 1_000_000
    assert report["candidate"]["closed_trades"] == 1
    assert report["evidence"]["checkpoint"]["bytes"] == checkpoint.stat().st_size
    assert report["evidence"]["journal"]["bytes"] == journal.stat().st_size
    assert not output.exists()


def test_run_rejects_a_checkpoint_with_runtime_authority(tmp_path: Path) -> None:
    """The observer must consume only a report-only checkpoint projection."""
    module = _load()
    checkpoint = _checkpoint()
    checkpoint["checkpoint_contract"]["execution_authority"] = "hyperliquid_mainnet"
    checkpoint_path = tmp_path / "checkpoint.json"
    journal_path = tmp_path / "journal.json"
    _write(checkpoint_path, checkpoint)
    _write(journal_path, _journal())
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint_path),
            "--journal",
            str(journal_path),
            "--out",
            str(tmp_path / "observer.json"),
        ]
    )

    with pytest.raises(ValueError, match="checkpoint execution authority"):
        module.run(args)


def test_command_summary_excludes_route_level_details() -> None:
    """Console output must stay concise while the checkpoint keeps full evidence."""
    module = _load()
    report = {
        "evidence_state": "prospective_resolutions_observed",
        "source_counts": {"candidate_post_cutoff": 1},
        "candidate": _economics(route_payload="candidate-secret"),
        "excluded_symmetric_sides": _economics(route_payload="control-secret"),
    }

    summary = module.command_summary(report)
    rendered = json.dumps(summary, sort_keys=True)

    assert summary["candidate"]["closed_trades"] == 1
    assert "candidate-secret" not in rendered
    assert "control-secret" not in rendered


def _checkpoint() -> dict[str, object]:
    return {
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "audit": {
            "run": {
                "profile_fingerprint": "profile-v25",
                "run_id": "run-v25",
            },
            "trade_reflections": {
                "trades": [
                    {
                        "strategy_id": "range_onset_bidirectional_v1",
                        "symbol": "SOL",
                        "side": "short",
                        "source_profile_fingerprint": "profile-v25",
                        "source_run_id": "run-v25",
                        "entry": {"venue_timestamp_ms": 1_000_000},
                        "exit": {"venue_timestamp_ms": 1_000_010},
                        "fees_usd": 0.1,
                        "funding_usd": 0.0,
                        "net_pnl_usd": 1.0,
                        "net_return_on_margin_pct": 2.0,
                    }
                ]
            },
        },
    }


def _journal() -> dict[str, object]:
    return {
        "schema_version": 1,
        "hypothesis_id": "cohort-asymmetric-shared-portfolio",
        "revision_number": 1,
        "created_at_utc": "1970-01-01T00:16:40Z",
        "status": "candidate",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }


def _economics(*, route_payload: str) -> dict[str, object]:
    return {
        "closed_trades": 1,
        "wins": 1,
        "losses": 0,
        "breakeven": 0,
        "net_pnl_usd": 1.0,
        "fees_usd": 0.1,
        "funding_usd": 0.0,
        "profit_factor": None,
        "mean_return_on_margin_pct": 2.0,
        "median_return_on_margin_pct": 2.0,
        "largest_winner_usd": 1.0,
        "net_pnl_excluding_largest_winner_usd": 0.0,
        "by_route_side": {"route": route_payload},
    }


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
