import pandas as pd

from hypervector.live.hulk_smash_live_config import load_hulk_smash_live_config
from hypervector.live.hulk_smash_live_decisions import (
    build_completed_hulk_decisions,
)


def test_completed_hulk_decisions_execute_only_exact_v3_short_selection() -> None:
    config = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="observe",
    )
    decisions = build_completed_hulk_decisions(
        _five_minute_bars(),
        observed_at=pd.Timestamp("2026-08-01T01:30:00Z"),
        config=config,
        component_builder=_empty_components,
        quality_builder=_empty_quality,
        signal_builder=_three_signals,
    )

    assert len(decisions) == 3
    assert decisions[0].decision_time_ms == 1_785_544_200_000
    assert decisions[0].entry_eligible is True
    assert decisions[0].decision_action == "enter_short"
    assert decisions[0].reason == "eligible"
    assert decisions[1].entry_eligible is False
    assert decisions[1].reason == "side_not_short"
    assert decisions[2].entry_eligible is False
    assert decisions[2].reason == "moderate_adx_not_present"
    assert all(decision.primary_regime == "NOT_CLASSIFIED" for decision in decisions)


def test_bidirectional_mode_preserves_long_and_short_hulk_signals() -> None:
    """The shared cohort may use Hulk signals without the legacy short filter."""
    config = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="observe",
    )

    decisions = build_completed_hulk_decisions(
        _five_minute_bars(),
        observed_at=pd.Timestamp("2026-08-01T01:30:00Z"),
        config=config,
        allowed_sides=frozenset({"long", "short"}),
        component_builder=_empty_components,
        quality_builder=_empty_quality,
        signal_builder=_three_signals,
    )

    assert decisions[0].signal_side == "short"
    assert decisions[0].decision_action == "enter_short"
    assert decisions[1].signal_side == "long"
    assert decisions[1].entry_eligible is True
    assert decisions[1].decision_action == "enter_long"


def test_completed_hulk_decisions_filter_history_and_incomplete_buckets() -> None:
    config = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="observe",
    )
    first = build_completed_hulk_decisions(
        _five_minute_bars(),
        observed_at=pd.Timestamp("2026-08-01T01:29:59Z"),
        config=config,
        component_builder=_empty_components,
        quality_builder=_empty_quality,
        signal_builder=_three_signals,
    )
    after = first[0].decision_time_ms
    unseen = build_completed_hulk_decisions(
        _five_minute_bars(),
        observed_at=pd.Timestamp("2026-08-01T01:30:00Z"),
        after_decision_time_ms=after,
        config=config,
        component_builder=_empty_components,
        quality_builder=_empty_quality,
        signal_builder=_three_signals,
    )

    assert len(first) == 2
    assert [decision.decision_time_ms for decision in unseen] == [
        1_785_546_000_000,
        1_785_547_800_000,
    ]


def test_hulk_readiness_does_not_treat_armed_squeeze_as_entry_trigger() -> None:
    """An armed squeeze without a release must report zero entry conditions."""
    config = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="observe",
    )

    decisions = build_completed_hulk_decisions(
        _five_minute_bars(),
        observed_at=pd.Timestamp("2026-08-01T01:30:00Z"),
        config=config,
        allowed_sides=frozenset({"long", "short"}),
        component_builder=_readiness_components,
        quality_builder=_readiness_quality,
        signal_builder=lambda *args, **kwargs: pd.DataFrame(),
    )

    readiness = decisions[-1].readiness
    assert readiness is not None
    assert readiness.side is None
    assert readiness.conditions_met == 0
    assert readiness.conditions_required == 4
    assert readiness.blockers == (
        "expansion_trigger_not_present",
        "moderate_adx_not_present",
        "signal_score_not_eligible",
        "entry_side_unavailable",
    )
    assert "EXPANSION TRIGGER NO" in readiness.indicators
    assert "MODERATE ADX EVIDENCE NO" in readiness.indicators
    assert "SCORE 0/7 NOT ELIGIBLE" in readiness.indicators
    assert "SIDE N/A / ALLOWED LONG+SHORT" in readiness.indicators
    assert "ADX 21.4/16.0" in readiness.indicators
    assert "SQUEEZE ARMED / RELEASE NO" in readiness.indicators
    assert readiness.metrics == {
        "adx": 21.4,
        "adx_usable": 16.0,
        "ema_trend": 1,
        "entry_candidate": "none",
        "entry_candidate_exact": False,
        "entry_contract": "hulk_expansion_moderate_adx_v1",
        "entry_moderate_adx_evidence": False,
        "entry_score": 0,
        "entry_score_eligible": False,
        "entry_score_minimum": 7,
        "entry_side_allowed": False,
        "heikin_ashi_choppy": False,
        "money_flow_direction": 1,
        "squeeze_on": True,
        "squeeze_release": False,
        "supertrend_direction": 1,
        "volume_ratio": 0.92,
    }


def _five_minute_bars() -> pd.DataFrame:
    times = pd.date_range("2026-08-01T00:00:00Z", periods=18, freq="5min")
    prices = [100.0 - index * 0.1 for index in range(len(times))]
    return pd.DataFrame(
        {
            "timestamp": times,
            "open": prices,
            "high": [price + 0.2 for price in prices],
            "low": [price - 0.2 for price in prices],
            "close": [price - 0.05 for price in prices],
            "volume": [10.0 + index for index in range(len(times))],
        }
    )


def _empty_components(
    bars: pd.DataFrame, root: object, *, bar_minutes: int
) -> pd.DataFrame:
    del root, bar_minutes
    return pd.DataFrame(index=bars.index)


def _empty_quality(bars: pd.DataFrame, **kwargs: object) -> pd.DataFrame:
    del kwargs
    return pd.DataFrame(index=bars.index)


def _readiness_components(
    bars: pd.DataFrame, root: object, *, bar_minutes: int
) -> pd.DataFrame:
    del root, bar_minutes
    index = pd.DatetimeIndex(bars["bar_open_at"])
    return pd.DataFrame(
        {
            "ema_trend": 1,
            "money_flow_direction": 1,
            "volume_ratio": 0.92,
        },
        index=index,
    )


def _readiness_quality(bars: pd.DataFrame, **kwargs: object) -> pd.DataFrame:
    del kwargs
    return pd.DataFrame(
        {
            "supertrend_direction": 1,
            "adx": 21.4,
            "squeeze_on": True,
            "squeeze_release": False,
            "ha_choppy": False,
        },
        index=bars.index,
    )


def _three_signals(
    bars: pd.DataFrame,
    components: pd.DataFrame,
    quality: pd.DataFrame,
    config: object,
) -> pd.DataFrame:
    del components, quality, config
    evidence = [
        ("squeeze_release", "supertrend", "ema_trend", "adx_usable"),
        ("squeeze_release", "supertrend", "ema_trend", "adx_usable"),
        ("squeeze_release", "supertrend", "ema_trend", "adx_trending"),
    ]
    count = len(bars)
    return pd.DataFrame(
        {
            "candidate": ["hulk_rebuilt_expansion_v1"] * count,
            "signal_time_utc": bars.index,
            "side": ["short", "long", "short"][:count],
            "score": [8, 9, 10][:count],
            "eligible": [True, True, True][:count],
            "reason": ["eligible"] * count,
            "trigger": ["squeeze_release"] * count,
            "evidence": evidence[:count],
            "stop_anchor": [100.2, 99.6, 99.0][:count],
        }
    )
