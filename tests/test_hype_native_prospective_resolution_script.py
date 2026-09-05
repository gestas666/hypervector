"""Command boundary for exact HYPE-native v54 post-close resolution."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from hypervector.research.hype_native_prospective_resolution import (
    HypeProxyExitUnconfirmedError,
)

_SCRIPT = Path("scripts/hype_native_prospective_resolution.py")


def test_run_binds_inputs_generator_and_exact_price_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolution retains immutable evidence for every economic input."""
    module = _load_script()
    args = module.build_parser().parse_args(_arguments(tmp_path))
    evidence = {"lifecycle_status": {"sha256": "a" * 64}}
    generator = [{"path": "resolution.py", "sha256": "b" * 64}]
    archive = _price_archive()
    monkeypatch.setattr(module, "_input_evidence", lambda _args: evidence)
    monkeypatch.setattr(module, "_generator_evidence", lambda: generator)
    status = {
        "status": "closed",
        "lifecycles": [{"entry_book_time_ms": 1_000, "exit_book_time_ms": 5_000}],
    }
    monkeypatch.setattr(module, "_status_report", lambda _path: status)
    monkeypatch.setattr(
        module,
        "read_complete_hl_funding_evidence",
        lambda *_: SimpleNamespace(evidence={"complete": True}),
    )
    monkeypatch.setattr(module, "load_verified_price_archive", lambda _config: archive)
    captured: dict[str, object] = {}

    def resolve(*_values: object, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"summary": {"net_pnl_usd_after_funding": 9.5}}

    monkeypatch.setattr(module, "resolve_hype_native_prospective_lifecycles", resolve)
    source = _MarkSource()
    l2_source = _L2Source()

    report = module.run(args, mark_source=source, l2_source=l2_source)

    assert report["evidence"]["lifecycle_status"]["sha256"] == "a" * 64
    assert report["evidence"]["generator_files"] == generator
    assert report["evidence"]["price_archive"]["mark_row_count"] == 1
    assert report["evidence"]["local_mark_archive"]["rows"] == 2
    assert report["evidence"]["local_l2_archive"]["rows"] == 1
    assert captured["mark_prices"]["mark_price"].tolist() == [100.0, 99.0]
    assert len(captured["stop_books"]) == 1
    assert source.rechecked is True
    assert l2_source.rechecked is True


def test_generator_identity_covers_resolution_and_shared_funding() -> None:
    """Changes to exact mark or funding semantics must change provenance."""
    module = _load_script()

    names = {Path(row["path"]).name for row in module._generator_evidence()}

    assert "hype_native_prospective_resolution.py" in names
    assert "hype_funding_events.py" in names


def test_unconfirmed_proxy_exit_becomes_explicit_technical_rejection() -> None:
    """A permanent mark mismatch must terminate without fabricated economics."""
    module = _load_script()
    status = {
        "identity": {"symbol": "HYPE"},
        "lifecycles": [
            {
                "side": "long",
                "exit_reason": "protective_stop_bbo_proxy",
                "entry_book_time_ms": 1_000,
                "exit_book_time_ms": 5_000,
            }
        ],
    }
    error = HypeProxyExitUnconfirmedError(
        {
            "mark_stop_truth": "confirmed_no_earlier_mark_stop",
            "minimum_mark_price": 99.4,
            "maximum_mark_price": 101.0,
            "mark_rows": 6,
            "maximum_mark_gap_ms": 1_000,
        }
    )

    report = module._technical_rejection_report(status, error)

    assert report["resolution_status"] == "technical_evidence_rejected"
    assert report["summary"]["resolved_trades"] == 0
    assert report["summary"]["technically_rejected_lifecycles"] == 1
    assert report["lifecycles"][0]["net_pnl_usd_after_funding"] is None


def _arguments(tmp_path: Path) -> list[str]:
    return [
        "--lifecycle-status",
        str(tmp_path / "status.json"),
        "--funding",
        str(tmp_path / "funding.parquet"),
        "--price-start",
        "2026-08-18T06:30:00Z",
        "--price-end",
        "2026-08-18T14:31:00Z",
        "--out",
        str(tmp_path / "resolution.json"),
    ]


def _price_archive() -> SimpleNamespace:
    return SimpleNamespace(
        frame=pd.DataFrame(
            {"ts_ms": [1], "mark_price": [100.0], "oracle_price": [100.0]}
        ),
        partition_count=1,
        row_count=1,
        maximum_observed_gap_ms=0,
        mark_row_count=1,
        missing_mark_row_count=0,
        oracle_row_count=1,
        missing_oracle_row_count=0,
    )


class _MarkSource:
    def __init__(self) -> None:
        self.rechecked = False

    def load(
        self, **_kwargs: object
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        return (
            (
                {"received_ts_ns": 1_000_000_000, "mark_price": 100.0},
                {"received_ts_ns": 2_000_000_000, "mark_price": 99.0},
            ),
            {"rows": 2, "files": [{"path": "mark.parquet"}]},
        )

    def require_unchanged(self, _evidence: object) -> None:
        self.rechecked = True


class _L2Source:
    def __init__(self) -> None:
        self.rechecked = False

    def load(
        self, **_kwargs: object
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        return (
            (
                {
                    "symbol": "HYPE",
                    "exchange_ts_ms": 2_001,
                    "received_ts_ns": 2_002_000_000,
                    "bids": [{"price": 99.0, "size": 20.0}],
                    "asks": [{"price": 99.1, "size": 20.0}],
                    "source": "hyperliquid_ws_l2Book",
                },
            ),
            {"rows": 1, "files": [{"path": "l2.parquet"}]},
        )

    def require_unchanged(self, _evidence: object) -> None:
        self.rechecked = True


def _load_script() -> ModuleType:
    spec = spec_from_file_location("hype_native_prospective_resolution_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
