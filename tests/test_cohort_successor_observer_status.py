"""Fail-closed projection of the isolated V58 successor observer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.research import cohort_successor_observer_status as status

_V57 = "multi_asset_growth_first_5000_spcx_short_containment_v57"
_V58 = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_PROFILE = "24820e4bfad8a978a7b617a29dc0326f8fc0e583389b67e0219ce4ab5789c874"
_BASE_PROFILE = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
_RUN = "1812cbfd3ad4b3f9b939c21c45caa38155e48ca78ddb205e68d68c9dd9b8f1d8"
_RUN_ID = "bidirectional-observe-1787108378615"
_NOW = datetime(2026, 8, 19, 3, 5, tzinfo=UTC)
_V58_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml"
)
_SYMBOLS = [
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
]


def test_loader_projects_exact_report_only_v58_observer(tmp_path: Path) -> None:
    """Fresh complete telemetry remains evidence and gains no live authority."""
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(_payload()))

    evidence = status.load_v58_successor_observer_status(
        source,
        observed_at=_NOW,
        maximum_age_seconds=300.0,
    )

    assert evidence.status == {
        "profile_id": _V58,
        "profile_fingerprint": _PROFILE,
        "base_profile_fingerprint": _BASE_PROFILE,
        "run_fingerprint": _RUN,
        "run_id": _RUN_ID,
        "symbols": _SYMBOLS,
        "observed_at_utc": "2026-08-19T03:04:00+00:00",
        "freshness_status": "fresh",
        "age_seconds": 60.0,
        "technical_complete": True,
        "technical_gaps": [],
        "provider_symbol_routes": 10,
        "poll_cycles": 8,
        "degraded_poll_cycles": 0,
        "eligible_evaluations": 0,
        "strategy_intents": 0,
        "routed_actions": 0,
        "live_change_supported": False,
        "automatic_promotion": False,
        "report_only": True,
        "execution_authority": "none",
    }
    assert evidence.evidence["checkpoint"]["path"] == str(source.resolve())
    assert evidence.evidence["observer_ledger"]["path"] == "ledger.jsonl"


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("checkpoint_contract", "execution_authority"), "mainnet", "contract"),
        (("audit", "signals", "routed_actions"), 1, "routed actions"),
        (("audit", "technical", "future_decisions"), 1, "technical"),
    ],
)
def test_loader_rejects_authority_or_technical_contradictions(
    tmp_path: Path,
    path: tuple[str, ...],
    value: object,
    message: str,
) -> None:
    """Unsafe authority and incomplete causal evidence cannot enter the digest."""
    payload = _payload()
    target = payload
    for key in path[:-1]:
        nested = target[key]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = value
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match=message):
        status.load_v58_successor_observer_status(
            source,
            observed_at=_NOW,
            maximum_age_seconds=300.0,
        )


def test_profile_wrapper_loads_only_for_exact_v57(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The staged V58 lane must not contaminate unrelated active profiles."""
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(_payload()))
    monkeypatch.setattr(status, "_STATUS_PATH", source)

    loaded = status.load_v58_successor_observer_for_profile(
        {"run": {"profile_id": _V57}},
        _NOW,
    )

    assert loaded is not None
    assert (
        status.load_v58_successor_observer_for_profile(
            {"run": {"profile_id": "other"}},
            _NOW,
        )
        is None
    )


def test_loader_accepts_exact_post_activation_report_only_restart(
    tmp_path: Path,
) -> None:
    """A later same-identity observer run preserves the prospective window."""
    payload = _payload()
    audit = payload["audit"]
    assert isinstance(audit, dict)
    run = audit["run"]
    assert isinstance(run, dict)
    run["run_id"] = "bidirectional-observe-1787127644202"
    payload["generated_at_utc"] = "2026-08-19T08:21:53+00:00"
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(payload))

    evidence = status.load_v58_successor_observer_status(
        source,
        observed_at=datetime(2026, 8, 19, 8, 22, tzinfo=UTC),
        maximum_age_seconds=300.0,
    )

    assert evidence.status["run_id"] == "bidirectional-observe-1787127644202"


def test_loader_reports_known_heartbeat_gap_without_stopping_diagnostics(
    tmp_path: Path,
) -> None:
    """A measured observer gap must degrade evidence, not kill its report loop."""
    payload = _payload()
    technical = payload["audit"]["technical"]
    technical["complete"] = False
    technical["technical_gaps"] = ["observer_heartbeat_gap_exceeds_entry_delay"]
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(payload))

    evidence = status.load_v58_successor_observer_status(
        source,
        observed_at=_NOW,
        maximum_age_seconds=300.0,
    )

    assert evidence.status["technical_complete"] is False
    assert evidence.status["technical_gaps"] == [
        "observer_heartbeat_gap_exceeds_entry_delay"
    ]
    assert evidence.status["live_change_supported"] is False


def test_loader_accepts_identity_derived_from_isolated_v58_root(
    tmp_path: Path,
) -> None:
    """A clean non-pooled root must retain exact V58 strategy identity."""
    payload, profile_fingerprint, run_fingerprint = _isolated_payload(tmp_path)
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(payload))

    evidence = status.load_v58_successor_observer_status(
        source,
        observed_at=_NOW,
        maximum_age_seconds=300.0,
        config_path=_V58_CONFIG,
    )

    assert evidence.status["profile_fingerprint"] == profile_fingerprint
    assert evidence.status["run_fingerprint"] == run_fingerprint
    assert evidence.status["base_profile_fingerprint"] == _BASE_PROFILE


def test_loader_rejects_isolated_identity_not_derived_from_v58_config(
    tmp_path: Path,
) -> None:
    """A caller cannot bless arbitrary hashes by selecting a new ledger root."""
    payload, _, _ = _isolated_payload(tmp_path)
    run = payload["audit"]["run"]
    run["run_fingerprint"] = "0" * 64
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="run identity"):
        status.load_v58_successor_observer_status(
            source,
            observed_at=_NOW,
            maximum_age_seconds=300.0,
            config_path=_V58_CONFIG,
        )


def test_loader_rejects_unknown_observer_technical_gap(tmp_path: Path) -> None:
    """Only a declared non-authoritative gap may enter the research digest."""
    payload = _payload()
    technical = payload["audit"]["technical"]
    technical["complete"] = False
    technical["technical_gaps"] = ["unknown_gap"]
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="technical gaps"):
        status.load_v58_successor_observer_status(
            source,
            observed_at=_NOW,
            maximum_age_seconds=300.0,
        )


@pytest.mark.parametrize(
    "run_id",
    [
        "bidirectional-observe-1787108378614",
        "bidirectional-live-1787127644202",
        "bidirectional-observe-not-a-timestamp",
    ],
)
def test_loader_rejects_pre_activation_or_malformed_restart(
    tmp_path: Path, run_id: str
) -> None:
    """Restart identity cannot precede or escape the frozen observer epoch."""
    payload = _payload()
    audit = payload["audit"]
    assert isinstance(audit, dict)
    run = audit["run"]
    assert isinstance(run, dict)
    run["run_id"] = run_id
    source = tmp_path / "observer.json"
    source.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="run identity"):
        status.load_v58_successor_observer_status(
            source,
            observed_at=_NOW,
            maximum_age_seconds=300.0,
        )


def _payload() -> dict[str, object]:
    generated = (_NOW - timedelta(seconds=60)).isoformat()
    return {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_observer_checkpoint",
        "generated_at_utc": generated,
        "checkpoint_contract": _checkpoint_contract(),
        "evidence": {
            "path": "ledger.jsonl",
            "sha256": "a" * 64,
            "bytes": 100,
            "stable_bytes": 100,
            "source_bytes_observed": 100,
            "dropped_tail_bytes": 0,
            "incomplete_tail_dropped": False,
        },
        "audit": _audit_payload(),
    }


def _isolated_payload(root: Path) -> tuple[dict[str, object], str, str]:
    base = load_multi_asset_live_config(_V58_CONFIG, mode="observe")
    isolated = with_observer_ledger_root(base, root / "isolated-epoch")
    payload = _payload()
    evidence = payload["evidence"]
    assert isinstance(evidence, dict)
    evidence["path"] = str(isolated.cohort_ledger)
    audit = payload["audit"]
    assert isinstance(audit, dict)
    run = audit["run"]
    assert isinstance(run, dict)
    run["profile_fingerprint"] = isolated.profile_fingerprint
    run["run_fingerprint"] = isolated.run_fingerprint
    return payload, isolated.profile_fingerprint, isolated.run_fingerprint


def _checkpoint_contract() -> dict[str, object]:
    return {
        "automatic_pause": False,
        "automatic_retuning": False,
        "execution_authority": "none",
        "final": False,
        "performance_gate": False,
        "report_only": True,
        "runtime_strategy_changed": False,
    }


def _audit_payload() -> dict[str, object]:
    return {
        "observer_contract": {
            "execution_authority": "none",
            "fills_observed": False,
            "orders_observed": False,
            "performance_gate": False,
            "profitability_measured": False,
            "report_only": True,
            "runtime_strategy_changed": False,
        },
        "run": {
            "profile_id": _V58,
            "profile_fingerprint": _PROFILE,
            "run_fingerprint": _RUN,
            "run_id": _RUN_ID,
            "symbols": _SYMBOLS,
        },
        "technical": _technical_payload(),
        "runtime": {
            "poll_cycles": 8,
            "successful_poll_cycles": 8,
            "degraded_poll_cycles": 0,
        },
        "signals": {
            "eligible_evaluations": 0,
            "strategy_intents": 0,
            "routed_actions": 0,
        },
    }


def _technical_payload() -> dict[str, object]:
    return {
        "complete": True,
        "expected_provider_symbols": 10,
        "initial_provider_symbols": 10,
        "observed_provider_symbols": 10,
        "missing_observed_provider_symbols": [],
        "initial_candle_symbols": sorted(_SYMBOLS),
        "duplicate_evaluations": 0,
        "future_decisions": 0,
        "technical_gaps": [],
    }
