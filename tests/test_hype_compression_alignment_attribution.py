"""Tests for frozen HYPE compression entry-relation attribution."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hype_compression_alignment_attribution import (
    FROZEN_HYPE_COMPRESSION_POLICY_ID,
    build_hype_compression_alignment_attribution,
)

_OPPOSED_LONG_LIFECYCLE = {
    "signal_time_utc": "2026-01-01T00:01:00+00:00",
    "entry_time_utc": "2026-01-01T00:01:00+00:00",
    "side": "long",
    "breakout_side_relation": "opposed",
    "net_return_bps": -20.0,
    "maximum_favorable_excursion_bps": 30.0,
    "maximum_adverse_excursion_bps": -6.0,
    "exit_reason": "protective_stop",
}


def _market(start: str, periods: int) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "entry_side": ["long", "long", "short", "short"][:periods],
            "breakout_side": ["long", "short", "short", "long"][:periods],
        },
        index=index,
    )


def _trade_rows(start: str, values: list[float]) -> pd.DataFrame:
    index = pd.date_range(start, periods=len(values), freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "policy_id": [FROZEN_HYPE_COMPRESSION_POLICY_ID] * len(values),
            "side": ["long", "long", "short", "short"][: len(values)],
            "signal_time_utc": [stamp.isoformat() for stamp in index],
            "entry_time_utc": [stamp.isoformat() for stamp in index],
            "net_return_bps": values,
            "maximum_favorable_excursion_bps": [20.0, 30.0, 40.0, 50.0][: len(values)],
            "maximum_adverse_excursion_bps": [-5.0, -6.0, -7.0, -8.0][: len(values)],
            "exit_reason": (["maximum_hold", "protective_stop"] * 2)[: len(values)],
        }
    )


def test_attribution_preserves_frozen_relations_sides_and_fold_stability() -> None:
    """Exact selected trades are partitioned without replaying or retuning them."""
    development = _market("2026-01-01", 4)
    confirmation = _market("2026-02-01", 2)
    confirmation_rows = _trade_rows("2026-02-01", [15.0, -5.0])
    confirmation_rows["censored"] = [False, False]

    report = build_hype_compression_alignment_attribution(
        development,
        _trade_rows("2026-01-01", [100.0, -20.0, 40.0, -10.0]),
        (confirmation,),
        confirmation_rows,
        frozen_policy_id=FROZEN_HYPE_COMPRESSION_POLICY_ID,
        fold_count=2,
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["selection_performed"] is False
    assert report["coverage"]["development"] == {
        "input_selected_rows": 4,
        "resolved_rows": 4,
        "censored_rows": 0,
    }
    development_report = report["segments"]["development"]
    assert development_report["by_relation"]["aligned"]["net_return_bps"] == 140.0
    assert development_report["by_relation"]["opposed"]["net_return_bps"] == -30.0
    assert (
        development_report["by_side_relation"]["long|aligned"][
            "net_excluding_largest_winner_bps"
        ]
        == 0.0
    )
    assert development_report["by_relation"]["aligned"]["fold_net_bps"] == [
        100.0,
        40.0,
    ]
    assert development_report["by_relation"]["aligned"]["positive_folds"] == 2
    assert development_report["lifecycles"][1] == _OPPOSED_LONG_LIFECYCLE
    assert (
        report["segments"]["later_confirmation"]["by_relation"]["opposed"]["trades"]
        == 1
    )


def test_attribution_rejects_trade_side_that_disagrees_with_source() -> None:
    """A source/trade direction mismatch cannot be silently relabeled."""
    market = _market("2026-01-01", 2)
    rows = _trade_rows("2026-01-01", [1.0, 2.0])
    rows.loc[0, "side"] = "short"

    with pytest.raises(ValueError, match="does not match market entry side"):
        build_hype_compression_alignment_attribution(
            market,
            rows,
            (),
            pd.DataFrame(),
            frozen_policy_id=FROZEN_HYPE_COMPRESSION_POLICY_ID,
            fold_count=2,
        )


def test_attribution_rejects_nonfrozen_policy_identity() -> None:
    """The diagnostic cannot become a hidden policy-selection surface."""
    market = _market("2026-01-01", 2)

    with pytest.raises(ValueError, match="frozen HYPE compression policy"):
        build_hype_compression_alignment_attribution(
            market,
            _trade_rows("2026-01-01", [1.0, 2.0]),
            (),
            pd.DataFrame(),
            frozen_policy_id="different_policy",
            fold_count=2,
        )
