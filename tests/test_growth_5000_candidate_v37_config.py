"""Contract tests for the non-activated $5,000 growth-sizing candidate."""

from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_CANDIDATE = Path("configs/multi_asset_bidirectional_growth_5000_candidate_v37.toml")
_ROSTER_BASELINE = Path(
    "configs/multi_asset_bidirectional_evidence_roster_canary_v36.toml"
)


def test_v37_changes_sizing_and_retires_gold_from_v36() -> None:
    """The growth candidate must preserve routes except the rejected GOLD asset."""
    baseline = load_multi_asset_live_config(_ROSTER_BASELINE, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")

    assert candidate.profile_id == "multi_asset_bidirectional_growth_5000_candidate_v37"
    assert candidate.network == baseline.network == "mainnet"
    assert candidate.margin_mode == baseline.margin_mode == "isolated"
    assert candidate.maximum_positions == baseline.maximum_positions == 10
    runtime_fields = ("cohort_ledger", "stop_file", "poll_seconds", "lookback_days")
    assert tuple(getattr(candidate, field) for field in runtime_fields) == tuple(
        getattr(baseline, field) for field in runtime_fields
    )
    assert candidate.symbols == tuple(
        symbol for symbol in baseline.symbols if symbol != "xyz:GOLD"
    )
    assert "xyz:GOLD" not in candidate.symbols
    assert all("xyz:GOLD" not in provider.symbols for provider in candidate.providers)
    assert all(
        "xyz:GOLD" not in provider.execution_symbols for provider in candidate.providers
    )
    assert candidate.executable_provider_symbols == {
        route
        for route in baseline.executable_provider_symbols
        if route[1] != "xyz:GOLD"
    }


@pytest.mark.parametrize(
    ("symbol", "venue_max_leverage", "maximum_hold_seconds"),
    [
        ("BTC", 40.0, 172800),
        ("ETH", 25.0, 172800),
        ("SOL", 20.0, 172800),
        ("HYPE", 10.0, 172800),
        ("xyz:SP500", 50.0, 86400),
        ("xyz:SPCX", 20.0, 86400),
        ("xyz:SNDK", 10.0, 86400),
        ("xyz:BRENTOIL", 20.0, 86400),
    ],
)
def test_v37_freezes_three_percent_isolated_slot_sizing(
    symbol: str,
    venue_max_leverage: float,
    maximum_hold_seconds: int,
) -> None:
    """Each occupied slot is 3% margin at 5x with a $750 notional ceiling."""
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    asset = {configured.symbol: configured for configured in candidate.assets}[symbol]

    assert asset.sides == frozenset({"long", "short"})
    assert asset.margin_fraction == pytest.approx(0.03)
    assert asset.leverage == pytest.approx(5.0)
    assert asset.max_notional_usd == pytest.approx(750.0)
    assert asset.venue_max_leverage == pytest.approx(venue_max_leverage)
    assert asset.stop_bps == pytest.approx(80.0)
    assert asset.maximum_hold_seconds == maximum_hold_seconds


def test_v37_remains_a_distinct_non_runtime_candidate() -> None:
    """The unified live CLI requires selection rather than promoting a research candidate."""
    from hypervector.cli import build_parser

    args = build_parser().parse_args(["cohort", "live"])
    assert args.config is None
    launcher = Path("src/hypervector/operations/multi_asset_bidirectional_live.py").read_text()
    assert _CANDIDATE.name not in launcher
