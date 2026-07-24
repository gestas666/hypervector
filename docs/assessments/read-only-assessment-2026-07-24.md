# Hypervector Read-Only Systems Assessment

**Assessment date:** 2026-07-24  
**Reviewed commit:** `10d94a1`  
**Audience:** Engineering, quantitative research, and trading operations  
**Scope:** Strategy logic, research/backtest accounting, paper/live execution, ML validation, data plumbing, and regime detection  
**Constraint:** The assessment itself was read-only. This document records the findings; it does not implement them.

## Technical summary

The highest-priority risks are execution and accounting mismatches, not weak signal thresholds. Several defects can make research results optimistic or make paper/live behavior diverge materially from research: same-bar fills, inactive research funding, per-bar funding charges in paper/live, ineffective leverage settings, stale equity-based sizing, missing protective exits, and success-shaped handling of venue error responses.

**Overall confidence: high for the directly reproduced defects; medium for profitability effects.** The defects were supported by source inspection and focused probes, but their portfolio-level financial impact has not been measured on a representative point-in-time dataset. A corrected backtest could report lower historical profitability while providing a more credible basis for future decisions.

The regime detector has two foundational fidelity problems: higher-timeframe look-ahead when a `DatetimeIndex` is present, and silent loss of higher-timeframe confirmation when a `RangeIndex` is used. It also contains unused inputs and thresholds, conflates missing evidence with neutral evidence, and is evaluated with biased forward-return handling.

The corrected regime redesign obeys a stronger research-platform invariant: preserve every source row, feature observation, raw strategy entry, and outcome. The detector appends causal evidence and data-quality metadata only. It does not modify sizing, routing, execution, row selection, or trade eligibility. Missing or stale features remain visible as missing or stale; they do not cause records or signals to be removed.

In this report, **capital safety refers only to correcting code or logic defects that can create unintended orders, exposure, or accounting state**. Examples are false-success order handling, missing fill reconciliation, non-reduce-only closes, stale-equity sizing, and configured exits that are not enforced. It does not authorize any strategy gate, data filter, confidence cutoff, liquidity veto, automatic sizing decision, or reduction in research visibility or trade opportunity.

## 1. Problem definition and success criteria

### Inputs

- Repository source and tests at commit `10d94a1`.
- Existing strategy, backtest, paper, live, data, ML, and regime implementations.
- Installed local `vectorbt==1.1.0` behavior for execution and sizing probes.

### Required outputs

1. Identify broken logic and bugs.
2. Identify system and strategy improvements that could increase after-cost profitability.
3. Propose regime detector changes that improve signal fidelity without reducing signal breadth through new gates.

### Decision criteria

Changes can be compared descriptively across these dimensions without suppressing observations or declaring a policy winner:

- point-in-time correctness;
- research-to-paper-to-live parity;
- after-cost expectancy or risk-adjusted return out of sample;
- calibration and stability of regime evidence;
- operational safety and observability;

The platform must retain and report the complete raw strategy entry set regardless of how any candidate scores on these dimensions.

Capital-safety findings are limited to restoring intended execution semantics and state correctness. They must not change which strategy signals qualify for entry or which data remains available for analysis.

### Authoritative no-gates charter

The repository already defines the controlling behavior. This assessment must trace to that charter rather than introduce a new policy:

| Requirement or source | Repository wording and assessment consequence |
|---|---|
| `SRS_HV1_NO_GATES` in `docs/superpowers/specs/2026-07-21-phase1-vectorbt-design.md` | The system must not apply strategy or risk rejection gates unless explicitly configured by Albert. Only technical failure aborts a trial. Performance, drawdown, trade count, regime, confidence, missing optional features, and model scores therefore remain reported trial results rather than implicit abort conditions. |
| `SRS_HV1_REGIME` | Regime labels and detection metrics are a separate research track from trade PnL. They are outputs for analysis, not entry or trial controls. |
| `SRS_HV1_REGIME_NO_GATE` | Regime labels must not hard-block trials or force trade vetoes unless composition mode is explicitly enabled. |
| `SRS_HV1_HIST_PROMO` | The 180-day robustness window is supported when available and is explicitly not a candidate kill-gate. Shorter and longer data views must remain visible with their provenance. |
| Phase 1 architecture | Segmented regime/equity analytics are described as “views, not gates.” |
| `src/hypervector/sweep/search.py` module contract | Grid search states that technical failure alone aborts a trial and records failures while allowing other trials to continue. |
| `src/hypervector/regime/metrics.py` module contract | Regime detection metrics are “reported, never gated.” |

The specification does not fully define the boundary of “technical failure.” **Medium confidence interpretation:** it means the trial cannot produce a valid result because execution failed, such as an exception or structurally invalid parameter combination. An undesirable metric, sparse trading, a regime label, missing optional evidence, or poor model confidence is not a technical failure under the stated charter. This interpretation would be updated by a more specific approved requirement or an explicit user-configured composition mode.

## 2. Evidence and methodology

The review combined static source inspection, focused unit tests, local behavioral probes, and inspection of the installed VectorBT implementation. No network-dependent evidence was used.

Confidence labels mean:

- **High:** directly observed in source and/or reproduced locally.
- **Medium:** strongly implied by the implementation but financial materiality is not yet quantified.
- **Low:** plausible risk requiring data or venue validation.

Every substantive interpretation remains provisional. Falsifiers and validation tests update the evidence; they do not automatically promote, suppress, or remove a strategy, signal, observation, or experiment.

## 3. Broken logic and defects

### 3.1 Capital-safety and execution parity

| Priority | Finding | Evidence | Likely impact | Confidence and falsifier |
|---|---|---|---|---|
| Critical | Venue error dictionaries can be reported as successful submissions. | `src/hypervector/live/exec_client.py:203` treats a returned dictionary as `submitted=True`; a local fake transport returning an explicit error produced `PlaceResult(submitted=True, venue_order_id=None, error=None)`. | Internal state can diverge from venue state. | **High.** Falsified if every supported venue error shape is rejected before constructing a successful result. |
| Critical | Live state assumes the full requested quantity filled at the local mark. | `src/hypervector/live/engine.py:178` updates local position after submission without actual filled quantity, price, or terminal order state. | Partial, rejected, or delayed fills can create incorrect exposure and subsequent orders. | **High for the code path; medium for frequency.** Validate with mocked partial-fill and rejection sequences plus venue reconciliation. |
| Critical | Paper and live sessions do not enforce configured stop-loss, take-profit, or trailing exits. | Exit configuration is used for sizing in `paper/session.py:373` and `live/session.py:198`; bracket enforcement exists in `nautilus/actor.py:385`, not the paper/live session loops. | Realized risk can exceed the risk assumed during sizing. | **High.** Falsified by an end-to-end test showing paper and live sessions close at every configured barrier. |
| High | Funding is charged once per input bar, although the configured rate is hourly. | `paper/session.py:199` and `live/session.py:133` apply the hourly rate on each bar. A focused 1-minute test showed a full hourly payment after one bar. | Approximate overcharge of 60 times on 1-minute bars or 12 times on 5-minute bars, subject to bar continuity. | **High for cadence defect.** Validate with elapsed-time integration across irregular bars and funding events. |
| High | Sizing uses initial equity rather than current equity. | `self.equity` is initialized in `paper/session.py:142` and `live/session.py:97`, then reused for sizing without observed updates. | Compounding, losses, and funding do not alter subsequent risk budgets. | **High.** Falsified if all sizing calls are proven to receive reconciled mark-to-market equity through another path. |
| High | Exit orders are not consistently reduce-only. | `src/hypervector/live/engine.py:55` builds intents with `reduce_only=False`. | A close can potentially flip exposure when local and venue positions differ. | **Medium.** Validate against each venue order path and reconciliation behavior. |

### 3.2 Backtest and accounting fidelity

| Priority | Finding | Evidence | Likely impact | Confidence and falsifier |
|---|---|---|---|---|
| Critical | Research signals fill at the same close used to compute them. | `compute_trial_metrics` passes close-derived signals to `Portfolio.from_signals`; installed VectorBT resolves the default order price to the current close. | Optimistic entry timing, especially on 1-minute mean-reversion signals. | **High.** Falsified if the production caller shifts decisions to the next executable bar before portfolio construction. |
| Critical | Research funding is inactive for current cost presets. | `sweep/metrics.py:160` checks `funding_rate_8h`, while presets in `sweep/costs.py:65` set `funding_rate_1h` and leave the 8-hour field unset. | Research PnL omits funding drag or receipts. | **High.** Validate with a position of known duration and a signed funding schedule. |
| High | The leverage control above 1x is ineffective in the current VectorBT sizing path. | `sweep/metrics.py:73` uses `size_type="percent"`; local inspection showed percentages above one remain constrained by available resources. CLI and autotune map leverage into this fraction. | Searches over 2x, 3x, and 5x can produce identical exposure to 1x. | **High for installed version.** Falsified by a trade-log probe showing borrowed exposure above available cash. |
| High | Sharpe annualization defaults to one-minute frequency for all requested timeframes. | `compute_trial_metrics` defaults to `freq="1min"`; callers do not pass the requested timeframe. | Cross-timeframe Sharpe values are not comparable and non-1-minute values are misannualized. | **High.** Recompute from the equity series using inferred bar duration. |
| High | Maximum drawdown units and sign are inconsistent with autotune penalties and CLI labels. | Metrics return a negative fraction, while autotune compares it with positive `25.0`; CLI labels the raw value as a percentage. | Drawdown penalties may never trigger and reports can misstate scale. | **High.** Test a synthetic equity curve with a known 25% drawdown end to end. |
| High | Long and short portfolio legs each receive the full initial capital, then their PnLs are combined against one capital base. | `sweep/portfolio.py:77` builds two portfolios independently; `sweep/portfolio.py:84` combines their results. Combined Sharpe is an arithmetic average rather than equity-curve Sharpe. | Return and risk metrics can be overstated or internally inconsistent. | **High.** Falsified by a shared-cash simulation matching the current combined output trade for trade. |
| High | Trail mode runs two stop engines, and the custom engine can retain stale position state. | `sweep/exits.py:88` creates custom trailing exits; `sweep/metrics.py:89` also enables VectorBT trailing stops. The custom state tracks its own stops but not every strategy exit. | Duplicate or stale exits and failure to re-arm subsequent entries. | **High from control flow; medium for portfolio materiality.** Validate with entry, signal exit, re-entry, and trail-hit sequences. |
| Medium | Research funding estimation is unsigned and does not use time-varying rates; funding adjustment is not propagated through all risk metrics. | `_estimate_funding` treats funding as absolute cost. | Shorts or favorable funding can be misrepresented even after activating the path. | **High for implementation; medium for impact.** Validate against a signed event-level funding ledger. |

### 3.3 Autotuning and selection defects

- **Selection criterion mismatch — high confidence.** `sweep/autotune.py:132` computes a penalized objective, but trial records are appended before penalties and the final displayed selection is sorted by raw Sharpe at `sweep/autotune.py:266`. The interface can therefore describe one objective while highlighting a candidate under another. Falsifier: retain and display the complete trial table, every scoring component, every failure, and each ranking view so the researcher can see why the views disagree without trials being discarded.
- **Only a subset of strategies receive entry-parameter tuning — high confidence.** Parameter construction is name-specific around `sweep/autotune.py:150`; registry `param_grid` is not used generically. `impulse_1m`, `oi_divergence`, and `funding_momentum` can receive empty entry parameters. Falsifier: inspect emitted trials and show variation in every registered tunable entry parameter.
- **`sl_pct` is a dead Optuna dimension — high confidence.** It is suggested at `sweep/autotune.py:182` but omitted from the `ExitConfig` constructed for evaluation. Falsifier: show trial-dependent stop percentages reaching the simulator.
- **Errors are hidden — high confidence.** A broad `except Exception: return -999` converts programming or data errors into a score. This prevents actionable diagnosis. Falsifier: verify structured propagation or logging of the original exception and trial context.
- **`fine_trials` is unused and “hybrid” does not execute two search phases — high confidence.** Validate the actual number and type of trials through deterministic instrumentation before relying on the interface label.

### 3.4 Data and strategy defects

- **Point-in-time OI and funding inputs are not produced by the research pipeline — high confidence.** The provenance schema and pipeline load OHLCV, while strategies and the ultimate detector consume `open_interest` and `funding_rate`. Consequences:
  - `funding_momentum` receives a constant fallback and produces no useful funding signal;
  - the ultimate funding and OI evidence is inactive;
  - `oi_divergence` treats missing OI as permissive and degrades into price-volume momentum.
  Falsifier: trace non-null, timestamped, point-in-time OI and funding fields from source through the feature and signal outputs.
- **RSI mishandles a zero-loss rising series — high confidence.** `strategies/indicators.py:25` replaces zero losses with missing values and fills the result with 50. A monotonic rising probe returned a 50-valued tail rather than an overbought reading. Falsifier: compare against a reference Wilder RSI across monotonic up, monotonic down, flat, and mixed cases.
- **`impulse_1m.di_period` is accepted but unused — high confidence.** The feature matrix uses a fixed DMI period. Falsifier: demonstrate distinct DI series and entries when only `di_period` changes.
- **Gap provenance assumes one-minute data — high confidence.** `data/provenance.py:61` hard-codes the expected interval. Clean five-minute data was reported as gaps. Falsifier: a clean multi-timeframe fixture produces zero gaps for its declared timeframe.
- **Order-book alignment can lose temporal semantics — high confidence for index loss, medium for signal impact.** `data/book_align.py:211` resets the index during `merge_asof`; downstream code can see a `RangeIndex`, synthesize time features, and disable automatic higher-timeframe resampling. Candle timestamps also appear to represent bar opens while the signal uses completed-bar values, so book data may be stale relative to the decision time. Validate with explicit availability timestamps and an as-of trace for several bars.
- **Spot endpoints are preferred before futures endpoints for perpetual research — medium confidence risk.** This can create basis and volume-distribution mismatch. It may be intentional. Validate the intended market and compare signal stability on venue-matched perpetual data.
- **Incomplete current candles may not be explicitly identified — low-to-medium confidence.** A still-forming candle can be mistaken for a final observation. It should remain in the dataset with explicit `is_complete`, observation-time, and expected-close metadata so researchers can inspect it and causal calculations can be reproduced. I do not have verified API-response timing evidence. Validate by comparing the final candle timestamp and close time with the retrieval time for each source.

### 3.5 ML validation leakage and calibration risks

- **Walk-forward boundaries do not purge by label outcome time — high confidence.** `ml/purged_cv.py:64` receives entry timestamps but not event end times; overlapping triple-barrier outcomes can cross train/test boundaries. Validate with fixtures whose label intervals deliberately overlap a fold boundary.
- **The reported baseline uses the test-set label mean — high confidence.** `ml/walk_forward.py:198` uses information unavailable at decision time. Replace with a training-only prevalence baseline for honest comparison.
- **Labels are generated for every qualifying signal bar, not necessarily independent executed entries — high confidence.** This creates overlapping, highly dependent samples. Measure effective sample size and compare event-deduplicated labels.
- **Realized-volatility annualization assumes one-minute bars — high confidence.** `ml/feature_matrix.py:114` uses a one-minute annualization constant and names fields `*_1m`. Validate feature scale across declared timeframes.
- **Isotonic calibration in `ml/ensemble.py` is fitted in sample — high confidence for that module.** This can overfit calibration. The out-of-fold path elsewhere is preferable. Validate with calibration curves and Brier score on untouched chronological data.
- **The default metalabel behavior is a hard trade gate — high confidence.** That behavior is incompatible with the corrected research baseline. The metalabel output should be recorded as an annotation alongside every signal and outcome, without filtering trades, rows, or displayed results. If the researcher explicitly requests a gated comparison, it must be a separately named experimental arm and must report every opportunity it would exclude while leaving the unrestricted baseline intact.

### 3.6 Test and interface defects

- **Strategy registration is not idempotent after registry clearing — high confidence.** `register_all_strategies()` relies on cached module import side effects. The focused sequence `test_regime_labels_only_up_down_range` followed by `test_impulse_1m_registry` reproduced `KeyError: unknown strategy impulse_1m_long`.
- **The CLI emits `profit_factor`, but the metric is not calculated — high confidence.** The value is consequently absent or null rather than a verified profitability measure.
- **The TUI’s advertised regime behavior is not a reliable live view — high confidence from source.** The loader reads JSON text rather than Parquet, invalid input silently falls back to synthetic data, timestamps and confidence are synthesized, and `--live` does not add polling. Validate with an integration test that changes a real input file and observes a timestamp-preserving update without synthetic fallback.

### 3.7 Direct no-gates charter mismatches

| Finding | Charter relationship | Confidence and falsifier |
|---|---|---|
| `sweep/portfolio.py:60` computes raw entries, then `sweep/portfolio.py:70` removes long entries in `BEAR_TREND`, removes short entries in `BULL_TREND`, and removes simultaneous short entries. The function exposes no explicit composition-mode argument. | This is a direct trade veto by regime and conflict policy rather than a segmented analytical view. It conflicts with `SRS_HV1_REGIME_NO_GATE` unless the caller has explicitly enabled a composition mode through a path not present in this function. | **High.** Falsified by an explicit user-configured composition control that defaults off and by preservation/reporting of the unrestricted raw portfolio beside the composed result. |
| Metalabel filtering defaults to `True` in `paper/session.py:93`, `paper/runner.py:79`, and the CLI path; probabilities below `min_p` set `allow_entry=False`. | A model score becomes a default entry veto rather than a reported metric. This conflicts with `SRS_HV1_NO_GATES` unless the user explicitly enables filtering rather than merely enabling model observation. | **High for behavior; medium for intended scope.** Falsified if the research default records metalabel output without filtering and filtering requires a separate explicit opt-in. |
| Autotune returns nontechnical penalty scores for fewer than ten trades and drawdown at `sweep/autotune.py:133`, while the charter specifies primary ranking by net PnL/total return and no risk stonewalls. | These thresholds steer ranking based on performance/risk rather than technical validity. The drawdown branch is also affected by the separate unit/sign defect. | **High for implementation; medium for whether the mode was explicitly user-authorized.** Falsified by reporting the metrics and all ranking views without an implicit default penalty, or by evidence that the user explicitly selected that penalty policy for the run. |
| `pine_composite`, `oi_divergence`, and `funding_momentum` define `regime_filter=True` defaults; other strategies expose mixed defaults. | A default-on filter can conceal the ungated strategy surface. Whether the filter is intrinsic strategy logic or an impermissible regime veto is not consistently specified. | **Medium.** Resolve by exposing and retaining both raw pre-filter signals and the named strategy-composition output, with any filtering choice explicit in run provenance. |
| `regime/metrics.py` only calculates and returns label statistics. | This module itself follows “reported, never gated.” The violations occur where downstream components consume regime or model outputs as entry controls. | **High.** Falsified if the metrics function is shown to mutate entries or trial status through an indirect path. |
| `sweep/search.py` records caught exceptions as `status="error"` and continues other trials, but catches every exception under one category. | Continuing the search aligns with the charter; the broad error category does not prove that only technical failures receive error status. | **Medium.** Validate with an explicit failure taxonomy and tests separating technical execution failure from valid but poor, sparse, missing-optional-feature, or regime-specific outcomes. |

## 4. Regime detector assessment

### 4.1 Causality and representation defects

1. **Higher-timeframe look-ahead — high confidence.** In `regime/ultimate.py:68`, default resampling labels a bucket at its start and aggregates its final close. Reindexing and forward-filling can make future closes visible to earlier one-minute rows. A prefix-invariance probe found six historical classifications that changed after future rows were appended.

2. **Higher-timeframe logic silently depends on index type — high confidence.** Automatic resampling runs for a `DatetimeIndex`, but typical normalized CLI data uses a `RangeIndex`. The same prices produced nine classification differences when only index representation changed.

3. **Advertised inputs are unused — high confidence.** `adx_threshold`, one-minute returns, and OI returns are computed or accepted but do not affect the ultimate state. Changing `adx_threshold` from 1 to 999 produced zero classification differences. The adaptive detector also advertises ADX without using it.

4. **Missing microstructure evidence is treated as neutral numeric evidence — high confidence.** OPI defaults to zero, while directional comparisons use zero as the boundary. Feature absence is therefore not distinguishable from a measured neutral value.

5. **State precedence erases orthogonal information — high confidence.** Spread, funding, compression, chop, and direction are assigned through a priority chain. Compression or carry conditions can overwrite direction even when both are useful descriptions of the same market.

### 4.2 Evaluator defects

- Tail forward returns are filled with zero, biasing the final horizon toward range “wins.”
- Bear-state mean return and Sharpe use an unsigned long-return interpretation. A perfect bear-state probe on falling prices reported 90% wins but negative mean return and strongly negative Sharpe.
- Annualization is fixed to one-minute bars.
- Compression success is scored as small absolute returns even though compression is described as preparation for expansion.
- Overlapping forward returns are treated as independent observations.
- Thresholds are not exposed cleanly for causal walk-forward tuning.

**Confidence: high for implementation defects; medium for the size and direction of metric bias.** A corrected evaluator on frozen data is required to quantify the difference.

## 5. No-overgating regime design

### 5.1 Research-platform invariants

These rules implement `SRS_HV1_NO_GATES`, `SRS_HV1_REGIME`, and `SRS_HV1_REGIME_NO_GATE` rather than adding a new assessment policy:

1. The raw data rows, feature rows, strategy entries, and outcomes must remain available and addressable with regime analysis enabled or disabled.
2. The raw strategy entry Boolean series must be byte-for-byte identical with regime or metalabel features enabled or disabled.
3. The detector must not add an `AND`, veto, minimum-confidence requirement, dwell lock, row filter, sample filter, trade filter, sizing multiplier, or routing decision.
4. Missing, stale, contradictory, and extreme observations must remain in the research dataset with explicit quality metadata. They must not be silently dropped, imputed into directional evidence, or hidden from reports.
5. Regime labels, probabilities, scores, confidence, freshness, and feature contributions are appended analytical columns only.
6. Only a technical failure may abort a trial. All nontechnical results—including losses, high drawdown, low trade count, weak confidence, unusual regimes, missing optional features, and inconclusive metrics—remain reported.
7. A restrictive or allocation-changing hypothesis may be studied only as a separately named, explicitly researcher-defined composition arm. It must never replace, mutate, or hide the complete unrestricted baseline.
8. Capital-safety work is limited to demonstrated execution, accounting, and state-consistency defects. It must not reduce research coverage or the raw opportunity set.

### 5.2 Proposed output model

Replace the single exclusive state as the primary control signal with continuous, orthogonal outputs:

- directional probabilities: `p_bull`, `p_bear`, `p_range`;
- compression score;
- carry/funding score;
- liquidity-friction score;
- feature availability and freshness;
- calibrated confidence and human-readable evidence contributions.

The legacy categorical state can remain as one display projection, while the continuous evidence remains visible beside it. No detector output is consumed as an automatic sizing or execution command. This prevents an exclusive label from hiding simultaneous evidence such as direction plus compression.

### 5.3 Specific fidelity enhancements

| Enhancement | Expected benefit | Research-platform behavior | Risk and validation |
|---|---|---|---|
| Join completed higher-timeframe bars by explicit availability time. | Removes look-ahead and index-dependent behavior. | Corrects appended evidence only; all source rows and raw entries remain visible. | Timestamp conventions differ by source. Prove prefix invariance and representation invariance. |
| Calculate ADX as an additional descriptive feature rather than a gate. | Lets researchers inspect energetic trends versus low-energy EMA drift. | Every source row remains present; rows lacking sufficient history carry missing ADX plus an explicit reason. ADX makes no trade decision. | ADX can lag. Report its conditional behavior and ablation results without hiding adverse cases. |
| Normalize EMA slope by ATR and expose each timeframe separately plus a documented composite. | Makes trend evidence more comparable without concealing component behavior. | Raw component values and the composite remain available; neither controls entries. | A composite can obscure disagreement. Always retain the components. |
| Record OPI, depth, and microprice as robust scores with freshness metadata. | Uses magnitude and feed quality instead of sign-only comparisons. | Missing inputs stay missing and the row remains present; no renormalization may hide the missing evidence. | Feed quality may dominate interpretation. Report missingness, staleness, and contribution distributions. |
| Evaluate funding at actual funding updates and retain both raw and robustly standardized series. | Reduces misleading repetition while preserving source evidence. | Raw events, repeated bar-aligned values, and transformed values remain inspectable. | Sparse history can destabilize transforms. Report sample size and transform sensitivity. |
| Calculate rolling point-in-time percentiles per symbol/timeframe alongside fixed-reference values. | Lets researchers compare adaptive and fixed representations. | Neither representation suppresses observations or becomes a policy threshold. | Percentiles can drift. Preserve the raw value and transformation parameters. |
| Expose raw and causally smoothed probability series together. | Lets researchers measure flip noise and latency without choosing one view prematurely. | Smoothing is an additional series, not a lockout or allocation command. | Smoothing delays turns. Report latency and turnover implications across multiple half-lives. |
| Emit confidence, availability, and contribution diagnostics. | Makes state changes auditable and missingness visible. | Diagnostics are research outputs only and never become implicit vetoes. | Added complexity. Keep the schema documented and preserve every underlying component. |

### 5.4 Research integration without policy enforcement

- Append regime, metalabel, liquidity, funding, and data-quality outputs to the same complete event record as the raw signal and realized outcome.
- Preserve raw inputs, component features, composite scores, and categorical projections so researchers can see agreement, disagreement, missingness, and failure cases.
- The detector must not issue position size, maker/taker, urgency, entry, or exit commands.
- Any sizing, routing, or filtering policy must be a separate, explicitly researcher-authored experiment with a distinct result series. The unrestricted baseline and all counterfactual opportunities remain visible beside it.
- Comparison reports must include total rows, raw signals, candidate actions, excluded opportunities, and outcomes for the complete baseline.

**Profitability confidence: unverified until measured.** The regime outputs create additional ways to analyze conditional performance; they do not establish that any policy derived from them is profitable.

## 6. Profitability optimization priorities

### Priority 1: repair measurement and execution parity

Correct next-bar execution, signed time-aware funding, timeframe annualization, leverage semantics, shared capital, one trailing-stop engine, current-equity sizing, protective exits, and venue fill reconciliation before retuning strategies.

This priority repairs incorrect measurement or unintended execution behavior only. It adds no data restriction, sample exclusion, entry gate, regime restriction, minimum-confidence requirement, or opportunity filter.

**Rationale:** optimization against biased measurements is likely to select artifacts.  
**Confidence:** high for measurement value; unverified for realized profit.  
**Falsifier:** corrected accounting produces immaterial metric and selection changes across representative strategies and periods.

### Priority 2: activate point-in-time derivatives data

Join venue-matched funding, premium/basis, and OI histories using explicit event and availability timestamps. Record provenance, freshness, and missingness. Do not use permissive Boolean fallbacks.

**Rationale:** this activates currently dead or degraded strategy and regime features.  
**Confidence:** high for activation, low-to-medium for profitability.  
**Falsifier:** ablation shows no stable after-cost out-of-sample benefit.

### Priority 3: make autotuning generic and selection-consistent

Sample from each strategy specification’s parameter grid, retain every trial and failure with structured reasons, and keep the charter-defined net PnL/total return ranking as the primary board. Show Sharpe, drawdown, trade count, alternative scores, and chronological walk-forward slices as additional views rather than implicit penalties or rejection rules. Time slices are comparison labels, not deleted data: the full dataset and all trial outcomes remain accessible. Only a classified technical failure may set a trial to `error` or abort that trial.

**Rationale:** reduces silent dead dimensions and winner-selection inconsistency.  
**Confidence:** high for correctness, medium for improved selection quality.  
**Falsifier:** deterministic audit shows current and corrected processes explore and select the same valid candidates.

### Priority 4: evaluate a true shared-capital portfolio

Build one equity curve with explicit gross and net exposure, turnover, signed funding, and shared cash. Compute combined Sharpe and drawdown from that curve rather than combining leg-level summary statistics.

**Rationale:** makes portfolio constraints and diversification measurable.  
**Confidence:** high.  
**Falsifier:** a shared-ledger reconciliation exactly matches current capital use and metrics.

### Priority 5: analyze regime evidence without changing the baseline

Attach regime outputs to every raw signal and compare conditional distributions, after-cost expectancy, turnover, drawdown, tail loss, and calibration across the complete opportunity set. If the researcher explicitly defines a sizing or filtering hypothesis, run it as an additional named result series without changing the unrestricted baseline.

**Rationale:** reveals where regime evidence is informative, neutral, or misleading without using it to restrict the research universe.  
**Confidence:** high for observational completeness, low for any profitability inference before data.  
**Falsifier:** any row, signal, outcome, or adverse case becomes unavailable after regime analysis is enabled.

## 7. Validation and experimentation plan

### 7.1 Unit and property tests

- **Causality:** appending future bars cannot alter any historical regime output.
- **Representation:** equivalent timestamp-indexed and timestamp-column inputs produce equivalent regime outputs.
- **Threshold sensitivity:** changing every public regime parameter measurably affects its declared feature path on a constructed fixture.
- **Data preservation:** row identities and counts are identical with regime analysis on and off, including missing, stale, extreme, and contradictory observations.
- **Signal preservation:** raw entry arrays and trade opportunity counts are identical with regime and metalabel analysis on and off.
- **No control side effects:** detector execution cannot write position size, routing, entry, exit, or eligibility fields.
- **Missingness:** removing an optional feature changes its availability metadata but does not remove the row, synthesize directional evidence, or conceal the missing value.
- **Trial-status charter:** losing PnL, high drawdown, low trade count, low model confidence, any regime label, and missing optional features still produce reported non-error trials. Only deliberately constructed technical failures produce `status="error"` or abort the affected trial.
- **Regime composition default:** portfolio and strategy research produce an unrestricted signal/result series by default; any explicitly enabled composition mode produces a second named series and records every vetoed opportunity.
- **Ranking traceability:** the primary board orders by net PnL/total return as required, while every secondary ranking remains available without deleting or changing trial status.
- **RSI:** compare monotonic, flat, and mixed series against a trusted Wilder reference.
- **Funding cadence:** integrate by elapsed time and event timestamp across 1-minute, 5-minute, irregular, and missing bars.
- **Execution:** cover rejection, partial fill, fill-price slippage, cancel failure, restart, and venue-position reconciliation.
- **Exit parity:** assert equivalent stop, target, and trail decisions in vectorized, event-driven, paper, and live-simulated paths.
- **Registry:** clear and register repeatedly in varying test order.

### 7.2 Research validation

1. Preserve a complete point-in-time dataset with stable row identifiers, provenance, availability timestamps, raw fields, missingness, and corrections.
2. Establish a corrected measurement baseline using next-executable-bar prices, signed funding, actual timeframe, shared capital, and one exit implementation without removing any observations.
3. Report anchored or rolling chronological views across multiple symbols, timeframes, volatility conditions, and funding regimes. These are analytical partitions; every row remains queryable in the full dataset.
4. Store transform parameters with each chronological view and retain both raw and transformed values.
5. Perform feature-family ablations—direction, ADX/slope, compression, microstructure, OI, and funding—while preserving the same row universe and reporting missingness.
6. Use block bootstrap or heteroskedasticity/autocorrelation-aware uncertainty estimates because forward returns and signals overlap, while continuing to expose the unaggregated observations.

Recommended metrics:

- after-cost expectancy and confidence interval;
- probability Brier score and log loss;
- rank information coefficient where appropriate;
- turnover, fill rate, slippage, and funding contribution;
- maximum drawdown and tail loss;
- regime flip rate, transition latency, and calibration by score bucket;
- raw signal count and executed opportunity count relative to baseline.

### 7.3 Non-gating evidence checks

These checks describe evidence quality; they do not promote, suppress, or remove research outputs:

- report prefix and representation invariance results;
- prove that all source rows, feature rows, raw entries, and outcomes remain available;
- report conditional results across every symbol, period, and feature family, including adverse and inconclusive cases;
- expose feature availability, missingness, freshness, contributions, and transformation parameters;
- show raw observations beside aggregate estimates and uncertainty intervals;
- label hypotheses and counterfactual policy arms without selecting a winner automatically.

I do not have verified information on which performance, drawdown, turnover, or latency outcomes the researcher considers desirable. The platform should expose those measurements rather than encode my preference as a restriction.

### 7.4 Parallel analysis and reproducibility

- Keep the unrestricted baseline as an immutable result series.
- Add regime annotations and any explicitly requested counterfactual policy as separate series on identical row identifiers.
- Reconcile research, paper, and live-simulated accounting bar by bar without changing raw signals.
- Make every transformation reversible or reproducible from stored parameters and raw inputs.
- Treat fill reconciliation, reduce-only closing behavior, and protective-exit parity as execution-correctness checks only; they must not alter the raw research signal series or hide opportunity data.

## 8. Trade-off matrix

| Option | What it reveals | Main risk | Complexity | Default platform treatment |
|---|---|---|---|---|
| Preserve current outputs unchanged | Provides a historical comparison point. | Existing metrics and execution state may remain unreliable. | None | Retain as a labeled legacy baseline, not as hidden truth. |
| Correct accounting/execution bugs | Shows results under intended accounting and execution semantics without filtering signals. | Reported historical performance may decline after removing optimistic artifacts. | Medium | Add a corrected series while preserving the legacy series for comparison. |
| Calculate regime-gated counterfactuals | Quantifies what a specified gate would include and exclude. | Can invite selection bias or be mistaken for the unrestricted baseline. | Low-to-medium | Only as an explicitly researcher-defined, separately labeled arm with excluded opportunities reported. |
| Calculate regime-based sizing counterfactuals | Shows how an allocation hypothesis changes exposure on the same signals. | Adds model, turnover, and interpretation risk. | Medium | Separate result series only; detector does not apply it automatically. |
| Add a probabilistic multi-axis regime model | Exposes richer simultaneous evidence and uncertainty. | Higher data, validation, and maintenance burden. | High | Append outputs and retain every component, raw row, and legacy label. |
| Activate OI/funding/premium data | Restores intended derivatives evidence and missingness visibility. | Point-in-time joins and feed quality can introduce leakage. | Medium-to-high | Preserve raw events, provenance, missingness, and all transformed views. |

## 9. Verification evidence from this assessment

### Completed checks

- Focused regime, advanced-module, live client, paper funding, and ML window tests: **17 passed in 4.45 seconds**.
- Rust TUI test suite: **passed** one integration test.
- Registry ordering reproduction: **one pass, one failure**, confirming `impulse_1m_long` can disappear after registry clearing.
- Direct probes reproduced:
  - rising-series RSI tail fixed at 50;
  - unused ADX threshold;
  - six prefix-invariance regime mismatches;
  - nine index-representation regime mismatches;
  - inactive research funding preset path;
  - false five-minute provenance gaps;
  - success-shaped venue error result;
  - incorrect bear-state Sharpe interpretation.

### Incomplete check

The full offline Python suite was interrupted after approximately 252 seconds because spawned Ray processes stalled while attempting external downloads. At interruption, the observed result was **1 failed, 89 passed, 4 deselected, 9 warnings**. This is not a complete-suite pass and must not be represented as one. The isolated failure was the reproducible strategy-registry issue described above.

### Repository state

The assessment did not alter application or test code. A separate untracked document named `docs/assessment-2026-07-24-bugs-and-regime-fidelity.md` already existed before this report was saved and was left untouched.

## 10. Open decisions

1. What drawdown, turnover, and latency changes are acceptable for adaptive sizing?
2. Which venue and contract should define the canonical point-in-time funding, OI, premium, and order-book feeds?
3. Should the first implementation milestone focus exclusively on accounting/execution parity, or also append the causal regime research columns?
4. Which complete-data views and cross-symbol/cross-period breakdowns are most useful to the researcher?

These decisions affect presentation and experiment ordering. They do not authorize the platform or this assessment to restrict data, signals, opportunities, or research outputs.
