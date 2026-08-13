# Hypervelocity Minimum Structural Age Challenger Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether requiring five completed one-minute decision rows in the current 5m structural episode before a new entry improves the source-faithful Hypervelocity replay without changing runtime behavior.

**Architecture:** Add one causal, report-only decision transform that masks entry directions during structural episode audit ages zero through four and permits entries from zero-based age five onward. Wire that single parameter into the existing BBWP research replay, preserve the canonical regime and open-position lifecycle, and compare it against the exact hard-BBWP25/recovery-6 authentic-context control. Runtime, TUI, faithful configuration, exit rules, and metalabel authority remain unchanged.

**Tech Stack:** Python 3.13, pandas, pytest, Ruff, checksum-verified Hyperliquid candles/L2/trades/mark/oracle/funding archives.

---

## Frozen hypothesis and evidence boundary

- Candidate: minimum structural episode age five in one-minute decision rows.
- Implementation convention: `regime_age_bars` is zero-based, so rows with age
  `< 5` are blocked and rows with age `>= 5` are allowed. At audit age five,
  five prior one-minute decisions have elapsed in the same structural state.
- The current 5m `state_5m` defines episode identity. A state change, including
  entry into or exit from RANGE, resets age causally.
- Only `entry_direction` may be masked. `primary_regime`, `state_5m`,
  `structural_direction`, reasons, already-open positions, RANGE holds, 8% gross
  margin target, liquidation, fees, funding, and cooldown stay unchanged.
- Control: hard 5m BBWP25 range precedence, 1m BBWP recovery age six,
  300-second maker TTL/cooldown, regime-reset re-entry, one position, 70%
  isolated margin, 40x, $120 initial equity, authentic mark/oracle and settled
  funding.
- Full window: 2026-04-28 00:00 UTC through 2026-07-27 00:00 UTC.
- Source evidence is diagnostic, not a tuning oracle. The pre-registered fact is
  that all 20 creator entries currently aligned with the 5m structural direction
  occurred at episode age five or later. Three early creator reversals already
  disagree with the 5m authority and are not claimed as preserved.
- No adjacent minimum-age sweep is permitted in this experiment.

## Success criteria and falsifiers

- Technical success: deterministic output, checksum-complete evidence, causal
  prefix invariance, and no runtime/config mutation.
- Economic evidence to consider promotion later: fewer liquidations, higher
  final equity, and no worse maximum drawdown than the exact control, while
  preserving all 20 structurally aligned creator entries.
- Reject this candidate if it worsens final equity or drawdown without a
  material liquidation reduction, if it changes canonical regime telemetry, or
  if new creator evidence shows valid aligned entries inside ages one through
  four.
- Even a favorable replay remains report-only until a sealed fresh shadow
  window corroborates it.

### Task 1: Write the causal transform contract

**Files:**
- Create: `tests/test_hypervelocity_minimum_structural_age.py`
- Modify: `src/hypervector/research/hypervelocity_bbwp_precedence.py`

**Step 1: Write the failing tests**

Add tests that call `apply_regime_entry_minimum_age(decisions,
minimum_age_inclusive=5)` and assert:

- zero-based ages `[0, 1, 2, 3, 4]` are blocked;
- zero-based age five and later are allowed;
- a structural state change resets age;
- canonical state and structural direction are unchanged;
- a prefix produces the same rows as the corresponding full-frame prefix;
- zero, booleans, and non-integers fail with an actionable error.

**Step 2: Run the focused test and observe RED**

Run:

```bash
uv run pytest tests/test_hypervelocity_minimum_structural_age.py -q
```

Expected: collection failure because `apply_regime_entry_minimum_age` does not
exist.

**Step 3: Implement the minimum transform**

Add the typed function with this behavior:

```python
age = regime_age_bars(result["state_5m"])
blocked = age.lt(minimum_age_inclusive) & result["entry_direction"].notna()
```

Publish `regime_age_5m_bars` and a distinct
`regime_entry_minimum_age_blocked` audit flag, then mask only
`entry_direction`.

**Step 4: Run the focused test and observe GREEN**

Run the same pytest command and require zero failures.

### Task 2: Wire exactly one report parameter

**Files:**
- Modify: `tests/test_hypervelocity_bbwp_script.py`
- Modify: `scripts/hypervelocity_bbwp_precedence.py`

**Step 1: Write failing command-contract tests**

Add tests for `--event-minimum-regime-age 5`, the candidate suffix
`_regime_age_gte_5`, the new audit count, and mutual exclusion with the existing
maximum-age experiment.

**Step 2: Run the command tests and observe RED**

```bash
uv run pytest tests/test_hypervelocity_bbwp_script.py -q
```

Expected: parser or transform failure because the option is absent.

**Step 3: Add the minimal report-only wiring**

- Add the parser option.
- Apply it after the already-frozen recovery transform.
- Reject simultaneous minimum and maximum regime ages.
- Append one serial-screen row and the `_regime_age_gte_5` identity.
- Count `regime_entry_minimum_age_blocked` separately from the older late-age
  experiment.

**Step 4: Keep files within project limits**

If the script would exceed 500 lines, extract its already-tested creator-source
loading/evidence helpers into
`src/hypervector/research/hypervelocity_source_inputs.py`. Preserve behavior
under the existing supplemental-position tests; do not add another replay
implementation.

**Step 5: Run both focused test files and Ruff**

```bash
uv run pytest tests/test_hypervelocity_minimum_structural_age.py \
  tests/test_hypervelocity_bbwp_script.py -q
uv run ruff check scripts/hypervelocity_bbwp_precedence.py \
  src/hypervector/research/hypervelocity_bbwp_precedence.py \
  src/hypervector/research/hypervelocity_source_inputs.py \
  tests/test_hypervelocity_minimum_structural_age.py \
  tests/test_hypervelocity_bbwp_script.py
```

### Task 3: Run the frozen comparison

**Files:**
- Create: `data/logs/research/hypervelocity_minimum_structural_age5_20260728.json`

**Step 1: Run the complete venue-matched replay**

Use:

- bars: `data/cache/BTC_1m_90d.parquet`;
- positions: `docs/external/manual_positions_unified_2026-07-09_to_today_20260724_150845.csv`;
- supplemental positions: `docs/external/creator_screenshot_positions_20260727.csv`;
- config: `configs/hypervelocity_faithful.toml`;
- prices: `data/cache/vendor/0xarchive/hyperliquid/BTC/20260428T000000000000Z_20260727T000000000000Z_prices/prices.parquet`;
- funding: `data/cache/vendor/hyperliquid/BTC/20260428T000000000000Z_20260727T000000000000Z_funding/funding.parquet`.

Pass hard BBWP base, recovery age six, minimum regime age five, $120 equity,
and the frozen UTC bounds. Complete the run regardless of interim performance;
performance is a measured result, not an abort gate.

**Step 2: Compare exact outcomes**

Report submissions, fills, targets, liquidations, fees, funding, final equity,
maximum drawdown, candidate-vs-control lifecycle substitutions, blocked-entry
count, creator-direction alignment, and source episode ages.

### Task 4: Integrate the newest creator evidence

**Files:**
- Modify or create a normalized creator evidence CSV under `docs/external/`
- Modify: `docs/reviews/2026-07-27-creator-screenshot-forward-validation.md`
- Modify if material: `HANDOFF.md`

1. Inventory files by timestamp and checksum without assuming every image is a
   new trade.
2. Transcribe only visible side, entry, exit/mark, timestamps, outcome, and
   status. Preserve unknown fields as unknown.
3. Deduplicate by source identity and trade evidence, retaining provenance.
4. Compare each causally resolvable entry with 1m/5m/15m state, structural
   episode age, entry eligibility, and replay outcome.
5. Re-evaluate the candidate against the expanded creator set; explicitly note
   screenshot-selection bias and any missing losing trades.

### Task 5: Full verification and decision record

1. Run the complete non-network Python suite, Rust TUI suite, focused Ruff,
   format check, and `git diff --check`.
2. Recompute the faithful config SHA-256 and require
   `801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`.
3. Verify ML remains observe-only and runtime/TUI strategy behavior is
   unchanged.
4. Record promote/reject/hold with confidence, failure modes, and the evidence
   that would falsify the decision.
5. Do not commit or push unless the user explicitly requests it.

## Measured result

The complete 2,160-hour replay rejected the exact age-five candidate. Both
reports used the same verified public L2/trade archive, 127,814 authentic
mark/oracle observations, all 2,160 funding rows, $120 initial equity, and
unchanged execution/risk parameters.

| Candidate | Submissions | Fills | Targets | Liquidations | Final equity | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Exact hard-BBWP25/recovery-6 control | 513 | 445 | 402 | 43 | $20.2578 | -99.4317% |
| Minimum hard-state age 5 | 475 | 406 | 361 | 45 | $0.9405 | -99.9381% |

The candidate blocked 4,609 otherwise directional decision rows. Only 40
resolved signal identities remained shared with the control: 33 retained
target status and seven retained liquidation status. The candidate removed 405
control resolved identities and introduced 366 different ones, demonstrating
large path substitution rather than a narrow delay.

Completed-bar source reconciliation also corrected the pre-screen assumption.
For the 22 deduplicated creator rows with visible exits, recovery-6 matched
12 directions and the candidate matched ten. It newly blocked two matched Jul
24 shorts: 12:47:05 UTC at post-BBWP hard-state age two and 14:00:45 UTC at age
zero. The first had canonical 5m age 212, proving that BBWP RANGE precedence can
reset the challenger episode even while the underlying canonical trend is
mature. Across the broader 35-entry source set, exact alignment fell from
17/35 to 13/35.

The original claim that all aligned source entries were at candidate age five
or later was therefore measured on a mismatched episode surface and is
withdrawn. Runtime, TUI, faithful configuration, 8% target, and ML observe-only
policy remain unchanged. Artifact:
`data/logs/research/hypervelocity_minimum_structural_age5_20260728.json`,
SHA-256
`b9394e7e4ce16de2d4e3a5aff9cef3f40ff56959e5938e02b35796921109c90b`.

Confidence is high for rejecting this exact candidate on the inspected path.
Private queue position and 21 mark gaps over 120 seconds remain replay failure
modes, but neither would explain the candidate's two additional modeled
liquidations, 95% lower terminal equity than control, worse drawdown, and worse
creator alignment simultaneously. A sealed new venue-matched window showing a
consistent liquidation reduction without lost source-compatible entries would
update this decision.

Fresh verification passed 996 non-network Python tests with four deselected
and 31 warnings, plus all 33 Rust TUI integration tests. Task-scoped Ruff and
format checks, Cargo formatting, diff hygiene, file-size checks, artifact
schema assertions, CLI fail-closed status, and configuration hashing passed.
