"""Checksum-bound supplemental repair for prospective HIP-3 path gaps."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import cast

from hypervector.data.oxa_api import validate_market_symbol
from hypervector.research.hip3_prospective_path_audit import hip3_bar_path_quality

_ARCHIVE_SOURCE = "0xarchive_exact_exchange_history"


@dataclass(frozen=True)
class Hip3ProspectivePathRepairConfig:
    """Exact supplemental archive bounds and frozen path-gap tolerances."""

    symbol: str
    start_ms: int
    end_ms: int
    maximum_mark_gap_ms: int = 5_000
    maximum_l2_gap_ms: int = 15_000

    def __post_init__(self) -> None:
        """Reject invalid identity, time bounds, and technical thresholds."""
        validate_market_symbol(self.symbol, "hip3")
        for name, value in (
            ("start_ms", self.start_ms),
            ("end_ms", self.end_ms),
            ("maximum_mark_gap_ms", self.maximum_mark_gap_ms),
            ("maximum_l2_gap_ms", self.maximum_l2_gap_ms),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.start_ms >= self.end_ms:
            raise ValueError("path repair requires start_ms < end_ms")


def build_hip3_prospective_path_repair(
    *,
    base_audit: Mapping[str, object],
    mark_timestamps_ms: Sequence[int],
    l2_timestamps_ms: Sequence[int],
    archive_evidence: Mapping[str, object],
    config: Hip3ProspectivePathRepairConfig,
) -> dict[str, object]:
    """Repair only unresolved bars using independently verified archive paths."""
    base = _validated_base(base_audit, config)
    evidence = _validated_archive_evidence(archive_evidence, config.symbol)
    marks = _validated_timestamps(mark_timestamps_ms, config, "mark")
    books = _validated_timestamps(l2_timestamps_ms, config, "L2")
    rows, repaired = _repaired_rows(base, marks, books, config)
    unresolved = sum(not bool(row["resolved"]) for row in rows)
    original = _original_unresolved(base)
    report = deepcopy(base)
    report["mode"] = "prospective_public_venue_path_coverage_with_archive_repair"
    report["bar_diagnostics"] = rows
    report["effective_channels"] = _effective_channels(rows)
    report["technical_assessment"] = _assessment(original, repaired, unresolved)
    _attach_source(report, config)
    _attach_identity(report, marks, books, evidence)
    report["limitations"] = _limitations()
    return report


def _validated_base(
    base: Mapping[str, object], config: Hip3ProspectivePathRepairConfig
) -> dict[str, object]:
    if base.get("schema_version") != "hip3_prospective_path_audit_v1":
        raise ValueError("base path audit schema is invalid")
    contract = _mapping(base, "contract")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("base path audit authority is invalid")
    if _mapping(base, "source").get("symbol") != config.symbol:
        raise ValueError("base path audit symbol is inconsistent")
    coverage = _mapping(base, "coverage")
    rows = _rows(base)
    if _integer(coverage, "completed_bars") != len(rows):
        raise ValueError("base path audit completed bar count is inconsistent")
    reported = _integer(_mapping(base, "technical_assessment"), "unresolved_bars")
    observed = sum(not bool(row.get("resolved")) for row in rows)
    if reported != observed:
        raise ValueError("base path audit unresolved count is inconsistent")
    return deepcopy(dict(base))


def _validated_archive_evidence(
    value: Mapping[str, object], symbol: str
) -> dict[str, object]:
    if value.get("complete") is not True:
        raise ValueError("supplemental archive must be checksum complete")
    if value.get("market_family") != "hip3":
        raise ValueError("supplemental archive market family is invalid")
    if value.get("symbol") != symbol:
        raise ValueError("supplemental archive symbol is inconsistent")
    return deepcopy(dict(value))


def _validated_timestamps(
    values: Sequence[int], config: Hip3ProspectivePathRepairConfig, channel: str
) -> tuple[int, ...]:
    timestamps = tuple(values)
    if any(
        isinstance(value, bool) or not isinstance(value, int) for value in timestamps
    ):
        raise ValueError(f"supplemental {channel} timestamps must be integers")
    if len(set(timestamps)) != len(timestamps):
        raise ValueError(f"supplemental {channel} timestamps must be unique")
    if any(value < config.start_ms or value >= config.end_ms for value in timestamps):
        raise ValueError(f"supplemental {channel} timestamp is outside repair bounds")
    return tuple(sorted(timestamps))


def _repaired_rows(
    base: Mapping[str, object],
    marks: tuple[int, ...],
    books: tuple[int, ...],
    config: Hip3ProspectivePathRepairConfig,
) -> tuple[list[dict[str, object]], int]:
    output: list[dict[str, object]] = []
    repaired = 0
    for original in _rows(base):
        if original.get("resolved") is True:
            output.append({**deepcopy(original), "path_source": "live_prospective"})
            continue
        row = _repair_row(original, marks, books, config)
        repaired += int(row["resolved"] is True)
        output.append(row)
    return output, repaired


def _repair_row(
    original: Mapping[str, object],
    marks: tuple[int, ...],
    books: tuple[int, ...],
    config: Hip3ProspectivePathRepairConfig,
) -> dict[str, object]:
    start = _integer(original, "bar_open_ms")
    end = _integer(original, "bar_close_ms")
    mark = hip3_bar_path_quality(
        marks, start_ms=start, end_ms=end, maximum_gap_ms=config.maximum_mark_gap_ms
    )
    l2 = hip3_bar_path_quality(
        books, start_ms=start, end_ms=end, maximum_gap_ms=config.maximum_l2_gap_ms
    )
    resolved = bool(mark["complete"]) and bool(l2["complete"])
    return {
        "bar_open_ms": start,
        "bar_close_ms": end,
        "mark": mark,
        "l2": l2,
        "resolved": resolved,
        "path_source": _ARCHIVE_SOURCE if resolved else "unresolved",
        "original": deepcopy(dict(original)),
    }


def _effective_channels(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {
        channel: {
            "complete_bars": sum(
                bool(_mapping(row, channel).get("complete")) for row in rows
            ),
            "incomplete_bars": sum(
                not bool(_mapping(row, channel).get("complete")) for row in rows
            ),
        }
        for channel in ("mark", "l2")
    }


def _assessment(original: int, repaired: int, unresolved: int) -> dict[str, object]:
    return {
        "prospective_bar_path_coverage_resolved": bool(original) and unresolved == 0,
        "unresolved_bars": unresolved,
        "original_unresolved_bars": original,
        "repaired_bars": repaired,
        "candle_ohlc_parity_resolved": False,
    }


def _attach_source(
    report: dict[str, object], config: Hip3ProspectivePathRepairConfig
) -> None:
    source = cast(dict[str, object], _mapping(report, "source"))
    source["path_repair"] = {
        "source": _ARCHIVE_SOURCE,
        "start_ms": config.start_ms,
        "end_ms": config.end_ms,
        "maximum_mark_gap_ms": config.maximum_mark_gap_ms,
        "maximum_l2_gap_ms": config.maximum_l2_gap_ms,
    }


def _attach_identity(
    report: dict[str, object],
    marks: tuple[int, ...],
    books: tuple[int, ...],
    evidence: Mapping[str, object],
) -> None:
    identity = cast(dict[str, object], _mapping(report, "evidence_identity"))
    payload = {
        "archive": evidence,
        "mark": _timestamp_identity(marks),
        "l2": _timestamp_identity(books),
    }
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    identity["supplemental_path_repair"] = payload | {
        "material_state_sha256": hashlib.sha256(material.encode()).hexdigest()
    }


def _timestamp_identity(values: Sequence[int]) -> dict[str, object]:
    payload = "\n".join(str(value) for value in values).encode()
    return {"rows": len(values), "sha256": hashlib.sha256(payload).hexdigest()}


def _original_unresolved(base: Mapping[str, object]) -> int:
    return _integer(_mapping(base, "technical_assessment"), "unresolved_bars")


def _rows(value: Mapping[str, object]) -> list[dict[str, object]]:
    rows = value.get("bar_diagnostics")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("base path audit bar diagnostics are invalid")
    return cast(list[dict[str, object]], rows)


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    selected = value.get(key)
    if not isinstance(selected, dict):
        raise ValueError(f"path repair evidence missing object {key}")
    return cast(dict[str, object], selected)


def _integer(value: Mapping[str, object], key: str) -> int:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise ValueError(f"path repair evidence {key} must be an integer")
    return selected


def _limitations() -> list[str]:
    return [
        "supplemental exchange history repairs only explicitly unresolved bars",
        "path coverage does not establish profitability or promotion authority",
        "public-trade OHLC versus live candleSnapshot parity remains separate",
    ]
