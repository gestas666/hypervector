"""Immutable v51 index lifecycle command tests."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

_PROFILE = "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51"
_FINGERPRINT = "30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908"


@pytest.mark.evidence
def test_command_publishes_source_bound_authority_none_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Publish only after exact source prefixes and profile identity reconcile."""
    script = _script()
    args = _arguments(script, tmp_path)
    monkeypatch.setattr(
        script, "build_v51_index_shadow_lifecycle", lambda **_: _report()
    )

    report = script.run_command(
        args,
        candle_fetcher=_candle_fetcher,
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        mark_source=_MarkSource(),
    )

    persisted = json.loads(Path(args.output).read_text(encoding="utf-8"))
    assert report == persisted
    assert persisted["execution_authority"] == "none"
    assert persisted["input_evidence"]["journal_prefix"]["rows"] == 1
    assert persisted["input_evidence"]["book_ledger_prefix"]["rows"] == 1
    assert persisted["input_evidence"]["candles_15m"]["rows"] == 1
    assert persisted["input_evidence"]["candles_1m"]["rows"] == 1


@pytest.mark.evidence
def test_prefix_mutation_aborts_without_partial_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changing prospective journal cannot publish mixed-window evidence."""
    script = _script()
    args = _arguments(script, tmp_path)

    def mutate(**_kwargs: object) -> dict[str, object]:
        Path(args.journal).write_text("{}\n", encoding="utf-8")
        return _report()

    monkeypatch.setattr(script, "build_v51_index_shadow_lifecycle", mutate)
    with pytest.raises(ValueError, match="prefix changed"):
        script.run_command(
            args,
            candle_fetcher=_candle_fetcher,
            funding_fetcher=lambda *_args, **_kwargs: _funding(),
            mark_source=_MarkSource(),
        )

    assert not Path(args.output).exists()


def test_existing_output_aborts_before_public_acquisition(tmp_path: Path) -> None:
    """Immutable publication fails before any unsigned network work."""
    script = _script()
    args = _arguments(script, tmp_path)
    Path(args.output).write_text("reserved", encoding="utf-8")

    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        script.run_command(
            args,
            candle_fetcher=_FailingFetcher(),
            funding_fetcher=_FailingFetcher(),
            mark_source=_FailingMarkSource(),
        )


@pytest.mark.evidence
def test_command_fetches_signal_warmup_before_lifecycle_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Slow-EMA warmup precedes decisions without widening mark-risk scope."""
    script = _script()
    args = _arguments(script, tmp_path)
    fetcher = _RecordingCandleFetcher()
    marks = _RecordingMarkSource()
    monkeypatch.setattr(
        script, "build_v51_index_shadow_lifecycle", lambda **_: _report()
    )

    script.run_command(
        args,
        candle_fetcher=fetcher,
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        mark_source=marks,
    )

    lookbacks = dict(fetcher.lookbacks)
    expected_extra_days = 56 * 900_000 / 86_400_000
    assert lookbacks["15m"] == pytest.approx(lookbacks["1m"] + expected_extra_days)
    assert marks.start_ms == 1_800_000_000_000


def test_generator_identity_covers_the_shared_live_exit_binder() -> None:
    """Immutable evidence must change when live exit binding semantics change."""
    generator = _script()._generator_identity()

    assert "src/hypervector/research/hip3_shadow_execution_contract.py" in generator
    assert "src/hypervector/live/cohort_execution_plan.py" in generator


def _script() -> ModuleType:
    path = Path("scripts/v51_index_shadow_lifecycle_replay.py")
    spec = importlib.util.spec_from_file_location("v51_index_lifecycle_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("v51 index lifecycle script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _arguments(script: ModuleType, tmp_path: Path) -> argparse.Namespace:
    journal = tmp_path / "journal.jsonl"
    books = tmp_path / "books.jsonl"
    journal.write_text(
        json.dumps(
            {
                "decision": {
                    "decision_time_ms": 1_800_000_900_000,
                    "observed_at_ms": 1_800_000_900_500,
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    books.write_text(
        json.dumps(
            {
                "event_type": "book_observation",
                "payload": {"recv_ts_ms": 1_800_000_901_000},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return script.build_parser().parse_args(
        [
            "--symbol",
            "xyz:SP500",
            "--journal",
            str(journal),
            "--book-ledger",
            str(books),
            "--observed-at-ms",
            "1800100000000",
            "--output",
            str(tmp_path / "report.json"),
        ]
    )


class _MarkSource:
    def load(
        self, *, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        del data_root, start_ms, end_ms
        rows = tuple(
            {
                "symbol": symbol,
                "observed_ts_ms": value,
                "received_ts_ns": value * 1_000_000,
                "mark_price": 100.0,
                "source": "hyperliquid_ws_activeAssetCtx",
            }
            for value in (1_800_000_000_000, 1_800_000_001_000)
        )
        return rows, {"rows": len(rows), "files": []}

    def require_unchanged(self, evidence: dict[str, object]) -> None:
        assert evidence["rows"] == 2


class _RecordingMarkSource(_MarkSource):
    def __init__(self) -> None:
        self.start_ms: int | None = None

    def load(
        self, *, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        self.start_ms = start_ms
        return super().load(
            data_root=data_root,
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
        )


class _FailingMarkSource:
    def load(self, **_kwargs: object) -> tuple[object, object]:
        raise AssertionError("acquisition must not start")

    def require_unchanged(self, evidence: dict[str, object]) -> None:
        raise AssertionError(evidence)


class _FailingFetcher:
    def __call__(self, *_args: object, **_kwargs: object) -> pd.DataFrame:
        raise AssertionError("acquisition must not start")


class _RecordingCandleFetcher:
    def __init__(self) -> None:
        self.lookbacks: list[tuple[str, float]] = []

    def __call__(
        self, symbol: str, timeframe: str, lookback: float, *, end_ms: int
    ) -> pd.DataFrame:
        self.lookbacks.append((timeframe, lookback))
        return _candle_fetcher(symbol, timeframe, lookback, end_ms=end_ms)


def _candle_fetcher(
    _symbol: str, timeframe: str, _lookback: float, *, end_ms: int
) -> pd.DataFrame:
    del end_ms
    timestamp = (
        pd.Timestamp("2027-01-15T08:00:00Z")
        if timeframe == "15m"
        else pd.Timestamp("2027-01-15T08:15:00Z")
    )
    return pd.DataFrame(
        {
            "timestamp": [timestamp],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.0],
            "volume": [1.0],
            "source": ["hl"],
        }
    )


def _funding() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2027-01-15T08:00:00Z")],
            "funding_rate": [0.0],
            "source": ["hl_funding_history"],
        }
    )


def _report() -> dict[str, object]:
    return {
        "schema_version": "v51_index_shadow_lifecycle_replay_v1",
        "symbol": "xyz:SP500",
        "provider_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
        "profile_id": "sp500_fresh15_pressure_shadow_research_v3",
        "runtime_profile_id": _PROFILE,
        "runtime_profile_fingerprint": _FINGERPRINT,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
