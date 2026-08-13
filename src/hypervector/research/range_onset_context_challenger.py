"""Causal entry-context challengers for the range-onset strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

BASELINE_CANDIDATE = "current_contract"
_COMPONENT_CANDIDATE = "component_alignment_gte_neg05"
_MTF_CANDIDATE = "dual_mtf_not_opposed"
_ONE_MINUTE_CANDIDATE = "state_1m_not_opposed"
_COMPONENT_THRESHOLD = -0.5
_COMPONENT_WEIGHTS = {
    "ema_21_55_direction": 1.0,
    "sma_100_200_direction": 1.0,
    "cipher_a_direction": 1.0,
    "harsi_direction": 1.0,
    "mtf_5m_bias": 2.0,
    "mtf_15m_bias": 2.0,
    "trend_slope_bps": 1.0,
}
_SIGNAL_COLUMNS = frozenset({"long_entry", "short_entry"})
_REGIME_COLUMNS = frozenset({"state_1m"})


def build_context_signal_variants(
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
    components: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Return the current rule and three fixed report-only entry challengers."""
    _validate_inputs(signals, regimes, components)
    long_entry = signals["long_entry"].astype(bool)
    short_entry = signals["short_entry"].astype(bool)
    source_entry = long_entry | short_entry
    side_sign = long_entry.astype(float) - short_entry.astype(float)
    numeric = components.loc[:, list(_COMPONENT_WEIGHTS)].astype(float)
    unavailable = source_entry & ~np.isfinite(numeric).all(axis=1)
    if unavailable.any():
        raise ValueError(
            f"context evidence unavailable at {int(unavailable.sum())} entry rows"
        )
    score = _component_alignment(numeric, side_sign).where(source_entry)
    dual_mtf_opposed = _dual_mtf_opposition(numeric, side_sign) & source_entry
    one_minute_opposed = (long_entry & regimes["state_1m"].eq("TREND_DOWN")) | (
        short_entry & regimes["state_1m"].eq("TREND_UP")
    )
    admission = {
        BASELINE_CANDIDATE: source_entry,
        _COMPONENT_CANDIDATE: source_entry & score.ge(_COMPONENT_THRESHOLD),
        _MTF_CANDIDATE: source_entry & ~dual_mtf_opposed,
        _ONE_MINUTE_CANDIDATE: source_entry & ~one_minute_opposed,
    }
    return {
        name: _annotated_variant(
            signals,
            name,
            allowed,
            long_entry,
            short_entry,
            score,
            dual_mtf_opposed,
            one_minute_opposed,
        )
        for name, allowed in admission.items()
    }


def _validate_inputs(
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
    components: pd.DataFrame,
) -> None:
    if not signals.index.equals(regimes.index) or not signals.index.equals(
        components.index
    ):
        raise ValueError("signals, regimes, and components require the same index")
    _require_columns(signals, _SIGNAL_COLUMNS, "signals")
    _require_columns(regimes, _REGIME_COLUMNS, "regimes")
    _require_columns(components, frozenset(_COMPONENT_WEIGHTS), "components")
    if (signals["long_entry"].astype(bool) & signals["short_entry"].astype(bool)).any():
        raise ValueError("context challengers do not accept conflicting source entries")


def _require_columns(
    frame: pd.DataFrame,
    required: frozenset[str],
    label: str,
) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{label} missing context columns: {missing}")


def _component_alignment(
    components: pd.DataFrame,
    side_sign: pd.Series,
) -> pd.Series:
    weighted = pd.Series(0.0, index=components.index)
    for name, weight in _COMPONENT_WEIGHTS.items():
        weighted += np.sign(components[name]) * weight
    return weighted * side_sign / sum(_COMPONENT_WEIGHTS.values())


def _dual_mtf_opposition(
    components: pd.DataFrame,
    side_sign: pd.Series,
) -> pd.Series:
    five = np.sign(components["mtf_5m_bias"]) * side_sign
    fifteen = np.sign(components["mtf_15m_bias"]) * side_sign
    return five.lt(0.0) & fifteen.lt(0.0)


def _annotated_variant(
    signals: pd.DataFrame,
    candidate: str,
    allowed: pd.Series,
    long_entry: pd.Series,
    short_entry: pd.Series,
    score: pd.Series,
    dual_mtf_opposed: pd.Series,
    one_minute_opposed: pd.Series,
) -> pd.DataFrame:
    result = signals.copy()
    result["long_entry"] = long_entry & allowed
    result["short_entry"] = short_entry & allowed
    result["context_candidate_id"] = candidate
    result["context_source_entry"] = long_entry | short_entry
    result["context_component_alignment_score"] = score
    result["context_dual_mtf_opposed"] = dual_mtf_opposed
    result["context_state_1m_opposed"] = one_minute_opposed
    return result
