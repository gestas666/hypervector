"""V94 strong-short Donchian identity: weak short breakdowns skipped, all else equal.

The rule passed its pre-registered re-score (docs/plans/2026-09-24-v94-review-
actions.md, "Pre-registered bar"): a Donchian 20/10 short is entered only when
(prior 20-bar low - signal close) / ATR20 >= 1.0. Longs, exits, recipe exits and
structural stops stay identical to the v1 identity, which must not change.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypervector.live.configured_canonical_regime import (
    configured_canonical_regime_symbols,
)
from hypervector.live.hourly_price_evidence import hourly_price_evidence_rows
from hypervector.live.hourly_price_provider import (
    DONCHIAN20_STRATEGY,
    HOURLY_PRICE_STRATEGIES,
    PROTECTED_DONCHIAN20_STRATEGY,
    STRONG_SHORT_DONCHIAN20_STRATEGY,
    STRONG_SHORT_MINIMUM_EXTENSION_ATR,
    HourlyPriceCollector,
    build_hourly_price_signals,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    load_multi_asset_live_config,
    validate_multi_asset_live_config,
)
from hypervector.live.multi_asset_polling_contract import (
    READINESS_SEED_LOOKBACK_MINUTES,
    SOURCE_TIMEFRAMES,
)
from hypervector.live.multi_asset_strategy_evidence import strategy_research_evidence
from hypervector.research.cohort_friction_contract_recent import (
    v89_hourly_modeled_contracts,
    v90_hourly_modeled_contracts,
    v94_strong_short_modeled_contracts,
)
from hypervector.research.cohort_friction_contracts import (
    contract_mismatches,
    modeled_contract,
    runtime_contract,
)
from hypervector.research.donchian_atr_breakout_signals import (
    DonchianAtrBreakoutConfig,
    build_donchian_atr_breakout_signals,
    build_donchian_atr_breakout_state,
)
from hypervector.research.v92_entry_candidates import build_v92_signals
from test_hourly_price_provider import _bars as provider_bars

STRONG = "hourly_donchian_20_10_atr20_strong_short_v1"
V93 = Path("configs/multi_asset_growth_first_5000_exit_v2_v93_proposal.toml")
V93_FINGERPRINT = "33131f1898d86dda4f5cab2b6091748144f6a81da29b9c9464a644b330dc3e05"
DONCHIAN_ROUTES = ("SOL", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA")
RESCORE = Path("docs/research-journal/v94-weak-short-rescore-20260924-v1.json")
# Completed hourly closes: a weak short (0.49 ATR) at hour 25, a continuation
# that is deeper but not fresh, a long, a strong short (2.43 ATR) and a long.
HOURLY_CLOSES = (
    [100.0] * 25
    + [99.0, 95.0, 101.0, 100.0]
    + [100.0] * 3
    + [90.0, 97.0, 100.0, 110.0, 103.0, 100.0]
)
WEAK_SHORT = pd.Timestamp("2026-01-02T01:45Z")
STRONG_SHORT = pd.Timestamp("2026-01-02T08:45Z")
# sha256 of the v1 identity's signal frame, pinned before V94 touched the builder.
V1_FIXTURE_DIGEST = "99b68f4105cd54fb8aa7535e27945a693ed6ca1c91922a27e753e242d2050133"
V1_PROVIDER_DIGEST = "fcecc565ec2ef8555855bf38eff3021a7b42e304b5ce346d4e8a7c07a3192182"


def _bars() -> pd.DataFrame:
    values = np.repeat(HOURLY_CLOSES, 4)
    return pd.DataFrame(
        {
            "open": values,
            "high": values + 0.5,
            "low": values - 0.5,
            "close": values,
            "volume": 10.0,
        },
        index=pd.date_range("2026-01-01", periods=len(values), freq="15min", tz="UTC"),
    )


def _digest(frame: pd.DataFrame) -> str:
    hashed = pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes()
    return hashlib.sha256(hashed).hexdigest()


def _short_extension(signals: pd.DataFrame, bars: pd.DataFrame) -> pd.Series:
    rows = signals.index[signals.short_entry]
    return (
        signals.loc[rows, "prior_entry_low"] - bars.loc[rows, "close"]
    ) / signals.loc[rows, "atr"]


def test_identity_is_registered_with_the_pre_registered_threshold() -> None:
    """The name is exact and the threshold is the 1.0 ATR fixed before the re-score."""
    assert STRONG_SHORT_DONCHIAN20_STRATEGY == STRONG
    assert STRONG_SHORT_MINIMUM_EXTENSION_ATR == 1.0
    assert STRONG in HOURLY_PRICE_STRATEGIES
    assert DONCHIAN20_STRATEGY in HOURLY_PRICE_STRATEGIES


def test_v1_identity_output_is_byte_identical_to_before_v94() -> None:
    """The shared builder change leaves every existing hourly identity untouched."""
    fixture = build_hourly_price_signals(_bars(), DONCHIAN20_STRATEGY)
    assert _digest(fixture) == V1_FIXTURE_DIGEST
    assert fixture.signal_name.iloc[0] == "completed_1h_donchian_20_10_atr20_stop_v1"
    provider = build_hourly_price_signals(
        provider_bars().set_index("timestamp"), DONCHIAN20_STRATEGY
    )
    assert _digest(provider) == V1_PROVIDER_DIGEST
    pd.testing.assert_frame_equal(
        build_hourly_price_signals(_bars(), PROTECTED_DONCHIAN20_STRATEGY), fixture
    )


def test_weak_shorts_are_skipped_and_everything_else_is_identical() -> None:
    """Only the weak short's entry, direction, stop and source time differ."""
    bars = _bars()
    base = build_hourly_price_signals(bars, DONCHIAN20_STRATEGY)
    strong = build_hourly_price_signals(bars, STRONG)
    extension = _short_extension(base, bars)
    weak = extension.index[extension < 1.0]
    assert weak.tolist() == [WEAK_SHORT]
    assert extension.index[extension >= 1.0].tolist() == [STRONG_SHORT]
    assert base.long_entry.sum() == 2

    expected = base.copy()
    expected.loc[weak, "short_entry"] = False
    expected.loc[weak, "entry_direction"] = base.entry_direction.iloc[0]
    expected.loc[weak, "stop_price"] = np.nan
    expected.loc[weak, "donchian_signal_bar_open"] = pd.NaT
    expected["signal_name"] = "completed_1h_donchian_20_10_atr20_stop_short_ext1atr_v1"
    pd.testing.assert_frame_equal(strong, expected)
    # The breakdown still closes an open long: the 20-bar low lies below the
    # 10-bar exit low, so the recipe exit does not depend on the entry.
    assert strong.loc[WEAK_SHORT, "long_exit"]
    assert strong.long_entry.equals(base.long_entry)
    assert (
        strong.loc[STRONG_SHORT, "stop_price"] == base.loc[STRONG_SHORT, "stop_price"]
    )


def test_deeper_continuation_after_a_skipped_weak_short_is_not_a_fresh_entry() -> None:
    """Skipping never manufactures a later entry the v1 identity would not take."""
    bars = _bars()
    strong = build_hourly_price_signals(bars, STRONG)
    continuation = WEAK_SHORT + pd.Timedelta(hours=1)
    assert bars.loc[continuation, "close"] == 95.0
    assert not strong.loc[continuation, "short_entry"]
    assert strong.index[strong.short_entry].tolist() == [STRONG_SHORT]


def test_live_identity_reproduces_the_re_scored_research_rule() -> None:
    """Entries equal the V92 research frame with the re-score's weak shorts removed."""
    bars = _bars()
    research = build_v92_signals(bars, "donchian")
    weak = research.short_entry & (research.entry_extension_atr < 1.0)
    assert weak.sum() == 1
    kept = research.loc[(research.long_entry | research.short_entry) & ~weak]
    strong = build_hourly_price_signals(bars, STRONG)
    entries = strong.loc[
        (strong.long_entry | strong.short_entry) & np.isfinite(strong.stop_price)
    ]
    assert entries.index.equals(kept.index)
    assert entries.entry_direction.tolist() == kept.entry_direction.tolist()
    np.testing.assert_allclose(entries.stop_price, kept.stop_price, rtol=0, atol=0)


def test_collector_withholds_only_the_weak_short_intent() -> None:
    """Published intents are the v1 intents minus weak shorts; exits are unchanged."""
    frame = _bars().reset_index(names="timestamp")
    observed = frame.timestamp.iloc[-1] + pd.Timedelta(minutes=15)

    def collect(strategy: str):
        return HourlyPriceCollector(strategy_id=strategy)(
            frame,
            symbol="xyz:SNDK",
            observed_at=observed,
            after_decision_time_ms=None,
        )

    base, strong = collect(DONCHIAN20_STRATEGY), collect(STRONG)
    weak_ms = int((WEAK_SHORT + pd.Timedelta(minutes=15)).timestamp() * 1000)
    assert [
        (intent.decision_time_ms, intent.side, intent.stop_anchor)
        for intent in strong.intents
    ] == [
        (intent.decision_time_ms, intent.side, intent.stop_anchor)
        for intent in base.intents
        if intent.decision_time_ms != weak_ms
    ]
    assert {intent.side for intent in strong.intents} == {"long", "short"}
    assert all(intent.strategy_id == STRONG for intent in strong.intents)
    for left, right in zip(base.evaluations, strong.evaluations, strict=True):
        assert left.decision_time_ms == right.decision_time_ms
        assert left.exit_sides == right.exit_sides
        if left.decision_time_ms == weak_ms:
            assert left.eligible and left.side == "short"
            assert not right.eligible and right.side is None
            assert right.reason == "hourly_price_exit"
        else:
            assert (left.eligible, left.side, left.reason) == (
                right.eligible,
                right.side,
                right.reason,
            )


def test_threshold_boundary_keeps_an_exact_one_atr_breakdown() -> None:
    """The comparison is >= 1.0: a breakdown of exactly one ATR is entered."""
    bars = _bars()
    state_bars = bars.resample("1h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    base = build_donchian_atr_breakout_state(
        state_bars, DonchianAtrBreakoutConfig(signal_hours=1)
    )
    extension = (base.prior_entry_low - state_bars.close) / base.atr
    target = float(extension.loc[STRONG_SHORT.floor("1h")])
    at_threshold = build_donchian_atr_breakout_state(
        state_bars,
        DonchianAtrBreakoutConfig(signal_hours=1, minimum_short_extension_atr=target),
    )
    above = build_donchian_atr_breakout_state(
        state_bars,
        DonchianAtrBreakoutConfig(
            signal_hours=1, minimum_short_extension_atr=math.nextafter(target, 99.0)
        ),
    )
    assert at_threshold.short_entry.loc[STRONG_SHORT.floor("1h")]
    assert not above.short_entry.loc[STRONG_SHORT.floor("1h")]
    assert np.isnan(above.stop_price.loc[STRONG_SHORT.floor("1h")])
    assert above.long_entry.equals(base.long_entry)
    pd.testing.assert_frame_equal(
        above.drop(columns=["short_entry", "stop_price"]),
        base.drop(columns=["short_entry", "stop_price"]),
    )


@pytest.mark.parametrize("value", [0.0, -1.0, math.nan, math.inf, True])
def test_invalid_short_extension_threshold_fails_closed(value: float) -> None:
    """A mistyped threshold is a configuration error, never a silent pass-through."""
    with pytest.raises(ValueError, match="short extension"):
        DonchianAtrBreakoutConfig(signal_hours=1, minimum_short_extension_atr=value)


def test_default_config_carries_no_short_filter() -> None:
    """Every existing caller keeps the unfiltered recipe by default."""
    assert DonchianAtrBreakoutConfig().minimum_short_extension_atr is None
    bars = _bars()
    default = build_donchian_atr_breakout_signals(
        bars, DonchianAtrBreakoutConfig(signal_hours=1)
    )
    pd.testing.assert_frame_equal(
        default, build_hourly_price_signals(bars, DONCHIAN20_STRATEGY)
    )


def _strong_config():
    config = load_multi_asset_live_config(V93, mode="observe")
    donchian = next(p for p in config.providers if p.strategy_id == DONCHIAN20_STRATEGY)
    strong = replace(donchian, strategy_id=STRONG)
    return config, replace(
        config,
        providers=tuple(strong if p is donchian else p for p in config.providers),
    )


def test_live_registries_accept_the_identity_on_the_v93_route_shape() -> None:
    """Validator, polling contract, collector and regime scope all accept it."""
    original, config = _strong_config()
    validate_multi_asset_live_config(config)
    assert original.profile_fingerprint == V93_FINGERPRINT
    assert config.profile_fingerprint != V93_FINGERPRINT
    provider = next(p for p in config.providers if p.strategy_id == STRONG)
    assert set(provider.execution_symbols) == set(DONCHIAN_ROUTES)
    assert SOURCE_TIMEFRAMES[STRONG] == SOURCE_TIMEFRAMES[DONCHIAN20_STRATEGY]
    assert (
        READINESS_SEED_LOOKBACK_MINUTES[STRONG]
        == READINESS_SEED_LOOKBACK_MINUTES[DONCHIAN20_STRATEGY]
    )
    collector = build_default_collector(provider, config, Path("unused"))
    assert isinstance(collector, HourlyPriceCollector)
    assert set(DONCHIAN_ROUTES) <= set(configured_canonical_regime_symbols(config))


@pytest.mark.parametrize(
    "change",
    [
        {
            "adaptive_exit_policy": "none",
            "profit_lock_policy": "completed_bar_trailing",
            "profit_lock_activation_bps": 100.0,
            "profit_lock_floor_bps": 25.0,
            "profit_lock_giveback_bps": 50.0,
        },
        {"maximum_stop_bps": 251.0},
        {"provider_recipe_exit_policy": "ignore"},
    ],
)
def test_identity_inherits_the_exact_hourly_contract(change: dict) -> None:
    """The new name cannot carry a different execution shape than the v1 route."""
    _, config = _strong_config()
    provider = next(p for p in config.providers if p.strategy_id == STRONG)
    invalid = replace(provider, execution=replace(provider.execution, **change))
    with pytest.raises(ValueError, match="hourly price"):
        validate_multi_asset_live_config(
            replace(
                config,
                providers=tuple(
                    invalid if p is provider else p for p in config.providers
                ),
            )
        )


def test_identity_refuses_a_single_side_scope() -> None:
    """Longs are unchanged, so the identity stays bidirectional like its parent."""
    _, config = _strong_config()
    provider = next(p for p in config.providers if p.strategy_id == STRONG)
    short_only = replace(provider, sides=frozenset({"short"}))
    with pytest.raises(ValueError):
        validate_multi_asset_live_config(
            replace(
                config,
                providers=tuple(
                    short_only if p is provider else p for p in config.providers
                ),
            )
        )


@pytest.mark.parametrize("symbol", DONCHIAN_ROUTES)
def test_each_route_resolves_the_re_score_adverse_contract(symbol: str) -> None:
    """Friction parity compares live fills against the re-score's adverse arm."""
    contract = modeled_contract(STRONG, symbol)
    assert contract is not None
    assert contract.entry_fee_bps == (4.5 if symbol == "SOL" else 0.9)
    assert contract.entry_slippage_bps == 5.5
    assert contract.evidence_source == str(RESCORE)
    v1 = modeled_contract(DONCHIAN20_STRATEGY, symbol)
    assert v1 is not None
    shape = (
        "entry_liquidity",
        "stop_policy",
        "stop_bps",
        "minimum_stop_bps",
        "maximum_stop_bps",
        "maximum_hold_seconds",
        "maximum_hold_policy",
        "hard_maximum_hold_seconds",
        "target_policy",
        "target_liquidity",
        "target_bps",
        "target_r_multiple",
    )
    assert {name: getattr(contract, name) for name in shape} == {
        name: getattr(v1, name) for name in shape
    }
    _, config = _strong_config()
    provider = next(p for p in config.providers if p.strategy_id == STRONG)
    runtime, source = runtime_contract(
        {"execution": provider.execution.as_payload()}, {"symbol": symbol}
    )
    assert source == "provider_execution"
    assert runtime is not None
    assert contract_mismatches(contract, runtime) == []


@pytest.mark.parametrize("symbol", ["BTC", "ETH", "HYPE", "xyz:SPCX", None])
def test_unlisted_routes_resolve_no_strong_short_contract(symbol: str | None) -> None:
    """The contract table names only the four Donchian routes it was scored on."""
    assert modeled_contract(STRONG, symbol) is None


def test_v1_contract_tables_are_unchanged() -> None:
    """Existing modeled contracts keep their exact keys; the new table is separate."""
    assert set(v94_strong_short_modeled_contracts()) == {
        (STRONG, symbol) for symbol in DONCHIAN_ROUTES
    }
    assert STRONG not in {strategy for strategy, _ in v89_hourly_modeled_contracts()}
    assert STRONG not in {strategy for strategy, _ in v90_hourly_modeled_contracts()}
    sndk = modeled_contract(DONCHIAN20_STRATEGY, "xyz:SNDK")
    assert sndk is not None and sndk.entry_slippage_bps == 2.5


def test_rescore_journal_records_the_pre_registered_pass() -> None:
    """The cited evidence file is committed and states the rule and its result."""
    document = json.loads(RESCORE.read_text())
    assert document["passed"] is True
    assert document["threshold_atr"] == 1.0
    assert all(item["passed"] for item in document["bar"])
    assert len(document["bar"]) == 4
    assert (
        "docs/plans/2026-09-24-v94-review-actions.md"
        in (document["pre_registered_bar_source"])
    )


@pytest.mark.parametrize(
    ("symbol", "quoted"),
    [
        ("xyz:SNDK", "+$212.74 measured / +$264.30 adverse"),
        ("SOL", "-$19.11 measured / -$7.24 adverse"),
        ("xyz:BRENTOIL", "+$20.98 measured / +$28.21 adverse"),
        ("xyz:TSLA", "-$4.52 measured / +$4.39 adverse"),
    ],
)
def test_evidence_rows_quote_the_re_score_honestly(symbol: str, quoted: str) -> None:
    """Every route is low confidence, not out of sample, and quotes its own cell."""
    evidence = strategy_research_evidence(STRONG, symbol)
    assert evidence.research_state == "preregistered_rescore_passed_in_sample"
    assert evidence.confidence == "low"
    assert evidence.execution_effect == "report_only"
    assert evidence.evidence_source == str(RESCORE)
    assert quoted in evidence.summary
    assert "not out of sample" in evidence.summary.lower()
    assert "SNDK-concentrated" in evidence.summary
    document = json.loads(RESCORE.read_text())
    cells = document["cells"]
    measured = cells["recent_all8|measured"]["v93"]["per_symbol"][symbol]["delta"]
    adverse = cells["recent_all8|adverse"]["v93"]["per_symbol"][symbol]["delta"]
    assert f"{measured:+.2f}".replace("+", "+$").replace("-", "-$") in quoted
    assert f"{adverse:+.2f}".replace("+", "+$").replace("-", "-$") in quoted


def test_v1_evidence_rows_are_unchanged_by_the_new_identity() -> None:
    """The new rows are additive and keyed only by the new identity."""
    rows = hourly_price_evidence_rows()
    strong_rows = [row for row in rows if row[0] == STRONG]
    assert sorted(row[1] for row in strong_rows) == sorted(DONCHIAN_ROUTES)
    assert strategy_research_evidence(
        DONCHIAN20_STRATEGY, "xyz:SNDK"
    ).research_state == (
        "exploratory_positive_all_windows_size_raised_3_9x_unvalidated"
    )
