"""Full candidate-matrix screening and archive shortlist contracts."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypervector.cli import _verified_replay_archive, build_parser, main
from hypervector.data.oxa_archive_audit import OxaArchiveBundle
from hypervector.research.maker_replay_models import MakerReplayReport
from hypervector.research.hypervelocity_archive_compare import (
    screen_candidate_matrix,
    select_archive_shortlist,
)


def _bars(count: int = 1_800) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=count, freq="1min", tz="UTC")
    close = 100.0 + np.sin(np.arange(count) / 30.0) * 2.0
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.15,
            "low": close - 0.15,
            "close": close,
            "volume": 100.0 + (np.arange(count) % 11),
            "source": "hl",
        },
        index=index,
    )


def test_screen_retains_all_baseline_single_pair_and_full_results() -> None:
    bars = _bars()
    positions = pd.DataFrame(
        {
            "open_time_utc": [bars.index[900].isoformat()],
            "side": ["long"],
        }
    )

    screenings = screen_candidate_matrix(bars, positions)

    assert len(screenings) == 12
    assert len({result["candidate"]["fingerprint"] for result in screenings}) == 12
    assert all("regime" in result for result in screenings)
    assert all("barrier" in result for result in screenings)
    assert all("portfolio" in result for result in screenings)
    assert all("decision_fingerprint" in result for result in screenings)
    assert all("outcomes" not in result["barrier"] for result in screenings)


def test_shortlist_always_retains_controls_and_best_single_and_pair() -> None:
    bars = _bars()
    positions = pd.DataFrame(
        {
            "open_time_utc": [bars.index[900].isoformat()],
            "side": ["long"],
        }
    )

    screenings = screen_candidate_matrix(bars, positions)
    shortlist = select_archive_shortlist(screenings)
    identifiers = [item["candidate"]["candidate_id"] for item in shortlist]

    assert len(shortlist) == 4
    assert identifiers[0] == "pareto60_baseline"
    assert identifiers[1] == "bbwp_blueprint_full"
    assert identifiers[2].startswith("single_")
    assert identifiers[3].startswith("pair_")
    used = {str(item["decision_fingerprint"]) for item in shortlist[:3]}
    distinct_pair_exists = any(
        len(item["candidate"]["changed_groups"]) == 2
        and str(item["decision_fingerprint"]) not in used
        for item in screenings
    )
    if distinct_pair_exists:
        assert str(shortlist[3]["decision_fingerprint"]) not in used


def _replay_report(rule: str) -> MakerReplayReport:
    return MakerReplayReport(
        fill_rule=rule,
        snapshots=10,
        market_trade_prints=5 if rule == "trade-through" else 0,
        submitted_entries=2,
        entry_fills=1,
        expired_entries=1,
        canceled_entries=0,
        pending_orders=0,
        completed_trades=1,
        open_positions=0,
        initial_equity=10_000.0,
        final_equity=10_475.0,
        submission_times_utc=(),
        trades=(),
        lifecycles=(),
        limitations=(),
    )


def test_cli_writes_stamped_screening_and_l2_shortlist(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    bars = _bars()
    positions_path = tmp_path / "positions.csv"
    pd.DataFrame(
        {"open_time_utc": [bars.index[900].isoformat()], "side": ["long"]}
    ).to_csv(positions_path, index=False)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, 1, tzinfo=UTC)
    bundle = OxaArchiveBundle(start, end, None, None, 0, 0)
    monkeypatch.setattr(
        "hypervector.cli._load_bars",
        lambda _args: (bars.reset_index(names="timestamp"), {"source": "fixture"}),
    )
    monkeypatch.setattr(
        "hypervector.cli._verified_replay_archive",
        lambda _args: (bundle,),
    )
    monkeypatch.setattr(
        "hypervector.cli._archive_replay_reports",
        lambda _args, _decisions, _bundles: {
            rule: _replay_report(rule) for rule in ("touch", "through", "trade-through")
        },
    )
    output = tmp_path / "comparison.json"

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "hypervelocity-archive-compare",
            "--positions",
            str(positions_path),
            "--archive-start",
            start.isoformat(),
            "--archive-end",
            end.isoformat(),
            "--out",
            str(output),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload == persisted
    assert len(payload["screenings"]) == 12
    assert len(payload["shortlist"]) == 4
    assert set(payload["l2_replay"]) == {
        item["candidate"]["candidate_id"] for item in payload["shortlist"]
    }
    assert all(
        len(result["candidate"]["fingerprint"]) == 64
        for result in payload["l2_replay"].values()
    )
    assert all(
        result["execution_summary"]["liquidation_adjusted"] is True
        for result in payload["l2_replay"].values()
    )
    assert payload["limitations"]["funding"] == "not_available"
    assert payload["limitations"]["l2_drawdown"] == "event_marked_available"


def test_archive_compare_parser_can_use_shared_archive_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = "2026-01-01T00:00:00Z"
    end = "2026-01-01T01:00:00Z"
    args = build_parser().parse_args(
        [
            "hypervelocity-archive-compare",
            "--positions",
            "positions.csv",
            "--archive-start",
            start,
            "--archive-end",
            end,
            "--out",
            "comparison.json",
        ]
    )
    monkeypatch.setattr(
        "hypervector.data.oxa_archive_audit.verified_archive_bundles",
        lambda _config: (),
    )

    assert _verified_replay_archive(args) == ()
