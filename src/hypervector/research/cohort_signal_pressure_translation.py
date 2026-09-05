"""Report-only provider-native to routing-publication pressure translation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

from hypervector.research.cohort_causal_book_context import (
    CausalBookSnapshot,
    latest_prior_book,
)
from hypervector.research.cohort_signal_candidates import SignalCandidate

BookIndex = Mapping[str, Sequence[CausalBookSnapshot]]
_STATES = ("retained", "flipped", "neutralized", "unavailable")
_LATEST_SIGNAL_LIMIT = 20


@dataclass
class _Coverage:
    eligible_signals: int = 0
    native_pressure_available: int = 0
    publication_book_matched: int = 0
    publication_book_stale: int = 0
    publication_book_missing: int = 0

    def as_payload(self) -> dict[str, int]:
        """Return exact causal coverage counters."""
        return {
            "eligible_signals": self.eligible_signals,
            "native_pressure_available": self.native_pressure_available,
            "publication_book_matched": self.publication_book_matched,
            "publication_book_stale": self.publication_book_stale,
            "publication_book_missing": self.publication_book_missing,
        }


def build_signal_pressure_translation(
    candidates: Sequence[SignalCandidate],
    books: BookIndex,
    maximum_book_age_ms: int,
) -> dict[str, object]:
    """Compare provider-native pressure with the causal publication-time book."""
    if (
        isinstance(maximum_book_age_ms, bool)
        or not isinstance(maximum_book_age_ms, int)
        or maximum_book_age_ms < 1
    ):
        raise ValueError("pressure translation maximum book age must be positive")
    coverage = _Coverage()
    grouped: dict[str, list[dict[str, object]]] = {}
    for candidate in candidates:
        if not candidate.eligible or candidate.side not in {"long", "short"}:
            continue
        row = _translation_row(candidate, books, maximum_book_age_ms, coverage)
        key = f"{candidate.strategy_id}|{candidate.symbol}"
        grouped.setdefault(key, []).append(row)
    return _report(grouped, coverage, maximum_book_age_ms)


def _translation_row(
    candidate: SignalCandidate,
    books: BookIndex,
    maximum_book_age_ms: int,
    coverage: _Coverage,
) -> dict[str, object]:
    coverage.eligible_signals += 1
    native = _native_directional_pressure(candidate)
    if native is not None:
        coverage.native_pressure_available += 1
    status, snapshot = latest_prior_book(
        books.get(candidate.symbol, ()),
        candidate.available_time_ms,
        maximum_book_age_ms,
    )
    setattr(
        coverage,
        f"publication_book_{status}",
        getattr(coverage, f"publication_book_{status}") + 1,
    )
    publication = _directional_opi(candidate, snapshot) if status == "matched" else None
    return _row_payload(candidate, native, publication, status, snapshot)


def _native_directional_pressure(candidate: SignalCandidate) -> float | None:
    value = candidate.metrics.get("imbalance_10")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("provider-native pressure must be numeric")
    pressure = float(value)
    if not isfinite(pressure) or not -1.0 <= pressure <= 1.0:
        raise ValueError("provider-native pressure must be within [-1, 1]")
    return pressure if candidate.side == "long" else -pressure


def _directional_opi(
    candidate: SignalCandidate,
    snapshot: CausalBookSnapshot | None,
) -> float | None:
    if snapshot is None:
        return None
    return snapshot.opi if candidate.side == "long" else -snapshot.opi


def _row_payload(
    candidate: SignalCandidate,
    native: float | None,
    publication: float | None,
    status: str,
    snapshot: CausalBookSnapshot | None,
) -> dict[str, object]:
    return {
        "decision_time_ms": candidate.decision_time_ms,
        "available_time_ms": candidate.available_time_ms,
        "source_run_id": candidate.source_run_id,
        "side": candidate.side,
        "native_directional_pressure": native,
        "publication_directional_opi": publication,
        "publication_book_status": status,
        "publication_book_time_ms": None if snapshot is None else snapshot.recv_ts_ms,
        "publication_book_age_ms": (
            None
            if snapshot is None
            else candidate.available_time_ms - snapshot.recv_ts_ms
        ),
        "translation_state": _translation_state(native, publication),
    }


def _translation_state(native: float | None, publication: float | None) -> str:
    if native is None or publication is None:
        return "unavailable"
    if native == 0.0 or publication == 0.0:
        return "neutralized"
    return "retained" if native * publication > 0.0 else "flipped"


def _report(
    grouped: Mapping[str, Sequence[Mapping[str, object]]],
    coverage: _Coverage,
    maximum_book_age_ms: int,
) -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "entry_eligibility_changed": False,
            "provider_native_source": "readiness.metrics.imbalance_10",
            "publication_source": "latest_nonfuture_asset_book_at_routing_publication",
        },
        "maximum_book_age_ms": maximum_book_age_ms,
        "coverage": coverage.as_payload(),
        "by_provider_symbol": {
            key: _provider_payload(rows) for key, rows in sorted(grouped.items())
        },
        "limitations": [
            "publication pressure is context rather than a fitted entry gate",
            "a retained sign does not establish future return expectancy",
            "routing-publication context is not the eventual venue fill book",
            "the diagnostic cannot route, size, close, or mutate a position",
        ],
    }


def _provider_payload(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    ordered = sorted(rows, key=lambda row: int(row["available_time_ms"]))
    return {
        "signals": [dict(row) for row in ordered[-_LATEST_SIGNAL_LIMIT:]],
        "translation_state": {
            state: sum(row["translation_state"] == state for row in ordered)
            for state in _STATES
        },
    }
