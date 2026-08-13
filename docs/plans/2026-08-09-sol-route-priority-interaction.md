# SOL Route Priority Interaction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** Build an immutable, report-only replay comparing the current SOL static-fallback provider order with a predeclared Range-Onset-first order under one shared SOL slot.

**Architecture:** Reuse the existing exact lifecycle adapters and priority-aware shared-account replay. A pure research module will compare exactly two fixed priority arms on development and the already-opened final block; a thin script will load and hash the exact SOL Range Onset, HT-Breakout, and Hulk evidence. The experiment cannot modify a live profile or evict an already-open lifecycle.

**Tech Stack:** Python 3.13, pandas, existing Hypervector replay/adapters, pytest, Ruff, immutable JSON evidence.

---

### Task 1: Freeze the two-arm priority contract

**Files:**
- Create: `tests/test_sol_route_priority_interaction.py`
- Create: `src/hypervector/research/sol_route_priority_interaction.py`

**Step 1: Write the failing simultaneous-conflict test**

Create synthetic `CohortOutcome` rows where HT-Breakout and Range Onset enter
SOL at the same timestamp. Assert that `current_static_priority` accepts
HT-Breakout and `range_first_static_priority` accepts Range Onset.

**Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_sol_route_priority_interaction.py::test_two_arms_change_only_simultaneous_flat_boundary_owner -q
```

Expected: FAIL because the research module does not exist.

**Step 3: Implement the minimal pure comparator**

Add fixed identities:

```python
HULK = "hulk_expansion_bidirectional_tuned_v2"
RANGE = "range_onset_bidirectional_v1"
BREAKOUT = "hype_breakout_onset_bidirectional_v1"
CURRENT_PRIORITY = (BREAKOUT, RANGE, HULK)
RANGE_FIRST_PRIORITY = (RANGE, BREAKOUT, HULK)
```

Implement a typed public function that accepts already-adapted outcomes and
returns both `PrioritizedPortfolioReport` payloads with execution authority
`none`, automatic promotion false, and trial count two.

**Step 4: Run the test to verify it passes**

Run the same focused command. Expected: PASS.

### Task 2: Preserve open-lifecycle and phase boundaries

**Files:**
- Modify: `tests/test_sol_route_priority_interaction.py`
- Modify: `src/hypervector/research/sol_route_priority_interaction.py`

**Step 1: Write failing lifecycle and split tests**

Assert that a later Range Onset signal cannot evict an open HT-Breakout
lifecycle under either arm. Assert that development and opened-final results
are reported separately and the final block is marked descriptive and unused
for selection.

**Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/test_sol_route_priority_interaction.py -q
```

Expected: at least one failure for missing partitioned artifact fields.

**Step 3: Implement the partitioned artifact builder**

Use `partition_cohort_outcomes` with the fixed boundaries:

```text
development end: 2026-05-28T00:00:00Z
opened final start: 2026-05-29T00:00:00Z
opened final end: 2026-07-28T00:00:00Z
```

Report accepted/rejected counts by provider and rejection reason. Keep open
position eviction impossible by relying on `replay_prioritized_outcomes`.

**Step 4: Run the tests to verify they pass**

Run the same file. Expected: PASS.

### Task 3: Load exact venue-matched source lifecycles

**Files:**
- Create: `scripts/sol_route_priority_interaction.py`
- Create: `tests/test_sol_route_priority_interaction_script.py`

**Step 1: Write the failing script contract test**

Assert the parser requires a unique output, the artifact binds every source
hash, uses `$75` notional and `5x` leverage for all three routes, encodes
4.5-bps entry fee identity, and exposes no execution authority.

**Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/test_sol_route_priority_interaction_script.py -q
```

Expected: FAIL because the script does not exist.

**Step 3: Implement the thin immutable runner**

Load:

- the three frozen Hulk tuned-v2 JSON artifacts;
- `data/cache/SOL_1m_365d.parquet`;
- full-year SOL Hyperliquid funding;
- the twelve frozen SOL Range Onset event artifacts.

Adapt Hulk with `adapt_hulk_payloads`, construct exact SOL HT-Breakout
lifecycles using the existing 80-bps/8h/24h-extension replay, and adapt
canonical Range Onset with `adapt_range_event_payloads`. Publish the immutable
JSON only after all validations succeed.

**Step 4: Run the script tests to verify they pass**

Run the same file. Expected: PASS.

### Task 4: Execute and decide

**Files:**
- Create: `data/logs/research/sol_route_priority_interaction_<timestamp>.json`
- Create: `docs/reviews/2026-08-09-sol-route-priority-interaction.md`
- Create or revise: `docs/research-journal/sol-route-priority-interaction-v1.json`

**Step 1: Run the fixed experiment once**

```bash
uv run python scripts/sol_route_priority_interaction.py \
  --out data/logs/research/sol_route_priority_interaction_<timestamp>.json
```

Expected: one immutable report with exactly two arms, separate development and
opened-final results, route attribution, rejection reasons, and no authority.

**Step 2: Review without selecting from the opened final block**

Compare development net, PF, drawdown, accepted paths, displaced paths, both
sides, and result excluding the largest winner. Use the opened final block only
as descriptive contradiction or support.

**Step 3: Append the source-backed journal decision**

Validate exact evidence SHA-256 and byte counts, append through
`research-db-journal-append`, and query the journal head and integrity.

### Task 5: Verify the scoped change

**Files:**
- Verify all files above.

**Step 1: Run focused tests and lint**

```bash
uv run pytest tests/test_sol_route_priority_interaction.py \
  tests/test_sol_route_priority_interaction_script.py \
  tests/test_evidence_selected_portfolio.py -q
uv run ruff check src/hypervector/research/sol_route_priority_interaction.py \
  scripts/sol_route_priority_interaction.py \
  tests/test_sol_route_priority_interaction.py \
  tests/test_sol_route_priority_interaction_script.py
git diff --check -- src/hypervector/research/sol_route_priority_interaction.py \
  scripts/sol_route_priority_interaction.py \
  tests/test_sol_route_priority_interaction.py \
  tests/test_sol_route_priority_interaction_script.py
```

Expected: zero failures or lint/whitespace errors.

**Step 2: Verify engineering limits and live isolation**

Confirm each new Python file is below 500 lines, each function is at most 50
lines, prediction/replay evidence is immutable, and the live ledger still
reports the same v25 run/profile with protected open positions. Do not restart
or mutate the backend.
