"""Durable authority-none V58 BTC sweep lifecycle watcher tests."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

from hyperliquid.utils.error import ClientError  # type: ignore[import-untyped]
import pytest


class _Info:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, path: str, payload: dict[str, object]) -> object:
        self.calls.append((path, payload))
        return [
            {"universe": [{"name": "BTC"}]},
            [
                {
                    "markPx": "69000",
                    "oraclePx": "69001",
                    "funding": "0.00001",
                    "openInterest": "12.5",
                }
            ],
        ]


class _RateLimitedOnce(_Info):
    def post(self, path: str, payload: dict[str, object]) -> object:
        if not self.calls:
            self.calls.append((path, payload))
            raise ClientError(429, None, "limited", {})
        return super().post(path, payload)


def test_transient_rate_limit_skips_one_cycle_without_stopping(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An explicit public HTTP 429 must be visible and retryable next cycle."""
    script = _script()
    args = _args(tmp_path, max_polls=2, report_every_polls=1)
    args.preregistration.write_text(
        json.dumps(_preregistration(args)), encoding="utf-8"
    )
    args.preregistration_sha256 = script.file_evidence(args.preregistration)["sha256"]
    reports: list[dict[str, object]] = []

    result = script.run_watcher(
        args,
        info=_RateLimitedOnce(),
        clock_ns=lambda: 1_787_150_003_000_000_000,
        report_builder=lambda _args: _report(),
        status_publisher=lambda report, **_kwargs: reports.append(report) or report,
        sleep_fn=lambda _seconds: None,
    )

    assert result == 0
    assert len(args.mark_ledger.read_text().splitlines()) == 1
    assert len(reports) == 1
    captured = capsys.readouterr()
    assert "http_429_retry_exhausted" in captured.err


def test_official_reader_retries_rate_limited_sdk_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A constructor-time public 429 must degrade one poll, not kill startup."""
    script = _script()
    attempts = 0

    def client() -> _Info:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ClientError(429, None, "limited", {})
        return _Info()

    monkeypatch.setattr(script, "_official_info_client", client)
    info = script.official_info()

    assert script._read_mark(info, "observer-v58", lambda: 1) is None
    assert script._read_mark(info, "observer-v58", lambda: 2) is not None
    assert attempts == 2


def test_bounded_runner_records_marks_and_publishes_report_only_status(
    tmp_path: Path,
) -> None:
    """Sampling cannot construct execution authority or lose durable receipts."""
    script = _script()
    info = _Info()
    args = _args(tmp_path, max_polls=2, report_every_polls=2)
    preregistration = _preregistration(args)
    args.preregistration.write_text(json.dumps(preregistration), encoding="utf-8")
    args.preregistration_sha256 = script.file_evidence(args.preregistration)["sha256"]
    reports: list[dict[str, object]] = []

    result = script.run_watcher(
        args,
        info=info,
        clock_ns=iter((1_787_150_000_000_000_000, 1_787_150_003_000_000_000)).__next__,
        report_builder=lambda _args: _report(),
        status_publisher=lambda report, **_kwargs: reports.append(report) or report,
        sleep_fn=lambda _seconds: None,
    )

    assert result == 0
    assert info.calls == [
        ("/info", {"type": "metaAndAssetCtxs"}),
        ("/info", {"type": "metaAndAssetCtxs"}),
    ]
    rows = [json.loads(line) for line in args.mark_ledger.read_text().splitlines()]
    assert [row["received_ts_ms"] for row in rows] == [
        1_787_150_000_000,
        1_787_150_003_000,
    ]
    assert reports[-1]["contract"]["execution_authority"] == "none"


def test_preregistration_rejects_an_observer_run_identity_mismatch(
    tmp_path: Path,
) -> None:
    """A prior V57 or different V58 run cannot be relabeled as this watcher."""
    script = _script()
    args = _args(tmp_path, max_polls=1, report_every_polls=1)
    value = _preregistration(args)
    value["observer_run_id"] = "different-run"
    args.preregistration.write_text(json.dumps(value), encoding="utf-8")
    args.preregistration_sha256 = script.file_evidence(args.preregistration)["sha256"]

    try:
        script.run_watcher(
            args,
            info=_Info(),
            clock_ns=lambda: 1_787_150_000_000_000_000,
            report_builder=lambda _args: _report(),
            status_publisher=lambda report, **_kwargs: report,
            sleep_fn=lambda _seconds: None,
        )
    except ValueError as exc:
        assert "identity" in str(exc)
    else:
        raise AssertionError("observer run mismatch must fail closed")


def _args(
    tmp_path: Path, *, max_polls: int, report_every_polls: int
) -> argparse.Namespace:
    config = tmp_path / "v58.toml"
    config.write_text("frozen-config", encoding="utf-8")
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text('{"sequence":1}\n', encoding="utf-8")
    return argparse.Namespace(
        preregistration=tmp_path / "prereg.json",
        preregistration_sha256="0" * 64,
        config=config,
        ledger=ledger,
        mark_ledger=tmp_path / "marks.jsonl",
        run_id="observer-v58",
        status=tmp_path / "latest.json",
        snapshot_dir=tmp_path / "snapshots",
        taker_fee_rate=0.00045,
        poll_seconds=3.0,
        report_every_polls=report_every_polls,
        max_polls=max_polls,
    )


def _preregistration(args: argparse.Namespace) -> dict[str, object]:
    script = _script()
    prefix = script.read_jsonl_prefix(args.ledger, "test ledger")[1]
    return {
        "schema_version": "v58_btc_sweep_lifecycle_preregistration_v1",
        "strategy_id": "liquidity_sweep_long_1h_stop60_target60_v2",
        "symbol": "BTC",
        "observer_run_id": args.run_id,
        "prospective_start_ms": 1_787_150_000_000,
        "config": {
            "path": str(args.config),
            **script.file_evidence(args.config),
        },
        "ledger_prefix": prefix,
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _report() -> dict[str, object]:
    return {
        "state": "awaiting_resolution",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
            "actual_orders_or_fills_claimed": False,
        },
        "summary": {"resolved": 0},
        "latest_attempts": [],
        "latest_executions": [],
    }


def _script() -> ModuleType:
    path = Path("scripts/v58_btc_sweep_lifecycle_watch.py")
    spec = importlib.util.spec_from_file_location("v58_btc_sweep_watch", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("V58 BTC sweep watcher script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
