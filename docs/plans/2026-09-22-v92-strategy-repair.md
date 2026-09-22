# V92 strategy repair implementation plan

**Goal:** Produce a tested, reviewable correction for extended breakout entries,
missing trend participation, and pre-profit loss exposure, with measured economic
results. Keep the authorized V91 drain and supervisor hold intact.

**Architecture:** Reuse the existing completed-bar signal projection and shared
portfolio simulator. Version candidate entry rules independently from V91.
Add explicit optional stop-risk sizing to the existing execution contract, and
compare a bounded failed-followthrough exit on identical recorded entries.

**Stack:** Typed Python, pandas, existing Hypervector execution contracts and
pytest; Rust cockpit compatibility checks for any emitted contract changes.

## Facts and uncertainty

High confidence: SNDK entered at 1,895.50 after a completed hourly close at
1,897.10, against a prior entry-channel high of 1,793.70 and ATR 21.69156.
The signal close was 4.7668 ATR beyond the channel. There was no entry distance
limit. Its approximately $43 initial gross stop risk matched existing sizing.
Exact replay reproduced all 247 adaptive states. No crypto entry qualified.
These observations do not establish profitable replacement parameters.

## Frozen research contract, before V92 results

- Universe: BTC, ETH, SOL, HYPE, xyz:SPCX, xyz:SNDK, xyz:BRENTOIL, xyz:TSLA.
- Primary historical inputs: existing 15m stitched venue candles and recorded
  funding from the V90 expansion bundle. Print exact coverage, gaps and hashes.
  These inputs were examined by prior research: chronological blocks are
  historical robustness checks, **not a newly sealed holdout**.
- Signals use completed bars only, execute at next bar open, reset indicator
  history at gaps and refuse entries with non-finite ATR.
- Candidate A: hourly Donchian 20/10, ATR20x2, unchanged stop and recipe exits,
  with a maximum extension of 1 ATR beyond the prior entry-channel boundary.
  The extension rule refuses only entry; it must not erase an existing exit.
  No threshold sweep.
- Candidate B: persistent hourly EMA21/55 direction, completed close on the
  same side of EMA21, ATR20x2 stop, entry opportunity on every completed hourly
  decision while flat. Both directions reported, long-only separately reported
  for crypto. No EMA period search. Re-entry behavior must be explicit.
- Exit candidate: after at least 30 minutes, close when the current completed
  close is at least 0.5 initial stop risk adverse and maximum completed-close
  favorable excursion stayed below 0.25 initial stop risk. Native stop executes
  first if crossed. Freeze these diagnostic constants; no loss-specific tuning.
- Compare unchanged hourly Donchian, A and B on the same capital/cost assumptions;
  this is a mechanism comparison, not falsely labeled full V91 portfolio parity.
- Costs: existing measured and adverse V90 venue fee/slippage scenarios, actual
  captured funding, same $500 notional cap. Report net PnL, trade counts,
  drawdown, worst trade, block results and buy-and-hold. Report all valid cells.
- Stop-risk sizing: optional explicit dollar budget plus friction allowance,
  capped by existing margin/notional limits. Demonstrate $10 as a **proposal**,
  not an approved live setting. Include adverse entry fill and stop-price
  movement in calculation. Gaps beyond the allowance can exceed the budget.
- The SNDK incident and previously viewed live paths are diagnostic cases only.
  ML remains report-only; prior validation did not establish executable value.

## Task 1: causal entry candidates

Create `src/hypervector/research/v92_entry_candidates.py` and
`tests/test_v92_entry_candidates.py`. Test prefix invariance, first eligible
hour timing, both sides, gap reset, extension boundary, and preservation of
opposite-position exits. Run the tests red, implement, then run green.
Reuse `completed_bar_indicators`, `completed_signal_projection`, and Donchian
builders. Add versioned provider integration only for a measured candidate.

## Task 2: explicit stop-risk sizing

Create `src/hypervector/live/cohort_stop_risk_sizing.py` and tests. Extend
`cohort_execution_plan.py`, `multi_asset_live_profile_values.py`, and the entry
path in `sol_range_onset_engine.py`. Defaults must preserve old fingerprints,
ledger round trips and behavior. Tests must verify long/short, fixed/structural
stop clamps, adverse entry bounds, fees/exit allowance, invalid numbers and no
increase beyond existing notional. Persist the sizing decision before submission.
Use a separate nested typed contract to avoid duplicating scalar fields.

## Task 3: failed-followthrough comparison

Create a pure policy with exact completed-price inputs, then integrate with the
research simulation or matched-entry replay. Test loss before profit activation,
age boundary, recovered winners, short symmetry, gap/stale refusal and native
stop precedence. Do not give it live authority solely because it saves SNDK.

## Task 4: reproducible economic screen

Create `scripts/v92_strategy_repair_screen.py` with explicit input/output paths,
configuration, hashes, recorded trials and no execution clients. Compare all
frozen variants with transaction costs and chronological blocks; maintain warmup
causality. Write a report under `docs/reviews/2026-09-22-v92-strategy-repair.md`.
Report economic failures alongside engineering verification. Do not tune away
an unfavorable result or claim that buying the historical low was possible.

## Task 5: integration and review

Review exact changed files against `.codex-v92-baseline.json`; run focused
causal/risk/recovery tests, relevant provider contracts and Python non-network
suite. Run Rust tests if contract projections change. Verify original V91
profile fingerprint remains identical and the live pause remains intact.
Prepare a concrete candidate/configuration and economic comparison for review;
stage only reviewed changes back into the shared checkout after confirming its
baseline files have not changed. Never revert unrelated work.

## Acceptance and rollback

Technical success means explicit, causally evaluated entry/exit/risk rules,
no legacy behavior drift, auditable amounts, and passing regression checks.
Economic results remain measured outcomes, not implicit trial-abort gates.
If the variants lose after costs, retain that result and do not call profitability
fixed. Keep research and tested infrastructure available while live stays paused.
No live restart, new risk limit, model authority or new strategy is authorized
by this implementation plan itself. Rollback is omission of optional contracts
and continued use of original versioned providers; preserve original ledgers.
