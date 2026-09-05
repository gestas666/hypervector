"""Bounded current-run evidence contracts for the cohort audit command."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/multi_asset_bidirectional_live_audit.py")
_RUN_ID = "run-current"


def test_current_run_scope_snapshots_only_selected_active_ledgers(
    tmp_path: Path,
) -> None:
    """First-event evidence must not copy unrelated historical ledgers."""
    module = _load_script()
    root = tmp_path / "ledgers"
    root.mkdir()
    for name in ("decisions", "btc", "hype"):
        (root / f"{name}.jsonl").write_text("{}\n")
    calls: list[tuple[str, str | None]] = []
    retired_calls: list[bool] = []

    @contextmanager
    def snapshot(path: Path, *, run_id: str | None = None) -> Iterator[object]:
        calls.append((path.name, run_id))
        yield (
            [{"event_type": "configuration_identity", "sequence": 101}],
            {"sha256": "a" * 64},
        )

    def retired(*_args: object, **_kwargs: object) -> tuple[dict, dict]:
        retired_calls.append(True)
        return {}, {}

    module.snapshot_decision_ledger = snapshot
    module.snapshot_retired_asset_ledgers = retired
    module.select_armed_live_run = lambda _rows, _run: ({}, {"run_id": _RUN_ID})
    module.configured_symbols = lambda _identity: ("BTC", "HYPE")
    module.audit_multi_asset_live_run = _fake_audit
    args = argparse.Namespace(
        ledger_root=root,
        run_id=_RUN_ID,
        out=tmp_path / "audit.json",
        out_dir=None,
        history_scope="current-run",
    )

    report, _ = module._publish(args)

    assert calls == [
        ("decisions.jsonl", _RUN_ID),
        ("btc.jsonl", _RUN_ID),
        ("hype.jsonl", _RUN_ID),
    ]
    assert retired_calls == []
    assert report["evidence"]["history_scope"] == "current-run"


def test_current_run_scope_rebases_only_after_proving_source_contiguity(
    tmp_path: Path,
) -> None:
    """A suffix may start above one but must not conceal a source gap."""
    module = _load_script()
    root = tmp_path / "ledgers"
    root.mkdir()
    for name in ("decisions", "btc"):
        (root / f"{name}.jsonl").write_text("{}\n")

    @contextmanager
    def snapshot(path: Path, *, run_id: str | None = None) -> Iterator[object]:
        start = 401 if path.name == "decisions.jsonl" else 901
        yield (
            [
                {"event_type": "configuration_identity", "sequence": start},
                {"event_type": "heartbeat", "sequence": start + 1},
            ],
            {"sha256": "b" * 64},
        )

    module.snapshot_decision_ledger = snapshot
    module.select_armed_live_run = lambda rows, _run: (rows, {"run_id": _RUN_ID})
    module.configured_symbols = lambda _identity: ("BTC",)
    module.audit_multi_asset_live_run = _rebase_audit
    args = argparse.Namespace(
        ledger_root=root,
        run_id=_RUN_ID,
        out=tmp_path / "audit.json",
        out_dir=None,
        history_scope="current-run",
    )

    report, _ = module._publish(args)

    assert report["evidence"]["cohort"]["source_sequence_start"] == 401
    assert report["evidence"]["assets"]["BTC"]["source_sequence_start"] == 901


def test_current_run_scope_rejects_a_source_sequence_gap(tmp_path: Path) -> None:
    """Rebasing must not turn missing source rows into valid-looking evidence."""
    module = _load_script()
    root = tmp_path / "ledgers"
    root.mkdir()
    for name in ("decisions", "btc"):
        (root / f"{name}.jsonl").write_text("{}\n")

    @contextmanager
    def snapshot(path: Path, *, run_id: str | None = None) -> Iterator[object]:
        del path, run_id
        yield (
            [
                {"event_type": "configuration_identity", "sequence": 401},
                {"event_type": "heartbeat", "sequence": 403},
            ],
            {"sha256": "c" * 64},
        )

    module.snapshot_decision_ledger = snapshot
    module.select_armed_live_run = lambda rows, _run: (rows, {"run_id": _RUN_ID})
    module.configured_symbols = lambda _identity: ("BTC",)
    module.audit_multi_asset_live_run = _fake_audit
    args = argparse.Namespace(
        ledger_root=root,
        run_id=_RUN_ID,
        out=tmp_path / "audit.json",
        out_dir=None,
        history_scope="current-run",
    )

    with pytest.raises(ValueError, match="source sequence is not contiguous"):
        module._publish(args)


def _fake_audit(
    _cohort: object,
    assets: object,
    *,
    all_time_asset_records: object,
    run_id: str,
) -> dict[str, object]:
    assert all_time_asset_records == assets
    return {"run": {"run_id": run_id}}


def _rebase_audit(
    cohort: object,
    assets: object,
    *,
    all_time_asset_records: object,
    run_id: str,
) -> dict[str, object]:
    assert [row["sequence"] for row in cohort] == [1, 2]
    assert [row["sequence"] for row in assets["BTC"]] == [1, 2]
    assert all_time_asset_records == assets
    return {"run": {"run_id": run_id}}


def _load_script() -> ModuleType:
    spec = spec_from_file_location("current_run_live_audit", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load cohort live audit script")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
