"""ConvictionProvider + FeatureBuilder: metalabel scale-only (default off)."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.paper.conviction import (
    FeatureBuilder,
    FeatureBuildError,
    FixedConvictionProvider,
    MetalabelConvictionProvider,
)
from hypervector.sweep.sizing import RiskConfig, risk_pct_from_conviction


def test_fixed_provider():
    r = FixedConvictionProvider(0.4).resolve()
    assert r.conviction == 0.4
    assert r.source == "fixed"
    assert r.metalabel_p is None
    assert r.metalabel_bundle_id is None


def test_metalabel_scales_with_p(monkeypatch):
    class FakeML:
        root = type("R", (), {"name": "bundle"})()
        feature_names = ["a"]

        def predict_probability(self, features):
            return float(features["a"])

    fb = FeatureBuilder()
    prov = MetalabelConvictionProvider(FakeML(), fb, fixed_fallback=0.5, min_p=0.5)
    r = prov.resolve(features={"a": 0.8})
    assert r.conviction == 0.8
    assert r.source == "metalabel"
    assert r.metalabel_p == 0.8
    assert r.metalabel_bundle_id == "bundle"
    assert r.allow_entry is True


def test_metalabel_filters_below_min_p():
    class FakeML:
        root = type("R", (), {"name": "bundle"})()
        feature_names = ["a"]

        def predict_probability(self, features):
            return 0.35

    prov = MetalabelConvictionProvider(
        FakeML(), FeatureBuilder(), fixed_fallback=0.5, min_p=0.5, filter_entries=True
    )
    r = prov.resolve(features={"a": 0.35})
    assert r.allow_entry is False
    assert r.source == "metalabel_skip"
    assert r.conviction == 0.0
    assert r.metalabel_p == 0.35
    assert r.skip_reason is not None and "below_min" in r.skip_reason


def test_metalabel_scale_only_no_filter():
    class FakeML:
        root = type("R", (), {"name": "bundle"})()
        feature_names = ["a"]

        def predict_probability(self, features):
            return 0.2

    prov = MetalabelConvictionProvider(
        FakeML(), FeatureBuilder(), fixed_fallback=0.5, min_p=0.5, filter_entries=False
    )
    r = prov.resolve(features={"a": 0.2})
    assert r.allow_entry is True
    assert r.source == "metalabel"
    assert r.conviction == 0.2


def test_metalabel_observe_records_probability_without_changing_conviction():
    """Observe mode annotates a signal without changing sizing or eligibility."""

    class FakeML:
        root = type("R", (), {"name": "hypervelocity-long-v001"})()
        feature_names = ["a"]

        def predict_probability(self, features):
            return float(features["a"])

    provider = MetalabelConvictionProvider(
        FakeML(),
        FeatureBuilder(),
        fixed_fallback=0.5,
        mode="observe",
    )

    result = provider.resolve(features={"a": 0.2})

    assert result.conviction == 0.5
    assert result.source == "metalabel_observe"
    assert result.metalabel_p == 0.2
    assert result.metalabel_bundle_id == "hypervelocity-long-v001"
    assert result.allow_entry is True


def test_metalabel_fail_closed_when_filtering():
    class FakeML:
        root = type("R", (), {"name": "bundle"})()
        feature_names = ["a", "b"]

        def predict_probability(self, features):
            raise AssertionError("should not call")

    prov = MetalabelConvictionProvider(
        FakeML(),
        FeatureBuilder(),
        fixed_fallback=0.5,
        filter_entries=True,
        fail_closed=True,
    )
    r = prov.resolve(features={"a": 0.1})  # missing b
    assert r.allow_entry is False
    assert r.source == "fallback_skip"
    assert r.conviction == 0.0


def test_metalabel_fallback_on_predict_error_scale_only():
    class FakeML:
        root = type("R", (), {"name": "bundle"})()
        feature_names = ["a"]

        def predict_probability(self, features):
            raise RuntimeError("boom")

    prov = MetalabelConvictionProvider(
        FakeML(),
        FeatureBuilder(),
        fixed_fallback=0.33,
        filter_entries=False,
        fail_closed=False,
    )
    r = prov.resolve(features={"a": 0.9})
    assert r.conviction == 0.33
    assert r.source == "fallback_fixed"
    assert r.allow_entry is True


def test_higher_p_higher_risk_size():
    cfg = RiskConfig(risk_pct_min=0.01, risk_pct_max=0.05)
    assert risk_pct_from_conviction(0.2, cfg) < risk_pct_from_conviction(0.8, cfg)


def test_feature_builder_mapping_path():
    fb = FeatureBuilder()
    out = fb.build(
        feature_names=["x", "y"], bars=None, features={"x": 1.0, "y": 2.0, "z": 9.0}
    )
    assert out == {"x": 1.0, "y": 2.0}


def test_feature_builder_computes_from_ohlcv():
    """Paper path only has OHLCV columns — must compute metalabel schema."""
    import numpy as np
    from hypervector.ml.feature_matrix import FEATURE_NAMES

    n = 80
    rng = np.random.default_rng(0)
    close = 50_000 + np.cumsum(rng.normal(0, 10, size=n))
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 5,
            "low": close - 5,
            "close": close,
            "volume": 1.0,
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC"),
        }
    )
    out = FeatureBuilder().build(feature_names=list(FEATURE_NAMES), bars=bars)
    assert set(out) == set(FEATURE_NAMES)
    assert all(isinstance(v, float) for v in out.values())


def test_feature_builder_bars_last_row_only():
    fb = FeatureBuilder()
    bars = pd.DataFrame({"a": [0.1, 0.9], "b": [0.2, 0.8]})
    out = fb.build(feature_names=["a", "b"], bars=bars, features=None)
    assert out == {"a": 0.9, "b": 0.8}


def test_feature_builder_missing_columns_raises():
    fb = FeatureBuilder()
    bars = pd.DataFrame({"a": [1.0]})
    with pytest.raises(FeatureBuildError, match="missing"):
        fb.build(feature_names=["a", "b"], bars=bars, features=None)


def test_session_default_uses_fixed_conviction(tmp_path):
    """Metalabel default off → FixedConvictionProvider; decisions carry source=fixed."""
    from hypervector.data.sources import fixture_ohlcv
    from hypervector.export.phase2 import export_candidate
    from hypervector.paper.session import PaperSession

    track = "downtrend"
    export = export_candidate(
        tmp_path / "exports",
        run_id="cv01",
        meta={
            "symbol": "BTC",
            "timeframe": "1m",
            "track": track,
            "lookback_days": 30,
            "init_cash": 10_000.0,
            "tp_sl_mode": "fixed_rr",
            "exits": {
                "mode": "fixed_rr",
                "sl_pct": 0.01,
                "rr": 2.0,
                "atr_length": 14,
                "sl_atr_mult": 1.5,
                "trail_atr_mult": 2.0,
            },
            "costs": {
                "taker_fee": 0.00035,
                "slippage_bps": 2.0,
                "funding_rate_8h": 0.0001,
                "minutes_per_funding": 480,
            },
            "risk": {
                "risk_pct_min": 0.01,
                "risk_pct_max": 0.05,
                "default_conviction": 0.5,
                "max_size_frac": 1.0,
            },
            "data_provenance": {"sources": {"fixture": 50}},
        },
        params={
            "strategy": "crown_stack_short",
            "bbwp_lookback": 20,
            "bbwp_threshold": 20.0,
            "exit_mode": "fixed_rr",
            "role": track,
        },
        metrics={
            "net_pnl": 1.0,
            "total_return_pct": 0.1,
            "sharpe": 0.1,
            "trade_count": 1,
        },
        candidate_id="cv_fixed",
        strict=True,
    )
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        conviction=0.42,
        metalabel_enabled=False,
    )
    assert isinstance(session.conviction_provider, FixedConvictionProvider)
    ohlcv = fixture_ohlcv(n_bars=80, drift=-5.0, wave_period=20)
    session.process_frame(ohlcv, max_bars=80)
    # Force a fill record path via engine so decision fields are observable
    rec = session.engine.apply_market_fill(
        feed_ts="t-fill",
        action="enter_long",
        side="buy",
        qty=0.01,
        mark_px=50_000.0,
        conviction=0.42,
        conviction_source="fixed",
        metalabel_p=None,
        metalabel_bundle_id=None,
    )
    assert rec["conviction"] == 0.42
    assert rec["conviction_source"] == "fixed"
    assert rec.get("metalabel_p") is None
