# V89 startup history and memory update — September 15, 2026

The installed asset telemetry recovery now streams validated history and retains only the first row plus fill, fee and funding records. It preserves start-time, fresh-ledger and accounting deduplication behavior. Installed code commit: `8c3ee9dd91c131efa6553829fb67e130847526df`; candidate commit: `a27d7c55a4ccaf8e5d59a4579cec99adabe1b4c4`. The strategy configuration and TUI binary are unchanged.

## Findings and limits

The user-run PID 24474 existed at 09:21 UTC and was absent at 09:30 UTC. Its backup manifest matched the supplied receipt, but no new cohort heartbeat or asset row appeared. The cause of its exit remains unverified; terminal output after the backup message is still needed. Direct terminal inspection was unavailable because the computer-use tool blocked Warp access.

A subsequent offline diagnostic successfully initialized all seven asset histories, the shared cohort telemetry and funding cursor against the original 8,204,691,053 ledger bytes. Its 17 local stages took 445.14 seconds (about 7 minutes 25 seconds), excluding backup, SDK creation, engine startup and venue reconciliation. This explains why a backup-complete message can precede a long wait; it does not prove why PID 24474 exited. The diagnostic denied network, subprocesses, credential-file reads and filesystem writes, and the authoritative ledger metadata remained unchanged.

## Validated memory change

The old asset telemetry constructor materialized the complete ledger. The new constructor reuses `SolLiveLedger.read_matching`, which still validates every row before filtering. It retains the first row to preserve ledger freshness and origin time, along with all fill, fee and funding records needed by the existing recovery functions.

| Same real BTC ledger | Previous | Updated |
| --- | ---: | ---: |
| Peak process resident memory | 4.081 GB | 0.283 GB |
| Telemetry recovery time | 17.74 s | 13.74 s |
| Recovered fill identities | 65 | 65 |
| Recovered fill-fee identities | 65 | 65 |
| Recovered funding identities | 124 | 124 |

Every recovered state field was identical; canonical state SHA-256: `b49a0b1cd33c6734e5bcad841b4a267a9b9b3ef964b1d830851a9797905b4ed3`. Peak memory fell 93.08% in this one measured case. This is a startup resource improvement, not evidence of a trading-performance change or the cause of the earlier exit.

A regression first failed on full-history materialization. All 66 targeted candidate checks subsequently passed, including corruption in discarded book rows, malformed accounting identities, empty and book-only histories, accounting deduplication and startup wiring. A 13-test subset passed again from the installed checkout. No strategy, sizing, stop, leverage, asset or financial execution behavior was changed.

## Combined user-run command

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --tui-bin target/release/tui-regime-detector \
  --tui-bin-sha256 eada0b1359d6ea16e84dfb3d35b46538f95b6dd04cc1945f1a64d0614b5c3d9e \
  --startup-timeout-seconds 1800
```

This installed launcher starts the backend, waits for a fresh configuration identity, binds its checkpoint writer to the new run, and opens the TUI. Its maximum startup wait here is 30 minutes; this is a timeout bound, not an expected duration. Quitting this combined TUI stops its owned backend. For a separately managed backend, use the detached `--mode monitor` command in the monitor guide instead. No financial backend was started by this investigation.

## Evidence, decision and rollback

High confidence in the measured recovery equivalence and memory reduction, supported by exact local outputs and the checks above. Changed accounting state, an invalid row being skipped, a source mismatch, or a new initialization failure would require revalidation. Full live startup and operational attachment remain to be observed.

The memory hypothesis is accepted and installed under the existing corrective-update approval. The startup-exit hypothesis remains unresolved. The next investigation is the first fresh user-run startup and its backend log/heartbeat; no repeated historical portfolio replay is required by this telemetry-only delta.

Machine-readable evidence: `/Users/gestas/Prototypes/hypervector/data/logs/research/bidirectional_cohort/v89_release_source_20260914_v1/startup_memory_validation_20260915.json` (SHA-256 `c937dc7a25fe6d2357ae464afd2945699153a49dffff6b101d25381538cb6a00`). The installation receipt and exact patch are in `startup_memory_installation_20260915` beside it. Prior source bytes were preserved, and the reverse patch check passed. Rollback requires the backend to be stopped and the installed source identity verified before manually reversing that exact patch. V19 release/journal bytes remain unchanged; this report records the supplement.
