"""Contracts for the strict/legacy source-session gate factorial."""

from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_session_factorial.py")
    assert path.is_file(), "source-session factorial script is missing"
    spec = importlib.util.spec_from_file_location("source_session_factorial", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load source-session factorial: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _labels(index: pd.DatetimeIndex, *, third_onset: bool) -> pd.DataFrame:
    primary = [
        "RANGE",
        "TREND_DOWN",
        "RANGE",
        "TREND_DOWN",
        "RANGE",
        "TREND_DOWN" if third_onset else "RANGE",
        "RANGE",
    ]
    return pd.DataFrame(
        {
            "available_at": index + pd.Timedelta(minutes=5),
            "primary_code": primary,
            "secondary_code": [None] * len(index),
            "confidence": [0.5, 0.8, 0.5, 0.5, 0.5, 0.9, 0.5],
        },
        index=index,
    )


def test_factorial_separates_revision_density_from_tuned_gates() -> None:
    """Each factor combination must preserve its distinct causal signal set."""
    module = _load_script()
    index = pd.date_range("2026-05-01T06:00:00Z", periods=7, freq="5min")
    bars = pd.DataFrame(
        {"open": 100.0, "high": 100.1, "low": 99.9},
        index=index,
    )

    candidates = module._candidate_signals(
        _labels(index, third_onset=False),
        _labels(index, third_onset=True),
        bars,
        datetime(2026, 5, 1, 6, tzinfo=UTC),
        datetime(2026, 5, 1, 7, tzinfo=UTC),
    )

    assert {name: len(signals) for name, signals in candidates.items()} == {
        "strict_tuned": 1,
        "legacy_tuned": 2,
        "strict_range_relaxed": 1,
        "strict_confidence_relaxed": 2,
        "strict_source_native": 2,
        "legacy_source_native": 3,
    }


def test_factorial_resamples_minute_candles_before_range_selection() -> None:
    """The operational range gate is defined on completed five-minute bars."""
    module = _load_script()
    index = pd.date_range("2026-05-01T06:00:00Z", periods=5, freq="1min")
    minute_bars = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 106.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.5, 101.5, 102.5, 103.5, 105.0],
            "volume": [1.0, 2.0, 3.0, 4.0, 5.0],
        },
        index=index,
    )

    signal_bars = module._signal_bars(minute_bars)

    assert list(signal_bars.index) == [index[0]]
    assert signal_bars.iloc[0].to_dict() == {
        "open": 100.0,
        "high": 106.0,
        "low": 99.0,
        "close": 105.0,
        "volume": 15.0,
    }


def test_factorial_loads_complete_signal_bars_across_native_gaps(
    tmp_path: Path,
) -> None:
    """Regime gaps must remain absent rather than becoming synthetic candles."""
    module = _load_script()
    first = pd.date_range("2025-05-01T00:00:00Z", periods=5, freq="1min")
    second = pd.date_range("2025-05-01T01:00:00Z", periods=5, freq="1min")
    timestamps = first.append(second)
    path = tmp_path / "native-gapped.parquet"
    pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl_native_candle",
        }
    ).to_parquet(path, index=False)

    signal_bars = module._load_signal_bars(path)

    assert signal_bars.index.tolist() == [first[0], second[0]]


def test_factorial_contract_keeps_risk_fixed_and_has_no_authority() -> None:
    """Only revision and gate minima may vary across the four report lanes."""
    module = _load_script()
    configs = module._configs(15_000.0, "trade-through")
    contract = module._contract(15_000.0, "trade-through")

    assert tuple(configs) == (
        "strict_tuned",
        "legacy_tuned",
        "strict_source_native",
        "legacy_source_native",
    )
    assert len(set(configs.values())) == 1
    config = configs["strict_tuned"]
    assert config.margin_fraction == 0.35
    assert config.leverage == 30.0
    assert config.target_margin_pct == 8.0
    assert contract["execution_authority"] == "none"
    assert contract["model_authority"] == "observe"
    assert contract["entry_session_utc"] == "[06:00,15:00)"
    assert contract["entry_session_clock"] == "decision_time_utc"
    assert contract["parameter_selection_allowed"] is False


def test_strict_only_candidate_set_excludes_legacy_replays() -> None:
    """Older validation may skip legacy lanes without changing strict configs."""
    module = _load_script()

    assert module._candidate_names("strict-only") == (
        "strict_tuned",
        "strict_source_native",
    )
    configs = module._configs(15_000.0, "trade-through", "strict-only")
    contract = module._contract(15_000.0, "trade-through", "strict-only")

    assert tuple(configs) == ("strict_tuned", "strict_source_native")
    assert len(set(configs.values())) == 1
    assert contract["candidate_set"] == "strict-only"


def test_strict_tuned_only_candidate_set_supports_continuous_validation() -> None:
    """A year replay may run only the already-frozen tuned control."""
    module = _load_script()

    assert module._candidate_names("strict-tuned-only") == ("strict_tuned",)
    configs = module._configs(15_000.0, "trade-through", "strict-tuned-only")

    assert tuple(configs) == ("strict_tuned",)


def test_strict_one_factor_set_isolates_each_entry_minimum() -> None:
    """The one-factor replay must change only one minimum per challenger."""
    module = _load_script()

    assert module._candidate_names("strict-one-factor") == (
        "strict_tuned",
        "strict_range_relaxed",
        "strict_confidence_relaxed",
    )
    contract = module._contract(15_000.0, "trade-through", "strict-one-factor")

    assert contract["strict_range_relaxed_minimum_confidence"] == 0.70
    assert contract["strict_range_relaxed_minimum_range_bps"] == 0.0
    assert contract["strict_confidence_relaxed_minimum_confidence"] == 0.0
    assert contract["strict_confidence_relaxed_minimum_range_bps"] == 12.0


def test_strict_range_pair_excludes_confidence_relaxation() -> None:
    """Backward validation compares only the frozen and range-relaxed arms."""
    module = _load_script()

    assert module._candidate_names("strict-range-pair") == (
        "strict_tuned",
        "strict_range_relaxed",
    )
    configs = module._configs(15_000.0, "trade-through", "strict-range-pair")
    contract = module._contract(15_000.0, "trade-through", "strict-range-pair")

    assert tuple(configs) == ("strict_tuned", "strict_range_relaxed")
    assert len(set(configs.values())) == 1
    assert contract["legacy_revision"] is None


def test_strict_range_pair_does_not_require_legacy_labels(tmp_path: Path) -> None:
    """A strict-only experiment must not depend on an unused source revision."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--bars",
            str(tmp_path / "bars.parquet"),
            "--strict-labels",
            str(tmp_path / "strict.parquet"),
            "--strict-metadata",
            str(tmp_path / "strict.json"),
            "--research-database",
            str(tmp_path / "research.duckdb"),
            "--start",
            "2025-04-28T00:00:00Z",
            "--end",
            "2025-05-28T00:00:00Z",
            "--price-context",
            str(tmp_path / "prices.parquet"),
            "--funding-context",
            str(tmp_path / "funding.parquet"),
            "--candidate-set",
            "strict-range-pair",
            "--fill-rule",
            "trade-through",
            "--out",
            str(tmp_path / "report.json"),
        ]
    )

    assert args.legacy_labels is None
    assert args.legacy_metadata is None


def test_strict_range_pair_builds_without_legacy_dataframe() -> None:
    """Only requested candidates may be materialized from label evidence."""
    module = _load_script()
    index = pd.date_range("2026-05-01T06:00:00Z", periods=7, freq="5min")
    bars = pd.DataFrame(
        {"open": 100.0, "high": 100.1, "low": 99.9},
        index=index,
    )

    candidates = module._candidate_signals(
        _labels(index, third_onset=False),
        None,
        bars,
        datetime(2026, 5, 1, 6, tzinfo=UTC),
        datetime(2026, 5, 1, 7, tzinfo=UTC),
        candidate_set="strict-range-pair",
    )

    assert tuple(candidates) == ("strict_tuned", "strict_range_relaxed")


def test_legacy_candidate_without_legacy_evidence_fails() -> None:
    """A requested legacy arm must fail explicitly when its evidence is absent."""
    module = _load_script()
    index = pd.date_range("2026-05-01T06:00:00Z", periods=7, freq="5min")
    bars = pd.DataFrame(
        {"open": 100.0, "high": 100.1, "low": 99.9},
        index=index,
    )

    with pytest.raises(ValueError, match="legacy labels are required"):
        module._candidate_signals(
            _labels(index, third_onset=False),
            None,
            bars,
            datetime(2026, 5, 1, 6, tzinfo=UTC),
            datetime(2026, 5, 1, 7, tzinfo=UTC),
        )


def test_strict_factorial_set_includes_tuned_and_every_gate_removal() -> None:
    """One event pass must compare tuned, one-factor, and both-relaxed lanes."""
    module = _load_script()

    assert module._candidate_names("strict-factorial") == (
        "strict_tuned",
        "strict_range_relaxed",
        "strict_confidence_relaxed",
        "strict_source_native",
    )
    configs = module._configs(15_000.0, "trade-through", "strict-factorial")

    assert tuple(configs) == module._candidate_names("strict-factorial")
    assert len(set(configs.values())) == 1


def test_all_day_entry_session_preserves_every_decision() -> None:
    """The 24/7 control must not inherit the fixed session filter."""
    module = _load_script()
    signals = tuple(
        module.SourceSignal(f"2026-05-01T{hour:02d}:00:00+00:00")
        for hour in (5, 6, 14, 15)
    )

    assert module._entry_signals(signals, "24/7") == signals
    assert [
        signal.decision_time_utc
        for signal in module._entry_signals(signals, "[06:00,15:00)")
    ] == [
        "2026-05-01T06:00:00+00:00",
        "2026-05-01T14:00:00+00:00",
    ]


def test_factorial_summary_surfaces_context_gaps() -> None:
    """Top-level arm comparisons must not hide stale liquidation context."""
    module = _load_script()
    report = module.MakerReplayReport(
        fill_rule="trade-through",
        snapshots=0,
        market_trade_prints=0,
        submitted_entries=0,
        entry_fills=0,
        expired_entries=0,
        canceled_entries=0,
        pending_orders=0,
        completed_trades=0,
        open_positions=0,
        initial_equity=15_000.0,
        final_equity=15_000.0,
        submission_times_utc=(),
        trades=(),
        lifecycles=(),
        limitations=(),
        stale_mark_events=3,
        missing_oracle_settlements=1,
        execution_economics_conclusive=False,
    )

    summary = module._summary(report)

    assert summary["stale_mark_events"] == 3
    assert summary["missing_oracle_settlements"] == 1
    assert summary["execution_economics_conclusive"] is False
