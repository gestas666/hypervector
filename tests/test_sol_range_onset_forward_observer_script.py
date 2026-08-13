from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Protocol

import pandas as pd
from pytest import MonkeyPatch

from hypervector.data.hl_event_stream import RecordedEvent
from hypervector.data.hl_events import BookLevel, L2SnapshotEvent
from hypervector.research.range_onset_forward_observer import (
    RangeOnsetForwardObserver,
)
from hypervector.research.sol_range_onset_shadow import SolRangeOnsetShadowEngine
from hypervector.research.sol_range_onset_shadow_ledger import SolShadowLedger
from hypervector.research.sol_range_onset_shadow_models import (
    SharedCapitalSnapshot,
    SolShadowConfig,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "sol_range_onset_forward_observer.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("sol_range_onset_forward_observer", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _raw_bars(rows: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-07-31T06:00:00Z", periods=rows, freq="1min"
            ),
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [10.0, 11.0, 12.0],
            "source": ["hl"] * rows,
        }
    )


def test_prepare_frames_removes_incomplete_bar(monkeypatch: MonkeyPatch) -> None:
    module = _load_module()

    def signals(bars: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            False,
            index=bars.index,
            columns=["long_entry", "short_entry", "long_exit", "short_exit"],
        )

    def regimes(bars: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "primary_regime": "RANGE",
                "state_1m": "RANGE",
                "state_5m": "RANGE",
                "context_15m": "RANGE",
                "confidence": 0.5,
            },
            index=bars.index,
        )

    monkeypatch.setattr(module, "build_range_onset_signals", signals)
    monkeypatch.setattr(module, "classify_multitimeframe", regimes)

    bars, signal_frame, regime_frame = module.prepare_observation_frames(
        _raw_bars(),
        observed_at=pd.Timestamp("2026-07-31T06:02:30Z"),
    )

    assert list(bars.index) == list(
        pd.date_range("2026-07-31T06:00:00Z", periods=2, freq="1min")
    )
    assert signal_frame.index.equals(bars.index)
    assert regime_frame.index.equals(bars.index)


def test_observe_cycle_is_annotation_only(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    module = _load_module()

    def signals(bars: pd.DataFrame) -> pd.DataFrame:
        result = pd.DataFrame(
            False,
            index=bars.index,
            columns=["long_entry", "short_entry", "long_exit", "short_exit"],
        )
        result["structural_direction"] = "long"
        result["regime_admitted"] = True
        result.iloc[-1, result.columns.get_loc("long_entry")] = True
        return result

    def regimes(bars: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "primary_regime": "RANGE",
                "state_1m": "RANGE",
                "state_5m": "RANGE",
                "context_15m": "TREND_UP",
                "confidence": 0.7,
            },
            index=bars.index,
        )

    monkeypatch.setattr(module, "build_range_onset_signals", signals)
    monkeypatch.setattr(module, "classify_multitimeframe", regimes)
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T06:00:00Z"),
        ledger_path=tmp_path / "decisions.jsonl",
    )

    decisions = module.observe_cycle(
        observer,
        _raw_bars(),
        observed_at=pd.Timestamp("2026-07-31T06:02:30Z"),
    )

    assert len(decisions) == 2
    assert decisions[-1]["long_entry"] is True
    assert decisions[-1]["execution_authority"] == "none"
    assert decisions[-1]["submitted"] is False
    assert decisions[-1]["place_attempted"] is False


def test_parser_has_no_live_or_submit_flags() -> None:
    parser = _load_module().build_parser()
    option_strings = {
        option for action in parser._actions for option in action.option_strings
    }

    assert "--enabled" not in option_strings
    assert "--live" not in option_strings
    assert "--submit" not in option_strings
    args = parser.parse_args([])
    assert args.shadow_ledger == Path(
        "data/research/forward/sol_range_onset/shadow.jsonl"
    )
    assert args.btc_ledger == Path("data/paper/decisions/decisions.jsonl")
    assert args.config is None


def test_canary_profile_resolves_separate_150_dollar_shadow_runtime() -> None:
    """The canary profile must not inherit the $15,000 shared research capital."""
    module = _load_module()
    args = module.build_parser().parse_args(
        ["--config", "configs/sol_range_onset_canary.toml"]
    )

    runtime = module._resolve_runtime(args)
    capital = runtime.capital_snapshot(1_785_477_721_000)

    assert runtime.config.initial_shared_equity_usd == 150.0
    assert runtime.config.notional_cap_usd == 22.5
    assert runtime.config.stop_bps == 80.0
    assert runtime.ledger == Path(
        "data/research/forward/sol_range_onset_canary/decisions.jsonl"
    )
    assert runtime.shadow_ledger == Path(
        "data/research/forward/sol_range_onset_canary/shadow.jsonl"
    )
    assert runtime.identity.capital_source == "standalone_canary"
    assert runtime.identity.portfolio_purpose == "canary_validation"
    assert capital is not None
    assert capital.equity_usd == 150.0
    assert capital.reserved_margin_usd == 0.0
    assert capital.source_run_id == "sol-canary-standalone"


class _Consumer(Protocol):
    def ingest_hyperliquid_event(self, event: RecordedEvent) -> str | None: ...


class _OneEventPump:
    def __init__(self, event: RecordedEvent) -> None:
        self._event = event

    def pump(self, consumer: _Consumer) -> int:
        consumer.ingest_hyperliquid_event(self._event)
        return 1


def _signal_row() -> dict[str, object]:
    return {
        "symbol": "SOL",
        "decision_time_utc": "2026-07-31T06:02:00+00:00",
        "reference_price": 100.0,
        "long_entry": True,
        "short_entry": False,
        "long_exit": False,
        "short_exit": False,
        "fresh_at_observation": True,
    }


def _book() -> L2SnapshotEvent:
    timestamp_ms = 1_785_477_720_100
    return L2SnapshotEvent(
        symbol="SOL",
        exchange_ts_ms=timestamp_ms,
        received_ts_ns=timestamp_ms * 1_000_000,
        bids=(BookLevel(99.9, 40.0, 1),),
        asks=(BookLevel(100.1, 40.0, 1),),
    )


def test_shadow_batch_ingests_decision_before_depth_and_persists_state(
    tmp_path: Path,
) -> None:
    module = _load_module()
    config = SolShadowConfig()
    ledger = SolShadowLedger(tmp_path / "shadow.jsonl", config)
    engine = SolRangeOnsetShadowEngine(config)
    consumer = module._ShadowConsumer(engine)
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T06:00:00Z"),
        ledger_path=tmp_path / "decisions.jsonl",
    )
    capital = SharedCapitalSnapshot(
        1_785_477_720_000,
        15_000.0,
        0.0,
        "btc-run",
    )

    records = module._process_shadow_batch(
        engine=engine,
        ledger=ledger,
        consumer=consumer,
        pump=_OneEventPump(_book()),
        decisions=(_signal_row(),),
        capital=capital,
        recorded_at_ms=1_785_477_721_000,
        observer=observer,
    )

    assert [record["action"] for record in records] == ["entry_filled"]
    assert engine.snapshot.position is not None
    assert engine.snapshot.position.direction == "long"
    restored = SolShadowLedger(tmp_path / "shadow.jsonl", config).restore_engine()
    assert restored.snapshot == engine.snapshot
    rows = [
        json.loads(line)
        for line in (tmp_path / "decisions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [row["action"] for row in rows] == [
        "enter_long",
        "book_observation",
        "shadow_state",
    ]
    assert rows[0]["position_qty"] > 0.0
    assert rows[-1]["symbol"] == "SOL"


def test_shadow_batch_has_no_fake_capital_fallback(tmp_path: Path) -> None:
    module = _load_module()
    config = SolShadowConfig()
    ledger = SolShadowLedger(tmp_path / "shadow.jsonl", config)
    engine = SolRangeOnsetShadowEngine(config)
    consumer = module._ShadowConsumer(engine)
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T06:00:00Z"),
        ledger_path=tmp_path / "decisions.jsonl",
    )

    records = module._process_shadow_batch(
        engine=engine,
        ledger=ledger,
        consumer=consumer,
        pump=_OneEventPump(_book()),
        decisions=(_signal_row(),),
        capital=None,
        recorded_at_ms=1_785_477_721_000,
        observer=observer,
    )

    assert engine.snapshot.position is None
    assert records[-1]["action"] == "entry_capital_unavailable"


def test_shadow_batch_does_not_retro_enter_a_stale_decision(tmp_path: Path) -> None:
    module = _load_module()
    config = SolShadowConfig()
    ledger = SolShadowLedger(tmp_path / "shadow.jsonl", config)
    engine = SolRangeOnsetShadowEngine(config)
    consumer = module._ShadowConsumer(engine)
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp("2026-07-31T06:00:00Z"),
        ledger_path=tmp_path / "decisions.jsonl",
    )
    capital = SharedCapitalSnapshot(
        1_785_477_720_000,
        15_000.0,
        0.0,
        "btc-run",
    )
    stale = {**_signal_row(), "fresh_at_observation": False}

    records = module._process_shadow_batch(
        engine=engine,
        ledger=ledger,
        consumer=consumer,
        pump=_OneEventPump(_book()),
        decisions=(stale,),
        capital=capital,
        recorded_at_ms=1_785_477_721_000,
        observer=observer,
    )

    assert engine.snapshot.position is None
    assert records[-1]["action"] == "stale_entry_ignored"
