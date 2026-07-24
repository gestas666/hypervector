# Read-Only Assessment — Bugs, Profitability Optimizations, Regime Detector Fidelity

**Date:** 2026-07-24
**Scope:** `src/hypervector` (strategies, sweep/backtest engine, regime module, data pipeline, ML metalabel path)
**Method:** Full source review; two engine-level claims verified empirically against installed `vectorbt==1.1.0` (synthetic 10-bar probe).
**No files were modified during the assessment.**

**Scope discipline:** hypervector is a research platform — the goal is to see everything and let results speak. This report is therefore limited to code bugs, logic bugs, and measurement-fidelity defects. It proposes **no new gating, capital-safety limits, or restrictiveness**. Where a threshold appears in a proposal, the intent is: expose it as a parameter and measure it with the evaluator — never enforce it silently. Existing *silent* gates already baked into the code are flagged (§3.1) because they hide results.

---

## 1. Broken logic / bugs

### 1.1 Backtest engine (these poison every reported metric)

| # | Bug | Where | Impact |
|---|-----|-------|--------|
| B1 | **Funding drag is never applied.** Gate is `if apply_costs and cost.funding_rate_8h:` but every HL preset sets `funding_rate_1h` and leaves `funding_rate_8h=None` → falsy → `_estimate_funding` is dead code | `sweep/metrics.py:161` vs `sweep/costs.py` presets | All research PnL overstated; worst for long-hold trend strategies. Gate should test `funding_rate_1h` |
| B2 | **Leverage is a silent no-op.** Verified: `size=5.0, size_type="percent"` fills identically to `size=1.0` (capped at 100% cash). Autotune's `leverage` categorical [1,2,3,5], `RiskConfig.max_size_frac`, and `backtest --leverage` do nothing above 1x | `sweep/metrics.py` (`size_type="percent"`), `sweep/sizing.py` | Exported `best_exit_cfg.leverage` is fiction; live parity risk if the live engine honors it |
| B3 | **Same-bar close fills.** Verified: entry signal on the 00:02 bar fills at the 00:02 close, the same close the signal was computed from | `vbt.Portfolio.from_signals` call in `compute_trial_metrics` | Optimistic for everything; materially inflates 1m mean-reversion (impulse_1m "close stretched below EMA" is filled at that stretched close). No next-bar-open execution anywhere |
| B4 | **Sharpe annualization ignores timeframe.** `freq="1min"` default and never passed by autotune / `cmd_backtest` / portfolio, while autotune default timeframe is `5m` | `sweep/metrics.py`, `sweep/autotune.py`, `cli.py cmd_backtest` | 5m Sharpe inflated ~sqrt(5)≈2.2x; boards across timeframes not comparable |
| B5 | **Trail mode runs two stop engines and one is stateful-buggy.** Mode `trail` sets vbt `sl_stop + sl_trail=True` AND ORs in custom `_trail_exits`; `_trail_exits` ignores signal/barrier exits, so after a signal exit `in_pos` stays True → next entry never re-arms, stale extreme/stop → wrong exits | `sweep/metrics.py` + `sweep/exits.py:_trail_exits` | Trail backtests unreliable |
| B6 | **Autotune selects the "best" by a different criterion than it optimizes.** Trials are appended to `trials_log` *before* the trades<10 / dd>25 penalty returns, then final pick is `sort by raw sharpe`. A degenerate 3-trade config the optimizer penalized can still be exported as best | `sweep/autotune.py evaluate_config` + post-loop sort | Overfit/degenerate exports |
| B7 | **Autotune never tunes impulse_1m / oi_divergence / funding_momentum entry params.** Objective builds params only for names matching `crown` / `pine` / `trend_ride`; registry `param_grid` is ignored → those strategies get empty `params` (exit-only tuning), silently | `sweep/autotune.py objective` | "Autotuned" results for the new strategy are not tuned |
| B8 | `except Exception: return -999.0` swallows every error (typo'd param, data issue) with no logging | `sweep/autotune.py` | Silent failure mode; combined with B2/B7 hides real problems |
| B9 | Optuna suggests `sl_pct` but `evaluate_config` never passes it into `ExitConfig` → `fixed_rr` mode always uses default 1% stop; dead search dimension | `sweep/autotune.py` | Wasted trials, misleading logged exit_cfg |

### 1.2 Dead inputs → silently dead strategies

- **Nothing in the research pipeline populates `funding_rate` or `open_interest`** (`data/pipeline.py` → OHLCV+source only; repo-wide grep confirms no producer). Consequences, all silent:
  - `funding_momentum_long/short`: z-score is identically 0 → **zero trades, forever**.
  - Ultimate regime `FUNDING_CARRY_REVERSAL` tier **can never fire**; OI tier inert.
  - `oi_divergence_*` degrades to a volume-momentum strategy (fallback `oi_up=True`).
- `strategies/impulse_1m.py`: the `di_delta = 0.0` fallback is a trap; with thresholds at -30/+25 it would mean zero entries ever. In practice `build_feature_matrix` always provides `di_delta_1m` (or raises on missing `open`), so the fallback is dead code masking failure. Also the `di_period` param is accepted but never used (DI is fixed at 14 inside the feature matrix).

### 1.3 Smaller defects

- `strategies/crown_stack.py` uses `Any` in signatures without importing it; only survives because of `from __future__ import annotations`.
- `cli.py cmd_backtest` prints `profit_factor`, which `compute_trial_metrics` never computes → always `null`.
- `sweep/portfolio.py`: long and short legs each get full `init_cash`, then combined return divides by one `init_cash` (double-counted capital); combined Sharpe is a naive average, not the combined-equity Sharpe.
- `regime/evaluator.py`: forward returns `fillna(0.0)` lets the last `forward_horizon` bars count as RANGE "wins" (|0|<10bps); Sharpe annualization hardcodes 1m bars.
- `data/book_align.py align_orderbook_to_ohlcv` returns a **reset RangeIndex** (drops the DatetimeIndex) → downstream, HTF resampling in the regime engine silently disables itself and time features go synthetic whenever book alignment is used (autotune `--book-path`, regime-eval `--book-path`).
- `sweep/autotune.py`: `fine_trials` unused; Karpathy mutation doesn't clamp params to valid ranges.
- `ml/ensemble.py` fits its calibrator in-sample (the `train_bundle.py` OOF path is correct; prefer it).

---

## 2. Regime detector (`regime/ultimate.py`) — findings + tuning proposals

### 2.1 Correctness issues

1. **HTF look-ahead bias (the big one).** `df_1m.resample("5min"/"15min")` uses default `label="left", closed="left"`, then `reindex(c.index, method="ffill")`. The 15m bar labeled 10:00 contains the close of 10:14 → at 1m bar 10:00 the macro trend already "knows" up to 14 minutes of future. Every `BULL/BEAR_MOMENTUM_EXPANSION` classification and the entire `regime-eval` accuracy number are contaminated optimistically.
2. **ADX is documented but does not exist.** Docstring, skill file, and the `adx_threshold=22.0` param all claim an ADX gate; ADX is never computed (same in `regime/adaptive.py`). Momentum expansion is actually just "EMA12>EMA48 on two TFs".
3. **OPI gate is sign-only (`>=0.0`/`<=0.0`), not the documented ±0.20**, and the missing-data default of 0.0 *passes both* bull and bear gates → without book data the "microstructure" tier is pure EMA.
4. **OI acceleration (`oi_ret`) and RSI are computed and never used.**
5. **Funding z-score fragility:** 48-minute window with `min_periods=10` over a step-wise hourly funding series, epsilon floor `1e-6` → any tiny funding step produces explosive |z| and spurious `FUNDING_CARRY_REVERSAL` flips (once funding data exists at all; today the tier is dead, see §1.2).
6. Hardcoded 6 bps spread cutoff even though `data/book_flow.py` already computes a rolling P90 `spread_regime_limit`.

### 2.2 Proposed enhancements for higher signal fidelity (ordered)

All of these are correctness / visibility / measurement items. None add a new hard gate: anything threshold-shaped is exposed as a parameter and scored by the evaluator so the data decides, not a prior.

1. **Kill the look-ahead (bug fix):** resample with `label="right", closed="right"` and then `.shift(1)` (use only the last *completed* HTF bar) before `reindex().ffill()`. Re-run `regime-eval` afterwards to establish the honest baseline; expect the accuracy number to drop — that is the real signal.
2. **Resolve the ADX doc/impl mismatch (bug):** the code claims an ADX condition (docstring, skill file, `adx_threshold=22.0` param) but never computes ADX. Either implement it (reuse `_wilder_dmi` from `ml/feature_matrix.py`) as a *parameterized* condition wired to the already-existing-but-dead `adx_threshold`, or correct the docs. If implemented, measure with-vs-without via the evaluator — do not hard-enable.
3. **Make OPI/OI degeneracy visible (bug):** OPI defaults to 0.0, which satisfies both the bull (`>=0`) and bear (`<=0`) conditions, and `oi_ret` is computed but never used — so the detector silently behaves differently from its documentation depending on data availability. Emit per-tier availability flags (`opi_available`, `oi_available`, `funding_available`) in the output frame, wire the documented ±0.20 OPI and OI-agreement conditions as parameters, and let the evaluator report both variants side by side.
4. **Robust funding z (numerics bug):** 48-minute window with `min_periods=10` over a step-wise hourly funding series and a `1e-6` epsilon floor produces explosive spurious |z|. Widen the window (e.g. ~24h of bars, parameterized), floor sigma relative to signal (`max(std, 0.1*|mean|, 1e-8)`). Then actually join HL funding history into the pipeline so the tier is live and observable at all.
5. **Optional dwell/hysteresis parameters (default off):** `regime/metrics.py` already reports `flip_rate` and `mean_duration` — if flicker hurts forward edge, dual enter/exit thresholds and a minimum dwell can be added as tunable parameters and adopted only where the evaluator shows a fidelity gain. Never as silent defaults.
6. **Make tier precedence measurable:** bars often satisfy several tiers at once (e.g. coiling during a strong trend) and the hardcoded priority order silently picks one. Report per-bar condition overlap (which tiers matched) and evaluate alternative orderings empirically instead of hardcoding the answer.
7. **Emit a per-bar confidence score** (scaled distance from thresholds: ADX excess, |z| depth, BBWP depth, OPI magnitude). Pure added information — downstream consumers can use or ignore it; it also makes threshold sensitivity visible in the evaluator.
8. **Fix the evaluator so tuning is trustworthy (measurement bugs):** pass thresholds through `evaluate_regime_accuracy` (currently locked to defaults, so threshold sweeps are impossible), drop tail bars instead of `fillna(0)`, annualize by actual bar interval, and add a state-transition matrix + persistence stats. Then sweep thresholds (adx/bbwp/chop/z) with walk-forward scoring so in-sample and out-of-window edge are both visible.
9. **Parameterize the hardcoded 6 bps spread zeroing:** `spread > 6.0 bps → long_w = short_w = 0.0` is itself a baked-in gate. Expose it as a parameter (or use the rolling P90 `spread_regime_limit` that `data/book_flow.py` already computes) and report how often it fires, so the restriction is a visible, tunable choice rather than a constant.

---

## 3. System / strategy profitability optimizations

1. **Fix engine realism before any more tuning** (B1 funding gate, B3 next-bar-open or shifted-signal execution, B4 pass real `freq`, B2 implement real leverage or surface the 1x cap explicitly in outputs so results aren't mislabeled). Right now the tuner optimizes measurement artifacts; the `sharpe + net_pnl/1000` objective is fed inflated inputs.
2. **Make autotune generic and consistent:** sample unknown strategies from `spec.param_grid` (today impulse_1m / oi_divergence / funding_momentum get zero entry-param tuning), make the final selection use the same criterion the optimizer maximizes (B6), log exceptions instead of silent `-999`, and persist **all** trials (the board JSON keeps only the top 10) so nothing is hidden. Report in-sample and walk-forward metrics side by side — do not gate exports on either.
3. **Actually consume the regime policy (wiring, optional).** `detect_ultimate_regime` produces `long_weight/short_weight/max_leverage` but nothing in sweep/backtest uses them; `portfolio.py` only uses the 4-state detector as a binary veto. Feeding the weights into `conviction_series` → `risk_pct_from_conviction` makes regime-scaled sizing a measurable research variant (run with/without and compare) — that's the entire point of the 5-tier engine.
4. **Join funding + OI history into `load_research_history`** (HL API exposes both). This resurrects two dead strategies and one dead regime tier at essentially zero modeling cost — pure "see everything": today those results simply don't exist.
5. **Combined portfolio correctness:** run long+short in a single vectorbt portfolio (shared capital) instead of summing two independently-capitalized legs; recompute Sharpe on combined equity.
6. **Cost preset naming mismatch (footgun, not a prescription):** `hl_taker_default` resolves to VIP1 (3.5 bps + 1.5 bps slip) while plain `default` resolves to base taker (4.5 bps + 2.0 bps) — the name/resolution mismatch is the defect; which preset to run is the operator's call and all presets (including `zero`) stay selectable. Comparing a maker-fee preset for coiling-regime entries is an optional profitability experiment.
7. **Trail exits:** keep exactly one implementation (vbt `sl_trail`), delete `_trail_exits`.
8. Preserve the DatetimeIndex in `align_orderbook_to_ohlcv` (restore it after `merge_asof`) so book-gated runs keep HTF confirmation and real time-of-day features.

The metalabel pipeline is comparatively healthy (SL-first double-hit resolution, purged+embargoed CV, OOF calibration in `train_bundle`), but note its labels inherit the engine's same-bar-close entry convention, so fixing B3 should be coordinated with relabeling.

### 3.1 Charter compliance audit (dedicated second pass)

Authoritative rules audited, from `docs/superpowers/specs/2026-07-21-phase1-vectorbt-design.md` and module contracts:

- **SRS_HV1_NO_GATES** — only technical failure aborts a trial; no strategy/risk rejection gates unless explicitly configured by Albert.
- **SRS_HV1_REGIME_NO_GATE** — regime labels must not veto trials or trades unless composition mode is explicitly enabled.
- **SRS_HV1_REGIME** — regime metrics remain separate research outputs, not entry/trial controls.
- **SRS_HV1_HIST_PROMO** — robustness windows (180d) are views, never candidate kill-gates.
- **Module contracts** — `sweep/search.py`: "technical failure only aborts a trial"; `regime/metrics.py`: "reported, never gated."

**Standing constraint honored throughout: every remediation below removes a restriction or adds visibility. None adds a gate.**

#### Verdict table

| Rule | Verdict | Evidence |
|---|---|---|
| SRS_HV1_NO_GATES | **Violated** in autotune + its export path; grid-search path compliant | V1-V4, V7 |
| SRS_HV1_REGIME_NO_GATE | **Violated** in `portfolio.py`; violated-by-default in `pine_composite` | V5, V6 |
| SRS_HV1_REGIME | Compliant | `regime/metrics.py` and `regime/evaluator.py` are pure reporting; `ultimate.py` policy columns are outputs consumed nowhere |
| SRS_HV1_HIST_PROMO | Compliant | 180d never used as a kill-gate anywhere; `config.validate_lookback` enforces only the charter's own ≥30d floor (SRS_HV1_HIST_FLOOR — technical) |
| Module contracts | `search.py` / `rank_trials` compliant; autotune and RunsDB persistence break aborted-trial visibility | V2, V4, V7 |

#### Violations (V#) — remediation is always restriction-removal / visibility-add

- **V1** `sweep/autotune.py`: hardcoded risk-rejection penalties inside the objective (`trades < 10 → -50+trades`, `max_dd > 25 → -20-dd`) — risk gates not "explicitly configured by Albert"; they silently steer the sampler and (via B6) disagree with final selection anyway. Remediate: lift penalties into explicit, visible config defaulting **off** (pure objective); always report raw metrics.
- **V2** `sweep/autotune.py`: `except Exception → return -999.0`, unlogged — a technical failure neither aborts visibly nor is recorded; the trial vanishes from `trials_log` entirely. The contract requires it to remain *an aborted trial*. Remediate: record it as a `status="error"` trial with the exception text, shown ranked-last exactly like `run_grid_search` does.
- **V3** `sweep/autotune.py`: export bundle written only when best `net_pnl > 0` — a performance kill-gate on export (conflicts with SRS_HV1_NO_GATES and SRS_HV1_STRAT_MULTI multi-candidate export). Remediate: export unconditionally; the sign of PnL is a reported fact, not an export condition.
- **V4** `sweep/autotune.py`: board JSON persists only `top_trials[:10]` — the rest of the search is hidden. Remediate: persist the full trial log.
- **V5** `sweep/portfolio.py`: hardwired regime trade veto — `entries_l & (regime != "BEAR_TREND")`, mirrored for shorts, plus same-bar conflict suppression — with **no composition-mode parameter at all**. Direct SRS_HV1_REGIME_NO_GATE violation. Remediate: add a `composition_mode` parameter defaulting **off** (raw pass-through) and report gated vs ungated metrics side by side.
- **V6** `strategies/pine_composite.py`: `regime_filter=True` **by default**, and both registered param_grids pin `regime_filter: [True]` — the regime detector (`detect_regime_ema`) vetoes entries by default and the ungated variant is not even reachable through the default grid. Remediate: default `False` and put both values in the grid. (`crown_stack` and `trend_ride` already do exactly this — the compliant pattern to copy.)
- **V7** `cli.py _run_sweep`: only `status == "ok"` trials are inserted into RunsDB — technical-failure trials disappear from the `report` command (the printed board at sweep time does include them). Remediate: persist error trials with their status so aborted trials remain visible research results.
- **V8** `regime/ultimate.py`: `spread > 6.0 bps → long_w = short_w = 0.0` hardcoded in the policy output. Currently **inert** (nothing consumes the weights, so no trial is vetoed today), but it is a latent unparameterized gate: the moment the policy is wired into sizing it becomes an invisible veto. Remediate: parameterize and report its fire-rate *before* any consumer exists.

Visibility note (not a gate, §1.2): missing `funding_rate` / `open_interest` / book columns silently neutralize or bypass strategy and regime conditions with zero warning. Emit data-availability provenance in every report so a dead input is impossible to miss.

#### Borderline — explicitly configurable, but the default leans gate-on

- **Paper book gate**: `paper/session.py` `book_gate_enabled=True` by default and **not exposed on the `paper-run` CLI at all** (no flag; `runner.py` passes defaults through) — a default-on entry veto in the paper domain that cannot be switched off from the CLI. Skips are ledgered (`skip_reason="book_gate"`), which preserves visibility, but the gate itself was never user-configured. Remediate: expose `--book-gate/--no-book-gate` on `paper-run`; consider observe-only default.
- **Paper metalabel filter**: `--metalabel` is opt-in (default off — compliant), but once enabled, `--metalabel-filter` defaults to **filtering** (`p < min_p` vetoes entry; predict failure fail-closed skips). A user enabling metalabel for *observation* gets a veto by default. `--no-metalabel-filter` (scale-only) exists. Remediate: flip the default to scale-only so a model score is a reported metric unless filtering is explicitly requested. (The companion `docs/read-only-assessment-2026-07-24.md` reached the same conclusion independently.)
- **`funding_momentum.py` / `oi_divergence.py`**: `regime_filter=True` defaults (raw EMA trend confirm — strategy thesis, not the regime-track detector), but the grids never sweep `regime_filter`, so the unfiltered variant is never measured. Remediate: add `False` to the grids (pure visibility).

#### Compliant surfaces (verified this pass)

- `sweep/search.py run_grid_search`: invalid params / exceptions → `status="error"` trials that are kept and ranked last; no metric-based aborts. Charter-clean.
- `report.py rank_trials`: "no risk filtering" — ranks by net PnL / total return (SRS_HV1_RANK_PRIMARY); technical failures shown last, never dropped.
- `regime/metrics.py` + `regime/evaluator.py`: pure reporting; nothing downstream mutates entries through them.
- `backtest --book-gate`: opt-in, default off.
- `crown_stack` / `trend_ride`: `regime_filter=False` default with both values in the grid — correct explicit-configuration pattern.
- `config.validate_lookback`: enforces only the charter's own ≥30d technical floor; the 180d PROMO window is a view and is used as a kill-gate nowhere.
- Export/phase2 `strict` schema validation and `cmd_export`'s research_meta refusal: technical completeness checks, not performance gates.
- Live fail-closed (`live/policy.py`) and paper/live path separation (`paper/ledger.py` write refusals): safety rails locked by AGENTS.md/HANDOFF decisions — a separate domain from research gating, compliant by design.

---

## Recommended fix order (highest leverage first)

1. B1 (funding gate)
2. B3 / B4 (execution timing, Sharpe freq)
3. Regime HTF look-ahead (§2.2.1)
4. Funding/OI data join (§3.4)
5. Autotune selection unification (B6/B7)

Charter remediations V1-V8 (§3.1) are independent restriction-removals / visibility-adds and can ship in any order alongside the bug fixes; V5 and V6 are the two live regime-veto violations and the quickest to remove.

## Verification appendix

Empirical probe against installed `vectorbt==1.1.0` (synthetic 10-bar series, entry signal at bar index 2 / 00:02, exit at bar 7):

| size (`size_type="percent"`) | Filled size | Entry fill | Final value |
|---|---|---|---|
| 0.5 | 49.02 | 00:02 @ 102.0 (signal bar's own close) | 10,245.10 |
| 1.0 | 98.04 | 00:02 @ 102.0 | 10,490.20 |
| 5.0 | **98.04 (identical to 1.0 — capped)** | 00:02 @ 102.0 | 10,490.20 |

Confirms B2 (leverage no-op above 1x) and B3 (same-bar close execution).
