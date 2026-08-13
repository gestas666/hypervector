"""Report-only side-authority variants for exact v39 HT breakout onsets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math

from hypervector.research.v39_forward_evidence_contract import PROFILE_FINGERPRINT

Record = Mapping[str, object]
_STRATEGY_ID = "hype_breakout_onset_bidirectional_v1"
_SYMBOLS = frozenset({"BTC", "ETH", "SOL"})


def build_v39_ht_side_authority_challenger(
    evaluations: Sequence[Record],
    *,
    run_id: str,
    profile_fingerprint: str,
) -> dict[str, object]:
    """Freeze three causal side variants without constructing trade intents."""
    _require_identity(run_id, profile_fingerprint)
    source = tuple(row for row in evaluations if row.get("strategy_id") == _STRATEGY_ID)
    eligible = tuple(
        _eligible_onset(row) for row in source if row.get("eligible") is True
    )
    decisions = tuple(sorted(eligible, key=_decision_key))
    _require_unique(decisions)
    return {
        "schema_version": "v39_ht_side_authority_challenger_v1",
        "mode": "pre_registered_report_only_side_variants",
        "contract": _contract(),
        "source": {
            "run_id": run_id,
            "profile_fingerprint": profile_fingerprint,
            "strategy_id": _STRATEGY_ID,
            "evaluations": len(source),
        },
        "variant_definitions": _variant_definitions(),
        "source_evaluations_sha256": _source_digest(source),
        "summary": _summary(decisions),
        "decisions": list(decisions),
        "limitations": _limitations(),
    }


def _eligible_onset(row: Record) -> dict[str, object]:
    symbol = _text(row.get("symbol"), "HT symbol")
    if symbol not in _SYMBOLS:
        raise ValueError(f"exact v39 HT symbol is unsupported: {symbol}")
    decision_time = _integer(row.get("decision_time_ms"), "HT decision time")
    reference = _number(row.get("reference_price"), "HT reference price")
    readiness = _mapping(row.get("readiness"), "HT readiness")
    metrics = _mapping(readiness.get("metrics"), "HT readiness metrics")
    if metrics.get("breakout_onset") is not True:
        raise ValueError("eligible v39 HT evaluation must be a breakout onset")
    structural = _side(metrics.get("structural_direction"), "structural side")
    source_side = _side(row.get("side"), "source side")
    if source_side != structural:
        raise ValueError("v39 HT source side must match structural direction")
    breakout = _optional_side(metrics.get("breakout_side"), "breakout side")
    relation = _relation(metrics.get("breakout_side_relation"), structural, breakout)
    return {
        "symbol": symbol,
        "decision_time_ms": decision_time,
        "reference_price": reference,
        "source_side": source_side,
        "structural_side": structural,
        "breakout_side": breakout,
        "breakout_side_relation": relation,
        "variants": _variants(structural, breakout),
    }


def _variants(structural: str, breakout: str | None) -> dict[str, object]:
    agreement = structural if structural == breakout else None
    return {
        "structural_side": _action(structural),
        "breakout_side": _action(breakout),
        "agree_only": _action(agreement),
    }


def _action(side: str | None) -> dict[str, object]:
    return {"action": f"enter_{side}" if side else "no_trade", "side": side}


def _summary(decisions: Sequence[Record]) -> dict[str, int]:
    relations = tuple(str(row["breakout_side_relation"]) for row in decisions)
    breakout_entries = sum(
        row.get("breakout_side") in {"long", "short"} for row in decisions
    )
    agree = relations.count("aligned")
    return {
        "eligible_onsets": len(decisions),
        "aligned_onsets": agree,
        "opposed_onsets": relations.count("opposed"),
        "unavailable_onsets": relations.count("unavailable"),
        "structural_variant_entries": len(decisions),
        "breakout_variant_entries": breakout_entries,
        "agree_only_variant_entries": agree,
        "agree_only_no_trades": len(decisions) - agree,
    }


def _variant_definitions() -> dict[str, object]:
    return {
        "structural_side": "current_provider_structural_sma_side",
        "breakout_side": "same_decision_completed_5m_breakout_side",
        "agree_only": "enter_only_when_structural_and_breakout_sides_match",
        "shared_contract": (
            "same_decision_time_reference_quote_stop_hold_fees_funding_and_exit_model"
        ),
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "entry_authority": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "performance_gate": False,
    }


def _limitations() -> list[str]:
    return [
        "decision variants are not counterfactual fills or performance estimates",
        "later outcomes require identical friction and lifecycle replay",
        "overlapping decisions require transitive episode attribution",
        "no fixed sample count or metric automatically grants execution authority",
    ]


def _source_digest(rows: Sequence[Record]) -> str:
    payload = json.dumps(list(rows), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _relation(value: object, structural: str, breakout: str | None) -> str:
    expected = (
        "unavailable"
        if breakout is None
        else "aligned"
        if breakout == structural
        else "opposed"
    )
    relation = _text(value, "breakout side relation")
    if relation != expected:
        raise ValueError("v39 HT breakout-side relation is internally inconsistent")
    return relation


def _require_identity(run_id: str, profile_fingerprint: str) -> None:
    if not run_id.strip():
        raise ValueError("v39 HT challenger run_id must be non-empty")
    if profile_fingerprint != PROFILE_FINGERPRINT:
        raise ValueError("v39 HT challenger profile fingerprint mismatch")


def _require_unique(rows: Sequence[Record]) -> None:
    keys = tuple(_decision_key(row) for row in rows)
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate exact v39 HT symbol-decision identity")


def _decision_key(row: Record) -> tuple[int, str]:
    return int(row["decision_time_ms"]), str(row["symbol"])


def _optional_side(value: object, label: str) -> str | None:
    return None if value is None else _side(value, label)


def _side(value: object, label: str) -> str:
    text = _text(value, label)
    if text not in {"long", "short"}:
        raise ValueError(f"{label} must be long or short")
    return text


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return number
