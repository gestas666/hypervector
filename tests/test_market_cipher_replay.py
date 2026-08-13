"""Lifecycle contracts for realistic Market Cipher portfolio replay."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.market_cipher_replay import (
    evaluate_market_cipher_replay,
)
from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayConfig,
)


def _bars(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    *,
    funding: list[float] | None = None,
    wave_cross: list[int] | None = None,
) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(opens), freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "funding_rate": funding or [0.0] * len(opens),
            "wave_cross": wave_cross or [0] * len(opens),
        },
        index=index,
    )


def _signal(
    timestamp: pd.Timestamp,
    *,
    symbol: str = "BTC",
    side: str = "long",
    score: int = 8,
    stop_anchor: float = 99.0,
    candidate: str = "mc_scalper_15m",
) -> dict[str, object]:
    return {
        "signal_time_utc": timestamp,
        "symbol": symbol,
        "candidate": candidate,
        "side": side,
        "score": score,
        "stop_anchor": stop_anchor,
        "eligible": True,
    }


def _config(**changes: object) -> MarketCipherReplayConfig:
    values: dict[str, object] = {
        "initial_equity": 10_000.0,
        "risk_fraction": 0.005,
        "leverage": 5.0,
        "entry_slippage_bps": 2.0,
        "market_exit_slippage_bps": 2.0,
    }
    values.update(changes)
    return MarketCipherReplayConfig(**values)


def test_entry_is_next_bar_adverse_and_gap_stop_cannot_improve() -> None:
    """A completed-bar signal fills later and gaps worsen stop execution."""
    bars = _bars(
        [100.0, 100.0, 99.0],
        [100.1, 100.1, 99.1],
        [99.9, 99.8, 98.0],
        [100.0, 100.0, 98.5],
    )
    signals = pd.DataFrame([_signal(bars.index[0])])

    report = evaluate_market_cipher_replay({"BTC": bars}, signals, _config())

    trade = report.trades[0]
    assert trade.signal_score == 8.0
    assert trade.entry_time_utc == bars.index[1].isoformat()
    assert trade.entry_price == pytest.approx(100.02)
    assert trade.stop_distance_bps == pytest.approx(50.0)
    assert trade.exit_reason == "stop"
    assert trade.exit_price == pytest.approx(99.0 * (1.0 - 2.0 / 10_000.0))


def test_exact_entry_price_override_bypasses_modeled_entry_slippage() -> None:
    """A venue-reconstructed fill remains exact while later exits retain friction."""
    bars = _bars(
        [100.0, 101.0, 101.0],
        [100.1, 101.1, 101.1],
        [99.9, 100.9, 100.9],
        [100.0, 101.0, 101.0],
    )
    signal = _signal(bars.index[0], stop_anchor=99.0)
    signal["entry_price_override"] = 100.5

    report = evaluate_market_cipher_replay(
        {"BTC": bars},
        pd.DataFrame([signal]),
        _config(entry_slippage_bps=25.0),
    )

    assert report.trades[0].entry_price == pytest.approx(100.5)


def test_invalid_exact_entry_price_override_is_rejected() -> None:
    """Malformed reconstructed fills cannot become success-shaped prices."""
    bars = _bars([100.0, 101.0], [100.1, 101.1], [99.9, 100.9], [100.0, 101.0])
    signal = _signal(bars.index[0], stop_anchor=99.0)
    signal["entry_price_override"] = -1.0

    report = evaluate_market_cipher_replay(
        {"BTC": bars}, pd.DataFrame([signal]), _config()
    )

    assert report.completed_trades == 0
    assert report.rejections[0].reason == "invalid_entry_price_override"


def test_liquidation_precedes_stop_when_bar_path_is_unknown() -> None:
    """A bar touching liquidation and stop resolves conservatively."""
    bars = _bars(
        [100.0, 100.0, 70.0],
        [100.1, 100.1, 71.0],
        [99.9, 99.8, 60.0],
        [100.0, 100.0, 65.0],
    )
    signals = pd.DataFrame([_signal(bars.index[0])])

    report = evaluate_market_cipher_replay({"BTC": bars}, signals, _config())

    assert report.liquidations == 1
    assert report.trades[0].exit_reason == "liquidation"
    assert report.liquidation_penalties_usd > 0.0


def test_staged_exit_quantities_reconcile_and_accounting_identity_holds() -> None:
    """The pre-registered 25/50/remainder variant closes exact quantities."""
    bars = _bars(
        [100.0, 100.0, 100.5, 100.6],
        [100.1, 100.7, 100.8, 100.7],
        [99.9, 99.9, 100.4, 100.5],
        [100.0, 100.6, 100.7, 100.6],
        wave_cross=[1, 0, -1, 0],
    )
    signals = pd.DataFrame([_signal(bars.index[0], stop_anchor=99.99)])
    config = _config(exit_variant="staged_25_50_trail")

    report = evaluate_market_cipher_replay({"BTC": bars}, signals, config)

    trade = report.trades[0]
    assert [leg.fraction_of_initial for leg in trade.exit_legs] == pytest.approx(
        [0.25, 0.375, 0.375]
    )
    assert sum(leg.quantity for leg in trade.exit_legs) == pytest.approx(
        trade.initial_quantity
    )
    assert trade.exit_reason == "opposite_wave_cross"
    expected = (
        report.initial_equity
        + report.gross_pnl_usd
        - report.total_fees_usd
        + report.funding_cashflow_usd
        - report.liquidation_penalties_usd
    )
    assert report.final_equity == pytest.approx(expected)


@pytest.mark.parametrize(
    ("side", "expected_sign"),
    [("long", -1), ("short", 1)],
)
def test_hourly_funding_uses_remaining_signed_notional(
    side: str, expected_sign: int
) -> None:
    """Positive funding is paid by longs and received by shorts."""
    bars = _bars(
        [100.0, 100.0, 100.0],
        [100.1, 100.1, 100.1],
        [99.9, 99.9, 99.9],
        [100.0, 100.0, 100.0],
        funding=[0.0, 0.001, 0.0],
    )
    anchor = 101.0 if side == "short" else 99.0
    signals = pd.DataFrame([_signal(bars.index[0], side=side, stop_anchor=anchor)])

    report = evaluate_market_cipher_replay({"BTC": bars}, signals, _config())

    assert report.funding_cashflow_usd * expected_sign > 0.0


def test_simultaneous_candidates_rank_and_reject_duplicate_symbol() -> None:
    """One symbol gets one position and the highest score wins deterministically."""
    btc = _bars(
        [100.0, 100.0, 100.0],
        [100.1, 100.1, 100.1],
        [99.9, 99.9, 99.9],
        [100.0, 100.0, 100.0],
    )
    signals = pd.DataFrame(
        [
            _signal(btc.index[0], score=8, candidate="lower"),
            _signal(btc.index[0], score=9, candidate="higher"),
        ]
    )

    report = evaluate_market_cipher_replay({"BTC": btc}, signals, _config())

    assert report.trades[0].candidate == "higher"
    assert report.rejections[0].reason == "duplicate_symbol_candidate"
    assert report.maximum_concurrent_positions == 1


def test_config_rejects_portfolio_risk_above_two_percent() -> None:
    """Configured concurrent position risk cannot exceed the frozen cap."""
    with pytest.raises(ValueError, match="configured portfolio risk"):
        _config(risk_fraction=0.01, maximum_concurrent_positions=3)


def test_gap_through_stop_anchor_rejects_entry_without_aborting_run() -> None:
    """A structurally invalid next-bar entry remains visible as a rejection."""
    bars = _bars(
        [100.0, 98.0, 98.0],
        [100.1, 98.1, 98.1],
        [99.9, 97.9, 97.9],
        [100.0, 98.0, 98.0],
    )
    signals = pd.DataFrame([_signal(bars.index[0], stop_anchor=99.0)])

    report = evaluate_market_cipher_replay({"BTC": bars}, signals, _config())

    assert report.completed_trades == 0
    assert report.rejections[0].reason == "stop_anchor_crossed_at_entry"


def test_replay_enforces_per_symbol_hyperliquid_leverage_tiers() -> None:
    """BTC leverage may not silently leak into the lower SOL venue tier."""
    bars = _bars([100.0, 100.0], [100.1, 100.1], [99.9, 99.9], [100.0, 100.0])

    with pytest.raises(ValueError, match="exceeds SOL venue maximum"):
        evaluate_market_cipher_replay(
            {"SOL": bars},
            pd.DataFrame(
                columns=[
                    "signal_time_utc",
                    "symbol",
                    "candidate",
                    "side",
                    "score",
                    "stop_anchor",
                    "eligible",
                ]
            ),
            _config(leverage=21.0),
        )


def test_replay_defines_hype_venue_leverage_tier() -> None:
    """HYPE research uses its explicit altcoin tier rather than a missing default."""
    config = _config(leverage=5.0)

    assert config.venue_max_leverage_for("HYPE") == 10.0


def test_control_target_r_multiple_changes_target_without_lookahead() -> None:
    """Hulk exit research can widen its target without changing signal timing."""
    bars = _bars(
        [100.0, 100.0, 100.5],
        [100.1, 100.5, 100.8],
        [99.9, 99.9, 100.4],
        [100.0, 100.4, 100.7],
    )
    signals = pd.DataFrame([_signal(bars.index[0], stop_anchor=99.99)])

    report = evaluate_market_cipher_replay(
        {"BTC": bars}, signals, _config(target_r_multiple=3.0)
    )

    assert report.trades[0].exit_reason == "target_reward_risk"
    assert report.trades[0].exit_legs[-1].reason == "target_reward_risk"
    assert report.trades[0].exit_time_utc == bars.index[2].isoformat()


def test_signal_risk_multiplier_scales_budget_without_changing_entry() -> None:
    """Annotation-driven sizing changes exposure, not signal or fill prices."""
    bars = _bars(
        [100.0, 100.0, 100.5],
        [100.1, 100.5, 100.8],
        [99.9, 99.9, 100.4],
        [100.0, 100.4, 100.7],
    )
    full = pd.DataFrame([_signal(bars.index[0], stop_anchor=99.99)])
    scaled = full.copy()
    scaled["risk_multiplier"] = 0.5
    config = _config(
        maximum_signal_risk_multiplier=1.5,
        maximum_portfolio_risk_fraction=0.03,
        target_r_multiple=3.0,
    )

    full_report = evaluate_market_cipher_replay({"BTC": bars}, full, config)
    scaled_report = evaluate_market_cipher_replay({"BTC": bars}, scaled, config)

    assert full_report.trades[0].risk_budget_usd == pytest.approx(50.0)
    assert scaled_report.trades[0].risk_budget_usd == pytest.approx(25.0)
    assert scaled_report.trades[0].entry_price == full_report.trades[0].entry_price
    assert abs(scaled_report.net_pnl_usd) < abs(full_report.net_pnl_usd)


def test_signal_risk_multiplier_above_configured_limit_is_rejected() -> None:
    """A Brain annotation cannot silently exceed the bounded risk envelope."""
    bars = _bars([100.0, 100.0], [100.1, 100.1], [99.9, 99.9], [100.0, 100.0])
    signals = pd.DataFrame([_signal(bars.index[0], stop_anchor=99.0)])
    signals["risk_multiplier"] = 2.0

    report = evaluate_market_cipher_replay(
        {"BTC": bars},
        signals,
        _config(
            maximum_signal_risk_multiplier=1.5,
            maximum_portfolio_risk_fraction=0.03,
        ),
    )

    assert report.completed_trades == 0
    assert report.rejections[0].reason == "risk_multiplier_exceeds_configured_max"


def test_configured_entry_delay_uses_later_bar_without_future_signal_change() -> None:
    """Robustness can perturb fill delay while retaining the original decision."""
    bars = _bars(
        [100.0, 101.0, 102.0, 102.0],
        [100.1, 101.1, 102.1, 102.1],
        [99.9, 100.9, 101.9, 101.9],
        [100.0, 101.0, 102.0, 102.0],
    )
    signals = pd.DataFrame([_signal(bars.index[0], stop_anchor=99.0)])

    report = evaluate_market_cipher_replay(
        {"BTC": bars}, signals, _config(entry_delay_bars=2)
    )

    assert report.trades[0].signal_time_utc == bars.index[0].isoformat()
    assert report.trades[0].entry_time_utc == bars.index[2].isoformat()
    assert report.trades[0].entry_price == pytest.approx(102.0204)


def test_funding_stress_multiplier_scales_authentic_settlement_cashflow() -> None:
    """Funding robustness changes the recorded venue rate magnitude explicitly."""
    bars = _bars(
        [100.0, 100.0, 100.0],
        [100.1, 100.1, 100.1],
        [99.9, 99.9, 99.9],
        [100.0, 100.0, 100.0],
        funding=[0.0, 0.001, 0.0],
    )
    signals = pd.DataFrame([_signal(bars.index[0], stop_anchor=99.0)])

    nominal = evaluate_market_cipher_replay({"BTC": bars}, signals, _config())
    stressed = evaluate_market_cipher_replay(
        {"BTC": bars}, signals, _config(funding_rate_multiplier=2.0)
    )

    assert stressed.funding_cashflow_usd == pytest.approx(
        2.0 * nominal.funding_cashflow_usd
    )
