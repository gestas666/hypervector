"""Validation and loading for checkpoint opportunity-matrix evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path


def load_opportunity_matrix(path: Path) -> Mapping[str, object]:
    """Load one source-bound report-only opportunity matrix."""
    if not path.is_file():
        raise FileNotFoundError(f"opportunity matrix does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("opportunity matrix must be a JSON object")
    return value


def load_supplemental_opportunity_matrix(path: Path) -> Mapping[str, object]:
    """Load one supplemental matrix with a source-specific error."""
    try:
        return load_opportunity_matrix(path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"supplemental opportunity matrix does not exist: {path}"
        ) from exc


def merge_opportunity_matrices(
    primary: Mapping[str, object] | None,
    supplemental: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Validate and combine one primary matrix with report-only challengers."""
    if primary is None:
        raise ValueError("supplemental opportunity matrices require a primary matrix")
    matrix = _validated_opportunity_matrix(primary)
    identities: set[str] = set()
    primary_challenger = matrix.get("forward_challenger")
    if primary_challenger is not None:
        _, identity = _validated_forward_challenger(primary_challenger)
        identities.add(identity)
    challengers: list[dict[str, object]] = []
    for value in supplemental:
        candidate_matrix = _validated_opportunity_matrix(value)
        challenger, identity = _validated_forward_challenger(
            candidate_matrix.get("forward_challenger")
        )
        if identity in identities:
            raise ValueError(f"duplicate candidate strategy identity: {identity}")
        identities.add(identity)
        challengers.append(challenger)
    if challengers:
        matrix["supplemental_forward_challengers"] = challengers
    return matrix


def _validated_forward_challenger(value: object) -> tuple[dict[str, object], str]:
    challenger = dict(_mapping(value, "forward opportunity challenger"))
    contract = _mapping(challenger.get("contract"), "forward challenger contract")
    if contract.get("report_only") is not True:
        raise ValueError("forward challenger must be report-only")
    if contract.get("execution_authority") != "none":
        raise ValueError("forward challenger execution authority must be none")
    if contract.get("live_strategy_changed") is not False:
        raise ValueError("forward challenger must not change the live strategy")
    if contract.get("automatic_promotion") is not False:
        raise ValueError("forward challenger must not promote automatically")
    if contract.get("portfolio_pnl_claimed") is not False:
        raise ValueError("forward challenger must not claim portfolio PnL")
    journal = _mapping(challenger.get("portfolio_journal"), "portfolio journal")
    journal_contract = _mapping(journal.get("contract"), "portfolio journal contract")
    if journal_contract.get("report_only") is not True:
        raise ValueError("portfolio journal must be report-only")
    if journal_contract.get("execution_authority") != "none":
        raise ValueError("portfolio journal execution authority must be none")
    if journal_contract.get("portfolio_pnl_claimed") is not False:
        raise ValueError("portfolio journal must not claim portfolio PnL")
    identity = _text(
        journal_contract.get("candidate_strategy_id"),
        "candidate strategy identity",
    )
    return challenger, identity


def _validated_opportunity_matrix(value: Mapping[str, object]) -> dict[str, object]:
    matrix = dict(value)
    if matrix.get("schema_version") != 1:
        raise ValueError("opportunity matrix has an unsupported schema")
    if matrix.get("mode") != "cohort_execution_opportunity_matrix":
        raise ValueError("opportunity matrix has an unexpected mode")
    contract = _mapping(matrix.get("contract"), "opportunity matrix contract")
    if contract.get("report_only") is not True:
        raise ValueError("opportunity matrix must be report-only")
    if contract.get("execution_authority") != "none":
        raise ValueError("opportunity matrix execution authority must be none")
    if contract.get("portfolio_pnl_claimed") is not False:
        raise ValueError("opportunity matrix must not claim portfolio PnL")
    comparisons = matrix.get("comparisons")
    results = matrix.get("results")
    if isinstance(comparisons, bool) or not isinstance(comparisons, int):
        raise ValueError("opportunity matrix comparisons must be an integer")
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError("opportunity matrix results must be a sequence")
    if len(results) != comparisons:
        raise ValueError("opportunity matrix result count is inconsistent")
    return matrix


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
