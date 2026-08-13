"""Completed-30m, zero-capital forward telemetry for the four-Pine stack."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pandas as pd

from hypervector.research.low_tf_multi_asset_contract import complete_ohlcv_bars
from hypervector.research.pine_stack_adaptive_supertrend import (
    AdaptiveSupertrendConfig,
)
from hypervector.research.pine_stack_features import (
    PineStackFeatureConfig,
    build_pine_stack_features,
)
from hypervector.research.pine_stack_market_sentiment import (
    MARKET_SENTIMENT_COMPONENTS,
)
from hypervector.research.pine_stack_tp_dimensions import TpDimensionsConfig
from hypervector.research.pine_stack_trend_levels import TrendLevelsConfig

_STRATEGY = "pine_stack_eth30_forward_observer_v1"
_FRESHNESS = pd.Timedelta(seconds=90)
_HISTORY_ROWS = 120
_REQUIRED_FEATURES = {
    "bar_open_at",
    "decision_time_utc",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "cs_selected_factor",
    "cs_trailing_stop",
    "cs_trend_state",
    "cs_long_onset",
    "cs_short_onset",
    "trend_levels_state",
    "trend_levels_episode_bars",
    "trend_levels_episode_high",
    "trend_levels_episode_low",
    "trend_levels_episode_mid",
    "trend_levels_close_location_delta_pct",
    "trend_levels_ambiguous_extreme",
    "sentiment_score",
    "component_support",
    "tp_density_match_raw",
    "tp_density_match_score",
    "tp_directional_pool_size",
    "tp_minimum_axis_support",
    "tp_insufficient_support",
    "tp_relative_volume_score",
    "tp_time_of_day_score",
    "tp_range_position_score",
    "execution_authority",
    *MARKET_SENTIMENT_COMPONENTS,
}


def forward_feature_config() -> PineStackFeatureConfig:
    """Return the frozen backend feature identity used for forward telemetry."""
    return PineStackFeatureConfig(
        adaptive_supertrend=AdaptiveSupertrendConfig(
            atr_period=10,
            sensitivity=5.0,
        ),
        trend_levels=TrendLevelsConfig(lookback=30, ambiguity_policy="hold"),
        tp_dimensions=TpDimensionsConfig(
            pivot_width=5,
            bin_count=5,
            include_time_of_day=False,
            minimum_directional_pool=50,
        ),
    )


def prepare_completed_pine_features(
    raw_minutes: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
    bar_minutes: int = 30,
) -> pd.DataFrame:
    """Build causal features after removing forming minute and native bars."""
    observed = _utc(observed_at)
    minutes = _validated_minutes(raw_minutes)
    complete = minutes["timestamp"] + pd.Timedelta(minutes=1) <= observed
    completed_minutes = minutes.loc[complete].reset_index(drop=True)
    native = complete_ohlcv_bars(
        completed_minutes,
        source_minutes=1,
        bar_minutes=bar_minutes,
    )
    features = build_pine_stack_features(
        native,
        bar_minutes=bar_minutes,
        config=forward_feature_config(),
    )
    available = features["decision_time_utc"].le(observed)
    return features.loc[available].reset_index(drop=True)


class PineStackForwardObserver:
    """Persist forward-only backend features without execution authority."""

    def __init__(
        self,
        *,
        activated_at: pd.Timestamp,
        ledger_path: Path,
        symbol: str = "ETH",
    ) -> None:
        """Restore immutable activation and last completed decision if present."""
        normalized = symbol.strip().upper()
        if normalized != "ETH":
            raise ValueError("the frozen Pine observer currently supports ETH only")
        state = _load_state(ledger_path, normalized)
        self._activated_at = state[0] or _utc(activated_at)
        self._last_decision = state[1]
        self._session_exists = state[2]
        self._ledger_path = ledger_path
        self._symbol = normalized
        self._run_id = f"pine-eth30-{int(self._activated_at.value // 1_000_000)}"

    def observe(
        self,
        features: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
    ) -> tuple[dict[str, object], ...]:
        """Append startup history and newly completed forward decisions once."""
        frame = _validated_features(features)
        observed = _utc(observed_at)
        rows: list[dict[str, object]] = []
        if not self._session_exists:
            rows.append(self._session_row(observed))
            rows.extend(self._history_rows(frame, observed))
            self._session_exists = True
        rows.extend(self._new_decision_rows(frame, observed))
        _append_rows(self._ledger_path, rows)
        return tuple(rows)

    def _session_row(self, observed: pd.Timestamp) -> dict[str, object]:
        return {
            **self._identity_fields(),
            "feed_ts": observed.isoformat(),
            "action": "session_start",
            "activated_at_utc": self._activated_at.isoformat(),
        }

    def _history_rows(
        self,
        features: pd.DataFrame,
        observed: pd.Timestamp,
    ) -> list[dict[str, object]]:
        eligible = features["decision_time_utc"].le(self._activated_at)
        history = features.loc[eligible].tail(_HISTORY_ROWS)
        return [
            self._feature_row(row, observed, action="regime_history")
            for _, row in history.iterrows()
        ]

    def _new_decision_rows(
        self,
        features: pd.DataFrame,
        observed: pd.Timestamp,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for _, feature in features.iterrows():
            decision = _utc(pd.Timestamp(feature["decision_time_utc"]))
            if decision <= self._activated_at or decision > observed:
                continue
            if self._last_decision is not None and decision <= self._last_decision:
                continue
            rows.append(
                self._feature_row(feature, observed, action="regime_observation")
            )
            self._last_decision = decision
        return rows

    def _feature_row(
        self,
        feature: pd.Series,
        observed: pd.Timestamp,
        *,
        action: str,
    ) -> dict[str, object]:
        decision = _utc(pd.Timestamp(feature["decision_time_utc"]))
        raw_direction = _candidate_direction(feature)
        fresh = observed - decision <= _FRESHNESS
        actionable = (
            action == "regime_observation" and fresh and raw_direction is not None
        )
        return {
            **self._identity_fields(),
            "feed_ts": decision.isoformat(),
            "action": action,
            "activated_at_utc": self._activated_at.isoformat(),
            "observed_at_utc": observed.isoformat(),
            "observation_lag_ms": int((observed - decision).total_seconds() * 1_000),
            "fresh_at_observation": fresh,
            "primary_regime": "NOT_CLASSIFIED",
            "regime_reason": _decision_reason(feature, raw_direction),
            "decision_action": _decision_action(action, raw_direction, fresh),
            "entry_direction": raw_direction,
            "entry_allowed": actionable,
            "pine_candidate_entry": raw_direction is not None,
            **_market_fields(feature),
            **_pine_fields(feature),
        }

    def _identity_fields(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "strategy": _STRATEGY,
            "strategy_name": _STRATEGY,
            "candidate_status": "historical_pseudo_holdout_failed_forward_observer",
            "run_id": self._run_id,
            "symbol": self._symbol,
            "execution_mode": "observe",
            "live_enabled": False,
            "live_armed": False,
            "execution_authority": "none",
            "model_authority": "none",
            "submitted": False,
            "place_attempted": False,
            "portfolio_purpose": "zero_capital_forward_observation",
            "strategy_params": _strategy_parameters(),
            "position_policy": {"max_positions_per_symbol": 0},
            "risk": {"capital_usd": 0.0, "notional_usd": 0.0},
            "exits": {
                "research_control": "cs_flip_or_8h_hold",
                "stop_margin_pct": 10.0,
            },
            "execution": {"authority": "none", "next_bar_model": "next_30m_open"},
            "costs": {"status": "not_applicable_zero_capital_observer"},
            "regime_policy": {
                "engine": "four_pine_completed_30m_observer_v1",
                "classification": "NOT_A_CANONICAL_REGIME_CLASSIFIER",
                "signal_timeframe": "30m",
                "execution_timeframe": "not_applicable_observer",
            },
        }


def _strategy_parameters() -> dict[str, object]:
    return {
        "cs_atr_period": 10,
        "cs_sensitivity": 5.0,
        "trend_lookback": 30,
        "sentiment_role": "annotation_only",
        "tp_pivot_width": 5,
        "tp_bins": 5,
        "tp_minimum_directional_pool": 50,
        "tp_time_of_day_axis": False,
    }


def _pine_fields(row: pd.Series) -> dict[str, object]:
    components = {
        name.removeprefix("sentiment_"): _optional_float(row[name])
        for name in MARKET_SENTIMENT_COMPONENTS
    }
    return {
        "pine_cs_state": int(row["cs_trend_state"]),
        "pine_cs_selected_factor": _optional_float(row["cs_selected_factor"]),
        "pine_cs_trailing_stop": _optional_float(row["cs_trailing_stop"]),
        "pine_cs_long_onset": bool(row["cs_long_onset"]),
        "pine_cs_short_onset": bool(row["cs_short_onset"]),
        "pine_trend_state": int(row["trend_levels_state"]),
        "pine_trend_episode_bars": int(row["trend_levels_episode_bars"]),
        "pine_trend_episode_high": _optional_float(row["trend_levels_episode_high"]),
        "pine_trend_episode_low": _optional_float(row["trend_levels_episode_low"]),
        "pine_trend_episode_mid": _optional_float(row["trend_levels_episode_mid"]),
        "pine_trend_delta_pct": _optional_float(
            row["trend_levels_close_location_delta_pct"]
        ),
        "pine_trend_ambiguous": bool(row["trend_levels_ambiguous_extreme"]),
        "pine_sentiment_score": _optional_float(row["sentiment_score"]),
        "pine_sentiment_support": int(row["component_support"]),
        "pine_sentiment_components": components,
        "pine_tp_density_raw": _optional_float(row["tp_density_match_raw"]),
        "pine_tp_density_score": _optional_float(row["tp_density_match_score"]),
        "pine_tp_directional_pool": int(row["tp_directional_pool_size"]),
        "pine_tp_minimum_support": int(row["tp_minimum_axis_support"]),
        "pine_tp_insufficient_support": bool(row["tp_insufficient_support"]),
        "pine_tp_relative_volume": _optional_float(row["tp_relative_volume_score"]),
        "pine_tp_time_of_day": _optional_float(row["tp_time_of_day_score"]),
        "pine_tp_range_position": _optional_float(row["tp_range_position_score"]),
        "pine_tp_score_semantics": "density_match_not_probability",
    }


def _market_fields(row: pd.Series) -> dict[str, float]:
    values = {
        name: _required_float(row[name], name)
        for name in ("open", "high", "low", "close", "volume")
    }
    return {**values, "mark_px": values["close"], "reference_price": values["close"]}


def _candidate_direction(row: pd.Series) -> str | None:
    long = bool(row["cs_long_onset"]) and int(row["trend_levels_state"]) == 1
    short = bool(row["cs_short_onset"]) and int(row["trend_levels_state"]) == -1
    if long and short:
        raise ValueError("Pine forward row has conflicting entry onsets")
    return "long" if long else "short" if short else None


def _decision_action(action: str, direction: str | None, fresh: bool) -> str:
    if action == "regime_history":
        return "history_only"
    if direction is None:
        return "observe_hold"
    return (
        f"observe_{direction}_onset"
        if fresh
        else f"stale_{direction}_onset_observe_only"
    )


def _decision_reason(row: pd.Series, direction: str | None) -> str:
    if direction is not None:
        return f"cs_{direction}_onset_trend_aligned"
    if bool(row["cs_long_onset"]) or bool(row["cs_short_onset"]):
        return "cs_onset_trend_not_aligned"
    return "no_cs_onset"


def _validated_minutes(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume", "source"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Pine forward minutes missing columns: {missing}")
    times = pd.DatetimeIndex(frame["timestamp"])
    if frame.empty or times.tz is None or times.has_duplicates:
        raise ValueError("Pine forward minutes require unique aware timestamps")
    if not times.is_monotonic_increasing:
        raise ValueError("Pine forward minutes must be chronological")
    if not frame["source"].eq("hl").all():
        raise ValueError("Pine forward minutes must come directly from Hyperliquid")
    return frame.reset_index(drop=True)


def _validated_features(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_REQUIRED_FEATURES.difference(frame.columns))
    if missing:
        raise ValueError(f"Pine forward features missing columns: {missing}")
    decisions = pd.DatetimeIndex(frame["decision_time_utc"])
    if frame.empty or decisions.tz is None or decisions.has_duplicates:
        raise ValueError("Pine forward decisions require unique aware timestamps")
    if not decisions.is_monotonic_increasing:
        raise ValueError("Pine forward decisions must be chronological")
    if not frame["execution_authority"].eq("none").all():
        raise ValueError("Pine forward features must have no execution authority")
    return frame.copy().reset_index(drop=True)


def _load_state(
    path: Path,
    symbol: str,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None, bool]:
    if not path.exists():
        return None, None, False
    activation: pd.Timestamp | None = None
    latest: pd.Timestamp | None = None
    session = False
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            row = _parse_ledger_row(raw, line_number, symbol)
            current_activation = _utc(pd.Timestamp(str(row["activated_at_utc"])))
            if activation is not None and current_activation != activation:
                raise ValueError("Pine forward activation changed within one ledger")
            activation = current_activation
            session |= row.get("action") == "session_start"
            if row.get("action") != "regime_observation":
                continue
            decision = _utc(pd.Timestamp(str(row["feed_ts"])))
            if latest is not None and decision <= latest:
                raise ValueError("Pine forward decisions must strictly increase")
            latest = decision
    return activation, latest, session


def _parse_ledger_row(raw: str, line: int, symbol: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Pine forward JSON at line {line}") from exc
    if not isinstance(value, dict) or value.get("symbol") != symbol:
        raise ValueError(f"Pine forward ledger line {line} has wrong symbol")
    if value.get("execution_authority") != "none":
        raise ValueError(f"Pine forward ledger line {line} has execution authority")
    return value


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


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError("Pine forward timestamps must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _required_float(value: object, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Pine forward {label} must be finite")
    return number


def _optional_float(value: object) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None
