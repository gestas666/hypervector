"""Reproducible Hypervelocity regime-candidate contracts."""

import tomllib
from dataclasses import asdict
from pathlib import Path

from hypervector.regime.hypervelocity_candidates import (
    hypervelocity_candidate_matrix,
)
from hypervector.strategies.hypervelocity_contract import faithful_regime_config


def test_candidate_matrix_covers_baseline_singles_pairs_and_full_blueprint() -> None:
    candidates = hypervelocity_candidate_matrix()

    assert len(candidates) == 12
    assert len({candidate.candidate_id for candidate in candidates}) == 12
    assert {len(candidate.changed_groups) for candidate in candidates} == {0, 1, 2, 4}
    assert sum(len(candidate.changed_groups) == 1 for candidate in candidates) == 4
    assert sum(len(candidate.changed_groups) == 2 for candidate in candidates) == 6


def test_baseline_candidate_reproduces_saved_pareto60_parameters() -> None:
    baseline = hypervelocity_candidate_matrix()[0]
    config = asdict(baseline.config)

    assert baseline.candidate_id == "pareto60_baseline"
    assert baseline.changed_groups == ()
    assert (config["ema_fast"], config["ema_slow"]) == (20, 50)
    assert config["range_filter"] == "choppiness"
    assert config["choppiness_length"] == 14
    assert config["choppiness_range_threshold"] == 85.0
    assert config["breakout_clearance_bps"] == 5.0
    assert config["breakout_volume_multiple"] == 2.0


def test_full_candidate_equals_faithful_bbwp_runtime_and_is_fingerprinted() -> None:
    full = hypervelocity_candidate_matrix()[-1]

    assert full.candidate_id == "bbwp_blueprint_full"
    assert full.config == faithful_regime_config()
    assert full.config.range_filter == "bbwp"
    assert full.changed_groups == ("ema", "range_filter", "clearance", "volume")
    assert len(full.fingerprint) == 64
    assert full.fingerprint == full.recomputed_fingerprint()


def test_candidate_fingerprints_change_with_parameter_groups() -> None:
    candidates = hypervelocity_candidate_matrix()

    assert len({candidate.fingerprint for candidate in candidates}) == len(candidates)


def test_saved_ema_candidate_is_research_only_and_exact() -> None:
    candidate = next(
        item
        for item in hypervelocity_candidate_matrix()
        if item.candidate_id == "single_ema"
    )
    path = Path("configs/research/hypervelocity_ema21_55_candidate.toml")

    with path.open("rb") as handle:
        saved = tomllib.load(handle)

    assert saved["candidate"]["candidate_id"] == candidate.candidate_id
    assert saved["candidate"]["runtime_promoted"] is False
    assert saved["candidate"]["fingerprint"] == candidate.fingerprint
    assert saved["regime"] == asdict(candidate.config)
