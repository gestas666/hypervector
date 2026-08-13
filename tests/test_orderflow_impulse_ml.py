"""Purged annotation-model tests for one-minute order-flow impulse events."""

from __future__ import annotations

import pandas as pd

from hypervector.research.orderflow_impulse_events import MODEL_FEATURE_NAMES
from hypervector.research.orderflow_impulse_ml import (
    evaluate_orderflow_impulse_models,
)


def _rows(events: int = 180) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    for event in range(events):
        signal = start + pd.Timedelta(minutes=event * 20)
        strength = (event % 20) / 20.0
        for side, sign in (("long", 1.0), ("short", -1.0)):
            record: dict[str, object] = {
                "event_id": f"BTC:{event}",
                "symbol": "BTC",
                "arm": "continuation_all" if side == "long" else "reversion_all",
                "side": side,
                "available_at_utc": signal,
                "entry_time_utc": signal,
                "outcome_time_utc": signal + pd.Timedelta(minutes=15),
                "status": "timeout",
                "net_return_bps_nominal": sign * (strength * 40.0 - 20.0),
            }
            record.update({name: strength for name in MODEL_FEATURE_NAMES})
            record["body_return_bps"] = 10.0
            record["trade_flow_imbalance"] = 0.5
            record["imbalance_5_last"] = 0.4
            record["imbalance_5_delta"] = 0.2
            record["micro_price_delta_bps"] = 0.1
            records.append(record)
    return (
        pd.DataFrame(records)
        .sort_values(["available_at_utc", "side"])
        .reset_index(drop=True)
    )


def test_models_emit_purged_oos_predictions_and_fixed_selection() -> None:
    """Ridge and LightGBM must produce only out-of-sample annotated rows."""
    result = evaluate_orderflow_impulse_models(_rows())

    assert set(result.predictions["candidate"]) == {
        "ridge_net_return",
        "lightgbm_net_return",
    }
    assert result.predictions["fold_id"].nunique() == 3
    assert result.predictions["prediction"].notna().all()
    assert set(result.selected["candidate"]) == {
        "ridge_net_return",
        "lightgbm_net_return",
    }
    for fold in result.folds:
        rows = _rows()
        train_outcome = rows.iloc[fold.train_indices]["outcome_time_utc"].max()
        test_signal = rows.iloc[fold.test_indices]["available_at_utc"].min()
        assert train_outcome < test_signal - pd.Timedelta(minutes=15)


def test_model_contract_requires_exactly_two_sides_per_event() -> None:
    """A missing side must fail rather than become a hidden directional gate."""
    rows = _rows().iloc[1:].reset_index(drop=True)

    try:
        evaluate_orderflow_impulse_models(rows)
    except ValueError as error:
        assert "exactly one long and short" in str(error)
    else:
        raise AssertionError("missing side was not rejected")
