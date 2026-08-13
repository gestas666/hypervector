"""CLI tests for the v49 config-bound policy forward sidecar."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from requests import RequestException

from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
)

_SCRIPT = Path(__file__).parents[1] / "scripts" / "v49_config_bound_policy_forward.py"


def _module() -> ModuleType:
    spec = spec_from_file_location("v49_config_bound_policy_forward_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_once_invokes_report_only_publisher_without_live_surface() -> None:
    module = _module()
    calls: list[object] = []
    args = module.build_parser().parse_args(["--run-id", "observe-v49", "--once"])

    def publish(value: object) -> dict[str, object]:
        calls.append(value)
        return {"state": "awaiting_exact_policy_resolution"}

    assert module.run_monitor(args, publish_fn=publish) == 0
    assert calls == [args]
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "i-accept-live-risk" not in source
    assert "submit_market" not in source
    assert "private_key" not in source


def test_nonfinite_interval_is_rejected() -> None:
    module = _module()
    args = module.build_parser().parse_args(
        ["--run-id", "observe-v49", "--interval-seconds", "nan"]
    )

    try:
        module.run_monitor(args, publish_fn=lambda _: {})
    except ValueError as exc:
        assert str(exc) == "monitor interval must be positive and finite"
    else:
        raise AssertionError("nonfinite monitor interval must fail closed")


def test_public_funding_failure_is_disclosed_without_suppressing_policy() -> None:
    module = _module()
    records = _funding_records()

    class FailingReader:
        def read(self, *_args: object) -> object:
            raise RequestException("429")

    module._funding_reader = FailingReader
    evidence, status = module._funding_evidence(records, "observe-v49")

    assert evidence is None
    assert status == {
        "status": "unavailable",
        "technical_issue": "RequestException: 429",
    }


def test_exact_depth_lifecycle_uses_source_bound_fee_and_sol_books() -> None:
    module = _module()
    captured: dict[str, object] = {}
    books = ({"event_type": "book_observation"},)

    module.extract_observer_asset_books = lambda _rows, _symbols: {"SOL": books}

    def build(*args: object, **kwargs: object) -> dict[str, object]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"mode": "cohort_eligible_exact_visible_depth_forward_report"}

    module.build_eligible_exact_depth_forward_report = build
    policy = {"contract": {"friction_components_bps": {"round_trip_taker_fee": 9.0}}}

    result = module._exact_depth_lifecycle([], policy, None)

    assert result["mode"] == "cohort_eligible_exact_visible_depth_forward_report"
    assert captured["args"] == ([], books)
    assert captured["kwargs"] == {
        "policy_report": policy,
        "funding_evidence": None,
        "taker_fee_rate": 0.00045,
        "maximum_entry_delay_ms": 60_000,
        "maximum_exit_delay_ms": 60_000,
    }


def test_profit_lock_lifecycle_uses_sol_candles_and_source_bound_fee() -> None:
    """The sidecar evaluates locks on the exact SOL path without authority."""
    module = _module()
    captured: dict[str, object] = {}
    candles = {60_000: object()}
    module.build_reflection_evidence_index = lambda _rows: SimpleNamespace(
        candles={"SOL": candles}
    )

    def build(*args: object, **kwargs: object) -> dict[str, object]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"contract": {"execution_authority": "none"}}

    module.build_policy_forward_profit_lock_report = build
    policy = {"contract": {"friction_components_bps": {"round_trip_taker_fee": 9.0}}}
    exact = {"latest_attempts": []}

    result = module._profit_lock_lifecycle([], policy, exact)

    assert result["contract"]["execution_authority"] == "none"
    assert captured["args"] == (candles, exact)
    assert captured["kwargs"] == {"taker_fee_rate": 0.00045}


def test_funding_window_covers_latest_observer_record_for_depth_exit() -> None:
    module = _module()
    records = _funding_records()
    records.append(
        {
            "event_type": "observer_status",
            "run_id": "observe-v49",
            "observed_at_utc": "1970-01-01T00:02:30+00:00",
            "payload": {},
        }
    )
    captured: dict[str, int] = {}

    class Reader:
        def read(self, symbol: str, start_ms: int, end_ms: int) -> object:
            captured.update(start=start_ms, end=end_ms)
            return EligiblePolicyFundingEvidence(symbol, start_ms, end_ms, ())

    module._funding_reader = Reader
    evidence, status = module._funding_evidence(records, "observe-v49")

    assert evidence is not None
    assert captured == {"start": 61_000, "end": 150_000}
    assert status["requested_end_ms"] == 150_000


def _funding_records() -> list[dict[str, object]]:
    return [
        {
            "event_type": "configuration_identity",
            "run_id": "observe-v49",
            "observed_at_utc": "1970-01-01T00:00:00+00:00",
            "payload": {"profile_fingerprint": "profile"},
        },
        {
            "event_type": "intent_routing",
            "run_id": "observe-v49",
            "observed_at_utc": "1970-01-01T00:01:01+00:00",
            "payload": {
                "evaluations": [
                    {
                        "strategy_id": "range_onset_bidirectional_v1",
                        "symbol": "SOL",
                        "decision_time_ms": 60_000,
                        "reference_price": 100.0,
                        "eligible": True,
                        "side": "short",
                        "readiness": {"side": "short", "blockers": [], "metrics": {}},
                    }
                ]
            },
        },
        {
            "event_type": "market_candles",
            "run_id": "observe-v49",
            "observed_at_utc": "1970-01-01T00:02:00+00:00",
            "payload": {
                "timeframe": "1m",
                "bars": {
                    "SOL": [
                        {
                            "timestamp_ms": 60_000,
                            "open": 100.0,
                            "high": 100.1,
                            "low": 99.9,
                            "close": 100.0,
                        }
                    ]
                },
            },
        },
    ]
