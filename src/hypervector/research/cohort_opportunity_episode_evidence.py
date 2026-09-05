"""Exact portfolio episode-onset attribution for route diagnostics."""

from __future__ import annotations

from collections.abc import Mapping

Record = Mapping[str, object]


def parse_episode_attributions(signal: Record) -> list[Record]:
    """Validate and return portfolio opportunity attribution rows."""
    raw = signal.get("portfolio_opportunity_dedup")
    if raw is None:
        return []
    portfolio = _mapping(raw, "portfolio opportunity dedup")
    rows = portfolio.get("by_attribution")
    if not isinstance(rows, list):
        raise ValueError("portfolio opportunity attributions must be an array")
    return [_mapping(row, "portfolio opportunity attribution") for row in rows]


def match_episode_capture(
    attributions: list[Record], route: str, blocker: str, horizon: str
) -> tuple[Record | None, int, int]:
    """Return a unique episode capture plus exact and ambiguous counts."""
    matches: list[Record] = []
    ambiguous = 0
    for row in attributions:
        onset, shared = _matching_episode(row, route, blocker, horizon)
        if shared:
            ambiguous += 1
        elif onset is not None:
            matches.append(onset)
    unique = matches[0] if len(matches) == 1 and not ambiguous else None
    return unique, len(matches), ambiguous


def episode_attribution_assessment(ambiguous: int, matches: int, fallback: str) -> str:
    """Censor shared-provider or side-separated episode attribution."""
    if ambiguous:
        return "portfolio_attribution_ambiguous"
    if matches > 1:
        return "side_separation_required"
    return fallback


def validated_blocker_episode_evidence(
    readiness: Record, expected: int
) -> dict[str, object]:
    """Validate poll-normalized readiness episodes or label legacy evidence."""
    raw = readiness.get("blocker_episode_combinations")
    if raw is None:
        return {
            "readiness_sampling_basis": "unavailable_legacy_audit",
            "blocker_episode_basis": "unavailable_legacy_audit",
            "blocker_episode_status": "unavailable_legacy_audit",
            "blocker_episode_combinations": [],
        }
    if not isinstance(raw, list):
        raise ValueError("blocker episode combinations must be an array")
    sampling = _required_text(readiness.get("readiness_sampling_basis"), "sampling")
    basis = _required_text(readiness.get("blocker_episode_basis"), "episode basis")
    if sampling != "backend_poll_evaluations":
        raise ValueError("readiness sampling basis is invalid")
    if basis != "maximal_consecutive_identical_blocker_sets":
        raise ValueError("blocker episode basis is invalid")
    rows = [_blocker_episode_row(value) for value in raw]
    if sum(int(row["evaluations"]) for row in rows) != expected:
        raise ValueError("blocker episode rows do not match readiness")
    return {
        "readiness_sampling_basis": sampling,
        "blocker_episode_basis": basis,
        "blocker_episode_status": "available",
        "blocker_episode_combinations": rows,
    }


def _blocker_episode_row(value: object) -> dict[str, object]:
    record = _mapping(value, "blocker episode combination")
    blockers = record.get("blockers")
    if not isinstance(blockers, list):
        raise ValueError("blocker episode blockers must be an array")
    normalized = [_required_text(item, "blocker episode blocker") for item in blockers]
    if normalized != sorted(set(normalized)):
        raise ValueError("blocker episode blockers must be sorted and unique")
    evaluations = _nonnegative_int(record.get("evaluations"), "evaluations")
    episodes = _nonnegative_int(record.get("episodes"), "episodes")
    if episodes < 1 or episodes > evaluations:
        raise ValueError("blocker episode counts are inconsistent")
    return {"blockers": normalized, "episodes": episodes, "evaluations": evaluations}


def _matching_episode(
    row: Record, route: str, blocker: str, horizon: str
) -> tuple[Record | None, bool]:
    symbol = _required_text(row.get("symbol"), "episode symbol")
    providers = row.get("providers")
    if not isinstance(providers, list):
        raise ValueError("episode providers must be an array")
    identities = [_episode_provider(provider, symbol) for provider in providers]
    if (route, blocker) not in identities:
        return None, False
    horizons = _mapping(row.get("horizons"), "episode horizons")
    raw = horizons.get(horizon)
    if raw is None:
        return None, False
    if len(identities) != 1:
        return None, True
    values = _mapping(raw, "episode horizon")
    return _mapping(values.get("episode_onsets"), "episode onsets"), False


def _episode_provider(value: object, symbol: str) -> tuple[str, str]:
    provider = _mapping(value, "episode provider")
    strategy = _required_text(provider.get("strategy_id"), "episode strategy")
    blocker = _required_text(provider.get("blocker"), "episode blocker")
    return f"{strategy}|{symbol}", blocker


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
    return value.strip()


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
