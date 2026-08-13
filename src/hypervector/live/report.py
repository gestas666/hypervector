"""Read-only live decision ledger summary (ops).

Pure counters over ``data/live/decisions/decisions.jsonl``. Never places
orders. Used by ``live-report`` CLI. Symmetric to :mod:`hypervector.paper.report`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from hypervector.infra import paths_for
from hypervector.live.ledger import DECISIONS_FILENAME
from hypervector.paper.report import load_decision_rows

_MARKET_ACTIONS = frozenset(
    {
        "enter_long",
        "enter_short",
        "close",
        "close_long",
        "close_short",
        "exit",
        "flatten",
    }
)


def default_live_decisions_path(data_root: Path | str) -> Path:
    return paths_for(data_root).live_decisions / DECISIONS_FILENAME


def _count(values: list[Any]) -> dict[str, int]:
    c = Counter("" if v is None else str(v) for v in values)
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


def _is_under(path: Path, ancestor: Path) -> bool:
    p = path.resolve()
    a = ancestor.resolve()
    if p == a:
        return True
    try:
        p.relative_to(a)
        return True
    except ValueError:
        return False


def summarize_live_decisions(
    rows: list[dict[str, Any]],
    *,
    decisions_path: Path | str | None = None,
    last_n: int = 5,
) -> dict[str, Any]:
    """Aggregate honesty + ops counters for live ledgers."""
    n = max(0, int(last_n))
    normalized = [_normalize_event_row(row) for row in rows]
    market_fills = _market_rows(normalized)
    report = _summary_counts(normalized, market_fills, decisions_path)
    report.update(
        {
            "last_market": _market_sample(market_fills, n),
            "event_sourced": _event_sourced_summary(normalized),
            "live_submit_implemented": True,
            "command": "live-run",
        }
    )
    return report


def _summary_counts(
    rows: list[dict[str, Any]],
    market_fills: list[dict[str, Any]],
    decisions_path: Path | str | None,
) -> dict[str, Any]:
    funding = [row for row in rows if row.get("action") == "funding"]
    sessions = [row for row in rows if row.get("action") == "session_start"]
    return {
        "ok": True,
        "ledger": "live",
        "decisions_path": str(decisions_path) if decisions_path is not None else None,
        "rows": len(rows),
        "market_fills": len(market_fills),
        "funding_rows": len(funding),
        "session_start_rows": len(sessions),
        "execution_mode": _count([r.get("execution_mode") for r in rows]),
        "submitted": _count([r.get("submitted") for r in rows]),
        "place_attempted": _count([r.get("place_attempted") for r in rows]),
        "live_phase": _count([r.get("live_phase") for r in rows]),
        "network": _count([r.get("network") for r in rows]),
        "action": _count([r.get("action") for r in market_fills]),
        "fill_model_id": _count([r.get("fill_model_id") for r in market_fills]),
        "submit_error": _count(
            [r.get("submit_error") for r in market_fills if r.get("submit_error")]
        ),
        "honesty": _honesty(rows),
    }


def _market_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("action") != "funding"
        and (
            str(row.get("action") or "") in _MARKET_ACTIONS
            or row.get("fill_model_id") is not None
            or row.get("place_attempted") is True
        )
    ]


def _market_sample(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    sample: list[dict[str, Any]] = []
    for row in rows[-count:] if count else []:
        intent = row.get("order_intent")
        order_intent = intent if isinstance(intent, dict) else {}
        sample.append(_sample_row(row, order_intent))
    return sample


def _sample_row(
    row: dict[str, Any],
    order_intent: dict[str, Any],
) -> dict[str, Any]:
    return {
        "feed_ts": row.get("feed_ts"),
        "action": row.get("action"),
        "execution_mode": row.get("execution_mode"),
        "submitted": row.get("submitted"),
        "place_attempted": row.get("place_attempted"),
        "live_phase": row.get("live_phase"),
        "venue_order_id": row.get("venue_order_id"),
        "submit_error": row.get("submit_error"),
        "network": row.get("network"),
        "fill_model_id": row.get("fill_model_id"),
        "order_intent_submit_enabled": order_intent.get("submit_enabled"),
    }


def _honesty(rows: list[dict[str, Any]]) -> dict[str, Any]:
    modes = {str(row["execution_mode"]) for row in rows if "execution_mode" in row}
    networks = {str(row["network"]) for row in rows if row.get("network")}
    return {
        "modes_seen": sorted(modes),
        "networks_seen": sorted(networks),
        "all_execution_mode_live": all(mode == "live" for mode in modes),
        "submitted_true_count": sum(row.get("submitted") is True for row in rows),
        "place_attempted_true_count": sum(
            row.get("place_attempted") is True for row in rows
        ),
        "live_phase_true_count": sum(row.get("live_phase") is True for row in rows),
    }


def _normalize_event_row(row: dict[str, Any]) -> dict[str, Any]:
    event_type = str(row.get("event_type") or "")
    if not event_type:
        return row
    payload = row.get("payload")
    normalized = dict(payload) if isinstance(payload, dict) else {}
    normalized.update(row)
    normalized.setdefault("feed_ts", row.get("observed_at_utc"))
    normalized.setdefault("action", _event_action(event_type, normalized))
    if event_type == "fill":
        normalized.setdefault("fill_model_id", "hyperliquid_mainnet")
        normalized.setdefault("venue_order_id", normalized.get("oid"))
    if not normalized.get("network") and row.get("execution_authority") == (
        "hyperliquid_mainnet"
    ):
        normalized["network"] = "mainnet"
    return normalized


def _event_action(event_type: str, row: dict[str, Any]) -> str | None:
    if event_type == "funding":
        return "funding"
    if event_type == "configuration_identity":
        return "session_start"
    if event_type != "fill":
        return None
    direction = str(row.get("direction") or "").strip().lower()
    if direction == "open long":
        return "enter_long"
    if direction == "open short":
        return "enter_short"
    if direction.startswith("close "):
        return "close"
    return "fill"


def _event_sourced_summary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    identities = [
        row for row in rows if row.get("event_type") == "configuration_identity"
    ]
    if not identities:
        return None
    identity = identities[-1]
    run_id = str(identity.get("run_id") or "")
    scoped = [row for row in rows if str(row.get("run_id") or "") == run_id]
    decisions = _events(scoped, "regime_decision")
    fills = _events(scoped, "fill")
    reconciliation = _last_event(scoped, "reconciliation")
    position = _last_event(scoped, "position")
    state = _last_event(scoped, "state_transition")
    financials = _event_financials(scoped, fills)
    return {
        "run_id": run_id,
        "profile_id": identity.get("profile_id"),
        "network": identity.get("network"),
        "execution_sides": identity.get("execution_sides"),
        "regime_decisions": len(decisions),
        "entry_signals": {
            "long": sum(row.get("long_entry") is True for row in decisions),
            "short": sum(row.get("short_entry") is True for row in decisions),
        },
        "order_intents": _order_intent_counts(scoped),
        "order_acknowledgements": _acknowledgement_counts(scoped),
        "fills": dict(Counter(_fill_key(row) for row in fills)),
        "verified_target_closes": _verified_target_closes(scoped),
        **financials,
        "account_value_usd": reconciliation.get("account_value_usd"),
        "position_size_signed": position.get("size_signed"),
        "state": state.get("state"),
        "last_fault": state.get("last_fault"),
    }


def _events(rows: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("event_type") == event_type]


def _last_event(rows: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    matches = _events(rows, event_type)
    return matches[-1] if matches else {}


def _fill_key(row: dict[str, Any]) -> str:
    direction = str(row.get("direction") or "unknown").strip().lower()
    return direction.replace(" ", "_")


def _order_intent_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"entry": 0, "target": 0, "close": 0}
    for row in _events(rows, "order_intent"):
        operation = str(row.get("operation") or "")
        if operation in counts:
            counts[operation] += 1
    counts["close"] += sum(
        row.get("event_type") == "close" and row.get("intent") is True for row in rows
    )
    return counts


def _acknowledgement_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    acknowledgements = [row for row in rows if isinstance(row.get("accepted"), bool)]
    return {
        "accepted": sum(row.get("accepted") is True for row in acknowledgements),
        "rejected": sum(row.get("accepted") is False for row in acknowledgements),
    }


def _verified_target_closes(rows: list[dict[str, Any]]) -> int:
    return sum(
        row.get("event_type") == "close"
        and row.get("reason") == "target"
        and row.get("verified_flat") is True
        for row in rows
    )


def _event_financials(
    rows: list[dict[str, Any]],
    fills: list[dict[str, Any]],
) -> dict[str, float]:
    gross = _sum_numbers(fills, "closed_pnl_usd")
    fees = _sum_numbers(_events(rows, "fee"), "fee_usd")
    funding = _sum_numbers(_events(rows, "funding"), "usdc_delta")
    return {
        "gross_closed_pnl_usd": gross,
        "fees_usd": fees,
        "funding_usd": funding,
        "net_realized_usd": round(gross - fees + funding, 10),
    }


def _sum_numbers(rows: list[dict[str, Any]], key: str) -> float:
    values = [
        value for row in rows if isinstance((value := row.get(key)), (int, float))
    ]
    return round(sum(float(value) for value in values), 10)


def report_from_data_root(
    data_root: Path | str,
    *,
    decisions_path: Path | str | None = None,
    last_n: int = 5,
) -> dict[str, Any]:
    """Load live decisions path and summarize. Refuses paper/ paths."""
    root = Path(data_root)
    path = (
        Path(decisions_path)
        if decisions_path is not None
        else default_live_decisions_path(root)
    )
    paths = paths_for(root)
    paper_root = paths.paper_decisions.parent  # .../paper
    if _is_under(path, paper_root):
        raise ValueError(f"refusing live-report on path under paper/: {path}")
    parts = path.resolve().parts
    if "paper" in parts and "live" not in parts:
        raise ValueError(f"refusing live-report on paper path: {path}")

    rows = load_decision_rows(path)
    return summarize_live_decisions(rows, decisions_path=path, last_n=last_n)
