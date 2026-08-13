"""Tests for the immutable ETH pullback metalabel command."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pandas as pd

SCRIPT = Path(__file__).parents[1] / "scripts" / "eth_pullback_metalabel_challenger.py"


def _load_script() -> object:
    spec = spec_from_file_location("eth_pullback_metalabel_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("ETH metalabel script could not be loaded")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_publishes_report_only_artifact_and_both_prediction_phases(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    """The command must preserve development OOS and confirmation predictions."""
    module = _load_script()
    bars = tmp_path / "bars.parquet"
    funding = tmp_path / "funding.parquet"
    pd.DataFrame({"timestamp": ["2026-01-01T00:00:00Z"]}).to_parquet(bars)
    pd.DataFrame({"time": [1], "fundingRate": [0.0]}).to_parquet(funding)
    fake = _fake_result()
    monkeypatch.setattr(
        module, "replay_eth_precompression_pullback", lambda *_: _replay()
    )
    monkeypatch.setattr(module, "build_eth_pullback_model_rows", lambda *_: _rows())
    monkeypatch.setattr(
        module, "evaluate_eth_pullback_metalabel", lambda *_a, **_k: fake
    )

    artifact, predictions = module.run(
        argparse.Namespace(
            bars=bars,
            funding=funding,
            out=tmp_path / "result.json",
            predictions_out=tmp_path / "predictions.parquet",
        )
    )

    assert artifact["execution_authority"] == "none"
    assert artifact["automatic_promotion"] is False
    assert artifact["runtime_strategy_changed"] is False
    assert (
        artifact["strategy_id"]
        == "eth_breakout_precompression_pullback_bidirectional_v1"
    )
    assert set(predictions["phase"]) == {
        "development_oos",
        "opened_final_confirmation",
    }
    assert predictions["side_sign"].notna().all()
    assert predictions["breakout_relation"].notna().all()
    assert artifact["prediction_rows"] == 2
    assert set(artifact["data_evidence"]) == {str(bars), str(funding)}


def test_script_rejects_existing_outputs_before_replay(tmp_path: Path) -> None:
    """Immutable evidence paths cannot be silently overwritten."""
    module = _load_script()
    bars = tmp_path / "bars.parquet"
    funding = tmp_path / "funding.parquet"
    out = tmp_path / "existing.json"
    bars.touch()
    funding.touch()
    out.touch()

    try:
        module.run(
            argparse.Namespace(
                bars=bars,
                funding=funding,
                out=out,
                predictions_out=tmp_path / "predictions.parquet",
            )
        )
    except FileExistsError as exc:
        assert "immutable ETH metalabel output exists" in str(exc)
    else:
        raise AssertionError("existing immutable output was accepted")


def _fake_result() -> object:
    class _Development:
        predictions = pd.DataFrame(
            {
                "signal_time_utc": [pd.Timestamp("2026-01-01", tz="UTC")],
                "candidate": ["ridge_return"],
            }
        )

    class _Result:
        development = _Development()
        final_predictions = pd.DataFrame(
            {
                "signal_time_utc": [pd.Timestamp("2026-02-01", tz="UTC")],
                "candidate": ["ridge_return"],
            }
        )
        report = {
            "contract": {
                "execution_authority": "none",
                "automatic_promotion": False,
                "runtime_strategy_changed": False,
            }
        }

    return _Result()


def _replay() -> object:
    class _Report:
        trades = ()

    class _Replay:
        report = _Report()
        market = pd.DataFrame()
        market_evidence = {"bars": 1}
        policy_evidence = {"signals": 1}

    return _Replay()


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_time_utc": [
                pd.Timestamp("2026-01-01", tz="UTC"),
                pd.Timestamp("2026-02-01", tz="UTC"),
            ],
            "side_sign": [1.0, -1.0],
            "breakout_relation_aligned": [1.0, 0.0],
        }
    )
