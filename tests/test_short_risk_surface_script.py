"""Contract tests for the current short-tail risk surface."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_script() -> object:
    path = Path("scripts/hypervelocity_short_risk_surface.py")
    spec = importlib.util.spec_from_file_location("short_risk_surface", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("short risk-surface script could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_short_risk_surface_is_bounded_and_preserves_control() -> None:
    """Only the predeclared allocation/leverage alternatives are replayed."""
    module = _load_script()
    configs = module._configs(15_000.0, "trade-through")

    assert tuple(configs) == (
        "alloc35_lev30_control",
        "alloc25_lev30",
        "alloc35_lev25",
        "alloc35_lev20",
    )
    assert configs["alloc35_lev30_control"].margin_fraction == 0.35
    assert configs["alloc35_lev30_control"].leverage == 30.0
    assert configs["alloc25_lev30"].margin_fraction == 0.25
    assert configs["alloc35_lev25"].leverage == 25.0
    assert configs["alloc35_lev20"].leverage == 20.0
    assert all(config.target_margin_pct == 8.0 for config in configs.values())
    assert all(config.maximum_hold_seconds == 86_400.0 for config in configs.values())
    assert all(config.occupied_signal_policy == "ignore" for config in configs.values())


def test_short_risk_surface_contract_has_no_execution_authority() -> None:
    """The bounded comparison cannot silently alter runtime or ML authority."""
    module = _load_script()
    contract = module._contract(15_000.0, "trade-through")

    assert contract["execution_authority"] == "none"
    assert contract["runtime_strategy_changed"] is False
    assert contract["model_authority"] == "observe"
    assert contract["signal_changed"] is False
    assert contract["candidate_count"] == 4


def test_control_parity_rejects_a_changed_replay() -> None:
    """The risk surface fails if its control no longer reproduces upstream."""
    module = _load_script()

    with pytest.raises(
        ValueError,
        match=r"control replay mismatch.*final_equity.*15000\.0.*14999\.0",
    ):
        module._verify_control_parity(
            {"final_equity": 15_000.0},
            {"final_equity": 14_999.0},
        )


def test_control_parity_compares_json_array_shape() -> None:
    """In-memory tuples and persisted JSON arrays represent the same report."""
    module = _load_script()

    module._verify_control_parity(
        {"submission_times_utc": ("2026-07-01T00:00:00+00:00",)},
        {"submission_times_utc": ["2026-07-01T00:00:00+00:00"]},
    )


def test_control_parity_tolerates_only_negligible_float_drift() -> None:
    """Sub-nanodollar replay drift passes while economic drift still fails."""
    module = _load_script()

    module._verify_control_parity(
        {"final_equity": 10_824.368422362313},
        {"final_equity": 10_824.368422362571},
    )
    with pytest.raises(ValueError, match="control replay mismatch"):
        module._verify_control_parity(
            {"final_equity": 10_824.35},
            {"final_equity": 10_824.36},
        )


def test_control_loader_accepts_corrected_strict_tuned_artifact(
    tmp_path: Path,
) -> None:
    """The corrected five-minute-range control supersedes the old short key."""
    module = _load_script()
    path = tmp_path / "corrected-control.json"
    path.write_text(
        json.dumps(
            {
                "event_replays": {
                    "strict_tuned": {"completed_trades": 55},
                }
            }
        ),
        encoding="utf-8",
    )

    assert module._control_replay(path) == {"completed_trades": 55}
