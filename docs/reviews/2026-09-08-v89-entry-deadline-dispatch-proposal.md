# V89 entry deadline: validated candidate and deployment proposal

Recommendation: approve the technical candidate at commit
`3d204863af40536187df96f161f4874d9fa42166` for a future user-run deployment at a
verified flat, order-free boundary. Confidence is high for the tested local
execution and recovery contracts. Live acceptance and financial benefit remain
unproven. No activation or trading-process restart was performed.

Why now: the preserved baseline allows a signal admitted at 29 seconds to be
submitted after a two-second venue-flat read, beyond its existing 30-second
limit. A 60-second limit has the same defect. The earlier four-entry live audit
found every acknowledgement inside its limit, so this is a reproduced technical
defect without an established live breach rate or attributed capital loss.

Evidence reviewed: the frozen deadline reproduction and four-entry native audit
in `2026-09-08-v89-entry-deadline-engine-gap.md`; the candidate's runner, engine,
order submission, IOC adapters, restart reader and reporting pipeline; installed
Hyperliquid SDK 0.24.0 source; deterministic failure injection; and cross-version
rollback replay. Economic prospective outcomes remain sealed under their
existing protocol. No strategy thresholds were tuned for this correction.

Observed problem: blocking work after admission can consume remaining headroom.
The original routing timestamp describes admission rather than the final local
SDK call. A naive late rejection after persisting an order intent would also
leave an apparently unresolved entry on restart.

Applicable market regime: technical applicability spans every configured regime
and both entry directions. The fake metadata tests cover BTC, ETH, SOL, HYPE,
xyz:SPCX, xyz:SNDK and xyz:BRENTOIL, plus the standalone SOL adapter. This does
not requalify their strategy edge, sizing, leverage limits or liquidity.

Proposed live change: install exactly the 19 source files listed in
`source_manifest.json`, relative to base commit `3b31a00`. Carry each route's
existing deadline through entry preparation, recheck after durable intent
persistence and after adapter metadata/lot preparation, and record the actual
named boundary. Expired unsent entries receive a durable client-ID-bound
`entry_not_submitted` record and return to FLAT. Other actions continue. Orders
already dispatched retain their original-ID recovery and protection path even
if the response arrives after the deadline. The reporting reader distinguishes
legacy/admission, adapter, SDK and mixed evidence.

Expected upside: restore the configured local freshness contract and make the
recorded timestamps and restart ownership explicit. No increase in trade
frequency, win probability or expected return is established. Some signals
previously submitted late will now be withheld under their existing limits.

Alternatives considered:

| Option | Benefit | Limitation |
| --- | --- | --- |
| Keep current version | No deployment transition | Retains the reproduced gap and admission-stage reporting |
| Add only an engine admission check | Smaller change | Does not cover subsequent persistence or adapter delays |
| Candidate 3d20486 | Covers the tested blocking stages and durable recovery | Requires deployment acceptance and backward-compatible rollback |

Main risks and failure modes: the final check precedes SDK signing, process
scheduling, HTTP transmission and venue receipt. It is not a hard real-time
venue-arrival guarantee. The installed SDK skips its midpoint lookup when given
the adapters' validated explicit price; an SDK change can alter that assumption.
A failed marker write remains an explicit technical failure with pending intent;
it cannot produce a success-shaped FLAT state. Corrupt or contradictory markers
are rejected. An older reader cannot resolve the new marker, even after a final
FLAT state record, so a complete blind rollback is unsuitable after new history.

Validation completed:

- 454 passing tests across 43 modules in the candidate checkout and again from
  frozen source in a temporary workspace.
- 229/229 changed executable lines and 72/72 changed branches covered. The new
  deadline module has 100% statement and branch coverage. Aggregate coverage of
  the 19 touched source modules is about 90% of statements and 87% including
  branches; unrelated legacy branches remain uncovered.
- Inclusive exact limits; already stale, provider, reconciliation retry,
  persistence and adapter-preparation expiry; later route and selected exit
  continuation; subsequent fresh entry; no-fill versus unsent distinction;
  response-loss recovery without duplication; and raw ACK/routing clock parity.
- Removing only the final check in an isolated fake-exchange test process caused
  all 16 overdue adapter variants to fail as expected. No live guard was changed.
- Both expiry locations, before and after the final FLAT write, recovered under
  the 1,336-file baseline source with exactly one retained compatibility file:
  `src/hypervector/live/sol_order_restart.py`. All four restored FLAT without
  client-ID lookup, entry submission or close submission. Venue operations were
  fakes and network connection attempts were denied.
- Ruff, import ordering, formatting and annotation checks passed. New functions
  and files meet size limits. Existing oversized test code and the untouched
  post-only batch function were verified as pre-existing exceptions.

Validation still required: explicit approval; a fresh source/configuration and
venue-ownership check; the normal durable prestart backup; and supervised
acceptance after a user-run restart. Restart the checkpoint reporter separately
so its process loads the new reporting code. Verify each process's source/run
identity, checkpoint freshness, phase labels, absence of execution faults,
unchanged provider scope and exact position/stop ownership. The existing
updated TUI can consume the checkpoint; no Rust source or executable changes
are included. Its separately stale HIP-3 research feed is not repaired here.

Success metrics: no local SDK-dispatch check above its configured limit; exact
inclusive boundaries; durable and attributable stale non-actions; no stale
intent resurrection; no duplicate recovery dispatch; unaffected selected exits
and protection; and source-consistent telemetry. A new entry is not required
merely to manufacture an acceptance trade.

Failure / rollback triggers: a mismatched source or profile, unexpected ownership,
duplicate dispatch, incorrectly resolved intent, unprotected position, corrupt
marker, or timing label that contradicts its boundary invalidates acceptance.
Preserve all ledgers and evidence. At an approved flat, order-free transition,
restore prior source files from `prior_files` but retain the candidate restart
reader if new markers exist. Retaining that reader unconditionally is the tested
compatible rollback. Do not delete or replace post-deployment history with the
prestart backup. Open-position rollback requires separate recovery validation;
the four rollback probes establish flat recovery only.

Confidence level: high for these deterministic local contracts, conditional on
the pinned source and SDK. A different execution path, altered source hash,
failed archived replay, incorrect clock reconstruction, or live boundary/stop
mismatch would falsify or update this assessment. No confidence level for
improved financial performance is supported by these tests.

Explicit approval requested: approval of this exact technical change for a
future user-run live deployment. The research brief's Human control clause
requires approval before changing live execution or deployment configuration.
The earlier mapped-reporting proposal remains separate and is not included.

Evidence bundle:
`data/logs/research/bidirectional_cohort/v89_entry_deadline_candidate_20260908_v1/`.
It contains the patch, candidate/prior copies, source and provider archives,
per-file hashes, test logs, coverage, mutation control, rollback fixtures and
cross-version results. The first portable replay exposed the required adjacent
backtest-lab source dependency; its 530 Python files are now pinned separately,
and the complete archived replay passes. The failed packaging and intermediate
regression records remain available. Nothing in this bundle grants execution
authority or establishes completion of the broader research mandate.
