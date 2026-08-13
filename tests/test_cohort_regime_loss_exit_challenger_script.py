"""CLI integration tests for immutable regime-loss exit evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from cohort_trade_reflection_fixtures import (
    reflection_asset_rows,
    reflection_cohort_rows,
)
from test_multi_asset_live_audit import _RUN_ID, _SYMBOLS, _asset_rows

_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "cohort_regime_loss_exit_challenger.py"
)


def test_publish_snapshots_ledgers_and_refuses_replacement(tmp_path: Path) -> None:
    """The command writes one report-only artifact from immutable snapshots."""
    module = _load()
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    _write_jsonl(ledger / "decisions.jsonl", reflection_cohort_rows())
    for symbol in _SYMBOLS:
        rows = reflection_asset_rows() if symbol == "BTC" else _asset_rows(symbol)
        _write_jsonl(ledger / f"{symbol.lower()}.jsonl", rows)
    _write_jsonl(ledger / "xyz:gold.jsonl", _asset_rows("xyz:GOLD"))
    output = tmp_path / "challenger.json"
    args = module.build_parser().parse_args(
        [
            "--ledger-root",
            str(ledger),
            "--run-id",
            _RUN_ID,
            "--profile-fingerprint",
            "cohort-profile-fingerprint",
            "--out",
            str(output),
        ]
    )

    report, actual_output = module.publish(args)

    assert actual_output == output
    assert report["contract"]["execution_authority"] == "none"
    assert report["all_live"]["opp5_loss30"]["eligible_lifecycles"] == 1
    assert report["evidence"]["cohort"]["complete_rows"] == len(
        reflection_cohort_rows()
    )
    assert set(report["evidence"]["assets"]) == set(_SYMBOLS)
    json.dumps(report, allow_nan=False)
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 1
    with pytest.raises(FileExistsError, match="immutable"):
        module.publish(args)


def _load() -> object:
    spec = spec_from_file_location("cohort_regime_loss_exit_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load regime-loss exit challenger script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8")
