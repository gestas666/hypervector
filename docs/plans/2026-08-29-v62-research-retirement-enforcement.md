# V62 Local-Replay Research and Retirement Enforcement Plan

> Status: approved for research implementation only. Live execution remains
> fail-closed pending an exact replacement and change-approval record.

## Execution record

The planned V62 preregistration artifact was intentionally not published. The
HYPE `a60_floor15_trail30` candidate had already been selected after inspecting
two current-profile lifecycles, so creating a dated preregistration afterward
would misrepresent the evidence chronology. Its exact alignment replay is
therefore classified as development-only; it cannot satisfy prospective live
promotion evidence even if its metrics pass. In the observed replay it failed
the development criteria as well.

The optional append-only cohort-ledger refresh did not complete within a
60-minute validation boundary and was terminated with no execution authority.
A subsequent database status check passed, but nine sources remain pending by
1,741,413,771 bytes. The V62 replay does not claim those unimported rows: it is
bound instead to the separate local candle, funding, 0xArchive L2-audit, and
public-trade research artifacts listed in its immutable source evidence.

## Goal

Build V62 as an execution-incapable research revision, use the indexed local
0xArchive plus locally captured order-book and public-trade data for causal
replay, and enforce that a changed live profile cannot start unless every
retired execution scope has a named replacement and the exact transition has
explicit operator approval.

## Traceable requirements

- `SRS_V62_RESEARCH_ONLY`: Every V62 experiment and generated report declares
  `execution_authority = none` and cannot construct a live execution client.
- `SRS_V62_LOCAL_REPLAY`: Candidate evidence is source-bound to local immutable
  inputs with hashes, row counts, time bounds, symbol coverage, and documented
  gaps. No network fetch is part of the replay.
- `SRS_V62_CAUSALITY`: Features use information published no later than the
  decision timestamp; fills use later book/trade events and include fees,
  funding when applicable, slippage, latency sensitivity, and censoring.
- `SRS_V62_NO_IMPLICIT_GATES`: Performance and sample-size results are reported
  trial outcomes. They do not abort a trial or alter the charter's ungated
  execution rule.
- `SRS_V62_CHANGE_APPROVAL`: A changed live profile requires an immutable
  approval document bound to the prior and candidate profile fingerprints.
  Research approval and live approval are distinct states.
- `SRS_V62_RETIREMENT_LINEAGE`: Every removed
  `strategy_id | symbol | side` scope maps one-to-one to a named candidate scope
  with the same symbol and side. Missing, duplicate, stale, or unapproved
  mappings fail closed before execution clients are constructed.
- `SRS_V62_REPLACEMENT_EVIDENCE`: Each replacement records source-bound
  recommendation evidence and a rollback profile. Evidence hashes and rollback
  identity must verify from disk.
- `SRS_V62_LIVE_BOUNDARY`: Live promotion additionally requires a fresh public
  preflight, flat/order-free reconciliation, a completed prior transition
  drain, one backend, no STOP sentinel, and the existing explicit
  `--enabled --i-accept-live-risk` flags.

## Known facts and assumptions

- V61 is stopped and its immutable audit reports four closed losing
  lifecycles. Its execution path accepted entries and stops without submission
  faults, so strategy performance and retirement governance are separate from
  execution correctness.
- The research database currently indexes over 132 million canonical book
  snapshots and 226 million canonical public trades from local archives.
- Existing V62 ETH, BRENTOIL, and state-dependent exit challengers did not pass
  their frozen promotion criteria. They remain rejected controls, not live
  candidates.
- HYPE's route-specific `a60_floor15_trail30` exit is the strongest known
  counterfactual, but its current closed-lifecycle sample is too small to call
  validated without event-level replay and prospective evidence.
- The active worktree contains extensive user-owned V51-V61 changes. V62 work
  will use isolated new modules and files where practical and will not commit,
  revert, or amend unrelated work.

## Task 1: Freeze local data and control identity

**Files:**

- Read: `data/research/market.duckdb`
- Read: `data/research/hip3_market.duckdb`
- Read: `data/research/live_event_research.duckdb`
- Read: `configs/multi_asset_growth_first_5000_eight_asset_sndk_exit_preserved_candidate_v61.toml`
- Create: `docs/research-journal/v62-local-replay-preregistration-20260829-v1.json`

1. Complete the append-only local cohort-ledger import and require prefix
   validation to pass.
2. Record database file hashes or immutable bundle fingerprints, table row
   counts, per-symbol book/trade bounds, duplicate counts, and material gaps.
3. Freeze V61 provider, symbol, side, sizing, entry, stop, target, profit-lock,
   and hold contracts.
4. Freeze candidate families and evaluation rules before reading results.
5. Mark missing trades, missing depth, ambiguous timestamps, and incomplete
   lifecycles as censored rather than profitable or losing synthetic fills.

## Task 2: Implement approval and retirement lineage with TDD

**Files:**

- Create: `tests/test_cohort_profile_change_approval.py`
- Create: `src/hypervector/live/cohort_profile_change_approval.py`

1. Write failing tests for unchanged-profile restart, changed profile without
   approval, research-only approval, stale fingerprints, unverified evidence,
   missing rollback, missing retirement, duplicate retirement, non-added
   replacement, and symbol/side coverage drift.
2. Run the focused tests and preserve the expected missing-module failure.
3. Implement strict typed parsing and validation. Do not infer approval from a
   recommendation, prior standing approval, filename, or profile version.
4. Return sanitized transition evidence with `execution_authority = none`; the
   validator authorizes profile selection only, never order submission.

## Task 3: Enforce before live-client construction

**Files:**

- Modify: `src/hypervector/live/multi_asset_live_config.py`
- Modify: `src/hypervector/live/multi_asset_live_profile_values.py`
- Modify: `src/hypervector/live/cohort_prestart_backup.py`
- Modify: `scripts/multi_asset_bidirectional_live.py`
- Modify: `scripts/multi_asset_bidirectional_preflight.py`
- Test: corresponding focused config, backup, live-start, and preflight tests

1. Add an optional transition-approval source to the candidate profile and its
   fingerprint.
2. Preserve that approval file in the immutable pre-start backup.
3. Compare the verified previous profile with the candidate after backup and
   before adapters or execution clients are created.
4. Require exact live approval for every changed profile and exact replacement
   lineage for every removed execution scope.
5. Project the same result in public preflight so a blocked transition is
   observable before an armed command is attempted.

## Task 4: Run V62 local event-level research

**Files:**

- Reuse existing route-specific replay libraries and immutable journals.
- Create focused V62 replay scripts/tests only where the existing interfaces
  cannot express local book/trade execution.
- Create immutable results under
  `data/logs/research/bidirectional_cohort/` and dispositions under
  `docs/research-journal/`.

1. Reproduce V61 control lifecycles from frozen entry events.
2. Evaluate route-specific exit repairs, beginning with HYPE
   `a60_floor15_trail30`; do not apply it globally.
3. Use next-available causal local book state for executable price and local
   trades for touch/queue evidence where both exist.
4. Run chronological walk-forward partitions, realistic nominal and stressed
   costs, latency sensitivity, largest-winner removal, and per-route sample
   reporting.
5. Keep rejected families rejected unless a materially distinct preregistered
   hypothesis and new untouched evidence satisfy their reopen condition.

## Task 5: Publish disposition and conditional candidate

**Files:**

- Create: `docs/research-journal/v62-local-replay-disposition-20260829-v1.json`
- Conditional create: `configs/multi_asset_growth_first_5000_eight_asset_local_replay_candidate_v62.toml`
- Conditional create: exact transition-approval template with status
  `pending_operator_approval`
- Conditional test: `tests/test_v62_local_replay_candidate_config.py`

1. Report all trials, including rejected, inconclusive, and censored results.
2. If no challenger passes, retain V61 as the rollback identity and leave
   affected routes suspended or `retirement_proposed`; do not label them
   retired.
3. If a challenger passes, create a candidate changing only validated scopes,
   generate replacement lineage, and leave live approval pending.
4. Request exact operator approval naming every replacement and fix before the
   approval status can become `approved_for_live_transition`.

## Task 6: Verification and conditional live transition

1. Run focused red/green tests at each implementation boundary.
2. Run Ruff on changed Python files, full non-network Python tests, Rust TUI
   tests, and `hypervector status`.
3. Re-run immutable report hashes and confirm reproducibility.
4. Run execution-incapable public preflight and require a current checkpoint,
   profile match, flat/order-free venue state, ledger reconciliation, sizing
   readiness, and approved retirement/change lineage.
5. Preserve V61 config, ledgers, and implementation backup as rollback inputs.
6. Only after the exact approval is recorded, remove the STOP sentinel as a
   deliberate transition step and invoke the live command with both arming
   flags.
7. Verify one backend, one run ID, candidate fingerprint, fresh heartbeat,
   protective orders, ledger writes, and TUI parity. Stop immediately on a
   mismatch.

## Failure modes and falsifiers

- Archive/index prefix mismatch or unknown source identity invalidates the
  affected replay.
- Insufficient independent lifecycles, nonpositive stressed validation,
  largest-winner dependence, or worse drawdown rejects promotion; it does not
  prove the incumbent is profitable.
- A missing trade tape may permit BBO sensitivity analysis but cannot prove a
  trade-through or queue fill.
- Approval fingerprint drift, evidence hash drift, an unapproved fix, or any
  removed scope without an added same-symbol/same-side replacement blocks live
  startup.
- Open positions/orders, a stale checkpoint, missing protective stops, STOP
  sentinel ambiguity, or backend multiplicity blocks cutover.

## Trade-offs

- Strict replacement lineage can intentionally prevent side containment that
  removes losing authority without a replacement. This matches the current
  operator rule but may delay loss containment; suspension remains available
  without declaring final retirement.
- Event-level replay is more credible than candle-only counterfactuals but can
  still misstate queue priority. Stressed marketable execution and prospective
  shadow validation bound that uncertainty.
- Retaining V61 while evidence accumulates avoids unsupported drift but does
  not claim V61 has positive expectancy. The backend remains stopped during
  this research phase.
