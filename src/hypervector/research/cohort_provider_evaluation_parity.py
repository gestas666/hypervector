"""Report-only semantic parity for one provider evaluation across processes."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import math

Record = Mapping[str, object]
_AUTHORITY_METRICS = frozenset(("candidate_authority", "entry_policy_authority"))
_FLOAT_ABS_TOLERANCE = 1e-9
_FLOAT_REL_TOLERANCE = 1e-12


def build_cohort_provider_evaluation_parity(
    *,
    rows_by_source: Mapping[str, Record],
    source_kinds: Mapping[str, str],
    provider_id: str,
    symbol: str,
    decision_time_ms: int,
) -> dict[str, object]:
    """Compare strategy semantics while isolating declared authority differences."""
    live_source = _validate_scope(
        rows_by_source, source_kinds, provider_id, symbol, decision_time_ms
    )
    evaluations = {
        source: _evaluation(row, provider_id, symbol, decision_time_ms)
        for source, row in rows_by_source.items()
    }
    semantic = {source: _semantic_view(row) for source, row in evaluations.items()}
    mismatches = _source_mismatches(semantic, live_source)
    return {
        "schema_version": 1,
        "mode": "cohort_provider_evaluation_process_parity",
        "contract": _contract(),
        "target": {
            "provider_id": provider_id,
            "symbol": symbol,
            "decision_time_ms": decision_time_ms,
        },
        "sources": _source_records(rows_by_source, source_kinds, evaluations),
        "semantic_evaluation": semantic[live_source],
        "mismatches": mismatches,
        "technical_assessment": {
            "semantic_parity_resolved": not mismatches,
            "compared_sources": len(rows_by_source),
            "semantic_mismatches": len(mismatches),
        },
        "limitations": [
            "process parity does not establish fills, profitability, or strategy edge",
            "the compared processes may share upstream public data or code defects",
            "one event cannot establish expected performance or authorize a live change",
        ],
    }


def _validate_scope(
    rows: Mapping[str, Record],
    kinds: Mapping[str, str],
    provider_id: str,
    symbol: str,
    decision_time_ms: int,
) -> str:
    if set(rows) != set(kinds) or len(rows) < 3:
        raise ValueError("parity requires matching live and two-observer sources")
    if any(not value.strip() for value in (*rows, provider_id, symbol)):
        raise ValueError("parity source and target identities must be nonempty")
    if isinstance(decision_time_ms, bool) or decision_time_ms < 0:
        raise ValueError("parity decision time must be nonnegative")
    live = [name for name, kind in kinds.items() if kind == "live"]
    observers = [name for name, kind in kinds.items() if kind == "observer"]
    if len(live) != 1 or len(observers) < 2 or len(live) + len(observers) != len(rows):
        raise ValueError("parity requires exactly one live source and two observers")
    for source, row in rows.items():
        _validate_authority(row, kinds[source])
    return live[0]


def _validate_authority(row: Record, kind: str) -> None:
    expected = (
        ("live", True, "hyperliquid_mainnet")
        if kind == "live"
        else ("observe", False, "none")
    )
    observed = (
        row.get("execution_mode"),
        row.get("live_armed"),
        row.get("execution_authority"),
    )
    if observed != expected:
        raise ValueError(f"{kind} parity source authority is inconsistent")
    for key in ("profile_id", "profile_fingerprint", "run_fingerprint", "run_id"):
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"parity source requires {key}")


def _evaluation(
    row: Record,
    provider_id: str,
    symbol: str,
    decision_time_ms: int,
) -> Record:
    if row.get("event_type") != "intent_routing":
        raise ValueError("parity source must be an intent-routing row")
    payload = _object(row.get("payload"), "intent-routing payload")
    values = payload.get("evaluations")
    if not isinstance(values, list):
        raise ValueError("intent-routing evaluations must be a list")
    matches = [
        _object(value, "provider evaluation")
        for value in values
        if isinstance(value, Mapping)
        and (
            value.get("strategy_id"),
            value.get("symbol"),
            value.get("decision_time_ms"),
        )
        == (provider_id, symbol, decision_time_ms)
    ]
    if len(matches) != 1:
        raise ValueError("parity source must contain one exact provider evaluation")
    return matches[0]


def _semantic_view(evaluation: Record) -> dict[str, object]:
    output = _normalize(evaluation, ())
    if not isinstance(output, dict):
        raise ValueError("normalized provider evaluation must be an object")
    output.setdefault("target_anchor", None)
    return output


def _normalize(value: object, path: tuple[str, ...]) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize(item, (*path, str(key)))
            for key, item in value.items()
            if not (path == ("readiness", "metrics") and key in _AUTHORITY_METRICS)
        }
    if isinstance(value, list):
        return [_normalize(item, path) for item in value]
    if isinstance(value, str) and path == ("readiness", "indicators"):
        return value.replace("[AUTOMATIC EXECUTION]", "[AUTHORITY]").replace(
            "[REPORT ONLY]", "[AUTHORITY]"
        )
    return value


def _source_mismatches(
    semantic: Mapping[str, dict[str, object]], live_source: str
) -> list[dict[str, object]]:
    reference = semantic[live_source]
    output: list[dict[str, object]] = []
    for source in sorted(name for name in semantic if name != live_source):
        output.extend(_differences(reference, semantic[source], source, ""))
    return output


def _differences(
    expected: object, observed: object, source: str, path: str
) -> list[dict[str, object]]:
    if isinstance(expected, Mapping) and isinstance(observed, Mapping):
        output: list[dict[str, object]] = []
        for key in sorted(set(expected) | set(observed)):
            child = f"{path}.{key}" if path else str(key)
            output.extend(
                _differences(expected.get(key), observed.get(key), source, child)
            )
        return output
    if isinstance(expected, list) and isinstance(observed, list):
        if len(expected) != len(observed):
            return [_mismatch(source, path, expected, observed)]
        output = []
        for index, (left, right) in enumerate(zip(expected, observed, strict=True)):
            output.extend(_differences(left, right, source, f"{path}[{index}]"))
        return output
    if _equal(expected, observed):
        return []
    return [_mismatch(source, path, expected, observed)]


def _equal(expected: object, observed: object) -> bool:
    numeric = (int, float)
    if (
        isinstance(expected, numeric)
        and not isinstance(expected, bool)
        and isinstance(observed, numeric)
        and not isinstance(observed, bool)
    ):
        return math.isclose(
            float(expected),
            float(observed),
            rel_tol=_FLOAT_REL_TOLERANCE,
            abs_tol=_FLOAT_ABS_TOLERANCE,
        )
    return expected == observed


def _mismatch(
    source: str, path: str, expected: object, observed: object
) -> dict[str, object]:
    return {"source": source, "path": path, "live": expected, "observed": observed}


def _source_records(
    rows: Mapping[str, Record],
    kinds: Mapping[str, str],
    evaluations: Mapping[str, Record],
) -> dict[str, object]:
    return {
        source: {
            "kind": kinds[source],
            "sequence": row.get("sequence"),
            "observed_at_utc": row.get("observed_at_utc"),
            "execution_mode": row.get("execution_mode"),
            "effective_mode": row.get("effective_mode"),
            "live_armed": row.get("live_armed"),
            "execution_authority": row.get("execution_authority"),
            "profile_id": row.get("profile_id"),
            "profile_fingerprint": row.get("profile_fingerprint"),
            "run_fingerprint": row.get("run_fingerprint"),
            "run_id": row.get("run_id"),
            "evaluation_sha256": _digest(evaluations[source]),
        }
        for source, row in rows.items()
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }


def _digest(value: Record) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _object(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value
