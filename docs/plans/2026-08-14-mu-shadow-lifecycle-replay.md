# MU Shadow Lifecycle Replay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Produce an immutable, report-only, causal lifecycle replay for the seven prospective `xyz:MU` breakout-pressure onsets using the exact shadow decision identity, public venue candles, recorded mark path, official funding, and recorded finite-depth books.

**Architecture:** Add a route-generic HIP-3 replay core that validates and joins frozen decision, candle, mark, funding, and REST-book evidence. Keep parsing, chronological lifecycle simulation, and reporting separate enough to stay below project size limits. Add a thin command that binds immutable local ledgers, fetches only unsigned public candles/funding through injectable boundaries, verifies inputs did not change, and publishes one authority-none JSON report. Reuse existing breakout signals, path-quality, fee evidence, and depth-fill helpers; do not alter v51, observers, routers, or execution code.

**Tech Stack:** Python 3.12, pandas, existing Hyperliquid public-data clients, EventArchive/DuckDB or bounded Parquet reads, pytest, Ruff.

---

## System Contract

- Inputs: exact shadow decision JSONL, exact REST book JSONL, prospective mark archive, public completed 15m `candleSnapshot`, official hourly `fundingHistory`, route-specific fee/latency evidence, and frozen `Hip3BreakoutShadowSpec`.
- Output: immutable JSON with authority `none`, no automatic promotion, no execution client, exact input/generator identities, per-lifecycle evidence, aggregate nominal/stress economics, side breakdown, largest-winner sensitivity, censored-path counts, and limitations.
- Signal identity: reproduce every eligible journal onset and reject extra/missing/side-mismatched computed onsets.
- Entry: first complete recorded depth book received at or after the prospective publication time, within the declared lateness bound.
- Stop: structural signal stop, capped by the route maximum; trigger only from post-entry recorded mark observations. Close at the first complete recorded depth book after the trigger. This is a mark-triggered observed-depth approximation, not a claim about the venue order's historical fill.
- Signal exit: frozen EMA cross evaluated only on completed public candles, then first recorded depth book at or after the decision publication.
- Fallback exit: 24-hour maximum hold; final unresolved/censored rows do not become profitable synthetic closes.
- Funding: exact official hourly events while the position is open, directionally charged using the replayed notional.
- Portfolio semantics: one position per route; overlapping eligible onsets are reported as suppressed while already open, not counted as independent funded trades.
- Technical failure: source mismatch, mutable input, missing exact entry identity, conflicting rows, incomplete required funding, or unresolved mark/book lifecycle remains explicit and cannot produce a promotion-shaped verdict.

### Task 1: Freeze Models and Identity Validation

**Files:**
- Create: `src/hypervector/research/hip3_shadow_lifecycle_models.py`
- Create: `tests/test_hip3_shadow_lifecycle_replay.py`

1. Write failing tests for exact symbol/provider/profile/config identity, finite nonnegative friction, positive notional, 15m-only timeframe, maximum book delay, and 24-hour hold.
2. Run the focused tests and confirm the expected import/contract failures.
3. Implement typed frozen configuration and lifecycle/result models with public docstrings.
4. Re-run focused tests and Ruff.

### Task 2: Parse and Reconcile Prospective Inputs

**Files:**
- Create: `src/hypervector/research/hip3_shadow_lifecycle_inputs.py`
- Modify: `tests/test_hip3_shadow_lifecycle_replay.py`

1. Write failing tests for duplicate/conflicting decisions, future/non-prospective decisions, wrong authority, malformed or crossed books, incomplete ten-level depth, wrong candle source/interval, mark receipt chronology, and incomplete hourly funding.
2. Add parsers that reuse the exact journal/book identity semantics from `hip3_shadow_signal_markouts` and existing funding validation rather than copying permissive alternatives.
3. Build a completed-candle/decision-pressure frame and reject gaps or source mismatches.
4. Recompute the frozen breakout signals and require exact eligible onset time/side parity with the journal.
5. Run focused tests and Ruff.

### Task 3: Implement Causal Lifecycle Simulation

**Files:**
- Create: `src/hypervector/research/hip3_shadow_lifecycle_replay.py`
- Modify: `tests/test_hip3_shadow_lifecycle_replay.py`

1. Write failing tests proving: entry cannot predate publication; pre-entry mark lows cannot stop a trade; post-entry stop triggers do; EMA exit uses the next causal book; maximum hold is secondary; incomplete mark cadence censors; overlapping entries are suppressed; depth insufficiency censors; long/short funding signs are correct; and largest-winner removal is exact.
2. Implement an event-ordered route simulator with one active position and explicit exit precedence: verified mark stop, completed-candle EMA signal, then maximum hold.
3. Use finite-depth VWAP at entry and close; do not invent a fill when the recorded book cannot complete the requested quantity.
4. Produce nominal and stress variants from frozen fee/latency assumptions without changing signal identity.
5. Run focused tests and inspect each failure before continuing.

### Task 4: Add Immutable Report-Only Command

**Files:**
- Create: `scripts/hip3_shadow_lifecycle_replay.py`
- Create: `tests/test_hip3_shadow_lifecycle_replay_script.py`

1. Write failing command tests for no-authority output, exact MU spec binding, distinct paths, no network in tests, incomplete/mutating input rejection, no partial publication, and generator identity.
2. Implement injectable unsigned candle/funding boundaries and bounded local mark loading.
3. Embed canonical candle/funding hashes and lifecycle evidence in the report; verify mutable JSONL prefixes and source files again before publication.
4. Use a fresh immutable output path and print only a compact non-authoritative summary.
5. Run command tests, all relevant HIP-3 tests, Ruff format/check, file/function limits, and `git diff --check`.

### Task 5: Run the Exact MU Replay and Validate the Artifact

**Files:**
- Create: `data/logs/research/xyz_mu_shadow_lifecycle_replay_20260814_v1.json` (ignored research evidence)
- Create or revise: `docs/research-journal/v51-mu-shadow-lifecycle-replay-v1.json`

1. Snapshot decision/book-ledger prefixes and the bounded prospective mark archive.
2. Run the command once for `xyz:MU`; do not rerun silently after a technical failure.
3. Independently verify hashes, seven-onset identity, lifecycle counts, funding, fees, depth completeness, exit reasons, largest-winner sensitivity, and no authority fields.
4. Append the hypothesis revision to the research DuckDB only after evidence hashes match.
5. Report results with confidence, failure modes, and explicit falsifiers. Request live approval only if a later, predeclared evidence standard supports an actual proposal; this task itself must not change live behavior.

## Acceptance Criteria

- Seven existing eligible onset decisions are either reproduced exactly or the replay fails closed.
- Every reported lifecycle has causal entry/exit timestamps and complete recorded depth for the requested size.
- Stop outcomes require complete post-entry mark evidence; unresolved paths remain censored.
- Official funding, measured fee assumptions, and nominal/stress friction are present and source-bound.
- Output contains no execution/promotion authority and changes no live process, config, route, sizing, leverage, or strategy.
- Focused and relevant regression suites pass; all new files are at most 500 lines and functions at most 50 lines.

## Risks and Falsifiers

- Public historical `candleSnapshot` may not reproduce the prospectively observed signal set; any mismatch aborts.
- Recorded activeAssetCtx cadence may leave lifecycle paths unresolved; unresolved paths cannot support an economic conclusion.
- Observed-depth close after a mark trigger may differ from the actual venue stop fill; the report must retain that limitation.
- Seven all-long onsets remain a small, clustered sample even if every lifecycle resolves. Positive PnL would update the hypothesis, not establish deployable edge.
- A negative or winner-concentrated replay would lower MU priority and preserve v51 unchanged.
