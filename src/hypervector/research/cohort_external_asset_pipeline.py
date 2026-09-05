"""Source-bound external-asset evidence for the v51 improvement digest."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path

from hypervector.research.cohort_external_lifecycle_status import (
    load_external_lifecycle_status,
)
from hypervector.research.cohort_external_partial_lifecycle import (
    load_external_partial_lifecycle,
)
from hypervector.research.cohort_external_comparable_epoch import (
    load_comparable_decision_epoch,
)
from hypervector.research.cohort_external_candidate_evidence import (
    external_candidate_source_evidence,
    external_candidate_status,
)

Record = Mapping[str, object]

_REPORT_ONLY = {
    "report_only": True,
    "execution_authority": "none",
    "automatic_promotion": False,
    "runtime_strategy_changed": False,
}


@dataclass(frozen=True)
class ExternalAssetPipeline:
    """Validated external candidate status and its exact source evidence."""

    status: dict[str, object]
    evidence: dict[str, object]


def load_external_asset_pipeline(
    catalog_path: Path,
    *,
    observed_at: datetime,
    maximum_observer_age_seconds: float,
) -> ExternalAssetPipeline:
    """Load a fail-closed report-only candidate catalog and fresh observers."""
    _require_aware(observed_at)
    _require_positive_finite(maximum_observer_age_seconds)
    catalog_raw = catalog_path.read_bytes()
    catalog = _mapping(json.loads(catalog_raw), "external candidate catalog")
    _require_contract(
        _mapping(catalog.get("contract"), "external candidate catalog contract"),
        "external candidate catalog",
    )
    liquidity, liquidity_evidence = _load_exact_json(
        catalog_path, catalog.get("liquidity_source"), "external liquidity source"
    )
    _require_source_contract(liquidity, "external liquidity source")
    markets = _liquidity_markets(liquidity)
    records = _candidate_records(catalog)
    candidates, evidence = _load_candidates(
        catalog_path,
        records,
        markets,
        observed_at,
        maximum_observer_age_seconds,
    )
    return ExternalAssetPipeline(
        status={
            **_REPORT_ONLY,
            "observed_at_utc": observed_at.isoformat(),
            "candidate_count": len(candidates),
            "candidates": candidates,
        },
        evidence={
            "catalog": _raw_evidence(catalog_path, catalog_raw),
            "liquidity_source": liquidity_evidence,
            "candidates": evidence,
        },
    )


def _load_candidates(
    catalog_path: Path,
    records: list[Record],
    markets: dict[str, tuple[int, Record]],
    observed_at: datetime,
    maximum_age_seconds: float,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    candidates: list[dict[str, object]] = []
    evidence: dict[str, object] = {}
    for record in records:
        candidate, source = _load_candidate(
            catalog_path, record, markets, observed_at, maximum_age_seconds
        )
        observer = _mapping(candidate.get("observer"), "external observer status")
        partial, partial_evidence = load_external_partial_lifecycle(
            catalog_path,
            record,
            symbol=str(candidate["symbol"]),
            provider_id=str(observer["provider_id"]),
            profile_id=str(observer["profile_id"]),
            observed_at=observed_at,
        )
        candidate["partial_lifecycle_evidence"] = partial
        if partial_evidence is not None:
            source["partial_lifecycle_evidence"] = partial_evidence
        candidates.append(candidate)
        evidence[_text(record.get("symbol"), "external candidate symbol")] = source
    return candidates, evidence


def _load_candidate(
    catalog_path: Path,
    record: Record,
    markets: dict[str, tuple[int, Record]],
    observed_at: datetime,
    maximum_age_seconds: float,
) -> tuple[dict[str, object], dict[str, object]]:
    symbol = _text(record.get("symbol"), "external candidate symbol")
    if symbol not in markets:
        raise ValueError(f"external candidate missing liquidity: {symbol}")
    observer, observer_evidence = _load_observer(
        catalog_path, record, symbol, observed_at, maximum_age_seconds
    )
    epoch = load_comparable_decision_epoch(
        catalog_path,
        record,
        symbol=symbol,
        profile_id=str(observer["profile_id"]),
        provider_id=str(observer["provider_id"]),
        observed_at_ms=int(observed_at.timestamp() * 1_000),
    )
    validation, validation_evidence = _load_technical_validation(
        catalog_path, record, symbol
    )
    lifecycle, lifecycle_evidence = load_external_lifecycle_status(
        catalog_path, record, symbol, observed_at, maximum_age_seconds
    )
    historical, historical_evidence = _load_historical(catalog_path, record, symbol)
    immutable_evidence = _load_immutable_evidence(catalog_path, record, symbol)
    candidate = external_candidate_status(
        record,
        symbol,
        markets[symbol],
        observer,
        None if epoch is None else epoch.status,
        lifecycle,
        validation,
        historical,
    )
    source = external_candidate_source_evidence(
        observer_evidence,
        immutable_evidence,
        historical_evidence,
        validation_evidence,
        lifecycle_evidence,
        None if epoch is None else epoch.evidence,
    )
    return candidate, source


def _load_technical_validation(
    catalog_path: Path, record: Record, symbol: str
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    source_value = record.get("technical_validation_status")
    if source_value is None:
        return None, None
    source = _mapping(source_value, "external technical validation status")
    path = _resolve(catalog_path, source.get("path"), "validation status path")
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), f"external technical validation {symbol}")
    _require_technical_validation_contract(payload, source, symbol)
    expected = _integer(payload.get("expected_decisions"), "validation expected")
    observed = _integer(payload.get("observed_decisions"), "validation observed")
    resolved = _integer(payload.get("resolved_decisions"), "validation resolved")
    eligible = _integer(payload.get("eligible_decisions"), "validation eligible")
    if expected == 0 or not eligible <= resolved <= observed <= expected:
        raise ValueError(f"external technical validation counts are invalid: {symbol}")
    start = _integer(payload.get("window_start_ms"), "validation window start")
    end = _integer(payload.get("window_end_exclusive_ms"), "validation window end")
    if start == 0 or end <= start:
        raise ValueError(f"external technical validation window is invalid: {symbol}")
    state = _validation_state(payload.get("state"))
    return {
        "mode": payload["mode"],
        "hypothesis_id": payload["hypothesis_id"],
        "state": state,
        "window_start_ms": start,
        "window_end_exclusive_ms": end,
        "expected_decisions": expected,
        "observed_decisions": observed,
        "resolved_decisions": resolved,
        "eligible_decisions": eligible,
        "coverage_fraction": resolved / expected,
        "complete": resolved == expected,
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }, _raw_evidence(path, raw)


def _require_technical_validation_contract(
    payload: Record, source: Record, symbol: str
) -> None:
    expected = {
        "schema_version": 1,
        "mode": _text(source.get("mode"), "validation status mode"),
        "hypothesis_id": _text(
            source.get("hypothesis_id"), "validation status hypothesis"
        ),
        "symbol": symbol,
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
    if any(payload.get(field) != value for field, value in expected.items()):
        raise ValueError(f"external technical validation contract is invalid: {symbol}")


def _validation_state(value: object) -> str:
    state = _text(value, "validation status state")
    allowed = {
        "collecting",
        "collecting_source_failure",
        "finalized_pass",
        "finalized_fail",
        "already_finalized_pass",
        "already_finalized_fail",
    }
    if state not in allowed:
        raise ValueError(f"external technical validation state is invalid: {state}")
    return state


def _load_observer(
    catalog_path: Path,
    record: Record,
    symbol: str,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> tuple[dict[str, object], dict[str, object]]:
    path = _resolve(catalog_path, record.get("observer_path"), "observer path")
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), f"external observer {symbol}")
    _require_contract(payload, f"external observer {symbol}")
    for field in ("orders_supported", "signing_client_constructed"):
        if payload.get(field) is not False:
            raise ValueError(f"external observer has invalid {field}: {symbol}")
    if payload.get("symbol") != symbol:
        raise ValueError(f"external observer symbol mismatch: {symbol}")
    observed_ms = _integer(payload.get("observed_at_ms"), "observer observed_at_ms")
    timestamp = datetime.fromtimestamp(observed_ms / 1000.0, tz=UTC)
    age = (observed_at - timestamp).total_seconds()
    if age < 0.0:
        raise ValueError(f"external observer is from the future: {symbol}")
    return (
        _observer_status(payload, timestamp, age, maximum_age_seconds),
        _raw_evidence(path, raw),
    )


def _observer_status(
    payload: Record,
    timestamp: datetime,
    age_seconds: float,
    maximum_age_seconds: float,
) -> dict[str, object]:
    stale = age_seconds > maximum_age_seconds
    blockers = _text_list(
        payload.get("promotion_blockers"), "external promotion blockers"
    )
    if stale and "observer_stale" not in blockers:
        blockers.append("observer_stale")
    status = {
        "mode": _text(payload.get("mode"), "external observer mode"),
        "profile_id": _text(payload.get("profile_id"), "external profile id"),
        "provider_id": _text(payload.get("provider_id"), "external provider id"),
        "observed_at_utc": timestamp.isoformat(),
        "age_seconds": age_seconds,
        "maximum_age_seconds": maximum_age_seconds,
        "freshness_status": "stale" if stale else "fresh",
        "promotion_blockers": blockers,
    }
    for field in (
        "decisions_published",
        "decision_rows_total",
        "eligible_decisions_total",
        "long_decisions_total",
        "short_decisions_total",
        "non_action_decisions_total",
        "live_canary_execution_observations",
        "prospective_candle_rows_total",
    ):
        value = payload.get(field)
        if value is not None:
            status[field] = _integer(value, f"external observer {field}")
    for field in (
        "latest_trailing_return_bps",
        "latest_shock_threshold_bps",
        "latest_threshold_fraction",
        "maximum_threshold_fraction_total",
    ):
        value = payload.get(field)
        if value is not None:
            status[field] = _number(value, f"external observer {field}")
    return status


def _load_historical(
    catalog_path: Path, record: Record, symbol: str
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    source = record.get("historical_live_source")
    if source is None:
        return None, None
    payload, evidence = _load_exact_json(
        catalog_path, source, f"external historical live {symbol}"
    )
    _require_historical_contract(payload, symbol)
    coverage = _mapping(payload.get("ledger_coverage"), "historical ledger coverage")
    summary = _mapping(
        payload.get("descriptive_all_live_lifecycles"), "historical live summary"
    )
    return {
        "ledger_rows": _integer(coverage.get("rows"), "historical ledger rows"),
        "book_observations": _integer(
            coverage.get("book_observations"), "historical book observations"
        ),
        "raw_fill_events": _integer(
            coverage.get("raw_fill_events"), "historical fill events"
        ),
        "closed_lifecycles": _integer(
            coverage.get("reconciled_closed_lifecycles"), "historical closes"
        ),
        "wins": _integer(summary.get("wins"), "historical wins"),
        "losses": _integer(summary.get("losses"), "historical losses"),
        "net_pnl_usd": _number(summary.get("net_pnl_usd"), "historical net"),
        "profit_factor": _number(
            summary.get("profit_factor"), "historical profit factor"
        ),
        "net_excluding_largest_winner_usd": _number(
            summary.get("net_pnl_excluding_largest_winner_usd"),
            "historical net excluding largest winner",
        ),
    }, evidence


def _load_immutable_evidence(
    catalog_path: Path, record: Record, symbol: str
) -> list[dict[str, object]]:
    values = record.get("immutable_evidence")
    if not isinstance(values, list):
        raise ValueError(f"external immutable evidence must be an array: {symbol}")
    evidence = []
    for index, source in enumerate(values):
        _, item = _load_exact_json(
            catalog_path, source, f"external immutable evidence {symbol} {index}"
        )
        evidence.append(item)
    return evidence


def _load_exact_json(
    catalog_path: Path, value: object, label: str
) -> tuple[Record, dict[str, object]]:
    source = _mapping(value, label)
    path = _resolve(catalog_path, source.get("path"), f"{label} path")
    raw = path.read_bytes()
    if source.get("sha256") != sha256(raw).hexdigest() or source.get("bytes") != len(
        raw
    ):
        raise ValueError(f"external candidate evidence mismatch: {path}")
    return _mapping(json.loads(raw), label), _raw_evidence(path, raw)


def _require_contract(payload: Record, label: str) -> None:
    for field, expected in _REPORT_ONLY.items():
        if payload.get(field) != expected:
            raise ValueError(f"{label} has invalid {field}")


def _require_source_contract(payload: Record, label: str) -> None:
    expected = {
        "mode": "hip3_market_qualification_v1",
        "status": "qualified_for_observation_only",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"{label} has invalid {field}")


def _require_historical_contract(payload: Record, symbol: str) -> None:
    expected = {
        "mode": "report_only",
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "symbol": symbol,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"external historical live has invalid {field}: {symbol}")


def _candidate_records(catalog: Record) -> list[Record]:
    values = catalog.get("candidates")
    if not isinstance(values, list) or not values:
        raise ValueError("external candidate catalog requires candidates")
    records = [_mapping(value, "external candidate") for value in values]
    symbols = [
        _text(record.get("symbol"), "external candidate symbol") for record in records
    ]
    if len(symbols) != len(set(symbols)):
        raise ValueError("external candidate symbols must be unique")
    return records


def _liquidity_markets(payload: Record) -> dict[str, tuple[int, Record]]:
    values = payload.get("markets")
    if not isinstance(values, list) or not values:
        raise ValueError("external liquidity source requires markets")
    output: dict[str, tuple[int, Record]] = {}
    for rank, value in enumerate(values, start=1):
        market = _mapping(value, "external liquidity market")
        symbol = _text(market.get("symbol"), "external liquidity symbol")
        if symbol in output:
            raise ValueError(f"duplicate external liquidity symbol: {symbol}")
        output[symbol] = (rank, market)
    return output


def _resolve(catalog_path: Path, value: object, label: str) -> Path:
    text = _text(value, label)
    path = Path(text)
    return path if path.is_absolute() else (catalog_path.parent / path).resolve()


def _raw_evidence(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return [_text(item, label) for item in value]


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _require_positive_finite(value: float) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("maximum external observer age must be positive and finite")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("external pipeline observation time must include a timezone")
