"""Continuous segmented source-follow replay CLI contract."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from hypervector.research.source_follow_portfolio_models import SourceSignal


def _module() -> ModuleType:
    path = Path("scripts/hypervelocity_source_continuous_replay.py")
    spec = importlib.util.spec_from_file_location("source_continuous_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load source continuous replay script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_segment_validation_requires_chronological_nonoverlap() -> None:
    """A continuous portfolio cannot replay overlapping evidence windows."""
    module = _module()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = SimpleNamespace(start=start, end=start + timedelta(days=2))
    overlap = SimpleNamespace(
        start=start + timedelta(days=1),
        end=start + timedelta(days=3),
    )

    with pytest.raises(ValueError, match="chronological and non-overlapping"):
        module.validate_ordered_selections((first, overlap))


def test_continuous_contract_is_fixed_to_the_development_lead() -> None:
    """The command must not expose a hidden risk or threshold tuning grid."""
    module = _module()
    contract = module.experiment_contract()

    assert contract["minimum_signal_range_bps"] == 12.0
    assert contract["margin_fraction"] == 0.50
    assert contract["leverage"] == 30.0
    assert contract["gross_margin_target_pct"] == 8.0
    assert contract["execution_authority"] == "none"


def test_range_floor_control_is_explicit_and_report_only() -> None:
    """The no-floor control must be named and retain the execution contract."""
    module = _module()

    contract = module.experiment_contract(
        "short",
        "alloc35_lev30",
        "uniform",
        minimum_signal_range_bps=0.0,
    )
    args = module.parse_args(
        [
            "--database",
            "market.duckdb",
            "--artifact",
            "source.json",
            "--prices",
            "prices.parquet",
            "--funding",
            "funding.parquet",
            "--minimum-signal-range-bps",
            "0",
            "--out",
            "report.json",
        ]
    )

    assert contract["candidate"] == "source_follow_minrange0_continuous_v1"
    assert contract["minimum_signal_range_bps"] == 0.0
    assert contract["execution_authority"] == "none"
    assert args.minimum_signal_range_bps == 0.0


def test_long_direction_challenger_is_explicit_and_preserves_signal_evidence() -> None:
    """Direction isolation must alter only direction, not recorded timestamps."""
    module = _module()
    signals = (SourceSignal("2026-01-01T00:00:00+00:00"),)

    directed = module.with_signal_direction(signals, "long")
    contract = module.experiment_contract("long")

    assert directed[0].decision_time_utc == signals[0].decision_time_utc
    assert directed[0].direction == "long"
    assert contract["signal_direction"] == "long"
    assert contract["candidate"] == "source_follow_minrange12_continuous_v1"


def test_lev25_profile_preserves_margin_allocation_and_eight_percent_target() -> None:
    """The wider-liquidation challenger must change leverage, not target return."""
    module = _module()

    config = module.risk_config("alloc50_lev25")
    contract = module.experiment_contract("short", "alloc50_lev25")

    assert config.margin_fraction == 0.50
    assert config.leverage == 25.0
    assert config.target_price_fraction == pytest.approx(8.0 / 25.0 / 100.0)
    assert contract["risk_profile"] == "alloc50_lev25"
    assert contract["gross_margin_target_pct"] == 8.0


@pytest.mark.parametrize(
    ("profile", "margin_fraction"),
    [
        ("alloc25_lev30", 0.25),
        ("alloc35_lev30", 0.35),
        ("alloc40_lev30", 0.40),
    ],
)
def test_allocation_challengers_change_margin_without_changing_target(
    profile: str,
    margin_fraction: float,
) -> None:
    """Allocation challengers must preserve the frozen signal leverage and TP."""
    module = _module()

    config = module.risk_config(profile)
    contract = module.experiment_contract("short", profile)

    assert config.margin_fraction == margin_fraction
    assert config.leverage == 30.0
    assert config.target_price_fraction == pytest.approx(8.0 / 30.0 / 100.0)
    assert contract["minimum_signal_range_bps"] == 12.0
    assert contract["gross_margin_target_pct"] == 8.0
    assert contract["execution_authority"] == "none"


def test_weak_choppy_sizing_profile_is_explicitly_report_only() -> None:
    """The subtype challenger must retain signals and have no execution authority."""
    module = _module()

    contract = module.experiment_contract(
        "short",
        "alloc50_lev30",
        "weak_choppy_half",
    )

    assert contract["sizing_profile"] == "weak_choppy_half"
    assert contract["weak_choppy_allocation_multiplier"] == 0.5
    assert contract["execution_authority"] == "none"


def test_progress_line_exposes_segment_equity_and_signal_count() -> None:
    """Long production replays must expose useful bounded progress."""
    module = _module()
    segment = {
        "ending_equity": 16_250.25,
        "selected_signal_count": 9,
    }

    line = module.format_progress(3, 12, segment)

    assert line == "completed segment 3/12 signals=9 equity=$16250.25"


def test_frozen_continuous_replay_rejects_session_limited_artifact(
    tmp_path: Path,
) -> None:
    """The all-day lead must fail closed on the older session artifact family."""
    module = _module()
    artifact = tmp_path / "session.json"
    artifact.write_text(
        json.dumps(
            {
                "candidate_family": "btc_allocation_leverage_surface_v1",
                "fresh": {
                    "candidates": {
                        "alloc50_lev30": {
                            "event_outcomes": [
                                {"recipe_id": "follow_td_session_06_15_conf70"}
                            ]
                        }
                    }
                },
            }
        )
    )

    with pytest.raises(ValueError, match="all-day source artifact"):
        module.validate_frozen_artifact(artifact, "alloc50_lev30")
