"""Screen finite creator BTC Recipe B/C interpretations without runtime authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.regime.classifier import classify_timeframe
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.hypervelocity_replay_evidence import decision_identity
from hypervector.research.hypervelocity_selective_recipe import (
    SELECTIVE_RECIPE_CANDIDATES,
    align_creator_recipe_entries,
    build_selective_recipe_events,
    load_selective_recipe_bars as _merged_bars,
    summarize_selective_recipe_alignment,
)
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile

_FAITHFUL_CONFIG_SHA256 = (
    "801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f"
)
_EXPECTED_AUDIT = {
    "complete": True,
    "expected_bundles": 48,
    "present_bundles": 48,
    "empty_book_windows": 0,
    "empty_trade_windows": 0,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--supplemental-bars", type=Path, required=True)
    parser.add_argument("--source-rows", type=Path, required=True)
    parser.add_argument("--live-rows", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--archive-audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _experiment_contract(_: argparse.Namespace) -> dict[str, object]:
    return {
        "report_only": True,
        "runtime_strategy_changed": False,
        "candidate_order": list(SELECTIVE_RECIPE_CANDIDATES),
        "session_windows_utc": {
            "bk_up_asia_conf06": "00:00-08:00",
            "fade_td_eu": "07:00-16:00",
        },
        "creator_confidence_threshold_descriptive_only": 0.6,
        "maker_ttl_seconds": 300.0,
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "recipe_b_max_hold_hours": 4.0,
        "recipe_c_max_hold_hours": 24.0,
        "stop_policy": "none",
        "model_authority": {
            "mode": "observe",
            "may_filter": False,
            "may_scale": False,
        },
    }


def _source_rows(path: Path, *, displayed_as_utc: bool) -> pd.DataFrame:
    """Load creator recipe rows under one explicit screenshot-time assumption."""
    if not path.is_file():
        raise FileNotFoundError(f"selective-recipe source rows are missing: {path}")
    frame = pd.read_csv(path)
    required = {
        "evidence_id",
        "recipe_id",
        "side",
        "entry_time_displayed",
        "entry_time_utc_inferred",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"selective-recipe source rows missing: {sorted(missing)}")
    if displayed_as_utc:
        timestamp = pd.to_datetime(
            frame["entry_time_displayed"], format="%Y-%m-%d %I:%M %p", utc=True
        )
    else:
        timestamp = pd.to_datetime(
            frame["entry_time_utc_inferred"], format="ISO8601", utc=True
        )
    selected = pd.DataFrame(
        {
            "source_id": frame["evidence_id"].astype(str),
            "recipe_id": frame["recipe_id"].astype(str),
            "side": frame["side"].astype(str),
            "entry_time_utc_inferred": timestamp,
        }
    )
    return selected.sort_values("entry_time_utc_inferred", kind="stable").reset_index(
        drop=True
    )


def _live_rows(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"selective-recipe live rows are missing: {path}")
    frame = pd.read_csv(path)
    required = {
        "evidence_id",
        "side",
        "open_time_utc_inferred",
        "entry_price",
        "exit_price",
        "margin_pnl_pct",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"selective-recipe live rows missing: {sorted(missing)}")
    frame["open_time_utc_inferred"] = pd.to_datetime(
        frame["open_time_utc_inferred"], format="ISO8601", utc=True
    )
    return frame.sort_values("open_time_utc_inferred", kind="stable").reset_index(
        drop=True
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verified_audit(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"selective-recipe archive audit is missing: {path}")
    payload = json.loads(path.read_text())
    mismatches = {
        key: (payload.get(key), expected)
        for key, expected in _EXPECTED_AUDIT.items()
        if payload.get(key) != expected
    }
    if mismatches:
        raise ValueError(f"selective-recipe archive audit is incomplete: {mismatches}")
    return {**payload, "sha256": _file_sha256(path)}


def _verified_config(path: Path) -> dict[str, object]:
    evidence = file_evidence(path)
    if evidence["sha256"] != _FAITHFUL_CONFIG_SHA256:
        raise ValueError("faithful config checksum mismatch")
    return evidence


def _json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    payload = frame.to_json(orient="records", date_format="iso")
    records = json.loads(payload)
    if not isinstance(records, list):
        raise RuntimeError("selective-recipe JSON record conversion failed")
    return records


def _event_diagnostics(events: pd.DataFrame) -> dict[str, dict[str, object]]:
    diagnostics: dict[str, dict[str, object]] = {}
    for candidate_id in SELECTIVE_RECIPE_CANDIDATES:
        selected = events.loc[events["candidate_id"].eq(candidate_id)].copy()
        days = pd.DatetimeIndex(selected["event_time_utc"]).normalize()
        counts = pd.Series(days).value_counts().sort_index()
        diagnostics[candidate_id] = {
            "total_events": len(selected),
            "current_confidence_ge_06": int(
                selected["passes_current_confidence_06"].sum()
            ),
            "active_days": int(len(counts)),
            "median_events_per_active_day": (
                0.0 if counts.empty else float(counts.median())
            ),
            "maximum_events_per_active_day": (0 if counts.empty else int(counts.max())),
        }
    return diagnostics


def _alignment_payload(
    source: pd.DataFrame,
    events: pd.DataFrame,
) -> dict[str, object]:
    alignment = align_creator_recipe_entries(source, events)
    return {
        "summary": summarize_selective_recipe_alignment(source, events, alignment),
        "rows": _json_records(alignment),
    }


def _live_market_context(
    live: pd.DataFrame,
    decisions: pd.DataFrame,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for _, source in live.iterrows():
        entry_time = pd.Timestamp(source["open_time_utc_inferred"])
        available_bar = entry_time.floor("min") - pd.Timedelta(minutes=1)
        position = decisions.index.get_indexer([available_bar], method="pad")[0]
        if position < 0:
            raise ValueError(f"no causal regime context before live row {entry_time}")
        decision_time = decisions.index[position]
        decision = decisions.iloc[position]
        rows.append(
            {
                "source_id": str(source["evidence_id"]),
                "entry_time_utc_inferred": entry_time,
                "decision_bar_utc": decision_time,
                "side": str(source["side"]),
                "entry_price": float(source["entry_price"]),
                "exit_price": float(source["exit_price"]),
                "margin_pnl_pct": float(source["margin_pnl_pct"]),
                "primary_regime": str(decision["primary_regime"]),
                "state_1m": str(decision["state_1m"]),
                "state_5m": str(decision["state_5m"]),
                "context_15m": str(decision["context_15m"]),
                "structural_direction": decision["structural_direction"],
                "current_confidence": float(decision["confidence"]),
                "structural_direction_matches_side": (
                    decision["structural_direction"] == source["side"]
                ),
            }
        )
    return _json_records(pd.DataFrame(rows))


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    return {
        "bars": file_evidence(args.bars),
        "supplemental_bars": file_evidence(args.supplemental_bars),
        "creator_recipe_rows": file_evidence(args.source_rows),
        "creator_live_rows": file_evidence(args.live_rows),
        "runtime_config": _verified_config(args.config),
        "archive_audit": file_evidence(args.archive_audit),
    }


def _limitations() -> list[str]:
    return [
        "Eight historical rows are selected winners; precision and expectancy are not estimable.",
        "The creator BK-up algorithm is not defined, so all three B mappings are proxies.",
        "UTC-5 is inferred from earlier screenshots; displayed-as-UTC is sensitivity only.",
        "Six July 27 live rows have no recipe labels and cannot validate B/C membership.",
        "Current detector confidence is not assumed equivalent to creator confidence.",
        "Alignment does not establish maker fillability or economic profitability.",
    ]


def _report(args: argparse.Namespace) -> dict[str, object]:
    _verified_config(args.config)
    bars = _merged_bars(args.bars, args.supplemental_bars)
    profile = load_hypervelocity_profile(args.config)
    decisions = classify_multitimeframe(bars, config=profile.regime_config)
    raw_1m = classify_timeframe(bars, config=profile.regime_config)
    events = build_selective_recipe_events(decisions, raw_1m)
    inferred = _source_rows(args.source_rows, displayed_as_utc=False)
    displayed_utc = _source_rows(args.source_rows, displayed_as_utc=True)
    live = _live_rows(args.live_rows)
    return {
        "ok": True,
        "experiment": "creator_selective_btc_bc_alignment_v1",
        **_experiment_contract(args),
        "window_start_utc": bars.index[0].isoformat(),
        "window_end_exclusive_utc": (
            bars.index[-1] + pd.Timedelta(minutes=1)
        ).isoformat(),
        "source_evidence": _source_evidence(args),
        "fresh_archive_audit": _verified_audit(args.archive_audit),
        "decision_identity_sha256": decision_identity(decisions),
        "event_diagnostics": _event_diagnostics(events),
        "alignment": {
            "utc_minus_5_inference": _alignment_payload(inferred, events),
            "displayed_as_utc_sensitivity": _alignment_payload(displayed_utc, events),
        },
        "live_rows_descriptive_only": _live_market_context(live, decisions),
        "limitations": _limitations(),
    }


def main() -> int:
    """Write one immutable selective-recipe source-alignment report."""
    args = _parser().parse_args()
    try:
        write_immutable_json(args.out, _report(args))
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
