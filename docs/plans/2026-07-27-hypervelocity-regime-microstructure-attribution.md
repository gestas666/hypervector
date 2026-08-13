# Hypervelocity Regime and Microstructure Attribution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine, without changing runtime trading behavior, whether causal regime age, 5-minute structure proximity, BBWP compression recency, 15-minute context, or Hyperliquid L2 pressure distinguishes successful Hypervelocity trades from liquidations.

**Architecture:** Build a research-only point-in-time annotation layer over the existing verified 0xArchive replay. Bar annotations are calculated from completed bars only. Book annotations use only snapshots at or before each decision timestamp and preserve missing evidence as missing. A separate attribution report joins these annotations to complete maker-replay lifecycles and reports outcome slices without filtering trials.

**Tech Stack:** Python 3.11+, pandas, existing Hypervector regime classifier, verified 0xArchive bundles, pytest, Ruff/mypy-compatible type hints.

---

## Frozen Runtime Contract

- Keep the 8% strategy target unchanged.
- Keep 70% portfolio allocation, isolated margin, and 40x BTC leverage unchanged.
- Keep Hypervelocity orderbook pressure annotation-only; it must not authorize, reject, size, route, or exit a trade.
- Keep the metalabel in `observe` with `may_filter=false` and `may_scale=false`.
- Do not promote a candidate runtime config from this analysis.
- Retain every lifecycle, including expired, canceled, unresolved, and missing-book rows.

## Task 1: Define Causal Annotation Contracts

**Files:**
- Create: `src/hypervector/research/hypervelocity_attribution.py`
- Create: `tests/test_hypervelocity_attribution.py`

1. Write failing tests proving regime age resets on state change and advances without future data.
2. Write failing tests for prior completed 5-minute rolling support/resistance distance; the current 5-minute bar must not enter its own reference window.
3. Write failing tests for BBWP compression recency and explicit missing warm-up values.
4. Implement the smallest typed functions that satisfy those contracts.
5. Run `uv run pytest tests/test_hypervelocity_attribution.py -q`.

## Task 2: Add Point-in-Time Hyperliquid Book Pressure

**Files:**
- Modify: `src/hypervector/research/hypervelocity_attribution.py`
- Modify: `tests/test_hypervelocity_attribution.py`

1. Write failing tests requiring backward-only snapshot selection and a maximum evidence-age check.
2. Write failing tests for five-level and twenty-level order pressure, spread, and microprice displacement.
3. Preserve unavailable or stale book evidence as null rather than a neutral zero.
4. Add a trailing causal pressure summary whose window contains no snapshot after the decision time.
5. Run the focused tests.

## Task 3: Join Complete Replay Lifecycles and Slice Outcomes

**Files:**
- Modify: `src/hypervector/research/hypervelocity_attribution.py`
- Modify: `tests/test_hypervelocity_attribution.py`

1. Write failing tests that retain all lifecycle statuses and missing annotations.
2. Join annotations by signal timestamp, not outcome timestamp.
3. Report targets and liquidations separately by direction, regime-age bucket, 5-minute structure-distance bucket, BBWP-recency bucket, 15-minute alignment, and pressure alignment.
4. Include row counts and missing counts in every reported dimension so sparse evidence cannot look conclusive.
5. Do not compute or expose a pass/fail promotion gate.

## Task 4: Add a Reproducible Offline Command

**Files:**
- Create: `scripts/hypervelocity_regime_attribution.py`
- Modify: `tests/test_hypervelocity_attribution.py`

1. Add a typed CLI accepting the existing archive comparison JSON, verified archive root, bars, decisions, and output path.
2. Fail explicitly on archive identity/checksum errors, timestamp regressions, missing required columns, or forward-looking joins.
3. Write JSON atomically and include source hashes, config fingerprint, analysis bounds, sample counts, and limitations.
4. Add a `--help` smoke test and deterministic small-fixture report test.

## Task 5: Run the 90-Day Attribution

**Files:**
- Create: `data/logs/research/hypervelocity_regime_attribution_20260727.json`

1. Reuse the exact trade-through candidate/report and verified April 28–July 27 archive inputs.
2. Produce the full causal attribution report without changing any runtime config.
3. Compare target/liquidation frequencies, especially late shorts, against fresh entries and book-pressure alignment.
4. Treat small cells as exploratory and report them without extrapolating certainty.

## Task 6: Verification and Decision Record

**Files:**
- Modify: `docs/plans/2026-07-27-hypervelocity-regime-microstructure-attribution.md`

1. Run focused tests and lint/type checks on new files.
2. Run `uv run pytest tests/ -q -m "not network"`.
3. Run `cargo test -p hypervector-tui` because the backend/TUI contract must remain intact even though no TUI code should change.
4. Verify the faithful runtime config still reports metalabel observe and compare its hash before/after.
5. Record measured results, limitations, confidence, and the evidence that would falsify each recommendation.

## Acceptance Criteria

- No production strategy, regime gate, sizing, leverage, target, or metalabel policy changes.
- All joins are demonstrably point-in-time and backward-only.
- Orderbook evidence comes from checksum-verified Hyperliquid native L2 bundles.
- Missing or stale evidence remains visible as missing.
- The report accounts for all replay lifecycles and states its denominator for every slice.
- Full non-network Python and Rust test suites pass.

## Rollback

The implementation is additive and research-only. Rollback consists of removing the new research module, script, tests, plan, and generated report. Runtime configuration and backend behavior require no rollback because they are not modified.

## Execution Note

The user explicitly approved continuing in this session, so implementation follows immediately. Git commit/push is deferred because this request did not authorize a new commit.

## Measured Result

- Completed artifacts: `data/logs/research/hypervelocity_regime_attribution_20260727.json` for the prior EMA-only archive winner and `data/logs/research/hypervelocity_regime_attribution_bbwp_full_20260727.json` for the faithful full-BBWP runtime configuration.
- Source replay: EMA21/55-only, public trade-through, 339 complete lifecycles: 244 targets, 40 liquidations, and 55 expirations.
- Native L2 coverage: 336/339 decision timestamps; maximum accepted snapshot age 541 ms. The remaining three rows stay null rather than receiving neutral defaults.
- A regression test exposed and fixed a one-minute availability error: replay `signal_time_utc` is the time a completed decision bar becomes observable, so bar annotations are shifted forward one minute before joining. The final artifact was regenerated after this correction.
- Late behavior is direction-specific. Late longs resolved 10 targets/1 liquidation; late shorts resolved 2 targets/6 liquidations. Compared with earlier shorts, the late-short liquidation odds ratio is 19.11 (two-sided Fisher exact p=0.000295). This is post-hoc evidence from only eight late shorts.
- BBWP compression recency of 6–30 bars resolved 102 targets/9 liquidations (91.89% target rate) versus 142/31 outside that bucket (Fisher p=0.0229, unadjusted). This is an annotation-only challenger and is not sufficient for promotion after multiple comparisons.
- Raw displayed L2 pressure did not show positive gating evidence. Direction-aligned pressure resolved 125 targets/25 liquidations; opposed pressure resolved 118/13 (Fisher p=0.1166). Pressure remains telemetry and execution evidence only.
- Prior 5-minute structure proximity below 25 bps resolved 8/8 targets, but the sample is too small to justify a gate (Fisher p=0.606 versus farther entries).
- Fifteen-minute context alignment resolved 101 targets/11 liquidations (90.18% target rate) versus 143/29 otherwise (Fisher p=0.1166). It remains non-veto context.
- A full event replay of a report-only `no late shorts after 15 state bars` challenger improved final equity from $8.84 to $28.26, liquidations from 40 to 37, and maximum drawdown from -99.95% to -99.85%, but still lost about 99.7% of starting equity. This falsified the rule as a sufficient fix; it was not promoted.
- Faithful config SHA-256 remained `801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`, with metalabel `mode=observe`, `may_filter=false`, `may_scale=false`, and runtime metalabel mode `observe`.
- The active full-BBWP result independently confirmed the same relationships: 247 targets/41 liquidations overall; late shorts 3/6 versus earlier shorts 122/20 (odds ratio 12.20, p=0.000889); 6–30-bar BBWP recency 104/10 versus 143/31 outside; aligned L2 pressure 128/25 versus opposed pressure 118/14. Its existing full trade-through result ended at $6.54 with -99.96% maximum drawdown, so no positive slice was treated as sufficient strategy repair.

## Decision

- Do not add a Hypervelocity orderbook-pressure gate from this evidence.
- Do not promote the late-short challenger.
- Keep the 8% target and existing runtime contract unchanged.
- Carry BBWP recency and late-short age forward as predeclared annotation-only challengers for a fresh venue-matched shadow window. A materially larger out-of-sample sample that preserves the direction-specific effect would update this decision.
