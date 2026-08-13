"""CLI integration tests for immutable dual-MTF reversal evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from cohort_trade_reflection_fixtures import (
    independent_canonical_rows,
    reflection_asset_rows,
    reflection_cohort_rows,
)
from test_multi_asset_live_audit import _RUN_ID, _SYMBOLS, _asset_rows

_SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_dual_mtf_reversal_exit.py"


def test_publish_is_immutable_and_has_no_execution_authority(tmp_path: Path) -> None:
    """The command snapshots live evidence and cannot replace its output."""
    module = _load()
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    cohort = independent_canonical_rows(reflection_cohort_rows())
    _attach_direction_metrics(cohort)
    _write_jsonl(ledger / "decisions.jsonl", cohort)
    for symbol in _SYMBOLS:
        rows = reflection_asset_rows() if symbol == "BTC" else _asset_rows(symbol)
        _write_jsonl(ledger / f"{symbol.lower()}.jsonl", rows)
    output = tmp_path / "dual-mtf.json"
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

    report, actual = module.publish(args)

    assert actual == output
    assert report["contract"]["execution_authority"] == "none"
    assert report["trial_count"] == 3
    assert set(report["evidence"]["assets"]) == set(_SYMBOLS)
    json.dumps(report, allow_nan=False)
    with pytest.raises(FileExistsError, match="immutable"):
        module.publish(args)


def _attach_direction_metrics(rows: list[dict[str, object]]) -> None:
    for row in rows:
        if row["event_type"] != "canonical_regime_evaluations":
            continue
        for evaluation in row["payload"]["evaluations"]:
            evaluation["readiness"] = {"metrics": {"structural_direction": "long"}}


def _load() -> object:
    spec = spec_from_file_location("dual_mtf_reversal_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load dual-MTF reversal script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
