"""Attach source-bound V58 ETH historical funding stress evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from math import isclose, isfinite
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence

Record = Mapping[str, object]

_ROUTE = "eth_breakout_precompression_pullback_bidirectional_v1|ETH"
_STRATEGY = _ROUTE.split("|", 1)[0]
_SOURCE_LABELS = ("funding", "manifest", "stress", "generator")


def attach_v58_eth_historical_funding_context(
    report: dict[str, object], path: Path
) -> None:
    """Attach immutable funding evidence or an explicit unavailable state."""
    if not path.is_file():
        report["eth_historical_funding_stress_context"] = _unavailable_payload()
        return
    before = file_evidence(path)
    artifact = _load_json(path)
    context = _context_payload(artifact)
    if file_evidence(path) != before:
        raise ValueError("V58 ETH historical funding stress changed during analysis")
    report["eth_historical_funding_stress_context"] = context
    _attach_to_eth_ledger(report, context)
    evidence = _mutable_mapping(report.get("evidence"), "report evidence")
    evidence["eth_historical_funding_stress_context"] = {
        "path": str(path.resolve()),
        **before,
    }


def _unavailable_payload() -> dict[str, object]:
    return {
        "status": "not_available",
        "reason": "historical_funding_stress_not_published",
        "execution_authority": "none",
        "live_change_supported": False,
    }


def _context_payload(artifact: Record) -> dict[str, object]:
    _require_contract(artifact)
    route = _route_identity(artifact)
    long = _distribution(artifact, "long")
    short = _distribution(artifact, "short")
    comparisons = _comparisons(artifact, route["notional_usd"], long["p99"])
    disposition = _mapping(artifact.get("disposition"), "funding disposition")
    source_evidence = _source_evidence(artifact)
    state = (
        "historically_understated" if disposition["p99_exceeds_frozen"] else "covered"
    )
    return {
        "status": disposition["status"],
        "route": _ROUTE,
        "hold_hours": artifact["hold_hours"],
        "hourly_event_count": _positive_int(
            artifact.get("hourly_event_count"), "hourly events"
        ),
        "rolling_window_count": _positive_int(
            artifact.get("rolling_window_count"), "rolling windows"
        ),
        "long_p99_cost_bps": long["p99"],
        "long_maximum_cost_bps": long["maximum"],
        "short_p99_cost_bps": short["p99"],
        "short_maximum_cost_bps": short["maximum"],
        **comparisons,
        "funding_stress_assumption_state": state,
        "source_evidence": source_evidence,
        "historical_distribution_claim": True,
        "sizing_input": False,
        "execution_authority": "none",
        "live_change_supported": False,
    }


def _require_contract(artifact: Record) -> None:
    expected = {
        "schema_version": 1,
        "mode": "v58_eth_historical_funding_stress_v1",
        "symbol": "ETH",
        "hold_hours": 12,
        "historical_distribution_claim": True,
        "sizing_input": False,
        "live_change_supported": False,
        "execution_authority": "none",
    }
    if any(artifact.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH historical funding authority or contract is invalid")
    disposition = _mapping(artifact.get("disposition"), "funding disposition")
    if disposition.get("status") != "report_only_stress_recalibration":
        raise ValueError("V58 ETH historical funding disposition is invalid")
    if disposition.get("proposed_live_change") is not None:
        raise ValueError("V58 ETH historical funding authority or contract is invalid")
    if not isinstance(disposition.get("p99_exceeds_frozen"), bool):
        raise ValueError("V58 ETH historical funding disposition is invalid")


def _route_identity(artifact: Record) -> dict[str, float | str]:
    route = _mapping(artifact.get("route_identity"), "funding route identity")
    expected = {"strategy_id": _STRATEGY, "symbol": "ETH", "hold_hours": 12}
    if any(route.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH historical funding route identity is invalid")
    return {
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
        "notional_usd": _positive_number(route.get("notional_usd"), "route notional"),
        "hold_hours": 12.0,
    }


def _distribution(artifact: Record, side: str) -> dict[str, float]:
    distributions = _mapping(
        artifact.get("rolling_12h_cost_bps"), "funding distributions"
    )
    row = _mapping(distributions.get(side), f"{side} funding distribution")
    p99 = _number(row.get("p99"), f"{side} p99")
    maximum = _number(row.get("maximum"), f"{side} maximum")
    if maximum < p99:
        raise ValueError(f"V58 ETH {side} funding distribution is inconsistent")
    return {"p99": p99, "maximum": maximum}


def _comparisons(
    artifact: Record, notional_usd: float | str, long_p99_bps: float
) -> dict[str, float]:
    comparisons = _mapping(artifact.get("comparisons"), "funding comparisons")
    frozen = _projection(comparisons, "frozen_projection")
    current = _projection(comparisons, "current_projection")
    delta_bps = _number(comparisons.get("p99_minus_frozen_bps"), "p99 delta")
    delta_usd = _number(
        comparisons.get("p99_minus_frozen_loss_usd"), "p99 dollar delta"
    )
    notional = _positive_number(notional_usd, "route notional")
    if not isclose(delta_bps, long_p99_bps - frozen["cost_bps"], abs_tol=1e-9):
        raise ValueError("V58 ETH funding bps comparison is inconsistent")
    expected_usd = delta_bps * notional / 10_000.0
    if not isclose(delta_usd, expected_usd, abs_tol=1e-9):
        raise ValueError("V58 ETH funding dollar comparison is inconsistent")
    return {
        "frozen_projection_cost_bps": frozen["cost_bps"],
        "frozen_fraction_historical_windows_above": frozen["fraction_above"],
        "current_projection_cost_bps": current["cost_bps"],
        "current_fraction_historical_windows_above": current["fraction_above"],
        "p99_minus_frozen_bps": delta_bps,
        "p99_minus_frozen_loss_usd": delta_usd,
    }


def _projection(comparisons: Record, key: str) -> dict[str, float]:
    row = _mapping(comparisons.get(key), f"{key} funding comparison")
    percentile = _fraction(row.get("empirical_percentile"), f"{key} percentile")
    fraction_above = _fraction(
        row.get("fraction_historical_windows_above"), f"{key} fraction"
    )
    if not isclose(percentile + fraction_above, 1.0, abs_tol=1e-9):
        raise ValueError(f"V58 ETH {key} funding comparison is inconsistent")
    return {
        "cost_bps": _number(row.get("cost_bps"), f"{key} cost"),
        "fraction_above": fraction_above,
    }


def _source_evidence(artifact: Record) -> dict[str, dict[str, object]]:
    sources = _mapping(artifact.get("source_evidence"), "funding source evidence")
    result: dict[str, dict[str, object]] = {}
    for label in _SOURCE_LABELS:
        row = _mapping(sources.get(label), f"{label} source evidence")
        path = _text(row.get("path"), f"{label} source path")
        size = _positive_int(row.get("bytes"), f"{label} source bytes")
        digest = _sha256(row.get("sha256"), f"{label} source hash")
        result[label] = {"path": path, "bytes": size, "sha256": digest}
    return result


def _attach_to_eth_ledger(
    report: dict[str, object], context: dict[str, object]
) -> None:
    ledger = _sequence(report.get("hypothesis_ledger"), "hypothesis ledger")
    matches = [row for row in ledger if row.get("route") == _ROUTE]
    if len(matches) != 1 or not isinstance(matches[0], dict):
        raise ValueError("V58 ETH historical funding hypothesis identity is invalid")
    matches[0]["funding_stress_assumption_state"] = context[
        "funding_stress_assumption_state"
    ]
    matches[0]["historical_funding_stress"] = context


def _load_json(path: Path) -> Record:
    try:
        value: object = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"V58 ETH historical funding stress is unreadable: {path}"
        ) from exc
    return _mapping(value, "historical funding stress")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _mutable_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be mutable mapping")
    return value


def _sequence(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"{label} rows must be mappings")
    return tuple(row for row in value if isinstance(row, Mapping))


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{label} must be finite numeric")
    return result


def _positive_number(value: object, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _fraction(value: object, label: str) -> float:
    result = _number(value, label)
    if result < 0.0 or result > 1.0:
        raise ValueError(f"{label} must be between zero and one")
    return result


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be lowercase SHA-256")
    return text
