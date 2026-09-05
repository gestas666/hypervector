"""Source-bound historical ETH exit disposition for continuous V58 research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path

Record = Mapping[str, object]

_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_SYMBOL = "ETH"
_CONTROL_ID = "generic_8h_control"
_LOCK_IDS = (
    "profit_a25_floor15_trail10",
    "profit_a40_floor15_trail20",
    "profit_a60_floor15_trail30",
)
_CONTROL_FIELDS = (
    "trades",
    "wins",
    "losses",
    "net_return_bps",
    "profit_factor",
    "maximum_drawdown_bps",
    "exit_reasons",
)


@dataclass(frozen=True)
class EthExitResearchContext:
    """Execution-incapable frozen ETH exit-policy history."""

    payload: dict[str, object]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_eth_exit_research_context(
    journal_path: Path, duration_path: Path
) -> EthExitResearchContext:
    """Validate and summarize the immutable ETH exit decision sources."""
    journal, journal_evidence = _read(journal_path, "ETH exit journal")
    duration, duration_evidence = _read(duration_path, "ETH duration artifact")
    _require_journal(journal, duration_evidence)
    _require_duration(duration)
    durations = _duration_rows(duration)
    locks = _profit_lock_rows(duration)
    _require_control_matches_720(durations, locks)
    payload = _payload(journal, durations, locks)
    return EthExitResearchContext(
        payload,
        {
            "journal": {"path": str(journal_path.resolve()), **journal_evidence},
            "duration": {"path": str(duration_path.resolve()), **duration_evidence},
        },
    )


def eth_exit_research_payload(context: EthExitResearchContext) -> dict[str, object]:
    """Serialize historical context without creating a performance gate."""
    return {
        **context.payload,
        "historical_evidence_is_proven_optimum": False,
        "performance_gate": False,
        "automatic_strategy_change": False,
        "execution_authority": context.execution_authority,
    }


def _payload(journal: Record, durations: Record, locks: Record) -> dict[str, object]:
    final_720 = _row(
        _mapping(durations["opened_final_60d"], "final durations"), "fixed_720m"
    )
    return {
        "strategy_id": _STRATEGY,
        "symbol": _SYMBOL,
        "retained_maximum_hold_minutes": 720,
        "duration_dispositions": _duration_dispositions(durations),
        "rejected_profit_locks": list(_rejected_locks(locks)),
        "legacy_control_policy_id": _CONTROL_ID,
        "legacy_control_enforced_hold_minutes": 720,
        "opened_final_720m_ex_largest_positive": (
            _number(
                final_720.get("net_excluding_largest_winner_bps"), "final ex-largest"
            )
            > 0.0
        ),
        "decision": _text(journal.get("decision"), "ETH exit decision"),
        "revisit_falsifier": _text(journal.get("falsifier"), "ETH exit falsifier"),
    }


def _duration_dispositions(durations: Record) -> dict[str, str]:
    development = _mapping(durations["development"], "development durations")
    final = _mapping(durations["opened_final_60d"], "final durations")
    rows = {
        minutes: (_row(development, key), _row(final, key))
        for minutes, key in (
            ("240", "fixed_240m"),
            ("480", "fixed_480m"),
            ("720", "fixed_720m"),
        )
    }
    if _net(rows["240"][0]) >= 0.0 or _net(rows["480"][1]) >= 0.0:
        raise ValueError("V58 ETH rejected duration evidence changed")
    if _net(rows["720"][0]) <= 0.0 or _net(rows["720"][1]) <= 0.0:
        raise ValueError("V58 ETH retained duration is no longer positive")
    return {
        "240": "rejected_development_negative",
        "480": "rejected_opened_final_negative",
        "720": "retained_least_contradicted",
    }


def _rejected_locks(locks: Record) -> tuple[str, ...]:
    development = _mapping(locks["development"], "development locks")
    final = _mapping(locks["opened_final_60d"], "final locks")
    if set(development) != {_CONTROL_ID, *_LOCK_IDS} or set(final) != {
        _CONTROL_ID,
        *_LOCK_IDS,
    }:
        raise ValueError("V58 ETH profit-lock policy set changed")
    if any(
        _net(_row(development, lock)) > 0.0 and _net(_row(final, lock)) > 0.0
        for lock in _LOCK_IDS
    ):
        raise ValueError("V58 ETH rejected profit-lock evidence changed")
    return _LOCK_IDS


def _require_control_matches_720(durations: Record, locks: Record) -> None:
    for partition in ("development", "opened_final_60d"):
        duration = _row(
            _mapping(durations[partition], "duration partition"), "fixed_720m"
        )
        control = _row(_mapping(locks[partition], "profit-lock partition"), _CONTROL_ID)
        if any(control.get(field) != duration.get(field) for field in _CONTROL_FIELDS):
            raise ValueError("V58 ETH legacy profit-lock control differs from 12h")


def _require_journal(journal: Record, duration_evidence: Record) -> None:
    expected = {
        "schema_version": 1,
        "hypothesis_id": "eth-breakout-precompression-pullback",
        "revision_number": 5,
        "strategy_id": _STRATEGY,
        "symbol": _SYMBOL,
        "status": "candidate",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    if any(journal.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH exit journal identity is invalid")
    evidence = _duration_reference(journal.get("evidence"))
    if (
        evidence.get("sha256") != duration_evidence["sha256"]
        or evidence.get("bytes") != duration_evidence["bytes"]
    ):
        raise ValueError("V58 ETH duration evidence differs from journal")


def _require_duration(duration: Record) -> None:
    expected = {
        "schema_version": 1,
        "mode": "eth_pullback_side_breakout_relation_attribution_v1",
        "strategy_id": _STRATEGY,
        "symbol": _SYMBOL,
    }
    if any(duration.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH duration artifact identity is invalid")
    contract = _mapping(duration.get("contract"), "ETH duration contract")
    safe = {
        "automatic_promotion": False,
        "entry_gate": False,
        "execution_authority": "none",
        "portfolio_pnl_claimed": False,
        "report_only": True,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(field) != value for field, value in safe.items()):
        raise ValueError("V58 ETH duration artifact authority is invalid")
    coverage = _mapping(duration.get("coverage"), "ETH duration coverage")
    if (
        coverage.get("development_trades") != 282
        or coverage.get("opened_final_trades") != 56
    ):
        raise ValueError("V58 ETH duration coverage changed")


def _duration_rows(duration: Record) -> Record:
    return _mapping(duration.get("duration_comparison"), "ETH durations")


def _profit_lock_rows(duration: Record) -> Record:
    return _mapping(duration.get("profit_lock_comparison"), "ETH profit locks")


def _duration_reference(value: object) -> Record:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("V58 ETH journal evidence must be an array")
    matches = [
        _mapping(item, "ETH journal evidence")
        for item in value
        if isinstance(item, Mapping)
        and item.get("role") == "exact_fixed_entry_profit_lock_and_duration_comparison"
    ]
    if len(matches) != 1:
        raise ValueError("V58 ETH duration journal reference is invalid")
    return matches[0]


def _read(path: Path, label: str) -> tuple[Record, dict[str, object]]:
    raw = path.read_bytes()
    value = json.loads(raw)
    return _mapping(value, label), {
        "bytes": len(raw),
        "sha256": sha256(raw).hexdigest(),
    }


def _row(rows: Record, key: str) -> Record:
    return _mapping(rows.get(key), f"ETH {key}")


def _net(row: Record) -> float:
    return _number(row.get("net_return_bps"), "ETH net return")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 {label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"V58 {label} must be non-empty text")
    return value.strip()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 {label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"V58 {label} must be finite")
    return number
