"""Contracts for immutable report-only live-audit prefix deltas."""

from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from cohort_live_audit_delta_fixtures import audit as _audit
from cohort_live_audit_delta_fixtures import (
    add_unchanged_attribution_pair as _add_unchanged_attribution_pair,
)
from cohort_live_audit_delta_fixtures import (
    audit_with_resolved_open_changes as _changed_audit,
)
from cohort_live_audit_delta_fixtures import episode_paths as _episode_paths
from cohort_live_audit_delta_fixtures import portfolio_dedup as _portfolio_dedup
from cohort_live_audit_delta_fixtures import signal_outcomes as _signal_outcomes


MODULE = Path("src/hypervector/research/cohort_live_audit_delta.py")
SCRIPT = Path("src/hypervector/operations/cohort_live_audit_delta.py")


def test_live_audit_delta_sources_exist() -> None:
    """The repeatable delta must have business logic and an operator command."""
    assert MODULE.is_file()
    assert SCRIPT.is_file()


def test_delta_separates_resolved_open_and_technical_changes() -> None:
    """Resolved economics must not be pooled with provisional open marks."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")
    after = _changed_audit()

    delta = build(before, after)

    assert delta["contract"] == {
        "automatic_promotion": False,
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
    }
    assert delta["identity"]["row_count_delta"] == 10
    assert delta["resolved_execution"]["closed_trades_delta"] == 1
    assert delta["resolved_execution"]["net_pnl_usd_delta"] == pytest.approx(-0.3)
    assert delta["resolved_execution"]["newly_closed_lifecycle_ids"] == ["SOL:2"]
    assert delta["technical_coverage"]["metric_value_gaps_delta"] == 2
    assert delta["technical_coverage"]["right_censored_observations_delta"] == -1
    _assert_open_lifecycle_delta(delta)
    assert delta["assessment"]["resolved_economic_change"] is True
    assert delta["assessment"]["journal_revision_recommended"] is True


def test_delta_reports_newly_matured_signal_and_one_blocker_paths() -> None:
    """Provider outcomes must expose captured and missed opportunity maturity."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")
    after = _audit(row_count=20, timestamp="2026-08-08T11:00:00+00:00")
    before["signal_outcomes"].update(_signal_outcomes(resolved=2, censored=2))
    after["signal_outcomes"].update(_signal_outcomes(resolved=4, censored=1))

    delta = build(before, after)

    signals = delta["signal_outcome_maturity"]
    assert signals["evaluations_delta"] == 2
    assert signals["eligible_evaluations_delta"] == 2
    assert signals["providers_added"] == []
    assert signals["providers_removed"] == []
    provider = signals["changed_providers"][0]
    assert provider["provider_symbol"] == "strategy-1|BTC"
    assert provider["horizons"]["5"] == {
        "censored_delta": -1,
        "cost_clearing_close_count_delta": 1,
        "cost_clearing_mfe_count_delta": 1,
        "failed_to_clear_cost_count_delta": 0,
        "independent_cost_clearing_close_count_delta": 1,
        "independent_cost_clearing_mfe_count_delta": 1,
        "independent_failed_to_clear_cost_count_delta": 0,
        "independent_reversed_after_cost_clear_count_delta": 1,
        "independent_robust_mfe_count_delta": 1,
        "non_overlapping_resolved_delta": 2,
        "resolved_delta": 2,
        "reversed_after_cost_clear_count_delta": 1,
        "robust_mfe_count_delta": 1,
    }
    blocker = provider["one_blocker_changes"][0]
    assert blocker["blocker"] == "expansion_trigger_not_present"
    assert blocker["evaluations_delta"] == 1
    assert blocker["horizons"]["5"]["resolved_delta"] == 1
    assert blocker["horizons"]["5"]["cost_clearing_mfe_count_delta"] == 1
    assert signals["newly_matured_paths"] is True
    assert delta["assessment"]["signal_outcome_maturity_change"] is True
    assert delta["assessment"]["journal_revision_recommended"] is False


def test_delta_reports_unique_portfolio_opportunity_maturity() -> None:
    """Prefix deltas must track deduplicated paths separately from providers."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")
    after = _audit(row_count=20, timestamp="2026-08-08T11:00:00+00:00")
    before["signal_outcomes"].update(_signal_outcomes(resolved=2, censored=2))
    after["signal_outcomes"].update(_signal_outcomes(resolved=4, censored=1))
    before_dedup = _portfolio_dedup(
        resolved=2,
        provider_observations=5,
        unique_paths=3,
    )
    after_dedup = _portfolio_dedup(
        resolved=4,
        provider_observations=9,
        unique_paths=5,
    )
    _add_unchanged_attribution_pair(before_dedup, after_dedup)
    before["signal_outcomes"]["portfolio_opportunity_dedup"] = before_dedup
    after["signal_outcomes"]["portfolio_opportunity_dedup"] = after_dedup

    delta = build(before, after)

    portfolio = delta["signal_outcome_maturity"]["portfolio_opportunity_maturity"]
    assert portfolio["comparable"] is True
    assert portfolio["provider_observations_delta"] == 4
    assert portfolio["unique_directional_paths_delta"] == 2
    assert portfolio["duplicate_provider_observations_removed_delta"] == 2
    assert portfolio["horizons"]["5"]["resolved_delta"] == 2
    assert portfolio["newly_matured_unique_paths"] is True
    episode_maturity = portfolio["episode_attribution_maturity"]
    assert episode_maturity["comparable"] is True
    assert episode_maturity["attributions_added"] == []
    assert episode_maturity["attributions_removed"] == []
    assert episode_maturity["newly_matured_episode_onsets"] is True
    _assert_episode_attribution_delta(episode_maturity)


def test_delta_labels_new_episode_attribution_as_not_yet_comparable() -> None:
    """A newly introduced episode schema must not invent historical maturity."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")
    after = _audit(row_count=20, timestamp="2026-08-08T11:00:00+00:00")
    before_dedup = _portfolio_dedup(
        resolved=2,
        provider_observations=5,
        unique_paths=3,
    )
    del before_dedup["by_attribution"]
    before["signal_outcomes"]["portfolio_opportunity_dedup"] = before_dedup
    after["signal_outcomes"]["portfolio_opportunity_dedup"] = _portfolio_dedup(
        resolved=4,
        provider_observations=9,
        unique_paths=5,
    )

    delta = build(before, after)

    portfolio = delta["signal_outcome_maturity"]["portfolio_opportunity_maturity"]
    assert portfolio["comparable"] is True
    assert portfolio["episode_attribution_maturity"] == {
        "comparable": False,
        "newly_available": True,
        "reason": "episode_attribution_absent_in_before_prefix",
    }


def test_delta_rejects_changed_resolved_episode_path() -> None:
    """A resolved episode's published economics must remain immutable."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")
    after = _audit(row_count=20, timestamp="2026-08-08T11:00:00+00:00")
    before_dedup = _portfolio_dedup(
        resolved=2,
        provider_observations=5,
        unique_paths=3,
    )
    after_dedup = _portfolio_dedup(
        resolved=2,
        provider_observations=5,
        unique_paths=3,
    )
    after_paths = _episode_paths(after_dedup)
    after_paths[0]["reference_price"] = 999.0
    before["signal_outcomes"]["portfolio_opportunity_dedup"] = before_dedup
    after["signal_outcomes"]["portfolio_opportunity_dedup"] = after_dedup

    with pytest.raises(ValueError, match="resolved episode path cannot change"):
        build(before, after)


def test_delta_rejects_disappearing_resolved_episode_path() -> None:
    """A resolved episode cannot vanish from a later prefix of the same run."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")
    after = _audit(row_count=20, timestamp="2026-08-08T11:00:00+00:00")
    before_dedup = _portfolio_dedup(
        resolved=2,
        provider_observations=5,
        unique_paths=3,
    )
    after_dedup = _portfolio_dedup(
        resolved=2,
        provider_observations=5,
        unique_paths=3,
    )
    _episode_paths(after_dedup).pop()
    before["signal_outcomes"]["portfolio_opportunity_dedup"] = before_dedup
    after["signal_outcomes"]["portfolio_opportunity_dedup"] = after_dedup

    with pytest.raises(ValueError, match="resolved episode path cannot disappear"):
        build(before, after)


def test_delta_labels_new_portfolio_measurement_as_not_yet_comparable() -> None:
    """A newly introduced audit field must not invent a historical delta."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")
    after = _audit(row_count=20, timestamp="2026-08-08T11:00:00+00:00")
    after["signal_outcomes"]["portfolio_opportunity_dedup"] = _portfolio_dedup(
        resolved=4,
        provider_observations=9,
        unique_paths=5,
    )

    delta = build(before, after)

    portfolio = delta["signal_outcome_maturity"]["portfolio_opportunity_maturity"]
    assert portfolio == {
        "comparable": False,
        "newly_available": True,
        "reason": "portfolio_dedup_absent_in_before_prefix",
    }


def test_delta_rejects_backward_signal_evaluation_counts() -> None:
    """Cumulative provider evaluation evidence cannot shrink within one run."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")
    after = _audit(row_count=20, timestamp="2026-08-08T11:00:00+00:00")
    before["signal_outcomes"].update(_signal_outcomes(resolved=4, censored=1))
    after["signal_outcomes"].update(_signal_outcomes(resolved=2, censored=2))

    with pytest.raises(ValueError, match="evaluations cannot move backwards"):
        build(before, after)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("run_id", "different-run", "same run_id"),
        ("profile_fingerprint", "b" * 64, "same profile_fingerprint"),
        ("row_count", 9, "row_count cannot move backwards"),
    ),
)
def test_delta_rejects_noncomparable_prefixes(
    field: str,
    value: str | int,
    message: str,
) -> None:
    """A delta must never compare unrelated or nonmonotonic evidence."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")
    after = _audit(row_count=11, timestamp="2026-08-08T11:00:00+00:00")
    after["run"][field] = value

    with pytest.raises(ValueError, match=message):
        build(before, after)


def test_command_publishes_exact_immutable_source_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The operator command must bind exact input bytes and refuse overwrite."""
    module = _load_script("cohort_live_audit_delta_command")
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    output = tmp_path / "delta.json"
    before_path.write_text(
        json.dumps(_audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")),
        encoding="utf-8",
    )
    after_path.write_text(
        json.dumps(_audit(row_count=11, timestamp="2026-08-08T11:00:00+00:00")),
        encoding="utf-8",
    )
    args = module.build_parser().parse_args(
        ["--before", str(before_path), "--after", str(after_path), "--out", str(output)]
    )

    report, published = module.publish(args)

    assert published == output
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["source_evidence"]["before"] == {
        "path": str(before_path),
        "sha256": sha256(before_path.read_bytes()).hexdigest(),
        "bytes": before_path.stat().st_size,
    }
    assert report["source_evidence"]["after"]["path"] == str(after_path)
    assert report["contract"]["execution_authority"] == "none"
    with pytest.raises(FileExistsError, match="immutable delta output exists"):
        module.publish(args)
    second_output = tmp_path / "delta-summary.json"
    assert (
        module.main(
            [
                "--before",
                str(before_path),
                "--after",
                str(after_path),
                "--out",
                str(second_output),
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["newly_matured_executable_bbo_episode_onsets"] is None
    assert summary["executable_bbo_path_identity_complete"] is None


def test_command_main_reports_refusal_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Expected operator errors must fail with one actionable message."""
    module = _load_script("cohort_live_audit_delta_main")
    source = tmp_path / "audit.json"
    output = tmp_path / "existing.json"
    source.write_text(
        json.dumps(_audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")),
        encoding="utf-8",
    )
    output.write_text("{}", encoding="utf-8")

    result = module.main(
        ["--before", str(source), "--after", str(source), "--out", str(output)]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "audit delta refused: immutable delta output exists" in captured.err
    assert "Traceback" not in captured.err


def _load_script(name: str) -> ModuleType:
    """Load the report-only script without invoking its entry point."""
    spec = spec_from_file_location(name, SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load script: {SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _assert_open_lifecycle_delta(delta: dict[str, object]) -> None:
    open_lifecycles = delta["open_lifecycles"]
    assert isinstance(open_lifecycles, dict)
    assert open_lifecycles["added"] == ["ETH:3"]
    assert open_lifecycles["removed"] == ["SOL:2"]
    assert open_lifecycles["removed_without_close"] == []
    matched = open_lifecycles["matched"]
    assert isinstance(matched, list)
    btc = matched[0]
    assert btc["lifecycle_id"] == "BTC:1"
    assert btc["marked_net_pnl_usd_delta"] == pytest.approx(0.05)
    assert btc["current_directional_return_bps_delta"] == 10.0
    assert btc["maximum_favorable_excursion_bps_delta"] == 5.0


def _assert_episode_attribution_delta(episode_maturity: object) -> None:
    assert isinstance(episode_maturity, dict)
    changed = episode_maturity["changed_attributions"]
    assert isinstance(changed, list)
    assert len(changed) == 1
    row = changed[0]
    assert row["identity"] == {
        "providers": [
            {
                "blocker": "expansion_trigger_not_present",
                "strategy_id": "strategy-1",
            }
        ],
        "side": "long",
        "source_run_id": "run-1",
        "symbol": "BTC",
    }
    assert row["path_groups_delta"] == 2
    assert row["decision_minutes_delta"] == 2
    assert row["episode_count_delta"] == 2
    horizon = row["horizons"]["5"]
    assert horizon["resolved_delta"] == 2
    assert horizon["independent_cost_clearing_close_count_delta"] == 1
    assert [item["decision_time_ms"] for item in horizon["new_independent_paths"]] == [
        120_001,
        180_001,
    ]
