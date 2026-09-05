"""Read-only rolling checkpoints for the shared live cohort."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from hypervector.research import cohort_live_checkpoint
from hypervector.research.cohort_live_checkpoint import (
    _asset_paths,
    build_live_checkpoint,
    publish_live_checkpoint,
)
from hypervector.research.cohort_configuration_generation import (
    ConfigurationGenerationExpectation,
)
from hypervector.research.cohort_asymmetric_forward_observer import (
    AsymmetricForwardDeclaration,
)
from hypervector.research.cohort_eligible_policy_forward import (
    EligiblePolicyForwardSpec,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
    EligiblePolicyFundingEvent,
)
from test_multi_asset_live_audit import _asset_rows, _cohort_rows

_RUN_ID = "cohort-live-a"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_GENERATED_AT = datetime(2026, 8, 2, 4, 0, tzinfo=timezone.utc)


def test_asset_paths_preserve_lowercase_hip3_namespace_identity(
    tmp_path: Path,
) -> None:
    """HIP-3 filenames must resolve to their exact configured identities."""
    cohort = tmp_path / "decisions.jsonl"
    cohort.touch()
    btc = tmp_path / "btc.jsonl"
    hip3 = tmp_path / "xyz:sp500.jsonl"
    btc.touch()
    hip3.touch()

    paths = _asset_paths(tmp_path, cohort, ("BTC", "xyz:SP500"))

    assert paths == {"BTC": btc, "xyz:SP500": hip3}


def test_checkpoint_reconciles_stopped_assets_with_old_running_heartbeat() -> None:
    """A stale cohort heartbeat cannot make terminal assets look active."""
    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    assert checkpoint["checkpoint_contract"] == {
        "report_only": True,
        "final": False,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "performance_gate": False,
        "balance_gate": False,
    }
    assert checkpoint["lifecycle"]["state"] == (
        "stale_running_heartbeat_after_asset_stop"
    )
    assert checkpoint["lifecycle"]["cohort_heartbeat_status"] == "running"
    assert checkpoint["lifecycle"]["asset_states"] == {
        symbol: "STOPPED" for symbol in _SYMBOLS
    }


def test_checkpoint_reports_consistent_running_assets() -> None:
    """A running heartbeat plus nonterminal assets is internally consistent."""
    assets = {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS}

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        assets,
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    assert checkpoint["lifecycle"]["state"] == "running_consistent"
    assert checkpoint["lifecycle"]["all_assets_terminal"] is False
    risk = checkpoint["audit"]["risk_utilization"]
    assert risk["summary"]["cap_bound_assets"] == 4
    assert risk["summary"]["executable_assets"] == 2
    assert risk["summary"][
        "maximum_simultaneous_effective_margin_fraction"
    ] == pytest.approx(2 * 5.0 / 503.16)
    assert risk["by_asset"]["BTC"]["configured_margin_fraction"] == 0.03
    assert risk["by_asset"]["BTC"]["effective_margin_fraction"] == pytest.approx(
        5.0 / 503.16
    )


def test_checkpoint_projects_predeclared_asymmetric_forward_evidence() -> None:
    """The read-only checkpoint should refresh the frozen portfolio observer."""
    declaration = AsymmetricForwardDeclaration(
        predeclared_at_utc="2026-08-02T04:00:00Z",
        entry_cutoff_timestamp_ms=int(_GENERATED_AT.timestamp() * 1_000),
    )

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        asymmetric_forward_declaration=declaration,
    )

    observer = checkpoint["audit"]["asymmetric_forward_observer"]
    assert observer["selected_variant_id"] == "sol_symmetric_sensitivity"
    assert observer["entry_cutoff_timestamp_ms"] == int(
        _GENERATED_AT.timestamp() * 1_000
    )
    assert observer["evidence_state"] == "awaiting_post_cutoff_resolution"
    assert observer["candidate"]["closed_trades"] == 0
    assert observer["contract"]["execution_authority"] == "none"


def test_checkpoint_projects_report_only_side_composition() -> None:
    """Every live checkpoint should refresh exact route-side research evidence."""
    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    composition = checkpoint["audit"]["side_composition"]
    assert composition["schema_version"] == 2
    assert composition["mode"] == "cohort_separate_side_composition"
    assert composition["contract"]["report_only"] is True
    assert composition["contract"]["execution_authority"] == "none"
    assert composition["contract"]["runtime_strategy_changed"] is False
    assert composition["source"]["run_id"] == _RUN_ID
    assert composition["source"]["profile_id"] == "cohort-profile"
    assert set(composition["frontier"]) == {"long", "short"}
    assert composition["summary"]["components"] == len(composition["components"])


def test_checkpoint_keeps_current_run_separate_from_portfolio_archive() -> None:
    """A full-history projection cannot inflate the active run's trade count."""
    archive = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "symbols": ["BTC", "ETH", "SOL", "HYPE"],
        "coverage": {
            "complete": True,
            "closed_orders": 26,
            "leverage_matches": 26,
        },
        "performance": {"scope": "all_live_history"},
    }

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        portfolio_archive=archive,
    )

    assert checkpoint["audit"]["portfolio_archive"] == archive
    current = checkpoint["audit"]["trade_reflections"]["performance"]["current_run"][
        "total"
    ]
    assert current["closed_trades"] == 0

    unsafe = json.loads(json.dumps(archive))
    unsafe["contract"]["execution_authority"] = "hyperliquid_mainnet"
    with pytest.raises(ValueError, match="portfolio archive contract"):
        build_live_checkpoint(
            _cohort_rows(),
            {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
            run_id=_RUN_ID,
            generated_at=_GENERATED_AT,
            portfolio_archive=unsafe,
        )


def test_checkpoint_does_not_downgrade_epoch_archive_from_bounded_reflections() -> None:
    """An append-only durable archive outranks a shorter reflection window."""
    fingerprint = "a" * 64
    archive = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "accounting_epoch": {
            "epoch_id": "growth_5000",
            "profile_fingerprint": fingerprint,
            "start_venue_timestamp_ms": 1,
        },
        "coverage": {
            "complete": True,
            "closed_orders": 9,
            "leverage_matches": 9,
        },
        "performance": {"scope": "all_live_history"},
    }

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        portfolio_archive=archive,
    )

    assert checkpoint["audit"]["portfolio_archive"] == archive


def test_full_checkpoint_rejects_divergent_archive_performance() -> None:
    """Equal all-time coverage must also reconcile PnL and realized drawdown."""
    archive = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "performance": {
            "total": {
                "closed_trades": 0,
                "net_pnl_usd": 1.0,
                "maximum_closed_sequence_drawdown_usd": 0.0,
            }
        },
    }

    with pytest.raises(ValueError, match="archive net_pnl_usd"):
        build_live_checkpoint(
            _cohort_rows(),
            {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
            run_id=_RUN_ID,
            generated_at=_GENERATED_AT,
            portfolio_archive=archive,
        )


def test_checkpoint_attaches_only_report_only_execution_opportunity_matrix() -> None:
    """Executable missed-entry evidence remains read-only checkpoint telemetry."""
    matrix = {
        "schema_version": 1,
        "mode": "cohort_execution_opportunity_matrix",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
        },
        "hypotheses": 0,
        "comparisons": 0,
        "results": [],
    }

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        execution_opportunity_matrix=matrix,
    )

    attached = checkpoint["audit"]["execution_opportunity_matrix"]
    provenance = attached.pop("checkpoint_provenance")
    assert attached == matrix
    assert provenance["relationship"] == "unattributed"
    assert provenance["checkpoint_run_id"] == _RUN_ID

    unsafe = json.loads(json.dumps(matrix))
    unsafe["contract"]["execution_authority"] = "venue"
    with pytest.raises(ValueError, match="execution authority"):
        build_live_checkpoint(
            _cohort_rows(),
            {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
            run_id=_RUN_ID,
            generated_at=_GENERATED_AT,
            execution_opportunity_matrix=unsafe,
        )


def test_checkpoint_labels_prior_run_opportunity_matrix_as_historical() -> None:
    """A different earlier evidence run cannot look current in the TUI payload."""
    matrix = {
        "schema_version": 1,
        "mode": "cohort_execution_opportunity_matrix",
        "runtime_updated_at_utc": "2026-08-01T12:00:00+00:00",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
        },
        "evidence": {
            "run_id": "cohort-live-prior",
            "config": "configs/prior.toml",
        },
        "hypotheses": 0,
        "comparisons": 0,
        "results": [],
    }

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        execution_opportunity_matrix=matrix,
    )

    assert checkpoint["audit"]["execution_opportunity_matrix"][
        "checkpoint_provenance"
    ] == {
        "relationship": "historical_prior_run",
        "checkpoint_run_id": _RUN_ID,
        "checkpoint_first_observed_at_utc": "2026-08-01T15:59:59+00:00",
        "evidence_run_id": "cohort-live-prior",
        "evidence_config_path": "configs/prior.toml",
        "matrix_updated_at_utc": "2026-08-01T12:00:00+00:00",
    }


def test_checkpoint_labels_same_run_opportunity_matrix_as_current() -> None:
    """Matching run identity is explicitly distinguished from historical data."""
    matrix = {
        "schema_version": 1,
        "mode": "cohort_execution_opportunity_matrix",
        "runtime_updated_at_utc": "2026-08-02T03:30:00+00:00",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
        },
        "evidence": {"run_id": _RUN_ID, "config": "configs/current.toml"},
        "hypotheses": 0,
        "comparisons": 0,
        "results": [],
    }

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        execution_opportunity_matrix=matrix,
    )

    provenance = checkpoint["audit"]["execution_opportunity_matrix"][
        "checkpoint_provenance"
    ]
    assert provenance["relationship"] == "current_run"
    assert provenance["checkpoint_run_id"] == provenance["evidence_run_id"]


def test_checkpoint_attaches_exact_eligible_policy_forward_journal() -> None:
    """The bounded checkpoint carries the frozen candidate lifecycle observer."""
    spec = EligiblePolicyForwardSpec(
        source_strategy_id="eth_breakout_precompression_pullback_bidirectional_v1",
        candidate_strategy_id=(
            "eth_breakout_precompression_pullback_bidirectional_v1_v12"
        ),
        symbol="ETH",
        source_run_id=_RUN_ID,
        cutoff_time_ms=1,
        stop_bps=60.0,
        maximum_hold_minutes=720,
        modeled_round_trip_friction_bps=13.0,
        notional_usd=25.0,
        maximum_positions=4,
    )

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        eligible_policy_forward_spec=spec,
    )

    journal = checkpoint["audit"]["eligible_policy_forward"]
    assert journal["state"] == "awaiting_fresh_eligible_signal"
    assert journal["contract"]["execution_authority"] == "none"
    assert journal["contract"]["live_strategy_changed"] is False


def test_checkpoint_threads_official_funding_into_exact_policy_journal() -> None:
    """Funding evidence remains report-only and explicitly source attributed."""
    spec = EligiblePolicyForwardSpec(
        source_strategy_id="eth_breakout_precompression_pullback_bidirectional_v1",
        candidate_strategy_id=(
            "eth_breakout_precompression_pullback_bidirectional_v1_v12"
        ),
        symbol="ETH",
        source_run_id=_RUN_ID,
        cutoff_time_ms=1,
        stop_bps=60.0,
        maximum_hold_minutes=720,
        modeled_round_trip_friction_bps=13.0,
        notional_usd=25.0,
        maximum_positions=4,
    )
    funding = EligiblePolicyFundingEvidence(
        symbol="ETH",
        requested_start_ms=1,
        requested_end_ms=1_000,
        events=(EligiblePolicyFundingEvent(500, 0.00001),),
    )

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        eligible_policy_forward_spec=spec,
        eligible_policy_funding_evidence=funding,
    )

    contract = checkpoint["audit"]["eligible_policy_forward"]["contract"]
    assert contract["funding_included"] is True
    assert contract["funding_source"] == "hl_funding_history"
    assert contract["execution_authority"] == "none"


def test_checkpoint_keeps_venue_portfolio_separate_from_execution_collateral() -> None:
    """Report-only total value must not alter the ledger's sizing account value."""
    venue_portfolio = {
        "status": "observed",
        "portfolio_value_usd": 507.08,
        "execution_collateral_value_usd": 504.11,
        "non_usdc_spot_value_usd": 2.97,
        "vault_equity_usd": 0.0,
        "valued_spot_assets": [],
        "observed_at_utc": "2026-08-04T09:00:00+00:00",
        "valuation_source": "spot_midpoints_plus_vault_equity",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "execution_collateral_unchanged": True,
        },
    }

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        venue_portfolio=venue_portfolio,
    )

    assert checkpoint["venue_portfolio"] == venue_portfolio
    assert checkpoint["audit"]["risk_utilization"][
        "account_value_usd"
    ] == pytest.approx(503.16)


def test_checkpoint_embeds_configured_selective_allocation_challenger() -> None:
    """The current provider topology receives its report-only comparison."""
    rows = _cohort_rows()
    providers = rows[0]["payload"]["providers"]
    providers[0]["execution_symbols"] = ["BTC", "HYPE"]
    providers[1]["execution_symbols"] = ["SOL", "HYPE"]
    providers.append(
        {
            "strategy_id": "hype_breakout_onset_bidirectional_v1",
            "symbols": ["HYPE"],
            "execution_symbols": ["HYPE"],
        }
    )

    checkpoint = build_live_checkpoint(
        rows,
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    challenger = checkpoint["audit"]["allocation_challenger"]
    assert challenger["status"] == "candidate_not_active"
    assert challenger["contract"]["balance_gate"] is False
    assert challenger["target_provider_symbol"] == (
        "hype_breakout_onset_bidirectional_v1|HYPE"
    )
    assert challenger["current"]["planned_notional_usd"] == pytest.approx(25.0)
    assert challenger["candidate"]["planned_notional_usd"] == pytest.approx(75.0)
    assert challenger["profit_forecast"] is None


def test_checkpoint_preserves_exact_maximum_hold_decision() -> None:
    """A causal soft-deadline decision survives the rolling projection."""
    rows = _cohort_rows()
    rows.append(
        _maximum_hold_row(
            sequence=len(rows) + 1,
            outcome="extend",
            exit_reason=None,
        )
    )

    checkpoint = build_live_checkpoint(
        rows,
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    evidence = checkpoint["audit"]["maximum_hold_decisions"]
    assert evidence["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "performance_gate": False,
        "balance_gate": False,
    }
    assert evidence["summary"] == {
        "observed": 1,
        "extended": 1,
        "exited": 0,
        "provider_symbols": 1,
    }
    assert evidence["by_provider_symbol"] == {
        "hulk_expansion_bidirectional_tuned_v2|HYPE": {
            "observed": 1,
            "extended": 1,
            "exited": 0,
        }
    }
    assert evidence["latest_decisions"] == [rows[-1]["payload"]]


def test_checkpoint_rejects_incoherent_maximum_hold_outcome() -> None:
    """An exit boundary cannot omit the runner's causal exit reason."""
    rows = _cohort_rows()
    rows.append(
        _maximum_hold_row(
            sequence=len(rows) + 1,
            outcome="exit",
            exit_reason=None,
        )
    )

    with pytest.raises(ValueError, match="exit outcome requires exit_reason"):
        build_live_checkpoint(
            rows,
            {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
            run_id=_RUN_ID,
            generated_at=_GENERATED_AT,
        )


def test_checkpoint_rejects_negative_maximum_hold_threshold() -> None:
    """The configured alignment threshold remains a true [0,1] fraction."""
    rows = _cohort_rows()
    decision = _maximum_hold_row(
        sequence=len(rows) + 1,
        outcome="extend",
        exit_reason=None,
    )
    decision["payload"]["structure_alignment_threshold"] = -0.5
    rows.append(decision)

    with pytest.raises(ValueError, match=r"alignment threshold is outside \[0,1\]"):
        build_live_checkpoint(
            rows,
            {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
            run_id=_RUN_ID,
            generated_at=_GENERATED_AT,
        )


def test_checkpoint_reports_mixed_asset_lifecycle() -> None:
    """Partial shutdown remains visible instead of collapsing to one status."""
    assets = {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS}
    assets["BTC"] = _asset_rows("BTC")

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        assets,
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    assert checkpoint["lifecycle"]["state"] == "mixed_asset_lifecycle"


def test_checkpoint_discloses_stale_runtime_configuration() -> None:
    """A running fingerprint mismatch remains visible but has no authority."""
    expectation = ConfigurationGenerationExpectation(
        source_path="configs/cohort.toml",
        source_modified_at_utc="2026-08-03T11:16:04+00:00",
        profile_fingerprint="current-profile",
    )

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        configuration_expectation=expectation,
    )

    generation = checkpoint["configuration_generation"]
    assert generation == {
        "state": "stale_runtime_configuration",
        "matches_runtime": False,
        "runtime_profile_fingerprint": "cohort-profile-fingerprint",
        "current_profile_fingerprint": "current-profile",
        "source_path": "configs/cohort.toml",
        "source_modified_at_utc": "2026-08-03T11:16:04+00:00",
        "current_asset_sizing": {},
        "current_asset_entry_slippage_caps": {},
        "current_asset_market_slippage_caps": {},
        "current_entry_context_overrides": {},
        "current_provider_sizing_overrides": {},
        "current_provider_directional_sizing_overrides": {},
        "current_provider_exit_policies": {},
        "current_provider_directional_exit_policies": {},
        "restart_state": "candidate_flat_no_orders",
        "blocking_assets": [],
        "execution_authority": "none",
        "automatic_restart": False,
    }


def test_checkpoint_confirms_matching_runtime_configuration() -> None:
    """Equal non-secret identities are reported as current, not inferred stale."""
    expectation = ConfigurationGenerationExpectation(
        source_path="configs/cohort.toml",
        source_modified_at_utc="2026-08-03T11:16:04+00:00",
        profile_fingerprint="cohort-profile-fingerprint",
    )

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        configuration_expectation=expectation,
    )

    generation = checkpoint["configuration_generation"]
    assert generation["state"] == "current_runtime_configuration"
    assert generation["matches_runtime"] is True
    assert generation["restart_state"] == "not_required_current_configuration"
    assert generation["blocking_assets"] == []
    assert generation["execution_authority"] == "none"
    assert generation["automatic_restart"] is False


def test_publish_atomically_replaces_one_bounded_latest_checkpoint(
    tmp_path: Path,
) -> None:
    """Each interval replaces one report and discloses a torn source suffix."""
    ledger_root = tmp_path / "ledgers"
    ledger_root.mkdir()
    _write_rows(ledger_root / "decisions.jsonl", _cohort_rows())
    for symbol in _SYMBOLS:
        _write_rows(ledger_root / f"{symbol.lower()}.jsonl", _asset_rows(symbol))
    with (ledger_root / "btc.jsonl").open("ab") as stream:
        stream.write(b'{"sequence":6')
    destination = tmp_path / "runtime" / "latest_checkpoint.json"

    first = publish_live_checkpoint(
        ledger_root,
        destination,
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )
    second_time = datetime(2026, 8, 2, 4, 1, tzinfo=timezone.utc)
    second = publish_live_checkpoint(
        ledger_root,
        destination,
        run_id=_RUN_ID,
        generated_at=second_time,
    )

    assert first["evidence"]["assets"]["BTC"]["incomplete_tail_dropped"] is True
    assert second["generated_at_utc"] == second_time.isoformat()
    assert json.loads(destination.read_text(encoding="utf-8")) == second
    assert [path.name for path in destination.parent.iterdir()] == [destination.name]


def test_publish_attaches_profile_acceptance_before_atomic_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact report verdict must be present in the published checkpoint."""
    ledger_root = tmp_path / "ledgers"
    ledger_root.mkdir()
    _write_rows(ledger_root / "decisions.jsonl", _cohort_rows())
    for symbol in _SYMBOLS:
        _write_rows(ledger_root / f"{symbol.lower()}.jsonl", _asset_rows(symbol))
    destination = tmp_path / "runtime" / "latest_checkpoint.json"
    calls: list[tuple[Path, datetime]] = []

    def attach(
        checkpoint: dict[str, object],
        config_path: Path,
        *,
        observed_at: datetime,
    ) -> bool:
        checkpoint["poststart_acceptance"] = {"accepted": True}
        calls.append((config_path, observed_at))
        return True

    monkeypatch.setattr(
        cohort_live_checkpoint,
        "attach_seven_asset_poststart_acceptance",
        attach,
    )
    config_path = Path("configs/multi_asset_bidirectional_canary.toml")

    checkpoint = publish_live_checkpoint(
        ledger_root,
        destination,
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        config_path=config_path,
    )

    assert calls == [(config_path, _GENERATED_AT)]
    assert checkpoint["poststart_acceptance"] == {"accepted": True}
    assert json.loads(destination.read_text(encoding="utf-8")) == checkpoint


def test_publish_retains_retired_history_without_runtime_authority(
    tmp_path: Path,
) -> None:
    """Retired ledgers stay historical but never enter runtime lifecycle scope."""
    ledger_root = tmp_path / "ledgers"
    ledger_root.mkdir()
    _write_rows(ledger_root / "decisions.jsonl", _cohort_rows())
    for symbol in _SYMBOLS:
        _write_rows(ledger_root / f"{symbol.lower()}.jsonl", _asset_rows(symbol))
    _write_rows(ledger_root / "doge.jsonl", _asset_rows("DOGE"))
    destination = tmp_path / "runtime" / "latest_checkpoint.json"

    checkpoint = publish_live_checkpoint(
        ledger_root,
        destination,
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    assert set(checkpoint["evidence"]["assets"]) == set(_SYMBOLS)
    assert set(checkpoint["evidence"]["retired_assets"]) == {"DOGE"}
    assert set(checkpoint["lifecycle"]["asset_states"]) == set(_SYMBOLS)


def test_publish_bounded_execution_history_preserves_complete_projection(
    tmp_path: Path,
) -> None:
    """The rolling writer uses compatible suffixes without shrinking all-time data."""
    ledger_root = tmp_path / "ledgers"
    ledger_root.mkdir()
    _write_rows(ledger_root / "decisions.jsonl", _cohort_rows())
    for symbol in _SYMBOLS:
        _write_rows(ledger_root / f"{symbol.lower()}.jsonl", _asset_rows(symbol))
    destination = tmp_path / "runtime" / "latest_checkpoint.json"
    archive = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "performance": {
            "total": {
                "closed_trades": 0,
                "net_pnl_usd": 0.0,
                "maximum_closed_sequence_drawdown_usd": 0.0,
            }
        },
    }
    complete = publish_live_checkpoint(
        ledger_root,
        destination,
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        portfolio_archive=archive,
    )

    bounded = publish_live_checkpoint(
        ledger_root,
        destination,
        run_id=_RUN_ID,
        generated_at=datetime(2026, 8, 2, 4, 1, tzinfo=timezone.utc),
        portfolio_archive=archive,
        compatible_execution_history=True,
        complete_historical_checkpoint=complete,
    )

    assert bounded["evidence"]["cohort"]["snapshot_scope"] == (
        "compatible_execution_history"
    )
    assert all(
        item["snapshot_scope"] == "compatible_execution_history"
        for item in bounded["evidence"]["assets"].values()
    )
    assert bounded["audit"]["historical_projection"]["status"] == (
        "current_by_execution_signature"
    )
    assert (
        bounded["audit"]["trade_reflections"]["all_time_live"]
        == (complete["audit"]["trade_reflections"]["all_time_live"])
    )
    assert json.loads(destination.read_text(encoding="utf-8")) == bounded


def test_publish_current_run_only_starts_at_exact_run_identity(tmp_path: Path) -> None:
    """Pending archive sync must not rescan compatible prior-run history."""
    ledger_root = tmp_path / "ledgers"
    ledger_root.mkdir()
    current_cohort = _cohort_rows()
    prior_cohort = deepcopy(current_cohort)
    _set_prior_run(prior_cohort, "cohort-live-prior")
    _continue_sequences(current_cohort, len(prior_cohort))
    _write_rows(
        ledger_root / "decisions.jsonl",
        [*prior_cohort, *current_cohort],
    )
    for symbol in _SYMBOLS:
        current_asset = _active_asset_rows(symbol)
        prior_asset = deepcopy(current_asset)
        _set_prior_run(prior_asset, "cohort-live-prior")
        _continue_sequences(current_asset, len(prior_asset))
        _write_rows(
            ledger_root / f"{symbol.lower()}.jsonl",
            [*prior_asset, *current_asset],
        )
    retired_asset = _active_asset_rows("DOGE")
    _set_prior_run(retired_asset, "cohort-live-retired")
    _write_rows(ledger_root / "doge.jsonl", retired_asset)
    archive = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "accounting_epoch": {
            "epoch_id": "growth_5000",
            "profile_fingerprint": "a" * 64,
            "start_venue_timestamp_ms": 1,
        },
        "coverage": {
            "complete": True,
            "closed_orders": 0,
            "leverage_matches": 0,
        },
        "performance": {"scope": "all_live_history"},
    }

    checkpoint = publish_live_checkpoint(
        ledger_root,
        tmp_path / "runtime" / "latest_checkpoint.json",
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        portfolio_archive=archive,
        current_run_only=True,
    )

    assert checkpoint["evidence"]["cohort"]["source_start_offset"] > 0
    assert all(
        item["source_start_offset"] > 0
        for item in checkpoint["evidence"]["assets"].values()
    )
    assert checkpoint["audit"]["portfolio_archive"] == archive
    assert checkpoint["evidence"]["retired_assets"] == {}


def test_bounded_checkpoint_retains_verified_complete_historical_projection() -> None:
    """Current telemetry stays fresh while all-time evidence keeps full coverage."""
    candidate = _historical_projection_fixture("2026-08-08T10:30:00+00:00")
    complete = _historical_projection_fixture("2026-08-08T10:00:00+00:00")
    candidate["audit"]["routing"] = {"cycles": 42}
    candidate["audit"]["trade_reflections"]["all_time_live"] = {
        "closed_trades": 2,
        "marker": "bounded",
    }
    candidate["audit"]["profit_lock_challenger"]["all_time_live_mechanism"] = {
        "marker": "bounded"
    }
    candidate["audit"]["profit_lock_challenger"][
        "risk_normalized_all_time_live_mechanism"
    ] = {"marker": "bounded-risk"}
    candidate["audit"]["side_composition"]["marker"] = "bounded"

    merged = cohort_live_checkpoint.merge_complete_historical_projection(
        candidate,
        complete,
    )

    assert merged["audit"]["routing"] == {"cycles": 42}
    assert merged["audit"]["trade_reflections"]["all_time_live"] == {
        "history_schema_version": 1,
        "closed_trades": 28,
        "performance": {
            "total": {
                "closed_trades": 28,
                "net_pnl_usd": 2.25,
                "maximum_closed_sequence_drawdown_usd": 1.75,
            }
        },
        "marker": "complete",
    }
    assert merged["audit"]["trade_reflections"]["provider_contract_history"] == {
        "marker": "complete"
    }
    assert merged["audit"]["entry_alignment_mechanism"] == {"marker": "complete"}
    assert merged["audit"]["side_composition"]["marker"] == "bounded"
    assert merged["audit"]["side_composition"]["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
    assert merged["audit"]["hulk_entry_quality_challenger"] == {"marker": "complete"}
    assert merged["audit"]["profit_lock_challenger"]["current_profile_mechanism"] == {
        "marker": "bounded-current"
    }
    assert merged["audit"]["profit_lock_challenger"]["all_time_live_mechanism"] == {
        "marker": "complete"
    }
    assert merged["audit"]["profit_lock_challenger"][
        "risk_normalized_all_time_live_mechanism"
    ] == {"marker": "complete"}
    projection = merged["audit"]["historical_projection"]
    assert projection["status"] == "current_by_execution_signature"
    assert projection["source_checkpoint_generated_at_utc"] == (
        "2026-08-08T10:00:00+00:00"
    )
    assert projection["verified_at_utc"] == "2026-08-08T10:30:00+00:00"
    assert candidate["audit"]["trade_reflections"]["all_time_live"]["marker"] == (
        "bounded"
    )


def test_bounded_checkpoint_keeps_scorecard_aligned_with_cached_provider_history() -> (
    None
):
    """Cached provider outcomes retain matching scorecard execution evidence."""
    candidate = _historical_projection_fixture("2026-08-08T10:30:00+00:00")
    complete = _historical_projection_fixture("2026-08-08T10:00:00+00:00")
    candidate_score = {
        "summary": {"mappings": 1, "mappings_with_live_outcomes": 0},
        "by_provider_symbol": {
            "strategy|BTC": {
                "forward_evaluations": 12,
                "execution_outcomes_identifiable": False,
            }
        },
    }
    complete_score = {
        "summary": {"mappings": 1, "mappings_with_live_outcomes": 1},
        "by_provider_symbol": {
            "strategy|BTC": {
                "forward_evaluations": 8,
                "execution_outcomes_identifiable": True,
                "execution_performance_scope": "provider_execution_contract_history",
                "execution_performance": {"closed_trades": 2},
                "execution_performance_by_side": {"long": {"closed_trades": 2}},
                "repeatability_evidence": {"closed_trades": 2},
            }
        },
    }
    candidate["audit"]["strategy_scorecard"] = candidate_score
    complete["audit"]["strategy_scorecard"] = complete_score
    complete["audit"]["trade_reflections"]["provider_contract_history"] = {
        "compatible_trades": 2,
        "performance": {"total": {"closed_trades": 2}},
    }

    merged = cohort_live_checkpoint.merge_complete_historical_projection(
        candidate,
        complete,
    )

    scorecard = merged["audit"]["strategy_scorecard"]
    record = scorecard["by_provider_symbol"]["strategy|BTC"]
    assert record["forward_evaluations"] == 12
    assert record["execution_outcomes_identifiable"] is True
    assert record["execution_performance"] == {"closed_trades": 2}
    assert record["execution_performance_by_side"] == {"long": {"closed_trades": 2}}
    assert record["repeatability_evidence"] == {"closed_trades": 2}
    assert scorecard["summary"]["mappings_with_live_outcomes"] == 1


def test_bounded_checkpoint_rebuilds_inconsistent_cached_scorecard_history() -> None:
    """A poisoned scorecard cache cannot survive a rolling historical merge."""
    candidate = _historical_projection_fixture("2026-08-08T10:30:00+00:00")
    complete = _historical_projection_fixture("2026-08-08T10:00:00+00:00")
    empty_scorecard = {
        "summary": {"mappings": 1, "mappings_with_live_outcomes": 0},
        "by_provider_symbol": {
            "strategy|BTC": {"execution_outcomes_identifiable": False}
        },
    }
    candidate["audit"]["strategy_scorecard"] = deepcopy(empty_scorecard)
    complete["audit"]["strategy_scorecard"] = deepcopy(empty_scorecard)
    complete["audit"]["trade_reflections"]["provider_contract_history"] = {
        "compatible_trades": 2,
        "performance": {"total": {"closed_trades": 2}},
    }

    with pytest.raises(
        cohort_live_checkpoint.HistoricalProjectionStale,
        match="scorecard outcomes differ from provider history",
    ):
        cohort_live_checkpoint.merge_complete_historical_projection(
            candidate,
            complete,
        )


def test_bounded_checkpoint_refuses_stale_historical_execution_signature() -> None:
    """A new venue fill requires a fresh complete-ledger historical projection."""
    candidate = _historical_projection_fixture("2026-08-08T10:30:00+00:00")
    complete = _historical_projection_fixture("2026-08-08T10:00:00+00:00")
    candidate["audit"]["execution"]["fills"] = 9
    candidate["audit"]["execution"]["fill_details"].append(
        {"trade_id": 2, "operation": "entry", "oid": 102}
    )

    with pytest.raises(
        cohort_live_checkpoint.HistoricalProjectionStale,
        match="execution history changed",
    ):
        cohort_live_checkpoint.merge_complete_historical_projection(
            candidate,
            complete,
        )


def test_bounded_checkpoint_accepts_exact_profile_restart_without_new_fills() -> None:
    """A process run-id change alone cannot force a full-ledger hot-loop rebuild."""
    candidate = _historical_projection_fixture("2026-08-08T10:30:00+00:00")
    complete = _historical_projection_fixture("2026-08-08T10:00:00+00:00")
    candidate["audit"]["run"]["run_id"] = "run-restarted"
    candidate["audit"]["execution"]["history_run_ids"].append("run-restarted")
    candidate["audit"]["side_composition"]["marker"] = "bounded-restart"

    merged = cohort_live_checkpoint.merge_complete_historical_projection(
        candidate,
        complete,
    )

    assert merged["audit"]["run"]["run_id"] == "run-restarted"
    assert merged["audit"]["side_composition"]["marker"] == "bounded-restart"
    assert merged["audit"]["historical_projection"]["status"] == (
        "current_by_execution_signature"
    )


def test_bounded_checkpoint_refuses_archive_ahead_of_complete_history() -> None:
    """DuckDB close coverage cannot outrun the copied rich-history evidence."""
    candidate = _historical_projection_fixture("2026-08-08T10:30:00+00:00")
    complete = _historical_projection_fixture("2026-08-08T10:00:00+00:00")
    candidate["audit"]["portfolio_archive"]["performance"]["total"]["closed_trades"] = (
        29
    )

    with pytest.raises(
        cohort_live_checkpoint.HistoricalProjectionStale,
        match="archive closed lifecycle count",
    ):
        cohort_live_checkpoint.merge_complete_historical_projection(
            candidate,
            complete,
        )


@pytest.mark.parametrize(
    ("field", "archive_value"),
    (
        ("net_pnl_usd", 1.25),
        ("maximum_closed_sequence_drawdown_usd", 3.5),
    ),
)
def test_bounded_checkpoint_refuses_archive_performance_mismatch(
    field: str,
    archive_value: float,
) -> None:
    """Equal trade counts cannot conceal divergent archive path economics."""
    candidate = _historical_projection_fixture("2026-08-08T10:30:00+00:00")
    complete = _historical_projection_fixture("2026-08-08T10:00:00+00:00")
    candidate["audit"]["portfolio_archive"]["performance"]["total"][field] = (
        archive_value
    )

    with pytest.raises(
        cohort_live_checkpoint.HistoricalProjectionStale,
        match=f"archive {field}",
    ):
        cohort_live_checkpoint.merge_complete_historical_projection(
            candidate,
            complete,
        )


def test_bounded_checkpoint_refuses_stale_historical_reflection_schema() -> None:
    """A new report field must force one full-ledger history rebuild."""
    candidate = _historical_projection_fixture("2026-08-08T10:30:00+00:00")
    complete = _historical_projection_fixture("2026-08-08T10:00:00+00:00")
    del complete["audit"]["trade_reflections"]["all_time_live"][
        "history_schema_version"
    ]

    with pytest.raises(
        cohort_live_checkpoint.HistoricalProjectionStale,
        match="historical reflection schema changed",
    ):
        cohort_live_checkpoint.merge_complete_historical_projection(
            candidate,
            complete,
        )


def test_bounded_checkpoint_rejects_unsafe_historical_lineage_contract() -> None:
    """A cached bounded document cannot smuggle execution authority into history."""
    candidate = _historical_projection_fixture("2026-08-08T10:30:00+00:00")
    complete = _historical_projection_fixture("2026-08-08T10:20:00+00:00")
    complete["audit"]["historical_projection"] = {
        "schema_version": 1,
        "mode": "cached_complete_ledger_history_v1",
        "status": "current_by_execution_signature",
        "source_checkpoint_generated_at_utc": "2026-08-08T10:00:00+00:00",
        "contract": {
            "report_only": True,
            "execution_authority": "hyperliquid_mainnet",
            "runtime_strategy_changed": False,
        },
    }

    with pytest.raises(ValueError, match="historical projection contract"):
        cohort_live_checkpoint.merge_complete_historical_projection(
            candidate,
            complete,
        )


def test_bounded_checkpoint_rejects_unsafe_side_composition_contract() -> None:
    """Fresh route-side evidence cannot carry execution authority."""
    candidate = _historical_projection_fixture("2026-08-08T10:30:00+00:00")
    complete = _historical_projection_fixture("2026-08-08T10:20:00+00:00")
    candidate["audit"]["side_composition"]["contract"]["execution_authority"] = (
        "hyperliquid_mainnet"
    )

    with pytest.raises(ValueError, match="side composition contract"):
        cohort_live_checkpoint.merge_complete_historical_projection(
            candidate,
            complete,
        )


def _active_asset_rows(symbol: str) -> list[dict[str, object]]:
    rows = _asset_rows(symbol)
    payload = rows[-1]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = "FLAT"
    payload["stop_reason"] = None
    return rows


def _set_prior_run(rows: list[dict[str, object]], run_id: str) -> None:
    for row in rows:
        row["run_id"] = run_id


def _continue_sequences(rows: list[dict[str, object]], offset: int) -> None:
    for row in rows:
        sequence = row.get("sequence")
        assert isinstance(sequence, int) and not isinstance(sequence, bool)
        row["sequence"] = sequence + offset


def _historical_projection_fixture(generated_at: str) -> dict[str, object]:
    all_time_mechanisms = {
        key: {"marker": "complete"}
        for key in (
            "all_time_live_mechanism",
            "mature_profit_floor_all_time_live_mechanism",
            "risk_normalized_all_time_live_mechanism",
            "regime_conditioned_all_time_live_mechanism",
            "support_decay_all_time_live_mechanism",
            "support_decay_retrace_all_time_live_mechanism",
        )
    }
    return {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": generated_at,
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
        },
        "audit": {
            "mode": "multi_asset_bidirectional_live_audit",
            "run": {
                "run_id": "run-current",
                "profile_fingerprint": "profile-current",
            },
            "execution": {
                "fills": 8,
                "closed_trades": 2,
                "history_run_ids": ["run-compatible", "run-current"],
                "fill_details": [{"trade_id": 1, "operation": "entry", "oid": 101}],
            },
            "portfolio_archive": {
                "performance": {
                    "total": {
                        "closed_trades": 28,
                        "net_pnl_usd": 2.25,
                        "maximum_closed_sequence_drawdown_usd": 1.75,
                    }
                }
            },
            "routing": {"cycles": 10},
            "trade_reflections": {
                "all_time_live": {
                    "history_schema_version": 1,
                    "closed_trades": 28,
                    "performance": {
                        "total": {
                            "closed_trades": 28,
                            "net_pnl_usd": 2.25,
                            "maximum_closed_sequence_drawdown_usd": 1.75,
                        }
                    },
                    "marker": "complete",
                },
                "performance": {
                    "all_time_live": {
                        "total": {"closed_trades": 28},
                        "marker": "complete",
                    }
                },
                "provider_contract_history": {"marker": "complete"},
            },
            "entry_alignment_mechanism": {"marker": "complete"},
            "side_composition": {
                "schema_version": 2,
                "mode": "cohort_separate_side_composition",
                "marker": "complete",
                "contract": {
                    "report_only": True,
                    "execution_authority": "none",
                    "runtime_strategy_changed": False,
                },
            },
            "hulk_entry_quality_challenger": {"marker": "complete"},
            "profit_lock_challenger": {
                "current_profile_mechanism": {"marker": "bounded-current"},
                **all_time_mechanisms,
            },
        },
    }


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _maximum_hold_row(
    *, sequence: int, outcome: str, exit_reason: str | None
) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision_id": "HYPE:99:soft_maximum_hold",
        "lifecycle_id": "HYPE:99",
        "symbol": "HYPE",
        "strategy_id": "hulk_expansion_bidirectional_tuned_v2",
        "side": "long",
        "decision_time_ms": 1_785_628_800_000,
        "opened_at_ms": 1_785_600_000_000,
        "elapsed_ms": 28_800_000,
        "soft_deadline_timestamp_ms": 1_785_628_800_000,
        "hard_deadline_timestamp_ms": 1_785_686_400_000,
        "outcome": outcome,
        "exit_reason": exit_reason,
        "structure_alignment_score": 0.75,
        "structure_alignment_threshold": 0.5,
        "provider_evaluation": {"primary_regime": "TREND_UP"},
        "canonical_evaluation": {"state_5m": "TREND_UP"},
    }
    row = {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": "maximum_hold_decision",
        "observed_at_utc": "2026-08-02T12:00:00+00:00",
        "execution_mode": "live",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "cohort-profile",
        "profile_fingerprint": "cohort-profile-fingerprint",
        "run_fingerprint": "cohort-profile-run",
        "run_id": _RUN_ID,
        "payload": payload,
    }
    return row
