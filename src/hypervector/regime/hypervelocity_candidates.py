"""Deterministic regime candidates for Hypervelocity archive comparison."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from itertools import combinations

from hypervector.regime.classifier import RegimeClassifierConfig
from hypervector.strategies.hypervelocity_contract import faithful_regime_config

_GROUPS = ("ema", "range_filter", "clearance", "volume")


@dataclass(frozen=True)
class HypervelocityRegimeCandidate:
    """One exact, fingerprinted regime configuration."""

    candidate_id: str
    changed_groups: tuple[str, ...]
    config: RegimeClassifierConfig
    fingerprint: str

    def recomputed_fingerprint(self) -> str:
        """Return the deterministic SHA-256 of the complete configuration."""
        payload = json.dumps(asdict(self.config), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe candidate identity and exact parameters."""
        return {
            "candidate_id": self.candidate_id,
            "changed_groups": list(self.changed_groups),
            "fingerprint": self.fingerprint,
            "parameters": asdict(self.config),
        }


def _baseline_config() -> RegimeClassifierConfig:
    return RegimeClassifierConfig(
        ema_fast=20,
        ema_slow=50,
        warmup_bars=60,
        structure_lookback=240,
        trend_strength_percentile=50.0,
        range_strength_percentile=40.0,
        minimum_trend_gap_bps=1.0,
        range_filter="choppiness",
        choppiness_length=14,
        choppiness_range_threshold=85.0,
        bbwp_length=20,
        bbwp_lookback=240,
        bbwp_compression_threshold=25.0,
        rsi_length=14,
        rsi_signal_length=7,
        coiling_width_bps=3.0,
        breakout_lookback=90,
        breakout_clearance_bps=5.0,
        breakout_volume_lookback=20,
        breakout_volume_multiple=2.0,
    )


def _apply_groups(
    baseline: RegimeClassifierConfig,
    groups: tuple[str, ...],
) -> RegimeClassifierConfig:
    updates: dict[str, object] = {}
    if "ema" in groups:
        updates.update(ema_fast=21, ema_slow=55)
    if "range_filter" in groups:
        updates.update(range_filter="bbwp")
    if "clearance" in groups:
        updates.update(breakout_clearance_bps=8.0)
    if "volume" in groups:
        updates.update(breakout_volume_multiple=2.5)
    return replace(baseline, **updates)


def _candidate_id(groups: tuple[str, ...]) -> str:
    if not groups:
        return "pareto60_baseline"
    if len(groups) == len(_GROUPS):
        return "bbwp_blueprint_full"
    prefix = "single" if len(groups) == 1 else "pair"
    return f"{prefix}_{'_'.join(groups)}"


def _candidate(
    baseline: RegimeClassifierConfig,
    groups: tuple[str, ...],
) -> HypervelocityRegimeCandidate:
    config = _apply_groups(baseline, groups)
    provisional = HypervelocityRegimeCandidate(
        _candidate_id(groups), groups, config, ""
    )
    return replace(provisional, fingerprint=provisional.recomputed_fingerprint())


def hypervelocity_candidate_matrix() -> tuple[HypervelocityRegimeCandidate, ...]:
    """Return baseline, all one/two-group changes, and the full BBWP blueprint."""
    baseline = _baseline_config()
    group_sets = (
        (),
        *((group,) for group in _GROUPS),
        *combinations(_GROUPS, 2),
        _GROUPS,
    )
    candidates = tuple(_candidate(baseline, groups) for groups in group_sets)
    if candidates[-1].config != faithful_regime_config():
        raise RuntimeError(
            "full candidate diverges from faithful runtime configuration"
        )
    return candidates
