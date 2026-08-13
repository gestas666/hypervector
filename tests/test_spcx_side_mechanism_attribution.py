"""Contracts for immutable SPCX side-mechanism attribution."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.spcx_side_mechanism_attribution import (
    build_gold_side_mechanism_attribution,
    build_spcx_side_mechanism_attribution,
)

_STRATEGY = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
_SYMBOL = "xyz:SPCX"
_GOLD_STRATEGY = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
_GOLD_SYMBOL = "xyz:GOLD"
_MODES = (
    "provider_exact",
    "alignment_onset",
    "next_bar_confirmation",
    "first_fast_ema_pullback",
)


def test_attribution_rejects_repeated_side_timing_split(tmp_path: Path) -> None:
    """Partition reversal must require a new mechanism identity."""
    report, trades = _source_files(tmp_path)

    artifact = build_spcx_side_mechanism_attribution(report, trades)

    assert artifact["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "model_authority": "none",
        "automatic_promotion": False,
        "automatic_retuning": False,
        "runtime_strategy_changed": False,
    }
    assert artifact["decision"] == (
        "tested_side_timing_set_falsified_requires_new_mechanism_identity"
    )
    assert artifact["assessment"]["stable_side_timing_arms"] == []
    assert artifact["assessment"]["tested_side_timing_arms"] == 8
    cells = artifact["cells"]
    development = cells["provider_exact|long|development|stress"]
    validation = cells["provider_exact|long|validation|stress"]
    assert development["trades"] == 2
    assert development["net_pnl_usd"] == pytest.approx(3.0)
    assert development["net_excluding_largest_winner_usd"] == pytest.approx(-2.0)
    assert validation["net_pnl_usd"] == pytest.approx(-1.0)
    assert len(cells) == 32


def test_attribution_fails_closed_when_trade_sidecar_changes(tmp_path: Path) -> None:
    """The source report hash must bind the exact trade rows under review."""
    report, trades = _source_files(tmp_path)
    frame = pd.read_parquet(trades)
    frame.loc[0, "net_pnl_usd"] = 999.0
    frame.to_parquet(trades, index=False)

    with pytest.raises(ValueError, match="trade sidecar evidence mismatch"):
        build_spcx_side_mechanism_attribution(report, trades)


def test_gold_attribution_rejects_static_side_timing_rescue(
    tmp_path: Path,
) -> None:
    """GOLD must not repeat a side split that reverses by partition."""
    report, trades = _source_files(
        tmp_path,
        strategy=_GOLD_STRATEGY,
        symbol=_GOLD_SYMBOL,
    )

    artifact = build_gold_side_mechanism_attribution(report, trades)

    assert artifact["route"] == {
        "strategy_id": _GOLD_STRATEGY,
        "symbol": _GOLD_SYMBOL,
    }
    assert artifact["schema_version"] == "gold_side_mechanism_attribution_v1"
    assert artifact["decision"] == (
        "tested_side_timing_set_falsified_requires_new_mechanism_identity"
    )
    assert artifact["assessment"]["stable_side_timing_arms"] == []
    assert artifact["assessment"]["tested_side_timing_arms"] == 8
    assert len(artifact["cells"]) == 32


def _source_files(
    root: Path,
    *,
    strategy: str = _STRATEGY,
    symbol: str = _SYMBOL,
) -> tuple[Path, Path]:
    report = root / "timing.json"
    trades = root / "timing.trades.parquet"
    frame = _trades(strategy=strategy, symbol=symbol)
    frame.to_parquet(trades, index=False)
    payload = {
        "schema_version": "hip3_entry_timing_challenger_v1",
        "report_only": True,
        "execution_authority": "none",
        "model_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "cases": {strategy: _case(strategy=strategy, symbol=symbol)},
        "trade_sidecar": {
            "path": str(trades.resolve()),
            "rows": len(frame),
            **file_evidence(trades),
        },
    }
    report.write_text(json.dumps(payload), encoding="utf-8")
    return report, trades


def _case(*, strategy: str, symbol: str) -> dict[str, object]:
    modes = {mode: {symbol: {}} for mode in _MODES}
    results = {
        phase: {friction: modes for friction in ("nominal", "stress")}
        for phase in ("development", "validation")
    }
    return {
        "strategy_id": strategy,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "timing_contract": {"fill_clock": "signal_then_next_open"},
        "windows": {
            "development_start_utc": "2026-05-17T22:30:00+00:00",
            "development_end_utc": "2026-07-05T08:15:00+00:00",
            "validation_end_utc": "2026-07-21T11:30:00+00:00",
            "holdout_end_utc": "2026-08-06T15:00:00+00:00",
        },
        "results": results,
        "holdout": {"status": "sealed_not_evaluated", "metrics_accessed": False},
    }


def _trades(*, strategy: str, symbol: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    values = {
        ("provider_exact", "long", "development"): (5.0, -2.0),
        ("provider_exact", "long", "validation"): (-1.0,),
        ("provider_exact", "short", "development"): (-2.0,),
        ("provider_exact", "short", "validation"): (3.0, -1.0),
        ("alignment_onset", "long", "development"): (2.0,),
        ("alignment_onset", "long", "validation"): (-1.0,),
        ("alignment_onset", "short", "development"): (-1.0,),
        ("alignment_onset", "short", "validation"): (2.0,),
        ("next_bar_confirmation", "long", "development"): (3.0,),
        ("next_bar_confirmation", "long", "validation"): (-1.0,),
        ("next_bar_confirmation", "short", "development"): (-1.0,),
        ("next_bar_confirmation", "short", "validation"): (2.0,),
    }
    for (mode, side, phase), outcomes in values.items():
        for friction in ("nominal", "stress"):
            for index, net in enumerate(outcomes):
                rows.append(
                    {
                        "strategy_id": strategy,
                        "symbol": symbol,
                        "phase": phase,
                        "friction": friction,
                        "timing_mode": mode,
                        "direction": side,
                        "entry_time_ms": index + 1,
                        "net_pnl_usd": net,
                    }
                )
    return pd.DataFrame.from_records(rows)
