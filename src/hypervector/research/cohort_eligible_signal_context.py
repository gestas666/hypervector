"""Report-only causal pressure and regime annotations for eligible signals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_causal_book_context import (
    CausalBookSnapshot,
    latest_prior_book,
)
from hypervector.research.cohort_eligible_signal_markouts import (
    AnnotatedSignal,
    build_executable_bbo_markouts,
)
from hypervector.research.cohort_forward_paths import validated_horizons
from hypervector.research.cohort_signal_candidates import SignalCandidate

BookIndex = Mapping[str, Sequence[CausalBookSnapshot]]
_LATEST_SIGNAL_LIMIT = 20
_DEFAULT_HORIZONS = (5, 15, 30, 60)
_REGIME_STATES = {"BREAKOUT", "RANGE", "TRANSITION", "TREND_DOWN", "TREND_UP"}
_STANCES = ("aligned", "neutral", "opposed", "unavailable")


@dataclass
class _Coverage:
    eligible_signals: int = 0
    book_matched: int = 0
    book_stale: int = 0
    book_missing: int = 0

    def as_payload(self) -> dict[str, int]:
        return {
            "eligible_signals": self.eligible_signals,
            "book_matched": self.book_matched,
            "book_stale": self.book_stale,
            "book_missing": self.book_missing,
        }


def build_eligible_signal_context(
    candidates: Sequence[SignalCandidate],
    books: BookIndex,
    maximum_book_age_ms: int,
    *,
    horizons_minutes: Sequence[int] = _DEFAULT_HORIZONS,
    provider_cadence_minutes: Mapping[str, int] | None = None,
) -> dict[str, object]:
    """Annotate eligible signals without claiming that they routed or filled."""
    horizons = validated_horizons(horizons_minutes)
    grouped: dict[str, list[dict[str, object]]] = {}
    annotated: list[AnnotatedSignal] = []
    coverage = _Coverage()
    for candidate in candidates:
        if not candidate.eligible or candidate.side not in {"long", "short"}:
            continue
        coverage.eligible_signals += 1
        status, row = _signal_annotation(candidate, books, maximum_book_age_ms)
        setattr(coverage, f"book_{status}", getattr(coverage, f"book_{status}") + 1)
        key = f"{candidate.strategy_id}|{candidate.symbol}"
        grouped.setdefault(key, []).append(row)
        annotated.append((candidate, row))
    markouts = build_executable_bbo_markouts(
        annotated,
        books,
        horizons_minutes=horizons,
        maximum_book_lateness_ms=maximum_book_age_ms,
        provider_cadence_minutes=provider_cadence_minutes,
    )
    return {
        "contract": _contract(),
        "maximum_book_age_ms": maximum_book_age_ms,
        "coverage": coverage.as_payload(),
        "by_provider_symbol": {
            key: _provider_summary(rows, markouts[key])
            for key, rows in sorted(grouped.items())
        },
        "limitations": _limitations(),
    }


def _signal_annotation(
    candidate: SignalCandidate,
    books: BookIndex,
    maximum_book_age_ms: int,
) -> tuple[str, dict[str, object]]:
    status, snapshot = latest_prior_book(
        books.get(candidate.symbol, ()),
        candidate.available_time_ms,
        maximum_book_age_ms,
    )
    row = _base_annotation(candidate)
    if status != "matched" or snapshot is None:
        row["pressure_stance"] = "unavailable"
        row["book_status"] = status
        return status, row
    direction = 1.0 if candidate.side == "long" else -1.0
    directional_opi = direction * snapshot.opi
    row.update(
        {
            "book_time_ms": snapshot.recv_ts_ms,
            "book_age_ms": candidate.available_time_ms - snapshot.recv_ts_ms,
            "directional_opi": directional_opi,
            "spread_bps": snapshot.spread_bps,
            "pressure_stance": _pressure_stance(directional_opi),
        }
    )
    return status, row


def _base_annotation(candidate: SignalCandidate) -> dict[str, object]:
    if candidate.side not in {"long", "short"}:
        raise ValueError("eligible signal context requires a direction")
    state_5m = _regime_state(candidate, "state_5m")
    context_15m = _regime_state(candidate, "context_15m")
    return {
        "decision_time_ms": candidate.decision_time_ms,
        "available_time_ms": candidate.available_time_ms,
        "side": candidate.side,
        "state_5m": state_5m,
        "state_5m_stance": _regime_stance(candidate.side, state_5m),
        "context_15m": context_15m,
        "context_15m_stance": _regime_stance(candidate.side, context_15m),
    }


def _regime_state(candidate: SignalCandidate, name: str) -> str | None:
    value = candidate.metrics.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or value not in _REGIME_STATES:
        raise ValueError(f"eligible signal {name} is invalid")
    return value


def _regime_stance(side: str, state: str | None) -> str:
    if state is None:
        return "unavailable"
    if (side, state) in {("long", "TREND_UP"), ("short", "TREND_DOWN")}:
        return "aligned"
    if (side, state) in {("long", "TREND_DOWN"), ("short", "TREND_UP")}:
        return "opposed"
    return "neutral"


def _pressure_stance(directional_opi: float) -> str:
    if directional_opi > 0.0:
        return "aligned"
    if directional_opi < 0.0:
        return "opposed"
    return "neutral"


def _provider_summary(
    rows: Sequence[Mapping[str, object]], markouts: Mapping[str, object]
) -> dict[str, object]:
    ordered = sorted(rows, key=lambda row: int(row["available_time_ms"]))
    return {
        "eligible_signals": len(ordered),
        "pressure_stance": _stance_counts(ordered, "pressure_stance"),
        "state_5m_stance": _stance_counts(ordered, "state_5m_stance"),
        "context_15m_stance": _stance_counts(ordered, "context_15m_stance"),
        "latest_signals": [dict(row) for row in ordered[-_LATEST_SIGNAL_LIMIT:]],
        "executable_bbo_markouts": dict(markouts),
    }


def _stance_counts(rows: Sequence[Mapping[str, object]], name: str) -> dict[str, int]:
    return {stance: sum(row.get(name) == stance for row in rows) for stance in _STANCES}


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "signals_are_annotations": True,
        "routing_or_fill_claimed": False,
        "thresholds_selected": False,
        "signal_eligibility_changed": False,
    }


def _limitations() -> list[str]:
    return [
        "eligible signals are provider decisions, not routed entries or fills",
        "L2 pressure is the latest causal snapshot and does not prove queue position",
        "BBO markouts are sampled executable quotes and do not claim fills or PnL",
        "fixed-horizon markouts exclude funding and provider exit behavior",
        "modeled residual slippage is cited research rather than a future fill fact",
        "episode onsets require uninterrupted configured provider cadence and side",
        "missing regime context remains unavailable rather than inferred",
        "no pressure or regime threshold is selected by this annotation",
        "the report cannot gate, route, size, close, or mutate a live position",
    ]
