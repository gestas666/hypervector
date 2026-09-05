"""Immutable raw storage for BTC liquidation development economics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    publish_immutable_directory,
    write_json,
)
from hypervector.research.btc_liquidation_covariate_models import (
    DepthExecution,
    FundingAdjustedHorizon,
)
from hypervector.research.btc_liquidation_development_materializer import (
    DevelopmentEpisodeReplay,
)

_MODE = "v58_btc_liquidation_development_economic_materialization"
_HYPOTHESIS = "v58-btc-short-liquidation-continuation-long-data-preflight"


def episode_arm_records(
    result: DevelopmentEpisodeReplay,
) -> tuple[dict[str, object], ...]:
    """Serialize one episode once for every frozen eligible intensity arm."""
    entry = result.entry
    episode = entry.episode
    common: dict[str, object] = {
        "schema_version": "btc_liquidation_development_arm_result_v1",
        "hypothesis_id": _HYPOTHESIS,
        "episode_id": episode.episode_id,
        "partition": episode.partition,
        "branch": episode.branch,
        "episode_end_ms": episode.end_ms,
        "episode_vwap": str(episode.volume_weighted_price),
        "entry": _entry_record(result),
        "regime": _regime_record(result.regime),
        "outcomes": [_outcome_record(row) for row in result.outcomes],
    }
    return tuple({**common, "arm": arm} for arm in episode.eligible_arms)


def build_development_materialization_report(
    records: tuple[dict[str, object], ...],
    *,
    episode_count: int,
    window_count: int,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    """Summarize raw development coverage without selecting an economic winner."""
    _validate_records(records, episode_count, window_count)
    entry_status = Counter(
        _mapping(row.get("entry"), "entry").get("status") for row in records
    )
    arm_counts = Counter(str(row.get("arm")) for row in records)
    horizon_status = Counter(
        (outcome.get("horizon_ms"), outcome.get("status"))
        for row in records
        for outcome in _record_list(row.get("outcomes"), "outcomes")
    )
    return {
        "schema_version": 1,
        "mode": _MODE,
        "hypothesis_id": _HYPOTHESIS,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "development_materialized_not_disposed",
        "contract": _contract(),
        "summary": {
            "episode_count": episode_count,
            "arm_record_count": len(records),
            "window_count": window_count,
            "entry_status_counts": _counter(entry_status),
            "arm_counts": _counter(arm_counts),
            "horizon_status_counts": {
                f"{horizon}:{status}": count
                for (horizon, status), count in sorted(horizon_status.items())
            },
        },
        "evidence": dict(evidence),
    }


def publish_development_materialization(
    output: Path,
    records: tuple[dict[str, object], ...],
    report: Mapping[str, object],
) -> None:
    """Atomically publish development rows and a hash-bound report once."""
    if not records:
        raise ValueError("development materialization has no records")

    def writer(staging: Path) -> None:
        results_path = staging / "results.jsonl.gz"
        with gzip_text_writer(results_path) as handle:
            for row in records:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
                handle.write("\n")
        report_path = staging / "report.json"
        write_json(report_path, dict(report))
        write_json(
            staging / "manifest.json",
            {
                "schema_version": "immutable_evidence_manifest_v1",
                "files": {
                    path.name: file_evidence(path)
                    for path in (report_path, results_path)
                },
            },
        )

    publish_immutable_directory(output, writer)


def _entry_record(result: DevelopmentEpisodeReplay) -> dict[str, object]:
    entry = result.entry
    return {
        "status": entry.status,
        "blockers": list(entry.blockers),
        "decision_time_ms": entry.decision_time_ms,
        "flow_imbalance": _decimal(entry.flow_imbalance),
        "decision_book_time_ms": entry.decision_book_time_ms,
        "decision_midpoint": _decimal(entry.decision_midpoint),
        "fill": _depth_record(entry.entry_fill),
    }


def _depth_record(fill: DepthExecution | None) -> dict[str, object] | None:
    if fill is None:
        return None
    return {
        "requested_quantity": str(fill.requested_quantity),
        "filled_quantity": str(fill.filled_quantity),
        "quote_notional": str(fill.quote_notional),
        "vwap": str(fill.vwap),
        "best_price": str(fill.best_price),
        "worst_price": str(fill.worst_price),
        "impact_bps": str(fill.impact_bps),
        "levels_consumed": fill.levels_consumed,
        "complete": fill.complete,
    }


def _outcome_record(row: FundingAdjustedHorizon) -> dict[str, object]:
    replay = row.replay
    funding = row.funding
    return {
        "horizon_ms": replay.horizon_ms,
        "target_time_ms": replay.target_time_ms,
        "status": replay.status,
        "reason": replay.reason,
        "exit_book_time_ms": replay.exit_book_time_ms,
        "exit_fill": _depth_record(replay.exit_fill),
        "gross_pnl_usd": _decimal(replay.gross_pnl_usd),
        "fee_usd": _decimal(replay.fee_usd),
        "funding_settlement_count": (
            None if funding is None else funding.settlement_count
        ),
        "total_funding_rate": (
            None if funding is None else str(funding.total_funding_rate)
        ),
        "funding_cashflow_usd": (
            None if funding is None else str(funding.cashflow_usd)
        ),
        "nominal_net_pnl_usd": _decimal(row.nominal_net_pnl_usd),
        "stressed_net_pnl_usd": _decimal(row.stressed_net_pnl_usd),
    }


def _regime_record(value: Mapping[str, object]) -> dict[str, object]:
    return {
        "bar_open_at": _timestamp(value.get("bar_open_at"), "bar_open_at"),
        "available_at": _timestamp(value.get("available_at"), "available_at"),
        "primary_regime": _text(value.get("primary_regime"), "primary_regime"),
        "regime_strength_score": _optional_float(value.get("regime_strength_score")),
        "breakout_direction": _optional_text(value.get("breakout_direction")),
    }


def _validate_records(
    records: tuple[dict[str, object], ...], episode_count: int, window_count: int
) -> None:
    if episode_count <= 0 or window_count <= 0 or not records:
        raise ValueError("development coverage counts must be positive")
    identities = tuple((row.get("episode_id"), row.get("arm")) for row in records)
    if len(identities) != len(set(identities)):
        raise ValueError("development arm result identities must be unique")
    episodes = {row.get("episode_id") for row in records}
    if len(episodes) != episode_count:
        raise ValueError("development result episode count does not reconcile")
    if any(row.get("partition") != "development" for row in records):
        raise ValueError("development output contains a sealed partition")


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "strategy_mutation": False,
        "development_outcomes_opened": True,
        "validation_outcomes_opened": False,
        "pseudo_holdout_outcomes_opened": False,
        "statistical_disposition_computed": False,
    }


def _counter(value: Counter[object]) -> dict[str, int]:
    return {str(key): int(count) for key, count in sorted(value.items(), key=str)}


def _record_list(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"development {label} must be a record list")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"development {label} must be an object")
    return value


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _timestamp(value: object, label: str) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError(f"development regime {label} must be timezone-aware")
    return timestamp.tz_convert("UTC").isoformat()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"development regime {label} must be nonempty text")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None or pd.isna(value) else _text(value, "optional field")


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("development regime score must be numeric")
    return float(value)
