"""CLI contract for immutable ETH pullback forward resolution."""

from __future__ import annotations

from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType
from typing import Iterator

from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
    EligiblePolicyFundingEvent,
)

_ROOT = Path(__file__).parents[1]
_SCRIPT = _ROOT / "scripts/eth_pullback_forward_resolution.py"
_CONFIG = _ROOT / "configs/research/multi_asset_eth_pullback_forward_observer_v1.toml"


def test_publishes_funded_report_with_immutable_prefix_evidence(
    tmp_path: Path,
) -> None:
    """The command publishes one exact report without execution authority."""
    module = _module()
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text("{}\n")
    output = tmp_path / "report.json"
    args = module.build_parser().parse_args(
        [
            "--config",
            str(_CONFIG),
            "--ledger",
            str(ledger),
            "--run-id",
            "observer-run",
            "--out",
            str(output),
        ]
    )
    reports = iter([_report(None), _report(-0.15)])
    module.snapshot_decision_ledger = _snapshot
    module.build_eth_pullback_forward_resolution = lambda *a, **k: next(reports)

    report = module.publish_report(args, funding_reader=_FundingReader())

    assert report["latest_executions"][0]["funding_bps"] == -0.15
    assert report["contract"]["execution_authority"] == "none"
    assert report["source_evidence"]["ledger"]["sha256"] == "prefix-sha"
    assert all(
        not Path(row["path"]).is_absolute()
        for row in report["source_evidence"]["generators"]
    )
    assert json.loads(output.read_text()) == report


def test_build_report_does_not_publish_output(tmp_path: Path) -> None:
    """A durable watcher can reuse exact assembly without immutable writes."""
    module = _module()
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text("{}\n")
    output = tmp_path / "report.json"
    args = module.build_parser().parse_args(
        [
            "--config",
            str(_CONFIG),
            "--ledger",
            str(ledger),
            "--run-id",
            "run",
            "--out",
            str(output),
        ]
    )
    module.snapshot_decision_ledger = _snapshot
    reports = iter([_report(None), _report(-0.15)])
    module.build_eth_pullback_forward_resolution = lambda *a, **k: next(reports)

    report = module.build_report(args, funding_reader=_FundingReader())

    assert report["latest_executions"][0]["funding_bps"] == -0.15
    assert not output.exists()


def test_rebinds_config_to_exact_observer_ledger_root(tmp_path: Path) -> None:
    """A shared observer prefix must retain its derived profile fingerprint."""
    module = _module()
    observer_root = tmp_path / "observer"
    observer_root.mkdir()
    ledger = observer_root / "decisions.jsonl"
    ledger.write_text("{}\n")
    output = tmp_path / "report.json"
    args = module.build_parser().parse_args(
        [
            "--config",
            str(_CONFIG),
            "--ledger",
            str(ledger),
            "--observer-ledger-root",
            str(observer_root),
            "--run-id",
            "observer-run",
            "--out",
            str(output),
        ]
    )
    observed: list[Path] = []
    module.snapshot_decision_ledger = _snapshot

    def _build(*args: object, **kwargs: object) -> dict[str, object]:
        config = kwargs["config"]
        observed.append(config.cohort_ledger)
        return _report(None)

    module.build_eth_pullback_forward_resolution = _build
    module._funding_reader = _FundingReader

    module.publish_report(args)

    assert observed == [ledger, ledger]


def test_source_references_cover_exact_exit_replay_dependencies() -> None:
    """Immutable evidence must bind every module that can change exit results."""
    module = _module()
    observed = {
        path.resolve().relative_to(_ROOT.resolve()).as_posix()
        for path in module._source_references(_CONFIG)
    }

    assert {
        "src/hypervector/research/cohort_eligible_exact_depth_forward.py",
        "src/hypervector/research/cohort_eligible_exact_depth_reporting.py",
        "src/hypervector/research/cohort_eligible_opposite_exit.py",
        "src/hypervector/research/cohort_exact_depth_books.py",
        "src/hypervector/research/cohort_signal_candidates.py",
        "src/hypervector/research/cohort_eligible_policy_funding.py",
        "src/hypervector/research/cohort_observer_exact_books.py",
    } <= observed


def _module() -> ModuleType:
    spec = spec_from_file_location("eth_pullback_forward_resolution_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load ETH resolution script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _snapshot(
    *args: object, **kwargs: object
) -> Iterator[tuple[list[object], dict[str, object]]]:
    yield [], {"sha256": "prefix-sha", "bytes": 3, "stable_bytes": 3}


class _FundingReader:
    def read(
        self, symbol: str, start_ms: int, end_ms: int
    ) -> EligiblePolicyFundingEvidence:
        return EligiblePolicyFundingEvidence(
            symbol=symbol,
            requested_start_ms=start_ms,
            requested_end_ms=end_ms,
            events=(
                EligiblePolicyFundingEvent(
                    timestamp_ms=start_ms, funding_rate=0.000015
                ),
            ),
        )


def _report(funding_bps: float | None) -> dict[str, object]:
    return {
        "contract": {"execution_authority": "none"},
        "latest_attempts": [],
        "latest_executions": [
            {
                "entry_time_ms": 100,
                "exit_time_ms": 200,
                "funding_bps": funding_bps,
            }
        ],
        "summary": {"resolved": 1},
    }
