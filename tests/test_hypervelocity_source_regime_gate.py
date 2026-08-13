from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.hypervelocity_source_regime_gate import (
    apply_source_regime_minimum_age,
    apply_source_regime_quality,
    apply_source_regime_agreement,
    bound_decision_grid,
    source_regime_agreement_grid,
    source_regime_interaction_grid,
    source_regime_quality_timing_grid,
)


def _script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_regime_gate.py")
    spec = importlib.util.spec_from_file_location("source_regime_gate_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load source-regime gate script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decisions() -> pd.DataFrame:
    index = pd.date_range("2026-07-28T00:00:00Z", periods=16, freq="1min")
    return pd.DataFrame(
        {
            "entry_direction": ["long"] * 14 + ["short"] * 2,
            "structural_direction": ["long"] * 14 + ["short"] * 2,
            "reason": ["eligible"] * 16,
        },
        index=index,
    )


def _labels() -> pd.DataFrame:
    index = pd.date_range("2026-07-28T00:00:00Z", periods=3, freq="5min")
    return pd.DataFrame(
        {
            "available_at": index + pd.Timedelta(minutes=5),
            "primary_code": ["TREND_UP", "RANGE", "BREAKOUT"],
            "secondary_code": [None, None, "BK_DOWNWARD"],
        },
        index=index,
    )


def test_source_gate_uses_only_labels_available_at_decision_time() -> None:
    result = apply_source_regime_agreement(_decisions(), _labels(), revision="strict")

    assert result.iloc[:4]["entry_direction"].isna().all()
    assert result.iloc[4]["entry_direction"] == "long"
    assert result.iloc[8]["entry_direction"] == "long"
    assert pd.isna(result.iloc[9]["entry_direction"])
    assert result.iloc[9]["reason"] == "source_regime_not_tradable"
    assert result.iloc[9]["source_regime_primary"] == "RANGE"


def test_source_gate_blocks_opposites_and_maps_breakout_direction() -> None:
    decisions = _decisions()
    decisions.iloc[4, decisions.columns.get_loc("entry_direction")] = "short"
    result = apply_source_regime_agreement(decisions, _labels(), revision="strict")

    assert pd.isna(result.iloc[4]["entry_direction"])
    assert result.iloc[4]["reason"] == "source_regime_direction_mismatch"
    assert result.iloc[4]["source_regime_direction"] == "long"
    assert result.iloc[14]["entry_direction"] == "short"
    assert result.iloc[14]["source_regime_direction"] == "short"


def test_source_quality_masks_only_weak_choppy_trends() -> None:
    decisions = _decisions().iloc[:4].copy()
    decisions["source_regime_secondary"] = [
        "TU_WEAK_CHOPPY",
        "TU_STRONG_LOW_VOL",
        "BK_UPWARD",
        None,
    ]

    result = apply_source_regime_quality(decisions)

    assert result["entry_direction"].tolist() == [None, "long", "long", "long"]
    assert result["source_regime_quality_wait"].tolist() == [True, False, False, False]
    assert decisions["entry_direction"].notna().all()


def test_source_minimum_age_delays_entry_without_changing_structure() -> None:
    decisions = _decisions().iloc[:7].copy()
    decisions["source_regime_primary"] = ["TREND_UP"] * 5 + ["RANGE"] * 2

    result = apply_source_regime_minimum_age(decisions, minimum_age_minutes=4)

    assert result["entry_direction"].tolist() == [
        None,
        None,
        None,
        None,
        "long",
        None,
        None,
    ]
    assert result["source_regime_age_minutes"].tolist() == [0, 1, 2, 3, 4, 0, 1]
    assert result["structural_direction"].tolist() == ["long"] * 7


def test_source_gate_rejects_noncausal_label_availability() -> None:
    labels = _labels()
    labels.loc[labels.index[0], "available_at"] = labels.index[0]

    with pytest.raises(ValueError, match="after its source bar"):
        apply_source_regime_agreement(_decisions(), labels, revision="strict")


def test_source_gate_grid_retains_unchanged_control() -> None:
    decisions = _decisions()
    result = source_regime_agreement_grid(
        decisions,
        {"strict": _labels(), "legacy": _labels()},
    )

    assert tuple(result) == (
        "canonical_control",
        "strict_source_agreement",
        "legacy_source_agreement",
    )
    pd.testing.assert_frame_equal(result["canonical_control"], decisions)


def test_decision_grid_is_bounded_after_causal_warmup() -> None:
    """Warmup rows may shape state but must not enter the scored replay window."""
    decisions = _decisions()
    grid = {"canonical_control": decisions}
    start = decisions.index[5].to_pydatetime()
    end = decisions.index[12].to_pydatetime()

    result = bound_decision_grid(grid, start=start, end=end)

    expected = decisions.iloc[5:12]
    pd.testing.assert_frame_equal(result["canonical_control"], expected)


def test_source_gate_replay_config_matches_runtime_cooldown() -> None:
    """Regime candidates must not inherit the older five-minute experiment."""
    module = _script()
    decisions = {
        "canonical_control": _decisions(),
        "strict_source_agreement": _decisions(),
    }

    configs = module._configs(decisions)

    assert set(configs) == set(decisions)
    assert {config.reentry_cooldown_seconds for config in configs.values()} == {60.0}
    assert {config.entry_ttl_seconds for config in configs.values()} == {300.0}
    assert {config.same_direction_reentry_policy for config in configs.values()} == {
        "regime_reset"
    }


def test_strict_stop25_comparison_changes_only_fixed_margin_stop() -> None:
    """The bounded tail-risk trial must retain one execution-identical control."""
    module = _script()
    configs = module._configs({}, strict_stop25=True)

    assert tuple(configs) == ("no_stop_control", "stop_25pct_margin")
    control, candidate = configs.values()
    assert control.fixed_margin_stop_pct is None
    assert candidate.fixed_margin_stop_pct == 25.0
    assert control.reentry_cooldown_seconds == 60.0
    assert candidate.reentry_cooldown_seconds == 60.0


def test_strict_control_only_replays_one_corrected_runtime_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gap-free label collection must not pay for rejected challenger lanes."""
    module = _script()
    monkeypatch.setattr(module, "classify_multitimeframe", lambda bars, config: bars)

    decisions = module._decisions(
        _decisions(),
        Path("configs/hypervelocity_faithful.toml"),
        {"strict": _labels(), "legacy": _labels()},
        hard_recovery_interaction=False,
        hard_recovery_wick_stop=False,
        strict_stop25=False,
        strict_quality_timing=False,
        strict_control_only=True,
    )

    assert tuple(decisions) == ("strict_source_control",)
    expected = apply_source_regime_agreement(_decisions(), _labels(), revision="strict")
    pd.testing.assert_frame_equal(decisions["strict_source_control"], expected)


def test_source_gate_interaction_retains_both_controls() -> None:
    canonical = _decisions()
    hard_recovery = canonical.copy()
    hard_recovery.iloc[4, hard_recovery.columns.get_loc("entry_direction")] = None
    result = source_regime_interaction_grid(
        canonical,
        hard_recovery,
        _labels(),
    )

    assert tuple(result) == (
        "canonical_control",
        "hard_bbwp_recovery6_control",
        "strict_source_agreement",
        "hard_bbwp_recovery6_strict_source_agreement",
    )
    pd.testing.assert_frame_equal(result["canonical_control"], canonical)
    pd.testing.assert_frame_equal(result["hard_bbwp_recovery6_control"], hard_recovery)
    assert pd.isna(
        result["hard_bbwp_recovery6_strict_source_agreement"].iloc[4]["entry_direction"]
    )


def test_source_quality_timing_grid_is_one_variable_per_challenger() -> None:
    grid = source_regime_quality_timing_grid(_decisions(), _labels())

    assert tuple(grid) == (
        "strict_source_control",
        "strict_source_no_weak_choppy",
        "strict_source_min_age4",
    )
    pd.testing.assert_frame_equal(
        grid["strict_source_control"],
        apply_source_regime_agreement(_decisions(), _labels(), revision="strict"),
    )
    assert "source_regime_quality_wait" in grid["strict_source_no_weak_choppy"]
    assert "source_regime_age_minutes" in grid["strict_source_min_age4"]
