"""Append-only, no-submit forward decisions for the SOL range-onset challenger."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hypervector.research.btc_shadow_capital import BtcShadowCapitalReader
from hypervector.research.sol_range_onset_shadow import (
    SharedCapitalSnapshot,
    SolRangeOnsetShadowEngine,
    SolShadowConfig,
)
from hypervector.research.sol_range_onset_shadow_ledger import SolShadowLedger

__all__ = (
    "BtcShadowCapitalReader",
    "RangeOnsetForwardObserver",
    "SharedCapitalSnapshot",
    "SolRangeOnsetShadowEngine",
    "SolShadowConfig",
    "SolShadowLedger",
)

_MINUTE = pd.Timedelta(minutes=1)
_SIGNAL_COLUMNS = (
    "long_entry",
    "short_entry",
    "long_exit",
    "short_exit",
    "structural_direction",
    "regime_admitted",
)
_REGIME_COLUMNS = (
    "primary_regime",
    "state_1m",
    "state_5m",
    "context_15m",
    "confidence",
)


@dataclass(frozen=True)
class ObserverSessionIdentity:
    """Non-secret portfolio provenance attached to every backend row."""

    profile_id: str
    capital_source: str
    portfolio_purpose: str
    profile_fingerprint: str
    run_fingerprint: str
    backend_ledger_path: str

    def __post_init__(self) -> None:
        """Reject missing provenance and malformed stable fingerprints."""
        for name in (
            "profile_id",
            "capital_source",
            "portfolio_purpose",
            "backend_ledger_path",
        ):
            value = str(getattr(self, name))
            if not value.strip():
                raise ValueError(f"observer {name} must be non-empty")
        for name in ("profile_fingerprint", "run_fingerprint"):
            value = str(getattr(self, name))
            if len(value) != 64 or any(
                char not in "0123456789abcdef" for char in value
            ):
                raise ValueError(f"observer {name} must be a lowercase SHA-256")


class RangeOnsetForwardObserver:
    """Persist completed-bar decisions without possessing execution authority."""

    def __init__(
        self,
        *,
        symbol: str,
        activated_at: pd.Timestamp,
        ledger_path: Path,
        config: SolShadowConfig | None = None,
        wallet_configured: bool | None = None,
        signing_key_configured: bool | None = None,
        identity: ObserverSessionIdentity | None = None,
    ) -> None:
        clean_symbol = symbol.strip().upper()
        if not clean_symbol:
            raise ValueError("observer symbol must be non-empty")
        self._symbol = clean_symbol
        requested_activation = _utc_timestamp(activated_at)
        self._ledger_path = ledger_path
        self._config = config or SolShadowConfig()
        self._identity = identity or ObserverSessionIdentity(
            profile_id="sol_range_onset_research_shadow_v1",
            capital_source="btc_shadow_shared_portfolio",
            portfolio_purpose="research_validation",
            profile_fingerprint=self._config.fingerprint,
            run_fingerprint=self._config.fingerprint,
            backend_ledger_path=str(ledger_path),
        )
        self._wallet_configured = wallet_configured
        self._signing_key_configured = signing_key_configured
        ledger_state = _load_ledger_state(ledger_path, clean_symbol)
        self._activated_at = ledger_state[0] or requested_activation
        self._last_decision_ms = ledger_state[1]
        self._run_id = f"sol-range-onset-{int(self._activated_at.value // 1_000_000)}"

    def observe(
        self,
        bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        signals: pd.DataFrame,
        regimes: pd.DataFrame,
    ) -> tuple[dict[str, object], ...]:
        """Append every newly completed post-activation decision exactly once."""
        _validate_frames(bars, signals, regimes)
        observed = _utc_timestamp(observed_at)
        complete = bars.index + _MINUTE <= observed
        decisions: list[dict[str, object]] = []
        for timestamp in bars.index[complete]:
            decision_time = timestamp + _MINUTE
            decision_ms = int(decision_time.value // 1_000_000)
            if decision_time <= self._activated_at:
                continue
            if (
                self._last_decision_ms is not None
                and decision_ms <= self._last_decision_ms
            ):
                continue
            decisions.append(
                _decision_row(
                    self._symbol,
                    self._activated_at,
                    observed,
                    decision_time,
                    bars.loc[timestamp],
                    signals.loc[timestamp],
                    regimes.loc[timestamp],
                    self._wallet_configured,
                    self._signing_key_configured,
                    self._config,
                    self._identity,
                )
            )
            self._last_decision_ms = decision_ms
        _append_rows(self._ledger_path, decisions)
        return tuple(decisions)

    def append_backend_rows(
        self,
        rows: tuple[dict[str, object], ...],
    ) -> None:
        """Append flattened no-submit lifecycle telemetry for the same run."""
        rendered: list[dict[str, object]] = []
        for row in rows:
            _validate_backend_row(row)
            rendered.append(
                {
                    **row,
                    **_backend_identity_fields(
                        self._symbol,
                        self._activated_at,
                        self._run_id,
                        self._wallet_configured,
                        self._signing_key_configured,
                        self._config,
                        self._identity,
                    ),
                }
            )
        _append_rows(self._ledger_path, rendered)


def _validate_frames(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
) -> None:
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("bars must use a DatetimeIndex")
    if bars.index.tz is None:
        raise ValueError("bars index must be timezone-aware")
    if not bars.index.equals(signals.index) or not bars.index.equals(regimes.index):
        raise ValueError(
            "bars, signals, and regimes must share the completed-bar index"
        )
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(bars.columns)
    missing.update(set(_SIGNAL_COLUMNS).difference(signals.columns))
    missing.update(set(_REGIME_COLUMNS).difference(regimes.columns))
    if missing:
        raise ValueError(f"observer frames are missing columns: {sorted(missing)}")
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError("bars index must be unique and increasing")
    if (
        len(bars.index) > 1
        and not bars.index.to_series().diff().iloc[1:].eq(_MINUTE).all()
    ):
        raise ValueError("observer bars require uninterrupted one-minute cadence")


def _decision_row(
    symbol: str,
    activated_at: pd.Timestamp,
    observed_at: pd.Timestamp,
    decision_time: pd.Timestamp,
    bar: pd.Series,
    signal: pd.Series,
    regime: pd.Series,
    wallet_configured: bool | None,
    signing_key_configured: bool | None,
    config: SolShadowConfig,
    identity: ObserverSessionIdentity,
) -> dict[str, object]:
    market = _market_fields(bar)
    reference_price = float(market["close"])
    if not math.isfinite(reference_price) or reference_price <= 0.0:
        raise ValueError("decision reference price must be positive and finite")
    lag_ms = int((observed_at - decision_time).total_seconds() * 1_000)
    if lag_ms < 0:
        raise ValueError("decision cannot be observed before its completed bar")
    long_entry = bool(signal["long_entry"])
    short_entry = bool(signal["short_entry"])
    long_exit = bool(signal["long_exit"])
    short_exit = bool(signal["short_exit"])
    structural_direction = str(signal["structural_direction"])
    if structural_direction not in {"long", "short", "neutral"}:
        raise ValueError("structural direction must be long, short, or neutral")
    regime_admitted = bool(signal["regime_admitted"])
    state_5m = str(regime["state_5m"])
    entry_direction = "long" if long_entry else "short" if short_entry else None
    return {
        "schema_version": 1,
        "strategy": "sol_1h_sma10x30_5m_range_or_breakout",
        "strategy_name": "sol_1h_sma10x30_5m_range_or_breakout",
        "candidate_status": "shadow_validation",
        "run_id": f"sol-range-onset-{int(activated_at.value // 1_000_000)}",
        "execution_mode": "shadow",
        "wallet_configured": wallet_configured,
        "signing_key_configured": signing_key_configured,
        "live_enabled": False,
        "live_armed": False,
        **_observer_identity_fields(identity),
        **_session_fields(config),
        "symbol": symbol,
        "feed_ts": decision_time.isoformat(),
        "action": "regime_observation",
        "activated_at_utc": activated_at.isoformat(),
        "decision_time_utc": decision_time.isoformat(),
        "observed_at_utc": observed_at.isoformat(),
        "observation_lag_ms": lag_ms,
        "fresh_at_observation": lag_ms <= 60_000,
        "reference_price": reference_price,
        "mark_px": reference_price,
        **market,
        "long_entry": long_entry,
        "short_entry": short_entry,
        "long_exit": long_exit,
        "short_exit": short_exit,
        "primary_regime": str(regime["primary_regime"]),
        "state_1m": str(regime["state_1m"]),
        "state_5m": state_5m,
        "context_15m": str(regime["context_15m"]),
        "confidence": _finite_float(regime["confidence"], "regime confidence"),
        "structural_direction": structural_direction,
        "regime_admitted": regime_admitted,
        "entry_allowed": long_entry or short_entry,
        "entry_direction": entry_direction,
        "decision_action": _decision_action(
            long_entry=long_entry,
            short_entry=short_entry,
            long_exit=long_exit,
            short_exit=short_exit,
        ),
        "regime_reason": (
            f"5m_{state_5m.lower()}_admitted"
            if regime_admitted
            else f"5m_{state_5m.lower()}_blocked"
        ),
        "execution_authority": "none",
        "model_authority": "none",
        "submitted": False,
        "place_attempted": False,
    }


def _session_fields(config: SolShadowConfig) -> dict[str, object]:
    return {
        "init_cash": config.initial_shared_equity_usd,
        "metalabel_mode": "off",
        "strategy_params": {"leverage": config.leverage},
        "position_policy": {
            "position_mode": "isolated_one_way",
            "max_positions_per_symbol": 1,
        },
        "risk": {
            "margin_fraction": config.margin_fraction,
            "max_notional_usd": config.notional_cap_usd,
        },
        "exits": {
            "mode": "protective_stop_or_signal_or_maximum_hold",
            "stop_bps": config.stop_bps,
            "maximum_hold_seconds": config.max_hold_ms / 1_000.0,
        },
        "execution": {
            "order_type": "market",
            "time_in_force": "ioc",
            "fill_model": "public_l2_depth_walk",
        },
        "costs": {
            "taker_fee_rate": config.taker_fee_rate,
            "funding_source": "hyperliquid_oracle_price",
        },
        "regime_policy": {
            "execution_timeframe": "1m",
            "signal_timeframe": "1h",
            "primary_timeframe": "5m",
            "allowed_entry_states": ["RANGE", "BREAKOUT"],
        },
    }


def _backend_identity_fields(
    symbol: str,
    activated_at: pd.Timestamp,
    run_id: str,
    wallet_configured: bool | None,
    signing_key_configured: bool | None,
    config: SolShadowConfig,
    identity: ObserverSessionIdentity,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "strategy": "sol_1h_sma10x30_5m_range_or_breakout",
        "strategy_name": "sol_1h_sma10x30_5m_range_or_breakout",
        "candidate_status": "shadow_validation",
        "run_id": run_id,
        "execution_mode": "shadow",
        "wallet_configured": wallet_configured,
        "signing_key_configured": signing_key_configured,
        "live_enabled": False,
        "live_armed": False,
        **_observer_identity_fields(identity),
        **_session_fields(config),
        "symbol": symbol,
        "activated_at_utc": activated_at.isoformat(),
        "execution_authority": "none",
        "model_authority": "none",
        "submitted": False,
        "place_attempted": False,
    }


def _observer_identity_fields(identity: ObserverSessionIdentity) -> dict[str, str]:
    return {
        "profile_id": identity.profile_id,
        "capital_source": identity.capital_source,
        "portfolio_purpose": identity.portfolio_purpose,
        "profile_fingerprint": identity.profile_fingerprint,
        "run_fingerprint": identity.run_fingerprint,
        "backend_ledger_path": identity.backend_ledger_path,
    }


def _market_fields(bar: pd.Series) -> dict[str, float]:
    fields = {
        name: _finite_float(bar[name], f"decision bar {name}")
        for name in ("open", "high", "low", "close", "volume")
    }
    if fields["open"] <= 0.0 or fields["close"] <= 0.0:
        raise ValueError("decision bar open and close must be positive")
    if fields["high"] < max(fields["open"], fields["close"]):
        raise ValueError("decision bar high must contain open and close")
    if fields["low"] > min(fields["open"], fields["close"]) or fields["low"] <= 0.0:
        raise ValueError("decision bar low must be positive and contain open and close")
    if fields["volume"] < 0.0:
        raise ValueError("decision bar volume cannot be negative")
    return fields


def _decision_action(
    *,
    long_entry: bool,
    short_entry: bool,
    long_exit: bool,
    short_exit: bool,
) -> str:
    if long_entry:
        return "long_onset" if short_exit else "enter_long"
    if short_entry:
        return "short_onset" if long_exit else "enter_short"
    if long_exit:
        return "long_exit"
    if short_exit:
        return "short_exit"
    return "hold"


def _load_ledger_state(
    path: Path,
    expected_symbol: str,
) -> tuple[pd.Timestamp | None, int | None]:
    if not path.exists():
        return None, None
    activation: pd.Timestamp | None = None
    latest: int | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid observer ledger JSON at line {line_number}"
                ) from exc
            if not isinstance(row, dict) or row.get("symbol") != expected_symbol:
                raise ValueError(f"observer ledger line {line_number} has wrong symbol")
            row_activation = _utc_timestamp(
                pd.Timestamp(str(row.get("activated_at_utc")))
            )
            if activation is not None and row_activation != activation:
                raise ValueError("observer ledger activation time must remain constant")
            activation = row_activation
            if row.get("action") != "regime_observation":
                continue
            timestamp = _utc_timestamp(pd.Timestamp(str(row.get("decision_time_utc"))))
            current = int(timestamp.value // 1_000_000)
            if latest is not None and current <= latest:
                raise ValueError(
                    "observer ledger decision times must strictly increase"
                )
            latest = current
    return activation, latest


def _validate_backend_row(row: dict[str, object]) -> None:
    action = row.get("action")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("observer backend row action must be non-empty")
    _utc_timestamp(pd.Timestamp(str(row.get("feed_ts"))))
    if row.get("execution_authority") != "none":
        raise ValueError("observer backend row execution authority must remain none")
    if row.get("submitted") is not False or row.get("place_attempted") is not False:
        raise ValueError("observer backend row must remain no-submit")


def _append_rows(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True))
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _utc_timestamp(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("observer timestamps must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _finite_float(value: object, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number
