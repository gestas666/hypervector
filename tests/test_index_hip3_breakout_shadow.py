"""Exact pre-close pressure contracts for the repaired index shadow routes."""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest

from hypervector.live.hip3_breakout_shadow_specs import (
    SP500_SHADOW_SPEC,
    SPCX_SHADOW_SPEC,
)
from hypervector.live.mu_hip3_preclose_pressure import (
    MU_PRESSURE_SOURCE,
    MuAssetLedgerBinding,
    MuHip3LedgerPreclosePressureSource,
)
from hypervector.live.mu_hip3_breakout_shadow_runner import (
    MuHip3ShadowPaths,
    MuHip3ShadowPollResult,
    _write_status,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)

_OPEN_MS = 1_786_565_700_000
_CLOSE_MS = _OPEN_MS + 900_000
_SCRIPT = Path("src/hypervector/operations/index_hip3_breakout_shadow_observe.py")


def _script_module() -> ModuleType:
    spec = spec_from_file_location("index_hip3_shadow_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _book(exchange_ms: int, recv_ms: int) -> dict[str, object]:
    return {
        "source": MU_PRESSURE_SOURCE,
        "exchange_ts_ms": exchange_ms,
        "recv_ts_ms": recv_ms,
        "bids": [
            {"price": 99.0 - position * 0.1, "size": 3.0} for position in range(10)
        ],
        "asks": [
            {"price": 101.0 + position * 0.1, "size": 1.0} for position in range(10)
        ],
    }


def _write_asset(path: Path, symbol: str, books: list[dict[str, object]]) -> None:
    rows = (
        {
            "event_type": "book_observation",
            "profile_id": f"index_fresh15_shadow_{symbol.lower()}",
            "payload": book,
        }
        for book in books
    )
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _source(tmp_path: Path, symbol: str, books: list[dict[str, object]]):
    token = symbol.lower()
    asset = tmp_path / f"{token}.jsonl"
    cohort = tmp_path / "cohort.jsonl"
    _write_asset(asset, symbol, books)
    cohort.write_text("", encoding="utf-8")
    return MuHip3LedgerPreclosePressureSource(
        asset_binding=MuAssetLedgerBinding(
            symbol,
            asset,
            f"index_fresh15_shadow_{token}",
        ),
        cohort_ledger=cohort,
    )


@pytest.mark.parametrize("symbol", ["xyz:SP500", "xyz:SPCX"])
def test_index_pressure_uses_exchange_age_and_requires_two_snapshots(
    tmp_path: Path,
    symbol: str,
) -> None:
    """Fast receipt cannot make an exchange-stale completed bar eligible."""
    source = _source(
        tmp_path,
        symbol,
        [
            _book(_OPEN_MS - 1, _OPEN_MS - 1),
            _book(_OPEN_MS + 1_000, _OPEN_MS + 1_010),
            _book(_CLOSE_MS - 15_001, _CLOSE_MS - 14_000),
        ],
    )

    evidence = source.completed_bar(
        symbol,
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS,
    )

    assert evidence.snapshot_count == 2
    assert evidence.end_boundary_age_ms == 15_001
    assert evidence.fresh is False
    assert evidence.status == "stale"


def test_index_pressure_rejects_one_snapshot_even_at_the_close(tmp_path: Path) -> None:
    """One exact book is insufficient evidence for archive/live parity."""
    source = _source(
        tmp_path,
        "xyz:SP500",
        [
            _book(_OPEN_MS - 1, _OPEN_MS - 1),
            _book(_CLOSE_MS - 1, _CLOSE_MS - 1),
        ],
    )

    evidence = source.completed_bar(
        "xyz:SP500",
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS,
    )

    assert evidence.snapshot_count == 1
    assert evidence.fresh is False
    assert evidence.status == "insufficient_snapshots"


def test_index_shadow_specs_are_distinct_v3_report_only_identities() -> None:
    """The corrected observers must not alias the known-defective v2 route."""
    expected = Hip3BreakoutPressureConfig(32, 21, 55, 0.1, 120.0)

    assert SP500_SHADOW_SPEC.config == expected
    assert SPCX_SHADOW_SPEC.config == expected
    assert SP500_SHADOW_SPEC.symbol == "xyz:SP500"
    assert SPCX_SHADOW_SPEC.symbol == "xyz:SPCX"
    assert "fresh15s_bidirectional_v3" in SP500_SHADOW_SPEC.provider_id
    assert SP500_SHADOW_SPEC.provider_id == SPCX_SHADOW_SPEC.provider_id
    assert SP500_SHADOW_SPEC.profile_id != SPCX_SHADOW_SPEC.profile_id


@pytest.mark.parametrize("symbol", ["xyz:SP500", "xyz:SPCX"])
def test_index_observer_selects_exact_isolated_paths(
    symbol: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One no-authority command must bind each exact index route separately."""
    module = _script_module()
    captured: dict[str, object] = {}

    def fake_main_for(spec, defaults, *, argv=None):
        captured.update(spec=spec, defaults=defaults, argv=argv)
        return 7

    monkeypatch.setattr(module, "main_for", fake_main_for)
    result = module.main(["--symbol", symbol, "--max-polls", "1"])

    assert result == 7
    assert captured["spec"].symbol == symbol
    assert symbol.lower() in captured["defaults"].asset.name.lower()
    assert captured["argv"] == ["--max-polls", "1"]


def test_index_observer_exposes_no_live_authority_flags() -> None:
    """The corrected observer command cannot be armed for execution."""
    module = _script_module()
    options = {
        option
        for action in module.build_selector()._actions
        for option in action.option_strings
    }
    source = _SCRIPT.read_text(encoding="utf-8")

    assert "--symbol" in options
    assert "--enabled" not in source
    assert "i-accept-live-risk" not in source
    assert "order" not in source.lower()


def test_index_status_accepts_its_exact_route_journal_type(tmp_path: Path) -> None:
    """A shared status writer must validate the selected index route identity."""
    paths = MuHip3ShadowPaths(
        tmp_path / "asset.jsonl",
        tmp_path / "cohort.jsonl",
        tmp_path / "cursor.json",
        tmp_path / "journal.jsonl",
        tmp_path / "status.json",
    )
    decision_time_ms = 1_786_918_500_000
    row = {
        "event_type": "sp500_hip3_breakout_shadow_decision",
        "event_id": f"{SP500_SHADOW_SPEC.provider_id}|xyz:SP500|{decision_time_ms}",
        "execution_authority": "none",
        "intents": [],
        "decision": {
            "decision_time_ms": decision_time_ms,
            "eligible": False,
            "side": None,
        },
    }
    paths.journal.write_text(json.dumps(row) + "\n", encoding="utf-8")
    result = MuHip3ShadowPollResult((), False, decision_time_ms, decision_time_ms, 0)

    _write_status(paths, result, SP500_SHADOW_SPEC)

    status = json.loads(paths.status.read_text(encoding="utf-8"))
    assert status["mode"] == "sp500_hip3_breakout_shadow_observer"
    assert status["decision_rows_total"] == 1
