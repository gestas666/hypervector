from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.range_onset_forward_observer import (
    ObserverSessionIdentity,
    RangeOnsetForwardObserver,
)
from hypervector.research.sol_range_onset_shadow_models import SolShadowConfig


def _bars(rows: int = 4) -> pd.DataFrame:
    index = pd.date_range("2026-07-31T05:55:00Z", periods=rows, freq="1min")
    return pd.DataFrame(
        {
            "open": [100.0 + value for value in range(rows)],
            "high": [101.0 + value for value in range(rows)],
            "low": [99.0 + value for value in range(rows)],
            "close": [100.5 + value for value in range(rows)],
            "volume": [10.0] * rows,
        },
        index=index,
    )


def _signals(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "long_entry": [False, True, False, False],
            "short_entry": [False, False, False, False],
            "long_exit": [False, False, False, True],
            "short_exit": [False, False, False, False],
            "structural_direction": ["neutral", "long", "long", "short"],
            "regime_admitted": [True, True, True, True],
        },
        index=index,
    )


def _regimes(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "primary_regime": ["RANGE"] * 4,
            "state_1m": ["RANGE"] * 4,
            "state_5m": ["RANGE"] * 4,
            "context_15m": ["TREND_UP"] * 4,
            "confidence": [0.7] * 4,
        },
        index=index,
    )


def test_observer_ignores_seed_bars_and_emits_completed_live_decisions(
    tmp_path: Path,
) -> None:
    bars = _bars()
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T05:57:00Z"),
        ledger_path=tmp_path / "decisions.jsonl",
    )

    decisions = observer.observe(
        bars,
        observed_at=pd.Timestamp("2026-07-31T05:59:15Z"),
        signals=_signals(bars.index),
        regimes=_regimes(bars.index),
    )

    assert [row["decision_time_utc"] for row in decisions] == [
        "2026-07-31T05:58:00+00:00",
        "2026-07-31T05:59:00+00:00",
    ]
    assert decisions[0]["long_entry"] is False
    assert decisions[1]["long_exit"] is True
    assert all(row["execution_authority"] == "none" for row in decisions)
    assert all(row["submitted"] is False for row in decisions)
    assert all(row["place_attempted"] is False for row in decisions)


def test_observer_rows_are_tui_compatible_backend_decisions(tmp_path: Path) -> None:
    bars = _bars()
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T05:55:00Z"),
        ledger_path=tmp_path / "decisions.jsonl",
        wallet_configured=True,
        signing_key_configured=True,
    )

    decisions = observer.observe(
        bars,
        observed_at=pd.Timestamp("2026-07-31T05:59:15Z"),
        signals=_signals(bars.index),
        regimes=_regimes(bars.index),
    )

    latest = decisions[-1]
    assert latest["run_id"] == "sol-range-onset-1785477300000"
    assert latest["feed_ts"] == "2026-07-31T05:59:00+00:00"
    assert latest["action"] == "regime_observation"
    assert latest["strategy_name"] == "sol_1h_sma10x30_5m_range_or_breakout"
    assert latest["execution_mode"] == "shadow"
    assert latest["mark_px"] == 103.5
    assert latest["open"] == 103.0
    assert latest["high"] == 104.0
    assert latest["low"] == 102.0
    assert latest["volume"] == 10.0
    assert latest["structural_direction"] == "short"
    assert latest["regime_admitted"] is True
    assert latest["entry_allowed"] is False
    assert latest["decision_action"] == "long_exit"
    assert latest["regime_reason"] == "5m_range_admitted"
    assert latest["wallet_configured"] is True
    assert latest["signing_key_configured"] is True
    assert latest["strategy_params"] == {"leverage": 5.0}
    assert latest["risk"] == {
        "margin_fraction": 0.03,
        "max_notional_usd": 2250.0,
    }
    assert latest["position_policy"] == {
        "position_mode": "isolated_one_way",
        "max_positions_per_symbol": 1,
    }
    assert latest["exits"] == {
        "mode": "protective_stop_or_signal_or_maximum_hold",
        "stop_bps": 60.0,
        "maximum_hold_seconds": 172800.0,
    }
    assert latest["metalabel_mode"] == "off"
    assert latest["candidate_status"] == "shadow_validation"
    assert latest["init_cash"] == 15000.0
    encoded = json.dumps(latest).lower()
    assert "wallet_address" not in encoded
    assert "private_key" not in encoded


def test_observer_reports_canary_capital_identity_without_changing_authority(
    tmp_path: Path,
) -> None:
    """Canary telemetry distinguishes capital purpose while remaining no-submit."""
    bars = _bars()
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T05:55:00Z"),
        ledger_path=tmp_path / "decisions.jsonl",
        config=SolShadowConfig(
            initial_shared_equity_usd=150.0,
            capital_base_cap_usd=150.0,
            notional_cap_usd=22.5,
            stop_bps=80.0,
        ),
        identity=ObserverSessionIdentity(
            profile_id="sol_range_onset_canary_v1",
            capital_source="standalone_canary",
            portfolio_purpose="canary_validation",
            profile_fingerprint="a" * 64,
            run_fingerprint="b" * 64,
            backend_ledger_path="data/research/forward/sol_range_onset_canary/decisions.jsonl",
        ),
    )

    latest = observer.observe(
        bars,
        observed_at=pd.Timestamp("2026-07-31T05:59:15Z"),
        signals=_signals(bars.index),
        regimes=_regimes(bars.index),
    )[-1]

    assert latest["execution_mode"] == "shadow"
    assert latest["init_cash"] == pytest.approx(150.0)
    assert latest["risk"]["max_notional_usd"] == pytest.approx(22.5)
    assert latest["exits"]["stop_bps"] == pytest.approx(80.0)
    assert latest["profile_id"] == "sol_range_onset_canary_v1"
    assert latest["capital_source"] == "standalone_canary"
    assert latest["portfolio_purpose"] == "canary_validation"
    assert latest["profile_fingerprint"] == "a" * 64
    assert latest["run_fingerprint"] == "b" * 64
    assert "sol_range_onset_canary" in latest["backend_ledger_path"]
    assert latest["execution_authority"] == "none"


def test_observer_deduplicates_decisions_across_restart(tmp_path: Path) -> None:
    bars = _bars()
    ledger = tmp_path / "decisions.jsonl"
    first = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T05:55:00Z"),
        ledger_path=ledger,
    )
    first.observe(
        bars,
        observed_at=pd.Timestamp("2026-07-31T05:59:15Z"),
        signals=_signals(bars.index),
        regimes=_regimes(bars.index),
    )
    resumed = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T06:10:00Z"),
        ledger_path=ledger,
    )

    decisions = resumed.observe(
        bars,
        observed_at=pd.Timestamp("2026-07-31T06:11:00Z"),
        signals=_signals(bars.index),
        regimes=_regimes(bars.index),
    )

    assert decisions == ()
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 4


def test_observer_rejects_misaligned_signal_or_regime_frames(tmp_path: Path) -> None:
    bars = _bars()
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T05:55:00Z"),
        ledger_path=tmp_path / "decisions.jsonl",
    )

    try:
        observer.observe(
            bars,
            observed_at=pd.Timestamp("2026-07-31T05:59:15Z"),
            signals=_signals(bars.index).iloc[:-1],
            regimes=_regimes(bars.index),
        )
    except ValueError as exc:
        assert "share the completed-bar index" in str(exc)
    else:
        raise AssertionError("misaligned signals must fail closed")


def test_observer_ledger_rows_are_valid_json(tmp_path: Path) -> None:
    bars = _bars()
    ledger = tmp_path / "decisions.jsonl"
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T05:55:00Z"),
        ledger_path=ledger,
    )
    observer.observe(
        bars,
        observed_at=pd.Timestamp("2026-07-31T05:59:15Z"),
        signals=_signals(bars.index),
        regimes=_regimes(bars.index),
    )

    rows = [
        json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["symbol"] == "SOL"
    assert rows[-1]["reference_price"] == 103.5


def test_observer_appends_backend_rows_without_breaking_decision_resume(
    tmp_path: Path,
) -> None:
    bars = _bars()
    ledger = tmp_path / "decisions.jsonl"
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T05:55:00Z"),
        ledger_path=ledger,
    )
    observer.observe(
        bars,
        observed_at=pd.Timestamp("2026-07-31T05:59:15Z"),
        signals=_signals(bars.index),
        regimes=_regimes(bars.index),
    )
    observer.append_backend_rows(
        (
            {
                "feed_ts": "2026-07-31T05:59:15+00:00",
                "action": "shadow_state",
                "position_qty": 1.0,
                "execution_authority": "none",
                "submitted": False,
                "place_attempted": False,
            },
        )
    )

    rows = [
        json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["run_id"] == "sol-range-onset-1785477300000"
    assert rows[-1]["symbol"] == "SOL"
    assert rows[-1]["execution_mode"] == "shadow"
    resumed = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T06:10:00Z"),
        ledger_path=ledger,
    )
    assert (
        resumed.observe(
            bars,
            observed_at=pd.Timestamp("2026-07-31T06:11:00Z"),
            signals=_signals(bars.index),
            regimes=_regimes(bars.index),
        )
        == ()
    )


def test_observer_rejects_backend_rows_with_execution_authority(tmp_path: Path) -> None:
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T05:55:00Z"),
        ledger_path=tmp_path / "decisions.jsonl",
    )

    try:
        observer.append_backend_rows(
            (
                {
                    "feed_ts": "2026-07-31T05:59:15+00:00",
                    "action": "shadow_state",
                    "execution_authority": "live",
                    "submitted": False,
                    "place_attempted": False,
                },
            )
        )
    except ValueError as exc:
        assert "execution authority" in str(exc)
    else:
        raise AssertionError("observer backend rows must remain no-submit")
